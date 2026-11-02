# -*- coding: utf-8 -*-
"""The authorization step in front of every mutating Revit call (Phase 7).

CPython side only. bridge.revit_post hands every POST outside the open reads to
authorize(), before the per-incarnation lock is taken, so the human wait never holds the
queue (D-07). authorize() asks the policy what the route needs:

* allow  - a Grant at once;
* confirm - one confirmation window in the MCP client (server-side elicitation, D-05),
  and a Grant only when the client answers accept;
* deny   - a Refusal;
* check  - a built-in check using bounded read-only Revit facts (D-10); shared-parameter
  additions also require a GUID/name match in the company file (D-22).

Document tokens are pinned before confirmation. After accept, the same preflight is repeated;
changed facts or an unsuccessful re-check void consent before a mutation can be sent.

A Grant carries the one-time permit minted over the exact argument text (permit.py), bound
to the target's session token and the policy hash. The policy is read again after the human
answers: an accept given under a policy that has since changed is refused (policy_changed). A Refusal carries text that says the
request was NOT sent and nothing changed.

Consent is the action of the client's answer on the server's own request, nothing else:
not the assistant's text, not any argument, not the content of an accept (the Hermes client
sends accept with empty content). A client that cannot show the window is "unavailable".

Known limits:
A process that can read the shared secret can mint its own one-time permits: the permit stops callers on the LAN, a stray curl and an outdated payload, not an agent running with the user's own OS rights.
Confirming execute_revit_code is not a review of the code: arbitrary code can still do anything the Revit API allows, including binding a shared parameter that is not in the company file.
A permit is bound to its own request bytes; it does not fix cross-process overlap in pyRevit's shared handler (backlog 999.1).
load_family is confirmed, but the shared parameters inside the loaded family file are not checked against the company shared-parameter file.
Which operations need a confirmation is the default of the base policy; the fleet operator can change any rule, relaxing ones included.
A client that redelivers an already executed allow-class call to a new server process can run it a second time without a window; a confirm-class call always opens a new window.

This module never prints, never logs and imports nothing from mcp at module level, so
importing bridge keeps the cold start cheap (ask_human imports mcp.types inside).
"""

import asyncio
import dataclasses
import hashlib
import json
import re
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


