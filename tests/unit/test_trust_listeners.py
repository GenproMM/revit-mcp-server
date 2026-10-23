# -*- coding: utf-8 -*-
"""trust.classify_listeners: is the Routes listener reachable beyond loopback (SEC-07, D-16).

The input is a plain list of (host text, port) pairs. Phase 5 builds it from the
.NET active TCP listener table; this suite only proves the pure classification, so
a wildcard, LAN or hostname bind is named "exposed" and a plain loopback bind is
"loopback_only". A bad input is "unknown", never an exception. Needs no Revit.
"""

import pytest

from revit_mcp import trust

PORT = 48884

LOOPBACK = "loopback_only"
EXPOSED = "exposed"
UNKNOWN = "unknown"

TABLE = [
    # loopback in every spelling the OS table can produce
    ([("127.0.0.1", PORT)], PORT, LOOPBACK),
    ([("127.0.0.2", PORT)], PORT, LOOPBACK),
    ([("127.255.255.254", PORT)], PORT, LOOPBACK),
    ([("::1", PORT)], PORT, LOOPBACK),
    ([("[::1]", PORT)], PORT, LOOPBACK),
    ([("0:0:0:0:0:0:0:1", PORT)], PORT, LOOPBACK),
    ([("::ffff:127.0.0.1", PORT)], PORT, LOOPBACK),
    ([("::FFFF:127.0.0.1", PORT)], PORT, LOOPBACK),
    ([("::1%1", PORT)], PORT, LOOPBACK),
    ([("[::1%1]", PORT)], PORT, LOOPBACK),
    ([("  127.0.0.1  ", PORT)], PORT, LOOPBACK),
    # reachable beyond the workstation, or not provably loopback
    ([("0.0.0.0", PORT)], PORT, EXPOSED),
    ([("::", PORT)], PORT, EXPOSED),
    ([("[::]", PORT)], PORT, EXPOSED),
    ([("192.168.1.20", PORT)], PORT, EXPOSED),
    ([("10.0.0.5", PORT)], PORT, EXPOSED),
    ([("8.8.8.8", PORT)], PORT, EXPOSED),
    ([("fe80::1%12", PORT)], PORT, EXPOSED),
    ([("::ffff:192.168.1.20", PORT)], PORT, EXPOSED),
    ([("localhost", PORT)], PORT, EXPOSED),
    ([("999.0.0.1", PORT)], PORT, EXPOSED),
    ([("127.0.0", PORT)], PORT, EXPOSED),
    ([("127.0.0.1.5", PORT)], PORT, EXPOSED),
    ([("127.0.0.-1", PORT)], PORT, EXPOSED),
    ([("0127.0.0.1", PORT)], PORT, EXPOSED),
    ([("127.0.0.01", PORT)], PORT, EXPOSED),
    ([("", PORT)], PORT, EXPOSED),
    # one exposed listener among loopback ones makes the whole bind exposed
    ([("127.0.0.1", PORT), ("0.0.0.0", PORT)], PORT, EXPOSED),
    ([("::1", PORT), ("192.168.1.20", PORT)], PORT, EXPOSED),
    # the two-Revit case is not an exposure: two loopback listeners stay loopback_only
    ([("127.0.0.1", PORT), ("127.0.0.1", PORT)], PORT, LOOPBACK),
    ([("127.0.0.1", PORT), ("::1", PORT)], PORT, LOOPBACK),
    # only the given port counts
    ([("0.0.0.0", 8000), ("127.0.0.1", PORT)], PORT, LOOPBACK),
    ([("0.0.0.0", 8000)], PORT, UNKNOWN),
    ([("127.0.0.1", PORT + 1)], PORT, UNKNOWN),
    # a port written as text is read as a number
    ([("127.0.0.1", "48884")], PORT, LOOPBACK),
    ([("127.0.0.1", PORT)], "48884", LOOPBACK),
    ([("0.0.0.0", "48884")], "48884", EXPOSED),
    # a tuple or a list is an endpoint; any iterable of endpoints is a list of endpoints
    ([["127.0.0.1", PORT]], PORT, LOOPBACK),
    ((("127.0.0.1", PORT),), PORT, LOOPBACK),
    # nothing to classify
    (None, PORT, UNKNOWN),
    (42, PORT, UNKNOWN),
    ([], PORT, UNKNOWN),
    ([("127.0.0.1",)], PORT, UNKNOWN),
    ([("127.0.0.1", PORT, "x")], PORT, UNKNOWN),
    ([(None, PORT)], PORT, UNKNOWN),
    ([(b"127.0.0.1", PORT)], PORT, UNKNOWN),
    ([("127.0.0.1", "abc")], PORT, UNKNOWN),
    ([("127.0.0.1", None)], PORT, UNKNOWN),
    ([("127.0.0.1", True)], PORT, UNKNOWN),
    ([("127.0.0.1", PORT), None], PORT, UNKNOWN),
    ([("127.0.0.1", PORT), "x"], PORT, UNKNOWN),
    ([("127.0.0.1", PORT)], None, UNKNOWN),
    ([("127.0.0.1", PORT)], "abc", UNKNOWN),
    ([("127.0.0.1", PORT)], True, UNKNOWN),
    ([("127.0.0.1", PORT)], "", UNKNOWN),
    ([("127.0.0.1", PORT)], -1, UNKNOWN),
]


