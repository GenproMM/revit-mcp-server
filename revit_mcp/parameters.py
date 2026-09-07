# -*- coding: UTF-8 -*-
"""
Parameters Module for Revit MCP
Handles reading element properties and setting parameter values
"""

from .utils import (
    get_element_name, get_element_id_value, make_element_id, suppress_warnings,
    sanitize_value,
)
from pyrevit import routes, revit, DB
import json
import traceback
import logging

logger = logging.getLogger(__name__)


# Lives in textutils so the text-type aliases are declared once and stay unit
# tested; this module keeps the short local name its call sites already use.
_safe_str = sanitize_value


# A parameter's origin is encoded in the ForgeTypeId that
# InternalDefinition.GetTypeId() returns:
#   revit.local.shared:<guid>-<version>   -> shared parameter
#   revit.local.project:<guid>-<version>  -> plain (non-shared) project parameter
# This is the ONLY reliable test. Do not check for DB.ExternalDefinition:
# BindingMap always yields InternalDefinition, because a shared parameter
# acquires an internal definition the moment it is loaded into a project, so
# that check reports "not shared" for every parameter including ADSK_* ones.
_SHARED_TYPEID_PREFIX = "revit.local.shared"
_PROJECT_TYPEID_PREFIX = "revit.local.project"


def _get_definition_type_id(definition):
    """Return the ForgeTypeId string of a Definition, or None if unavailable."""
    try:
        type_id = definition.GetTypeId()
        if type_id is None:
            return None
        return type_id.TypeId or None
    except Exception:
        return None


def _classify_definition(definition):
    """Classify a parameter Definition by origin.

    Returns (is_shared, guid, type_id) where is_shared is True for a shared
    parameter, False for a plain project parameter, and None when the origin
    cannot be determined (older API, or a built-in parameter). guid is the
    shared parameter's GUID (hex, no dashes) and is None unless is_shared.
    """
    type_id = _get_definition_type_id(definition)
    if type_id:
        lowered = type_id.lower()
        if lowered.startswith(_SHARED_TYPEID_PREFIX):
            guid = None
            remainder = type_id.split(":", 1)[1] if ":" in type_id else ""
            if remainder:
                guid = remainder.split("-")[0] or None
            return True, guid, type_id
        if lowered.startswith(_PROJECT_TYPEID_PREFIX):
            return False, None, type_id
    return None, None, type_id


def _get_binding_kind(binding):
    """Return 'instance' or 'type' for a parameter binding."""
    try:
        if isinstance(binding, DB.InstanceBinding):
            return "instance"
        if isinstance(binding, DB.TypeBinding):
            return "type"
    except Exception:
        pass
    return _safe_str(type(binding).__name__)


def _get_binding_categories(binding):
    """Return the sorted category names a binding applies to."""
    names = []
    try:
        for category in binding.Categories:
            try:
                names.append(_safe_str(category.Name))
            except Exception:
                continue
    except Exception:
        pass
    return sorted(names)


def _get_definition_data_type(definition):
    """Get a Definition's data type label safely across Revit versions."""
    try:
        # Revit 2022+ (spec ForgeTypeId)
        if hasattr(definition, "GetDataType"):
            return _safe_str(DB.LabelUtils.GetLabelForSpec(definition.GetDataType()))
    except Exception:
        pass
    try:
        # Older Revit
        if hasattr(definition, "ParameterType"):
            return _safe_str(definition.ParameterType)
    except Exception:
        pass
    return "Unknown"


def _get_definition_group_name(definition):
    """Get a Definition's group label safely across Revit versions."""
    try:
        # Revit 2024+
        if hasattr(definition, "GetGroupTypeId"):
            return _safe_str(
                DB.LabelUtils.GetLabelForGroup(definition.GetGroupTypeId())
            )
    except Exception:
        pass
    try:
        # Older Revit
        if hasattr(definition, "ParameterGroup"):
            return _safe_str(definition.ParameterGroup)
    except Exception:
        pass
    return "Other"


def _name_prefix(name):
    """The namespace prefix of a parameter name — text before the first '_'."""
    if name and "_" in name:
        return name.split("_")[0]
    return "(none)"


def _as_bool(value):
    """Interpret a query-string value as a boolean."""
    if value is None:
        return False
    return _safe_str(value).strip().lower() in ("1", "true", "yes", "on")


def _get_param_group_name(param):
    """Get the parameter group name safely across Revit versions."""
    try:
        # Revit 2024+
        if hasattr(param.Definition, "GetGroupTypeId"):
            group_id = param.Definition.GetGroupTypeId()
            return _safe_str(DB.LabelUtils.GetLabelForGroup(group_id))
        # Older Revit
        if hasattr(param.Definition, "ParameterGroup"):
            return _safe_str(param.Definition.ParameterGroup)
    except Exception:
        pass
    return "Other"


