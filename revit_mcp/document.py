# -*- coding: UTF-8 -*-
"""
Document Module for Revit MCP
Save / persistence operations for the active document.

Note: Save / SaveAs must NOT run inside a Transaction — these handlers
deliberately do not open one.

Document identity (plan 02-13, G1 explicit-route-only): the registered handler
calls the guard first, so an ambiguous, closed or inactive document is refused
before any directory is created or Save / SaveAs is called, saves only the
Document the guard resolved, and answers with the title and path re-read from
that Document after the operation.
"""

from pyrevit import routes, revit, DB
from .utils import parse_request_data
from .identity import (
    mutation_document_or_response,
    request_document_selector,
    attribute_response,
    current_descriptor,
)
import os
import logging

logger = logging.getLogger(__name__)


def _same_path(left, right):
    """True when two file paths name the same file (case and slash style ignored)."""
    try:
        return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))
    except Exception:
        return left == right


def register_document_routes(api):
    """Register document persistence routes with the API."""

    def _save_document(doc, request):
        """
        Save the document the guard resolved (runs on that Document, never on the
        injected one). If a file_path is given (or the document has never been
        saved, e.g. it was started from a template), performs SaveAs; otherwise
        saves in place.
        """
        try:
            if not doc:
                return routes.make_response(
                    data={"error": "No active Revit document"}, status=503
                )

            data = {}
            if request and request.data:
                data = parse_request_data(request.data)

            file_path = data.get("file_path")
            overwrite = bool(data.get("overwrite", True))

            # A document started from a template (or never saved) has no real
            # path on disk yet, so it must be SaveAs'd to an explicit location.
            is_new = True
            try:
                is_new = doc.IsModelInPlace if hasattr(doc, "IsModelInPlace") else False
            except Exception:
                pass
            path_on_disk = ""
            try:
                path_on_disk = doc.PathName or ""
            except Exception:
                path_on_disk = ""

            if file_path:
                # Ensure parent directory exists
                try:
                    parent = os.path.dirname(file_path)
                    if parent and not os.path.exists(parent):
                        os.makedirs(parent)
                except Exception as mk_err:
                    logger.warning("Could not create directory: {}".format(str(mk_err)))

                save_opts = DB.SaveAsOptions()
                save_opts.OverwriteExistingFile = overwrite

                # A workshared document -- which is what /open_model/ hands back
                # after a detach-and-preserve-worksets open -- cannot be
                # SaveAs'd without this. Revit refuses outright: "The document
                # just had worksharing enabled or was opened detached, so
                # WorksharingSaveAsOptions.SaveAsCentral must be set to true for
                # SaveAs." Saving as central is also what keeps the worksets:
                # it writes a new central file that still carries them.
                is_workshared = False
                try:
                    is_workshared = bool(doc.IsWorkshared)
                except Exception:
                    logger.warning("Could not read doc.IsWorkshared")
                as_central = bool(data.get("as_central", is_workshared))
                if as_central:
                    try:
                        ws_opts = DB.WorksharingSaveAsOptions()
                        ws_opts.SaveAsCentral = True
                        save_opts.SetWorksharingOptions(ws_opts)
                    except Exception as ws_err:
                        return routes.make_response(
                            data={"error": "Could not set worksharing save options: "
                                           "{}".format(str(ws_err))},
                            status=500,
                        )

                model_path = DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(file_path)
                doc.SaveAs(model_path, save_opts)

                # Report where the document actually lives now, read from the Document
                # that was saved. The requested path is only echoed when it is the same
                # file; otherwise the reply names the real path and keeps the request
                # under its own key, so a save is never reported against a path the
                # document did not end up at.
                saved_at = file_path
                landed_elsewhere = False
                try:
                    actual_path = doc.PathName or ""
                    if actual_path and not _same_path(actual_path, file_path):
                        saved_at = actual_path
                        landed_elsewhere = True
                except Exception:
                    logger.warning("Could not read doc.PathName after SaveAs")
                reply = {
                    "status": "success",
                    "operation": "save_as",
                    "file_path": saved_at,
                    "previous_path": path_on_disk,
                    "is_workshared": is_workshared,
                    "saved_as_central": as_central,
                    "message": "Document saved to {}{}".format(
                        saved_at,
                        " as a central model" if as_central else "",
                    ),
                }
                if landed_elsewhere:
                    reply["requested_file_path"] = file_path
                return routes.make_response(data=reply)

            if not path_on_disk:
                return routes.make_response(
                    data={
                        "error": "Document has never been saved — provide a file_path to save it (e.g. C:\\\\Models\\\\ESB.rvt)."
                    },
                    status=400,
                )

            # Save in place
            doc.Save()
            return routes.make_response(data={
                "status": "success",
                "operation": "save",
                "file_path": path_on_disk,
                "message": "Document saved",
            })

        except Exception as e:
            logger.error("save_document failed: {}".format(str(e)))
            return routes.make_response(
                data={"error": str(e)}, status=500
            )

    @api.route("/save_document/", methods=["POST"])
    def save_document(uiapp, doc, request):
        """
        Save the document named by the optional "document" selector (or the one open
        document). If a file_path is given (or the document has never been saved),
        performs SaveAs; otherwise saves in place.

        Payload (all optional):
        {
            "document": "doc1....",
            "file_path": "C:\\\\path\\\\to\\\\Model.rvt",
            "overwrite": true
        }
        """
        # G1 explicit guard: first, before any directory is created or anything is saved.
        document, descriptor, refusal = mutation_document_or_response(
            request_document_selector(request), uiapp=uiapp)
        if refusal is not None:
            return refusal
        response = _save_document(document, request)
        # Title and path are re-read from the Document that was saved, after the operation.
        return attribute_response(response, current_descriptor(descriptor, document), uiapp=uiapp)

    logger.info("Document routes registered successfully")
