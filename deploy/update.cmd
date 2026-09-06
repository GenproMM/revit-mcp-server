@echo off
rem ===========================================================================
rem  update.cmd -- RUNS ON THE WORKSTATION, from the share.
rem
rem  Invoked by the per-user logon Scheduled Task and by the "Update RevitMCP"
rem  Start Menu shortcut. Mirrors a new payload into a NEW versioned folder and
rem  then re-points the `current` junction, so a running python.exe is never
rem  overwritten.
rem
rem  Deliberately silent and harmless when the share is unreachable.
rem ===========================================================================
setlocal enabledelayedexpansion

set "SHARE=%~dp0.."
set "DEST=%LOCALAPPDATA%\RevitMCP"
set "LOG=%DEST%\update.log"

rem The interpreter is pyRevit's own bundled CPython -- we ship no runtime.
call "%~dp0find-python.cmd"

rem /delayed: wait ~3 minutes before doing anything. Used by the autostart
rem shortcut, so the update does not contend with everything else launching at
rem logon and the network has time to come up. ping rather than timeout: it
rem does not need an interactive console.
if /i "%~1"=="/delayed" ping -n 181 127.0.0.1 >nul 2>&1

if not exist "%DEST%" mkdir "%DEST%" 2>nul

rem --- share reachable? ----------------------------------------------------
rem Note: a bare `if exist` on an unreachable UNC path blocks for the SMB
rem timeout rather than returning false, so this is the slowest line here.
rem That is acceptable in a background scheduled task; it is exactly why this
rem logic is NOT inside startup.py, where it would stall Revit's UI thread.
if not exist "%SHARE%\payload\VERSION" (
    call :log "share unreachable or payload missing; nothing to do"
    exit /b 0
)

set /p REMOTE=<"%SHARE%\payload\VERSION"
set "REMOTE=%REMOTE: =%"
if "%REMOTE%"=="" (call :log "remote VERSION is empty; aborting" & exit /b 0)

set "LOCAL="
if exist "%DEST%\current-version.txt" set /p LOCAL=<"%DEST%\current-version.txt"
rem Guard the strip: on a first install LOCAL is undefined, and %LOCAL: =% on
rem an undefined variable yields literal junk rather than an empty string.
if defined LOCAL set "LOCAL=%LOCAL: =%"

if /i "%REMOTE%"=="%LOCAL%" (
    if exist "%DEST%\current\app\server.py" (
        call :log "already at %REMOTE%"
        exit /b 0
    )
    call :log "version matches but install is broken; re-installing %REMOTE%"
)

rem No ">" in log text: cmd parses redirection inside the quoted argument to
rem CALL, which silently creates a stray file named after the version.
call :log "updating from %LOCAL% to %REMOTE%"

rem --- garbage collect FIRST, not last -------------------------------------
rem A running server still has its version directory open, so deletes
rem legitimately fail. Every failure here is "retry next time",
rem never an error.
rem
rem Target is "current + one previous". We are about to add %REMOTE%, so only
rem ONE existing version may survive -- hence GTR 1, not GTR 2. And never touch
rem the version the junction actually points at: the user may have rolled back
rem by hand, in which case it is not the newest directory.
set /a KEEP=0
for /f "usebackq delims=" %%d in (`dir /b /ad /o-d "%DEST%\versions" 2^>nul`) do (
    set /a KEEP+=1
    if !KEEP! GTR 1 if /i not "%%d"=="%REMOTE%" if /i not "%%d"=="%LOCAL%" (
        rmdir /s /q "%DEST%\versions\%%d" 2>nul && call :log "  gc: removed %%d"
    )
)

rem --- copy into a NEW folder ----------------------------------------------
set "NEW=%DEST%\versions\%REMOTE%"
if exist "%NEW%\.complete" del /q "%NEW%\.complete" 2>nul
mkdir "%NEW%" 2>nul

rem /XJ everywhere: robocopy and rmdir /s both traverse junctions
rem transparently, which is how a version store gets wiped by accident.
robocopy "%SHARE%\payload" "%NEW%" /MIR /XJ /R:2 /W:2 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    call :log "ERROR: copy failed; leaving the current install untouched"
    exit /b 1
)

if not exist "%NEW%\app\server.py" (
    call :log "ERROR: copied payload is incomplete; aborting"
    exit /b 1
)

rem The wheels under app\libs are ABI-pinned to one CPython minor version.
rem If pyRevit has shipped a different engine since the payload was built,
rem say so here rather than letting Hermes fail with an opaque ImportError.
if exist "%NEW%\ENGINE" if defined MCP_ENGINE (
    set /p WANT=<"%NEW%\ENGINE"
    if /i not "!WANT!"=="%MCP_ENGINE%" (
        call :log "WARNING: payload built for engine !WANT!, this machine has %MCP_ENGINE%"
    )
)

rem --- warm the new tree BEFORE it goes live -------------------------------
rem A fresh path means a cold file cache, no __pycache__ for app\, and a first
rem Defender scan of unsigned binaries. Without this the first Hermes session
rem after every update takes seconds and looks hung.
if defined MCP_PYEXE (
    "%MCP_PYEXE%" -m compileall -q "%NEW%\app" >nul 2>&1
    "%MCP_PYEXE%" "%NEW%\app\warm.py" >nul 2>&1
    if errorlevel 1 (
        call :log "ERROR: import check failed in the new version; not switching"
        exit /b 1
    )
) else (
    call :log "WARNING: pyRevit CPython not found; skipping the import check"
)
>"%NEW%\.complete" echo %REMOTE%

rem --- flip the junction ---------------------------------------------------
rem rmdir WITHOUT /s: with /s it would delete the TARGET's contents.
if exist "%DEST%\current" rmdir "%DEST%\current" 2>nul
if exist "%DEST%\current" (
    call :log "ERROR: could not release the current junction; not switching"
    exit /b 1
)
mklink /J "%DEST%\current" "%NEW%" >nul 2>&1
if errorlevel 1 (
    call :log "ERROR: mklink failed; run install.cmd to repair"
    exit /b 1
)

>"%DEST%\current-version.txt" echo %REMOTE%
call :log "now at %REMOTE%"

if /i "%~1"=="/interactive" (
    echo(
    echo RevitMCP updated to %REMOTE%.
    echo Restart Hermes Agent, or run /reload-mcp, to pick it up.
    echo(
    pause
)
exit /b 0

:log
for /f "usebackq delims=" %%t in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"`) do set "TS=%%t"
>>"%LOG%" echo [%TS%] %~1
if /i "%~1"=="" exit /b 0
echo %~1
exit /b 0
