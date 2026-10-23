# -*- coding: utf-8 -*-
"""Decision table for the pure integrity evaluation and the 423 body.

Every manifest and observation shape maps to exactly one of three states, an
unreachable or unreadable input is never reported as a mismatch, and the 423 body
is pinned. Needs no Revit.
"""

import copy
import hashlib
import random

import pytest

from revit_mcp import trust


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


A = "revit_mcp/alpha.py"
B = "revit_mcp/beta.py"
S = "startup.py"


def _manifest(**overrides):
    manifest = {
        "schema": 1,
        "generated_at": "2026-10-23T00:00:00Z",
        "commit": "0" * 40,
        "files": {A: _digest("a"), B: _digest("b"), S: _digest("s")},
    }
    manifest.update(overrides)
    return manifest


def _observed(**overrides):
    observed = {
        "hashes": {A: _digest("a"), B: _digest("b"), S: _digest("s")},
        "present_py": [A, B],
        "unreadable": [],
    }
    observed.update(overrides)
    return observed


def _lists(result):
    return result["modified"], result["missing"], result["unexpected"]


# ---------------------------------------------------------------- match / mismatch

def test_match_has_three_empty_lists():
    result = trust.evaluate_integrity(_manifest(), _observed())
    assert result["state"] == trust.INTEGRITY_MATCH
    assert result["reason"] is None
    assert _lists(result) == ([], [], [])
    assert trust.mismatch_files(result) == []


def test_modified_file_lands_in_modified():
    observed = _observed()
    observed["hashes"][A] = _digest("tampered")
    result = trust.evaluate_integrity(_manifest(), observed)
    assert result["state"] == trust.INTEGRITY_MISMATCH
    assert _lists(result) == ([A], [], [])


def test_missing_file_lands_in_missing():
    observed = _observed(present_py=[A])
    del observed["hashes"][B]
    result = trust.evaluate_integrity(_manifest(), observed)
    assert result["state"] == trust.INTEGRITY_MISMATCH
    assert _lists(result) == ([], [B], [])


def test_unexpected_py_lands_in_unexpected():
    result = trust.evaluate_integrity(
        _manifest(), _observed(present_py=[A, B, "revit_mcp/rogue.py"]))
    assert result["state"] == trust.INTEGRITY_MISMATCH
    assert _lists(result) == ([], [], ["revit_mcp/rogue.py"])


def test_underscore_prefixed_py_is_unexpected_too():
    result = trust.evaluate_integrity(
        _manifest(), _observed(present_py=[A, B, "revit_mcp/_scratch.py"]))
    assert result["state"] == trust.INTEGRITY_MISMATCH
    assert result["unexpected"] == ["revit_mcp/_scratch.py"]


def test_combination_gives_the_sorted_union():
    observed = _observed(present_py=[A, "revit_mcp/zzz.py", "revit_mcp/_a.py"])
    observed["hashes"][A] = _digest("tampered")
    del observed["hashes"][B]
    result = trust.evaluate_integrity(_manifest(), observed)
    assert result["state"] == trust.INTEGRITY_MISMATCH
    assert trust.mismatch_files(result) == sorted(
        [A, B, "revit_mcp/_a.py", "revit_mcp/zzz.py"])


def test_non_py_listed_file_is_checked_by_hash_only():
    observed = _observed()
    observed["hashes"][S] = _digest("changed")
    result = trust.evaluate_integrity(_manifest(), observed)
    assert result["modified"] == [S]


# ---------------------------------------------------------------- manifest_missing / unreadable

def test_unverifiable_manifest_none_is_manifest_missing():
    result = trust.evaluate_integrity(None, _observed())
    assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert result["reason"] == trust.REASON_MANIFEST_MISSING
    assert _lists(result) == ([], [], [])


BAD_PATHS = [
    "/abs.py", "C:/x.py", "revit_mcp\\x.py", "../x.py", "revit_mcp/../x.py",
    "revit_mcp//x.py", "./x.py", "",
]


