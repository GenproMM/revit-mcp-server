# -*- coding: utf-8 -*-
"""Read-only config parsing in scratch cmd sessions; no deploy script is run."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(sys.platform != "win32", reason="cmd encoding is Windows-specific")
@pytest.mark.parametrize("codepage,endings", [(866, "lf"), (866, "crlf"), (65001, "crlf")])
def test_scratch_config_preserves_ascii_overrides_and_complete_parse(tmp_path, codepage, endings):
    raw = (ROOT / "deploy/config.cmd").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    raw = raw.replace(b"\r\n", b"\n")
    if endings == "crlf":
        raw = raw.replace(b"\n", b"\r\n")
    config = tmp_path / "config.cmd"
    config.write_bytes(raw)
    probe = tmp_path / "probe.py"
    probe.write_text("import json, os\nprint(json.dumps({k: os.environ.get(k) for k in "
                     "('MCP_SHARE_ROOT','MCP_SECRET_FILE','MCP_POLICY_FILE','MCP_EXT_NAME')}))\n",
                     encoding="ascii")
    env = dict(os.environ, MCP_SHARE_ROOT=str(tmp_path / "share"),
               MCP_SECRET_FILE=str(tmp_path / "secret"), MCP_POLICY_FILE=str(tmp_path / "policy.toml"))
    env.pop("MCP_EXT_NAME", None)
    command = 'chcp {} >nul && call "{}" && "{}" "{}"'.format(codepage, config, sys.executable, probe)
    # chcp changes the console shared by child processes. Give this probe its
    # own console so the CP65001 case cannot corrupt later scratch tests.
    result = subprocess.run("cmd.exe /d /c " + command, env=env, capture_output=True, timeout=15,
                            creationflags=subprocess.CREATE_NEW_CONSOLE)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    values = json.loads(result.stdout)
    for key in ("MCP_SHARE_ROOT", "MCP_SECRET_FILE", "MCP_POLICY_FILE"):
        assert values[key] == env[key]
    assert values["MCP_EXT_NAME"] == "revit-mcp-server.extension"
    assert not result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell stdin regression")
def test_windows_powershell_utf8_stdin_preserves_quotes_and_cyrillic(tmp_path):
    import shutil
    powershell = shutil.which("powershell.exe")
    if not powershell:
        pytest.skip("Windows PowerShell not installed")
    script = tmp_path / "stdin-probe.ps1"
    text = '''$OldEncoding = $OutputEncoding
$OldConsoleEncoding = [Console]::OutputEncoding
$OldPythonEncoding = $env:PYTHONIOENCODING
try {
  $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  [Console]::OutputEncoding = $OutputEncoding
  $env:PYTHONIOENCODING = 'utf-8'
  $Code = @'
import json
value = "Кириллица 'двойные' кавычки"
assert value == "Кириллица 'двойные' кавычки"
print(json.dumps(value, ensure_ascii=True))
'@
  $Code | & $env:PHASE7_TEST_PY -
  exit $LASTEXITCODE
} finally {
  $OutputEncoding = $OldEncoding
  [Console]::OutputEncoding = $OldConsoleEncoding
  $env:PYTHONIOENCODING = $OldPythonEncoding
}
'''
    # Windows PowerShell 5 needs a BOM for non-ASCII source in a .ps1 file.
    script.write_text(text, encoding="utf-8-sig")
    result = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-File", str(script)],
                            env=dict(os.environ, PHASE7_TEST_PY=sys.executable),
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert json.loads(result.stdout) == "Кириллица 'двойные' кавычки"


def test_operator_instruction_survives_chat_copy_and_covers_the_engine():
    raw = (ROOT / "deploy/START-HERE.txt").read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("utf-8-sig")
    # Markdown in a chat eats paired asterisks; every regex quantifier is spelled {0,}.
    assert "*" not in text
    for phrase in (r"\\srv-dfs\BIM\06_RevitMCP_pilot\install\install.cmd",
                   r"\RevitMCP-pilot-20261026-113138\ext", "extensions paths forget",
                   "2б. Движок IronPython 2.7", "attach master 342 --attached",
                   r"\\srv-dfs\BIM\06_RevitMCP_pilot\diag-secret.ps1"):
        assert phrase in text
    script = (ROOT / "deploy/diag-secret.ps1").read_bytes()
    assert all(b < 0x80 for b in script) and b"*" not in script  # Windows PowerShell 5.1 reads it as ANSI
    assert b"_bridge_secret" in script and b"Get-Content" not in script  # hashes only, never the content
