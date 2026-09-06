@echo off
rem ===========================================================================
rem  find-python.cmd -- locate the CPython interpreter that ships with pyRevit.
rem
rem  Sets, for the caller:
rem     MCP_PYEXE     full path to python.exe
rem     MCP_ENGINE    engine folder name, e.g. CPY3123
rem
rem  pyRevit bundles an embeddable CPython under bin\cengines\CPY<version>\.
rem  We reuse it instead of shipping our own: pyRevit is a hard prerequisite
rem  anyway, and it keeps an unsigned interpreter out of the user profile.
rem
rem  Called (not executed) by build-payload.cmd, install.cmd and update.cmd,
rem  so it must not use setlocal.
rem ===========================================================================

rem An already-set MCP_PYEXE wins: that is the escape hatch for a build server
rem without pyRevit, where the engine has been copied in by hand.
if defined MCP_PYEXE if exist "%MCP_PYEXE%" goto :named

set "MCP_PYEXE="
set "MCP_ENGINE="

for %%r in (
    "%APPDATA%\pyRevit-Master"
    "%APPDATA%\pyRevit"
    "%PROGRAMFILES%\pyRevit-Master"
    "%PROGRAMFILES%\pyRevit CLI"
    "%PROGRAMFILES(X86)%\pyRevit-Master"
) do call :probe "%%~r\bin\cengines"

rem Last resort: derive it from wherever pyrevit.exe lives.
if not defined MCP_PYEXE for /f "usebackq delims=" %%p in (`where pyrevit 2^>nul`) do (
    if not defined MCP_PYEXE call :probe "%%~dpp cengines"
)

exit /b 0

:named
rem Name the engine after the folder the interpreter sits in, so the ABI
rem check against payload\ENGINE still means something.
for %%d in ("%MCP_PYEXE%\..") do set "MCP_ENGINE=%%~nxd"
exit /b 0

:probe
rem Highest-numbered engine wins, so a pyRevit that ships two keeps the newer.
if not exist "%~1" exit /b 0
for /f "usebackq delims=" %%e in (`dir /b /ad /o-n "%~1\CPY*" 2^>nul`) do (
    if not defined MCP_PYEXE if exist "%~1\%%e\python.exe" (
        set "MCP_PYEXE=%~1\%%e\python.exe"
        set "MCP_ENGINE=%%e"
    )
)
exit /b 0
