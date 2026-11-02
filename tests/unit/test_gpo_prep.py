# -*- coding: utf-8 -*-
"""deploy/gpo-prep.ps1 against a scratch profile: a stub pyrevit and stub update.cmd. Windows only."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "gpo-prep.ps1"
POWERSHELL = shutil.which("powershell.exe") or shutil.which("powershell")

pytestmark = pytest.mark.skipif(os.name != "nt" or not POWERSHELL, reason="needs Windows PowerShell")

_PYREVIT_STUB = r"""@echo off
if /i "%1"=="env" ( type "%~dp0engine.txt" & exit /b 0 )
if /i "%1"=="attach" (
  >>"%~dp0attach.log" echo %*
  >"%~dp0engine.txt" echo master ^| Product: "2024.3.3 Update" ^| Engine: IPY342 (342^) ^| Path: "x"
  exit /b 0
)
exit /b 1
"""


def _case(tmp_path, ext_share):
    appdata, local, bin_dir = tmp_path / "ad", tmp_path / "la", tmp_path / "bin"
    main, pilot = tmp_path / "share" / "06_RevitMCP", tmp_path / "share" / "06_RevitMCP_pilot"
    for d in (appdata / "pyRevit", local / "RevitMCP", bin_dir, main / "install", pilot / "install"):
        d.mkdir(parents=True)
    (local / "RevitMCP" / "current-version.txt").write_text("old", encoding="ascii")
    registered = (main if ext_share == "main" else pilot) / "install" / ".." / "ext"
    ini = ('[core]\r\nuserextensions = ["{}"]\r\n[routes]\r\nenabled = true\r\n'
           .format(str(registered).replace("\\", "\\\\")))
    (appdata / "pyRevit" / "pyRevit_config.ini").write_bytes(ini.encode("utf-8"))
    (bin_dir / "engine.txt").write_text(
        'master | Product: "2024.3.3 Update" | Engine: IPY2712PR (2712) | Path: "x"\r\n', encoding="ascii")
    (bin_dir / "pyrevit.cmd").write_text(_PYREVIT_STUB.replace("\n", "\r\n"), encoding="ascii")
    marker = tmp_path / "update-ran.txt"
    for share in (main, pilot):
        (share / "install" / "update.cmd").write_text(
            '@echo off\r\n>>"{}" echo %~dp0\r\n'.format(marker), encoding="ascii")
    env = dict(os.environ, APPDATA=str(appdata), LOCALAPPDATA=str(local))
    result = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
         "-ShareRoot", str(main), "-PyRevit", str(bin_dir / "pyrevit.cmd")],
        env=env, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    log = (local / "RevitMCP" / "gpo-prep.log").read_text(encoding="utf-8-sig")
    return log, appdata, bin_dir, marker


def test_script_is_ascii_so_windows_powershell_reads_it():
    data = SCRIPT.read_bytes()
    assert all(b < 0x80 for b in data) and b"*" not in data


def test_main_share_user_gets_engine_host_and_update(tmp_path):
    if any(p.lower() == "revit.exe" for p in subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True).stdout.replace('"', "").split(",")):
        pytest.skip("Revit is running here; the script would correctly refuse to change anything")
    log, appdata, bin_dir, marker = _case(tmp_path, "main")
    assert (bin_dir / "attach.log").read_text().strip() == "attach master 342 --attached"
    assert "engine: now IPY342" in log
    ini = (appdata / "pyRevit" / "pyRevit_config.ini").read_text(encoding="utf-8")
    assert 'host = "127.0.0.1"' in ini and "port = 48884" in ini
    assert marker.exists() and "06_RevitMCP\\install" in marker.read_text()


def test_pilot_user_is_never_switched_to_the_main_payload(tmp_path):
    if any(p.lower() == "revit.exe" for p in subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True).stdout.replace('"', "").split(",")):
        pytest.skip("Revit is running here; the script would correctly refuse to change anything")
    log, _appdata, _bin, marker = _case(tmp_path, "pilot")
    assert "update: skipped; our extension is not registered from" in log
    assert not marker.exists()