def _get_param_value_display(param, doc):
    """Get a display-friendly parameter value."""
    try:
        if not param.HasValue:
            return ""
        if param.StorageType == DB.StorageType.String:
            return _safe_str(param.AsString() or "")
        elif param.StorageType == DB.StorageType.Integer:
            display = param.AsValueString()
            if display:
                return _safe_str(display)
            return str(param.AsInteger())
        elif param.StorageType == DB.StorageType.Double:
            display = param.AsValueString()
            if display:
                return _safe_str(display)
            return str(round(param.AsDouble(), 6))
        elif param.StorageType == DB.StorageType.ElementId:
            eid = param.AsElementId()
            if eid and eid != DB.ElementId.InvalidElementId:
                elem = doc.GetElement(eid)
                if elem:
                    return _safe_str(get_element_name(elem))
            return ""
    except Exception:
        return ""
    return ""


def register_parameter_routes(api):
    """Register all parameter routes with the API"""

    @api.route("/project_parameters/", methods=["GET"])
    def get_project_parameters_handler(
        doc, shared_only=None, prefix=None, search=None, summary_only=None
    ):
        """List the project parameters bound in this document.

        Query params (all optional): shared_only, prefix, search, summary_only.
        """
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document"}, status=503
                )

            want_shared_only = _as_bool(shared_only)
            want_summary_only = _as_bool(summary_only)
            prefix_filter = _safe_str(prefix) if prefix else None
            search_filter = _safe_str(search).lower() if search else None

            rows = []
            skipped = 0
            iterator = doc.ParameterBindings.ForwardIterator()
            iterator.Reset()
            while iterator.MoveNext():
                try:
                    definition = iterator.Key
                    binding = iterator.Current
                    is_shared, guid, type_id = _classify_definition(definition)
                    rows.append({
                        "name": _safe_str(definition.Name),
                        "is_shared": is_shared,
                        "guid": guid,
                        "binding": _get_binding_kind(binding),
                        "data_type": _get_definition_data_type(definition),
                        "group": _get_definition_group_name(definition),
                        "categories": _get_binding_categories(binding),
                        "type_id": _safe_str(type_id),
                    })
                except Exception as row_error:
                    # One unreadable binding must not sink the whole listing.
                    skipped += 1
                    logger.warning(
                        "Skipped a parameter binding: {}".format(str(row_error))
                    )

            shared_prefixes = {}
            non_shared_prefixes = {}
            for row in rows:
                bucket = None
                if row["is_shared"] is True:
                    bucket = shared_prefixes
                elif row["is_shared"] is False:
                    bucket = non_shared_prefixes
                if bucket is not None:
                    key = _name_prefix(row["name"])
                    bucket[key] = bucket.get(key, 0) + 1

            summary = {
                "total": len(rows),
                "shared": len([r for r in rows if r["is_shared"] is True]),
                "non_shared": len([r for r in rows if r["is_shared"] is False]),
                "unclassified": len([r for r in rows if r["is_shared"] is None]),
                "skipped": skipped,
                "shared_prefixes": shared_prefixes,
                "non_shared_prefixes": non_shared_prefixes,
            }

            selected = rows
            if want_shared_only:
                selected = [r for r in selected if r["is_shared"] is True]
            if prefix_filter:
                selected = [
                    r for r in selected if r["name"].startswith(prefix_filter)
                ]
            if search_filter:
                selected = [
                    r for r in selected if search_filter in r["name"].lower()
                ]
            selected = sorted(selected, key=lambda r: r["name"])

            data = {
                "status": "success",
                "summary": summary,
                "filter": {
                    "shared_only": want_shared_only,
                    "prefix": prefix_filter,
                    "search": _safe_str(search) if search else None,
                    "summary_only": want_summary_only,
                },
                "returned_count": 0 if want_summary_only else len(selected),
            }
            if not want_summary_only:
                data["parameters"] = selected

            return routes.make_response(data=data)

        except Exception as e:
            logger.error("Failed to list project parameters: {}".format(str(e)))
            return routes.make_response(
                data={"error": str(e), "traceback": traceback.format_exc()},
                status=500,
            )

    @api.route("/element_properties/<element_id>", methods=["GET"])
    def get_element_properties_handler(doc, element_id):
        """Get all properties and parameters of an element."""
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document"}, status=503
                )

            elem_id = make_element_id(int(element_id))
            elem = doc.GetElement(elem_id)
            if not elem:
                return routes.make_response(
                    data={"error": "Element not found."},
                    status=404,
                )

            category = ""
            try:
                if elem.Category:
                    category = _safe_str(elem.Category.Name)
            except Exception:
                pass

            family = ""
            type_name = ""
            try:
                type_id = elem.GetTypeId()
                if type_id and type_id != DB.ElementId.InvalidElementId:
                    elem_type = doc.GetElement(type_id)
                    if elem_type:
                        type_name = _safe_str(get_element_name(elem_type))
                        if hasattr(elem_type, "Family") and elem_type.Family:
                            family = _safe_str(get_element_name(elem_type.Family))
                        elif hasattr(elem_type, "FamilyName"):
                            family = _safe_str(elem_type.FamilyName)
            except Exception:
                pass

            # Collect instance parameters
            parameters = []
            seen_names = set()

            for param in elem.GetOrderedParameters():
                try:
                    param_name = _safe_str(param.Definition.Name)
                    if param_name in seen_names:
                        continue
                    seen_names.add(param_name)

                    parameters.append({
                        "name": param_name,
                        "value": _safe_str(_get_param_value_display(param, doc)),
                        "storage_type": str(param.StorageType),
                        "read_only": param.IsReadOnly,
                        "group": _safe_str(_get_param_group_name(param)),
                        "is_instance": True,
                    })
                except Exception:
                    continue

            # Collect type parameters
            try:
                type_id = elem.GetTypeId()
                if type_id and type_id != DB.ElementId.InvalidElementId:
                    elem_type = doc.GetElement(type_id)
                    if elem_type:
                        for param in elem_type.GetOrderedParameters():
                            try:
                                param_name = _safe_str(param.Definition.Name)
                                if param_name in seen_names:
                                    continue
                                seen_names.add(param_name)

                                parameters.append({
                                    "name": param_name,
                                    "value": _safe_str(_get_param_value_display(param, doc)),
                                    "storage_type": str(param.StorageType),
                                    "read_only": param.IsReadOnly,
                                    "group": _safe_str(_get_param_group_name(param)),
                                    "is_instance": False,
                                })
                            except Exception:
                                continue
            except Exception:
                pass

            return routes.make_response(
                data={
                    "status": "success",
                    "element_id": int(element_id),
                    "category": category,
                    "family": family,
                    "type": type_name,
                    "parameters": parameters,
                    "parameter_count": len(parameters),
                    "message": "Found {} parameters on element {}".format(
                        len(parameters), element_id
                    ),
                }
            )

        except Exception as e:
            logger.error("Failed to get element properties: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace}, status=500
            )

    @api.route("/set_parameter/", methods=["POST"])
    def set_parameter_handler(doc, request):
        """Set a single parameter value on an element."""
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document"}, status=503
                )

            data = json.loads(request.data) if isinstance(request.data, str) else request.data

            element_id = data.get("element_id")
            parameter_name = data.get("parameter_name")
            value = data.get("value")

            if element_id is None:
                return routes.make_response(
                    data={"error": "element_id is required"}, status=400
                )
            if not parameter_name:
                return routes.make_response(
                    data={"error": "parameter_name is required"}, status=400
                )
            if value is None:
                return routes.make_response(
                    data={"error": "value is required"}, status=400
                )

            elem_id = make_element_id(element_id)
            elem = doc.GetElement(elem_id)
            if not elem:
                return routes.make_response(
                    data={"error": "Element {} not found".format(element_id)},
                    status=404,
                )

            # Find the parameter
            param = elem.LookupParameter(parameter_name)
            if not param:
                # Try type parameters
                type_id = elem.GetTypeId()
                if type_id and type_id != DB.ElementId.InvalidElementId:
                    elem_type = doc.GetElement(type_id)
                    if elem_type:
                        param = elem_type.LookupParameter(parameter_name)

            if not param:
                available = []
                for p in elem.Parameters:
                    try:
                        available.append(p.Definition.Name)
                    except Exception:
                        continue
                available.sort()
                return routes.make_response(
                    data={
                        "error": "Parameter '{}' not found on element {}".format(
                            parameter_name, element_id
                        ),
                        "available_parameters": available[:30],
                    },
                    status=404,
                )

            if param.IsReadOnly:
                return routes.make_response(
                    data={"error": "Parameter '{}' is read-only and cannot be modified.".format(parameter_name)},
                    status=500,
                )

            # Get old value
            old_value = _get_param_value_display(param, doc)

            t = DB.Transaction(doc, "Set Parameter via MCP")
            t.Start()
            suppress_warnings(t)

            try:
                # Set value based on storage type
                if param.StorageType == DB.StorageType.String:
                    param.Set(str(value))
                elif param.StorageType == DB.StorageType.Integer:
                    param.Set(int(value))
                elif param.StorageType == DB.StorageType.Double:
                    param.Set(float(value))
                elif param.StorageType == DB.StorageType.ElementId:
                    param.Set(make_element_id(value))

                t.Commit()

                new_value = _get_param_value_display(param, doc)

                return routes.make_response(
                    data={
                        "status": "success",
                        "element_id": int(element_id),
                        "parameter_name": parameter_name,
                        "old_value": old_value,
                        "new_value": str(value),
                        "message": "Set '{}' from '{}' to '{}' on element {}".format(
                            parameter_name, old_value, value, element_id
                        ),
                    }
                )

            except Exception as tx_error:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise tx_error

        except Exception as e:
            logger.error("Failed to set parameter: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace}, status=500
            )

    logger.info("Parameter routes registered successfully")
