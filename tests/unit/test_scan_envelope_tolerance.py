# -*- coding: utf-8 -*-
"""D-06 static check: an extension tree tolerates the _mcp envelope. Needs no Revit."""

import importlib.util
import os
import shutil
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCANNER = os.path.join(REPO_ROOT, "scripts", "scan_envelope_tolerance.py")
PRE_PHASE_REV = "c187004"

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")


@pytest.fixture(scope="module")
def scanner():
    spec = importlib.util.spec_from_file_location("scan_envelope_tolerance_tool", SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def handler(body):
    """A route handler that parses its body into `data`, then runs `body`."""
    lines = [
        "def handler(doc, request):",
        "    data = parse_request_data(request.data)",
    ]
    lines.extend("    " + line for line in body.splitlines())
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------- tolerant shapes


TOLERANT = [
    ('x = data.get("x")', "get"),
    ('x = data["x"]', "subscript"),
    ('if "x" in data:\n    pass', "in"),
    ('if "x" not in data:\n    pass', "not in"),
    ("if not data:\n    pass", "truthiness via not"),
    ("if data:\n    pass", "truthiness"),
    ("if isinstance(data, dict):\n    pass", "isinstance"),
    ("if data == {}:\n    pass", "comparison"),
    ('x = data.get("a", {}).get("b")', "get chain"),
]


@pytest.mark.parametrize("body", [row[0] for row in TOLERANT], ids=[row[1] for row in TOLERANT])
def test_read_only_uses_of_the_body_are_tolerant(scanner, body):
    assert scanner.scan_source("m.py", handler(body)) == []


def test_rebinding_to_a_reply_dict_ends_the_tracking(scanner):
    source = handler(
        'x = data.get("x")\n'
        'data = {"status": "success"}\n'
        "return routes.make_response(data=data)"
    )
    assert scanner.scan_source("m.py", source) == []


def test_iterating_the_body_is_suspect_and_names_the_line(scanner):
    findings = scanner.scan_source("m.py", handler("for key in data:\n    pass"))
    assert len(findings) == 1
    label, line, reason = findings[0]
    assert label == "m.py"
    assert line == 3
    assert "iterated" in reason


# ------------------------------------------------------------ the real pre-phase tree


@needs_git
def test_pre_phase_tree_scan_completes_and_prints_one_line_per_module(scanner, capsys):
    probe = subprocess.run(
        ["git", "-C", REPO_ROOT, "rev-parse", "--verify", PRE_PHASE_REV + "^{commit}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if probe.returncode != 0:
        pytest.skip("revision {} is not in this clone".format(PRE_PHASE_REV))

    code = scanner.main(["--git-rev", PRE_PHASE_REV, "--repo", REPO_ROOT])
    lines = capsys.readouterr().out.splitlines()

    assert code in (0, 1)
    assert all(line.startswith("ENVELOPE_") for line in lines)
    modules = [line for line in lines if line.startswith(("ENVELOPE_TOLERANT", "ENVELOPE_SUSPECT"))]
    assert len(modules) >= 24
    assert lines[-1].startswith("ENVELOPE_SCAN_OK" if code == 0 else "ENVELOPE_SCAN_SUSPECT")


def test_a_handler_nested_in_the_register_function_is_followed(scanner):
    source = (
        "def register_x_routes(api):\n"
        "    @api.route('/x/', methods=['POST'])\n"
        "    def handler(doc, request):\n"
        "        data = parse_request_data(request.data) or {}\n"
        "        for key in data:\n"
        "            pass\n"
    )
    findings = scanner.scan_source("m.py", source)
    assert [(line, "iterated" in reason) for _, line, reason in findings] == [(5, True)]


def test_a_branch_that_rebinds_does_not_hide_the_other_path(scanner):
    source = handler(
        "if x:\n"
        "    data = {}\n"
        "return routes.make_response(data=data)"
    )
    findings = scanner.scan_source("m.py", source)
    assert len(findings) == 1


def test_the_parse_of_a_non_request_value_is_out_of_scope(scanner):
    source = (
        "def split(raw):\n"
        "    data = parse_request_data(raw)\n"
        "    return dict((k, v) for k, v in data.items())\n"
    )
    assert scanner.scan_source("trust.py", source) == []
