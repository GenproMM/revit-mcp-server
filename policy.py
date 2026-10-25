# -*- coding: utf-8 -*-
"""The mutation-safety policy: what a call to each Revit route needs before it is sent (Phase 7).

CPython side only. The policy is data, a TOML file that ships beside this module
(policy.base.toml, D-16): for every route the decision (allow, confirm, deny, or a named
built-in check), the reasons the confirmation window states, whether the route is bound
to a document, and which read-only facts the window may show. A route that is not listed
is denied by the caller (unknown_route): nothing is classified by default.

Nothing here reads a file at import. The base policy is read on first use, in a worker
thread, and kept; an invalid base is a PolicyError on every call, never a silent fallback.
The optional operator file (REVIT_MCP_POLICY_FILE, else the path staged in policy_source)
is re-read at most every two seconds, in a worker thread under a three second cap, and
applied atomically only when it is complete, stable and valid.
This module never prints, never logs, never touches stdout and imports nothing from mcp.

Validation is strict and closed (D-16): every key, word, type and number of a policy file
must come from the vocabularies below, or the whole file is invalid; nothing named in a file
is ever evaluated, imported or opened. An invalid base policy is a release defect (D-17:
"should not happen in a release"; deploy/gate.py refuses to build such a payload) and blocks
the gated routes at run time. The operator layer (D-14, D-15) overlays the base by route key
and by settings key and may set any decision, including allow for a destructive route; it
can neither add a route nor change a route's method, document binding or facts.
"""

import asyncio
import copy
import dataclasses
import hashlib
import os
import time
import tomllib
import types
from typing import Any, Mapping, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_VERSION = 1
BASE_FILE = "policy.base.toml"
DECISIONS = ("allow", "confirm", "deny", "check")
CHECKS = ("parameter_write", "family_edit")
METHODS = ("GET", "POST")

# Closed vocabularies (D-16). A word outside them invalidates the file that carries it.
REASONS = frozenset((
    "create", "read", "view_state", "file_io", "document_state", "process_local", "delete",
    "transform", "load_family", "edit_family", "execute_code", "parameter_write",
    "type_parameter", "multiple_elements", "overwrites_value", "facts_unavailable",
    "group_member", "shared_parameter_source", "family_contents_unchecked",
    "parameter_definition"))
CONFIRM_WHEN = frozenset((
    "type_parameter", "multiple_elements", "overwrites_value", "facts_unavailable",
    "group_member"))
FACTS = ("none", "parameter", "elements", "family", "load", "code")
SETTINGS_RANGES = {"confirm_timeout_s": (30, 900), "permit_ttl_s": (10, 110)}
SETTINGS_TEXT = ("shared_parameters_file",)
OPERATOR_ROUTE_KEYS = ("decision", "reasons", "check", "confirm_when")
STRUCTURAL_ROUTE_KEYS = ("method", "document_bound", "facts")
BASE_TOP_KEYS = ("schema", "settings", "routes", "tools")
OPERATOR_TOP_KEYS = ("schema", "settings", "routes")
TOOL_KEYS = ("routes", "local")

CONFIRM_TIMEOUT_RANGE = SETTINGS_RANGES["confirm_timeout_s"]
PERMIT_TTL_RANGE = SETTINGS_RANGES["permit_ttl_s"]
KEY_SHOWN = 60   # characters of a file's own key shown in a message


class PolicyError(ValueError):
    """The policy file is unreadable or invalid; the text names the key path, never a secret."""


@dataclasses.dataclass(frozen=True)
class Rule:
    """One route's rule."""

    route: str
    method: str
    decision: str
    reasons: Tuple[str, ...]
    check: Optional[str]
    confirm_when: Tuple[str, ...]
    document_bound: bool
    facts: str


@dataclasses.dataclass(frozen=True)
class Policy:
    """An immutable, validated policy."""

    schema: int
    settings: Mapping[str, Any]
    rules: Mapping[str, Rule]
    tools: Mapping[str, Mapping[str, Any]]
    source: str
    hash: str

    def rule_for(self, route: str) -> Optional[Rule]:
        """The rule of a route key such as "/delete_elements/", or None when it is unlisted."""
        return self.rules.get(route)

    @property
    def confirm_timeout_s(self) -> int:
        return self.settings["confirm_timeout_s"]

    @property
    def permit_ttl_s(self) -> int:
        return self.settings["permit_ttl_s"]


