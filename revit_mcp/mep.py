# -*- coding: UTF-8 -*-
"""
MEP Module for Revit MCP
Handles duct, pipe, and MEP system creation
"""

from .utils import (
    get_element_name, get_element_id_value, make_element_id, suppress_warnings,
    parse_request_data, commit_and_report, finalize_outcome, build_outcome,
    exception_outcome, transaction_status_of,
)
from .identity import mutation_document_or_response, request_document_selector, attribute_response
from pyrevit import routes, revit, DB
import traceback
import logging

logger = logging.getLogger(__name__)

MM_TO_FEET = 1.0 / 304.8


def _set_step(failed, item, lookup, make_value):
    """Run one secondary Set() step and record why it did not happen (D-12).

    A step the request asked for must never vanish silently: a parameter that is
    missing, read-only, raises on Set or answers False becomes a `failed` entry named
    after the step, which turns the reply into a partial. The primary element (the duct,
    the pipe, the system) is already in `succeeded` and stays there.
    """
    try:
        param = lookup()
        if not param:
            failed.append({"item": item, "reason": "parameter not found"})
        elif param.IsReadOnly:
            failed.append({"item": item, "reason": "parameter is read-only"})
        elif param.Set(make_value()) is False:
            failed.append({"item": item, "reason": "Set() returned false"})
    except Exception as step_err:
        failed.append({"item": item, "reason": str(step_err)})


