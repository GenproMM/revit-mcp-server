# -*- coding: utf-8 -*-
"""Phase 6 live audit gate (skeleton for the RED commit of plan 06-06): stubs only."""
import re

BAD_ID = 999999999
DEFAULT_PORT = 48884
DEFAULT_COUNT = 5
MAX_COUNT = 20
SENTINEL_OK = "PHASE6_AUDIT_OK"
SENTINEL_STOP = "PHASE6_AUDIT_STOP"
ALLOWED_READS = frozenset()
ALLOWED_TOOLS = frozenset()
AUDIT_LINE = re.compile(r"^Audit: call_id ([0-9a-f-]{36})$", re.MULTILINE)


def _outside_repo(path):
    raise NotImplementedError


def evidence_template():
    raise NotImplementedError


def secret_occurrences(data, secret):
    raise NotImplementedError


def parse_audit_files(mapping):
    raise NotImplementedError


def audit_id_of(reply_text):
    raise NotImplementedError


def classify_single(record, secret):
    raise NotImplementedError


def classify_dual(record, secret):
    raise NotImplementedError


def refusal(args):
    raise NotImplementedError


def report(verdict, reasons, posts_sent, secret_occurrences=None):
    raise NotImplementedError


def main(argv=None):
    raise NotImplementedError
