# -*- coding: UTF-8 -*-
"""
Documentation Module for Revit MCP
Handles sheet creation, schedule creation, and document export
"""

from .utils import get_element_name, get_element_id_value, suppress_warnings, parse_request_data, commit_and_report, finalize_outcome, exception_outcome
from .identity import mutation_document_or_response, request_document_selector, attribute_response
from .security import gate_or_response
from pyrevit import routes, revit, DB
import traceback
import logging
import os
import time

logger = logging.getLogger(__name__)


def register_documentation_routes(api):
    """Register all documentation routes with the API"""

    def _create_sheet(doc, request):
        """Create a drawing sheet in Revit."""
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

            data = {}
            if request and request.data:
                data = parse_request_data(request.data)

            sheet_number = data.get("sheet_number")
            sheet_name = data.get("sheet_name", "Unnamed Sheet")
            title_block_name = data.get("title_block_name")

            # Find title block
            title_blocks = (
                DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
                .OfClass(DB.FamilySymbol)
                .ToElements()
            )

            if not title_blocks or len(title_blocks) == 0:
                return routes.make_response(
                    data={"error": "No title block families found — load a title block family into the project"},
                    status=404,
                )

            target_tb = None
            if title_block_name:
                for tb in title_blocks:
                    try:
                        if get_element_name(tb) == title_block_name:
                            target_tb = tb
                            break
                    except Exception:
                        continue

            if not target_tb:
                target_tb = title_blocks[0]

            # Check for duplicate sheet number
            if sheet_number:
                existing_sheets = (
                    DB.FilteredElementCollector(doc)
                    .OfClass(DB.ViewSheet)
                    .ToElements()
                )
                for sheet in existing_sheets:
                    try:
                        if sheet.SheetNumber == sheet_number:
                            return routes.make_response(
                                data={"error": "Sheet number '{}' already exists in the project".format(sheet_number)},
                                status=400,
                            )
                    except Exception:
                        continue

            requested = 1
            t = DB.Transaction(doc, "Create Sheet via MCP")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                # Activate title block
                if not target_tb.IsActive:
                    target_tb.Activate()
                    doc.Regenerate()

                # Create the sheet
                new_sheet = DB.ViewSheet.Create(doc, target_tb.Id)

                # The number and the name are their own steps: a number that is already
                # taken must show as a failed step, not vanish behind "Created sheet".
                if sheet_number:
                    try:
                        new_sheet.SheetNumber = sheet_number
                    except Exception as number_err:
                        logger.warning("Could not set the sheet number: {}".format(number_err))
                        failed.append({"item": "sheet_number", "reason": str(number_err)})
                if sheet_name:
                    try:
                        new_sheet.Name = sheet_name
                    except Exception as name_err:
                        logger.warning("Could not set the sheet name: {}".format(name_err))
                        failed.append({"item": "sheet_name", "reason": str(name_err)})

                commit_result = commit_and_report(t, swallower)

            except Exception as tx_error:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise tx_error

            if not commit_result["committed"]:
                # A rolled-back sheet never existed: read nothing from it (Pitfall 2).
                payload, http = finalize_outcome(commit_result, {}, requested, [], failed)
                return routes.make_response(data=payload, status=http)

            succeeded.append(get_element_id_value(new_sheet))
            tb_name = get_element_name(target_tb)
            message = "Created sheet {} - {}".format(new_sheet.SheetNumber, new_sheet.Name)
            if failed:
                message += " (not applied: {})".format(
                    "; ".join("{}: {}".format(f["item"], f["reason"]) for f in failed))

            data = {
                "created": {
                    "id": succeeded[0],
                    "sheet_number": new_sheet.SheetNumber,
                    "sheet_name": new_sheet.Name,
                    "title_block": tb_name,
                },
                "message": message,
            }
            payload, http = finalize_outcome(
                commit_result, data, requested, succeeded, failed)
            return routes.make_response(data=payload, status=http)

        except Exception as e:
            logger.error("Failed to create sheet: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace,
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500
            )

    @api.route("/create_sheet/", methods=["POST"])
    def create_sheet_handler(uiapp, doc, request):
        """Create a drawing sheet in Revit."""
        # Phase 5 gate (D-01): shared secret and integrity, before anything else.
        gate_refusal = gate_or_response(request)
        if gate_refusal is not None:
            return gate_refusal
        # G1 explicit guard: first, before any document access, file output or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_create_sheet(document, request), descriptor, uiapp=uiapp)

    def _create_schedule(doc, request):
        """Create a schedule view in Revit."""
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

            if not request or not request.data:
                return routes.make_response(
                    data={"error": "No data provided"}, status=400
                )

            data = parse_request_data(request.data)

            category_str = data.get("category")
            fields = data.get("fields")
            schedule_name = data.get("schedule_name")

            if not category_str:
                return routes.make_response(
                    data={"error": "No category provided"}, status=400
                )

            # Resolve category
            try:
                bic = getattr(DB.BuiltInCategory, category_str)
            except AttributeError:
                return routes.make_response(
                    data={"error": "Invalid category '{}' — use a valid BuiltInCategory name like OST_Walls, OST_Rooms, OST_Doors".format(category_str)},
                    status=400,
                )

            # Get ElementId for category
            cat_id = DB.ElementId(bic)

            requested = 1
            t = DB.Transaction(doc, "Create Schedule via MCP")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                # Create the schedule
                schedule = DB.ViewSchedule.CreateSchedule(doc, cat_id)

                if schedule_name:
                    name_to_set = schedule_name
                else:
                    # Auto-generate name from category
                    cat_name = category_str.replace("OST_", "")
                    name_to_set = "{} Schedule".format(cat_name)
                # The name is its own step: a taken name must show as a failed step.
                try:
                    schedule.Name = name_to_set
                except Exception as name_err:
                    logger.warning("Could not set the schedule name: {}".format(name_err))
                    failed.append({"item": "name", "reason": str(name_err)})

                # Add fields
                sched_def = schedule.Definition
                schedulable_fields = sched_def.GetSchedulableFields()

                fields_added = []
                fields_failed = []

                if fields:
                    for field_name in fields:
                        found = False
                        for sf in schedulable_fields:
                            try:
                                if sf.GetName(doc) == field_name:
                                    sched_def.AddField(sf)
                                    fields_added.append(field_name)
                                    found = True
                                    break
                            except Exception:
                                continue

                        if not found:
                            fields_failed.append(field_name)
                            failed.append({"item": field_name, "reason": "field not found"})
                else:
                    # Add first few available fields as defaults
                    count = 0
                    for sf in schedulable_fields:
                        if count >= 5:
                            break
                        try:
                            fname = sf.GetName(doc)
                            sched_def.AddField(sf)
                            fields_added.append(fname)
                            count += 1
                        except Exception:
                            continue

                # Get row count
                row_count = 0
                try:
                    table_data = schedule.GetTableData()
                    section = table_data.GetSectionData(DB.SectionType.Body)
                    row_count = section.NumberOfRows
                except Exception:
                    pass

                commit_result = commit_and_report(t, swallower)

            except Exception as tx_error:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise tx_error

            if not commit_result["committed"]:
                # A rolled-back schedule never existed: read nothing from it (Pitfall 2).
                payload, http = finalize_outcome(commit_result, {}, requested, [], failed)
                return routes.make_response(data=payload, status=http)

            succeeded.append(get_element_id_value(schedule))

            # Get category display name
            cat_display = category_str.replace("OST_", "").lower()

            result = {
                "created": {
                    "id": succeeded[0],
                    "name": schedule.Name,
                    "category": cat_display,
                    "fields": fields_added,
                    "row_count": row_count,
                },
                "message": "Created {} schedule with {} field{} and {} row{}".format(
                    cat_display,
                    len(fields_added),
                    "s" if len(fields_added) != 1 else "",
                    row_count,
                    "s" if row_count != 1 else "",
                ),
            }

            if fields_failed:
                # Get available field names for error context
                available = []
                for sf in schedulable_fields:
                    try:
                        available.append(sf.GetName(doc))
                    except Exception:
                        continue
                result["fields_not_found"] = fields_failed
                result["available_fields"] = sorted(available)[:30]

            payload, http = finalize_outcome(
                commit_result, result, requested, succeeded, failed)
            return routes.make_response(data=payload, status=http)

        except Exception as e:
            logger.error("Failed to create schedule: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace,
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500
            )

    @api.route("/create_schedule/", methods=["POST"])
    def create_schedule_handler(uiapp, doc, request):
        """Create a schedule view in Revit."""
        # Phase 5 gate (D-01): shared secret and integrity, before anything else.
        gate_refusal = gate_or_response(request)
        if gate_refusal is not None:
            return gate_refusal
        # G1 explicit guard: first, before any document access, file output or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_create_schedule(document, request), descriptor, uiapp=uiapp)

    def _export_document(doc, request):
        """Export a view or sheet to file."""
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

            data = {}
            if request and request.data:
                data = parse_request_data(request.data)

            view_name = data.get("view_name")
            export_format = data.get("format", "pdf")
            resolution = data.get("resolution", 300)

            supported_formats = ["pdf", "png", "jpg", "dwg"]
            if export_format.lower() not in supported_formats:
                return routes.make_response(
                    data={"error": "Format '{}' not supported — use pdf, png, jpg, or dwg".format(export_format)},
                    status=400,
                )

            # Find the view
            target_view = None
            if view_name:
                views = (
                    DB.FilteredElementCollector(doc)
                    .OfClass(DB.View)
                    .ToElements()
                )
                for v in views:
                    try:
                        if get_element_name(v) == view_name:
                            target_view = v
                            break
                    except Exception:
                        continue

                if not target_view:
                    return routes.make_response(
                        data={"error": "View '{}' not found in the project".format(view_name)},
                        status=404,
                    )
            else:
                target_view = doc.ActiveView

            if not target_view:
                return routes.make_response(
                    data={"error": "No view available for export"}, status=400
                )

            actual_view_name = get_element_name(target_view)

            # Determine export path
            export_dir = os.path.join(
                os.environ.get("USERPROFILE", os.environ.get("HOME", "C:\\")),
                "Documents",
                "RevitMCPExport",
            )
            if not os.path.exists(export_dir):
                os.makedirs(export_dir)

            fmt = export_format.lower()

            # The file this call is expected to write. It is the item every export result
            # names, so it is fixed before anything runs.
            if fmt == "png" or fmt == "jpg":
                safe_name = actual_view_name.replace(" ", "_").replace("/", "_")
                file_path = os.path.join(
                    export_dir, safe_name + (".png" if fmt == "png" else ".jpg"))
            elif fmt == "pdf":
                file_path = os.path.join(
                    export_dir, actual_view_name.replace(" ", "_") + ".pdf")
            else:
                safe_name = actual_view_name.replace(" ", "_")
                file_path = os.path.join(export_dir, safe_name + ".dwg")

            requested = 1
            t = DB.Transaction(doc, "Export Document via MCP")
            t.Start()
            swallower = suppress_warnings(t)

            try:
                file_size_kb = 0
                # What the export call itself said (D-06): the Boolean Document.Export
                # returns, or, for an image, whether this call wrote the file.
                export_ok = False
                failure_reason = None

                if fmt == "png" or fmt == "jpg":
                    # Image export
                    options = DB.ImageExportOptions()
                    options.ZoomType = DB.ZoomFitType.FitToPage
                    options.PixelSize = resolution
                    options.ExportRange = DB.ExportRange.SetOfViews

                    view_set = DB.ViewSet()
                    view_set.Insert(target_view)

                    # Use ICollection for SetViewsAndSheets
                    from System.Collections.Generic import List
                    view_ids = List[DB.ElementId]()
                    view_ids.Add(target_view.Id)
                    options.SetViewsAndSheets(view_ids)

                    if fmt == "png":
                        options.HLRandWFViewsFileType = DB.ImageFileType.PNG
                    else:
                        options.HLRandWFViewsFileType = DB.ImageFileType.JPGMedium

                    options.FilePath = os.path.join(export_dir, safe_name)

                    export_started = time.time()
                    doc.ExportImage(options)

                    # ExportImage returns nothing, so the file is the evidence. A file left
                    # by an earlier export does not count: it must have been written by this
                    # call (two seconds of slack for coarse file-system timestamps).
                    export_ok = (
                        os.path.exists(file_path)
                        and os.path.getmtime(file_path) >= export_started - 2
                    )
                    if not export_ok:
                        failure_reason = "expected export file was not created"

                elif fmt == "pdf":
                    # PDF export (Revit 2022+)
                    try:
                        pdf_options = DB.PDFExportOptions()
                        pdf_options.FileName = actual_view_name.replace(" ", "_")
                        pdf_options.Combine = True

                        from System.Collections.Generic import List
                        view_ids = List[DB.ElementId]()
                        view_ids.Add(target_view.Id)

                        export_ok = bool(doc.Export(export_dir, view_ids, pdf_options))
                        if not export_ok:
                            failure_reason = "Document.Export returned False"
                    except Exception as pdf_err:
                        t.RollBack()
                        failed.append({"item": file_path, "reason": str(pdf_err)})
                        return routes.make_response(
                            data={
                                "error": "PDF export not available: {}. Try format 'png' as an alternative.".format(str(pdf_err)),
                                "outcome": exception_outcome(t, requested, succeeded, failed),
                            },
                            status=500,
                        )

                elif fmt == "dwg":
                    # DWG export
                    try:
                        dwg_options = DB.DWGExportOptions()

                        from System.Collections.Generic import List
                        view_ids = List[DB.ElementId]()
                        view_ids.Add(target_view.Id)

                        export_ok = bool(doc.Export(export_dir, safe_name, view_ids, dwg_options))
                        if not export_ok:
                            failure_reason = "Document.Export returned False"
                    except Exception as dwg_err:
                        t.RollBack()
                        failed.append({"item": file_path, "reason": str(dwg_err)})
                        return routes.make_response(
                            data={
                                "error": "DWG export failed: {}".format(str(dwg_err)),
                                "outcome": exception_outcome(t, requested, succeeded, failed),
                            },
                            status=500,
                        )

                commit_result = commit_and_report(t, swallower)

            except Exception as tx_error:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise tx_error

            if export_ok:
                if commit_result["committed"]:
                    succeeded.append(file_path)
            else:
                failed.append({"item": file_path, "reason": failure_reason})

            # Get file size, only for an export that was reported and that was kept
            if export_ok and commit_result["committed"]:
                try:
                    if file_path and os.path.exists(file_path):
                        file_size_kb = int(os.path.getsize(file_path) / 1024)
                except Exception:
                    pass

            if export_ok:
                data = {
                    "exported": {
                        "view_name": actual_view_name,
                        "format": fmt,
                        "file_path": file_path,
                        "file_size_kb": file_size_kb,
                    },
                    "message": "Exported '{}' to {} ({} KB)".format(
                        actual_view_name, fmt.upper(), file_size_kb
                    ),
                }
            else:
                data = {
                    "message": "Export of '{}' to {} failed: {} ({})".format(
                        actual_view_name, fmt.upper(), failure_reason, file_path
                    ),
                }
            payload, http = finalize_outcome(
                commit_result, data, requested, succeeded, failed)
            return routes.make_response(data=payload, status=http)

        except Exception as e:
            logger.error("Failed to export document: {}".format(str(e)))
            error_trace = traceback.format_exc()
            return routes.make_response(
                data={"error": str(e), "traceback": error_trace,
                      "outcome": exception_outcome(t, requested, succeeded, failed)},
                status=500
            )

    @api.route("/export_document/", methods=["POST"])
    def export_document_handler(uiapp, doc, request):
        """Export a view or sheet to file."""
        # Phase 5 gate (D-01): shared secret and integrity, before anything else.
        gate_refusal = gate_or_response(request)
        if gate_refusal is not None:
            return gate_refusal
        # G1 explicit guard: first, before any document access, file output or transaction.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        return attribute_response(_export_document(document, request), descriptor, uiapp=uiapp)

    logger.info("Documentation routes registered successfully")
