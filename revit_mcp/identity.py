# -*- coding: UTF-8 -*-
"""Process identity and the live-document registry (helper module, no routes).

Process identity: initialized at extension startup, never at first GET. The
token survives repeated initialization within this AppDomain. This is not
literal OS process-creation timing, authentication, or arbitrary-code isolation.

Document registry (plan 02-04, D-05/D-08, accepted G2 retained-reference-equals-v1):
one lifetime ``Document`` reference is retained per issued opaque token. On every
request the registry enumerates ``Application.Documents`` afresh, and a retained
reference stays bound only while ``IsValidObject`` is true and exactly one
document of the current enumeration ``Equals`` it. A reference that is invalid or
has no match is retired and its token tombstoned for the rest of the process
incarnation; a replacement document with the same title, path or runtime hash is a
new lifetime and receives a new token. Zero-or-several matches, and a validity or
equality check that raises, are refused by name: never resolved by title, path or
hash, never treated as closure, never retargeted.

Nothing here caches the active document; it is compared with the registry's
documents at request time. Title and path are presentation fields only.

The registry logic is pure Python over duck-typed ``Document`` objects so the
CPython unit suite can drive it with doubles. Imports of System / pyrevit and of
sibling helpers stay inside the functions that need them: this module must stay
importable both as ``revit_mcp.identity`` and standalone.
"""

import re
import threading

_KEY = "genpro_revit_mcp.process_identity.v1"

# Slot that keeps the document registry alive for the whole process incarnation.
REGISTRY_KEY = "genpro_revit_mcp.document_registry.v1"

# doc1.<registry generation>.<counter>: opaque. Never derived from title, path or
# any runtime hash; the generation makes a lost registry unable to reissue a token.
_TOKEN_SHAPE = re.compile(r"^doc1\.([0-9a-f]{12})\.([1-9][0-9]*)$")

_INACCESSIBLE = "document-identity-unavailable"
_AMBIGUOUS = "document-identity-ambiguous"
_ACTIVE_UNKNOWN = "document-active-unknown"

_REFUSAL_STATUS = {
    _INACCESSIBLE: 503,
    _AMBIGUOUS: 400,
    _ACTIVE_UNKNOWN: 503,
}


def initialize_process_identity():
    """Assign one GUID in our owned AppDomain slot during extension startup."""
    import System

    domain = System.AppDomain.CurrentDomain
    token = domain.GetData(_KEY)
    if token is None:
        token = str(System.Guid.NewGuid())
        domain.SetData(_KEY, token)
    return token


def get_process_identity(revit_version):
    """Read the initialized token and actual bound primary RoutesServer port.

    No configured/default/request port is a substitute for server_address.
    Missing startup state or unavailable bound server fails rather than guessing.
    """
    import System
    from pyrevit.coreutils import envvars

    token = System.AppDomain.CurrentDomain.GetData(_KEY)
    if not token:
        raise RuntimeError("Process identity unavailable: extension startup initialization missing")
    primary = envvars.get_pyrevit_env_var(envvars.ROUTES_SERVER)
    if primary is None:
        raise RuntimeError("Process identity unavailable: no retained RoutesServer")
    port = int(primary.server.server_address[1])
    if port < 1 or port > 65535:
        raise RuntimeError("Process identity unavailable: invalid bound port")
    version = str(revit_version) if revit_version is not None else ""
    if not version.strip():
        raise RuntimeError("Process identity unavailable: Revit version missing")
    return {
        "pid": int(System.Diagnostics.Process.GetCurrentProcess().Id),
        "actual_port": port,
        "session_token": str(token),
        "revit_version": version,
    }


def process_identity_or_error(uiapp=None):
    """(identity, None) or (None, reason): a route reports, it never raises.

    A route handler that pyRevit dispatches in the Revit API context passes the
    ``uiapp`` it was injected with; the version is then read from that object. Without
    one the process-global HOST_APP is used, as before.
    """
    try:
        if uiapp is not None:
            return get_process_identity(uiapp.Application.VersionNumber), None
        from pyrevit import HOST_APP

        return get_process_identity(HOST_APP.app.VersionNumber), None
    except Exception as exc:
        return None, str(exc) or exc.__class__.__name__


# ----------------------------------------------------------------- registry


class LocalStore(object):
    """A process-local key/value slot, used where there is no AppDomain (CPython tests)."""

    def __init__(self):
        self._values = {}

    def get(self, key):
        return self._values.get(key)

    def set(self, key, value):
        self._values[key] = value