def _bad_manifests():
    cases = {
        "list instead of dict": ["schema", 1],
        "schema 2": _manifest(schema=2),
        "schema text 1": _manifest(schema="1"),
        "schema True": _manifest(schema=True),
        "schema float": _manifest(schema=1.0),
        "files missing": {"schema": 1},
        "files list": _manifest(files=[A]),
        "files empty": _manifest(files={}),
        "digest 63 chars": _manifest(files={A: _digest("a")[:63]}),
        "digest uppercase": _manifest(files={A: _digest("a").upper()}),
        "digest not text": _manifest(files={A: 12345}),
        "digest None": _manifest(files={A: None}),
    }
    for key in BAD_PATHS:
        cases["key {!r}".format(key)] = _manifest(files={key: _digest("a"), B: _digest("b")})
    cases["key not text"] = _manifest(files={7: _digest("a")})
    return cases


BAD_MANIFESTS = _bad_manifests()


@pytest.mark.parametrize("name", sorted(BAD_MANIFESTS))
def test_unverifiable_malformed_manifest_is_manifest_unreadable(name):
    result = trust.evaluate_integrity(BAD_MANIFESTS[name], _observed())
    assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert result["reason"] == trust.REASON_MANIFEST_UNREADABLE
    assert _lists(result) == ([], [], [])


@pytest.mark.parametrize("key", BAD_PATHS)
def test_valid_manifest_path_rejects_unsafe_keys(key):
    assert trust.valid_manifest_path(key) is False


@pytest.mark.parametrize("key", [A, S, "extension.json", "revit_mcp/\u0441\u0442\u0435\u043d\u0430.py"])
def test_valid_manifest_path_accepts_relative_keys(key):
    assert trust.valid_manifest_path(key) is True


def test_valid_manifest_path_rejects_non_text():
    assert trust.valid_manifest_path(None) is False
    assert trust.valid_manifest_path(b"revit_mcp/x.py") is False


# ---------------------------------------------------------------- read_error

def test_unverifiable_observed_none_is_read_error():
    result = trust.evaluate_integrity(_manifest(), None)
    assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert result["reason"] == trust.REASON_READ_ERROR


@pytest.mark.parametrize("missing_key", ["hashes", "present_py", "unreadable"])
def test_unverifiable_observed_missing_a_field_is_read_error(missing_key):
    observed = _observed()
    del observed[missing_key]
    result = trust.evaluate_integrity(_manifest(), observed)
    assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert result["reason"] == trust.REASON_READ_ERROR


def test_unverifiable_unreadable_wins_over_a_modified_file():
    observed = _observed(unreadable=[B])
    observed["hashes"][A] = _digest("tampered")
    result = trust.evaluate_integrity(_manifest(), observed)
    assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert result["reason"] == trust.REASON_READ_ERROR
    assert _lists(result) == ([], [], [])


def test_unverifiable_unhashable_observation_never_raises():
    result = trust.evaluate_integrity(_manifest(), _observed(present_py=[["x"]]))
    assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert result["reason"] == trust.REASON_READ_ERROR


def test_unverifiable_property_never_mismatch_when_a_file_is_also_modified():
    tampered = _observed()
    tampered["hashes"][A] = _digest("tampered")
    tampered["present_py"].append("revit_mcp/rogue.py")
    cases = []
    for manifest in BAD_MANIFESTS.values():
        cases.append((manifest, tampered))
    cases.append((None, tampered))
    cases.append((_manifest(), None))
    for key in ("hashes", "present_py", "unreadable"):
        broken = copy.deepcopy(tampered)
        del broken[key]
        cases.append((_manifest(), broken))
    cases.append((_manifest(), dict(tampered, unreadable=[A])))
    assert len(cases) > 25
    for manifest, observed in cases:
        result = trust.evaluate_integrity(manifest, observed)
        assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
        assert result["state"] != trust.INTEGRITY_MISMATCH
        assert result["reason"] in (trust.REASON_MANIFEST_MISSING,
                                    trust.REASON_MANIFEST_UNREADABLE,
                                    trust.REASON_READ_ERROR)


