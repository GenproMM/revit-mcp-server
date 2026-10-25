# -*- coding: utf-8 -*-
"""Phase 7 (07-05): a permit is consumed exactly once, however many callers race for it.

The single-use registry of revit_mcp/permits.py is shared by every request thread of the
Routes server. These rows hit it from 32 threads released together by a barrier, and check
that only fully verified permits are recorded, that spent entries are purged and that the
registry is bounded. Needs no Revit.
"""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import permit
from revit_mcp import permits

SECRET = "phase7-permit-concurrency-secret-0123456789"
SESSION = "33333333-3333-4333-8333-333333333333"
ROUTE = "/delete_elements/"
NOW = 1900000000
THREADS = 32


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch):
    monkeypatch.setattr(permits, "_CONSUMED", {})


def mint(i=0, now=NOW, ttl=60):
    text = permit.args_text({"element_ids": [i]})
    minted = permit.mint(SECRET, ROUTE, text, SESSION, "abcdefabcdef", ttl, now=now)
    raw = permit.wire_text(text, {"secret": SECRET, "permit": minted}).encode("ascii")
    return raw, minted


def check(raw, now=NOW):
    return permits.check_and_consume(raw, ROUTE, SECRET, SESSION, now=now)


def race(raws, now=NOW):
    """Run one check per entry of ``raws`` on its own thread, all released together."""
    barrier = threading.Barrier(len(raws))

    def one(raw):
        barrier.wait(timeout=30)
        return check(raw, now=now)

    with ThreadPoolExecutor(max_workers=len(raws)) as pool:
        return list(pool.map(one, raws))


def test_the_same_permit_on_32_threads_is_consumed_exactly_once():
    raw, _ = mint()
    results = race([raw] * THREADS)
    assert results.count("ok") == 1 and results.count("replayed") == 31
    assert len(permits._CONSUMED) == 1


def test_the_32_thread_race_is_stable_over_repeats():
    for i in range(10):
        raw, _ = mint(i)
        results = race([raw] * THREADS)
        assert results.count("ok") == 1 and results.count("replayed") == THREADS - 1


def test_32_distinct_permits_in_parallel_are_all_accepted():
    raws = [mint(i)[0] for i in range(THREADS)]
    results = race(raws)
    assert results == ["ok"] * THREADS
    assert len(permits._CONSUMED) == THREADS


def test_a_failed_check_never_records_a_nonce():
    raw, minted = mint()
    for bad in (
        permit.wire_text(permit.args_text({"element_ids": [0]}), {"secret": SECRET, "permit": dict(minted, m="0" * 64)}),
        permit.wire_text(permit.args_text({"element_ids": [9]}), {"secret": SECRET, "permit": minted}),
    ):
        assert check(bad.encode("ascii")) in ("bad_signature", "args_mismatch")
    assert check(raw, now=minted["e"] + permits.SKEW + 1) == "expired"
    assert check(raw, now=minted["e"] - permits.MAX_TTL - 1) == "ttl_too_long"
    assert permits.check_and_consume(raw, "/other/", SECRET, SESSION, now=NOW) == "route_mismatch"
    assert permits.check_and_consume(raw, ROUTE, SECRET, "someone-else", now=NOW) == "session_mismatch"
    assert permits._CONSUMED == {}
    assert check(raw) == "ok"
    assert list(permits._CONSUMED) == [minted["n"]]


def test_spent_entries_are_purged_by_the_next_successful_check():
    first, minted = mint(1, now=NOW)
    assert check(first, now=NOW) == "ok"
    assert len(permits._CONSUMED) == 1
    later = minted["e"] + permits.SKEW + 1
    second, _ = mint(2, now=later)
    assert check(second, now=later) == "ok"
    assert list(permits._CONSUMED) != [minted["n"]]
    assert len(permits._CONSUMED) == 1


def test_an_entry_inside_the_skew_window_is_not_purged_and_still_replays():
    raw, minted = mint(1)
    assert check(raw) == "ok"
    at = minted["e"] + permits.SKEW
    other, _ = mint(2, now=at)
    assert check(other, now=at) == "ok"
    assert len(permits._CONSUMED) == 2
    assert check(raw, now=at) == "replayed"


def test_a_full_registry_answers_registry_full_until_entries_expire(monkeypatch):
    monkeypatch.setattr(permits, "REGISTRY_CAP", 3)
    for i in range(3):
        assert check(mint(i)[0]) == "ok"
    fourth, _ = mint(3)
    assert check(fourth) == "registry_full"
    assert len(permits._CONSUMED) == 3
    later = NOW + 60 + permits.SKEW + 1
    fresh, _ = mint(4, now=later)
    assert check(fresh, now=later) == "ok"
    assert len(permits._CONSUMED) == 1


def test_a_refused_registry_full_permit_is_not_recorded(monkeypatch):
    monkeypatch.setattr(permits, "REGISTRY_CAP", 1)
    assert check(mint(0)[0]) == "ok"
    refused, minted = mint(1)
    assert check(refused) == "registry_full"
    assert minted["n"] not in permits._CONSUMED


def test_a_race_at_the_cap_admits_exactly_the_cap(monkeypatch):
    monkeypatch.setattr(permits, "REGISTRY_CAP", 5)
    results = race([mint(i)[0] for i in range(THREADS)])
    assert results.count("ok") == 5
    assert results.count("registry_full") == THREADS - 5
    assert len(permits._CONSUMED) == 5