class _AppDomainStore(object):
    """The owned AppDomain slot, the same mechanism as the process token."""

    def get(self, key):
        import System

        return System.AppDomain.CurrentDomain.GetData(key)

    def set(self, key, value):
        import System

        System.AppDomain.CurrentDomain.SetData(key, value)


_FALLBACK_STORE = LocalStore()


def _default_store():
    try:
        import System  # noqa: F401
    except ImportError:
        return _FALLBACK_STORE
    return _AppDomainStore()


def _new_generation():
    try:
        import System

        return str(System.Guid.NewGuid()).replace("-", "")[:12].lower()
    except ImportError:
        import uuid

        return uuid.uuid4().hex[:12]


def _is_linked(document):
    """A link's document is never a model to select or mutate.

    If the flag cannot be read the document is kept: that can only make the
    default selection refuse as ambiguous, never pick a wrong target.
    """
    try:
        return bool(document.IsLinked)
    except Exception:
        return False


def _safe_equals(left, right):
    """True / False, or None when the check itself raised."""
    try:
        return bool(left.Equals(right))
    except Exception:
        return None


def _bind(reference, current):
    """Bind one retained lifetime against the request-time enumeration.

    Returns (verdict, matches, detail): verdict is "bound" (exactly one match),
    "retired" (invalid or no match: the lifetime is gone), "ambiguous" (several
    matches) or "inaccessible" (a check raised: neither alive nor closed).
    """
    try:
        valid = bool(reference.IsValidObject)
    except Exception as exc:
        return "inaccessible", [], "IsValidObject raised: {}".format(str(exc) or exc.__class__.__name__)
    if not valid:
        return "retired", [], None
    matches = []
    for candidate in current:
        verdict = _safe_equals(reference, candidate)
        if verdict is None:
            return "inaccessible", [], "Equals raised while comparing against an open document"
        if verdict:
            matches.append(candidate)
    if not matches:
        return "retired", [], None
    if len(matches) > 1:
        return "ambiguous", matches, "{} open documents Equal this lifetime".format(len(matches))
    return "bound", matches, None


def _counter_of(token):
    return int(_TOKEN_SHAPE.match(token).group(2))


class Observation(object):
    """What one request-time reconciliation established."""

    def __init__(self):
        self.entries = []        # [{"token", "document", "active"}] in enumeration order
        self.unresolved = {}     # token -> (code, detail)
        self.complete = True     # False: the eligible set cannot be known
        self.unknown_active = False

    def entry_for(self, token):
        for entry in self.entries:
            if entry["token"] == token:
                return entry
        return None


class DocumentRegistry(object):
    """Opaque tokens bound to document lifetimes for one process incarnation."""

    def __init__(self):
        self.generation = _new_generation()
        self._next = 1
        self._retained = {}      # token -> the lifetime Document reference
        self._tombstones = set()  # tokens whose lifetime ended: never reissued, never revived
        self._lock = threading.RLock()

    def _issue(self, document):
        token = "doc1.{}.{}".format(self.generation, self._next)
        self._next += 1
        self._retained[token] = document
        return token

    def classify(self, selector):
        """What a selector is, without looking at Revit: invalid, stale, closed, live or unknown."""
        if not isinstance(selector, str):
            return "invalid"
        match = _TOKEN_SHAPE.match(selector)
        if match is None:
            return "invalid"
        if match.group(1) != self.generation:
            return "stale"
        if selector in self._tombstones:
            return "closed"
        if selector in self._retained:
            return "live"
        return "unknown"

    def observe(self, documents, active):
        """Reconcile retained lifetimes with a fresh enumeration; issue tokens to new ones."""
        with self._lock:
            observation = Observation()
            current = [d for d in documents if not _is_linked(d)]
            bound = {}       # token -> the enumeration's wrapper
            claimed = set()  # ids of enumeration wrappers some retained lifetime matched

            for token, reference in list(self._retained.items()):
                verdict, matches, detail = _bind(reference, current)
                if verdict == "retired":
                    del self._retained[token]
                    self._tombstones.add(token)
                elif verdict == "bound":
                    bound[token] = matches[0]
                    claimed.add(id(matches[0]))
                elif verdict == "ambiguous":
                    observation.unresolved[token] = (_AMBIGUOUS, detail)
                    for match in matches:
                        claimed.add(id(match))
                else:
                    observation.unresolved[token] = (_INACCESSIBLE, detail)

            owners = {}
            for token, wrapper in bound.items():
                owners.setdefault(id(wrapper), []).append(token)
            for tokens in owners.values():
                if len(tokens) > 1:
                    for token in tokens:
                        observation.unresolved[token] = (
                            _AMBIGUOUS, "several retained lifetimes bind one open document")
                        bound.pop(token, None)

            # A new lifetime is issued a token only when nothing retained is in doubt:
            # an unreadable retained lifetime could be this very document.
            if not observation.unresolved:
                for wrapper in current:
                    if id(wrapper) in claimed:
                        continue
                    clashes = [(t, _safe_equals(ref, wrapper)) for t, ref in self._retained.items()]
                    doubtful = [t for t, verdict in clashes if verdict is None]
                    equal = [t for t, verdict in clashes if verdict]
                    for token in doubtful:
                        observation.unresolved[token] = (
                            _INACCESSIBLE, "Equals raised while comparing against an open document")
                    for token in equal:
                        observation.unresolved[token] = (
                            _AMBIGUOUS, "a second enumerated document Equals this lifetime")
                        bound.pop(token, None)
                    if doubtful or equal:
                        break
                    bound[self._issue(wrapper)] = wrapper

            observation.complete = not observation.unresolved
            by_wrapper = dict((id(w), t) for t, w in bound.items())
            for wrapper in current:
                token = by_wrapper.get(id(wrapper))
                if token is None:
                    continue
                flag = False
                if active is not None:
                    flag = _safe_equals(wrapper, active)
                    if flag is None:
                        observation.unknown_active = True
                observation.entries.append({"token": token, "document": wrapper, "active": flag})
            return observation


