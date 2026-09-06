@echo off
rem ===========================================================================
rem  Deployment configuration. EDIT THIS FILE ONCE on the build server.
rem
rem  Each value can be overridden from the environment, which is how the
rem  release scripts are staged against a scratch directory before they touch
rem  the real share.
rem
rem  MCP_SHARE_ROOT is the folder that holds src\, ext\, payload\ and install\.
rem  Prefer an ASCII, space-free alias (DFS link or a second share name) over
rem  the Cyrillic path: that string ends up on IronPython 2.7's sys.path, in a
rem  TOML config and in cache keys, on a fleet running user_locale = "ru".
rem ===========================================================================

if not defined MCP_SHARE_ROOT set "MCP_SHARE_ROOT=\\srv-dfs\BIM\01_Ресурсы плагинов\827_RevitMCP"

rem Fallback if the ASCII alias does not exist yet:
rem set "MCP_SHARE_ROOT=\\srv-dfs\BIM\01_Ресурсы плагинов\827_RevitMCP"

rem No Python version to set: we build against the CPython that pyRevit ships,
rem so pyRevit must be installed on this build server too. If it is not, point
rem MCP_PYEXE at a copy of the fleet's bin\cengines\CPY*\python.exe before
rem running the build -- the wheels must match the interpreter users will run.
rem   set "MCP_PYEXE=D:\revit-mcp-build\CPY3123\python.exe"

rem Extension folder name. This is a DEPLOYMENT CONTRACT: pyRevit keys its
rem config section by the folder name. Renaming it creates a fresh section
rem that re-reads default_enabled. Never change it.
if not defined MCP_EXT_NAME set "MCP_EXT_NAME=revit-mcp-server.extension"
