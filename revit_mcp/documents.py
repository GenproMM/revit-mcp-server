# -*- coding: UTF-8 -*-
"""
Documents Module for Revit MCP
Lists the documents open in this Revit process, each with its own selector.

A thin data provider: the registry, the selector rules and the refusals all live
in identity.py (pure logic, unit tested on the CPython side). This route reads
Application.Documents on every request and never caches the active document.

The handler takes no injected document: a process with no open document must
still answer with an empty list rather than a 503.

Activation (plan 02-05, D-12, the accepted G4 policy): /activate_document/ is a
separate explicit action that makes one already-open, saved, non-workshared
document with an existing file path the active one, by handing that document's
own PathName to UIApplication.OpenAndActivateDocument(string). Every other class
is refused with a named reason BEFORE any API call; nothing here saves, reopens,
opens a file or substitutes a path. The reported active document is re-read after
the call and compared with Equals; neither the input nor the API return value is
trusted. Reads and ordinary mutations never reach this module's activation call.
"""

import logging

logger = logging.getLogger(__name__)


# Refusal reasons of the G4 gate, in the order they are evaluated. Everything but
# the measured class (saved, non-workshared, existing file path) is refused before
# any API call; "unmeasured" means refused, not tried.
ACTIVATION_REFUSALS = {
    "unsaved": (
        "The document has never been saved (its path is empty), so there is no file to "
        "activate from. Activation was refused; nothing was saved, opened or changed."),
    "detached": (
        "The document is a detached copy and has no usable source file. Activation was "
        "refused; nothing was saved, reopened or changed, and no other path was tried."),
    "no-usable-file-path": (
        "The document path is not an existing file on this machine (a cloud or other "
        "non-file path, or a file that has moved). Activation was refused; no other path "
        "was tried and nothing was saved, reopened or changed."),
    "linked-unsupported": (
        "A link document cannot be activated. Activation was refused; nothing was changed."),
    "family-unmeasured": (
        "Family documents are an unmeasured class: activation was refused, not tried. "
        "Nothing was changed."),
    "cloud-unmeasured": (
        "Cloud models are an unmeasured class: activation was refused, not tried. "
        "Nothing was changed."),
    "workshared-unmeasured": (
        "Workshared models, even a saved one with an existing path, are an unmeasured "
        "class: activation was refused, not tried. Nothing was saved, reopened or changed."),
    "eligibility-unreadable": (
        "A property needed to decide whether this document may be activated could not be "
        "read, so activation was refused, not tried. Nothing was changed."),
}


def _file_exists(path):
    """True only for an existing file; any failure to find out is False."""
    try:
        import System
    except ImportError:
        import os

        return os.path.isfile(path)
    try:
        return bool(System.IO.File.Exists(path))
    except Exception:
        return False


def _read_flag(document, name):
    """True / False, or None when the property could not be read."""
    try:
        return bool(getattr(document, name))
    except Exception:
        return None


def activation_refusal_reason(document, file_exists=None):
    """Why this document may not be activated, or None when it is the measured class.

    Fixed order: unsaved, detached, no-usable-file-path, linked-unsupported,
    family-unmeasured, cloud-unmeasured, workshared-unmeasured. A property that
    cannot be read refuses as eligibility-unreadable: the gate fails closed. Pure
    over a duck-typed Document; it calls no activation API.
    """
    exists = file_exists or _file_exists
    try:
        path = document.PathName
    except Exception:
        return "eligibility-unreadable"
    if not path or not str(path).strip():
        return "unsaved"
    detached = _read_flag(document, "IsDetached")
    if detached is None:
        return "eligibility-unreadable"
    if detached:
        return "detached"
    try:
        found = bool(exists(path))
    except Exception:
        found = False
    if not found:
        return "no-usable-file-path"
    for name, reason in (("IsLinked", "linked-unsupported"),
                         ("IsFamilyDocument", "family-unmeasured"),
                         ("IsModelInCloud", "cloud-unmeasured"),
                         ("IsWorkshared", "workshared-unmeasured")):
        value = _read_flag(document, name)
        if value is None:
            return "eligibility-unreadable"
        if value:
            return reason
    return None


def _active_of(listing):
    """(descriptor, error) for the active document of a current_document_descriptors result."""
    if not listing.get("ok"):
        return None, listing.get("error") or "the open documents could not be read"
    for descriptor in listing["documents"]:
        if descriptor.get("active"):
            return descriptor, None
    return None, None


def _observed_active(read_snapshot, registry):
    """(descriptor, error): the document active in Revit now, re-read, never copied."""
    from .identity import current_document_descriptors

    try:
        return _active_of(current_document_descriptors(read_snapshot(), registry))
    except Exception as exc:
        return None, str(exc) or exc.__class__.__name__


def _with_observed(payload, descriptor, error):
    payload["observed_active_document"] = descriptor
    if error:
        payload["observed_active_error"] = error
    return payload


