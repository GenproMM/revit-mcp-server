# -*- coding: utf-8 -*-
"""Verbatim documentation pins for the Phase 7 authorization limits."""

import os

import pytest

import approval


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BYPASS_SECRET_SENTENCE = (
    "A process that can read the shared secret can mint its own one-time permits: the permit stops callers on the LAN, a stray curl and an outdated payload, not an agent running with the user's own OS rights."
)
BYPASS_CODE_SENTENCE = (
    "Confirming execute_revit_code is not a review of the code: arbitrary code can still do anything the Revit API allows, including binding a shared parameter that is not in the company file."
)
BYPASS_OVERLAP_SENTENCE = (
    "A permit is bound to its own request bytes; it does not fix cross-process overlap in pyRevit's shared handler (backlog 999.1)."
)
BYPASS_LOAD_FAMILY_SENTENCE = (
    "load_family is confirmed, but the shared parameters inside the loaded family file are not checked against the company shared-parameter file."
)
POLICY_DEFAULT_SENTENCE = (
    "Which operations need a confirmation is the default of the base policy; the fleet operator can change any rule, relaxing ones included."
)
REDELIVERY_SENTENCE = (
    "A client that redelivers an already executed allow-class call to a new server process can run it a second time without a window; a confirm-class call always opens a new window."
)
RU_LIMIT_SENTENCE = (
    "Подтверждение защищает от случайной опасной операции, но не от программы, которая работает с вашими правами Windows и может прочитать общий секрет."
)

ENGLISH_LIMITS = (
    BYPASS_SECRET_SENTENCE,
    BYPASS_CODE_SENTENCE,
    BYPASS_OVERLAP_SENTENCE,
    BYPASS_LOAD_FAMILY_SENTENCE,
    POLICY_DEFAULT_SENTENCE,
    REDELIVERY_SENTENCE,
)


def _read(relpath):
    with open(os.path.join(REPO_ROOT, relpath), encoding="utf-8") as handle:
        return handle.read()


@pytest.mark.parametrize("sentence", ENGLISH_LIMITS)
def test_claude_md_pins_each_phase7_limit(sentence):
    assert sentence in _read("CLAUDE.md")


@pytest.mark.parametrize("sentence", ENGLISH_LIMITS)
def test_approval_docstring_pins_each_phase7_limit(sentence):
    assert sentence in approval.__doc__


def test_user_guide_pins_russian_phase7_limit():
    assert RU_LIMIT_SENTENCE in _read(os.path.join("deploy", "USER-GUIDE.md"))


def test_r5_runbook_names_operator_policy():
    assert "operator_policy.toml" in _read(os.path.join("deploy", "RELEASE-RUNBOOK.md"))


def test_user_guide_explains_unconfirmed_refusal():
    assert "подтверждение не получено" in _read(os.path.join("deploy", "USER-GUIDE.md"))