def register_mep_routes(api):
    """Register all MEP routes with the API"""

    def _create_duct(doc, request):
        """Create a duct between two points."""
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

            data = parse_request_data(request.data)

            start_point = data.get("start_point")
            end_point = data.get("end_point")
            if not start_point or not end_point:
                return routes.make_response(
                    data={"error": "start_point and end_point are required"},
                    status=400,
                )

            # Convert points
            start = DB.XYZ(
                float(start_point.get("x", 0)) * MM_TO_FEET,
                float(start_point.get("y", 0)) * MM_TO_FEET,
                float(start_point.get("z", 0)) * MM_TO_FEET,
            )
            end = DB.XYZ(
                float(end_point.get("x", 0)) * MM_TO_FEET,
                float(end_point.get("y", 0)) * MM_TO_FEET,
                float(end_point.get("z", 0)) * MM_TO_FEET,
            )

            # Find duct type
            duct_type_name = data.get("duct_type")
            duct_types = (
                DB.FilteredElementCollector(doc)
                .OfClass(DB.Mechanical.DuctType)
                .ToElements()
            )

            if not duct_types:
                return routes.make_response(
                    data={"error": "No duct types available — load a mechanical template or family first."},
                    status=500,
                )

            target_duct_type = None
            if duct_type_name:
                for dt in duct_types:
                    if get_element_name(dt) == duct_type_name:
                        target_duct_type = dt
                        break
                if not target_duct_type:
                    available = [get_element_name(dt) for dt in duct_types]
                    return routes.make_response(
                        data={
                            "error": "Duct type '{}' not found".format(duct_type_name),
                            "available_duct_types": available,
                        },
                        status=404,
                    )
            else:
                target_duct_type = duct_types[0]

            # Find mechanical system type
            system_type_name = data.get("system_type")
            mech_system_types = (
                DB.FilteredElementCollector(doc)
                .OfClass(DB.Mechanical.MechanicalSystemType)
                .ToElements()
            )

            target_system_type = None
            if mech_system_types:
                if system_type_name:
                    for st in mech_system_types:
                        if get_element_name(st) == system_type_name:
                            target_system_type = st
                            break
                if not target_system_type:
                    target_system_type = mech_system_types[0]

            # Find level
            level_name = data.get("level_name")
            levels = (
                DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_Levels)
                .WhereElementIsNotElementType()
                .ToElements()
            )
            target_level = None
            if level_name:
                for lv in levels:
                    if get_element_name(lv) == level_name:
                        target_level = lv
                        break
            if not target_level and levels:
                # Use nearest level by elevation
                z_elev = start.Z
                target_level = min(levels, key=lambda lv: abs(lv.Elevation - z_elev))

            if not target_level:
                return routes.make_response(
                    data={"error": "No levels found in the project"},
                    status=500,
                )

            requested = 1
            t = DB.Transaction(doc, "Create Duct via MCP")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                sys_type_id = target_system_type.Id if target_system_type else DB.ElementId.InvalidElementId
                duct = DB.Mechanical.Duct.Create(
                    doc,
                    sys_type_id,
                    target_duct_type.Id,
                    target_level.Id,
                    start,
                    end,
                )
                # Read the id while the element is valid; after a rollback it is not.
                duct_id = get_element_id_value(duct)
                succeeded.append(duct_id)

                # Set diameter or dimensions if specified; each is its own step (D-12)
                diameter = data.get("diameter")
                width = data.get("width")
                height = data.get("height")

                if diameter:
                    _set_step(failed, "diameter",
                              lambda: duct.LookupParameter("Diameter"),
                              lambda: float(diameter) * MM_TO_FEET)

                if width:
                    _set_step(failed, "width",
                              lambda: duct.LookupParameter("Width"),
                              lambda: float(width) * MM_TO_FEET)

                if height:
                    _set_step(failed, "height",
                              lambda: duct.LookupParameter("Height"),
                              lambda: float(height) * MM_TO_FEET)

                commit_result = commit_and_report(t, swallower)
                reply = {}
                if commit_result["committed"]:
                    reply = {
                        "duct_id": duct_id,
                        "system_type": get_element_name(target_system_type) if target_system_type else "None",
                        "duct_type": get_element_name(target_duct_type),
                        "level": get_element_name(target_level),
                        "message": "Created duct on level '{}'".format(get_element_name(target_level)),
                    }
                payload, http = finalize_outcome(
                    commit_result, reply, requested, succeeded, failed)
                return routes.make_response(data=payload, status=http)

            except Exception as tx_error:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise tx_error

        except Exception as e:
            logger.error("Failed to create duct: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace,
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500
            )

    @api.route("/create_duct/", methods=["POST"])
    def create_duct_handler(uiapp, doc, request):
        """Create a duct between two points."""
        # G1 explicit guard: first, before any document access or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_create_duct(document, request), descriptor, uiapp=uiapp)

    def _create_pipe(doc, request):
        """Create a pipe between two points."""
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

            data = parse_request_data(request.data)

            start_point = data.get("start_point")
            end_point = data.get("end_point")
            if not start_point or not end_point:
                return routes.make_response(
                    data={"error": "start_point and end_point are required"},
                    status=400,
                )

            start = DB.XYZ(
                float(start_point.get("x", 0)) * MM_TO_FEET,
                float(start_point.get("y", 0)) * MM_TO_FEET,
                float(start_point.get("z", 0)) * MM_TO_FEET,
            )
            end = DB.XYZ(
                float(end_point.get("x", 0)) * MM_TO_FEET,
                float(end_point.get("y", 0)) * MM_TO_FEET,
                float(end_point.get("z", 0)) * MM_TO_FEET,
            )

            # Find pipe type
            pipe_type_name = data.get("pipe_type")
            pipe_types = (
                DB.FilteredElementCollector(doc)
                .OfClass(DB.Plumbing.PipeType)
                .ToElements()
            )

            if not pipe_types:
                return routes.make_response(
                    data={"error": "No pipe types available — load a plumbing template or family first."},
                    status=500,
                )

            target_pipe_type = None
            if pipe_type_name:
                for pt in pipe_types:
                    if get_element_name(pt) == pipe_type_name:
                        target_pipe_type = pt
                        break
                if not target_pipe_type:
                    available = [get_element_name(pt) for pt in pipe_types]
                    return routes.make_response(
                        data={
                            "error": "Pipe type '{}' not found".format(pipe_type_name),
                            "available_pipe_types": available,
                        },
                        status=404,
                    )
            else:
                target_pipe_type = pipe_types[0]

            # Find piping system type
            system_type_name = data.get("system_type")
            piping_system_types = (
                DB.FilteredElementCollector(doc)
                .OfClass(DB.Plumbing.PipingSystemType)
                .ToElements()
            )

            target_system_type = None
            if piping_system_types:
                if system_type_name:
                    for st in piping_system_types:
                        if get_element_name(st) == system_type_name:
                            target_system_type = st
                            break
                if not target_system_type:
                    target_system_type = piping_system_types[0]

            # Find level
            level_name = data.get("level_name")
            levels = (
                DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_Levels)
                .WhereElementIsNotElementType()
                .ToElements()
            )
            target_level = None
            if level_name:
                for lv in levels:
                    if get_element_name(lv) == level_name:
                        target_level = lv
                        break
            if not target_level and levels:
                z_elev = start.Z
                target_level = min(levels, key=lambda lv: abs(lv.Elevation - z_elev))

            if not target_level:
                return routes.make_response(
                    data={"error": "No levels found in the project"},
                    status=500,
                )

            requested = 1
            t = DB.Transaction(doc, "Create Pipe via MCP")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                sys_type_id = target_system_type.Id if target_system_type else DB.ElementId.InvalidElementId
                pipe = DB.Plumbing.Pipe.Create(
                    doc,
                    sys_type_id,
                    target_pipe_type.Id,
                    target_level.Id,
                    start,
                    end,
                )
                # Read the id while the element is valid; after a rollback it is not.
                pipe_id = get_element_id_value(pipe)
                succeeded.append(pipe_id)

                # Set diameter if specified; its own step (D-12)
                diameter = data.get("diameter")
                if diameter:
                    _set_step(failed, "diameter",
                              lambda: pipe.LookupParameter("Diameter"),
                              lambda: float(diameter) * MM_TO_FEET)

                commit_result = commit_and_report(t, swallower)
                reply = {}
                if commit_result["committed"]:
                    reply = {
                        "pipe_id": pipe_id,
                        "system_type": get_element_name(target_system_type) if target_system_type else "None",
                        "pipe_type": get_element_name(target_pipe_type),
                        "level": get_element_name(target_level),
                        "message": "Created pipe on level '{}'".format(get_element_name(target_level)),
                    }
                payload, http = finalize_outcome(
                    commit_result, reply, requested, succeeded, failed)
                return routes.make_response(data=payload, status=http)

            except Exception as tx_error:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise tx_error

        except Exception as e:
            logger.error("Failed to create pipe: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace,
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500
            )

    @api.route("/create_pipe/", methods=["POST"])
    def create_pipe_handler(uiapp, doc, request):
        """Create a pipe between two points."""
        # G1 explicit guard: first, before any document access or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_create_pipe(document, request), descriptor, uiapp=uiapp)

    def _create_mep_system(doc, request):
        """Create a mechanical or piping system."""
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

            data = parse_request_data(request.data)

            system_type = data.get("system_type")
            system_name = data.get("system_name")

            if not system_type:
                return routes.make_response(
                    data={"error": "system_type is required (mechanical or piping)"},
                    status=400,
                )
            if not system_name:
                return routes.make_response(
                    data={"error": "system_name is required"},
                    status=400,
                )
            if system_type not in ("mechanical", "piping"):
                return routes.make_response(
                    data={"error": "system_type must be 'mechanical' or 'piping'"},
                    status=400,
                )

            # Collect element IDs if provided
            element_ids = data.get("element_ids", [])
            connector_set = None

            if element_ids:
                # Get connectors from the specified elements
                for eid in element_ids:
                    elem_id = make_element_id(eid)
                    elem = doc.GetElement(elem_id)
                    if not elem:
                        return routes.make_response(
                            data={"error": "Element {} not found".format(eid)},
                            status=404,
                        )

            requested = 1
            t = DB.Transaction(doc, "Create MEP System via MCP")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                new_system = None

                if not element_ids:
                    t.RollBack()
                    return routes.make_response(
                        data={
                            "error": "element_ids is required. Provide IDs of ducts/pipes to group into a system.",
                            "hint": "Create ducts or pipes first, then group them.",
                        },
                        status=400,
                    )

                # Find existing MEP systems from the provided elements
                existing_systems = set()
                for eid in element_ids:
                    elem = doc.GetElement(make_element_id(eid))
                    if not elem:
                        continue
                    # Check connectors for existing system assignments
                    conn_mgr = None
                    if hasattr(elem, "ConnectorManager"):
                        conn_mgr = elem.ConnectorManager
                    elif hasattr(elem, "MEPModel") and elem.MEPModel:
                        conn_mgr = elem.MEPModel.ConnectorManager
                    if conn_mgr:
                        for c in conn_mgr.Connectors:
                            if hasattr(c, "MEPSystem") and c.MEPSystem:
                                existing_systems.add(get_element_id_value(c.MEPSystem))

                if existing_systems:
                    # Rename the first existing system
                    sys_id = list(existing_systems)[0]
                    new_system = doc.GetElement(make_element_id(sys_id))
                    if new_system:
                        renamed = new_system
                        _set_step(
                            failed, "system_name",
                            lambda: (renamed.LookupParameter("System Name")
                                     or renamed.LookupParameter("Comments")),
                            lambda: system_name)
                else:
                    # Try to create a new system with unused connectors
                    first_connector = None
                    unused_connectors = DB.ConnectorSet()
                    for eid in element_ids:
                        elem = doc.GetElement(make_element_id(eid))
                        if not elem:
                            continue
                        conn_mgr = None
                        if hasattr(elem, "ConnectorManager"):
                            conn_mgr = elem.ConnectorManager
                        elif hasattr(elem, "MEPModel") and elem.MEPModel:
                            conn_mgr = elem.MEPModel.ConnectorManager
                        if conn_mgr:
                            for c in conn_mgr.Connectors:
                                if not hasattr(c, "MEPSystem") or not c.MEPSystem:
                                    unused_connectors.Insert(c)
                                    if not first_connector:
                                        first_connector = c

                    if first_connector:
                        if system_type == "mechanical":
                            duct_enum = DB.Mechanical.DuctSystemType.SupplyAir
                            new_system = doc.Create.NewMechanicalSystem(
                                first_connector, unused_connectors, duct_enum
                            )
                        elif system_type == "piping":
                            pipe_enum = DB.Plumbing.PipeSystemType.DomesticHotWater
                            new_system = doc.Create.NewPipingSystem(
                                first_connector, unused_connectors, pipe_enum
                            )
                    else:
                        t.RollBack()
                        return routes.make_response(
                            data={
                                "error": "All connectors are already assigned to systems and could not be renamed.",
                                "outcome": exception_outcome(t, requested, succeeded, failed),
                            },
                            status=500,
                        )

                    # Name the system Revit just created (the rename branch above
                    # already ran its own name step).
                    if new_system:
                        created = new_system
                        _set_step(
                            failed, "system_name",
                            lambda: created.LookupParameter("System Name"),
                            lambda: system_name)

                if not new_system:
                    # Nothing to group: undo instead of committing an empty
                    # transaction, and say so (D-15).
                    t.RollBack()
                    reason = "Revit created no {} system from the given elements".format(system_type)
                    return routes.make_response(
                        data={
                            "status": "failed",
                            "error": reason,
                            "message": reason,
                            "outcome": build_outcome(
                                transaction_status_of(t), requested, [],
                                [{"item": "system", "reason": reason}],
                                list(swallower.failures) if swallower is not None else []),
                        },
                        status=422,
                    )

                # Read the id while the element is valid; after a rollback it is not.
                system_id = get_element_id_value(new_system)
                succeeded.append(system_id)

                commit_result = commit_and_report(t, swallower)
                reply = {}
                if commit_result["committed"]:
                    reply = {
                        "system_id": system_id,
                        "system_name": system_name,
                        "system_type": system_type,
                        "element_count": len(element_ids),
                        "message": "Created {} system '{}'".format(system_type, system_name),
                    }
                payload, http = finalize_outcome(
                    commit_result, reply, requested, succeeded, failed)
                return routes.make_response(data=payload, status=http)

            except Exception as tx_error:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise tx_error

        except Exception as e:
            logger.error("Failed to create MEP system: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace,
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500
            )

    @api.route("/create_mep_system/", methods=["POST"])
    def create_mep_system_handler(uiapp, doc, request):
        """Create a mechanical or piping system."""
        # G1 explicit guard: first, before any document access or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_create_mep_system(document, request), descriptor, uiapp=uiapp)

    logger.info("MEP routes registered successfully")
