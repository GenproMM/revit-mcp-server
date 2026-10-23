@echo off
rem ===========================================================================
rem  publish-extension.cmd -- RUN ON THE BUILD SERVER.
rem
rem  Publishes a PRUNED copy of the pyRevit half to <share>\ext\. Workstations
rem  load it straight from the UNC path, so this folder must contain only what
rem  Revit needs.
rem
rem  Publishing a copy (rather than pointing pyRevit at the git working copy)
rem  also removes the race where a user starts Revit in the middle of a git
rem  pull and loads a half-updated extension, and keeps .planning/, LLM.txt and
rem  the local Obsidian vault off a department-readable share.
rem
rem  Usage:  deploy\publish-extension.cmd
rem
rem  Publishing needs pyRevit's CPython (found by find-python.cmd) and git on
rem  this host: it stages the shared secret and writes the integrity manifest
rem  for exactly the files it publishes.
rem ===========================================================================
setlocal

set "REPO=%~dp0.."
call "%~dp0config.cmd" || exit /b 1
call "%~dp0find-python.cmd"
if not defined MCP_PYEXE (echo ERROR: pyRevit's CPython was not found; it is needed to stage the shared secret and write the integrity manifest. & exit /b 1)

set "DEST=%MCP_SHARE_ROOT%\ext\%MCP_EXT_NAME%"

echo(
echo === Publishing extension
echo     from: %REPO%
echo     to  : %DEST%
echo(

if not exist "%REPO%\startup.py" (echo ERROR: startup.py not found -- wrong repo root. & exit /b 1)
if not exist "%REPO%\extension.json" (echo ERROR: extension.json not found. & exit /b 1)

rem Guard the single highest-leverage deployment bug: with default_enabled
rem False, pyRevit writes disabled = true the first time it sees the extension
rem on a clean workstation and it never loads -- no error, no diagnostic.
findstr /i /c:"\"default_enabled\": \"True\"" "%REPO%\extension.json" >nul || (
    echo ERROR: extension.json must have "default_enabled": "True".
    echo        Otherwise the extension silently never loads on a clean machine.
    exit /b 1
)
findstr /i /c:"\"builtin\": \"False\"" "%REPO%\extension.json" >nul || (
    echo ERROR: extension.json must have "builtin": "False".
    echo        "True" sets private_repo and routes updates through the
    echo        private-repo path with username/password.
    exit /b 1
)

for /f "usebackq delims=" %%i in (`git -C "%REPO%" status --porcelain 2^>nul`) do (
    echo WARNING: uncommitted change -- %%i
)

rem ALLOW-list, not a deny-list. An exclude list silently leaks every new
rem directory someone drops in the repo root -- build output, notes, a scratch
rem folder -- onto a department-readable share and onto IronPython's sys.path.
rem The extension is exactly these four things; state them.
if exist "%DEST%" rmdir /s /q "%DEST%"
mkdir "%DEST%" || exit /b 1

copy /y "%REPO%\extension.json" "%DEST%\" >nul || exit /b 1
copy /y "%REPO%\startup.py"     "%DEST%\" >nul || exit /b 1
if exist "%REPO%\LICENSE" copy /y "%REPO%\LICENSE" "%DEST%\" >nul

rem /XJ: never follow junctions or the dev symlink in %%APPDATA%%\pyRevit\Extensions.
robocopy "%REPO%\revit_mcp" "%DEST%\revit_mcp" /E /XJ /XD __pycache__ /XF *.pyc _bridge_secret _manifest.json ^
    /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (echo ERROR: publish failed. & exit /b 1)

rem The fleet secret is staged AFTER the copy. The copy above excludes any
rem developer's own revit_mcp\_bridge_secret and any stray _manifest.json, so
rem only the fleet secret ships. secret_tool.py creates MCP_SECRET_FILE once
rem and never overwrites it; see config.cmd for the rotation procedure.
"%MCP_PYEXE%" "%~dp0secret_tool.py" stage --secret-file "%MCP_SECRET_FILE%" --dest "%DEST%\revit_mcp\_bridge_secret" || (echo ERROR: could not stage the shared secret. & exit /b 1)

rem The integrity manifest. The file list comes from git ls-files and the
rem hashes from the copies just published, written right after the copy so the
rem manifest describes what shipped. Nothing is copied into %%DEST%% after this
rem line. An untracked .py in revit_mcp stops the publish.
"%MCP_PYEXE%" "%~dp0make_manifest.py" --repo "%REPO%" --dest "%DEST%" || (echo ERROR: could not write the integrity manifest. & exit /b 1)

rem Keep the workstation-side scripts next to the payload they install.
rem "%%~dp0" ends in a backslash, which would escape the closing quote --
rem hence the trailing dot.
robocopy "%~dp0." "%MCP_SHARE_ROOT%\install" install.cmd update.cmd find-python.cmd check_routes_config.py /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (echo ERROR: could not publish installer scripts. & exit /b 1)

echo(
echo Published. Contents:
dir /b "%DEST%"
echo(
echo Users get this at their next Revit restart. No action required from them.
exit /b 0
