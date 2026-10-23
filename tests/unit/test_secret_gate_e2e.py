# -*- coding: utf-8 -*-
"""Tracer: the shared-secret gate end to end, across both halves.

The real, unchanged bridge._send posts a body built by bridge.with_envelope
through httpx.MockTransport into a simulated Revit handler made of the new
revit_mcp.trust functions (what a Phase 5 per-handler guard will do), and the
refusal travels back through tools.utils.format_response. The Revit side reads
the body through parse_request_data under the IronPython 3 json stand-in, so it
receives bytes exactly as pyRevit delivers them. Needs no Revit.
"""

import json

import httpx
import pytest

import bridge
from revit_mcp import trust
from tools.utils import format_response

SECRET = "e2e-secret-0123456789-abcdefXYZ"
WRONG = "e2e-wrongg-9876543210-zyxwvuABC"


@pytest.fixture(scope="module")
def anyio_backend():
    # trio is not installed and must not be added: pin asyncio.
    return "asyncio"


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


def _revit_handler(expected, seen):
    """What a Phase 5 guard does: split, check, refuse with 401 or answer 200."""

    def handler(request):
        seen.append(request)
        envelope, payload = trust.split_envelope(request.content)
        verdict = trust.check_secret(trust.envelope_secret(envelope), expected)
        if verdict != trust.AUTH_OK:
            body, status = trust.auth_failure(verdict)
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={"status": "success", "received": payload})

    return handler


async def _post(data, expected, seen):
    transport = httpx.MockTransport(_revit_handler(expected, seen))
    async with httpx.AsyncClient(base_url="http://revit.test/genpro_revit_mcp/",
                                 transport=transport) as client:
        return await bridge._send(client, "POST", "/delete_elements/", data, 5.0, None)


DATA = {"element_ids": [1, 2], "document": "A.rvt"}


@pytest.fixture(autouse=True)
def _ironpython3_json(monkeypatch):
    monkeypatch.setattr("revit_mcp.textutils.json", _IronPython3Json())


@pytest.mark.anyio
async def test_e2e_correct_secret_reaches_handler_without_the_envelope():
    seen = []
    result = await _post(bridge.with_envelope(DATA, SECRET), SECRET, seen)
    assert isinstance(result, dict)
    assert result["received"] == {"element_ids": [1, 2], "document": "A.rvt"}
    assert "_mcp" not in result["received"]


@pytest.mark.anyio
async def test_e2e_wrong_secret_is_a_visible_401():
    seen = []
    result = await _post(bridge.with_envelope(DATA, WRONG), SECRET, seen)
    assert isinstance(result, str)
    assert result.startswith("Error: 401 - ")
    assert '"auth"' in result
    assert "mismatch" in result
    assert format_response(result) == result
    assert SECRET not in result
    assert WRONG not in result


@pytest.mark.anyio
async def test_e2e_missing_secret_is_a_visible_401():
    seen = []
    envelope = bridge.with_envelope(DATA, None)
    assert "_mcp" not in envelope
    result = await _post(envelope, SECRET, seen)
    assert isinstance(result, str)
    assert result.startswith("Error: 401 - ")
    assert "missing" in result
    assert format_response(result) == result


@pytest.mark.anyio
async def test_e2e_unconfigured_server_is_a_visible_401():
    seen = []
    result = await _post(bridge.with_envelope(DATA, SECRET), None, seen)
    assert isinstance(result, str)
    assert result.startswith("Error: 401 - ")
    assert "server_not_configured" in result
    assert SECRET not in result


@pytest.mark.anyio
async def test_e2e_secret_travels_as_text_plain_bytes_under_the_reserved_key():
    seen = []
    await _post(bridge.with_envelope(DATA, SECRET), SECRET, seen)
    assert len(seen) == 1
    request = seen[0]
    assert request.headers["content-type"] == "text/plain; charset=utf-8"
    assert isinstance(request.content, bytes)
    assert json.loads(request.content)["_mcp"] == {"secret": SECRET}
