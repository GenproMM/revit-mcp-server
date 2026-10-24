@echo off
rem ===========================================================================
rem  publish-extension.cmd -- RUN ON THE BUILD SERVER.
rem
rem  Publishes a PRUNED copy of the pyRevit half to <share>\ext\. Workstations
rem  load it straight from the UNC path, so this folder must contain only what
rem  Revit needs.
rem
rem  The build never happens in <share>\ext\. It is assembled in
rem  <share>\ext-staging\, which no workstation has registered with pyRevit,
rem  and every gate runs there: the secret is staged, the integrity manifest is
rem  written, the manifest is checked against the staged files and the staged
rem  secret is compared with MCP_SECRET_FILE. Only a tree that passed all of
rem  that replaces the live one, by renaming: ext\ moves to ext-previous\ and
rem  ext-staging\ moves to ext\. A Revit that starts in the middle of a publish
rem  therefore loads either the whole old build or the whole new one, never a
rem  half-built folder (03-REVIEW WR-02), and a publish that fails anywhere
rem  before the rename leaves ext\ exactly as it was.
rem
rem  One previous version is kept in <share>\ext-previous\ so that
rem  deploy\rollback-extension.cmd can put it back without git or a rebuild.
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

rem ext, ext-staging and ext-previous are siblings under one share root, so
rem the moves below are renames on one volume.
set "LIVE=%MCP_SHARE_ROOT%\ext\%MCP_EXT_NAME%"
set "STAGE=%MCP_SHARE_ROOT%\ext-staging\%MCP_EXT_NAME%"
set "PREV=%MCP_SHARE_ROOT%\ext-previous\%MCP_EXT_NAME%"
rem Where the live build waits while the old previous build is discarded.
set "OUTGOING=%MCP_SHARE_ROOT%\ext-previous\%MCP_EXT_NAME%.outgoing"

echo(
echo === Publishing extension
echo     from   : %REPO%
echo     staging: %STAGE%
echo     live   : %LIVE%
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

rem An earlier publish that was cut off between its two renames leaves the live
rem build here. Do not guess: say so and stop before touching anything.
if exist "%OUTGOING%" goto :interrupted

rem ALLOW-list, not a deny-list. An exclude list silently leaks every new
rem directory someone drops in the repo root -- build output, notes, a scratch
rem folder -- onto a department-readable share and onto IronPython's sys.path.
rem The extension is exactly these four things; state them.
rem A STAGE left behind by a failed publish is removed first; it was never live.
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%" || (echo ERROR: could not create the staging folder. & exit /b 1)

copy /y "%REPO%\extension.json" "%STAGE%\" >nul || exit /b 1
copy /y "%REPO%\startup.py"     "%STAGE%\" >nul || exit /b 1
if exist "%REPO%\LICENSE" copy /y "%REPO%\LICENSE" "%STAGE%\" >nul

rem /XJ: never follow junctions or the dev symlink in %%APPDATA%%\pyRevit\Extensions.
robocopy "%REPO%\revit_mcp" "%STAGE%\revit_mcp" /E /XJ /XD __pycache__ /XF *.pyc _bridge_secret _manifest.json ^
    /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (echo ERROR: publish failed. & exit /b 1)

rem The fleet secret is staged AFTER the copy. The copy above excludes any
rem developer's own revit_mcp\_bridge_secret and any stray _manifest.json, so
rem only the fleet secret ships. secret_tool.py creates MCP_SECRET_FILE once
rem and never overwrites it; see config.cmd for the rotation procedure.
"%MCP_PYEXE%" "%~dp0secret_tool.py" stage --secret-file "%MCP_SECRET_FILE%" --dest "%STAGE%\revit_mcp\_bridge_secret" || (echo ERROR: could not stage the shared secret. & exit /b 1)

rem The integrity manifest. The file list comes from git ls-files and the
rem hashes from the staged copies, written right after the copy so the manifest
rem describes what will ship. Nothing is copied into the staged tree after this
rem line. An untracked .py in revit_mcp stops the publish.
"%MCP_PYEXE%" "%~dp0make_manifest.py" --repo "%REPO%" --dest "%STAGE%" || (echo ERROR: could not write the integrity manifest. & exit /b 1)

rem The gates. Both read the staged tree back from disk: the manifest must
rem verify as verified_match, and the staged secret must equal MCP_SECRET_FILE
rem byte for byte. Neither failure has touched the live folder.
"%MCP_PYEXE%" "%~dp0make_manifest.py" --check --dest "%STAGE%" || (echo ERROR: the staged extension does not match its integrity manifest; ext is unchanged. & exit /b 1)
"%MCP_PYEXE%" "%~dp0secret_tool.py" verify --secret-file "%MCP_SECRET_FILE%" --artifact "%STAGE%\revit_mcp\_bridge_secret" || (echo ERROR: the staged secret does not match MCP_SECRET_FILE; ext is unchanged. & exit /b 1)

rem The swap. The live folder moves aside FIRST: if a file in it is open (a
rem Revit is running from it) the rename fails here and nothing at all has
rem changed. Only then is the old previous build discarded.
if not exist "%MCP_SHARE_ROOT%\ext" mkdir "%MCP_SHARE_ROOT%\ext"
if not exist "%MCP_SHARE_ROOT%\ext-previous" mkdir "%MCP_SHARE_ROOT%\ext-previous"
if not exist "%LIVE%" goto :first_publish
move "%LIVE%" "%OUTGOING%" >nul 2>&1
if errorlevel 1 goto :live_busy
if exist "%PREV%" rmdir /s /q "%PREV%"
if exist "%PREV%" goto :prev_stuck
move "%OUTGOING%" "%PREV%" >nul 2>&1
if errorlevel 1 goto :prev_move_failed
:first_publish
move "%STAGE%" "%LIVE%" >nul 2>&1
if errorlevel 1 goto :stage_move_failed

rem Keep the workstation-side scripts next to the payload they install.
rem "%%~dp0" ends in a backslash, which would escape the closing quote --
rem hence the trailing dot.
robocopy "%~dp0." "%MCP_SHARE_ROOT%\install" install.cmd update.cmd find-python.cmd check_routes_config.py /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (echo ERROR: could not publish installer scripts. & exit /b 1)

echo(
echo Published. Contents:
dir /b "%LIVE%"
echo(
if exist "%PREV%" echo Previous version kept in %PREV%; roll back with deploy\rollback-extension.cmd
echo Users get this at their next Revit restart. No action required from them.
exit /b 0

:interrupted
echo ERROR: %OUTGOING% exists: an earlier publish was interrupted between its two renames.
echo        Nothing changed. If %LIVE% is missing, move that folder back to it,
echo        then delete the .outgoing folder and publish again.
exit /b 1

:live_busy
echo ERROR: the live extension could not be moved aside (is a file in it open?).
echo        Nothing changed; the new build is in %STAGE%.
exit /b 1

:prev_stuck
move "%OUTGOING%" "%LIVE%" >nul 2>&1
echo ERROR: the old previous version in %PREV% could not be removed.
echo        The live extension was put back. Nothing changed; the new build is in %STAGE%.
exit /b 1

:prev_move_failed
move "%OUTGOING%" "%LIVE%" >nul 2>&1
echo ERROR: the live extension could not be kept as the previous version.
echo        The live extension was put back; the new build is in %STAGE%.
exit /b 1

:stage_move_failed
if exist "%PREV%" move "%PREV%" "%LIVE%" >nul 2>&1
echo ERROR: the new build could not be moved into place.
echo        The previous version was restored to %LIVE%; the new build is in %STAGE%.
exit /b 1
