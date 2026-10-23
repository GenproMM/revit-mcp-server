# -*- coding: utf-8 -*-
"""revit_mcp/trust.py split_envelope and envelope_secret over bytes, str and dict bodies.

The Revit half receives the body as bytes (IronPython 3), str (IronPython 2.7) or an
already-parsed dict, and split_envelope must read all three the same way and never
raise. Two cases run with the IronPython 3 json stand-in that refuses bytes. Needs no Revit.
"""

import json

import pytest

from revit_mcp import trust

SECRET = "envelope-secret-0123456789-xyz"


class _IronPython3Json(object):
    """json as IronPython 3 ships it: loads() refuses bytes (see test_textutils)."""

    def loads(self, payload, *args, **kwargs):
        if not isinstance(payload, str):
            raise TypeError(
                "the JSON object must be str, not {!r}".format(
                    payload.__class__.__name__
                )
            )
        return json.loads(payload, *args, **kwargs)


BODY = {"element_ids": [1, 2], "document": "A.rvt", "_mcp": {"secret": SECRET}}
PAYLOAD = {"element_ids": [1, 2], "document": "A.rvt"}


def _shapes(body):
    text = json.dumps(body)
    return [text.encode("utf-8"), text, dict(body)]


def test_all_three_body_shapes_split_identically():
    for shape in _shapes(BODY):
        envelope, payload = trust.split_envelope(shape)
        assert envelope == {"secret": SECRET}
        assert payload == PAYLOAD


def test_the_whole_envelope_dict_is_returned_for_later_phases():
    body = {"x": 1, "_mcp": {"secret": SECRET, "call_id": "c-1", "approval": "t"}}
    envelope, payload = trust.split_envelope(body)
    assert envelope == {"secret": SECRET, "call_id": "c-1", "approval": "t"}
    assert payload == {"x": 1}


def test_payload_keeps_document_and_every_other_key():
    envelope, payload = trust.split_envelope(BODY)
    assert payload["document"] == "A.rvt"
    assert payload["element_ids"] == [1, 2]
    assert "_mcp" not in payload


@pytest.mark.parametrize("raw", [b"", b"   ", None, b"not json", "not json", b"\xff\xfe", b"{", b"nul\x00l"])
def test_empty_null_and_unparseable_bodies_give_an_empty_pair(raw):
    assert trust.split_envelope(raw) == ({}, None)


def test_a_json_list_body_gives_the_list_as_payload():
    envelope, payload = trust.split_envelope(b"[1, 2]")
    assert envelope == {}
    assert payload == [1, 2]


@pytest.mark.parametrize("raw", [b"5", b"null", b'"text"', b"true"])
def test_a_json_scalar_body_is_not_an_envelope(raw):
    envelope, payload = trust.split_envelope(raw)
    assert envelope == {}
    assert payload == json.loads(raw)


@pytest.mark.parametrize("value", [None, "x", 5, [1], True, "secret"])
def test_a_non_dict_reserved_key_gives_an_empty_envelope(value):
    envelope, payload = trust.split_envelope({"a": 1, "_mcp": value})
    assert envelope == {}
    assert payload == {"a": 1}
    assert trust.check_secret(trust.envelope_secret(envelope), SECRET) == "missing"


def test_a_body_without_the_reserved_key_is_missing_never_ok():
    envelope, payload = trust.split_envelope(b'{"a": 1}')
    assert envelope == {}
    assert payload == {"a": 1}
    assert trust.check_secret(trust.envelope_secret(envelope), SECRET) == "missing"


def test_split_never_mutates_its_input():
    body = {"a": 1, "_mcp": {"secret": SECRET}}
    first = trust.split_envelope(body)
    assert body == {"a": 1, "_mcp": {"secret": SECRET}}
    second = trust.split_envelope(body)
    assert first == second


def test_envelope_secret_reads_only_dict_envelopes():
    assert trust.envelope_secret({"secret": SECRET}) == SECRET
    assert trust.envelope_secret({}) is None
    assert trust.envelope_secret(None) is None
    assert trust.envelope_secret("secret") is None
    assert trust.envelope_secret(["secret"]) is None


def test_split_reads_bytes_under_the_ironpython3_json_stand_in(monkeypatch):
    monkeypatch.setattr("revit_mcp.textutils.json", _IronPython3Json())
    envelope, payload = trust.split_envelope(json.dumps(BODY).encode("utf-8"))
    assert envelope == {"secret": SECRET}
    assert payload == PAYLOAD


def test_cyrillic_body_survives_under_the_ironpython3_json_stand_in(monkeypatch):
    monkeypatch.setattr("revit_mcp.textutils.json", _IronPython3Json())
    secret = "Секретный-пароль-й-2026-абв"
    body = {"value": "ИЗ Группирование", "_mcp": {"secret": secret}}
    for raw in (json.dumps(body).encode("utf-8"),
                json.dumps(body, ensure_ascii=False).encode("utf-8")):
        envelope, payload = trust.split_envelope(raw)
        assert payload == {"value": "ИЗ Группирование"}
        assert trust.check_secret(trust.envelope_secret(envelope), secret) == "ok"


def test_the_bytes_and_str_forms_of_one_secret_compare_ok():
    body = json.dumps({"_mcp": {"secret": SECRET}})
    for raw in (body.encode("utf-8"), body):
        envelope, _ = trust.split_envelope(raw)
        assert trust.check_secret(trust.envelope_secret(envelope), SECRET.encode("utf-8")) == "ok"
