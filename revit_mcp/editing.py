# -*- coding: UTF-8 -*-
"""
Editing Module for Revit MCP
Handles element deletion, modification, and selection retrieval
"""

from .utils import get_element_name, make_element_id, get_element_id_value, suppress_warnings, parse_request_data, commit_and_report, finalize_outcome, build_outcome, exception_outcome
from .identity import mutation_document_or_response, request_document_selector, attribute_response
from .lookup import resolve_instance_parameter
from .security import gate_or_response
from pyrevit import routes, revit, DB
import traceback
import logging

logger = logging.getLogger(__name__)


def register_editing_routes(api):
    """Register all editing routes with the API"""

    def _delete_elements(doc, request):
        """Delete one or more elements from the Revit model."""
        # Hoisted so the 500 reply can say what really happened (D-14).
        t = None
        requested = None
        succeeded = []
        failed = []
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document"}, status=503
                )

            # Parse request data
            if not request or not request.data:
                return routes.make_response(
                    data={"error": "No data provided"}, status=400
                )

            data = parse_request_data(request.data)

            element_ids = data.get("element_ids", [])
            if not element_ids:
                return routes.make_response(
                    data={"error": "No element_ids provided"}, status=400
                )

            requested = len(element_ids)

            # Validate all elements exist before deleting. All or nothing (D-05): the
            # first missing id refuses the whole call, so a committed delete removed
            # every requested element and there is never a partial status here.
            elements_to_delete = []
            for eid in element_ids:
                elem_id = make_element_id(eid)
                elem = doc.GetElement(elem_id)
                if not elem:
                    return routes.make_response(
                        data={"error": "Element {} not found in the active model".format(eid)},
                        status=404,
                    )
                elements_to_delete.append(elem_id)

            # Delete in a single transaction
            t = DB.Transaction(doc, "Delete Elements via MCP")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                deleted_ids = []
                cascaded_ids = []

                for elem_id in elements_to_delete:
                    # doc.Delete returns a collection of all deleted IDs (including cascaded)
                    result = doc.Delete(elem_id)
                    primary_id = get_element_id_value(elem_id)
                    deleted_ids.append(primary_id)

                    # Track cascaded deletions
                    if result:
                        for del_id in result:
                            del_id_int = get_element_id_value(del_id)
                            if del_id_int != primary_id and del_id_int not in cascaded_ids:
                                cascaded_ids.append(del_id_int)

                commit_result = commit_and_report(t, swallower)
                if commit_result["committed"]:
                    succeeded.extend(element_ids)

                # Remove primary IDs from cascaded list
                cascaded_ids = [cid for cid in cascaded_ids if cid not in deleted_ids]

                message = "Deleted {} element{}".format(
                    len(deleted_ids),
                    "s" if len(deleted_ids) != 1 else ""
                )
                if cascaded_ids:
                    message += " ({} hosted element{} also removed)".format(
                        len(cascaded_ids),
                        "s" if len(cascaded_ids) != 1 else ""
                    )

                data = {
                    "deleted_count": len(deleted_ids),
                    "deleted_ids": deleted_ids,
                    "cascaded_ids": cascaded_ids,
                    "message": message,
                }
                payload, http = finalize_outcome(
                    commit_result, data, requested, succeeded, failed)
                return routes.make_response(data=payload, status=http)

            except Exception as tx_error:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise tx_error

        except Exception as e:
            logger.error("Failed to delete elements: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace,
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500
            )

    @api.route("/delete_elements/", methods=["POST"])
    def delete_elements_handler(uiapp, doc, request):
        """Delete one or more elements from the Revit model."""
        # Phase 5 gate (D-01): shared secret and integrity, before anything else.
        gate_refusal = gate_or_response(request)
        if gate_refusal is not None:
            return gate_refusal
        # G1 explicit guard: first, before any document access, file output or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_delete_elements(document, request), descriptor, uiapp=uiapp)

    def _modify_element(doc, request):
        """Modify parameter values on a Revit element."""
        # Hoisted so the 500 reply can say what really happened (D-14).
        t = None
        requested = None
        succeeded = []
        outcome_failed = []
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document"}, status=503
                )

            if not request or not request.data:
                return routes.make_response(
                    data={"error": "No data provided"}, status=400
                )

            data = parse_request_data(request.data)

            element_id = data.get("element_id")
            parameters = data.get("parameters", {})

            if element_id is None:
                return routes.make_response(
                    data={"error": "No element_id provided"}, status=400
                )

            if not parameters:
                return routes.make_response(
                    data={"error": "No parameters provided"}, status=400
                )

            requested = len(parameters)

            # Find the element
            elem_id = make_element_id(element_id)
            elem = doc.GetElement(elem_id)
            if not elem:
                return routes.make_response(
                    data={"error": "Element {} not found in the active model".format(element_id)},
                    status=404,
                )

            # Start transaction
            t = DB.Transaction(doc, "Modify Element via MCP")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                changes = []
                failed = []

                def fail(param_name, reason, available=None):
                    # One reason text, two shapes: the legacy `failed` entry and the
                    # D-03 outcome.failed entry (item = the parameter name).
                    entry = {"parameter": param_name, "reason": reason}
                    if available is not None:
                        entry["available_parameters"] = available
                    failed.append(entry)
                    outcome_failed.append({"item": param_name, "reason": reason})

                for param_name, new_value in parameters.items():
                    param = resolve_instance_parameter(elem, param_name)
                    if not param:
                        # List available parameters for better error messages
                        available = []
                        for p in elem.Parameters:
                            try:
                                available.append(p.Definition.Name)
                            except Exception:
                                continue
                        available.sort()
                        fail(param_name, "not found", available[:20])
                        continue

                    if param.IsReadOnly:
                        fail(param_name, "read-only")
                        continue

                    # Get old value
                    old_value = ""
                    try:
                        if param.StorageType == DB.StorageType.String:
                            old_value = param.AsString() or ""
                        elif param.StorageType == DB.StorageType.Integer:
                            old_value = str(param.AsInteger())
                        elif param.StorageType == DB.StorageType.Double:
                            old_value = str(round(param.AsDouble(), 6))
                        elif param.StorageType == DB.StorageType.ElementId:
                            old_value = str(get_element_id_value(param.AsElementId()))
                    except Exception:
                        old_value = ""

                    # Set new value
                    try:
                        if param.StorageType == DB.StorageType.String:
                            param.Set(str(new_value))
                        elif param.StorageType == DB.StorageType.Integer:
                            param.Set(int(new_value))
                        elif param.StorageType == DB.StorageType.Double:
                            param.Set(float(new_value))
                        elif param.StorageType == DB.StorageType.ElementId:
                            param.Set(make_element_id(new_value))
                        else:
                            fail(param_name, "unsupported storage type")
                            continue

                        changes.append({
                            "parameter": param_name,
                            "old_value": old_value,
                            "new_value": str(new_value),
                            "status": "set",
                        })
                        succeeded.append(param_name)
                    except Exception as set_err:
                        fail(param_name, "set failed: {}".format(str(set_err)))

                # t.Commit() can return TransactionStatus.RolledBack silently
                # when _FailureSwallower vetoes an error-severity failure --
                # never discard that return value and report success anyway.
                # See debug session param-write-rolls-back.
                commit_result = commit_and_report(t, swallower)

                if not commit_result["committed"]:
                    logger.error(
                        "modify_element transaction did not commit "
                        "(status={}) for element {}".format(
                            commit_result["transaction_status"], element_id
                        )
                    )
                    return routes.make_response(
                        data={
                            "status": "rolled_back",
                            "element_id": element_id,
                            "attempted_changes": changes,
                            "failed": failed,
                            "transaction_status": commit_result["transaction_status"],
                            "failures": commit_result["failures"],
                            "outcome": build_outcome(
                                commit_result["transaction_status"], requested, [],
                                outcome_failed, commit_result["failures"]),
                            "message": (
                                "Parameter Set() calls succeeded in-transaction, "
                                "but Revit rolled the transaction back at Commit() "
                                "because of the error-severity failure(s) listed "
                                "in 'failures'. No changes were saved to the model."
                            ),
                        },
                        status=409,
                    )

                message = "Modified {} parameter{} on element {}".format(
                    len(changes),
                    "s" if len(changes) != 1 else "",
                    element_id,
                )

                data = {
                    "element_id": element_id,
                    "changes": changes,
                    "failed": failed,
                    "transaction_status": commit_result["transaction_status"],
                    "message": message,
                }
                payload, http = finalize_outcome(
                    commit_result, data, requested, succeeded, outcome_failed)
                return routes.make_response(data=payload, status=http)

            except Exception as tx_error:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise tx_error

        except Exception as e:
            logger.error("Failed to modify element: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace,
                      "outcome": exception_outcome(t, requested, succeeded, outcome_failed)},
                status=500
            )

    @api.route("/modify_element/", methods=["POST"])
    def modify_element_handler(uiapp, doc, request):
        """Modify parameter values on a Revit element."""
        # Phase 5 gate (D-01): shared secret and integrity, before anything else.
        gate_refusal = gate_or_response(request)
        if gate_refusal is not None:
            return gate_refusal
        # G1 explicit guard: first, before any document access, file output or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_modify_element(document, request), descriptor, uiapp=uiapp)

    @api.route("/selected_elements/", methods=["GET"])
    def get_selected_elements_handler(doc, uidoc):
        """Get details of elements currently selected in Revit UI."""
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document"}, status=503
                )

            if not uidoc:
                return routes.make_response(
                    data={"error": "No active UI document"}, status=503
                )

            # Get current selection
            selection = uidoc.Selection.GetElementIds()

            elements = []
            for elem_id in selection:
                elem = doc.GetElement(elem_id)
                if not elem:
                    continue

                elem_info = {
                    "id": get_element_id_value(elem_id),
                    "category": elem.Category.Name if elem.Category else "Unknown",
                    "type": get_element_name(elem),
                }

                # Try to get level
                try:
                    level_id = elem.LevelId
                    if level_id and level_id != DB.ElementId.InvalidElementId:
                        level = doc.GetElement(level_id)
                        if level:
                            elem_info["level"] = get_element_name(level)
                except Exception:
                    pass

                # Get key parameters
                params = {}
                key_param_names = ["Mark", "Comments", "Length", "Area", "Volume", "Width", "Height"]
                for pname in key_param_names:
                    try:
                        p = elem.LookupParameter(pname)
                        if p and p.HasValue:
                            if p.StorageType == DB.StorageType.String:
                                val = p.AsString()
                                if val:
                                    params[pname] = val
                            elif p.StorageType == DB.StorageType.Double:
                                params[pname] = str(round(p.AsDouble(), 4))
                            elif p.StorageType == DB.StorageType.Integer:
                                params[pname] = str(p.AsInteger())
                    except Exception:
                        continue

                if params:
                    elem_info["parameters"] = params

                elements.append(elem_info)

            count = len(elements)
            if count == 0:
                message = "No elements currently selected"
            elif count == 1:
                message = "1 element currently selected"
            else:
                message = "{} elements currently selected".format(count)

            return routes.make_response(
                data={
                    "status": "success",
                    "elements": elements,
                    "count": count,
                    "message": message,
                }
            )

        except Exception as e:
            logger.error("Failed to get selected elements: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace}, status=500
            )

    logger.info("Editing routes registered successfully")
