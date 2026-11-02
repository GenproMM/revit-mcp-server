# -*- coding: utf-8 -*-
"""Product version and runtime facts in /status/ and get_revit_status. Needs no Revit."""

import importlib
import json
import re
from pathlib import Path

from revit_mcp import runtime_info
from tools import status_tools
from tools.status_tools import _version_lines

from test_phase5_status_diagnostics import load_status

ROOT = Path(__file__).resolve().parents[2]

_SERVER = {"product_version": "2.0.0", "build": "2026.11.02-1200.abc1234", "python": "3.12.3",
           "mcp_sdk": "1.30.0", "executable": "python.exe"}


def _runtime(**overrides):
    block = {
        "product_version": "2.0.0",
        "extension": {"path": r"\\srv\share\ext\revit-mcp-server.extension",
                      "commit": "92fbaf585b0de09add80921165416366f3ee9988", "built_at": "2026-10-26T18:06:15"},
        "python": {"implementation": "ironpython", "version": "3.4.2", "major": 3},
        "pyrevit": {"version": "6.5.5.26237+2044", "engine": "IPY342", "home": None},
        "revit": {"version": "2024", "sub_version": "2024.3.3", "build": "20250516_1515(x64)"},
    }
    block.update(overrides)
    return block


def test_product_version_is_the_same_in_both_halves_and_the_build():
    match = re.search(r'(?m)^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert match.group(1) == runtime_info.PRODUCT_VERSION == status_tools.PRODUCT_VERSION == "2.0.0"


def test_python_info_names_the_running_interpreter():
    info = runtime_info.python_info()
    assert info["major"] == 3
    assert re.match(r"^\d+\.\d+\.\d+$", info["version"])
    assert info["implementation"]


def test_extension_build_reads_the_manifest_once(tmp_path):
    manifest = tmp_path / "_manifest.json"
    manifest.write_text(json.dumps({"schema": 1, "commit": "abc", "generated_at": "t", "files": {}}),
                        encoding="utf-8")
    first = runtime_info.extension_build(str(tmp_path))
    manifest.unlink()
    assert first == {"path": str(tmp_path), "commit": "abc", "built_at": "t"}
    assert runtime_info.extension_build(str(tmp_path)) == first


def test_extension_build_without_a_manifest_has_no_commit(tmp_path):
    assert runtime_info.extension_build(str(tmp_path)) == {
        "path": str(tmp_path), "commit": None, "built_at": None}


def test_ironpython_2_engine_raises_an_alert_and_python_3_does_not():
    ipy27 = _runtime(python={"implementation": "ironpython", "version": "2.7.12", "major": 2})
    alerts = runtime_info.runtime_alerts(ipy27)
    assert len(alerts) == 1 and "IPY342" in alerts[0] and "2.7.12" in alerts[0]
    assert runtime_info.runtime_alerts(_runtime()) == []
    assert runtime_info.runtime_alerts(None) == []


def test_status_route_reports_the_runtime_block(monkeypatch):
    handler, _ = load_status(monkeypatch)
    status, body = handler()
    assert status == 200
    runtime = body["runtime"]
    assert runtime["product_version"] == "2.0.0"
    assert runtime["python"]["major"] == 3
    assert runtime["revit"]["version"] == "2024"
    assert runtime["extension"]["path"] == str(ROOT)
    assert "runtime_alerts" not in body
    assert body["health"] == "healthy"


def test_status_route_degrades_health_on_an_unsupported_engine(monkeypatch):
    handler, security = load_status(monkeypatch)
    # status.py imports runtime_info lazily from the same synthetic package as security.
    module = importlib.import_module(security.__name__.rpartition(".")[0] + ".runtime_info")
    monkeypatch.setattr(module, "python_info",
                        lambda: {"implementation": "ironpython", "version": "2.7.12", "major": 2})
    status, body = handler()
    assert body["health"] == "degraded"
    assert body["runtime_alerts"] and "IPY342" in body["runtime_alerts"][0]


def test_version_lines_name_both_halves():
    lines = _version_lines({"status": "active", "runtime": _runtime()}, _SERVER)
    assert lines[0] == ("MCP server: RevitMCP 2.0.0, build 2026.11.02-1200.abc1234, Python 3.12.3, "
                        "MCP SDK 1.30.0.")
    assert lines[1] == ("Revit extension: RevitMCP 2.0.0, build 92fbaf5 (2026-10-26T18:06:15), "
                        r"loaded from \\srv\share\ext\revit-mcp-server.extension.")
    assert lines[2] == ("Revit side: pyRevit 6.5.5.26237+2044, engine IPY342 (ironpython 3.4.2), "
                        "Revit 2024.3.3 build 20250516_1515(x64).")
    assert len(lines) == 3


def test_version_lines_flag_an_old_extension_and_a_difference():
    old = _version_lines({"status": "active"}, _SERVER)
    assert old[-1] == "Revit extension: reports no version (older than 2.0.0)."
    differ = _version_lines({"status": "active", "runtime": _runtime(product_version="2.1.0")}, _SERVER)
    assert differ[-1].startswith("Versions DIFFER: the Revit extension is 2.1.0, this MCP server is 2.0.0")


def test_version_lines_without_a_reply_name_only_the_server():
    assert _version_lines("Error: Revit is not reachable", dict(_SERVER, build=None)) == [
        "MCP server: RevitMCP 2.0.0, build development checkout, Python 3.12.3, MCP SDK 1.30.0."]


def test_server_info_in_a_checkout_has_no_build():
    info = status_tools.server_info()
    assert info["product_version"] == "2.0.0"
    assert info["build"] is None
    assert re.match(r"^\d+\.\d+\.\d+$", info["python"])
