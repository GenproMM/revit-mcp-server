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


def _observed_sentence(descriptor, error):
    if descriptor is not None:
        return "The document active in Revit now is {} ({}).".format(
            descriptor["document"], descriptor["title"])
    if error:
        return "Which document is active now could not be read ({}).".format(error)
    return "No listed document is active in Revit now."


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
    try:
        snapshot = read()
        listing = current_document_descriptors(snapshot, registry) if selector is None else None
        resolved = None if selector is None else resolve_document(selector, snapshot, registry)
    except Exception as exc:
        detail = str(exc) or exc.__class__.__name__
        return 503, _with_observed({
            "error": "The open documents could not be read ({}). Nothing was selected, "
                     "activated or changed.".format(detail),
            "error_code": "document-registry-unavailable",
        }, None, detail)

    if selector is None:
        payload = {
            "error": "No document was named. Activation never chooses a default: pass the "
                     "'document' value of exactly one document from list_documents.",
            "error_code": "document-selector-required",
        }
        if listing.get("ok"):
            payload["candidates"] = listing["documents"]
        observed, observed_error = _active_of(listing)
        return 400, _with_observed(payload, observed, observed_error)

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

    try:
        path = document.PathName
        uiapp.OpenAndActivateDocument(path)
    except Exception as exc:
        # Never success, never a retry with another path, a save, a reopen or a
        # worksharing option: report the failure and what is actually active now.
        observed, observed_error = _observed_active(read, registry)
        payload = {
            "error": "Activating document {} ({}) failed: {}. It was not retried; no other "
                     "path was tried and nothing was saved or reopened. {}".format(
                         descriptor["document"], descriptor["title"],
                         str(exc) or exc.__class__.__name__,
                         _observed_sentence(observed, observed_error)),
            "error_code": "activation-failed",
            "reason": "activation-failed",
            "document": descriptor,
        }
        return 500, _with_observed(payload, observed, observed_error)

    try:
        verified = resolve_document(selector, read(), registry)
    except Exception as exc:
        observed, observed_error = _observed_active(read, registry)
        payload = {
            "error": "Activation of document {} ({}) was requested but the active document "
                     "could not be re-read ({}); it is not known to be activated. {}".format(
                         descriptor["document"], descriptor["title"],
                         str(exc) or exc.__class__.__name__,
                         _observed_sentence(observed, observed_error)),
            "error_code": "activation-unverified",
            "reason": "activation-unverified",
            "document": descriptor,
        }
        return 500, _with_observed(payload, observed, observed_error)
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


# ------------------------------------------------ addressed reads (plan 02-06, D-11)
#
# Exactly two reads may inspect a document that is open but not active: the summary
# and the levels. Each is read ONLY through the Document the registry just resolved
# from the request's token (never the UI's active document, never a retained
# reference, never a global). The UI document is read for nothing here except the
# before/after diagnostics, which go through the same registry snapshot as every
# other route. D-08: a closed token is refused by name, not answered with other data.
# D-12: nothing here activates a document.
#
# Whether pyRevit's dispatch of these production routes leaves the UI focus alone
# was measured only for the 02-20 diagnostic button; the live recheck is 02-07.


def _db():
    """The Revit DB namespace, imported here so this module loads under CPython."""
    from pyrevit import DB

    return DB


def _count_elements(document, db, category=None):
    """Non-type element count of ``document`` itself, optionally within one category."""
    collector = db.FilteredElementCollector(document)
    if category is not None:
        collector = collector.OfCategory(category)
    return int(collector.WhereElementIsNotElementType().GetElementCount())


# (key in the reply, property of the document's own ProjectInformation element)
_PROJECT_INFORMATION_FIELDS = (
    ("name", "Name"),
    ("number", "Number"),
    ("client", "ClientName"),
    ("status", "Status"),
)


def _project_information(document):
    """({key: text}, [unreadable field names]) read from this Document's ProjectInformation.

    A field that cannot be read is omitted and named, never filled from anywhere else.
    """
    from .textutils import sanitize_value

    try:
        info = document.ProjectInformation
        if info is None:
            raise ValueError("the document has no ProjectInformation")
    except Exception as exc:
        logger.warning("project information unreadable: {}".format(str(exc) or exc.__class__.__name__))
        return {}, ["project_information"]
    values = {}
    unreadable = []
    for key, attribute in _PROJECT_INFORMATION_FIELDS:
        try:
            values[key] = sanitize_value(getattr(info, attribute))
        except Exception as exc:
            logger.warning("project information {} unreadable: {}".format(
                key, str(exc) or exc.__class__.__name__))
            unreadable.append("project_information." + key)
    return values, unreadable


