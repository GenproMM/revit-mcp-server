# -*- coding: utf-8 -*-
"""One provenance renderer for every tool result (02-16, D-05/D-06/D-15, IDENT-04).

format_response(response) is the only formatter the tool registrars call. The
bridge tags what it returns with provenance metadata (an attribute on a dict or
str subclass, never a key a route could forge) and format_response appends the
visible attribution AFTER its unchanged projection, so a reply collapsed to its
``message`` / ``result`` / ``data`` / ``output`` still names the process that
answered and the document the route reports.

Three kinds of result are told apart:

* received: a complete HTTP reply from an incarnation proven before the send;
  names the verified process and the document the ROUTE reports (never the one
  that was requested);
* not sent / no reply / outcome unknown: nothing is credited to any process or
  document, at most the requested target is named;
* untagged text or dicts (a refusal built inside a tool, a fake transport): no
  suffix, and a ``process_identity`` inside a body is never trusted by itself.

CPython only. HTTP is httpx.MockTransport and netstat is faked: no Revit, no
pyRevit, no network. Needs no Revit.
"""

import asyncio
import base64
import json

import httpx
import pytest

import bridge
from tools.utils import format_response

REAL_SELECTED_CLIENT = bridge._selected_client

PREFIX = "/genpro_revit_mcp"
TOKEN_A = "11111111-1111-4111-8111-111111111111"
TOKEN_B = "22222222-2222-4222-8222-222222222222"
PORT_A, PID_A = 48884, 111
PORT_B, PID_B = 48885, 222

PROCESS_LINE_A = "Verified Revit process: PID 111; Revit 2024; port 48884; session " + TOKEN_A
PROCESS_LINE_B = "Verified Revit process: PID 222; Revit 2025; port 48885; session " + TOKEN_B

NOTICE = ("Arbitrary code is a trusted exception: no document guard or confinement applies and "
          "the documents it changed are not identified or attributed.")


def ident(pid, port, token, version):
    return {"pid": pid, "actual_port": port, "session_token": token, "revit_version": version}


IDENT_A = ident(PID_A, PORT_A, TOKEN_A, "2024")
IDENT_B = ident(PID_B, PORT_B, TOKEN_B, "2025")


def selector(port, pid, token):
    return bridge._selector_for({"host": "127.0.0.1", "port": port, "pid": pid,
                                 "session_token": token})


SEL_A = selector(PORT_A, PID_A, TOKEN_A)
SEL_B = selector(PORT_B, PID_B, TOKEN_B)


def received(value, process=IDENT_A, http_status=200, corroborated=None):
    """What the bridge hands back for a complete reply from a proven process."""
    return bridge._tag(value, {
        "kind": "received", "process": dict(process), "http_status": http_status,
        "corroborated": corroborated,
        "requested": {"address": "127.0.0.1:{}".format(process["actual_port"]),
                      "pid": process["pid"]}})


def uncertain(value, kind, requested=None):
    return bridge._tag(value, {"kind": kind, "process": None, "http_status": None,
                               "corroborated": None, "requested": requested})


REQUESTED_A = {"address": "127.0.0.1:48884", "pid": PID_A}


def doc(token="docA", title="Project1", path="", active=True):
    return {"document": token, "title": title, "path": path, "active": active, "saved": bool(path)}


# --- received replies: the suffix survives every projection ---------------------

@pytest.mark.parametrize("body", [
    {"status": "success", "message": "done"},
    {"status": "success", "result": 42},
    {"status": "success", "data": {"a": 1}},
    {"status": "success", "output": "printed"},
    {"count": 3},
])
def test_received_success_keeps_its_projection_and_appends_the_process(body):
    plain = format_response(dict(body))
    out = format_response(received(dict(body)))
    assert out.startswith(plain + "\n")
    assert out.splitlines()[-1] == PROCESS_LINE_A


def test_message_cannot_hide_the_document_the_route_reports():
    body = {"status": "success", "message": "Moved 2 elements", "document": doc(path="C:/m/a.rvt")}
    out = format_response(received(body))
    assert out.startswith("Moved 2 elements\n")
    assert "Project1" in out and "docA" in out and "C:/m/a.rvt" in out
    assert PROCESS_LINE_A in out


