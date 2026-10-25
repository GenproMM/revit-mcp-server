# -*- coding: utf-8 -*-
"""The authorization step in front of every mutating Revit call (Phase 7).

CPython side only. bridge.revit_post hands every POST outside the open reads to
authorize(), before the per-incarnation lock is taken, so the human wait never holds the
queue (D-07). authorize() asks the policy what the route needs:

* allow  - a Grant at once;
* confirm - one confirmation window in the MCP client (server-side elicitation, D-05),
  and a Grant only when the client answers accept;
* deny   - a Refusal;
* check  - a built-in check; in this slice a check with no facts means confirm (D-10), and
  a shared-parameter family edit is denied because the company file cannot be checked yet
  (D-22).

A Grant carries the one-time permit minted over the exact argument text (permit.py), bound
to the target's session token and the policy hash. The policy is read again after the human
answers: an accept given under a policy that has since changed is refused (policy_changed). A Refusal carries text that says the
request was NOT sent and nothing changed.

Consent is the action of the client's answer on the server's own request, nothing else:
not the assistant's text, not any argument, not the content of an accept (the Hermes client
sends accept with empty content). A client that cannot show the window is "unavailable".

This module never prints, never logs and imports nothing from mcp at module level, so
importing bridge keeps the cold start cheap (ask_human imports mcp.types inside).
"""

import asyncio
import dataclasses
import json
import secrets
import time
import unicodedata
from typing import Any, Callable, Optional, Tuple

import permit
import policy

EMPTY_FORM = {"type": "object", "properties": {}}

ARGUMENT_LINES = 10      # argument lines shown in the window
VALUE_MAX = 120          # characters of one shown value
KEY_MAX = 60             # characters of one shown argument name

# Elicitation clients may coalesce visually similar simultaneous requests. Keep one window
# open per running MCP event loop, while retaining per-loop ownership (an asyncio.Lock cannot
# be safely shared by the separate loops the unit suite and some MCP hosts create).
_WINDOW_LOCKS = {}


def _window_lock():
    """The confirmation-window lock for the active event loop."""
    loop = asyncio.get_running_loop()
    key = id(loop)
    lock = _WINDOW_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _WINDOW_LOCKS[key] = lock
    return lock


@dataclasses.dataclass(frozen=True)
class AuthorizationRequest:
    """What the bridge asks the authorizer: the call as it will be sent, and how to reach its target."""

    route: str
    endpoint: str
    data: dict
    ctx: Any
    target: dict
    call: Any
    secret: Optional[str]
    read_post: Callable
    timeout: float


@dataclasses.dataclass(frozen=True)
class Grant:
    """The call may be sent: the final body data, its exact text and its permit (None = no permit)."""

    data: dict
    args_text: str
    permit: Optional[dict]
    audit_fields: dict


@dataclasses.dataclass(frozen=True)
class Refusal:
    """The call must not be sent: a label, reason codes and the text the model reads."""

    label: str
    reasons: Tuple[str, ...]
    text: str
    audit_fields: dict


def operation_code() -> str:
    """Six uppercase hex characters that make each window's text unique."""
    return secrets.token_hex(3).upper()


# ----------------------------------------------------------------------- texts

_SUFFIX = ("Nothing was changed. Do not retry automatically; a new call opens a new "
           "confirmation window.")


def refusal_text(label: str, reasons) -> str:
    """The text of a refusal: it says the request was NOT sent, why, and that nothing changed."""
    reasons = list(reasons)
    if "approval_declined" in reasons:
        why = "DECLINED by the user in the confirmation window."
    elif "approval_cancelled" in reasons:
        why = ("NOT CONFIRMED: the confirmation window was cancelled "
               "(подтверждение не получено).")
    elif label == "expired" or "approval_timeout" in reasons:
        why = ("NOT CONFIRMED: no answer within the time limit (EXPIRED; "
               "подтверждение не получено).")
    elif "approval_unavailable" in reasons:
        why = ("UNAVAILABLE: this client cannot show a confirmation window "
               "(MCP elicitation).")
    elif "approval_error" in reasons:
        why = ("NOT CONFIRMED: the client failed to show or answer the confirmation window "
               "(MCP elicitation).")
    elif "policy_changed" in reasons:
        why = ("NOT CONFIRMED: the approval policy changed while the window was open; "
               "ask again.")
    elif "no_secret" in reasons:
        why = ("DENIED: this MCP server has no shared secret, so no permit can be issued. "
               "Run the Update RevitMCP shortcut and restart the assistant session.")
    else:
        why = "DENIED by policy ({}).".format(", ".join(reasons))
    return "Error: the request was NOT sent to Revit: {} {}".format(why, _SUFFIX)


def _plain(text: str) -> str:
    """Text without control, format, line-separator and unassigned characters (no spoofed lines)."""
    return "".join(ch for ch in text
                   if not unicodedata.category(ch).startswith("C") and ch not in "  ")


def _shown(value: Any) -> str:
    """A model-controlled value as compact JSON, cleaned, cut to VALUE_MAX with its length."""
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        text = str(value)
    text = _plain(text)
    if len(text) > VALUE_MAX:
        return "{} (длина {})".format(text[:VALUE_MAX], len(text))
    return text