def collect_document_summary(document, db=None):
    """The summary of ``document``: title, path, non-type element count, level count,
    project information. Every value is read from this Document and nothing else.

    These are the G3-measured comparison fields, NOT the model_info category subset.
    A count that cannot be read raises (the route turns it into a named 500); only
    project-information fields are omitted individually.
    """
    from .textutils import sanitize_string, sanitize_value

    if db is None:
        db = _db()
    project_information, unreadable = _project_information(document)
    return {"summary": {
        "title": sanitize_string(document.Title),
        "path": sanitize_value(document.PathName),
        "non_type_element_count": _count_elements(document, db),
        "level_count": _count_elements(document, db, db.BuiltInCategory.OST_Levels),
        "project_information": project_information,
        "unreadable_fields": unreadable,
    }}


def _resolve_for_read(selector, read, registry):
    """(snapshot, resolved, None), or (None, None, (status, payload)) for a refusal.

    A refusal is a finished reply: a missing, malformed, stale, unknown, closed or
    ambiguous selector, or an unreadable registry, never falls back to another
    document and never reaches a collector.
    """
    from .identity import current_document_descriptors, resolve_document

    try:
        snapshot = read()
        listing = current_document_descriptors(snapshot, registry) if selector is None else None
        resolved = None if selector is None else resolve_document(selector, snapshot, registry)
    except Exception as exc:
        detail = str(exc) or exc.__class__.__name__
        return None, None, (503, _with_observed({
            "error": "The open documents could not be read ({}). Nothing was selected, "
                     "read or changed.".format(detail),
            "error_code": "document-registry-unavailable",
        }, None, detail))
    if selector is None:
        payload = {
            "error": "No document was named. A read never chooses a default: pass the "
                     "'document' value of exactly one document from list_documents.",
            "error_code": "document-selector-required",
        }
        if listing.get("ok"):
            payload["candidates"] = listing["documents"]
        observed, observed_error = _active_of(listing)
        return None, None, (400, _with_observed(payload, observed, observed_error))
    if not resolved["ok"]:
        payload = {"error": resolved["error"], "error_code": resolved["code"]}
        if "candidates" in resolved:
            payload["candidates"] = resolved["candidates"]
        observed, observed_error = _observed_active(lambda: snapshot, registry)
        return None, None, (resolved["status"], _with_observed(payload, observed, observed_error))
    return snapshot, resolved, None


def run_document_read(selector, collect, read_snapshot=None, registry=None):
    """Resolve ``selector`` and hand the freshly resolved Document to ``collect``.

    Returns (http_status, payload). ``collect(document)`` returns the dict of data
    to merge into the reply. The reply reports whether the target is the active
    document, and the active document before and after the collection as an
    observation (``ui_switched`` is None when it could not be established). This
    function never activates anything and never reads the UI document itself.
    """
    from .identity import read_live_snapshot

    read = read_snapshot or read_live_snapshot
    snapshot, resolved, refusal = _resolve_for_read(selector, read, registry)
    if refusal is not None:
        return refusal
    document = resolved["document"]
    descriptor = resolved["descriptor"]
    before, before_error = _observed_active(lambda: snapshot, registry)
    try:
        data = collect(document)
    except Exception as exc:
        observed, observed_error = _observed_active(read, registry)
        payload = {
            "error": "Reading document {} ({}) failed: {}. Nothing was activated or changed "
                     "and no other document was read in its place. {}".format(
                         descriptor["document"], descriptor["title"],
                         str(exc) or exc.__class__.__name__,
                         _observed_sentence(observed, observed_error)),
            "error_code": "document-read-failed",
            "reason": "document-read-failed",
            "document": descriptor,
        }
        return 500, _with_observed(payload, observed, observed_error)
    after, after_error = _observed_active(read, registry)
    before_token = before["document"] if before else None
    after_token = after["document"] if after else None
    switched = None if (before_error or after_error) else before_token != after_token
    payload = {
        "status": "success",
        "document": descriptor,
        "target_is_active": bool(descriptor["active"]),
        "ui_switched": switched,
        "active_before": before_token,
        "active_after": after_token,
    }
    if before_error:
        payload["active_before_error"] = before_error
    if after_error:
        payload["active_after_error"] = after_error
    payload.update(data)
    return 200, payload


