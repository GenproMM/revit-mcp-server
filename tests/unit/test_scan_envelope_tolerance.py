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


# ------------------------------------------------------------------ the suspect table


SUSPECT_ROWS = [
    ("x = data.items()", "items"),
    ("x = data.keys()", "keys"),
    ("x = data.values()", "values"),
    ("x = data.copy()", "copy"),
    ("x = dict(data)", "dict()"),
    ("x = list(data)", "list()"),
    ("x = len(data)", "len()"),
    ("x = json.dumps(data)", "json.dumps()"),
    ("x = str(data)", "str()"),
    ('x = "{}".format(data)', "format()"),
    ("x = f(**data)", "double star"),
    ("x = routes.make_response(data=data)", "make_response keyword"),
    ("x = helper(data)", "helper()"),
    ("x = [k for k in data]", "comprehension"),
    ("for key in data:\n    pass", "for loop"),
    ("return data", "return"),
    ("other = data", "alias"),
    ('x = {"echo": data}', "container"),
    ('x = "%s" % data', "binary operation"),
    ("x = data.get", "get not called"),
]


@pytest.mark.parametrize("body", [row[0] for row in SUSPECT_ROWS], ids=[row[1] for row in SUSPECT_ROWS])
def test_every_non_read_use_of_the_body_is_suspect_and_names_line_3(scanner, body):
    findings = scanner.scan_source("m.py", handler(body))
    assert findings, "no finding for: " + body
    assert {line for _, line, _ in findings} == {3}


def test_a_compound_parse_expression_is_tracked(scanner):
    source = (
        "def handler(doc, request):\n"
        "    data = parse_request_data(request.data) if request.data else {}\n"
        "    return data\n"
    )
    assert [line for _, line, _ in scanner.scan_source("m.py", source)] == [3]


def test_a_reply_that_reuses_the_name_only_after_rebinding_is_tolerant(scanner):
    source = handler(
        'name = data.get("name")\n'
        'data = {"status": "success", "name": name}\n'
        "return routes.make_response(data=data)"
    )
    assert scanner.scan_source("m.py", source) == []


# --------------------------------------------------------------- raw request.data reads


RAW_SUSPECT = [
    "x = request.data.decode()",
    'return routes.make_response(data={"echo": request.data})',
    "x = request.data or {}",
    "x = len(request.data)",
]
RAW_TOLERANT = [
    "x = parse_request_data(request.data)",
    "if not request or not request.data:\n    pass",
    "if request and request.data:\n    pass",
]


def raw_source(body):
    lines = ["def handler(doc, request):"]
    lines.extend("    " + line for line in body.splitlines())
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("body", RAW_SUSPECT)
def test_a_raw_read_of_request_data_is_suspect(scanner, body):
    findings = scanner.scan_source("m.py", raw_source(body))
    assert findings
    assert all("request.data" in reason for _, _, reason in findings)


@pytest.mark.parametrize("body", RAW_TOLERANT)
def test_the_sanctioned_reads_of_request_data_are_tolerant(scanner, body):
    assert scanner.scan_source("m.py", raw_source(body)) == []


def test_a_module_that_does_not_parse_is_a_finding_not_a_pass(scanner):
    findings = scanner.scan_source("m.py", "def broken(:\n")
    assert len(findings) == 1
    assert "does not parse" in findings[0][2]


# ---------------------------------------------------------------------------- --dir CLI


def write_module(folder, name, source):
    with open(os.path.join(str(folder), name), "wb") as handle:
        handle.write(source.encode("utf-8"))


def snapshot(root):
    seen = {}
    for folder, dirs, names in os.walk(str(root)):
        for name in dirs + names:
            path = os.path.join(folder, name)
            stat = os.stat(path)
            seen[path] = (stat.st_size, stat.st_mtime_ns)
    return seen