def test_the_reported_document_is_never_invented_from_the_request():
    out = format_response(received({"message": "done"}))
    assert PROCESS_LINE_A in out
    assert "document" not in out.lower().replace("document scope", "")


def test_two_unsaved_project1_in_two_processes_render_differently():
    body = {"message": "done", "document": doc(token="docA")}
    first = format_response(received(dict(body), process=IDENT_A))
    second = format_response(received(dict(body), process=IDENT_B))
    assert first != second
    assert PROCESS_LINE_A in first and PROCESS_LINE_B not in first
    assert PROCESS_LINE_B in second and PROCESS_LINE_A not in second
    assert "Project1" in first and "Project1" in second


def test_documents_changed_and_observed_active_document_are_rendered():
    body = {"status": "success", "message": "edited", "documents_changed": [
        dict(doc(token="docP", title="Plan"), role="project", changed=True),
        {"title": "Door", "path": "C:/f/door.rfa", "is_family_document": True,
         "role": "family", "changed": True, "saved": False}],
        "observed_active_document": doc(token="docP", title="Plan")}
    out = format_response(received(body))
    assert "Plan" in out and "Door" in out
    assert "project" in out and "family" in out
    assert "changed: yes" in out and "saved: no" in out
    assert "Active document re-read by Revit" in out


def test_error_dict_projection_is_unchanged_and_attributed():
    body = {"error": "Element 7 not found", "status": "error", "document": doc()}
    plain = format_response(dict(body))
    out = format_response(received(dict(body), http_status=404))
    assert out.startswith(plain + "\n")
    assert "=== ERROR DETAILS ===" in out
    assert out.splitlines()[-1] == PROCESS_LINE_A


def test_a_falsy_error_dict_is_still_success_when_tagged():
    out = format_response(received({"error": None, "count": 3}))
    assert "ERROR DETAILS" not in out
    assert PROCESS_LINE_A in out


def test_rolled_back_409_text_is_unchanged_and_attributed():
    text = ('Error: 409 - {"status": "rolled_back", "transaction_status": "RolledBack", '
            '"process_identity": ' + json.dumps(IDENT_A) + ', "document": ' + json.dumps(doc()) + '}')
    out = format_response(received(text, http_status=409))
    assert out.startswith(text + "\n")
    assert "rolled_back" in out
    assert "ERROR DETAILS" not in out          # still the verbatim string, not a dict rendering
    assert PROCESS_LINE_A in out
    assert "Project1" in out.split(text, 1)[1]    # the document is also named in the suffix


def test_a_received_error_text_without_a_json_body_still_names_the_process():
    out = format_response(received("Error: 500 - <html>boom</html>", http_status=500))
    assert out.startswith("Error: 500 - <html>boom</html>\n")
    assert out.splitlines()[-1] == PROCESS_LINE_A


def test_412_refusal_text_names_the_reported_document_and_process():
    body = {"error": "not active", "status": "precondition_failed", "document": doc(token="docB")}
    text = "Error: 412 - " + json.dumps(body)
    out = format_response(received(text, http_status=412))
    assert out.startswith(text + "\n")
    assert "docB" in out.split(text, 1)[1]
    assert PROCESS_LINE_A in out


# --- D-15: arbitrary code reports a process and a scope, never a changed document

def test_execute_code_reply_shows_process_and_scope_and_no_document():
    body = {"status": "success", "output": "42", "document_scope": NOTICE,
            "process_identity": IDENT_A}
    out = format_response(received(body, corroborated=True))
    assert out.startswith("42\n")
    assert PROCESS_LINE_A in out
    assert "Document scope: " + NOTICE in out
    lowered = out.lower()
    assert "revit reported this document" not in lowered
    assert "documents this call worked on" not in lowered
    assert "changed: yes" not in lowered


def test_execute_code_scope_wins_even_if_a_document_key_appears():
    body = {"output": "x", "document_scope": NOTICE, "document": doc(),
            "documents_changed": [dict(doc(), role="project", changed=True)]}
    out = format_response(received(body))
    assert "Document scope: " + NOTICE in out
    assert "Revit reported this document" not in out
    assert "Documents this call worked on" not in out
    assert "Project1" not in out


def test_execute_code_error_text_keeps_the_scope_notice_visible():
    body = {"error": "NameError", "document_scope": NOTICE}
    out = format_response(received("Error: 500 - " + json.dumps(body), http_status=500))
    assert out.count(NOTICE) >= 1
    assert PROCESS_LINE_A in out


