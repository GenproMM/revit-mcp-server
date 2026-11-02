# -*- coding: UTF-8 -*-
"""
Status Module for Revit MCP
Handles API status and health check endpoints
"""

from pyrevit import routes
import logging

from .utils import sanitize_string

logger = logging.getLogger(__name__)


def _pyrevit_facts():
    """pyRevit version, engine and home directory, each None when unreadable; never raises."""
    facts = {"version": None, "engine": None, "home": None}
    try:
        import pyrevit

        version = getattr(pyrevit, "VERSION_STRING", None)
        facts["version"] = str(version).strip() if version else None
        home = getattr(pyrevit, "HOME_DIR", None)
        facts["home"] = sanitize_string(home) if home else None
    except Exception as exc:
        logger.warning("Could not read the pyRevit version: {}".format(str(exc)))
    try:
        from pyrevit import engine

        version = getattr(engine, "EngineVersion", None)
        facts["engine"] = str(version) if version else None
    except Exception as exc:
        logger.warning("Could not read the pyRevit engine: {}".format(str(exc)))
    return facts


def _revit_facts(host_app):
    """Revit version, sub-version and build, each None when unreadable; never raises."""
    facts = {"version": None, "sub_version": None, "build": None}
    try:
        app = host_app.app
        for key, attr in (("version", "VersionNumber"), ("sub_version", "SubVersionNumber"),
                          ("build", "VersionBuild")):
            value = getattr(app, attr, None)
            facts[key] = str(value) if value else None
    except Exception as exc:
        logger.warning("Could not read the Revit version: {}".format(str(exc)))
    return facts


def _runtime():
    """(runtime block, runtime alerts) for /status/; ({}, []) when it cannot be built."""
    try:
        from pyrevit import HOST_APP
        from .runtime_info import extension_root, runtime_alerts, runtime_block

        block = runtime_block(extension_root(__file__), _pyrevit_facts(), _revit_facts(HOST_APP))
        return block, runtime_alerts(block)
    except Exception as exc:
        logger.warning("Could not build the runtime status block: {}".format(str(exc)))
        return {}, []


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
                  "runtime" names the product version, the extension build and
                  path, the Python engine, pyRevit and Revit; "runtime_alerts"
                  (which also degrade health) say when the engine is unsupported.
        """
        identity_data = {}
        try:
            from pyrevit import revit

            want_verbose = str(verbose).lower() in ("true", "1", "yes")

            # Imported lazily and defensively: a status route that cannot
            # answer because the registry is unavailable would defeat its own
            # purpose, so registration reporting degrades rather than fails.
            try:
                from . import registry

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

            identity_data = {}
            identity_error = None
            try:
                from .identity import get_process_identity
                from pyrevit import HOST_APP

                identity_data = get_process_identity(HOST_APP.app.VersionNumber)
            except Exception as identity_exc:
                identity_error = str(identity_exc)
                logger.warning("Could not read process identity: {}".format(identity_error))

            # The security block (secret fingerprint, integrity verdict, bind) is
            # imported lazily and defensively like the registry: /status/ must
            # still answer when the security module cannot be imported (SEC-05).
            block = {}
            alerts = []
            try:
                from .security import status_block
                from .trust import security_alerts

                block = status_block(
                    identity_data.get("actual_port")
                    if isinstance(identity_data, dict) else None
                )
                alerts = security_alerts(block)
            except Exception as security_exc:
                logger.warning(
                    "Could not build the security status block: {}".format(
                        str(security_exc)
                    )
                )
                block = {}
                alerts = []
            if alerts:
                block = dict(block)
                block["security_alerts"] = alerts

            # Versions of every layer, so one /status/ answers "what is installed
            # and what runs it" without a shell on the workstation.
            runtime, runtime_alerts = _runtime()
            if runtime:
                block = dict(block)
                block["runtime"] = runtime
            if runtime_alerts:
                block["runtime_alerts"] = runtime_alerts
                alerts = list(alerts) + list(runtime_alerts)

            doc = revit.doc
            if doc:
                payload = {
                    "status": "active",
                    "health": "degraded" if (degraded or alerts) else "healthy",
                    "revit_available": True,
                    "document_title": (
                        sanitize_string(doc.Title) if doc.Title else "Untitled"
                    ),
                    "api_name": api.name,
                }
                payload.update(registration)
                payload.update(block)
                if identity_error:
                    payload["health"] = "degraded"
                    payload["identity_error"] = identity_error
                else:
                    payload["process_identity"] = identity_data
                return routes.make_response(data=payload)
            else:
                payload = {
                    "status": "unhealthy",
                    "revit_available": False,
                    "error": "No active Revit document",
                    "api_name": api.name,
                }
                payload.update(registration)
                payload.update(block)
                payload["health"] = (
                    "degraded" if (degraded or alerts or identity_error) else "healthy"
                )
                if identity_error:
                    payload["identity_error"] = identity_error
                else:
                    payload["process_identity"] = identity_data
                return routes.make_response(data=payload, status=503)

        except Exception as e:
            logger.error("Health check failed:{}".format(str(e)))
            payload = {
                "status": "unhealthy",
                "revit_available": False,
                "error": str(e),
                "api_name": api.name
            }
            if identity_data:
                payload["process_identity"] = identity_data
            return routes.make_response(data=payload, status=503)

    logger.info("Status routes registered successfully")