def test_dir_mode_reports_one_line_per_module_and_exits_1_on_a_suspect(scanner, tmp_path, capsys):
    write_module(tmp_path, "good.py", handler('x = data.get("x")'))
    write_module(tmp_path, "bad.py", handler("for key in data:\n    pass"))
    before = snapshot(tmp_path)

    code = scanner.main(["--dir", str(tmp_path)])
    lines = capsys.readouterr().out.splitlines()

    assert code == 1
    assert lines == [
        "ENVELOPE_SUSPECT bad.py:3 iterated",
        "ENVELOPE_TOLERANT good.py",
        "ENVELOPE_SCAN_SUSPECT findings=1",
    ]
    assert snapshot(tmp_path) == before


def test_dir_mode_exits_0_when_every_module_is_tolerant(scanner, tmp_path, capsys):
    write_module(tmp_path, "good.py", handler('x = data.get("x")'))
    assert scanner.main(["--dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "ENVELOPE_TOLERANT good.py",
        "ENVELOPE_SCAN_OK files=1",
    ]


def test_dir_mode_skips_pycache_and_other_files(scanner, tmp_path, capsys):
    write_module(tmp_path, "good.py", handler('x = data.get("x")'))
    write_module(tmp_path, "notes.txt", "for key in data:\n")
    os.mkdir(os.path.join(str(tmp_path), "__pycache__"))
    write_module(os.path.join(str(tmp_path), "__pycache__"), "junk.py", handler("return data"))
    assert scanner.main(["--dir", str(tmp_path)]) == 0
    assert "files=1" in capsys.readouterr().out


def test_dir_mode_missing_directory_exits_2_with_an_error_line(scanner, tmp_path, capsys):
    assert scanner.main(["--dir", str(tmp_path / "missing")]) == 2
    assert capsys.readouterr().out.startswith("ERROR:")


def test_dir_mode_without_any_module_exits_2(scanner, tmp_path, capsys):
    assert scanner.main(["--dir", str(tmp_path)]) == 2
    assert capsys.readouterr().out.startswith("ERROR:")


@needs_git
def test_unknown_git_revision_exits_2_with_an_error_line(scanner, capsys):
    code = scanner.main(["--git-rev", "no-such-revision-0000", "--repo", REPO_ROOT])
    assert code == 2
    assert capsys.readouterr().out.startswith("ERROR:")


def test_no_source_given_or_both_given_exits_2(scanner, tmp_path, capsys):
    assert scanner.main([]) == 2
    assert scanner.main(["--dir", str(tmp_path), "--git-rev", "HEAD"]) == 2
    assert "ENVELOPE_SCAN_" not in capsys.readouterr().out


def test_the_current_extension_tree_scans_without_a_usage_error(scanner, capsys):
    code = scanner.main(["--dir", os.path.join(REPO_ROOT, "revit_mcp")])
    lines = capsys.readouterr().out.splitlines()
    assert code in (0, 1)
    assert lines[-1].startswith("ENVELOPE_SCAN_")


def test_the_output_is_sorted_by_module_then_line(scanner, tmp_path, capsys):
    write_module(tmp_path, "b.py", handler("return data"))
    write_module(tmp_path, "a.py", handler("x = len(data)\ny = list(data)"))
    scanner.main(["--dir", str(tmp_path)])
    heads = [line.split(" ")[1] for line in capsys.readouterr().out.splitlines()[:-1]]
    assert heads == ["a.py:3", "a.py:4", "b.py:3"]


# ----------------------------------------------------------------- build-server grammar


def test_the_scanner_parses_under_python_38_grammar_and_has_no_annotations():
    import ast

    with open(SCANNER, "rb") as handle:
        source = handle.read().decode("utf-8")
    tree = ast.parse(source, feature_version=(3, 8))
    for node in ast.walk(tree):
        assert not isinstance(node, ast.AnnAssign)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.returns is None
            every = node.args.args + node.args.kwonlyargs
            assert all(arg.annotation is None for arg in every)


def test_the_scanner_imports_only_the_standard_library_it_names():
    import ast

    with open(SCANNER, "rb") as handle:
        tree = ast.parse(handle.read().decode("utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported <= {"argparse", "ast", "os", "subprocess", "sys"}
