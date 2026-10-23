# -*- coding: utf-8 -*-
"""Client half of the shared-secret contract (bridge.load_secret), and proof it is inert.

bridge.load_secret reads the secret file the same way revit_mcp/trust.py does; the
payload ships no revit_mcp/ package, so the rule is duplicated in bridge.py and the
parity tests here are what keep the two halves identical. Nothing in production code
calls load_secret or with_envelope until Phase 5, and bridge._send still posts exactly
json.dumps(data). Needs no Revit.
"""

import ast
import builtins
import glob
import json
import logging
import os

import httpx
import pytest

import bridge
from revit_mcp import trust

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SECRET = "client-secret-0123456789-abcXYZ"
OTHER = "client-other--9876543210-zyxABC"


@pytest.fixture(scope="module")
def anyio_backend():
    # trio is not installed and must not be added: pin asyncio.
    return "asyncio"


def _write(directory, raw, name="_bridge_secret"):
    path = os.path.join(str(directory), name)
    with open(path, "wb") as handle:
        handle.write(raw)
    return path


# Shared fixtures for the parity tables: (id, bytes).
FIXTURES = [
    ("plain", SECRET.encode("utf-8")),
    ("trailing-crlf", SECRET.encode("utf-8") + b"\r\n"),
    ("trailing-lf", SECRET.encode("utf-8") + b"\n"),
    ("bom", b"\xef\xbb\xbf" + SECRET.encode("utf-8")),
    ("bom-crlf", b"\xef\xbb\xbf" + SECRET.encode("utf-8") + b"\r\n"),
    ("surrounding-space", b"  \t" + SECRET.encode("utf-8") + b" \t\r\n"),
    ("empty", b""),
    ("whitespace-only", b" \t\r\n  "),
    ("fifteen", b"a" * 15),
    ("sixteen", b"a" * 16),
    ("fifteen-crlf", b"a" * 15 + b"\r\n"),
    ("sixteen-crlf", b"a" * 16 + b"\r\n"),
    ("utf16-le", "0123456789abcdefXYZ".encode("utf-16")),
    ("utf16-le-nobom", "0123456789abcdefXYZ".encode("utf-16-le")),
    ("undecodable", b"\xff\xfe\xfa" + b"a" * 20),
    ("nul-inside", b"a" * 10 + b"\x00" + b"b" * 10),
    ("nul-trailing", b"a" * 20 + b"\x00"),
    ("cyrillic", "секрет-0123456789-ключ".encode("utf-8")),
]
FIXTURE_IDS = [name for name, _ in FIXTURES]


# --- constants ----------------------------------------------------------------

def test_constants_equal_the_trust_constants():
    assert (bridge.ENVELOPE_KEY, bridge.SECRET_KEY, bridge.SECRET_FILE_NAME,
            bridge.MIN_SECRET_LENGTH) == (trust.ENVELOPE_KEY, trust.SECRET_KEY,
                                          trust.SECRET_FILE_NAME, trust.MIN_SECRET_LENGTH)


# --- parity with trust.py -----------------------------------------------------

@pytest.mark.parametrize("raw", [raw for _, raw in FIXTURES], ids=FIXTURE_IDS)
def test_parity_secret_from_bytes_matches_trust(raw):
    assert bridge._secret_from_bytes(raw) == trust.secret_from_bytes(raw)


@pytest.mark.parametrize("value", [None, "text", 7, ["a"], bytearray(b"a" * 20)])
def test_parity_non_bytes_input(value):
    assert bridge._secret_from_bytes(value) == trust.secret_from_bytes(value)


@pytest.mark.parametrize("raw", [raw for _, raw in FIXTURES], ids=FIXTURE_IDS)
def test_parity_load_secret_matches_read_secret_file(tmp_path, raw):
    path = _write(tmp_path, raw)
    assert bridge.load_secret([str(tmp_path)]) == trust.read_secret_file(path)


def test_parity_known_outcomes():
    assert bridge._secret_from_bytes(SECRET.encode("utf-8") + b"\r\n") == SECRET
    assert bridge._secret_from_bytes(b"\xef\xbb\xbf" + SECRET.encode("utf-8")) == SECRET
    assert bridge._secret_from_bytes(b"a" * 15) is None
    assert bridge._secret_from_bytes(b"a" * 16) == "a" * 16
    assert bridge._secret_from_bytes("секрет-0123456789-ключ".encode("utf-8")) == \
        "секрет-0123456789-ключ"


# --- search order -------------------------------------------------------------

