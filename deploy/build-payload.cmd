@echo off
rem ===========================================================================
rem  build-payload.cmd -- RUN ON THE BUILD SERVER (Windows x64, PyPI access).
rem
rem  Produces <share>\payload\ : the CPython half of the server plus its
rem  dependencies, built against the CPython that pyRevit itself ships.
rem
rem  We do NOT bundle an interpreter. pyRevit is a hard prerequisite for every
rem  user, and it installs an embeddable CPython at
rem  bin\cengines\CPY<version>\python.exe. Reusing it drops ~67 MB from the
rem  payload and keeps an unsigned python.exe out of the user profile.
rem
rem  The trade-off: the wheels are ABI-pinned to that CPython minor version.
rem  A pyRevit update that changes the engine requires re-running this script.
rem  The engine tag is recorded in payload\ENGINE and checked on the workstation.
rem
rem  Usage:  deploy\build-payload.cmd
rem ===========================================================================
setlocal enabledelayedexpansion

set "REPO=%~dp0.."
call "%~dp0config.cmd" || exit /b 1
call "%~dp0find-python.cmd"

where uv >nul 2>&1 || (echo ERROR: uv not found on PATH. & exit /b 1)

if not defined MCP_PYEXE (
    echo ERROR: could not find pyRevit's CPython engine on this machine.
    echo        Looked for bin\cengines\CPY*\python.exe and bin\engines\CPY*\python.exe
    echo        under the usual pyRevit install locations. pyRevit must be
    echo        installed on the build host so the wheels are built for the same
    echo        interpreter the fleet runs.
    exit /b 1
)

rem Never build a payload against pyRevit 4.8's CPython 3.8: the result would
rem install nowhere. pyproject.toml requires 3.11+.
if not "%MCP_ENGINE_OK%"=="1" (
    echo ERROR: %MCP_ENGINE% is CPython %MCP_PYVER%; the payload requires 3.11 or newer.
    echo        %MCP_PYEXE%
    echo        Build on a host running pyRevit 5.x or later.
    exit /b 1
)

rem find-python.cmd already asked the interpreter itself (parsing the engine
rem folder name is unsafe -- CPY3123 is unambiguous only because the minor is
rem two digits, and CPY385 is exactly where that guess goes wrong).
set "PYVER=%MCP_PYVER%"
if not defined PYVER (echo ERROR: could not query the pyRevit interpreter. & exit /b 1)

set "OUT=%MCP_SHARE_ROOT%\payload"

rem Staging is LOCAL, deliberately. The acceptance gate below spawns the server
rem out of %BUILD%, and from the share that measures SMB round trips for ~1000
rem module files instead of the server's cold start: 2.30 s over UNC against
rem 0.91 s on local disk for the same commit, with a 2.0 s limit. Workstations
rem run the payload from %LOCALAPPDATA%, never from the share, so local staging
rem is also the honest measurement. It lets uv hardlink from its cache too.
if not defined MCP_BUILD_DIR set "MCP_BUILD_DIR=%TEMP%\revitmcp-payload.build"
set "BUILD=%MCP_BUILD_DIR%"