def run_activation(selector, uiapp, read_snapshot=None, registry=None, file_exists=None):
    """Activate the document named by ``selector`` if, and only if, it is eligible.

    Returns (http_status, payload). The handler adds the process identity. Order:
    resolve the token (400/404/503 on any doubt), return 200 without an API call
    when it is already active, refuse an ineligible class with 422 and a machine
    readable reason, otherwise make the single OpenAndActivateDocument(path) call
    with the document's own PathName and report 200 only when the re-read active
    document Equals the target (else 409 with the observed active document).
    """
    from .identity import current_document_descriptors, read_live_snapshot, resolve_document

    read = read_snapshot or read_live_snapshot
    snapshot = read()

    if selector is None:
        listing = current_document_descriptors(snapshot, registry)
        payload = {
            "error": "No document was named. Activation never chooses a default: pass the "
                     "'document' value of exactly one document from list_documents.",
            "error_code": "document-selector-required",
        }
        if listing.get("ok"):
            payload["candidates"] = listing["documents"]
        observed, observed_error = _active_of(listing)
        return 400, _with_observed(payload, observed, observed_error)

    resolved = resolve_document(selector, snapshot, registry)
    if not resolved["ok"]:
        payload = {"error": resolved["error"], "error_code": resolved["code"]}
        if "candidates" in resolved:
            payload["candidates"] = resolved["candidates"]
        observed, observed_error = _observed_active(lambda: snapshot, registry)
        return resolved["status"], _with_observed(payload, observed, observed_error)

    document = resolved["document"]
    descriptor = resolved["descriptor"]
    if descriptor["active"]:
        payload = {
            "status": "success",
            "activation": "already-active",
            "document": descriptor,
            "message": "The document is already the active document; no activation call was made.",
        }
        return 200, _with_observed(payload, descriptor, None)

    reason = activation_refusal_reason(document, file_exists)
    if reason is not None:
        payload = {
            "error": ACTIVATION_REFUSALS[reason],
            "error_code": reason,
            "reason": reason,
            "document": descriptor,
        }
        observed, observed_error = _observed_active(lambda: snapshot, registry)
        return 422, _with_observed(payload, observed, observed_error)

    path = document.PathName
    uiapp.OpenAndActivateDocument(path)

    verified = resolve_document(selector, read(), registry)
    if verified["ok"] and verified["descriptor"]["active"]:
        payload = {
            "status": "success",
            "activation": "activated",
            "document": verified["descriptor"],
            "message": "The document is now the active document (re-read from Revit).",
        }
        return 200, _with_observed(payload, verified["descriptor"], None)
    observed, observed_error = _observed_active(read, registry)
    payload = {
        "error": "The activation call returned but the document is not the active document "
                 "now; it was not activated. No other path was tried and nothing was saved "
                 "or reopened.",
        "error_code": "document-not-activated",
        "reason": "document-not-activated",
        "document": descriptor,
    }
    return 409, _with_observed(payload, observed, observed_error)


def _selector_from_request(request):
    """(selector, problem): the 'document' value of a text/plain JSON body, or why not."""
    from .textutils import parse_request_data

    body = getattr(request, "data", None) if request is not None else None
    if body is None or body == b"" or body == "":
        return None, None
    try:
        data = parse_request_data(body)
    except Exception:
        return None, "The request body is not valid JSON."
    if not isinstance(data, dict):
        return None, "The request body must be a JSON object with a 'document' value."
    return data.get("document"), None


def register_documents_routes(api):
    """Register the document listing route with the API"""
    from pyrevit import routes  # inside: keeps cold start cheap and the module importable offline

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

    @api.route("/activate_document/", methods=["POST"])
    def activate_document(request):
        """
        Make one already-open saved document the active document in Revit.

        Payload: {"document": "<selector from /documents/>"}. Only a saved,
        non-workshared document with an existing file path is activated; every
        other class is refused with a named reason and HTTP 422 before any API
        call. Success (200) means the re-read active document Equals the target.
        Every reply carries process_identity and observed_active_document.
        """
        identity = None
        identity_error = None
        try:
            from .identity import process_identity_or_error
            from pyrevit import HOST_APP

            identity, identity_error = process_identity_or_error()
            selector, problem = _selector_from_request(request)
            if problem:
                status, payload = 400, {"error": problem, "error_code": "request-body-invalid"}
            else:
                status, payload = run_activation(selector, HOST_APP.uiapp)
        except Exception as e:
            logger.error("activate_document failed: {}".format(str(e)))
            status, payload = 500, {"error": str(e), "error_code": "activation-error"}
        if identity:
            payload["process_identity"] = identity
        else:
            payload["identity_error"] = identity_error
        return routes.make_response(data=payload, status=status)

    logger.info("Documents routes registered successfully")
