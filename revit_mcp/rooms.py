# -*- coding: UTF-8 -*-
"""
Rooms Module for Revit MCP
Handles room creation and room separation lines
"""

from .utils import (
    get_element_name, get_element_id_value, make_element_id, suppress_warnings,
    parse_request_data, commit_and_report, finalize_outcome, exception_outcome,
)
from .identity import mutation_document_or_response, request_document_selector, attribute_response
from .security import gate_or_response
from pyrevit import routes, revit, DB
from System.Collections.Generic import List
import traceback
import logging

logger = logging.getLogger(__name__)

MM_TO_FEET = 1.0 / 304.8


def _set_step(failed, item, lookup, make_value):
    """Run one secondary Set() step and record why it did not happen (D-12).

    A step the request asked for must never vanish silently: a parameter that is
    missing, read-only, raises on Set or answers False becomes a `failed` entry named
    after the step, which turns the reply into a partial. The room itself is already in
    `succeeded` and stays there.
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


def register_room_routes(api):
    """Register all room routes with the API"""

    def _create_room(doc, request):
        """Create a room at a specified level."""
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

            level_name = data.get("level_name")
            if not level_name:
                return routes.make_response(
                    data={"error": "level_name is required"}, status=400
                )

            # Find the level
            levels = (
                DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_Levels)
                .WhereElementIsNotElementType()
                .ToElements()
            )
            target_level = None
            for lv in levels:
                if get_element_name(lv) == level_name:
                    target_level = lv
                    break

            if not target_level:
                available = [get_element_name(lv) for lv in levels]
                return routes.make_response(
                    data={
                        "error": "Level '{}' not found".format(level_name),
                        "available_levels": available,
                    },
                    status=404,
                )

            # Get the phase — rooms require a phase
            phases = doc.Phases
            if not phases or phases.Size == 0:
                return routes.make_response(
                    data={"error": "No phases found in the project"},
                    status=500,
                )
            phase = phases.get_Item(phases.Size - 1)

            requested = 1
            t = DB.Transaction(doc, "Create Room via MCP")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                location = data.get("location")
                if location:
                    x = float(location.get("x", 0)) * MM_TO_FEET
                    y = float(location.get("y", 0)) * MM_TO_FEET
                    point = DB.UV(x, y)
                    room = doc.Create.NewRoom(target_level, point)
                else:
                    # Create unplaced room first, then Revit associates it
                    room = doc.Create.NewRoom(phase)

                if not room:
                    t.RollBack()
                    return routes.make_response(
                        data={"error": "Failed to create room — no enclosed area found at the specified location. Add walls or room separation lines first.",
                              "outcome": exception_outcome(t, requested, succeeded, failed)},
                        status=500,
                    )

                # Read the id while the room is valid; after a rollback it is not.
                room_id = get_element_id_value(room)
                succeeded.append(room_id)

                # Set name and number if provided; each is its own step (D-12)
                room_name = data.get("name")
                if room_name:
                    _set_step(failed, "name",
                              lambda: room.LookupParameter("Name"),
                              lambda: room_name)

                room_number = data.get("number")
                if room_number:
                    _set_step(failed, "number",
                              lambda: room.LookupParameter("Number"),
                              lambda: room_number)

                commit_result = commit_and_report(t, swallower)
                if not commit_result["committed"]:
                    # Nothing below may read the room: a rolled-back element is invalid.
                    payload, http = finalize_outcome(
                        commit_result, {}, requested, succeeded, failed)
                    return routes.make_response(data=payload, status=http)

                # Get area after commit
                area = 0.0
                try:
                    area_param = room.LookupParameter("Area")
                    if area_param and area_param.HasValue:
                        area = round(area_param.AsDouble() * 0.092903, 2)  # sq ft to sq m
                except Exception:
                    pass

                actual_name = ""
                try:
                    name_p = room.LookupParameter("Name")
                    if name_p:
                        actual_name = name_p.AsString() or ""
                except Exception:
                    pass

                actual_number = ""
                try:
                    number_p = room.LookupParameter("Number")
                    if number_p:
                        actual_number = number_p.AsString() or ""
                except Exception:
                    pass

                reply = {
                    "room_id": room_id,
                    "name": actual_name,
                    "number": actual_number,
                    "level": level_name,
                    "area": area,
                    "message": "Room '{}' created on level '{}'".format(
                        actual_name or actual_number or "Unnamed", level_name
                    ),
                }
                payload, http = finalize_outcome(
                    commit_result, reply, requested, succeeded, failed)
                return routes.make_response(data=payload, status=http)

            except Exception as tx_error:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise tx_error

        except Exception as e:
            logger.error("Failed to create room: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace,
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500
            )

    @api.route("/create_room/", methods=["POST"])
    def create_room_handler(uiapp, doc, request):
        """Create a room at a specified level."""
        # Phase 5 gate (D-01): shared secret and integrity, before anything else.
        gate_refusal = gate_or_response(request)
        if gate_refusal is not None:
            return gate_refusal
        # G1 explicit guard: first, before any document access or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_create_room(document, request), descriptor, uiapp=uiapp)

    def _create_room_separation(doc, request):
        """Create room separation lines."""
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

            lines = data.get("lines", [])
            if not lines:
                return routes.make_response(
                    data={"error": "No lines provided"}, status=400
                )

            # Find the view to create lines in
            view_name = data.get("view_name")
            level_name = data.get("level_name")

            target_view = None
            if view_name:
                views = (
                    DB.FilteredElementCollector(doc)
                    .OfClass(DB.ViewPlan)
                    .WhereElementIsNotElementType()
                    .ToElements()
                )
                for v in views:
                    if get_element_name(v) == view_name:
                        target_view = v
                        break
                if not target_view:
                    return routes.make_response(
                        data={"error": "View '{}' not found".format(view_name)},
                        status=404,
                    )
            else:
                # Use active view if it's a plan view
                active_view = doc.ActiveView
                if hasattr(active_view, "ViewType") and active_view.ViewType in [
                    DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan, DB.ViewType.AreaPlan
                ]:
                    target_view = active_view
                else:
                    return routes.make_response(
                        data={"error": "Active view is not a plan view — specify a view_name or switch to a plan view"},
                        status=400,
                    )

            # Find sketch plane from level
            sketch_plane = None
            if level_name:
                levels = (
                    DB.FilteredElementCollector(doc)
                    .OfCategory(DB.BuiltInCategory.OST_Levels)
                    .WhereElementIsNotElementType()
                    .ToElements()
                )
                for lv in levels:
                    if get_element_name(lv) == level_name:
                        sketch_plane = lv
                        break

            requested = len(lines)
            t = DB.Transaction(doc, "Create Room Separation Lines via MCP")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                created_ids = []
                curve_array = DB.CurveArray()

                for line_def in lines:
                    sp = line_def.get("start_point", {})
                    ep = line_def.get("end_point", {})

                    start = DB.XYZ(
                        float(sp.get("x", 0)) * MM_TO_FEET,
                        float(sp.get("y", 0)) * MM_TO_FEET,
                        float(sp.get("z", 0)) * MM_TO_FEET,
                    )
                    end = DB.XYZ(
                        float(ep.get("x", 0)) * MM_TO_FEET,
                        float(ep.get("y", 0)) * MM_TO_FEET,
                        float(ep.get("z", 0)) * MM_TO_FEET,
                    )

                    line = DB.Line.CreateBound(start, end)
                    curve_array.Append(line)

                # Create room separation lines
                sp_plane = target_view.SketchPlane
                if not sp_plane:
                    # Create a sketch plane from the view's level
                    level_id = target_view.GenLevel.Id if target_view.GenLevel else None
                    if level_id:
                        level_elem = doc.GetElement(level_id)
                        sp_plane = DB.SketchPlane.Create(doc, level_id)

                separator = doc.Create.NewRoomBoundaryLines(
                    sp_plane, curve_array, target_view
                )

                if separator:
                    for elem in separator:
                        created_ids.append(get_element_id_value(elem))
                succeeded.extend(created_ids)

                if not created_ids:
                    # Revit answered no line at all: every requested line failed.
                    for index in range(len(lines)):
                        failed.append({"item": index,
                                       "reason": "NewRoomBoundaryLines created no line"})

                commit_result = commit_and_report(t, swallower)
                reply = {}
                if commit_result["committed"]:
                    reply = {
                        "line_count": len(created_ids),
                        "line_ids": created_ids,
                        "message": "Created {} room separation line{}".format(
                            len(created_ids),
                            "s" if len(created_ids) != 1 else ""
                        ),
                    }
                payload, http = finalize_outcome(
                    commit_result, reply, requested, succeeded, failed)
                return routes.make_response(data=payload, status=http)

            except Exception as tx_error:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise tx_error

        except Exception as e:
            logger.error("Failed to create room separation: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace,
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500
            )

    @api.route("/create_room_separation/", methods=["POST"])
    def create_room_separation_handler(uiapp, doc, request):
        """Create room separation lines."""
        # Phase 5 gate (D-01): shared secret and integrity, before anything else.
        gate_refusal = gate_or_response(request)
        if gate_refusal is not None:
            return gate_refusal
        # G1 explicit guard: first, before any document access or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_create_room_separation(document, request), descriptor, uiapp=uiapp)

    logger.info("Room routes registered successfully")
