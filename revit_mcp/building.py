# -*- coding: UTF-8 -*-
"""
Building Module for Revit MCP
Handles creation of line-based elements (walls, beams), surface-based
elements (floors, roofs, ceilings), and levels.
"""

from .utils import (
    get_element_name, get_element_id_value, suppress_warnings, parse_request_data,
    commit_and_report, finalize_outcome, exception_outcome,
)
from .identity import mutation_document_or_response, request_document_selector, attribute_response
from .security import gate_or_response
from pyrevit import routes, revit, DB
from System.Collections.Generic import List
import traceback
import logging

logger = logging.getLogger(__name__)


def register_building_routes(api):
    """Register all building creation routes with the API"""

    def _create_line_based(doc, request):
        """
        Create line-based elements (walls, beams) in the Revit model (runs on the guarded document).
        Supports batch creation via elements array.
        """
        # Hoisted so the 500 reply can say what really happened (D-14).
        t = None
        requested = None
        succeeded = []
        failed = []
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document — open a project in Revit"},
                    status=503,
                )

            data = parse_request_data(request.data)
            elements = data.get("elements", [])

            if not elements:
                return routes.make_response(
                    data={"error": "No elements provided — pass an array of element definitions"},
                    status=400,
                )
            requested = len(elements)

            # Collect all levels and wall/beam types once for performance
            all_levels = (
                DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_Levels)
                .WhereElementIsNotElementType()
                .ToElements()
            )
            level_map = {}
            for lv in all_levels:
                try:
                    level_map[get_element_name(lv)] = lv
                except Exception:
                    continue

            if not level_map:
                return routes.make_response(
                    data={"error": "No levels found in the project — create levels first"},
                    status=404,
                )

            wall_types = (
                DB.FilteredElementCollector(doc)
                .OfClass(DB.WallType)
                .ToElements()
            )
            wall_type_map = {}
            for wt in wall_types:
                try:
                    wall_type_map[get_element_name(wt)] = wt
                except Exception:
                    continue

            beam_types = (
                DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_StructuralFraming)
                .OfClass(DB.FamilySymbol)
                .ToElements()
            )
            beam_type_map = {}
            for bt in beam_types:
                try:
                    beam_type_map[get_element_name(bt)] = bt
                except Exception:
                    continue

            created = []
            errors = []

            def fail(idx, reason):
                # One reason text, two shapes: the legacy `errors` string and the D-03
                # outcome.failed entry (item = input index).
                errors.append("Element {}: {}".format(idx, reason))
                failed.append({"item": idx, "reason": reason})

            t = DB.Transaction(doc, "Create Line-Based Elements")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                for idx, elem in enumerate(elements):
                    try:
                        element_type = elem.get("element_type")
                        if not element_type:
                            fail(
                                idx,
                                "element_type is required",
                            )
                            continue

                        start = elem.get("start_point")
                        end = elem.get("end_point")
                        if not start or not end:
                            fail(
                                idx,
                                "start_point and end_point are required",
                            )
                            continue

                        # Convert mm to feet
                        sp = DB.XYZ(
                            float(start["x"]) / 304.8,
                            float(start["y"]) / 304.8,
                            float(start.get("z", 0)) / 304.8,
                        )
                        ep = DB.XYZ(
                            float(end["x"]) / 304.8,
                            float(end["y"]) / 304.8,
                            float(end.get("z", 0)) / 304.8,
                        )

                        # Validate non-zero length
                        if sp.DistanceTo(ep) < 0.001:
                            fail(
                                idx,
                                "Start and end points must be different (zero-length element)",
                            )
                            continue

                        line = DB.Line.CreateBound(sp, ep)

                        # Find level
                        level_name = elem.get("level_name")
                        level = None
                        if level_name:
                            level = level_map.get(level_name)
                            if not level:
                                available = ", ".join(sorted(level_map.keys()))
                                fail(
                                    idx,
                                    "Level '{}' not found. Available levels: {}".format(level_name, available),
                                )
                                continue
                        else:
                            # Use first level (lowest elevation)
                            sorted_levels = sorted(level_map.values(), key=lambda x: x.Elevation)
                            level = sorted_levels[0]

                        if element_type == "wall":
                            type_name = elem.get("type_name")
                            wall_type = None
                            if type_name:
                                wall_type = wall_type_map.get(type_name)
                                if not wall_type:
                                    available = ", ".join(sorted(wall_type_map.keys())[:10])
                                    fail(
                                        idx,
                                        "Wall type '{}' not found. Available types: {}".format(type_name, available),
                                    )
                                    continue
                            else:
                                if wall_type_map:
                                    wall_type = list(wall_type_map.values())[0]
                                else:
                                    fail(
                                        idx,
                                        "No wall types available — load wall families into the project",
                                    )
                                    continue

                            height_mm = float(elem.get("height", 3000))
                            height_feet = height_mm / 304.8
                            offset_mm = float(elem.get("offset", 0))
                            offset_feet = offset_mm / 304.8
                            is_structural = bool(elem.get("structural", False))

                            # Names are read before the create call, so once the element
                            # exists nothing left in this branch can fail and put it in
                            # both `succeeded` and `failed`.
                            type_label = get_element_name(wall_type)
                            level_label = get_element_name(level)
                            wall = DB.Wall.Create(
                                doc,
                                line,
                                wall_type.Id,
                                level.Id,
                                height_feet,
                                offset_feet,
                                False,
                                is_structural,
                            )

                            wall_id = get_element_id_value(wall)
                            created.append({
                                "id": wall_id,
                                "name": elem.get("name", ""),
                                "type": type_label,
                                "level": level_label,
                                "element_type": "wall",
                            })
                            succeeded.append(wall_id)

                        elif element_type == "beam":
                            type_name = elem.get("type_name")
                            beam_type = None
                            if type_name:
                                beam_type = beam_type_map.get(type_name)
                                if not beam_type:
                                    available = ", ".join(sorted(beam_type_map.keys())[:10])
                                    fail(
                                        idx,
                                        "Beam type '{}' not found. Available types: {}".format(type_name, available),
                                    )
                                    continue
                            else:
                                if beam_type_map:
                                    beam_type = list(beam_type_map.values())[0]
                                else:
                                    fail(
                                        idx,
                                        "No beam types available — load structural framing families",
                                    )
                                    continue

                            if not beam_type.IsActive:
                                beam_type.Activate()
                                doc.Regenerate()

                            type_label = get_element_name(beam_type)
                            level_label = get_element_name(level)
                            beam = doc.Create.NewFamilyInstance(
                                line,
                                beam_type,
                                level,
                                DB.Structure.StructuralType.Beam,
                            )

                            beam_id = get_element_id_value(beam)
                            created.append({
                                "id": beam_id,
                                "name": elem.get("name", ""),
                                "type": type_label,
                                "level": level_label,
                                "element_type": "beam",
                            })
                            succeeded.append(beam_id)

                        else:
                            fail(
                                idx,
                                "element_type '{}' not supported — use 'wall' or 'beam'".format(element_type),
                            )
                            continue

                    except Exception as elem_err:
                        fail(idx, str(elem_err))
                        continue

                commit_result = commit_and_report(t, swallower)

            except Exception as tx_err:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                return routes.make_response(
                    data={"error": "Transaction failed: {}".format(str(tx_err)),
                          "outcome": exception_outcome(t, requested, succeeded, failed)},
                    status=500,
                )

            response_data = {
                "created": created,
                "count": len(created),
                "message": "Created {} element(s)".format(len(created)),
            }
            if errors:
                response_data["errors"] = errors

            payload, http = finalize_outcome(
                commit_result, response_data, requested, succeeded, failed)
            return routes.make_response(data=payload, status=http)

        except Exception as e:
            logger.error("Failed to create line-based elements: {}".format(str(e)))
            return routes.make_response(
                data={"error": str(e), "traceback": traceback.format_exc(),
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500,
            )

    @api.route("/create_line/", methods=["POST"])
    def create_line_based(uiapp, doc, request):
        """Create line-based elements (walls, beams) in the Revit model."""
        # G1 explicit guard: first, before any document access or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_create_line_based(document, request), descriptor, uiapp=uiapp)

    def _create_surface_based(doc, request):
        """
        Create surface-based elements (floors, roofs, ceilings) in the Revit model (runs on the guarded document).
        Supports batch creation via elements array.
        """
        # Hoisted so the 500 reply can say what really happened (D-14).
        t = None
        requested = None
        succeeded = []
        failed = []
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document — open a project in Revit"},
                    status=503,
                )

            data = parse_request_data(request.data)
            elements = data.get("elements", [])

            if not elements:
                return routes.make_response(
                    data={"error": "No elements provided — pass an array of element definitions"},
                    status=400,
                )
            requested = len(elements)

            # Collect levels
            all_levels = (
                DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_Levels)
                .WhereElementIsNotElementType()
                .ToElements()
            )
            level_map = {}
            for lv in all_levels:
                try:
                    level_map[get_element_name(lv)] = lv
                except Exception:
                    continue

            if not level_map:
                return routes.make_response(
                    data={"error": "No levels found — create levels first"},
                    status=404,
                )

            # Collect floor types
            floor_types = DB.FilteredElementCollector(doc).OfClass(DB.FloorType).ToElements()
            floor_type_map = {}
            for ft in floor_types:
                try:
                    floor_type_map[get_element_name(ft)] = ft
                except Exception:
                    continue

            # Collect roof types
            roof_types = DB.FilteredElementCollector(doc).OfClass(DB.RoofType).ToElements()
            roof_type_map = {}
            for rt in roof_types:
                try:
                    roof_type_map[get_element_name(rt)] = rt
                except Exception:
                    continue

            created = []
            errors = []

            def fail(idx, reason, item=None):
                # One reason text, two shapes: the legacy `errors` string and the D-03
                # outcome.failed entry. `item` is the input index, or "INDEX.step" for a
                # secondary step of an element that was created (D-12).
                errors.append("Element {}: {}".format(idx, reason))
                failed.append({"item": idx if item is None else item, "reason": reason})

            t = DB.Transaction(doc, "Create Surface-Based Elements")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                for idx, elem in enumerate(elements):
                    try:
                        element_type = elem.get("element_type")
                        if not element_type:
                            fail(
                                idx,
                                "element_type is required",
                            )
                            continue

                        if element_type not in ("floor", "roof", "ceiling"):
                            fail(
                                idx,
                                "element_type must be 'floor', 'roof', or 'ceiling'",
                            )
                            continue

                        boundary = elem.get("boundary", [])
                        if len(boundary) < 3:
                            fail(
                                idx,
                                "Boundary requires at least 3 points/segments, got {}".format(len(boundary)),
                            )
                            continue

                        # BUG-007: Auto-detect point format vs segment format
                        # Point format: [{"x":0,"y":0,"z":0}, ...]
                        # Segment format: [{"p0":{"x":0,...},"p1":{"x":0,...}}, ...]
                        if "x" in boundary[0] or "y" in boundary[0]:
                            # Point array format — convert to segment format.
                            points = list(boundary)
                            # Drop an explicit closing point (last == first); otherwise the
                            # wrap-around below would create a zero-length segment and Revit
                            # rejects it with "Curve length is too small".
                            if len(points) > 1:
                                f, l = points[0], points[-1]
                                same = (
                                    abs(float(f.get("x", 0)) - float(l.get("x", 0))) < 0.001
                                    and abs(float(f.get("y", 0)) - float(l.get("y", 0))) < 0.001
                                    and abs(float(f.get("z", 0)) - float(l.get("z", 0))) < 0.001
                                )
                                if same:
                                    points = points[:-1]
                            boundary = []
                            for pi in range(len(points)):
                                p0 = points[pi]
                                p1 = points[(pi + 1) % len(points)]
                                boundary.append({"p0": p0, "p1": p1})

                        # Validate closed polygon
                        first_p0 = boundary[0].get("p0", {})
                        last_p1 = boundary[-1].get("p1", {})
                        fp = (float(first_p0.get("x", 0)), float(first_p0.get("y", 0)), float(first_p0.get("z", 0)))
                        lp = (float(last_p1.get("x", 0)), float(last_p1.get("y", 0)), float(last_p1.get("z", 0)))
                        dist = ((fp[0] - lp[0]) ** 2 + (fp[1] - lp[1]) ** 2 + (fp[2] - lp[2]) ** 2) ** 0.5
                        if dist > 1.0:  # tolerance of 1mm
                            fail(
                                idx,
                                "Boundary must form a closed polygon — last point ({}, {}, {}) does not match first point ({}, {}, {})".format(lp[0], lp[1], lp[2], fp[0], fp[1], fp[2]),
                            )
                            continue

                        # Find level
                        level_name = elem.get("level_name")
                        level = None
                        if level_name:
                            level = level_map.get(level_name)
                            if not level:
                                available = ", ".join(sorted(level_map.keys()))
                                fail(
                                    idx,
                                    "Level '{}' not found. Available levels: {}".format(level_name, available),
                                )
                                continue
                        else:
                            sorted_levels = sorted(level_map.values(), key=lambda x: x.Elevation)
                            level = sorted_levels[0]

                        if element_type == "floor" or element_type == "ceiling":
                            type_name = elem.get("type_name")
                            floor_type = None
                            if type_name:
                                floor_type = floor_type_map.get(type_name)
                                if not floor_type:
                                    available = ", ".join(sorted(floor_type_map.keys())[:10])
                                    fail(
                                        idx,
                                        "Floor type '{}' not found. Available: {}".format(type_name, available),
                                    )
                                    continue
                            else:
                                if floor_type_map:
                                    # Prefer a real (non-foundation) floor type. Picking the
                                    # raw first type often lands on "Foundation Slab", which
                                    # Revit categorizes as a Structural Foundation, not a
                                    # Floor — surprising when the caller asked for a floor.
                                    floor_type = None
                                    for ft in floor_type_map.values():
                                        try:
                                            if not getattr(ft, "IsFoundationSlab", False):
                                                floor_type = ft
                                                break
                                        except Exception:
                                            continue
                                    if floor_type is None:
                                        floor_type = list(floor_type_map.values())[0]
                                else:
                                    fail(
                                        idx,
                                        "No floor types available — load floor families",
                                    )
                                    continue

                            # Build curve loop
                            curve_loop = DB.CurveLoop()
                            for seg in boundary:
                                p0 = seg.get("p0", {})
                                p1 = seg.get("p1", {})
                                s = DB.XYZ(
                                    float(p0.get("x", 0)) / 304.8,
                                    float(p0.get("y", 0)) / 304.8,
                                    float(p0.get("z", 0)) / 304.8,
                                )
                                e = DB.XYZ(
                                    float(p1.get("x", 0)) / 304.8,
                                    float(p1.get("y", 0)) / 304.8,
                                    float(p1.get("z", 0)) / 304.8,
                                )
                                curve_loop.Append(DB.Line.CreateBound(s, e))

                            curve_loops = List[DB.CurveLoop]()
                            curve_loops.Add(curve_loop)

                            # Parsed and named before the create call, so an element that
                            # exists can only fail at the guarded offset step below.
                            offset_mm = float(elem.get("offset", 0))
                            type_label = get_element_name(floor_type)
                            level_label = get_element_name(level)

                            floor = DB.Floor.Create(doc, curve_loops, floor_type.Id, level.Id)
                            floor_id = get_element_id_value(floor)
                            created.append({
                                "id": floor_id,
                                "name": elem.get("name", ""),
                                "type": type_label,
                                "level": level_label,
                                "element_type": element_type,
                            })
                            succeeded.append(floor_id)

                            # Apply offset if specified; a floor that exists but kept its
                            # default offset is a failed step, not a failed floor (D-12).
                            if offset_mm != 0:
                                try:
                                    offset_param = floor.get_Parameter(
                                        DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM
                                    )
                                    if not offset_param or offset_param.IsReadOnly:
                                        fail(
                                            idx,
                                            "offset parameter not found or read-only",
                                            "{}.offset".format(idx),
                                        )
                                    elif offset_param.Set(offset_mm / 304.8) is False:
                                        fail(
                                            idx,
                                            "offset Set() returned false",
                                            "{}.offset".format(idx),
                                        )
                                except Exception as offset_err:
                                    fail(idx, str(offset_err), "{}.offset".format(idx))

                        elif element_type == "roof":
                            type_name = elem.get("type_name")
                            roof_type = None
                            if type_name:
                                roof_type = roof_type_map.get(type_name)
                                if not roof_type:
                                    available = ", ".join(sorted(roof_type_map.keys())[:10])
                                    fail(
                                        idx,
                                        "Roof type '{}' not found. Available: {}".format(type_name, available),
                                    )
                                    continue
                            else:
                                if roof_type_map:
                                    roof_type = list(roof_type_map.values())[0]
                                else:
                                    fail(
                                        idx,
                                        "No roof types available — load roof families",
                                    )
                                    continue

                            # Build CurveArray for legacy NewFootPrintRoof API
                            curve_array = DB.CurveArray()
                            for seg in boundary:
                                p0 = seg.get("p0", {})
                                p1 = seg.get("p1", {})
                                s = DB.XYZ(
                                    float(p0.get("x", 0)) / 304.8,
                                    float(p0.get("y", 0)) / 304.8,
                                    float(p0.get("z", 0)) / 304.8,
                                )
                                e = DB.XYZ(
                                    float(p1.get("x", 0)) / 304.8,
                                    float(p1.get("y", 0)) / 304.8,
                                    float(p1.get("z", 0)) / 304.8,
                                )
                                curve_array.Append(DB.Line.CreateBound(s, e))

                            import clr
                            model_curves = clr.Reference[DB.ModelCurveArray]()
                            type_label = get_element_name(roof_type)
                            level_label = get_element_name(level)
                            roof = doc.Create.NewFootPrintRoof(
                                curve_array, level, roof_type, model_curves
                            )

                            roof_id = get_element_id_value(roof)
                            created.append({
                                "id": roof_id,
                                "name": elem.get("name", ""),
                                "type": type_label,
                                "level": level_label,
                                "element_type": "roof",
                            })
                            succeeded.append(roof_id)

                    except Exception as elem_err:
                        fail(idx, str(elem_err))
                        continue

                commit_result = commit_and_report(t, swallower)

            except Exception as tx_err:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                return routes.make_response(
                    data={"error": "Transaction failed: {}".format(str(tx_err)),
                          "outcome": exception_outcome(t, requested, succeeded, failed)},
                    status=500,
                )

            response_data = {
                "created": created,
                "count": len(created),
                "message": "Created {} element(s)".format(len(created)),
            }
            if errors:
                response_data["errors"] = errors

            payload, http = finalize_outcome(
                commit_result, response_data, requested, succeeded, failed)
            return routes.make_response(data=payload, status=http)

        except Exception as e:
            logger.error("Failed to create surface-based elements: {}".format(str(e)))
            return routes.make_response(
                data={"error": str(e), "traceback": traceback.format_exc(),
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500,
            )

    @api.route("/create_surface/", methods=["POST"])
    def create_surface_based(uiapp, doc, request):
        """Create surface-based elements (floors, roofs, ceilings) in the Revit model."""
        # G1 explicit guard: first, before any document access or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_create_surface_based(document, request), descriptor, uiapp=uiapp)

    def _create_level(doc, request):
        """
        Create building levels at specified elevations (runs on the guarded document).
        Supports batch creation via levels array.
        """
        # Hoisted so the 500 reply can say what really happened (D-14).
        t = None
        requested = None
        succeeded = []
        failed = []
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document — open a project in Revit"},
                    status=503,
                )

            data = parse_request_data(request.data)
            levels = data.get("levels", [])

            if not levels:
                return routes.make_response(
                    data={"error": "No levels provided — pass an array of level definitions"},
                    status=400,
                )
            requested = len(levels)

            created = []
            errors = []

            def fail(idx, reason, item=None):
                # One reason text, two shapes: the legacy `errors` string and the D-03
                # outcome.failed entry. `item` is the input index, or "INDEX.name" for the
                # naming step of a level that was created (D-12).
                errors.append("Level {}: {}".format(idx, reason))
                failed.append({"item": idx if item is None else item, "reason": reason})

            t = DB.Transaction(doc, "Create Levels")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                for idx, lv in enumerate(levels):
                    try:
                        elevation_mm = lv.get("elevation")
                        if elevation_mm is None:
                            fail(idx, "elevation is required")
                            continue

                        elevation_feet = float(elevation_mm) / 304.8
                        new_level = DB.Level.Create(doc, elevation_feet)
                        # The level exists from here on: it is succeeded and in `created`
                        # whatever happens to its name (D-12).
                        level_id = get_element_id_value(new_level)
                        succeeded.append(level_id)

                        name = lv.get("name")
                        if name:
                            try:
                                new_level.Name = str(name)
                            except Exception as name_err:
                                # The level keeps Revit's default name, which `created` reports.
                                fail(idx, str(name_err), "{}.name".format(idx))

                        created.append({
                            "id": level_id,
                            "name": get_element_name(new_level),
                            "elevation_mm": float(elevation_mm),
                        })

                    except Exception as lv_err:
                        fail(idx, str(lv_err))
                        continue

                commit_result = commit_and_report(t, swallower)

            except Exception as tx_err:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                return routes.make_response(
                    data={"error": "Transaction failed: {}".format(str(tx_err)),
                          "outcome": exception_outcome(t, requested, succeeded, failed)},
                    status=500,
                )

            response_data = {
                "created": created,
                "count": len(created),
                "message": "Created {} level(s)".format(len(created)),
            }
            if errors:
                response_data["errors"] = errors

            payload, http = finalize_outcome(
                commit_result, response_data, requested, succeeded, failed)
            return routes.make_response(data=payload, status=http)

        except Exception as e:
            logger.error("Failed to create levels: {}".format(str(e)))
            return routes.make_response(
                data={"error": str(e), "traceback": traceback.format_exc(),
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500,
            )

    @api.route("/create_level/", methods=["POST"])
    def create_level_handler(uiapp, doc, request):
        """Create building levels at specified elevations."""
        # Phase 5 gate (D-01): shared secret and integrity, before anything else.
        gate_refusal = gate_or_response(request)
        if gate_refusal is not None:
            return gate_refusal
        # G1 explicit guard: first, before any document access or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_create_level(document, request), descriptor, uiapp=uiapp)

    logger.info("Building routes registered successfully")