def test_search_second_directory_when_first_has_no_file(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _write(b, SECRET.encode("utf-8"))
    assert bridge.load_secret([str(a), str(b)]) == SECRET


def test_search_first_valid_file_wins(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _write(a, SECRET.encode("utf-8"))
    _write(b, OTHER.encode("utf-8"))
    assert bridge.load_secret([str(a), str(b)]) == SECRET


def test_search_first_existing_file_decides_even_when_invalid(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _write(a, b"")
    _write(b, SECRET.encode("utf-8"))
    assert bridge.load_secret([str(a), str(b)]) is None


def test_search_no_file_anywhere_is_none(tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    assert bridge.load_secret([str(a), str(tmp_path / "missing")]) is None
    assert bridge.load_secret([]) is None


def test_default_search_dirs_are_beside_bridge_then_revit_mcp(tmp_path, monkeypatch):
    fake = tmp_path / "bridge.py"
    fake.write_text("# fake", encoding="utf-8")
    (tmp_path / "revit_mcp").mkdir()
    _write(tmp_path / "revit_mcp", OTHER.encode("utf-8"))
    monkeypatch.setattr(bridge, "__file__", str(fake))
    assert bridge.load_secret() == OTHER  # dev layout (D-09)
    _write(tmp_path, SECRET.encode("utf-8"))
    assert bridge.load_secret() == SECRET  # payload layout (D-08) wins


def test_default_search_with_nothing_present_is_none(tmp_path, monkeypatch):
    fake = tmp_path / "bridge.py"
    fake.write_text("# fake", encoding="utf-8")
    monkeypatch.setattr(bridge, "__file__", str(fake))
    assert bridge.load_secret() is None


def test_search_dirs_none_means_the_defaults(tmp_path, monkeypatch):
    fake = tmp_path / "bridge.py"
    fake.write_text("# fake", encoding="utf-8")
    _write(tmp_path, SECRET.encode("utf-8"))
    monkeypatch.setattr(bridge, "__file__", str(fake))
    assert bridge.load_secret(None) == SECRET


# --- never raises, never logs, never leaks ------------------------------------

def test_secret_never_raises_for_a_directory(tmp_path, caplog):
    (tmp_path / "_bridge_secret").mkdir()
    with caplog.at_level(logging.DEBUG):
        assert bridge.load_secret([str(tmp_path)]) is None
    assert caplog.records == []


def test_secret_never_raises_for_an_unreadable_file(tmp_path, monkeypatch, caplog):
    path = _write(tmp_path, SECRET.encode("utf-8"))
    real_open = builtins.open

    def deny(file, *args, **kwargs):
        if os.path.abspath(str(file)) == os.path.abspath(path):
            raise PermissionError("denied")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", deny)
    with caplog.at_level(logging.DEBUG):
        assert bridge.load_secret([str(tmp_path)]) is None
    assert caplog.records == []


def test_secret_never_logged_on_success(tmp_path, caplog):
    _write(tmp_path, SECRET.encode("utf-8"))
    with caplog.at_level(logging.DEBUG):
        assert bridge.load_secret([str(tmp_path)]) == SECRET
    assert SECRET not in caplog.text
    assert caplog.records == []


def test_secret_never_printed(tmp_path, capsys):
    _write(tmp_path, SECRET.encode("utf-8"))
    bridge.load_secret([str(tmp_path)])
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err


@pytest.mark.parametrize("bad", [None, 7, ["a"], "\x00"])
def test_secret_never_raises_for_hostile_directory_arguments(bad):
    assert bridge.load_secret([bad]) is None


def test_secret_never_in_with_envelope_refusal_text():
    for body in ({"_mcp": {"secret": "x"}, "v": SECRET}, ["a", SECRET], "text " + SECRET):
        with pytest.raises(ValueError) as excinfo:
            bridge.with_envelope(body, "y")
        text = str(excinfo.value)
        assert SECRET not in text
        assert "'x'" not in text and '"x"' not in text and "'y'" not in text


# --- with_envelope ------------------------------------------------------------

def test_with_envelope_returns_a_new_dict_and_never_mutates():
    original = {"a": 1}
    result = bridge.with_envelope(original, SECRET)
    assert result == {"a": 1, "_mcp": {"secret": SECRET}}
    assert result is not original
    assert "_mcp" not in original


def test_with_envelope_none_body():
    assert bridge.with_envelope(None, SECRET) == {"_mcp": {"secret": SECRET}}


def test_with_envelope_none_secret_adds_no_envelope():
    original = {"a": 1}
    result = bridge.with_envelope(original, None)
    assert result == {"a": 1}
    assert result is not original


def test_with_envelope_refuses_a_preseeded_envelope():
    with pytest.raises(ValueError) as excinfo:
        bridge.with_envelope({"_mcp": {"secret": "x"}, "v": SECRET}, "y")
    text = str(excinfo.value)
    assert SECRET not in text
    assert "'x'" not in text and "'y'" not in text


def test_with_envelope_refuses_a_non_dict_body():
    with pytest.raises(ValueError) as excinfo:
        bridge.with_envelope(["a"], SECRET)
    assert SECRET not in str(excinfo.value)


# --- inert: the send path is untouched (D-10) ---------------------------------

@pytest.mark.anyio
async def test_inert_send_posts_exactly_json_dumps():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"status": "success"})

    data = {"element_ids": [1], "document": "Проект.rvt"}
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(base_url="http://revit.test/genpro_revit_mcp/",
                                 transport=transport) as client:
        await bridge._send(client, "POST", "/delete_elements/", data, 5.0, None)
    assert len(seen) == 1
    request = seen[0]
    assert request.content == json.dumps(data).encode("utf-8")
    assert request.headers["content-type"] == "text/plain; charset=utf-8"
    assert "_mcp" not in json.loads(request.content)


def _production_files():
    paths = [os.path.join(REPO_ROOT, "bridge.py"), os.path.join(REPO_ROOT, "main.py")]
    paths += sorted(glob.glob(os.path.join(REPO_ROOT, "tools", "*.py")))
    return paths


def _call_names(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                yield func.id
            elif isinstance(func, ast.Attribute):
                yield func.attr


def test_inert_no_production_call_sites():
    paths = _production_files()
    assert len(paths) >= 3  # bridge.py, main.py and at least one tools module
    offenders = []
    for path in paths:
        with open(path, "rb") as handle:
            tree = ast.parse(handle.read(), filename=path)
        for name in _call_names(tree):
            if name in ("load_secret", "with_envelope"):
                offenders.append((os.path.basename(path), name))
    assert offenders == []


def test_inert_load_secret_is_not_run_at_import():
    # Importing bridge must not read a secret file: the only references to
    # load_secret in bridge.py are its definition.
    with open(os.path.join(REPO_ROOT, "bridge.py"), "rb") as handle:
        tree = ast.parse(handle.read())
    defs = [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "load_secret"]
    assert len(defs) == 1
    mentions = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "load_secret"]
    assert mentions == []
