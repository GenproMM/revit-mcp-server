@echo off
rem ===========================================================================
rem  install.cmd -- RUNS ON THE WORKSTATION. Double-click from the share.
rem
rem      \\srv-dfs\BIM\RevitMCP\install\install.cmd
rem
rem  Everything lands in the user's profile. No admin rights, no UAC prompt.
rem
rem  Steps: mirror payload -> configure pyRevit (via pyrevit.exe only) ->
rem         register with Hermes -> schedule updates -> add a shortcut.
rem ===========================================================================
setlocal enabledelayedexpansion

set "SHARE=%~dp0.."
set "DEST=%LOCALAPPDATA%\RevitMCP"
set "EXTPATH=%SHARE%\ext"
rem Exported for the PowerShell blocks below (scheduled task + shortcut).
set "MCP_UPDATE=%SHARE%\install\update.cmd"

rem We ship no interpreter: pyRevit is a hard prerequisite for every user and
rem installs an embeddable CPython at bin\cengines\CPY*\python.exe. Reusing it
rem keeps an unsigned python.exe out of the user profile entirely.
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
    echo  Looked for bin\cengines\CPY*\python.exe under the usual pyRevit
    echo  install paths. pyRevit is required before installing RevitMCP.
    goto :fail
)

if not exist "%SHARE%\payload\VERSION" (
    echo  ERROR: cannot read %SHARE%\payload\VERSION
    echo  The share is unreachable, or the payload has not been built yet.
    goto :fail
)

rem --- 0. Hermes must be closed --------------------------------------------
rem Hermes reads config.yaml at startup and can write it back from its own
rem settings UI, which would silently discard our entry. Asking up front turns
rem a confusing half-finished install into one clear instruction.
:checkhermes
tasklist /FI "IMAGENAME eq hermes.exe" 2>nul | find /i "hermes.exe" >nul
if errorlevel 1 goto :hermesclosed
echo  Hermes Agent is running. Please close it completely, then press any key.
echo  ^(Its config file has to be edited while it is not holding it.^)
pause >nul
goto :checkhermes
:hermesclosed

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

rem An older copy in the user's own Extensions folder would be a second
rem extension calling routes.API("revit_mcp"); one silently wins. Rename
rem rather than delete -- reversible, and pyRevit ignores the new name.
for %%o in (revit-mcp-server.extension revit-mcp-python.extension mcp-server-for-revit-python.extension) do (
    if exist "%APPDATA%\pyRevit\Extensions\%%o" (
        echo        retiring old local copy: %%o
        move /y "%APPDATA%\pyRevit\Extensions\%%o" "%APPDATA%\pyRevit\Extensions\%%o.retired" >nul 2>&1
    )
)

"!PYREVIT!" configs routes enable >nul 2>&1
"!PYREVIT!" configs routes port 48884 >nul 2>&1
rem coreapi is deliberately NOT enabled: it exposes pyRevit's own API surface
rem for no benefit here.
rem Unregister the retired share root before adding the current one. The old
rem root sat inside \\srv-dfs\BIM\01_Ресурсы плагинов, a git repository owned by
rem the domain admins: pyRevit opens every registered extension path as a repo,
rem libgit2 climbs to that .git, and the ownership check throws
rem   "repository path '//srv-dfs/BIM/01_Ресурсы плагинов' is not owned by
rem    current user"
rem in the user's face. Adding the new path does not remove the old one, so a
rem machine installed before 2026-09-09 would keep the fault after moving.
rem
rem The path is never spelled out here. The folder above it is Cyrillic, cmd
rem parses this file in the console codepage (866 on a Russian Windows, and a
rem double-click always gives us that), so a literal would arrive mangled and
rem the forget would silently miss. Instead the exact string is read back from
rem pyRevit's own config -- where it is already correctly encoded -- and matched
rem on its ASCII segment. Reading that file is fine; only writing it by hand is
rem forbidden, and the forget itself still goes through pyrevit.exe.
rem "pyrevit extensions paths" with no argument prints usage, not the list,
rem which is why the config is the source here.
rem Drop this block once every workstation has re-run the installer.
rem The whole match-and-forget runs inside Python: the path must never round
rem trip through a cmd variable, because that is where the console codepage
rem would mangle it. Python holds the string and hands it straight to
rem pyrevit.exe as an argv element.
"%MCP_PYEXE%" "%~dp0forget_retired_path.py" "!PYREVIT!" 827_RevitMCP

"!PYREVIT!" extensions paths add "%EXTPATH%" >nul 2>&1

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
rem GenproMCP is retired by this install: this server supersedes it.
rem
rem NOT because of a route-name collision -- the comment that used to say so
rem was wrong. GenproMCP declares routes.API('genpro_mcp') and this extension
rem declares routes.API("revit_mcp"), so they would coexist on 48884 quite
rem happily. It is disabled because the decision is one server, one namespace,
rem one deployment channel -- not because it would break anything.
rem
rem KNOWN GAP, accepted deliberately: open_revit_server_model has not been
rem ported yet, so from this install until that port ships there is no way to
rem open an RSN:// model in the background with #_RVT_LINK worksets closed.
rem The BIM audit workflow opens those models by hand in the meantime. Close
rem the gap by porting the operation (ExternalEvent controller, dialog
rem watchdog, operation state machine) into revit_mcp/.
"!PYREVIT!" extensions disable GenproMCP >nul 2>&1
"!PYREVIT!" extensions disable GenproMCP.extension >nul 2>&1
echo        routes enabled on 48884, extension path registered, extension enabled
echo        GenproMCP disabled (superseded; see the note in install.cmd)

rem Read-only sanity check. Routes must stay on loopback: /execute_code/ is
rem unauthenticated arbitrary IronPython with full doc/DB/clr access, and
rem 127.0.0.1 is the only thing containing it.
findstr /i /c:"host = \"127.0.0.1\"" "%APPDATA%\pyRevit\pyRevit_config.ini" >nul 2>&1
if errorlevel 1 (
    echo(
    echo        WARNING: could not confirm [routes] host = "127.0.0.1".
    echo        Verify it before using this on a shared network. The route
    echo        /execute_code/ is unauthenticated remote code execution.
    echo(
)

rem --- 3. Hermes -----------------------------------------------------------
echo  [3/6] Registering the MCP server with Hermes Agent...
rem No PYTHONPATH: the embeddable interpreter ignores it. configure_hermes.py
rem puts its own install-libs\ on sys.path instead.
"%MCP_PYEXE%" "%DEST%\current\configure_hermes.py" --root "%DEST%\current" --python "%MCP_PYEXE%"
set "HRC=%errorlevel%"
if not "%HRC%"=="0" (
    echo(
    echo        Hermes config was NOT written automatically ^(see above^).
    echo        Everything else is installed; finish that step by hand.
    echo(
)

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
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
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
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
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
echo        then check http://localhost:48884/revit_mcp/status/ in a browser.
echo        It should return JSON.
echo(
echo     2. Restart Hermes Agent, or run /reload-mcp in it.
echo(
echo   Updates arrive on their own from now on: they are fetched a few minutes
echo   after you log on, and the Revit half refreshes whenever Revit restarts.
echo(
pause
exit /b 0

:fail
echo(
echo  Installation aborted. Nothing was left half-configured.
echo(
pause
exit /b 1
