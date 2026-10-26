# -*- coding: utf-8 -*-
"""Company FOP parsing and matching; fixtures are local, never the corporate share."""

import asyncio
import codecs
import threading
import time
import unicodedata

import pytest

import policy

G = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
H = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
NAME = "ADSK_Й_Марка"
TEXT = "# shared parameters\n*META\tVERSION\tMINVERSION\nMETA\t2\t1\n*GROUP\tID\tNAME\nGROUP\t1\tОбщие\n*PARAM\tGUID\tNAME\tDATATYPE\nPARAM\t{}\t{}\tTEXT\t\t1\t1\n".format(G, NAME)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def clear_cache():
    policy._FOP_CACHE.clear()


@pytest.mark.parametrize("encoding,bom", [
    ("utf-16-le", codecs.BOM_UTF16_LE), ("utf-16-be", codecs.BOM_UTF16_BE),
    ("utf-8", codecs.BOM_UTF8), ("utf-8", b""),
])
def test_expected_encodings_preserve_cyrillic(encoding, bom):
    index = policy.parse_fop_bytes(bom + TEXT.encode(encoding))
    assert dict(index.names_by_guid) == {G: NAME}
    assert dict(index.guids_by_name) == {NAME: frozenset({G})}


@pytest.mark.parametrize("raw", [b"\xff", codecs.BOM_UTF16_LE + b"x", codecs.BOM_UTF8 + b"\xff"])
def test_invalid_encoding_is_not_guessed(raw):
    with pytest.raises(policy.FopError, match="undecodable"):
        policy.parse_fop_bytes(raw)


def test_no_header_is_not_a_shared_parameter_file():
    with pytest.raises(policy.FopError, match="not a shared parameter file"):
        policy.parse_fop_bytes(b"hello")


@pytest.mark.parametrize("record", ["PARAM\tbad\tX", "PARAM\t" + G, "PARAM\t" + G + "\t"])
def test_malformed_record_is_not_ignored(record):
    with pytest.raises(policy.FopError):
        policy.parse_fop_bytes((TEXT + record).encode())


def test_duplicates_preserve_name_guid_set_and_conflicting_guid_is_invalid():
    index = policy.parse_fop_bytes((TEXT + "PARAM\t{}\t{}\tTEXT\n".format(H, NAME)).encode())
    assert index.guids_by_name[NAME] == frozenset({G, H})
    with pytest.raises(policy.FopError):
        policy.parse_fop_bytes((TEXT + "PARAM\t{}\tOther\tTEXT\n".format(G)).encode())


@pytest.mark.parametrize("definition,verdict", [
    ({"name": NAME, "resolved": False}, "unresolved"),
    ({"name": NAME, "resolved": True, "ambiguous": True, "guid": G}, "ambiguous"),
    ({"name": NAME, "resolved": True, "guid": H}, "not_in_fop"),
    ({"name": "Other", "resolved": True, "guid": G}, "name_mismatch"),
    ({"name": NAME.lower(), "resolved": True, "guid": G}, "name_mismatch"),
    ({"name": unicodedata.normalize("NFD", NAME), "resolved": True, "guid": G.upper()}, "match"),
])
def test_guid_and_exact_nfc_name_matching(definition, verdict):
    assert policy.match_shared(policy.parse_fop_bytes(TEXT.encode()), [definition]) == {definition["name"]: verdict}


def test_repeated_definition_cannot_hide_a_mismatch():
    index = policy.parse_fop_bytes(TEXT.encode())
    definitions = [{"name": NAME, "resolved": True, "guid": H},
                   {"name": NAME, "resolved": True, "guid": G}]
    assert policy.match_shared(index, definitions)[NAME] != "match"


@pytest.mark.anyio
async def test_file_states_and_match(tmp_path):
    definition = [{"name": NAME, "resolved": True, "guid": G}]
    assert await policy.fop_for(definition, "") == {"state": "not_configured"}
    path = tmp_path / "ФОП.txt"
    assert (await policy.fop_for(definition, str(path)))["state"] == "unreadable"
    path.write_bytes(b"\xff")
    assert (await policy.fop_for(definition, str(path)))["state"] == "undecodable"
    path.write_bytes(TEXT.encode())
    assert await policy.fop_for(definition, str(path)) == {"state": "ok", "verdicts": {NAME: "match"}}


@pytest.mark.anyio
async def test_cache_avoids_reread_and_invalidates_on_size_change(tmp_path):
    path = tmp_path / "ФОП.txt"
    path.write_bytes(TEXT.encode())
    calls = []
    main_thread = threading.get_ident()

    def reader(name):
        assert threading.get_ident() != main_thread
        calls.append(name)
        return path.read_bytes()

    first = await policy.read_fop(str(path), reader=reader)
    assert await policy.read_fop(str(path), reader=reader) is first
    assert len(calls) == 1
    path.write_bytes((TEXT + "# changed\n").encode())
    await policy.read_fop(str(path), reader=reader)
    assert len(calls) == 2


@pytest.mark.anyio
async def test_slow_reader_times_out_without_waiting_for_thread(tmp_path, monkeypatch):
    path = tmp_path / "slow.txt"
    path.write_bytes(TEXT.encode())
    release = threading.Event()
    monkeypatch.setattr(policy, "FOP_TIMEOUT_S", 0.05)

    def reader(name):
        release.wait(2)
        return path.read_bytes()

    started = time.monotonic()
    try:
        assert (await policy.fop_for([], str(path), reader=reader))["state"] == "unreadable"
        assert time.monotonic() - started < 0.5
    finally:
        release.set()


def test_default_fop_path_is_exact():
    assert policy.load_base().settings["shared_parameters_file"] == (
        r"\\Srv-dfs\BIM\01_Ресурсы плагинов\2_Shared_parameters\ГП_ФОП2025.txt")