def test_the_scope_notice_is_not_repeated_when_the_projection_already_shows_it():
    body = {"error": "NameError", "status": "error", "document_scope": NOTICE}
    out = format_response(received(body, http_status=500))
    assert out.count(NOTICE) == 1


# --- results that were not received name no process and no document -------------

def test_not_sent_names_no_process_and_no_document():
    text = "Error: Listener PID mismatch (owners [9]); request not sent. Rediscover targets."
    out = format_response(uncertain(text, "not-sent", REQUESTED_A))
    assert out.startswith(text + "\n")
    assert "Verified Revit process" not in out
    assert "Revit reported this document" not in out
    assert "Attribution: none" in out
    assert "not sent" in out.lower()
    assert "127.0.0.1:48884" in out


def test_not_sent_without_an_established_target_says_so():
    out = format_response(uncertain("Error: No usable Revit process found; request not sent.",
                                    "not-sent", None))
    assert "Attribution: none" in out
    assert "no target was established" in out
    assert "127.0.0.1" not in out


def test_outcome_unknown_is_never_labelled_safe_and_credits_nobody():
    text = ("Error: ReadTimeout - the request was sent to Revit but no complete response arrived "
            "within 30.0s; outcome UNKNOWN - the change may have been applied in Revit. Verify the "
            "model state before retrying.")
    out = format_response(uncertain(text, "unknown", REQUESTED_A))
    assert out.startswith(text + "\n")
    suffix = out[len(text):]
    assert "Attribution: unconfirmed" in suffix
    assert "UNKNOWN" in suffix
    assert "Verified Revit process" not in out
    assert "Revit reported this document" not in out
    for safe in ("safely", "nothing was changed", "not sent", "did not change"):
        assert safe not in suffix.lower()
    assert "127.0.0.1:48884" in suffix


def test_a_read_without_a_reply_credits_nobody():
    out = format_response(uncertain("Error: ReadTimeout", "no-reply", REQUESTED_A))
    assert out.startswith("Error: ReadTimeout\n")
    assert "Attribution: none" in out and "No reply" in out
    assert "Verified Revit process" not in out


def test_an_unverified_reply_is_not_credited_to_the_requested_process():
    out = format_response(uncertain("Error: 500 - boom", "unverified-reply", REQUESTED_A))
    assert "Attribution: unconfirmed" in out
    assert "Verified Revit process" not in out


# --- nothing is trusted from a body alone ---------------------------------------

def test_untagged_dicts_and_strings_render_exactly_as_before():
    body = {"message": "hi", "process_identity": IDENT_A, "document": doc(),
            "_verified_process": dict(IDENT_A), "document_scope": NOTICE}
    assert format_response(body) == "hi"
    assert format_response("Error: boom") == "Error: boom"
    assert format_response(None) == "None"


def test_a_forged_provenance_key_inside_a_body_is_not_metadata():
    body = {"message": "hi", "revit_provenance": {"kind": "received", "process": dict(IDENT_A)}}
    assert format_response(body) == "hi"


def test_the_attribute_name_is_shared_between_bridge_and_renderer():
    import tools.utils as utils

    assert utils.PROVENANCE_ATTR == bridge.PROVENANCE_ATTR


def test_metadata_does_not_leak_into_the_payload_or_equality():
    body = {"status": "success", "message": "m"}
    tagged = received(dict(body))
    assert tagged == body
    assert json.loads(json.dumps(tagged)) == body
    assert isinstance(tagged, dict)
    text = received("Error: 409 - x", http_status=409)
    assert text == "Error: 409 - x" and isinstance(text, str)


# --- the bridge attaches the metadata -------------------------------------------

