# -*- coding: utf-8 -*-
"""The mutation-safety policy: what a call to each Revit route needs before it is sent (Phase 7).

CPython side only. The policy is data, a TOML file that ships beside this module
(policy.base.toml, D-16): for every route the decision (allow, confirm, deny, or a named
built-in check), the reasons the confirmation window states, whether the route is bound
to a document, and which read-only facts the window may show. A route that is not listed
is denied by the caller (unknown_route): nothing is classified by default.

Nothing here reads a file at import. The base policy is read on first use, in a worker
thread, and kept; an invalid base is a PolicyError on every call, never a silent fallback.
This module never prints, never logs, never touches stdout and imports nothing from mcp.

This is the minimum validation the first slice needs (schema, ranges, decisions, check
names, route keys of tools); the closed vocabularies of reasons, facts and operator
overlays belong to plan 07-04.
"""

import asyncio
import dataclasses
import hashlib
import os
import tomllib
import types
from typing import Any, Mapping, Optional, Tuple

SCHEMA_VERSION = 1
BASE_FILE = "policy.base.toml"
DECISIONS = ("allow", "confirm", "deny", "check")
CHECKS = ("parameter_write", "family_edit")
METHODS = ("GET", "POST")

CONFIRM_TIMEOUT_RANGE = (30, 900)
PERMIT_TTL_RANGE = (10, 110)


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


def _text_list(path: str, value: Any) -> Tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        _fail(path, "must be a list of text")
    return tuple(value)


def _setting_int(settings: dict, name: str, low: int, high: int) -> int:
    value = settings.get(name)
    if type(value) is not int or not low <= value <= high:
        _fail("settings.{}".format(name), "must be an integer in {}..{}".format(low, high))
    return value


def build_policy(document: dict, source: str, policy_hash: str) -> Policy:
    """Validate a parsed document and return the immutable Policy (PolicyError names the key path)."""
    if not isinstance(document, dict):
        _fail("policy", "must be a table")
    if document.get("schema") != SCHEMA_VERSION or type(document.get("schema")) is not int:
        _fail("schema", "must be {}".format(SCHEMA_VERSION))
    settings = document.get("settings")
    if not isinstance(settings, dict):
        _fail("settings", "missing")
    checked = {
        "confirm_timeout_s": _setting_int(settings, "confirm_timeout_s", *CONFIRM_TIMEOUT_RANGE),
        "permit_ttl_s": _setting_int(settings, "permit_ttl_s", *PERMIT_TTL_RANGE),
    }
    fop = settings.get("shared_parameters_file")
    if fop is not None:
        if not isinstance(fop, str):
            _fail("settings.shared_parameters_file", "must be text")
        checked["shared_parameters_file"] = fop

    routes = document.get("routes")
    if not isinstance(routes, dict) or not routes:
        _fail("routes", "missing")
    rules = {}
    for key, entry in routes.items():
        path = 'routes."{}"'.format(key)
        if not isinstance(entry, dict):
            _fail(path, "must be a table")
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
        bound = entry.get("document_bound", False)
        if not isinstance(bound, bool):
            _fail(path + ".document_bound", "must be true or false")
        facts = entry.get("facts", "none")
        if not isinstance(facts, str):
            _fail(path + ".facts", "must be text")
        rules[key] = Rule(
            route=key, method=method, decision=decision,
            reasons=_text_list(path + ".reasons", entry.get("reasons", [])),
            check=check,
            confirm_when=_text_list(path + ".confirm_when", entry.get("confirm_when", [])),
            document_bound=bound, facts=facts)

    tools = document.get("tools", {})
    if not isinstance(tools, dict):
        _fail("tools", "must be a table")
    frozen_tools = {}
    for name, entry in tools.items():
        path = "tools.{}".format(name)
        if not isinstance(entry, dict):
            _fail(path, "must be a table")
        keys = _text_list(path + ".routes", entry.get("routes"))
        for key in keys:
            if key not in rules:
                _fail(path + ".routes", "names {!r}, which is not in [routes]".format(key))
        frozen_tools[name] = types.MappingProxyType(
            {"routes": keys, "local": bool(entry.get("local", False))})

    return Policy(
        schema=SCHEMA_VERSION,
        settings=types.MappingProxyType(checked),
        rules=types.MappingProxyType(rules),
        tools=types.MappingProxyType(frozen_tools),
        source=source,
        hash=policy_hash)


def _normalized(data: Optional[bytes]) -> bytes:
    return (data or b"").replace(b"\r\n", b"\n")


def policy_hash(base_bytes: bytes, operator_bytes: Optional[bytes] = None) -> str:
    """12 hex characters over the LF-normalized base and operator bytes, NUL between them."""
    digest = hashlib.sha256(_normalized(base_bytes) + b"\x00" + _normalized(operator_bytes))
    return digest.hexdigest()[:12]


def load_base(path: Optional[str] = None) -> Policy:
    """The base policy file beside this module (or ``path``), parsed, validated and hashed."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), BASE_FILE)
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise PolicyError("base policy file cannot be read: {}".format(type(exc).__name__)) from exc
    return build_policy(parse_policy_bytes(data), "base", policy_hash(data))


_ACTIVE: Optional[Policy] = None


async def current() -> Policy:
    """The active policy: the base, read once in a worker thread and kept.

    Raises PolicyError while the base is invalid (it is read again on the next call, so
    a repaired file is picked up); the caller turns it into a refusal, so a broken policy
    blocks mutations instead of allowing them.
    """
    global _ACTIVE
    if _ACTIVE is None:
        _ACTIVE = await asyncio.to_thread(load_base)
    return _ACTIVE


def _reset() -> None:
    """Forget the loaded policy (tests)."""
    global _ACTIVE
    _ACTIVE = None