@pytest.mark.parametrize("endpoints,port,expected", TABLE)
def test_classification_table(endpoints, port, expected):
    assert trust.classify_listeners(endpoints, port) == expected


def test_a_generator_of_endpoints_is_accepted():
    assert trust.classify_listeners(
        ((host, PORT) for host in ("127.0.0.1", "::1")), PORT
    ) == LOOPBACK


def test_constants_are_the_three_documented_words():
    assert trust.BIND_LOOPBACK_ONLY == LOOPBACK
    assert trust.BIND_EXPOSED == EXPOSED
    assert trust.BIND_UNKNOWN == UNKNOWN


def test_the_table_exercises_all_three_outcomes():
    assert set(row[2] for row in TABLE) == set([LOOPBACK, EXPOSED, UNKNOWN])


def test_a_hostile_endpoint_never_raises():
    class Explodes(object):
        def __iter__(self):
            raise RuntimeError("boom")

        def __len__(self):
            raise RuntimeError("boom")

    class Port(object):
        def __int__(self):
            raise RuntimeError("boom")

    assert trust.classify_listeners(Explodes(), PORT) == UNKNOWN
    assert trust.classify_listeners([Explodes()], PORT) == UNKNOWN
    assert trust.classify_listeners([("127.0.0.1", Port())], PORT) == UNKNOWN
    assert trust.classify_listeners([("127.0.0.1", PORT)], Port()) == UNKNOWN


@pytest.mark.parametrize("host,expected", [
    ("127.0.0.1", True),
    ("::1", True),
    ("[::1]", True),
    ("::ffff:127.0.0.9", True),
    ("0.0.0.0", False),
    ("::", False),
    ("::ffff:10.0.0.1", False),
    ("localhost", False),
    ("::ffff:::ffff:127.0.0.1", False),
    (None, False),
    (127, False),
    (b"127.0.0.1", False),
])
def test_loopback_test_on_a_single_host(host, expected):
    assert trust._is_loopback_host(host) is expected


@pytest.mark.parametrize("value,expected", [
    (48884, 48884),
    ("48884", 48884),
    (" 48884 ", 48884),
    (0, 0),
    (True, None),
    (False, None),
    (-1, None),
    ("-1", None),
    ("48884.0", None),
    ("abc", None),
    ("", None),
    (None, None),
    (1.5, None),
    (b"48884", None),
])
def test_port_reading(value, expected):
    assert trust._as_port(value) == expected