class Machine(object):
    """Fake listener table and fake Routes servers for two Revit processes."""

    def __init__(self):
        self.listeners = {PORT_A: [PID_A], PORT_B: [PID_B]}
        self.who = {PORT_A: IDENT_A, PORT_B: IDENT_B}
        self.replies = {}      # (port, route) -> httpx.Response | callable(request) -> Response
        self.faults = {}       # (port, route) -> exception factory
        self.seen = []         # (port, method, route)
        self.bodies = []

    def snapshot(self, ports, **_kwargs):
        return dict((p, list(self.listeners.get(p, []))) for p in ports)

    async def respond(self, request):
        port = request.url.port
        route = request.url.path[len(PREFIX):]
        self.seen.append((port, request.method, route))
        self.bodies.append(request.content)
        if route == "/status/":
            return httpx.Response(200, json={"status": "active", "health": "healthy",
                                             "process_identity": dict(self.who[port])})
        fault = self.faults.get((port, route))
        if fault is not None:
            raise fault(request)
        reply = self.replies.get((port, route))
        if reply is None:
            return httpx.Response(200, json={"message": "ok"})
        if callable(reply):
            reply = reply(request)
            if asyncio.iscoroutine(reply):
                reply = await reply
        return reply

    def client(self, target):
        return httpx.AsyncClient(
            base_url="http://127.0.0.1:{}{}/".format(target["port"], PREFIX),
            transport=httpx.MockTransport(self.respond), trust_env=False)

    def routes(self):
        return [s for s in self.seen if s[2] != "/status/"]


@pytest.fixture
def machine(monkeypatch):
    fake = Machine()
    monkeypatch.setattr(bridge, "listener_snapshot", fake.snapshot)
    monkeypatch.setattr(bridge, "_selected_client", fake.client)
    return fake


def provenance(value):
    return getattr(value, bridge.PROVENANCE_ATTR, None)


def run(coro):
    return asyncio.run(coro)


def test_a_received_200_is_tagged_with_the_handshake_identity(machine):
    machine.replies[(PORT_A, "/edit/")] = httpx.Response(200, json={"message": "edited"})
    result = run(bridge.revit_post("/edit/", {"x": 1}, target=SEL_A))
    assert result == {"message": "edited"}
    meta = provenance(result)
    assert meta["kind"] == "received" and meta["http_status"] == 200
    assert meta["process"] == IDENT_A
    assert meta["requested"] == {"address": "127.0.0.1:48884", "pid": PID_A}
    assert meta["corroborated"] is None           # the reply carries no process stamp
    assert format_response(result).splitlines()[-1] == PROCESS_LINE_A


def test_a_matching_reply_stamp_corroborates_the_verified_process(machine):
    machine.replies[(PORT_A, "/edit/")] = httpx.Response(
        200, json={"message": "edited", "process_identity": dict(IDENT_A), "document": doc()})
    result = run(bridge.revit_post("/edit/", {}, target=SEL_A))
    assert provenance(result)["corroborated"] is True
    text = format_response(result)
    assert text.startswith("edited\n") and PROCESS_LINE_A in text and "Project1" in text


@pytest.mark.parametrize("changes", [
    {"pid": PID_B}, {"actual_port": PORT_B},
    {"session_token": TOKEN_B},
])
def test_a_reply_stamp_of_another_process_is_never_attributed_to_the_selected_one(machine, changes):
    machine.replies[(PORT_A, "/edit/")] = httpx.Response(
        200, json={"message": "body-of-the-other-process", "process_identity": dict(IDENT_A, **changes)})
    result = run(bridge.revit_post("/edit/", {}, target=SEL_A))
    assert isinstance(result, str) and result.startswith("Error: ")
    assert "different" in result.lower() and "UNKNOWN" in result
    assert "body-of-the-other-process" not in result
    meta = provenance(result)
    assert meta["kind"] == "unknown" and meta["process"] is None
    text = format_response(result)
    assert "Verified Revit process" not in text
    assert "Attribution: unconfirmed" in text


def test_a_conflicting_reply_to_a_read_is_discarded_without_claiming_an_unknown_outcome(machine):
    machine.replies[(PORT_A, "/list/")] = httpx.Response(
        200, json={"rows": [1], "process_identity": dict(IDENT_A, pid=PID_B)})
    result = run(bridge.revit_get("/list/", target=SEL_A))
    assert result.startswith("Error: ") and "different" in result.lower()
    assert "UNKNOWN" not in result
    assert provenance(result)["kind"] == "no-reply"


def test_a_malformed_reply_stamp_is_uncorroborated_not_a_conflict(machine):
    machine.replies[(PORT_A, "/edit/")] = httpx.Response(
        200, json={"message": "edited", "process_identity": {"pid": "x"}})
    result = run(bridge.revit_post("/edit/", {}, target=SEL_A))
    assert result == {"message": "edited", "process_identity": {"pid": "x"}}
    assert provenance(result)["corroborated"] is None