def get_document_registry(store=None):
    """The one registry of this process incarnation, kept in an owned slot.

    A slot that holds anything else (or nothing) gets a new registry with a new
    generation, so a registry that was lost can never reissue an earlier token:
    tokens of the previous generation are refused as stale, by name.
    """
    if store is None:
        store = _default_store()
    registry = store.get(REGISTRY_KEY)
    if registry is None or not hasattr(registry, "observe") or not hasattr(registry, "classify"):
        registry = DocumentRegistry()
        store.set(REGISTRY_KEY, registry)
    return registry


def read_live_snapshot(uiapp=None):
    """(documents, active_document) read from Revit now; never cached.

    ``documents`` is a fresh enumeration of Application.Documents; the active
    document is the UI's active document, or None when no document is active.

    A route handler that pyRevit dispatches in the Revit API context passes the
    ``uiapp`` it was injected with, and everything is then read through that object
    (``uiapp.Application`` and ``uiapp.ActiveUIDocument``). Without one the
    process-global HOST_APP is used, as before.
    """
    if uiapp is not None:
        application = uiapp.Application
    else:
        from pyrevit import HOST_APP

        uiapp = HOST_APP.uiapp
        application = HOST_APP.app
    documents = [document for document in application.Documents]
    ui_document = uiapp.ActiveUIDocument
    return documents, (ui_document.Document if ui_document is not None else None)


# ----------------------------------------------------- descriptors, resolution


def _descriptor(entry):
    from .textutils import sanitize_string, sanitize_value

    document = entry["document"]
    try:
        title = sanitize_string(document.Title)
    except Exception:
        title = "Unnamed"
    try:
        path = sanitize_value(document.PathName)
    except Exception:
        path = ""
    return {
        "document": entry["token"],
        "title": title,
        "path": path,
        "active": entry["active"],
        "saved": bool(path),
    }


def _refusal(status, code, error, observation=None):
    result = {"ok": False, "status": status, "code": code, "error": error}
    if observation is not None and observation.complete and not observation.unknown_active:
        result["candidates"] = [_descriptor(entry) for entry in observation.entries]
    return result


def _doubt_refusal(observation):
    """The refusal for a registry in doubt, or None when the observation is clean."""
    if observation.unresolved:
        order = [_INACCESSIBLE, _AMBIGUOUS]
        items = sorted(observation.unresolved.items(),
                       key=lambda item: (order.index(item[1][0]), item[0]))
        code = items[0][1][0]
        detail = "; ".join("{}: {}".format(token, why[1]) for token, why in items)
        return _refusal(
            _REFUSAL_STATUS[code], code,
            "Open documents cannot be told apart safely right now ({}). Nothing was "
            "selected or changed; do not fall back to the active document.".format(detail))
    if observation.unknown_active:
        return _refusal(
            _REFUSAL_STATUS[_ACTIVE_UNKNOWN], _ACTIVE_UNKNOWN,
            "Which open document is active could not be determined. Nothing was "
            "selected or changed.")
    return None


def _snapshot_and_registry(snapshot, registry):
    if snapshot is None:
        snapshot = read_live_snapshot()
    if registry is None:
        registry = get_document_registry()
    return snapshot, registry


