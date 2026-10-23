@echo off
rem ===========================================================================
rem  install.cmd -- RUNS ON THE WORKSTATION. Double-click from the share.
rem
rem      \\srv-dfs\BIM\RevitMCP\install\install.cmd
rem
rem  Everything lands in the user's profile. No admin rights, no UAC prompt.
rem
rem  Steps: mirror payload -> check shared Routes -> register OUR extension ->
rem         show manual Hermes setup -> schedule updates -> add a shortcut.
rem ===========================================================================
setlocal enabledelayedexpansion

set "SHARE=%~dp0.."
set "DEST=%LOCALAPPDATA%\RevitMCP"
set "EXTPATH=%SHARE%\ext"
rem Exported for the PowerShell blocks below (scheduled task + shortcut).
set "MCP_UPDATE=%SHARE%\install\update.cmd"

rem We ship no interpreter: pyRevit is a hard prerequisite for every user and
rem installs an embeddable CPython under bin\. Reusing it keeps an unsigned
rem python.exe out of the user profile entirely. find-python.cmd knows both
rem layouts (4.8's bin\engines\, 5+'s bin\cengines\) and grades the version.
call "%~dp0find-python.cmd"

echo(
echo  ==========================================================
echo   RevitMCP -- installation
echo  ==========================================================
echo   share : %SHARE%
echo   local : %DEST%
echo(

if not defined MCP_PYEXE (
    echo  ERROR: pyRevit's CPython engine was not found.
    echo  Looked for bin\cengines\CPY*\python.exe and bin\engines\CPY*\python.exe
    echo  under the usual pyRevit install paths. pyRevit is required before
    echo  installing RevitMCP.
    goto :fail
)

rem pyRevit 4.8 ships CPython 3.8 (bin\engines\CPY385); the payload wheels are
rem built for 3.11+. Stop here with the actual reason rather than letting the
rem install run on to warm.py, which would fail with an opaque ImportError.
if not "%MCP_ENGINE_OK%"=="1" (
    echo  ERROR: pyRevit's CPython engine on this machine is too old.
    echo(
    echo    found  : %MCP_PYEXE%
    echo    engine : %MCP_ENGINE%  ^(CPython %MCP_PYVER%^)
    echo    needed : CPython 3.11 or newer
    echo(
    echo  This is pyRevit 4.8, which bundles CPython 3.8. RevitMCP needs the
    echo  interpreter that pyRevit 5.x and later ship ^(CPY3123, CPython 3.12^).
    echo  Update pyRevit, then run this installer again.
    goto :fail
)

if not exist "%SHARE%\payload\VERSION" (
    echo  ERROR: cannot read %SHARE%\payload\VERSION
    echo  The share is unreachable, or the payload has not been built yet.
    goto :fail
)

rem Hermes configuration is manual. Never rewrite an existing MCP entry here.

rem --- 1. payload ----------------------------------------------------------
echo  [1/6] Copying the server and its dependencies...
call "%~dp0update.cmd"
if errorlevel 1 goto :fail
if not exist "%DEST%\current\app\server.py" (
    echo  ERROR: the payload is incomplete after the copy.
    goto :fail
)

rem Verify the server actually starts under pyRevit's interpreter. This also
rem catches a pyRevit engine bump: the wheels under app\libs are ABI-pinned to
rem one CPython minor version.
"%MCP_PYEXE%" "%DEST%\current\app\warm.py" >nul 2>&1
if errorlevel 1 (
    echo(
    echo  ERROR: the server will not start under %MCP_ENGINE%.
    echo  The dependencies were built for the CPython recorded in
    echo  %SHARE%\payload\ENGINE. If pyRevit was updated, the payload has to
    echo  be rebuilt on the build server. Send that file and this message on.
    goto :fail
)
echo        ok, running on %MCP_ENGINE%

rem --- 2. pyRevit ----------------------------------------------------------
echo  [2/6] Configuring pyRevit...
set "PYREVIT="
for %%p in (
    "%APPDATA%\pyRevit-Master\bin\pyrevit.exe"
    "%APPDATA%\pyRevit\bin\pyrevit.exe"
    "%PROGRAMFILES%\pyRevit-Master\bin\pyrevit.exe"
    "%PROGRAMFILES%\pyRevit CLI\bin\pyrevit.exe"
) do if not defined PYREVIT if exist %%p set "PYREVIT=%%~p"
if not defined PYREVIT for /f "usebackq delims=" %%p in (`where pyrevit 2^>nul`) do if not defined PYREVIT set "PYREVIT=%%p"

if not defined PYREVIT (
    echo  ERROR: pyrevit.exe not found. Is pyRevit installed for this user?
    echo  Never edit pyRevit_config.ini by hand -- pyRevit rewrites it on every
    echo  Revit start and a malformed value breaks every extension.
    goto :fail
)
echo        cli: !PYREVIT!

rem Shared Routes belongs to every extension. Read settings, never rewrite them.
"%MCP_PYEXE%" "%~dp0check_routes_config.py"
if errorlevel 1 goto :fail

rem A same-name local installation needs an explicit migration decision.
rem Never move it or guess that another vendor's extension is obsolete.
if exist "%APPDATA%\pyRevit\Extensions\revit-mcp-server.extension" (
    echo  ERROR: an existing revit-mcp-server.extension needs manual path review.
    echo  No extension was moved or disabled. Ask the maintainer before migrating.
    goto :fail
)

"!PYREVIT!" extensions paths add "%EXTPATH%" >nul 2>&1
if errorlevel 1 goto :fail

rem Clear a stale disable. pyRevit reads default_enabled only the FIRST time it
rem sees an extension and keys the config section by folder name -- which has
rem never changed. So a machine that once saw a build with
rem default_enabled: "False" (or the GenproMCP-era extension) still carries
rem   [revit-mcp-server.extension]
rem   disabled = true
rem and this install would land correctly and never load: no error, no UI, no
rem routes, and /status/ answering "Route does not exist" from pyRevit's own
rem server. Verified on the first pilot machine. publish-extension.cmd guards
rem the other half of this -- what we publish -- but nothing else undoes what a
rem previous version already wrote here.
"!PYREVIT!" extensions enable revit-mcp-server >nul 2>&1
if errorlevel 1 goto :fail
echo        OUR extension path registered and enabled; other extensions unchanged

rem --- 3. Hermes -----------------------------------------------------------
echo  [3/6] Manual MCP registration required; Hermes config was not changed.
echo        Follow USER-GUIDE.md in Hermes UI. Do not replace another MCP entry.
echo        Keep its command, environment and enabled state unchanged.
echo        Use the shared Routes port reported above as OUR REVIT_PORT.

rem --- 4. automatic updates at logon ---------------------------------------
rem Task Scheduler is the better trigger (it can wait for the network), but on
rem a locked-down workstation registering a task is denied without admin --
rem in the root folder AND in a subfolder, even at RunLevel Limited. So try it,
rem and fall back to an autostart shortcut, which needs no special rights.
echo  [4/6] Setting up automatic updates at logon...
set "SCHEDULED="
schtasks /Create /TN "RevitMCP Update" /TR "cmd /c \"%MCP_UPDATE%\"" /SC ONLOGON /DELAY 0005:00 /RL LIMITED /F >nul 2>&1
if not errorlevel 1 set "SCHEDULED=1"

if defined SCHEDULED (
    echo        scheduled task created
    rem Remove any autostart shortcut from an earlier install so the update
    rem does not run twice per logon.
    del /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\RevitMCP Update.lnk" 2>nul
) else (
    echo        no rights for Task Scheduler; using the Startup folder instead
    powershell -NoProfile -Command ^
      "try {" ^
      "  $p = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\RevitMCP Update.lnk';" ^
      "  $w = New-Object -ComObject WScript.Shell;" ^
      "  $l = $w.CreateShortcut($p);" ^
      "  $l.TargetPath = 'cmd.exe';" ^
      "  $l.Arguments  = '/c \"' + $env:MCP_UPDATE + '\" /delayed';" ^
      "  $l.Description = 'Fetch the latest RevitMCP from the department share';" ^
      "  $l.WindowStyle = 7;" ^
      "  $l.Save();" ^
      "  Write-Host '       autostart entry created'" ^
      "} catch { Write-Host ('       WARNING: no automatic updates: ' + $_.Exception.Message) }"
)

rem --- 5. shortcut ---------------------------------------------------------
echo  [5/6] Adding a manual-update shortcut...
powershell -NoProfile -Command ^
  "try {" ^
  "  $dir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs';" ^
  "  $w = New-Object -ComObject WScript.Shell;" ^
  "  $l = $w.CreateShortcut((Join-Path $dir 'Update RevitMCP.lnk'));" ^
  "  $l.TargetPath = 'cmd.exe';" ^
  "  $l.Arguments  = '/c \"' + $env:MCP_UPDATE + '\" /interactive';" ^
  "  $l.Description = 'Fetch the latest RevitMCP from the department share';" ^
  "  $l.Save();" ^
  "  Write-Host '       added'" ^
  "} catch { Write-Host ('       WARNING: ' + $_.Exception.Message) }"

rem --- 6. done -------------------------------------------------------------
set /p V=<"%DEST%\current-version.txt"
echo(
echo  ==========================================================
echo   Installed. Version %V%
echo  ==========================================================
echo(
echo   Two things left, both one-time:
echo(
echo     1. Restart Revit completely ^(not pyRevit Reload^), open a model,
echo        then check http://127.0.0.1:PORT/genpro_revit_mcp/status/ in a browser.
echo        Replace PORT with the shared Routes port reported above.
echo        It should return JSON with api_name = genpro_revit_mcp.
echo(
echo     2. Register OUR server manually in Hermes UI, then reload its MCP tools.
echo(
echo   Updates arrive on their own from now on: they are fetched a few minutes
echo   after you log on, and the Revit half refreshes whenever Revit restarts.
echo(
pause
exit /b 0

:fail
echo(
echo  Installation stopped. Earlier completed steps may remain; see output above.
echo  No other extension was retired or disabled; shared Routes settings were not changed.
echo(
pause
exit /b 1