def parse_policy_bytes(data: bytes) -> dict:
    """The TOML document held by the bytes of a policy file (a UTF-8 BOM is tolerated)."""
    try:
        text = data.decode("utf-8-sig")
    except (UnicodeDecodeError, AttributeError) as exc:
        raise PolicyError("policy file is not UTF-8 text: {}".format(type(exc).__name__)) from exc
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError("policy file is not valid TOML: {}".format(exc)) from exc


def _fail(path: str, message: str):
    raise PolicyError("{}: {}".format(path, message))


def _shown(key: Any) -> str:
    """A key of the file's own, printable and short, for a message path (never a value)."""
    text = "".join(ch if ch.isprintable() else "?" for ch in str(key))
    return text if len(text) <= KEY_SHOWN else text[:KEY_SHOWN] + "..."


def _route_path(key: Any) -> str:
    return 'routes."{}"'.format(_shown(key))


def _check_keys(path: str, table: dict, allowed) -> None:
    for key in table:
        if key not in allowed:
            _fail("{}.{}".format(path, _shown(key)) if path else _shown(key), "unknown key")


def _text_list(path: str, value: Any) -> Tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _fail(path, "must be a list of text")
    return tuple(value)


def _words(path: str, value: Any, vocabulary) -> Tuple[str, ...]:
    """A list of words that all belong to ``vocabulary`` (the message never repeats a word)."""
    words = _text_list(path, value)
    for word in words:
        if word not in vocabulary:
            _fail(path, "unknown word (not in the closed vocabulary)")
    return words


def _setting_int(settings: dict, name: str, low: int, high: int) -> int:
    value = settings.get(name)
    if type(value) is not int or not low <= value <= high:
        _fail("settings.{}".format(name), "must be an integer in {}..{}".format(low, high))
    return value


def _check_schema(document: dict) -> None:
    if type(document.get("schema")) is not int or document.get("schema") != SCHEMA_VERSION:
        _fail("schema", "must be {}".format(SCHEMA_VERSION))


def _check_settings(settings: Any, required: bool) -> None:
    """Settings keys come from SETTINGS_RANGES and SETTINGS_TEXT; each value has its type and range."""
    if not isinstance(settings, dict):
        _fail("settings", "must be a table")
    _check_keys("settings", settings, tuple(SETTINGS_RANGES) + SETTINGS_TEXT)
    for name, (low, high) in SETTINGS_RANGES.items():
        if required or name in settings:
            _setting_int(settings, name, low, high)
    for name in SETTINGS_TEXT:
        if name in settings and not isinstance(settings[name], str):
            _fail("settings.{}".format(name), "must be text")


def _check_route(path: str, entry: Any) -> None:
    """One merged route table: keys, method, decision (GET is allow only), check, words, facts."""
    if not isinstance(entry, dict):
        _fail(path, "must be a table")
    _check_keys(path, entry, STRUCTURAL_ROUTE_KEYS + OPERATOR_ROUTE_KEYS)
    method = entry.get("method")
    if method not in METHODS:
        _fail(path + ".method", "must be one of {}".format(METHODS))
    decision = entry.get("decision")
    if decision not in DECISIONS:
        _fail(path + ".decision", "must be one of {}".format(DECISIONS))
    if method == "GET" and decision != "allow":
        _fail(path + ".decision", "a GET route can only be allow (nothing can enforce more)")
    check = entry.get("check")
    if decision == "check":
        if check not in CHECKS:
            _fail(path + ".check", "must be one of {}".format(CHECKS))
    elif check is not None:
        _fail(path + ".check", "is only valid with decision check")
    if not isinstance(entry.get("document_bound", False), bool):
        _fail(path + ".document_bound", "must be true or false")
    facts = entry.get("facts", "none")
    if not isinstance(facts, str) or facts not in FACTS:
        _fail(path + ".facts", "must be one of {}".format(FACTS))
    _words(path + ".reasons", entry.get("reasons", []), REASONS)
    _words(path + ".confirm_when", entry.get("confirm_when", []), CONFIRM_WHEN)


def validate_base(document: Any) -> None:
    """Raise PolicyError (key path only, never file content) unless ``document`` is a valid policy.

    Used for the base file and, after an overlay, for the merged document. Nothing in a
    document is ever evaluated: every key, word, type and number is checked against the
    closed vocabularies above.
    """
    if not isinstance(document, dict):
        _fail("policy", "must be a table")
    _check_keys("", document, BASE_TOP_KEYS)
    _check_schema(document)
    _check_settings(document.get("settings"), required=True)

    routes = document.get("routes")
    if not isinstance(routes, dict) or not routes:
        _fail("routes", "missing")
    for key, entry in routes.items():
        _check_route(_route_path(key), entry)

    tools = document.get("tools", {})
    if not isinstance(tools, dict):
        _fail("tools", "must be a table")
    for name, entry in tools.items():
        path = "tools.{}".format(_shown(name))
        if not isinstance(entry, dict):
            _fail(path, "must be a table")
        _check_keys(path, entry, TOOL_KEYS)
        for key in _text_list(path + ".routes", entry.get("routes")):
            if key not in routes:
                _fail(path + ".routes", "names a route that is not in [routes]")
        if not isinstance(entry.get("local", False), bool):
            _fail(path + ".local", "must be true or false")