def build_message(request: AuthorizationRequest, rule: policy.Rule, code: str,
                  fact_lines=(), timeout_s: int = 300) -> str:
    """The Russian confirmation text. The first line is the operation code."""
    minutes = max(1, int(round(timeout_s / 60.0)))
    tool = getattr(request.call, "tool", None) or request.route
    target = request.target
    lines = [
        "Код операции: {}".format(code),
        "Revit MCP просит подтвердить операцию (окно действует {} мин).".format(minutes),
        "Инструмент: {} (маршрут {})".format(tool, request.route),
        "Revit: PID {}, порт {}".format(target.get("pid"), target.get("port")),
        "Причины: {}".format(", ".join(rule.reasons) if rule.reasons else "-"),
    ]
    lines.extend(fact_lines)
    items = list(request.data.items()) if isinstance(request.data, dict) else []
    for key, value in items[:ARGUMENT_LINES]:
        lines.append("- {} = {}".format(_plain(str(key))[:KEY_MAX], _shown(value)))
    if len(items) > ARGUMENT_LINES:
        lines.append("- … ещё аргументов: {}".format(len(items) - ARGUMENT_LINES))
    lines.append("Ответьте «Да», чтобы выполнить ровно эту операцию один раз, "
                 "или «Нет», чтобы отменить.")
    return "\n".join(lines)


# ----------------------------------------------------------------------- human

async def ask_human(ctx: Any, message: str, timeout_s: float) -> str:
    """Show ``message`` in the client and return one word; never raises except CancelledError.

    "accepted", "declined", "cancelled", "expired" (no answer in time), "unavailable"
    (no session, or the client declares no elicitation capability) or "error" (the client
    failed the request). The content of an accept is ignored: consent is the action only.
    """
    import mcp.types as types  # inside: keeps import bridge free of mcp (cold start)

    try:
        session = getattr(ctx, "session", None)
    except Exception:
        session = None
    if session is None:
        return "unavailable"
    try:
        capable = session.check_client_capability(
            types.ClientCapabilities(elicitation=types.ElicitationCapability()))
        if not capable:
            return "unavailable"
        request_id = ctx.request_id
        result = await session.elicit_form(message, EMPTY_FORM, request_id)
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        return "expired"
    except Exception:
        return "error"
    return {"accept": "accepted", "decline": "declined",
            "cancel": "cancelled"}.get(getattr(result, "action", None), "error")


# ------------------------------------------------------------------- authorize

def _refuse(label: str, reasons, pol: Optional[policy.Policy], decision: str = "deny",
            extra: Optional[dict] = None) -> Refusal:
    fields = {"decision": decision, "reasons": list(reasons)}
    if pol is not None:
        fields["policy"] = {"source": pol.source, "hash": pol.hash}
    if extra:
        fields.update(extra)
    return Refusal(label, tuple(reasons), refusal_text(label, reasons), fields)


def _grant(request: AuthorizationRequest, pol: policy.Policy, decision: str, reasons,
           approval: str, wait_ms: int = 0) -> Grant:
    text = permit.args_text(request.data)
    minted = permit.mint(request.secret, request.route, text,
                         request.target["session_token"], pol.hash, pol.permit_ttl_s)
    return Grant(request.data, text, minted, {
        "policy": {"source": pol.source, "hash": pol.hash}, "decision": decision,
        "approval": approval, "approval_wait_ms": wait_ms, "reasons": list(reasons),
        "permit": minted["n"][:8]})


_ANSWERS = {
    "declined": ("denied", "approval_declined"),
    "cancelled": ("denied", "approval_cancelled"),
    "expired": ("expired", "approval_timeout"),
    "unavailable": ("denied", "approval_unavailable"),
    "error": ("denied", "approval_error"),
}


async def authorize(request: AuthorizationRequest):
    """A Grant, or a Refusal that says nothing was sent. Raises nothing the bridge must not expect."""
    try:
        pol = await policy.current()
    except policy.PolicyError:
        return _refuse("denied", ["policy_invalid"], None)
    rule = pol.rule_for(request.route)
    if rule is None:
        return _refuse("denied", ["unknown_route"], pol)
    if rule.decision == "deny":
        return _refuse("denied", rule.reasons, pol)
    if not request.secret:
        return _refuse("denied", ["no_secret"], pol)

    effective_decision = policy.decide(rule, request.data, facts=None, fop=None)
    decision, reasons = effective_decision.decision, list(effective_decision.reasons)
    if decision == "deny":
        return _refuse("denied", reasons, pol)
    if decision == "allow":
        return _grant(request, pol, "allow", reasons, "none")
    if decision != "confirm":
        return _refuse("denied", ["unknown_decision"], pol)

    effective = dataclasses.replace(rule, decision="confirm", reasons=tuple(reasons))
    started = time.monotonic()
    try:
        # One policy deadline covers both waiting for an earlier window and the client answer.
        # This is before bridge._dispatch, so no target lock or Revit transaction is held here.
        async with asyncio.timeout(pol.confirm_timeout_s):
            async with _window_lock():
                code = operation_code()
                message = build_message(request, effective, code, timeout_s=pol.confirm_timeout_s)
                answer = await ask_human(request.ctx, message, pol.confirm_timeout_s)
    except TimeoutError:
        answer = "expired"
    wait_ms = int((time.monotonic() - started) * 1000)
    if answer == "accepted":
        # SAFE-13: an approval is for the policy that opened the window. Re-read the policy
        # now (forced, so a change applied while the human decided is seen) and refuse when
        # the active hash is no longer the one the window was shown under.
        answered = {"approval": "accepted", "approval_wait_ms": wait_ms}
        try:
            latest = await policy.current(force=True)
        except policy.PolicyError:
            return _refuse("denied", ["policy_invalid"], None, "confirm",
                           dict(answered, reasons=reasons + ["policy_invalid"]))
        if latest.hash != pol.hash:
            return _refuse("denied", ["policy_changed"], latest, "confirm",
                           dict(answered, reasons=reasons + ["policy_changed"]))
        return _grant(request, latest, "confirm", reasons, "accepted", wait_ms)
    label, why = _ANSWERS[answer]
    return _refuse(label, [why], pol, "confirm",
                   {"approval": answer, "approval_wait_ms": wait_ms, "reasons": reasons + [why]})
