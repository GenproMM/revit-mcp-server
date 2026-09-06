# Corporate deployment (closed network)

How this repository is delivered to a department that has no internet access on
its workstations, only an SMB share and a per-user pyRevit install.

## Why the MCP server cannot live on the server

`revit_mcp/` is a set of pyRevit Routes handlers running **inside the Revit
process**, serving `127.0.0.1:48884`. `main.py` fixes `BASE_URL` once at import
from `REVIT_HOST` (`main.py:21-23`), so one server process serves exactly one
Revit workstation. Pointing a central instance at users' machines would need
per-request host routing, Routes bound to `0.0.0.0` everywhere, and an auth
layer on both hops — while `/execute_code/` is unauthenticated arbitrary
IronPython with full `doc`/`DB`/`clr` access.

Both halves therefore run on the workstation. **The server is a distribution
and update point, not a runtime.**

## Layout

```
\\srv-dfs\BIM\RevitMCP\            (read-only for users)
├─ src\revit-mcp-server\           git working copy — yours only, in NO search path
├─ ext\revit-mcp-server.extension\ published, pruned; pyRevit loads this over UNC
├─ payload\                        mirrored to workstations
│   ├─ VERSION                     written LAST by build-payload.cmd
│   ├─ ENGINE                      pyRevit CPython the wheels were built for
│   ├─ app\                        main.py, tools\, server.py, libs\, gate.py, warm.py
│   ├─ install-libs\               ruamel.yaml, for the installer only
│   └─ configure_hermes.py
└─ install\  install.cmd, update.cmd, find-python.cmd

WORKSTATION (user profile only — no admin, no UAC)
├─ %LOCALAPPDATA%\RevitMCP\versions\<VERSION>\
├─ %LOCALAPPDATA%\RevitMCP\current  ──junction──> versions\<VERSION>
├─ %USERPROFILE%\.hermes\config.yaml       managed block under mcp_servers
├─ %APPDATA%\pyRevit\pyRevit_config.ini    written ONLY via pyrevit.exe
└─ update trigger at logon                 scheduled task, else Startup folder
```

## The interpreter: pyRevit's, not ours

We ship no Python. pyRevit is a hard prerequisite for every user, and it
installs an embeddable CPython at `bin\cengines\CPY<version>\python.exe`
(3.12.3 on the reference machine). Reusing it drops ~67 MB from the payload and,
more importantly, keeps an unsigned `python.exe` out of the user profile
entirely — which is exactly what AppLocker/WDAC default rules block.

Two consequences follow from it being the *embeddable* distribution, and both
are load-bearing:

- It ships a `python312._pth`, so `site` is disabled and **`PYTHONPATH` is
  ignored outright**. Dependencies cannot be injected by environment variable.
  `app\server.py` — the entry point Hermes launches — puts `app\libs` on
  `sys.path` itself and then hands over to `main.py`. `configure_hermes.py`
  does the same for its own `install-libs\`.
- Editing pyRevit's `._pth` instead would be worse: that file is shared with
  pyRevit's in-Revit CPython engine and is overwritten on every pyRevit update.

The trade-off is an ABI pin: the wheels under `app\libs` are built for one
CPython minor version. `build-payload.cmd` records which engine it targeted in
`payload\ENGINE`; `update.cmd` warns on a mismatch and `install.cmd` fails with
a clear message. **A pyRevit update that changes the CPython engine means
re-running `build-payload.cmd`** — that is the one maintenance obligation this
choice creates.

## Releasing

On the build server (Windows x64, PyPI or an internal mirror, **and pyRevit
installed** so the wheels match the fleet's interpreter):

```bat
cd \\srv-dfs\BIM\RevitMCP\src\revit-mcp-server
git pull