def test_a_received_4xx_names_the_answering_process(machine):
    body = {"error": "document is not active", "status": "precondition_failed",
            "process_identity": dict(IDENT_A), "document": doc(token="docB")}
    machine.replies[(PORT_A, "/edit/")] = httpx.Response(412, json=body)
    result = run(bridge.revit_post("/edit/", {}, target=SEL_A))
    assert isinstance(result, str) and result.startswith("Error: 412 - ")
    meta = provenance(result)
    assert meta["kind"] == "received" and meta["http_status"] == 412
    text = format_response(result)
    assert text.startswith(result + "\n") and PROCESS_LINE_A in text and "docB" in text


def test_a_route_cannot_forge_the_bridge_metadata_keys(machine):
    machine.replies[(PORT_A, "/edit/")] = httpx.Response(200, json={
        "message": "m", "_verified_process": {"pid": 1}, "revit_provenance": {"kind": "received"}})
    result = run(bridge.revit_post("/edit/", {}, target=SEL_A))
    assert "_verified_process" not in result
    assert provenance(result)["process"] == IDENT_A


def test_refusal_before_send_is_not_sent_and_names_the_requested_target(machine):
    machine.listeners[PORT_A] = [PID_A, 999]            # duplicated listener
    result = run(bridge.revit_post("/edit/", {}, target=SEL_A))
    assert result.startswith("Error: ") and "request not sent" in result
    meta = provenance(result)
    assert meta["kind"] == "not-sent" and meta["process"] is None
    assert meta["requested"] == {"address": "127.0.0.1:48884", "pid": PID_A}
    assert machine.routes() == []
    assert "Verified Revit process" not in format_response(result)


def test_inventory_failure_is_not_sent(machine, monkeypatch):
    monkeypatch.setattr(bridge, "listener_snapshot", lambda ports, **kw: None)
    result = run(bridge.revit_post("/edit/", {}, target=SEL_A))
    meta = provenance(result)
    assert meta["kind"] == "not-sent" and meta["process"] is None
    assert machine.seen == []


def test_invalid_selector_and_ambiguous_default_name_no_target(machine):
    bad = run(bridge.revit_post("/edit/", {}, target="revit1:not-a-selector"))
    assert provenance(bad)["kind"] == "not-sent" and provenance(bad)["requested"] is None
    ambiguous = run(bridge.revit_post("/edit/", {}))      # two usable processes, no selector
    assert ambiguous.startswith("Error: ") and "Multiple usable" in ambiguous
    assert provenance(ambiguous)["kind"] == "not-sent" and provenance(ambiguous)["requested"] is None
    assert machine.routes() == []


def test_queue_busy_is_not_sent_and_names_the_requested_target(machine):
    gate = {}

    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow(request):
            started.set()
            await release.wait()
            return httpx.Response(200, json={"message": "first"})

        machine.replies[(PORT_A, "/slow/")] = slow
        first = asyncio.ensure_future(bridge.revit_post("/slow/", {}, target=SEL_A))
        await asyncio.wait_for(started.wait(), 1.0)
        second = await bridge.revit_post("/other/", {}, target=SEL_A, timeout=0.1)
        release.set()
        gate["first"] = await first
        return second

    result = run(scenario())
    assert "NOT sent to Revit" in result
    meta = provenance(result)
    assert meta["kind"] == "not-sent" and meta["requested"]["pid"] == PID_A
    assert provenance(gate["first"])["kind"] == "received"


def test_post_failure_after_send_is_outcome_unknown_and_credits_nobody(machine):
    machine.faults[(PORT_A, "/edit/")] = lambda req: httpx.ReadTimeout("", request=req)
    result = run(bridge.revit_post("/edit/", {}, target=SEL_A))
    assert "outcome UNKNOWN" in result
    meta = provenance(result)
    assert meta["kind"] == "unknown" and meta["process"] is None
    text = format_response(result)
    assert "Attribution: unconfirmed" in text and "Verified Revit process" not in text


