# -*- coding: UTF-8 -*-
"""
Status Module for Revit MCP
Handles API status and health check endpoints
"""

from pyrevit import routes
import logging

from utils import sanitize_string

logger = logging.getLogger(__name__)


def register_status_routes(api):
    """Register all status-related routes with the API"""

    @api.route('/status/', methods=["GET"])
    def revit_status(verbose=None):
        """
        Health check endpoint that verifies Revit context availability.

        Also reports how many route domains registered at extension load, so a
        workstation missing a capability can be told apart from one that is
        merely idle. Registration failures are isolated per domain, which
        makes this the only place they become visible.

        Query params:
            verbose: "true" to include the full list of registered domain
                     names. Omitted by default -- this route is called often
                     and the names are only needed when diagnosing.

        Returns:
            dict: Health status, document information, and registration state.
                  "health" is "degraded" when any domain failed to register.
                  "failed_domains" is present only when something failed.
        """
        try:
            from pyrevit import revit

            want_verbose = str(verbose).lower() in ("true", "1", "yes")

            # Imported lazily and defensively: a status route that cannot
            # answer because the registry is unavailable would defeat its own
            # purpose, so registration reporting degrades rather than fails.
            try:
                from revit_mcp import registry

                registration = registry.snapshot(verbose=want_verbose)
                degraded = registry.is_degraded()
            except Exception as reg_error:
                logger.warning(
                    "Could not read the registration registry: {}".format(
                        str(reg_error)
                    )
                )
                registration = {"registry_error": str(reg_error)}
                degraded = False

            doc = revit.doc
            if doc:
                payload = {
                    "status": "active",
                    "health": "degraded" if degraded else "healthy",
                    "revit_available": True,
                    "document_title": (
                        sanitize_string(doc.Title) if doc.Title else "Untitled"
                    ),
                    "api_name": "revit_mcp",
                }
                payload.update(registration)
                return routes.make_response(data=payload)
            else:
                payload = {
                    "status": "unhealthy",
                    "revit_available": False,
                    "error": "No active Revit document",
                    "api_name": "revit_mcp",
                }
                payload.update(registration)
                return routes.make_response(data=payload, status=503)

        except Exception as e:
            logger.error("Health check failed:{}".format(str(e)))
            return routes.make_response(data={
                "status": "unhealthy",
                "revit_available": False,
                "error": str(e),
                "api_name": "revit_mcp"
            }, status=503)

    logger.info("Status routes registered successfully")