# ---------------------------------------------------------------- ordering and encoding

def test_result_does_not_depend_on_input_ordering():
    names = [A, B, S, "revit_mcp/zeta.py", "revit_mcp/_eta.py"]
    files = dict((n, _digest(n)) for n in names)
    base_hashes = dict(files)
    base_hashes[A] = _digest("tampered")
    del base_hashes[B]
    present = [n for n in names if n.startswith("revit_mcp/")] + ["revit_mcp/rogue.py"]
    expected = trust.evaluate_integrity(
        _manifest(files=files),
        {"hashes": base_hashes, "present_py": present, "unreadable": []})
    assert expected["state"] == trust.INTEGRITY_MISMATCH
    rng = random.Random(7)
    for _ in range(20):
        keys = list(files)
        rng.shuffle(keys)
        hkeys = list(base_hashes)
        rng.shuffle(hkeys)
        shuffled_present = list(present)
        rng.shuffle(shuffled_present)
        again = trust.evaluate_integrity(
            _manifest(files=dict((k, files[k]) for k in keys)),
            {"hashes": dict((k, base_hashes[k]) for k in hkeys),
             "present_py": shuffled_present, "unreadable": []})
        assert again == expected


def test_non_ascii_names_are_preserved_and_sorted_by_code_point():
    names = [u"revit_mcp/\u044f.py", u"revit_mcp/a.py", u"revit_mcp/\u0430.py", u"revit_mcp/_z.py"]
    result = trust.evaluate_integrity(
        _manifest(), _observed(present_py=[A, B] + names))
    assert result["state"] == trust.INTEGRITY_MISMATCH
    assert result["unexpected"] == sorted(names)
    assert result["unexpected"][-1] == u"revit_mcp/\u044f.py"
    assert trust.mismatch_files(result) == sorted(names)


def test_evaluate_does_not_mutate_its_inputs():
    manifest, observed = _manifest(), _observed(present_py=[A, B, "revit_mcp/x.py"])
    before = copy.deepcopy((manifest, observed))
    trust.evaluate_integrity(manifest, observed)
    assert (manifest, observed) == before


# ---------------------------------------------------------------- mismatch_files

@pytest.mark.parametrize("value", [None, [], "x", 5, {"modified": 3}])
def test_mismatch_files_of_a_malformed_result_is_empty(value):
    assert trust.mismatch_files(value) == []


# ---------------------------------------------------------------- 423

def test_integrity_423_status_and_body_keys():
    body, status = trust.integrity_failure(["revit_mcp/b.py", "revit_mcp/a.py"])
    assert status == 423
    assert sorted(body) == ["error", "files", "integrity"]
    assert body["integrity"] == "verified_mismatch"
    assert body["files"] == ["revit_mcp/a.py", "revit_mcp/b.py"]
    assert "Reinstall the extension" in body["error"]


@pytest.mark.parametrize("value", [None, 5, "revit_mcp/a.py", object()])
def test_integrity_423_non_iterable_gives_empty_files(value):
    body, status = trust.integrity_failure(value)
    assert status == 423
    assert body["files"] == []


def test_integrity_423_drops_non_text_items():
    body, _ = trust.integrity_failure(["b", 3, None, "a", "a"])
    assert body["files"] == ["a", "b"]


def test_integrity_423_collides_with_no_other_status_in_use():
    assert trust.INTEGRITY_FAILURE_STATUS == 423
    assert 423 not in {200, 401, 409, 412, 422, 503}


def test_integrity_423_body_names_the_files_of_a_real_result():
    observed = _observed(present_py=[A, B, "revit_mcp/rogue.py"])
    observed["hashes"][A] = _digest("tampered")
    result = trust.evaluate_integrity(_manifest(), observed)
    body, status = trust.integrity_failure(trust.mismatch_files(result))
    assert status == 423
    assert body["files"] == [A, "revit_mcp/rogue.py"]