def test_connect_failure_is_not_sent(machine):
    machine.faults[(PORT_A, "/edit/")] = lambda req: httpx.ConnectError("no", request=req)
    result = run(bridge.revit_post("/edit/", {}, target=SEL_A))
    assert provenance(result)["kind"] == "not-sent"
    assert "UNKNOWN" not in result


def test_a_read_that_gets_no_reply_is_tagged_no_reply(machine):
    machine.faults[(PORT_A, "/list/")] = lambda req: httpx.ReadTimeout("", request=req)
    result = run(bridge.revit_get("/list/", target=SEL_A))
    assert result == "Error: ReadTimeout"
    assert provenance(result)["kind"] == "no-reply"


def test_a_post_whose_200_reply_is_not_json_is_outcome_unknown(machine):
    machine.replies[(PORT_A, "/edit/")] = httpx.Response(200, content=b"<html>proxy</html>")
    result = run(bridge.revit_post("/edit/", {}, target=SEL_A))
    assert result.startswith("Error: ") and "UNKNOWN" in result
    assert provenance(result)["kind"] == "unknown" and provenance(result)["process"] is None


def test_a_read_whose_200_reply_is_not_json_credits_nobody(machine):
    machine.replies[(PORT_A, "/list/")] = httpx.Response(200, content=b"<html>proxy</html>")
    result = run(bridge.revit_get("/list/", target=SEL_A))
    assert result.startswith("Error: ") and "UNKNOWN" not in result
    assert provenance(result)["kind"] == "no-reply"


def test_two_processes_answer_with_their_own_attribution(machine):
    for port in (PORT_A, PORT_B):
        machine.replies[(port, "/edit/")] = httpx.Response(
            200, json={"message": "done", "document": doc(token="docX")})
    a = format_response(run(bridge.revit_post("/edit/", {}, target=SEL_A)))
    b = format_response(run(bridge.revit_post("/edit/", {}, target=SEL_B)))
    assert PROCESS_LINE_A in a and PROCESS_LINE_B not in a
    assert PROCESS_LINE_B in b and PROCESS_LINE_A not in b
    assert a != b


def test_status_no_selector_keeps_the_legacy_shapes_and_is_tagged(machine):
    machine.listeners[PORT_B] = []                       # exactly one usable process
    payload = run(bridge.revit_get("/status/"))
    assert payload == {"status": "active", "health": "healthy", "process_identity": dict(IDENT_A)}
    assert provenance(payload)["process"] == IDENT_A
    assert provenance(payload)["kind"] == "received"


def test_status_selected_503_keeps_identity_and_is_tagged(machine):
    async def respond(request):
        machine.seen.append((request.url.port, request.method, "/status/"))
        return httpx.Response(503, json={"status": "unhealthy", "error": "No active Revit document",
                                         "process_identity": dict(IDENT_A)})

    machine.respond = respond
    result = run(bridge.revit_get("/status/", target=SEL_A))
    assert result["_verified_process"]["pid"] == PID_A
    assert provenance(result)["kind"] == "received" and provenance(result)["http_status"] == 503
    text = format_response(result)
    assert "No active Revit document" in text and PROCESS_LINE_A in text
    assert "_verified_process" not in text.lower().replace("verified revit process", "")


def test_image_success_cannot_carry_text_but_an_image_error_is_attributed(machine):
    png = base64.b64encode(b"\x89PNG").decode("ascii")
    machine.replies[(PORT_A, "/get_view/Level 1")] = httpx.Response(200, json={"image_data": png})
    image = run(bridge.revit_image("/get_view/Level 1", target=SEL_A))
    assert not isinstance(image, str) and provenance(image) is None
    machine.replies[(PORT_A, "/get_view/Nope")] = httpx.Response(404, json={"error": "no such view"})
    result = run(bridge.revit_image("/get_view/Nope", target=SEL_A))
    assert result.startswith("Error: 404 - ") and provenance(result)["kind"] == "received"


# --- through real tool registrars -----------------------------------------------

class FakeMCP(object):
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


def tool(register, name):
    mcp = FakeMCP()
    register(mcp, bridge.revit_get, bridge.revit_post, bridge.revit_image)
    return mcp.tools[name]