def run_document_summary(selector, read_snapshot=None, registry=None, db=None):
    """Summary of the document named by ``selector``, active or not (D-11)."""
    def collect(document):
        return collect_document_summary(document, db)

    return run_document_read(selector, collect, read_snapshot, registry)


_FEET_TO_MM = 304.8  # tool-facing dimensions are millimeters; Revit stores feet


def _element_id_value(element):
    """The integer value of an element's id, across the Revit 2024-2027 API differences."""
    from .utils import get_element_id_value

    return get_element_id_value(element)


def _level_details(level, element_id):
    """One level as the reply shows it; raises when any part cannot be read."""
    from .textutils import sanitize_string

    name = sanitize_string(level.Name)
    elevation = level.Elevation
    return {
        "name": name,
        "elevation_mm": round(elevation * _FEET_TO_MM, 0),
        "elevation_feet": round(elevation, 4),
        "id": element_id(level),
    }


def collect_document_levels(document, db=None, element_id=None):
    """The levels of ``document``, sorted by elevation, read from this Document only.

    A level that cannot be read is skipped, logged and counted in skipped_levels
    (the existing list_levels behavior), never silently dropped from the count.
    """
    if db is None:
        db = _db()
    if element_id is None:
        element_id = _element_id_value
    elements = (db.FilteredElementCollector(document)
                .OfCategory(db.BuiltInCategory.OST_Levels)
                .WhereElementIsNotElementType()
                .ToElements())
    levels = []
    skipped = 0
    for level in elements:
        try:
            levels.append(_level_details(level, element_id))
        except Exception as exc:
            skipped += 1
            logger.warning("could not process level: {}".format(str(exc) or exc.__class__.__name__))
    levels.sort(key=lambda item: item["elevation_feet"])
    return {"levels": levels, "total_levels": len(levels), "skipped_levels": skipped}


def run_document_levels(selector, read_snapshot=None, registry=None, db=None, element_id=None):
    """Levels of the document named by ``selector``, active or not (D-11)."""
    def collect(document):
        return collect_document_levels(document, db, element_id)

    return run_document_read(selector, collect, read_snapshot, registry)


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


def _read_reply(request, runner):
    """(status, payload) for an addressed-read route: never raises, always names the process."""
    identity = None
    identity_error = None
    try:
        from .identity import process_identity_or_error

        identity, identity_error = process_identity_or_error()
        selector, problem = _selector_from_request(request)
        if problem:
            status, payload = 400, {"error": problem, "error_code": "request-body-invalid"}
        else:
            status, payload = runner(selector)
    except Exception as e:
        logger.error("addressed read failed: {}".format(str(e)))
        status, payload = 500, {"error": str(e), "error_code": "document-read-error"}
    if identity:
        payload["process_identity"] = identity
    else:
        payload["identity_error"] = identity_error
    return status, payload


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

    @api.route("/document_summary/", methods=["POST"])
    def document_summary(request):
        """
        Summary of one open document, active or not, read only through that document.

        Payload: {"document": "<selector from /documents/>"}. Returns title, path,
        non-type element count, level count and project information of exactly that
        document (these are not the model_info category counts), with
        target_is_active and the active document before and after as an observation
        (ui_switched). Nothing is activated. A closed, stale, unknown, ambiguous or
        missing selector is refused by name. Every reply carries process_identity.
        """
        status, payload = _read_reply(request, run_document_summary)
        return routes.make_response(data=payload, status=status)

    @api.route("/document_levels/", methods=["POST"])
    def document_levels(request):
        """
        Levels of one open document, active or not, read only through that document.

        Payload: {"document": "<selector from /documents/>"}. Returns each level's
        name, elevation in millimeters (and feet) and id, sorted by elevation, with
        total_levels, skipped_levels, target_is_active and the active document
        before and after as an observation (ui_switched). Nothing is activated. A
        closed, stale, unknown, ambiguous or missing selector is refused by name.
        Every reply carries process_identity.
        """
        status, payload = _read_reply(request, run_document_levels)
        return routes.make_response(data=payload, status=status)

    logger.info("Documents routes registered successfully")