def _quote(value: Any) -> str:
    """Single-line quoted data, not instructions; length is measured before cleaning."""
    def clean(item):
        if isinstance(item, str):
            return _plain(item)
        if isinstance(item, dict):
            return {_plain(str(key)): clean(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(val) for val in item]
        return item

    original = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), default=str)
    cleaned = clean(value)
    if not isinstance(cleaned, str):
        cleaned = _plain(json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"), default=str))
    suffix = " (длина {})".format(len(original)) if len(original) > VALUE_MAX else ""
    return json.dumps(cleaned[:VALUE_MAX], ensure_ascii=False) + suffix


REASON_TEXT = {
    "delete": "удаление элементов", "transform": "перемещение / копирование / поворот / отражение элементов",
    "parameter_write": "запись параметров", "type_parameter": "параметр типа: изменение затронет все экземпляры типа",
    "multiple_elements": "затронуто больше одного элемента", "overwrites_value": "перезаписывается непустое значение",
    "group_member": "элемент в группе: значение может измениться у других экземпляров группы (не проверено)",
    "facts_unavailable": "факты из модели получить не удалось", "execute_code": "выполнение произвольного кода",
    "load_family": "загрузка семейства", "edit_family": "правка и перезагрузка семейства",
    "shared_parameter_source": "источник общих параметров не подтверждён",
    "family_contents_unchecked": "содержимое семейства не проверено",
    "parameter_definition": "определение параметра проекта", "create": "создание элементов",
    "read": "чтение", "view_state": "изменение вида", "file_io": "операция с файлом",
    "document_state": "изменение состояния документа", "process_local": "локальная операция",
}


def _fact(value):
    if value is None or value == "unknown":
        return "неизвестно"
    if isinstance(value, bool):
        return "да" if value else "нет"
    return _quote(value)


def facts_digest(reply) -> str:
    """Bind all supplied facts and the selected document token, not incidental reply fields."""
    descriptor = (reply.get("document") or {}) if isinstance(reply, dict) else {}
    payload = {"document": descriptor.get("document"),
               "facts": reply.get("facts") if isinstance(reply, dict) else None}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _fact_lines(request, preflight):
    facts = preflight.get("facts") if isinstance(preflight, dict) else None
    if not isinstance(facts, dict) or facts.get("available") is not True:
        return ["Факты из модели: неизвестно"]
    route = request.route
    if route in ("/set_parameter/", "/modify_element/"):
        element = facts.get("element") or {}
        lines = []
        for parameter in (facts.get("parameters") or [])[:3]:
            name = parameter.get("name")
            if parameter.get("resolved") == "type" or element.get("is_type") is True:
                count = element.get("type_instance_count")
                impact = ("затронет {} экземпляров".format(count) if isinstance(count, int) else
                          "затронет: неизвестно" + (" (подсчёт остановлен на пределе)" if element.get("count_capped") else ""))
                lines.append("параметр типа {} у типа {} — {}".format(_fact(name), _fact(element.get("type")), impact))
            else:
                level = {"instance": "экземпляр", "not_found": "не найден"}.get(parameter.get("resolved"), "неизвестно")
                lines.append("параметр {}: уровень {}".format(_fact(name), level))
            new = request.data.get("value") if route == "/set_parameter/" else (request.data.get("parameters") or {}).get(name)
            lines.append("текущее {} (raw {}) → новое {} (raw, внутренние единицы)".format(
                _fact(parameter.get("display_value")), _fact(parameter.get("raw_value")), _quote(new)))
        return lines or ["Параметры: неизвестно"]
    if route in ("/delete_elements/", "/transform_elements/"):
        lines = ["{}: {} (найдено {}, не найдено: {})".format(
            "элементов к удалению" if route == "/delete_elements/" else "элементов к трансформации",
            facts.get("requested", "неизвестно"), facts.get("found", "неизвестно"),
            ", ".join(_plain(str(x))[:VALUE_MAX] for x in facts.get("missing", [])) if "missing" in facts else "неизвестно"),
            "категории: {}".format(_fact(facts.get("categories"))),
            "каскад удаления: неизвестно"]
        if (facts.get("kinds") or {}).get("parameter_definition", 0):
            lines.insert(0, "Удаляется определение параметра проекта и его значения.")
        return lines
    if route == "/edit_family/":
        family = facts.get("family") or {}
        shared = facts.get("shared") or {}
        lines = ["Семейство: {}; экземпляров: {}".format(_fact(family.get("name")), _fact(family.get("instance_count")))]
        definitions = shared.get("definitions", [])
        for item in definitions:
            verdict = (preflight.get("fop") or {}).get("verdicts", {}).get(item.get("name"))
            words = {"match": "совпадает с ФОП", "unresolved": "не разрешён", "ambiguous": "неоднозначен",
                     "not_in_fop": "нет в ФОП", "name_mismatch": "имя не совпадает"}
            lines.append("Общий параметр {}: {}".format(_quote(item.get("name")), words.get(verdict, "неизвестно")))
        lines.append("Файл общих параметров Revit: {}".format(_fact(shared.get("configured_file"))))
        return lines
    if route == "/load_family/":
        file = facts.get("file") or {}
        return ["Файл: {}; размер: {}; уже загружено: {}".format(
            _fact(file.get("path")), _fact(file.get("size")), _fact(facts.get("already_loaded")))]
    return ["Факты: неизвестно"]


def build_message(request: AuthorizationRequest, rule: policy.Rule, decision=None, code=None,
                  timeout_s: int = 300, preflight=None) -> str:
    """Russian plain-text window, at most 1500 characters; fixed warnings survive trimming."""
    if isinstance(decision, str) and code is None:  # existing callers supply the operation code third
        code, decision = decision, None
    reasons = decision.reasons if decision is not None else rule.reasons
    descriptor = (preflight or {}).get("document") or {}
    if request.route == "/execute_code/":
        document = "не привязан (код выполняется в Revit)"
    elif descriptor:
        document = "«{}» — {}".format(_plain(str(descriptor.get("title", "неизвестно")))[:120],
                                     _fact(descriptor.get("path")))
    else:
        document = "не определён"
    fixed = ["Код операции: {}".format(code),
             "Revit MCP просит подтвердить операцию (окно действует {} мин).".format(max(1, round(timeout_s / 60))),
             "Инструмент: {} (маршрут {})".format(_plain(str(getattr(request.call, "tool", None) or request.route))[:60], request.route),
             "Revit: PID {}, порт {}".format(request.target.get("pid"), request.target.get("port")),
             "Документ: " + document,
             "Причины: " + "; ".join(REASON_TEXT.get(reason, "причина неизвестна") for reason in reasons)]
    excerpt = ""
    if request.route == "/execute_code/":
        source = request.data.get("code", "")
        fixed.extend(["длина кода: {}".format(len(source)),
                      "SHA-256: " + hashlib.sha256(source.encode("utf-8")).hexdigest()[:16],
                      "произвольный код, безопасность содержимого не проверяется"])
        excerpt = "Код (начало, данные): " + json.dumps(_plain(source[:600]), ensure_ascii=False)
    if request.route == "/delete_elements/":
        fixed.append("Будут удалены также зависимые элементы; точный каскад удаления: неизвестно.")
    if request.route == "/load_family/":
        fixed.extend(["содержимое семейства: неизвестно", "общие параметры внутри семейства не проверяются по ФОП"])
    if request.route == "/edit_family/" and request.data.get("reload", True):
        fixed.append("перезагрузка перезапишет значения параметров у всех экземпляров")
    final = "Ответьте «Да», чтобы выполнить ровно эту операцию один раз, или «Нет», чтобы отменить."
    details = _fact_lines(request, preflight) if request.route != "/execute_code/" else []
    arguments = ["- {} = {}".format(_quote(str(key)[:KEY_MAX]), _quote(value))
                 for key, value in list(request.data.items())[:ARGUMENT_LINES] if key != "code"]
    # Reserve the final question and prioritize facts over normalized argument display.
    result = "\n".join(fixed)
    budget = 1500 - len(final) - 2
    if len(result) > budget:
        result = result[:budget - 1] + "…"
    for line in details + arguments + ([excerpt] if excerpt else []):
        room = budget - len(result) - 1
        if room <= 0:
            break
        result += "\n" + (line if len(line) <= room else line[:max(0, room - 1)] + "…")
    return result + "\n" + final


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


_PREFLIGHT_FACTS = frozenset(("parameter", "elements", "family", "load"))
_DOCUMENT_REFUSAL = re.compile(r"^Error: (400|404|412|503) - (.*)", re.DOTALL)


async def _preflight(request):
    body = {"route": request.route, "args": request.data}
    if "document" in request.data:
        body["document"] = request.data["document"]
    try:
        return await request.read_post("/mutation_preflight/", body)
    except asyncio.CancelledError:
        raise
    except Exception:
        return None


def _valid_preflight(reply):
    return (isinstance(reply, dict) and reply.get("status") == "ok"
            and isinstance(reply.get("document"), dict)
            and isinstance(reply["document"].get("document"), str)
            and bool(reply["document"]["document"])
            and isinstance(reply.get("facts"), dict))


async def _fop(request, pol, reply, *, force=False):
    if not request.data.get("add_shared_parameters"):
        return None
    facts = reply.get("facts") if _valid_preflight(reply) else None
    if not facts or facts.get("available") is not True:
        return None
    definitions = (facts.get("shared") or {}).get("definitions")
    if not isinstance(definitions, list):
        return None
    return await policy.fop_for(definitions, pol.settings.get("shared_parameters_file"), force=force)


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

    needs_preflight = rule.facts in _PREFLIGHT_FACTS
    preflight = await _preflight(request) if needs_preflight else None
    refusal = _DOCUMENT_REFUSAL.match(preflight) if isinstance(preflight, str) else None
    if refusal:
        denied = _refuse("denied", ["preflight_refused"], pol)
        return dataclasses.replace(denied, text=denied.text + " Revit: " + _plain(refusal.group(2))[:300])
    if not _valid_preflight(preflight):
        preflight = None
    facts = preflight["facts"] if preflight else None
    fop = await _fop(request, pol, preflight) if rule.check == "family_edit" else None
    effective_decision = policy.decide(rule, request.data, facts=facts, fop=fop)
    if preflight and rule.document_bound and "document" not in request.data:
        request = dataclasses.replace(request, data=dict(request.data, document=preflight["document"]["document"]))
    if preflight and fop is not None:
        preflight = dict(preflight, fop=fop)
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
                message = build_message(request, effective, effective_decision, code,
                                        timeout_s=pol.confirm_timeout_s, preflight=preflight)
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
            return _refuse("denied", reasons + ["policy_invalid"], None, "confirm", answered)
        if latest.hash != pol.hash:
            return _refuse("denied", reasons + ["policy_changed"], latest, "confirm", answered)
        if needs_preflight:
            checked = await _preflight(request)
            try:
                unchanged = (_valid_preflight(checked) and preflight is not None
                             and facts_digest(checked) == facts_digest(preflight))
            except (TypeError, ValueError):
                unchanged = False
            if not unchanged:
                return _refuse("denied", reasons + ["facts_changed"], latest, "confirm", answered)
            if rule.check == "family_edit" and request.data.get("add_shared_parameters"):
                checked_fop = await _fop(request, latest, checked, force=True)
                if policy.decide(rule, request.data, checked["facts"], checked_fop).decision == "deny":
                    return _refuse("denied", reasons + ["shared_parameter_source"], latest, "confirm", answered)
        return _grant(request, latest, "confirm", reasons, "accepted", wait_ms)
    label, why = _ANSWERS[answer]
    return _refuse(label, reasons + [why], pol, "confirm",
                   {"approval": answer, "approval_wait_ms": wait_ms})