def build_policy(document: dict, source: str, policy_hash: str) -> Policy:
    """Validate a parsed document and return the immutable Policy (PolicyError names the key path)."""
    validate_base(document)
    settings = document["settings"]
    checked = {name: settings[name] for name in SETTINGS_RANGES}
    for name in SETTINGS_TEXT:
        if name in settings:
            checked[name] = settings[name]

    rules = {}
    for key, entry in document["routes"].items():
        rules[key] = Rule(
            route=key, method=entry["method"], decision=entry["decision"],
            reasons=tuple(entry.get("reasons", [])),
            check=entry.get("check"),
            confirm_when=tuple(entry.get("confirm_when", [])),
            document_bound=entry.get("document_bound", False),
            facts=entry.get("facts", "none"))

    frozen_tools = {}
    for name, entry in document.get("tools", {}).items():
        frozen_tools[name] = types.MappingProxyType(
            {"routes": tuple(entry["routes"]), "local": bool(entry.get("local", False))})

    return Policy(
        schema=SCHEMA_VERSION,
        settings=types.MappingProxyType(checked),
        rules=types.MappingProxyType(rules),
        tools=types.MappingProxyType(frozen_tools),
        source=source,
        hash=policy_hash)


def validate_operator(document: Any, base_document: dict) -> None:
    """Raise PolicyError unless the operator ``document`` is acceptable over ``base_document`` (D-14, D-15).

    The operator may set any decision and replace reasons, check and confirm_when of a route
    the base lists, and any settings key. It cannot add a route, a tool or a top-level key,
    change a route's method, document_bound or facts, or turn a GET route into anything but
    allow. One defect rejects the whole file.
    """
    if not isinstance(document, dict):
        _fail("operator policy", "must be a table")
    _check_keys("", document, OPERATOR_TOP_KEYS)
    _check_schema(document)
    if "settings" in document:
        _check_settings(document["settings"], required=False)
    routes = document.get("routes", {})
    if not isinstance(routes, dict):
        _fail("routes", "must be a table")
    base_routes = base_document.get("routes", {})
    for key, entry in routes.items():
        path = _route_path(key)
        if key not in base_routes:
            _fail(path, "is not a route of the base policy (an operator cannot add routes)")
        if not isinstance(entry, dict):
            _fail(path, "must be a table")
        for name in entry:
            if name in STRUCTURAL_ROUTE_KEYS:
                _fail("{}.{}".format(path, name), "cannot be changed by the operator")
        _check_keys(path, entry, OPERATOR_ROUTE_KEYS)
    # The merged document must be valid as a whole (GET stays allow, check pairs with a check name, words).
    validate_base(_overlay(base_document, document))


def _overlay(base_document: dict, operator_document: dict) -> dict:
    """The base with the operator's settings keys and route keys laid over it (no validation)."""
    merged = copy.deepcopy(base_document)
    merged["settings"].update(copy.deepcopy(operator_document.get("settings", {})))
    for key, entry in operator_document.get("routes", {}).items():
        route = merged["routes"][key]
        route.update(copy.deepcopy(entry))
        # A route relaxed away from "check" no longer carries the base's check name.
        if route.get("decision") != "check" and "check" not in entry:
            route.pop("check", None)
    return merged


def merge(base_document: dict, operator_document: dict) -> dict:
    """The merged document (a new dict; neither input changes). Raises PolicyError like validate_operator.

    Settings keys replace the base values; a route overlay replaces only the keys it names
    (lists are replaced, not appended).
    """
    validate_operator(operator_document, base_document)
    return _overlay(base_document, operator_document)


def _normalized(data: Optional[bytes]) -> bytes:
    return (data or b"").replace(b"\r\n", b"\n")


def policy_hash(base_bytes: bytes, operator_bytes: Optional[bytes] = None) -> str:
    """12 hex characters over the LF-normalized base and operator bytes, NUL between them."""
    digest = hashlib.sha256(_normalized(base_bytes) + b"\x00" + _normalized(operator_bytes))
    return digest.hexdigest()[:12]


