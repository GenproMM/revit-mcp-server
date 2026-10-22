# -*- coding: UTF-8 -*-
"""
Documents Module for Revit MCP
Lists the documents open in this Revit process, each with its own selector.

A thin data provider: the registry, the selector rules and the refusals all live
in identity.py (pure logic, unit tested on the CPython side). This route reads
Application.Documents on every request and never caches the active document.

The handler takes no injected document: a process with no open document must
still answer with an empty list rather than a 503.
"""

from pyrevit import routes
import logging

logger = logging.getLogger(__name__)


def register_documents_routes(api):
    """Register the document listing route with the API"""

    @api.route("/documents/", methods=["GET"])
    def list_documents():
        """
        List every open (non-link) document in this Revit process.

        Returns:
            dict: process_identity (PID, actual port, session token, Revit
                  version), documents (selector "document", title, path, active,
                  saved), count and active_document. An empty list is valid data.
                  When two documents cannot be told apart safely the response is
                  an error naming why; the list never silently drops a document.
        """
        identity = None
        identity_error = None
        try:
            from .identity import current_document_descriptors, process_identity_or_error

            identity, identity_error = process_identity_or_error()
            result = current_document_descriptors()
            if result.get("ok"):
                payload = {
                    "status": "success",
                    "documents": result["documents"],
                    "count": result["count"],
                    "active_document": result["active_document"],
                }
                status = 200
            else:
                payload = {
                    "error": result["error"],
                    "error_code": result["code"],
                }
                status = result["status"]
            if identity:
                payload["process_identity"] = identity
            else:
                payload["identity_error"] = identity_error
            return routes.make_response(data=payload, status=status)
        except Exception as e:
            logger.error("list_documents failed: {}".format(str(e)))
            payload = {"error": str(e)}
            if identity:
                payload["process_identity"] = identity
            return routes.make_response(data=payload, status=500)

    logger.info("Documents routes registered successfully")