def test_execute_revit_code_shows_process_and_scope_and_no_changed_document(machine):
    from tools.code_execution_tools import register_code_execution_tools

    machine.replies[(PORT_A, "/execute_code/")] = httpx.Response(200, json={
        "status": "success", "output": "42", "document_scope": NOTICE,
        "process_identity": dict(IDENT_A)})
    out = run(tool(register_code_execution_tools, "execute_revit_code")(
        "print(42)", "demo", SEL_A))
    assert out.startswith("42\n")
    assert PROCESS_LINE_A in out and "Document scope: " + NOTICE in out
    assert "Revit reported this document" not in out
    assert "Documents this call worked on" not in out
    assert machine.routes() == [(PORT_A, "POST", "/execute_code/")]


def test_a_guarded_mutation_tool_renders_message_document_and_process(machine):
    from tools.transform_tools import register_transform_tools

    machine.replies[(PORT_A, "/transform_elements/")] = httpx.Response(200, json={
        "status": "success", "message": "Moved 1 element", "process_identity": dict(IDENT_A),
        "document": doc(token="docA", title="Project1")})
    fn = tool(register_transform_tools, "transform_elements")
    out = run(fn([1], "move", vector={"x": 1, "y": 0, "z": 0}, target=SEL_A))
    assert out.startswith("Moved 1 element\n")
    assert PROCESS_LINE_A in out and "Project1" in out and "docA" in out


def test_model_info_is_target_aware_and_names_the_process_and_not_a_document(machine):
    from tools.status_tools import register_status_tools

    machine.replies[(PORT_B, "/model_info/")] = httpx.Response(200, json={
        "title": "Project1", "total_elements": 5})
    fn = tool(register_status_tools, "get_revit_model_info")
    assert "target" in fn.__code__.co_varnames[:fn.__code__.co_argcount]
    out = run(fn(target=SEL_B))
    assert "Project1" in out and "Total Elements: 5" in out
    assert PROCESS_LINE_B in out and PROCESS_LINE_A not in out
    assert "Revit reported this document" not in out      # the route stamps no document here
    assert machine.routes() == [(PORT_B, "GET", "/model_info/")]


def test_model_info_without_selector_and_two_processes_is_refused_not_sent(machine):
    from tools.status_tools import register_status_tools

    out = run(tool(register_status_tools, "get_revit_model_info")())
    assert out.startswith("Error: ") and "Multiple usable" in out
    assert "Attribution: none" in out and "Verified Revit process" not in out
    assert machine.routes() == []


def test_status_names_the_answering_process_not_the_configured_slot(machine, monkeypatch):
    from tools.status_tools import register_status_tools

    machine.listeners[PORT_A] = []                      # only the process on 48885 is usable
    monkeypatch.setattr(bridge.revit_get, "revit_target", "localhost:48884", raising=False)
    out = run(tool(register_status_tools, "get_revit_status")())
    assert PROCESS_LINE_B in out
    last = out.splitlines()[-1]
    assert last.startswith("MCP target: localhost:48884")
    assert "configured launch slot" in last and "48885" in last


def test_status_keeps_the_plain_target_line_when_the_configured_port_answered(machine, monkeypatch):
    from tools.status_tools import register_status_tools

    machine.listeners[PORT_B] = []
    monkeypatch.setattr(bridge.revit_get, "revit_target", "localhost:48884", raising=False)
    out = run(tool(register_status_tools, "get_revit_status")())
    assert PROCESS_LINE_A in out
    assert out.splitlines()[-1] == "MCP target: localhost:48884"


def test_status_refusal_does_not_present_the_configured_slot_as_a_route(machine, monkeypatch):
    from tools.status_tools import register_status_tools

    monkeypatch.setattr(bridge.revit_get, "revit_target", "localhost:48884", raising=False)
    out = run(tool(register_status_tools, "get_revit_status")())      # two usable: refused
    assert out.startswith("Error: ") and "Multiple usable" in out
    assert "Verified Revit process" not in out
    assert out.splitlines()[-1].startswith("MCP target: localhost:48884")
    assert "does not route" in out.splitlines()[-1]


def test_get_revit_view_error_goes_through_the_renderer(machine):
    from tools.view_tools import register_view_tools

    machine.replies[(PORT_A, "/get_view/Nope")] = httpx.Response(404, json={"error": "no such view"})
    out = run(tool(register_view_tools, "get_revit_view")("Nope", SEL_A))
    assert out.startswith("Error: 404 - ")
    assert PROCESS_LINE_A in out
