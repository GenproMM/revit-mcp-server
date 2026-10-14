# -*- coding: utf-8 -*-
"""Doc pins for the honest scope of serialization (SER-05, d27-b, IDENT-05).

The wording of three sentences is load-bearing: it tells a developer, a fleet
admin and an engineer what the bridge's lock does and does not protect. These
tests fail if a sentence drifts or an over-claim phrase appears. Needs no Revit.
"""

import ast
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCOPE_SENTENCE = (
    "Serialization covers calls issued through this one MCP server process only."
)
STATUS_SENTENCE = (
    "Only /status/ skips the queue: every other call to Revit, reads included, "
    "waits for the lock."
)
CROSS_PROCESS_SENTENCE = (
    "Overlapping sessions against one Revit can still cross-wire until d27-c lands."
)
RU_CROSS_PROCESS_SENTENCE = (
    "Две сессии помощника, одновременно работающие с одним Revit, "
    "могут получить ответы друг друга."
)

# Lowercase phrases no doc may contain: each one would tell a reader that a
# call is protected when, under d27-b, it is not or is only queued.
OVERCLAIMS = [
    "reads are safe",
    "safe during mutations",
    "guarantees exclusive",
    "no other client can",
    "does not queue reads",
    "reads never wait",
    "reads are not blocked",
]

# Files scanned for over-claims; Task 2 of plan 01-07 widens this list.
OVERCLAIM_SCANNED = ["CLAUDE.md"]


def _read(relpath):
    with open(os.path.join(REPO_ROOT, relpath), encoding="utf-8") as handle:
        return handle.read()


def _bridge_docstring():
    return ast.get_docstring(ast.parse(_read("bridge.py")))


def test_serialization_scope_pinned_in_bridge_docstring():
    doc = _bridge_docstring()
    for needle in (
        SCOPE_SENTENCE,
        STATUS_SENTENCE,
        CROSS_PROCESS_SENTENCE,
        "curl",
        "/execute_code/",
        "/model_info/",
        "cross-wired-mutation",
        "cross-wired-read",
        "6.5.3",
        "2026-10-07",
        "REVIT_PORT",
    ):
        assert needle in doc, "bridge.py docstring lost {!r}".format(needle)


def test_serialization_scope_docstring_has_no_transport_markers():
    """Other tests slice bridge.py's source on these markers; the docstring
    comes first, so a literal copy would shift every slice."""
    doc = _bridge_docstring()
    markers = (
        "def _get_client()",  # tests/unit/test_local_bridge_transport.py
        "async def revit_get",  # tests/unit/test_local_bridge_transport.py
        "else:  # POST",  # tests/unit/test_textutils.py
    )
    for marker in markers:
        assert marker not in doc, "docstring contains slicing marker {!r}".format(marker)
    source = _read("bridge.py")
    for marker in markers:
        assert source.count(marker) == 1, "marker {!r} must stay unique".format(marker)


def test_serialization_scope_pinned_in_claude_md():
    text = _read("CLAUDE.md")
    for needle in (
        SCOPE_SENTENCE,
        STATUS_SENTENCE,
        CROSS_PROCESS_SENTENCE,
        "REVIT_PORT",
        "bridge.py",
        "UNLOCKED_GET",
    ):
        assert needle in text, "CLAUDE.md lost {!r}".format(needle)
    old = "Port `48884` is hardcoded; only the host is configurable"
    assert old not in text, "CLAUDE.md still says the port is hardcoded"


def test_serialization_scope_no_overclaims():
    scanned = {"bridge.py docstring": _bridge_docstring()}
    for relpath in OVERCLAIM_SCANNED:
        scanned[relpath] = _read(relpath)
    for name, text in scanned.items():
        lowered = text.lower()
        for phrase in OVERCLAIMS:
            assert phrase not in lowered, "{} contains over-claim {!r}".format(name, phrase)