rem --- version stamp -------------------------------------------------------
rem PowerShell, not %date% -- cmd's date format is locale-dependent and this
rem fleet runs a ru locale.
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "Get-Date -Format yyyy.MM.dd-HHmm"`) do set "STAMP=%%i"
for /f "usebackq delims=" %%i in (`git -C "%REPO%" rev-parse --short HEAD 2^>nul`) do set "SHA=%%i"
if defined SHA (set "VERSION=%STAMP%.%SHA%") else (set "VERSION=%STAMP%")

echo(
echo === Building payload %VERSION%
echo     repo   : %REPO%
echo     python : %MCP_PYEXE%
echo     engine : %MCP_ENGINE%  (CPython %PYVER%)
echo     staging: %BUILD%
echo     output : %OUT%
echo(

for /f "usebackq delims=" %%i in (`git -C "%REPO%" status --porcelain 2^>nul`) do (
    echo WARNING: uncommitted change -- %%i
    set "DIRTY=1"
)
if defined DIRTY echo WARNING: building from a dirty tree; the VERSION sha will not describe it.& echo(

if exist "%BUILD%" rmdir /s /q "%BUILD%"
mkdir "%BUILD%" || exit /b 1

rem --- 1. dependencies -----------------------------------------------------
rem From uv.lock, never requirements.txt (CLAUDE.md calls it a stale mirror).
echo [1/5] Resolving dependencies from uv.lock...
uv export --project "%REPO%" --frozen --no-dev --no-emit-project --format requirements.txt -o "%BUILD%\requirements.lock.txt" >nul || exit /b 1

echo [2/5] Installing dependencies for CPython %PYVER%...
uv pip install --python "%MCP_PYEXE%" --target "%BUILD%\libs" ^
    --python-platform windows --python-version %PYVER% --compile-bytecode ^
    -r "%BUILD%\requirements.lock.txt" || exit /b 1

rem ruamel.yaml is needed only by the installer, so it stays out of the
rem server's import path.
echo       + install-libs (ruamel.yaml, for configure_hermes.py)
uv export --project "%REPO%" --frozen --only-group deploy --no-emit-project --format requirements.txt -o "%BUILD%\requirements.deploy.txt" >nul || exit /b 1
uv pip install --python "%MCP_PYEXE%" --target "%BUILD%\install-libs" ^
    --python-platform windows --python-version %PYVER% --compile-bytecode ^
    -r "%BUILD%\requirements.deploy.txt" || exit /b 1

rem --- 2. application ------------------------------------------------------
echo [3/5] Staging application files...
mkdir "%BUILD%\app" 2>nul
move /y "%BUILD%\libs" "%BUILD%\app\libs" >nul || exit /b 1
copy /y "%REPO%\main.py"            "%BUILD%\app\" >nul || exit /b 1
copy /y "%~dp0server.py"            "%BUILD%\app\" >nul || exit /b 1
copy /y "%~dp0gate.py"              "%BUILD%\app\" >nul || exit /b 1
copy /y "%~dp0warm.py"              "%BUILD%\app\" >nul || exit /b 1
copy /y "%~dp0configure_hermes.py"  "%BUILD%\"    >nul || exit /b 1
robocopy "%REPO%\tools" "%BUILD%\app\tools" /E /XJ /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 exit /b 1
robocopy "%REPO%\tests" "%BUILD%\app\tests" /E /XJ /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 exit /b 1

>"%BUILD%\ENGINE" echo %MCP_ENGINE%
"%MCP_PYEXE%" -m compileall -q "%BUILD%\app" >nul 2>&1

rem --- 3. verify BEFORE publishing ----------------------------------------
echo [4/5] Verifying against the real entry point...
"%MCP_PYEXE%" "%BUILD%\app\gate.py" || (echo ERROR: acceptance gate failed. & exit /b 1)
"%MCP_PYEXE%" -c "import sys;sys.path.insert(0,r'%BUILD%\install-libs');import ruamel.yaml;print('      ruamel OK')" || (echo ERROR: install-libs check failed. & exit /b 1)

rem --- 4. publish; VERSION written LAST ------------------------------------
rem update.cmd on the workstation reads VERSION first, so writing it last
rem guarantees nobody mirrors a half-published payload.
echo [5/5] Publishing to %OUT% ...
robocopy "%BUILD%" "%OUT%" /MIR /XJ /XF VERSION /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (echo ERROR: publish failed. & exit /b 1)
>"%OUT%\VERSION" echo %VERSION%
rmdir /s /q "%BUILD%"

echo(
echo Done. payload %VERSION% published for engine %MCP_ENGINE% (CPython %PYVER%).
echo Workstations pick it up at next logon, or via the "Update RevitMCP" shortcut.
exit /b 0