def _read_base(path: str):
    """(Policy, bytes, document) of a base policy file; PolicyError when it is unreadable or invalid."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise PolicyError("base policy file cannot be read: {}".format(type(exc).__name__)) from exc
    document = parse_policy_bytes(data)
    return build_policy(document, "base", policy_hash(data)), data, document


def load_base(path: Optional[str] = None) -> Policy:
    """The base policy file beside this module (or ``path``), parsed, validated and hashed."""
    if path is None:
        path = os.path.join(_HERE, BASE_FILE)
    return _read_base(path)[0]


# ------------------------------------------------------------- the operator file

POLICY_FILE_ENV = "REVIT_MCP_POLICY_FILE"
POLICY_SOURCE_FILE = "policy_source"
RELOAD_INTERVAL_S = 2.0   # a gated call re-reads the operator file when this much time has passed
READ_TIMEOUT_S = 3.0      # cap on the worker-thread read of the share (research Pitfall 9)
DEBOUNCE_S = 0.2          # the file is read twice this far apart; a torn write differs (Pitfall 15)
MAX_OPERATOR_BYTES = 262144
_SOURCE_MAX = 4096

OPERATOR_STATES = ("not_configured", "absent", "pending", "accepted", "rejected", "unreachable")
_ABSENT_WINERRORS = (None, 2, 3)   # file / path not found; any other WinError (67 "network name not found") is unreachable

_debounce_sleep = time.sleep       # tests replace it; the worker thread looks it up at call time


def operator_path(source_dir: Optional[str] = None) -> Optional[str]:
    """Where the operator policy lives (D-27): REVIT_MCP_POLICY_FILE, else the first line of policy_source.

    ``policy_source`` is staged beside this module by the payload build and holds one UNC
    path; the text is returned byte-identical (Cyrillic included). An empty or blank value
    in either place counts as absent. Reads one small local file; the store calls it in a
    worker thread, never on the event loop.
    """
    value = os.environ.get(POLICY_FILE_ENV, "").strip()
    if value:
        return value
    directory = source_dir if source_dir is not None else _HERE
    try:
        with open(os.path.join(directory, POLICY_SOURCE_FILE), "rb") as handle:
            raw = handle.read(_SOURCE_MAX)
        lines = raw.decode("utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    first = lines[0].strip() if lines else ""
    return first or None


def _read_file(path: str) -> bytes:
    """The bytes of the operator file, at most one byte more than the cap (the store rejects a longer one)."""
    with open(path, "rb") as handle:
        return handle.read(MAX_OPERATOR_BYTES + 1)


class PolicyStore:
    """The active policy: the base, plus the operator overlay when a valid, stable file exists (D-14..D-17).

    ``current()`` re-reads the operator file at most every RELOAD_INTERVAL_S (or when forced),
    in a worker thread under a READ_TIMEOUT_S cap, reading twice DEBOUNCE_S apart. A file
    is applied only when both reads agree, it parses and it validates as a whole; the new
    immutable Policy replaces the old by one reference assignment, so a concurrent caller
    sees the old or the new object, never a mix. Anything else leaves the active policy as it
    was (an invalid update keeps the last valid operator version; a first invalid file
    leaves the base) and sets ``operator_state`` and ``diagnostic``. A deleted file is the
    one case that falls back to the base ("absent"). An invalid base raises PolicyError on
    every call (blocked): nothing weaker is substituted.
    """

    def __init__(self, base_path: Optional[str] = None, reader=None, clock=None,
                 source_dir: Optional[str] = None):
        self._base_path = base_path or os.path.join(_HERE, BASE_FILE)
        self._reader = reader or _read_file
        self._clock = clock or time.monotonic
        self._source_dir = source_dir
        self._base: Optional[Policy] = None
        self._base_bytes = b""
        self._base_document: dict = {}
        self._base_error: Optional[str] = None
        self._active: Optional[Policy] = None
        self._operator_sha: Optional[str] = None
        self._operator_file: Optional[str] = None
        self._state = "not_configured"
        self._diagnostic: Optional[str] = None
        self._last_check: Optional[float] = None
        self._refreshing = False

    async def current(self, force: bool = False) -> Policy:
        """The active Policy; PolicyError while the base is invalid. Never blocks the loop on the share."""
        base = await self._ensure_base()
        now = self._clock()
        due = force or self._last_check is None or now - self._last_check >= RELOAD_INTERVAL_S
        if due and not self._refreshing:
            self._refreshing = True
            self._last_check = now
            try:
                await self._refresh(base)
            finally:
                self._refreshing = False
        return self._active

    def status(self) -> dict:
        """What the policy is right now. Never raises; the keys are always the same."""
        try:
            active = self._active
            blocked = self._base is None and self._base_error is not None
            return {
                "source": active.source if active else None,
                "hash": active.hash if active else None,
                "operator_file": self._operator_file,
                "operator_state": self._state,
                "diagnostic": self._diagnostic,
                "blocked": blocked,
                "blocked_reason": self._base_error if blocked else None,
                "confirm_timeout_s": active.confirm_timeout_s if active else None,
                "permit_ttl_s": active.permit_ttl_s if active else None,
            }
        except Exception:  # a status call must never be the thing that fails
            return {"source": None, "hash": None, "operator_file": None,
                    "operator_state": "unreachable", "diagnostic": "status failed",
                    "blocked": True, "blocked_reason": "status failed",
                    "confirm_timeout_s": None, "permit_ttl_s": None}

    # ----------------------------------------------------------------- internals

    async def _ensure_base(self) -> Policy:
        if self._base is not None:
            return self._base
        try:
            base, data, document = await asyncio.to_thread(_read_base, self._base_path)
        except PolicyError as exc:
            self._base_error = str(exc)
            raise
        if self._base is None:  # a concurrent first call may have finished first
            self._base, self._base_bytes, self._base_document = base, data, document
            self._base_error = None
            self._active = base
            self._operator_sha = None
            self._last_check = None
        return self._base

    def _read_operator(self):
        """Worker thread: (path, first read, second read), or (None, None, None) when no path is configured."""
        path = operator_path(self._source_dir)
        self._operator_file = path
        if not path:
            return None, None, None
        first = self._reader(path)
        _debounce_sleep(DEBOUNCE_S)
        return path, first, self._reader(path)

    def _set(self, state: str, diagnostic: Optional[str]) -> None:
        self._state = state
        self._diagnostic = diagnostic

    def _fall_back_to_base(self, state: str, diagnostic: Optional[str]) -> None:
        self._active = self._base
        self._operator_sha = None
        self._set(state, diagnostic)

    async def _refresh(self, base: Policy) -> None:
        try:
            path, first, second = await asyncio.wait_for(
                asyncio.to_thread(self._read_operator), READ_TIMEOUT_S)
        except FileNotFoundError as exc:
            if getattr(exc, "winerror", None) in _ABSENT_WINERRORS:
                self._fall_back_to_base("absent", "operator policy file not found")
            else:  # a share that cannot be reached is not a deleted file: keep what is active
                self._set("unreachable", type(exc).__name__)
            return
        except Exception as exc:  # OSError, the read timeout, a failing reader: keep the active policy
            self._set("unreachable", type(exc).__name__)
            return
        if path is None:
            self._fall_back_to_base("not_configured", None)
            return
        if first != second:
            self._set("pending", "operator policy file changed between two reads")
            return
        if not isinstance(first, (bytes, bytearray)) or len(first) > MAX_OPERATOR_BYTES:
            self._set("rejected", "operator policy file is not a readable file of at most "
                                  "{} bytes".format(MAX_OPERATOR_BYTES))
            return
        first = bytes(first)
        digest = hashlib.sha256(first).hexdigest()
        if digest == self._operator_sha:
            self._set("accepted", None)
            return
        try:
            merged = merge(self._base_document, parse_policy_bytes(first))
            new = build_policy(merged, "operator", policy_hash(self._base_bytes, first))
        except PolicyError as exc:
            self._set("rejected", str(exc))
            return
        self._active = new  # one reference assignment: callers see the old or the new object
        self._operator_sha = digest
        self._set("accepted", None)


_STORE: Optional[PolicyStore] = None


def _store() -> PolicyStore:
    global _STORE
    if _STORE is None:
        _STORE = PolicyStore()
    return _STORE


async def current(force: bool = False) -> Policy:
    """The active policy of this process (see PolicyStore.current); PolicyError while the base is invalid.

    The caller turns the error into a refusal, so a broken policy blocks mutations instead
    of allowing them.
    """
    return await _store().current(force=force)


async def status(refresh: bool = True) -> dict:
    """The policy status dict; refreshes first (forced) unless ``refresh`` is false. Never raises."""
    try:
        await current(force=refresh)
    except PolicyError:
        pass
    except Exception:  # the status is read for display; a failure shows in the dict, not as an error
        pass
    return _store().status()


def _reset() -> None:
    """Forget the store and everything it loaded (tests)."""
    global _STORE
    _STORE = None
