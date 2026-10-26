# -*- coding: UTF-8 -*-
"""Bridge-internal open read for confirmation facts (D-09); never a mutation.

Reports what the named mutation would touch. Unknown facts stay unknown; no trial
transaction, file open, document activation or write is performed.
"""

import logging

from pyrevit import routes

from .security import strip_envelope
from .identity import mutation_document_or_response, request_document_selector
from .textutils import parse_request_data

logger = logging.getLogger(__name__)

SUPPORTED_ROUTES = (
    "/set_parameter/", "/modify_element/", "/delete_elements/",
    "/transform_elements/", "/edit_family/", "/load_family/",
)


def _not_collected(doc, args):
    return {"available": False, "reason": "not_collected"}


_FACTS = dict((route, _not_collected) for route in SUPPORTED_ROUTES)


def register_preflight_routes(api):
    @api.route("/mutation_preflight/", methods=["POST"])
    def mutation_preflight_handler(uiapp, doc, request):
        """Resolve the document exactly as a mutation does, then read bounded facts."""
        strip_envelope(request)
        try:
            try:
                data = parse_request_data(request.data)
            except Exception:
                return routes.make_response(
                    data={"error": "Invalid preflight body", "error_code": "preflight-bad-request"},
                    status=400)
            if not isinstance(data, dict) or not isinstance(data.get("args", {}), dict):
                return routes.make_response(
                    data={"error": "Preflight body and args must be objects",
                          "error_code": "preflight-bad-request"}, status=400)
            route = data.get("route")
            if route not in SUPPORTED_ROUTES:
                return routes.make_response(
                    data={"error": "Unsupported preflight route",
                          "error_code": "preflight-unsupported-route"}, status=400)
            selected_doc, descriptor, refusal = mutation_document_or_response(
                request_document_selector(request), uiapp=uiapp)
            if refusal is not None:
                return refusal
            facts = _FACTS[route](selected_doc, data.get("args", {}))
            return routes.make_response(data={
                "status": "ok", "route": route, "document": descriptor, "facts": facts,
            }, status=200)
        except Exception as exc:
            logger.warning("Mutation preflight failed: %s", type(exc).__name__)
            return routes.make_response(data={
                "error": "Preflight failed ({})".format(type(exc).__name__),
                "error_code": "preflight-failed",
            }, status=500)
