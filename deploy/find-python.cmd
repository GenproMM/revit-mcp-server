@echo off
rem ===========================================================================
rem  find-python.cmd -- locate the CPython interpreter that ships with pyRevit.
rem
rem  Sets, for the caller:
rem     MCP_PYEXE     full path to python.exe
rem     MCP_ENGINE    engine folder name, e.g. CPY3123
rem     MCP_ENGINE_OK 1 if that engine is new enough to run the payload, else 0
rem
rem  pyRevit bundles an embeddable CPython under its bin\ directory. WHERE it
rem  puts it depends on the pyRevit generation, and the fleet runs both:
rem
rem     pyRevit 4.8    bin\engines\CPY385      CPython 3.8   -- too old
rem     pyRevit 5.x    bin\cengines\CPY3123    CPython 3.12  -- supported
rem     pyRevit 6.5.3  bin\cengines\CPY3123    CPython 3.12  -- supported
rem
rem  4.8 dropped the "c" prefix, so probing cengines\ alone finds nothing on
rem  half the fleet and install.cmd then blames a missing pyRevit that is in
rem  fact installed. We probe both, and grade what we find: the payload wheels
rem  are built for CPython >=3.11 (pyproject.toml), so 3.8 cannot run it and
rem  the caller must say that plainly instead of failing later inside warm.py.
rem
rem  We reuse pyRevit's interpreter instead of shipping our own: pyRevit is a
rem  hard prerequisite anyway, and it keeps an unsigned interpreter out of the
rem  user profile.
rem
rem  Called (not executed) by build-payload.cmd, install.cmd and update.cmd,
rem  so it must not use setlocal.
rem ===========================================================================

rem An already-set MCP_PYEXE wins: that is the escape hatch for a build server
rem without pyRevit, where the engine has been copied in by hand.
if defined MCP_PYEXE if exist "%MCP_PYEXE%" goto :named

set "MCP_PYEXE="
set "MCP_ENGINE="
set "MCP_ENGINE_OK="

rem cengines\ (pyRevit 5+) is probed before engines\ (4.8) at every root, so a
rem machine carrying both layouts lands on the supported one.
for %%r in (
    "%APPDATA%\pyRevit-Master"
    "%APPDATA%\pyRevit"
    "%PROGRAMFILES%\pyRevit-Master"
    "%PROGRAMFILES%\pyRevit CLI"
    "%PROGRAMFILES(X86)%\pyRevit-Master"
) do (
    call :probe "%%~r\bin\cengines"
    call :probe "%%~r\bin\engines"
)

rem Last resort: derive it from wherever pyrevit.exe lives.
if not defined MCP_PYEXE for /f "usebackq delims=" %%p in (`where pyrevit 2^>nul`) do (
    if not defined MCP_PYEXE call :probe "%%~dpp cengines"
    if not defined MCP_PYEXE call :probe "%%~dpp engines"
)

goto :grade

:named
rem Name the engine after the folder the interpreter sits in, so the ABI
rem check against payload\ENGINE still means something.
for %%d in ("%MCP_PYEXE%\..") do set "MCP_ENGINE=%%~nxd"
goto :grade

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

:grade
rem Ask the interpreter itself rather than parsing the engine folder name --
rem CPY3123 is unambiguous only because the minor is two digits, and CPY385
rem is exactly the case where that guess goes wrong. Not via for /f with
rem backticks: that re-parses the quotes and mangles the -c string.
set "MCP_ENGINE_OK=0"
if not defined MCP_PYEXE exit /b 0
set "MCP_PYVERFILE=%TEMP%\mcp-engine-%RANDOM%.txt"
"%MCP_PYEXE%" -c "import sys;v=sys.version_info;f=open(r'%MCP_PYVERFILE%','w');f.write('%%d.%%d %%d' %% (v[0],v[1],1 if v[:2]>=(3,11) else 0));f.close()" 2>nul
set "MCP_PYVER="
if exist "%MCP_PYVERFILE%" set /p MCP_PYVER=<"%MCP_PYVERFILE%"
del "%MCP_PYVERFILE%" 2>nul
if not defined MCP_PYVER exit /b 0
for /f "tokens=1,2" %%a in ("%MCP_PYVER%") do (
    set "MCP_PYVER=%%a"
    set "MCP_ENGINE_OK=%%b"
)
exit /b 0
