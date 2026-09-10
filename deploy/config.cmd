@echo off
rem ===========================================================================
rem  Deployment configuration. EDIT THIS FILE ONCE on the build server.
rem
rem  Each value can be overridden from the environment, which is how the
rem  release scripts are staged against a scratch directory before they touch
rem  the real share.
rem
rem  MCP_SHARE_ROOT is the folder that holds src\, ext\, payload\ and install\.
rem  It is ASCII and space-free on purpose: this string ends up on IronPython's
rem  sys.path, in a TOML config and in cache keys, on a fleet running
rem  user_locale = "ru".
rem
rem  It must also stay OUTSIDE any git repository. pyRevit walks every
rem  registered extension path and opens each one as a git repo; libgit2 climbs
rem  the directory tree looking for .git and checks whatever it finds for
rem  ownership. The previous root lived under \\srv-dfs\BIM\01_Ресурсы плагинов,
rem  whose hidden .git belongs to the domain admins, so every workstation got
rem      Exception: repository path '//srv-dfs/BIM/01_Ресурсы плагинов'
rem      is not owned by current user
rem  on the pyRevit Update button. Publishing a .git-free tree of our own does
rem  not help -- the climb reaches the parent regardless. Keep this path out of
rem  a repository and the whole class of failure cannot happen.
rem ===========================================================================

if not defined MCP_SHARE_ROOT set "MCP_SHARE_ROOT=\\srv-dfs\BIM\06_RevitMCP"

rem Previous root, retired 2026-09-09 (it sat inside a git repo -- see above).
rem install.cmd unregisters this one from pyRevit on every run; do not delete
rem the line until every workstation has re-run the installer.
set "MCP_SHARE_ROOT_RETIRED=\\srv-dfs\BIM\01_Ресурсы плагинов\827_RevitMCP"

rem No Python version to set: we build against the CPython that pyRevit ships,
rem so pyRevit must be installed on this build server too. If it is not, point
rem MCP_PYEXE at a copy of the fleet's bin\cengines\CPY*\python.exe before
rem running the build -- the wheels must match the interpreter users will run.
rem   set "MCP_PYEXE=D:\revit-mcp-build\CPY3123\python.exe"

rem Extension folder name. This is a DEPLOYMENT CONTRACT: pyRevit keys its
rem config section by the folder name. Renaming it creates a fresh section
rem that re-reads default_enabled. Never change it.
if not defined MCP_EXT_NAME set "MCP_EXT_NAME=revit-mcp-server.extension"