def current_document_descriptors(snapshot=None, registry=None):
    """Every open (non-link) document with its selector and active flag, read now.

    Returns {"ok": True, "documents": [...], "count": n, "active_document": token
    or None}; an empty list is valid data. A registry in doubt (an unreadable or
    ambiguous lifetime) returns {"ok": False, "status", "code", "error"} instead
    of a list that might hide a document.
    """
    snapshot, registry = _snapshot_and_registry(snapshot, registry)
    observation = registry.observe(snapshot[0], snapshot[1])
    refusal = _doubt_refusal(observation)
    if refusal is not None:
        return refusal
    documents = [_descriptor(entry) for entry in observation.entries]
    active = None
    for descriptor in documents:
        if descriptor["active"]:
            active = descriptor["document"]
    return {"ok": True, "documents": documents, "count": len(documents), "active_document": active}


_SELECTOR_HELP = (
    "A document selector is the opaque 'document' value that list_documents "
    "returns; a title or a path is never a selector."
)


def resolve_document(selector, snapshot=None, registry=None):
    """Resolve one explicit document selector against the documents open now.

    Success: {"ok": True, "document": <Document>, "descriptor": {...}}.
    Refusal: {"ok": False, "status", "code", "error"[, "candidates"]} with 400
    invalid selector or ambiguous lifetime, 404 stale / closed (tombstoned) /
    unknown token, 503 identity or active state unreadable. A closed or unknown
    selector is never answered with whatever document is open or active now.
    """
    snapshot, registry = _snapshot_and_registry(snapshot, registry)
    observation = registry.observe(snapshot[0], snapshot[1])
    return _resolve_observed(registry, observation, selector)


def _resolve_observed(registry, observation, selector):
    """resolve_document over an observation already taken for this request."""
    kind = registry.classify(selector)
    if kind == "invalid":
        return _refusal(400, "document-selector-invalid",
                        "Invalid document selector. " + _SELECTOR_HELP, observation)
    if kind == "stale":
        return _refusal(404, "document-token-stale",
                        "This document selector was issued by an earlier registry of this "
                        "Revit process and cannot be honoured. List the documents again.",
                        observation)
    if kind == "closed":
        return _refusal(404, "document-closed",
                        "The document behind selector {} was closed; its selector is retired "
                        "for good. No other document was substituted. List the documents "
                        "again.".format(selector), observation)
    if kind == "unknown":
        return _refusal(404, "document-token-unknown",
                        "Selector {} was never issued by this Revit process. {}".format(
                            selector, _SELECTOR_HELP), observation)
    if selector in observation.unresolved:
        code, detail = observation.unresolved[selector]
        return _refusal(_REFUSAL_STATUS[code], code,
                        "The document behind selector {} cannot be identified safely right "
                        "now ({}). Nothing was selected or changed.".format(selector, detail))
    entry = observation.entry_for(selector)
    if entry is None:
        # A live token that is neither bound nor unresolved cannot occur; refuse, never guess.
        return _refusal(404, "document-token-unknown",
                        "Selector {} did not resolve to an open document.".format(selector),
                        observation)
    if entry["active"] is None:
        return _refusal(_REFUSAL_STATUS[_ACTIVE_UNKNOWN], _ACTIVE_UNKNOWN,
                        "Whether the document is active could not be determined.")
    return {"ok": True, "document": entry["document"], "descriptor": _descriptor(entry)}


# ------------------------------------------------------- mutation decision


def _active_token(observation):
    for entry in observation.entries:
        if entry["active"]:
            return entry["token"]
    return None


def _require_active(result, observation):
    """D-10: a mutation only ever lands on the document active in the UI."""
    if result["descriptor"]["active"]:
        return result
    refusal = _refusal(
        412, "document-not-active",
        "The document {} is open but is not the active document in Revit. This call "
        "does not activate a document and did not change anything. Make it active "
        "with the separate activation step, then retry with the same selector.".format(
            result["descriptor"]["document"]),
        observation)
    refusal["active_document"] = _active_token(observation)
    return refusal