deploy\publish-extension.cmd     :: Revit half  -> live at each user's next Revit restart
deploy\build-payload.cmd         :: CPython half -> live at each user's next logon
```

Run whichever half you changed; running both is harmless. Neither requires any
action from users.

`build-payload.cmd` refuses to publish unless the bundled runtime imports
cleanly and `tests/test_init_latency.py` passes under the **bundled**
interpreter. `publish-extension.cmd` refuses to publish unless
`extension.json` has `default_enabled: "True"` and `builtin: "False"`.

## First-time install (per user)

The user double-clicks `\\srv-dfs\BIM\RevitMCP\install\install.cmd`, closes
Hermes when asked, then restarts Revit and Hermes. That is the whole procedure.

It copies the payload, verifies the interpreter actually runs, configures
pyRevit through `pyrevit.exe`, registers the server with Hermes, schedules
updates and adds a Start Menu shortcut.

## The update trigger

`install.cmd` tries `schtasks /Create` first — a scheduled task is the better
trigger because it can wait for the network. **On a locked-down workstation
this is denied without admin**, in the root task folder *and* in a subfolder,
even at `/RL LIMITED`. Verified on the reference machine: access denied for
`schtasks /Create` and for `Register-ScheduledTask` alike.

So the installer falls back to a shortcut in the per-user Startup folder
(`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`), which needs no
special rights. It launches minimised and runs `update.cmd /delayed`, which
waits ~3 minutes so the update does not contend with everything else starting
at logon and the network has time to come up.

Either way `update.cmd` exits silently and changes nothing when the share is
unreachable, so a laptop off the network simply updates at its next logon on
site. The installer removes the Startup shortcut if a scheduled task was
created, so the update never runs twice.

## Things that will bite you

**`extension.json` flags are load-bearing.** With `default_enabled: "False"`,
pyRevit writes `disabled = true` the first time it sees the extension on a
clean machine and it never loads — no error, no diagnostic. `builtin: "True"`
additionally sets `private_repo` and routes updates through the private-repo
path. `publish-extension.cmd` blocks on both.

**Never edit `pyRevit_config.ini` by hand.** pyRevit rewrites it on every Revit
start (`upgrade_user_config` then `save_changes`); `userextensions` is a JSON
array inside a TOML-ish file. A hand-appended line gets reformatted or dropped,
and a malformed value can wedge config loading for every extension. Use
`pyrevit extensions paths add`.

**The extension folder name is a contract.** pyRevit keys its config section by
the folder name. Renaming creates a fresh section that re-reads
`default_enabled`. Keep `revit-mcp-server.extension` forever.

**`rmdir /s` and `robocopy /MIR` traverse junctions transparently.** That is how
a version store gets wiped by accident. `update.cmd` releases the junction with
`rmdir` and no `/s`, and passes `/XJ` to every robocopy.

**Never point Hermes at a `.cmd` wrapper.** A batch file missing `@echo off`
echoes commands to stdout and corrupts the first JSON-RPC frame. Environment
goes in the `env:` block; Hermes runs `python.exe` directly.

**`REVIT_HOST` is pinned to `127.0.0.1`, not `localhost`.** Routes binds IPv4
only; on an IPv6-enabled image `localhost` resolves `::1` first and every call
eats a failed connect.

**Never launch `main.py` directly.** It is `server.py` that injects `sys.path`;
`python.exe main.py` under the embeddable interpreter dies on `import mcp`.
This is also why `tests/test_init_latency.py` cannot be used as-is against a
deployed install — it spawns `sys.executable main.py`. Use `app\gate.py`, which
measures the same thing through the real entry point.

**Extension loading is over UNC.** Cheap on a LAN (+0.2-1 s to Revit startup),
expensive over VPN: ~500-1000 SMB round trips of module probing, so tens of
seconds, and pyRevit's `startuplogtimeout = 10` will trip. If laptops appear,
mirror the extension (~370 KB) locally in `update.cmd` and repoint
`pyrevit extensions paths` — the machinery is already there.

**Use an ASCII, space-free share alias.** The Cyrillic path lands on IronPython
2.7's `sys.path`, in the TOML config and in cache keys, on a `ru` locale fleet.
Ask IT for a DFS link such as `\\srv-dfs\BIM\RevitMCP` and use only that.

**`/execute_code/` is unauthenticated RCE.** Fleet-wide rollout is fleet-wide
exposure; the only thing containing it is `[routes] host = "127.0.0.1"`.
`install.cmd` warns if it cannot confirm that. Get this reviewed before rollout.

## Diagnosing a broken workstation

| Symptom | Check |
|---|---|
| Hermes shows no Revit tools | Does `<pyrevit python.exe> %LOCALAPPDATA%\RevitMCP\current\app\warm.py` succeed? Managed block present in `~/.hermes/config.yaml`? |
| Tools present, every call errors | `http://localhost:48884/revit_mcp/status/` in a browser — empty means the extension did not load |
| Extension did not load | `[revit-mcp-server.extension] disabled` in `pyRevit_config.ini`; extension path registered; Revit fully restarted (Reload is not enough) |
| Server will not start | Compare `payload\ENGINE` with the machine's `bin\cengines\CPY*` — a pyRevit engine bump needs a payload rebuild |
| Stuck on an old version | `%LOCALAPPDATA%\RevitMCP\update.log`; run the "Update RevitMCP" shortcut by hand |

## Rollback

```bat
rmdir "%LOCALAPPDATA%\RevitMCP\current"
mklink /J "%LOCALAPPDATA%\RevitMCP\current" "%LOCALAPPDATA%\RevitMCP\versions\<older>"
echo <older>>"%LOCALAPPDATA%\RevitMCP\current-version.txt"
```

`rmdir` **without** `/s`. `update.cmd` will not garbage-collect the version the
junction points at, so a rollback survives until you deliberately move on.

## Starting Revit from the MCP server

`get_revit_process_status` and `start_revit` are the only tools that work while
Revit is closed — everything else goes through the Routes bridge, which lives
inside the Revit process. `start_revit` finds Revit under
`C:\Program Files\Autodesk\Revit *` (override with `REVIT_EXE`), launches it
detached with stdio pinned to DEVNULL — inheriting stdout would corrupt the MCP
stream — and polls the bridge until it answers.

A cold Revit start plus pyRevit load is 60-180 s, so the managed Hermes block
sets a generous per-server `timeout`. If the client still cuts the call off,
raise `timeout` there rather than shortening `wait_seconds`.
