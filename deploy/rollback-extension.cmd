@echo off
rem ===========================================================================
rem  rollback-extension.cmd -- RUN ON THE BUILD SERVER, by an administrator.
rem
rem  Puts the previous Revit-half build back in service with one rename:
rem
rem      <share>\ext\<name>           -> <share>\ext-rejected\<name>
rem      <share>\ext-previous\<name>  -> <share>\ext\<name>
rem
rem  It needs no git and no rebuild, and it does not need pyRevit's CPython.
rem  Workstations get the rolled-back extension at their next FULL Revit
rem  restart; a running Revit keeps what it loaded.
rem
rem  The payload does not need rolling back. A bridge that sends the _mcp
rem  envelope is harmless to the previous extension. Do NOT roll the payload
rem  back while the new extension is live: a bridge without the envelope has
rem  every mutation refused with 401 missing.
rem
rem  Only one previous version exists. A second rollback needs a republish
rem  from an older tag. There is no switch that turns the gates off: rollback
rem  is the previous build, never a disable flag.
rem
rem  Usage:  deploy\rollback-extension.cmd
rem ===========================================================================
setlocal

call "%~dp0config.cmd" || exit /b 1

set "LIVE=%MCP_SHARE_ROOT%\ext\%MCP_EXT_NAME%"
set "PREV=%MCP_SHARE_ROOT%\ext-previous\%MCP_EXT_NAME%"
set "REJECTED=%MCP_SHARE_ROOT%\ext-rejected\%MCP_EXT_NAME%"

echo(
echo === Rolling back extension
echo     live    : %LIVE%
echo     previous: %PREV%
echo     rejected: %REJECTED%
echo(

if not exist "%PREV%" goto :no_previous

rem The build being taken out of service is kept in ext-rejected for inspection.
rem Only one is kept: an older rejected build is removed first.
if exist "%REJECTED%" rmdir /s /q "%REJECTED%"
if exist "%REJECTED%" goto :rejected_stuck
if not exist "%MCP_SHARE_ROOT%\ext-rejected" mkdir "%MCP_SHARE_ROOT%\ext-rejected"

rem The live folder moves aside FIRST: if a file in it is open the rename
rem fails here and nothing has changed.
if not exist "%LIVE%" goto :put_back
move "%LIVE%" "%REJECTED%" >nul 2>&1
if errorlevel 1 goto :live_busy
:put_back
move "%PREV%" "%LIVE%" >nul 2>&1
if errorlevel 1 goto :prev_move_failed

echo Rolled back. %LIVE% is now the previous build;
echo the build that was live is in %REJECTED%.
echo Users get the rolled-back extension at their next full Revit restart.
exit /b 0

:no_previous
echo ERROR: there is nothing to roll back to: %PREV% does not exist.
echo        Nothing changed.
exit /b 1

:rejected_stuck
echo ERROR: the older rejected build in %REJECTED% could not be removed.
echo        Nothing changed.
exit /b 1

:live_busy
echo ERROR: the live extension could not be moved aside (is a file in it open?).
echo        Nothing changed.
exit /b 1

:prev_move_failed
move "%REJECTED%" "%LIVE%" >nul 2>&1
echo ERROR: the previous version could not be moved into place.
echo        The build that was live was put back. Nothing changed.
exit /b 1