def decide_mutation_document(selector, snapshot=None, registry=None):
    """The named decision a mutating route takes before it touches any document.

    With a selector (D-08, D-10): the one document it names, only if it is open
    AND active in the UI; open but inactive is 412; closed, stale or unknown is
    404; a title or path is 400. Nothing falls back to another document.

    Without one (D-09): the only open, eligible (non-link) document, again only
    if it is active (else 412). No document is 503. Several documents is 400
    "document-selector-required" with every candidate listed; the UI's current
    selection is never used to choose between them.

    Returns {"ok": True, "document", "descriptor"} or a refusal with "status"
    (400, 404, 412, 503), "code", "error" and, where the open set is known,
    "candidates". Identity comes from the registry's retained-reference Equals
    resolution, never from title or path.
    """
    snapshot, registry = _snapshot_and_registry(snapshot, registry)
    observation = registry.observe(snapshot[0], snapshot[1])
    if selector is not None:
        resolved = _resolve_observed(registry, observation, selector)
        if not resolved["ok"]:
            return resolved
        return _require_active(resolved, observation)
    refusal = _doubt_refusal(observation)
    if refusal is not None:
        return refusal
    entries = observation.entries
    if not entries:
        return _refusal(503, "no-open-document", "No document is open in this Revit process.",
                        observation)
    if len(entries) > 1:
        return _refusal(
            400, "document-selector-required",
            "{} documents are open and the call named none. Pass the 'document' value of "
            "exactly one of the candidates; the document active in the UI is not "
            "assumed.".format(len(entries)), observation)
    entry = entries[0]
    return _require_active(
        {"ok": True, "document": entry["document"], "descriptor": _descriptor(entry)}, observation)


def mutation_document_or_response(selector=None, snapshot=None, registry=None,
                                  identity=None, read_snapshot=None, uiapp=None):
    """Route-handler guard: call it explicitly first, in every mutating handler.

    Returns (document, descriptor, None) when the decision is ok, else
    (None, None, response) where response is a routes.make_response carrying
    {error, error_code, process_identity, candidates[, active_document]} at the
    decision's status. Never raises: an unreadable Revit state is a 503 response.
    Explicit per-handler call only (G1): no wrapper or decorator is installed
    in startup.py.

    A handler that pyRevit dispatches in the Revit API context passes the ``uiapp`` it
    was injected with; the snapshot and the process identity are then read through it
    and never through the process-global HOST_APP.
    """
    try:
        if snapshot is None:
            snapshot = read_snapshot() if read_snapshot else read_live_snapshot(uiapp)
        decision = decide_mutation_document(selector, snapshot, registry)
    except Exception as exc:
        decision = {
            "ok": False, "status": 503, "code": "document-registry-unavailable",
            "error": "The open documents could not be read ({}). Nothing was selected or "
                     "changed.".format(str(exc) or exc.__class__.__name__),
        }
    if decision["ok"]:
        return decision["document"], decision["descriptor"], None
    from pyrevit import routes

    identity_error = None
    if identity is None:
        identity, identity_error = process_identity_or_error(uiapp)
    payload = {"error": decision["error"], "error_code": decision["code"]}
    if identity:
        payload["process_identity"] = identity
    else:
        payload["identity_error"] = identity_error
    for key in ("candidates", "active_document"):
        if key in decision:
            payload[key] = decision[key]
    return None, None, routes.make_response(data=payload, status=decision["status"])


# ------------------------------------------------- request selector and attribution


def request_document_selector(request):
    """The ``document`` value of a mutating request body, or None when none was sent.

    Never raises. An absent key, an empty or unreadable body, or a body that is not a
    JSON object is None: the handler's own parse then reports its own error exactly as
    before, and nothing has been touched. A key that is present but null is an explicit,
    broken choice, so it is returned as "" (an invalid selector the guard refuses) and
    never reads as "omitted", which would fall back to the one-open-document default.
    """
    try:
        raw = getattr(request, "data", None)
        if not raw:
            return None
        from .textutils import parse_request_data

        data = parse_request_data(raw)
    except Exception:
        return None
    if not isinstance(data, dict) or "document" not in data:
        return None
    value = data["document"]
    return "" if value is None else value


def attribute_response(response, descriptor, uiapp=None, identity=None):
    """Stamp the document a mutation ran on, and the process, onto its reply (IDENT-02).

    ``descriptor`` is the one the guard returned for this request, so the reply names the
    document the handler actually worked on, at request time, whatever the outcome: a
    success, a validation error, a rolled-back or failed reply all carry it. The reply
    keeps its status and every other key. A reply whose data is not a dict is returned
    untouched. Never raises.
    """
    try:
        data = getattr(response, "data", None)
        if not isinstance(data, dict):
            return response
        data["document"] = dict(descriptor)
        identity_error = None
        if identity is None:
            identity, identity_error = process_identity_or_error(uiapp)
        if identity:
            data["process_identity"] = identity
        else:
            data["identity_error"] = identity_error
    except Exception:
        pass
    return response
