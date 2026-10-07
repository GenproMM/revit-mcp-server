---
phase: 01-serialization-and-configurable-addressing
plan: 04
subsystem: transport
tags: [bench, handler-overlap, pyrevit, REVIT_PORT, two-instance, serialization, probe]

requires:
  - phase: 01-02
    provides: "bridge.py mutation lock and read-only allowlist (D-08) that the bench measures"
  - phase: 01-03
    provides: "get_revit_status MCP target line and tests/test_two_instance_targets.py harness"
provides:
  - "scripts/probe_handler_overlap.py: D-23 overlap probe (raw httpx, bypasses bridge.py) with unit-tested verdict classifier"
  - "Bench record: two Revit 2024.3 instances on 48884/48885 (staggered), two-instance harness TWO_INSTANCE_OK"
  - "Measured D-23 verdict: pyRevit's shared handler cross-wires overlapping requests (cross-wired-mutation and cross-wired-read), reproduced twice"
  - "User decisions: D-18 not triggered, D-27 d27-b (+ d27-c later), A5 a5-a"
affects: [01-05, phase-01-replan, phase-02]

actuals:
  tokens: 3650
  tasks: 3
  commits: 1
plan_head_before: ce79645fa5556629c7afbb179762f767236828bb

tech-stack:
  added: []
  patterns:
    - "Probe records, does not gate: exit 0 whenever the experiment completed, exit 2 unreachable, exit 3 no document"
    - "Pure verdict classifier (classify_phase) kept separate from the I/O so the experiment's interpretation is unit-tested without Revit"

key-files:
  created:
    - scripts/probe_handler_overlap.py
    - tests/unit/test_probe_handler_overlap.py
  modified: []

key-decisions:
  - "D-18 not triggered: staggered launch gave two Revit PIDs on two ports, one listener each"
  - "D-27 -> d27-b: lock every route that goes through pyRevit's handler, exempt only /status/ (/model_info/ stays locked because it was not measured); d27-c (Revit-side cross-process fix) added as a later follow-up; Phase 1 stops for re-planning"
  - "A5 -> a5-a: the two-instance harness counts as SC5 evidence; the one-session two-entry user model is NOT documented for users (standing constraint: one shared revit server entry, no copies); per-call target selection moves to Phase 2 (IDENT-01) with one lock per Revit target"

requirements-completed: []

coverage:
  - id: D1
    description: "D-23 probe classifier and generated IronPython code are unit-tested; offline run prints OVERLAP_UNREACHABLE and exits 2"
    requirement: "SER-01"
    verification:
      - kind: unit
        ref: "tests/unit/test_probe_handler_overlap.py (eight test_probe_ tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Two staggered Revit instances on distinct ports and PIDs; harness reports each entry's own target and document"
    requirement: "IDENT-05"
    verification:
      - kind: other
        ref: "live bench: Get-NetTCPConnection + /routes/sisters + tests/test_two_instance_targets.py -> TWO_INSTANCE_OK (see Bench record)"
        status: pass
    human_judgment: true
    rationale: "Live two-Revit evidence recorded by a human; acceptance of IDENT-05 and SC5 is deferred to the gap plans/verification because of the A5 deviation and the halted phase"
  - id: D3
    description: "D-23 verdict for plan 01-05 to cite"
    requirement: "SER-02"
    verification:
      - kind: other
        ref: "uv run python scripts/probe_handler_overlap.py --port 48884 (twice, identical verdicts: cross-wired-mutation, cross-wired-read, D27_TRIGGER=yes)"
        status: pass
    human_judgment: true
    rationale: "The measurement succeeded, but its consequence (SER-01/SER-02 meaning change) is a user decision taken at the checkpoint"

duration: 90min
completed: 2026-10-07
status: halted
---

# Phase 1 Plan 04: Two-Revit Bench and D-23 Overlap Probe Summary

**The live bench proved two staggered Revit instances take 48884 and 48885 (D-18 clear) and measured that pyRevit's shared handler cross-wires overlapping requests: the overlapped request answers 200 with the other request's output and its own body never runs, so the user chose d27-b and Phase 1 halts for re-planning.**

Status is `halted` (designed stop, #2830): the plan's Task 3 decision gate resolved to "record and stop the phase". Plan 01-05 depends on this plan and must not run as written.

## Performance

- **Duration:** about 90 min (executor Task 1, human bench, decisions, this continuation)
- **Started:** 2026-10-07T06:57:00Z (approximate; Task 1 committed 08:00 local)
- **Completed:** 2026-10-07T09:40:00Z
- **Tasks:** 3 (1 committed tracer, 1 human bench, 1 decision gate)
- **Files modified:** 2 (both created, both in Task 1)

## Accomplishments

- `scripts/probe_handler_overlap.py` runs a mutation-vs-mutation phase (M) and a mutation-vs-read phase (R) against one live instance using raw `httpx` (deliberately bypassing `bridge.py`), classifies each with `classify_phase`, and prints `OVERLAP_VERDICT` / `D27_TRIGGER`. Offline it prints `OVERLAP_UNREACHABLE` and exits 2 before any POST.
- Eight `test_probe_` unit tests pin the classifier (serialized, cross-wired-mutation, cross-wired-read, duplicate-run, hang, d27 trigger) and that generated code is IronPython-safe (no f-string, no CR).
- The live bench settled D-16 (staggered launch gives distinct ports), D-23 (handler overlap is unsafe) and exposed the A5 constraint.

## Task Commits

1. **Task 1: End-to-end overlap probe (tracer, tdd)** - `e44b4dd` (feat)
2. **Task 2: Live two-Revit bench** - checkpoint:human-verify, run by the human; no commit, evidence recorded below
3. **Task 3: Decision gate** - checkpoint:decision, answered by the user; recorded below

**Plan metadata:** committed separately (docs: complete plan)

## Bench record

### Environment and deviations from the bench script

- **pyRevit:** `pyrevit --version` -> `v6.5.3.26176+2017.b74f72a1a3b5ef3ebfe86482010f40c6c57ca04b` ("You have the latest version"). The bench ran on **6.5.3**, the version research read. **RESEARCH assumption A2 (fleet 6.5.5 behaves like 6.5.3) is NOT exercised by this bench.** The overlap verdict and the port allocation are proven for 6.5.3 only.
- **Revit:** BOTH instances are Autodesk Revit 2024.3.30 build 20250516_1515(x64), the same version twice, not two different versions as the plan's example suggested. A cross-version pair (for example 2024 plus 2027) is untested. Recorded as a deviation.
- **Step 6 (one assistant session, two entries): NOT performed**, by user constraint (see A5 below).
- **Step 8 (simultaneous launch): NOT performed.** Recorded as "not performed"; it is a finding, not acceptance (D-25), so SC5 does not depend on it.
- **Step 7 was run twice** back-to-back on instance A, with no Revit restart between runs. Verdicts were identical. The probe docstring asks for a full restart afterwards; the second run without one is a deviation, and the identical result shows the cross-wiring did not corrupt the handler's later behaviour in this sample.
- A later harness re-run from `C:\Users\Admin` failed only with "can't open file" because of the wrong working directory. Not a product failure; ignored.

### Step 2: staggered start (D-25 acceptance run)

The human started B only after A answered.

```
curl 48884 /revit_mcp/status/ -> 503
curl 48885 /revit_mcp/status/ -> 503      (Revit up, no document yet)
```

### Step 3: listener proof (D-16, A6)

```
LocalAddress LocalPort OwningProcess
127.0.0.1    48885     35780
127.0.0.1    48884     11088
```

`Get-Process -Id 35780` -> `Revit`; `Get-Process -Id 11088` -> `Revit`.

`curl.exe -s http://127.0.0.1:48884/routes/sisters`:

```
[{"host": "Autodesk Revit 2024.3.30 build: 20250516_1515(x64)", "process_id": 35780, "server_host": "127.0.0.1", "server_port": 48885, "version": "2024"}, {"host": "Autodesk Revit 2024.3.30 build: 20250516_1515(x64)", "process_id": 11088, "server_host": "127.0.0.1", "server_port": 48884, "version": "2024"}]
```

Exactly one listener per port, two distinct Revit PIDs: **D-18 NOT triggered.** **A6 confirmed** (`/routes/sisters` lists both servers).

### Step 4

A different model was opened in each instance (document names in the harness output below).

### Step 5: harness (D-17), run from the repo root

```
ENTRY label=revit-a port=48884 target=127.0.0.1:48884 status=active document=MCP_TEST_2_maggenda
ENTRY label=revit-b port=48885 target=127.0.0.1:48885 status=active document=Р_Низино_ПТОР_maggenda_отсоединено
LISTENERS port=48884 pids=11088
LISTENERS port=48885 pids=35780
TWO_INSTANCE_OK
```

### Step 6: one assistant session, two entries

**Not performed.** The user stated a standing product constraint: every user shares ONE `revit` MCP server entry and users cannot make copies of it; this must stay so. The two-entry user model of D-03 is not available to users. Treated as **A5 triggered** (see decision below).

### Step 7: D-23 overlap probe, instance A, port 48884 (run twice, identical verdicts)

Run 1:

```
CALLER phase=M name=A status=200 elapsed=4.39 got=MARK-A-719301e7
CALLER phase=M name=B status=200 elapsed=3.97 got=MARK-A-719301e7
RUNS phase=M A=1 B=0
OVERLAP_VERDICT phase=M verdict=cross-wired-mutation
OVERLAP_REASONS phase=M B answered with A's marker; B answered 200 but its body never ran
CALLER phase=R name=C status=200 elapsed=4.04 got=MARK-C-b157189d
CALLER phase=R name=levels status=200 elapsed=3.62 got=MARK-C-b157189d
CALLER phase=R name=status status=200 elapsed=0.01 got={"status": "active", "health": "healthy", "api_name": "revit
RUNS phase=R C=1
OVERLAP_VERDICT phase=R verdict=cross-wired-read
OVERLAP_REASONS phase=R read levels returned a mutation marker (MARK-C-b157189d)
STATUS_ELAPSED_S=0.01
D27_TRIGGER=yes
```

Run 2:

```
CALLER phase=M name=A status=200 elapsed=4.05 got=MARK-A-d1aeefeb
CALLER phase=M name=B status=200 elapsed=3.60 got=MARK-A-d1aeefeb
RUNS phase=M A=1 B=0
OVERLAP_VERDICT phase=M verdict=cross-wired-mutation
OVERLAP_REASONS phase=M B answered with A's marker; B answered 200 but its body never ran
CALLER phase=R name=C status=200 elapsed=4.10 got=MARK-C-bf4cc252
CALLER phase=R name=levels status=200 elapsed=3.63 got=MARK-C-bf4cc252
CALLER phase=R name=status status=200 elapsed=0.02 got={"status": "active", "health": "healthy", "api_name": "revit
RUNS phase=R C=1
OVERLAP_VERDICT phase=R verdict=cross-wired-read
OVERLAP_REASONS phase=R read levels returned a mutation marker (MARK-C-bf4cc252)
STATUS_ELAPSED_S=0.02
D27_TRIGGER=yes
```

**D-27 TRIGGERED.** Interpretation: when two requests overlap in pyRevit's shared handler, every waiting caller receives the response of the request that was executing; the overlapped request's own body never runs, yet it answers 200. A mutation can be silently lost while reported as success, and a read can return a mutation's output. `/status/` (served on the HTTP thread, off the handler) is unaffected (0.01 to 0.02 s while the handler was busy about 4 s). Consequences:

1. The D-08 read-only allowlist that bypasses `bridge.py`'s lock is unsafe as built; the measured `cross-wired-read` is exactly that case.
2. `bridge.py`'s lock is per server process, and each assistant session runs its own process, so overlapping sessions against one Revit are not serialized by any lock. Only a Revit-side fix closes that.
3. `/model_info/` was NOT measured.

The measured `levels` read (`/list_levels/`) waited about 3.6 s behind the 4 s mutation, so the read was not "fast" either: on this handler a read cannot be both unlocked and correct.

### Step 8: simultaneous launch

Not performed. Finding only, not acceptance (D-25).

### Step 9: IDENT-05 negative probes (orchestrator, same machine, no Revit needed)

```
REVIT_PORT=abc uv run python main.py </dev/null
  -> exit=2, stdout 0 bytes,
     stderr: "revit-mcp: refusing to start: REVIT_PORT must be an integer in 1..65535, got 'abc' (no fallback to the default port)"

uv run python tests/test_two_instance_targets.py --ports 48999,48998
  -> ENTRY label=revit-a port=48999 target=127.0.0.1:48999 status= document=
     ENTRY label=revit-b port=48998 target=127.0.0.1:48998 ...
     TWO_INSTANCE_FAIL            (expected: nothing listening), exit 1
```

Negative probes pass. Not run: whether the assistant client passes an empty `REVIT_PORT` through (optional step).

### Outcome lines

- **D-18: not triggered.** (Staggered launch gave PIDs 11088 -> 48884 and 35780 -> 48885.)
- **D-27: triggered. User chose `d27-b`** (plus `d27-c` later as a separate follow-up). Phase 1 stops for re-planning (`/gsd-plan-phase 1 --gaps`).
- **A5: triggered. User chose `a5-a`.** The harness counts as SC5 evidence; deviation from SC5's "one assistant session" wording recorded.

## Decisions Made

- **D-27 / d27-b, narrowed by the user.** Lock every route that goes through pyRevit's handler (API context). Exempt only `/status/`. The plan's d27-b wording also exempted `/model_info/`; the user keeps `/model_info/` locked because it was not measured. This is narrower than the plan text.
- **d27-c, later, separate.** A Revit-side fix for the cross-process overlap (the root cause in pyRevit's shared handler) is a follow-up item. Until it lands, overlapping sessions against one Revit can still cross-wire; this must be said honestly in docs.
- **A5 / a5-a.** The harness (step 5) counts as SC5 evidence. The two-entry scheme must NOT be documented for users (standing constraint: one shared `revit` server entry, no copies). Per-call target selection inside one server moves to Phase 2 (IDENT-01), with one lock per Revit target.
- **D-18 not triggered**, so D-02/D-03 (one MCP entry = one Revit instance chosen by port) stand as the transport model; they are no longer a user-facing story.

## Deviations from Plan

### Bench deviations (not code deviations)

**1. Same Revit version twice** (2024.3.30 x2) instead of two versions. Cross-version pair untested.
**2. pyRevit 6.5.3 on the bench**, not the fleet's 6.5.5. RESEARCH A2 unexercised.
**3. Step 6 not performed** (user constraint, A5 / a5-a). SC5's "one assistant session" is evidenced by the harness only.
**4. Step 8 not performed.** Launch-order finding absent.
**5. Probe run twice without a Revit restart between runs.** Same verdicts both times.

### Auto-fixed Issues

None. Task 1 was committed as planned; no product code changed in this plan (`git status --porcelain -- revit_mcp bridge.py deploy` empty). This continuation changed no code.

---

**Total deviations:** 5 bench deviations, 0 code deviations
**Impact on plan:** The deviations narrow what SC5 and A2 can claim; none of them hides the D-27 finding, which is the plan's most important output.

## Issues Encountered

- The D-23 verdict invalidated the read-only allowlist that plan 01-02 shipped (D-08), the thing this bench was designed to check (threat T-01-10, severity high). The mitigation planned for it (stop at the D-27 gate) worked.
- Plan 01-05 as written (honest serialization scope plus `REVIT_PORT` / two-entry docs) is now wrong on both counts.

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: unlocked-read-cross-wiring | bridge.py (read-only allowlist, plan 01-02) | T-01-10 materialised: an unlocked read overlapping a mutation returns the mutation's output; a mutation overlapped by anything is silently dropped while answering 200 |
| threat_flag: cross-process-overlap | pyRevit handler (not in repo) | No client-side lock serializes two assistant sessions against one Revit; closes only with d27-c |

## Requirements status

**SER-01, SER-02 and IDENT-05 are NOT marked complete by this plan.** Their acceptance is deferred to the gap plans and phase verification: SER-01 and SER-02 change meaning under d27-b (everything except `/status/` queues, so "reads are not blocked by a held queue" no longer holds for reads), and IDENT-05 and SC5 carry the A5 deviation. `requirements-completed` is therefore empty.

## Follow-up for re-planning (`/gsd-plan-phase 1 --gaps`)

1. **d27-b lock change.** `bridge.py` must take the mutation lock for every route that goes through pyRevit's handler; exempt only `/status/`. `/model_info/` stays locked (unmeasured).
2. **D-08 read-only allowlist: remove or revise.** As built it sends reads around the lock and is the measured `cross-wired-read`. Its unit tests and the plan 01-02 decision text need revising.
3. **SER-02 meaning change.** "Holding the queue does not block `/status/` and reading calls" becomes "does not block `/status/`" only. Update REQUIREMENTS.md SER-02, ROADMAP Phase 1 success criteria and any docs that promise concurrent reads. Slow reads will queue behind mutations.
4. **d27-c as a later item.** Revit-side fix for the cross-process overlap in pyRevit's shared handler (the lock is per server process; each assistant session runs its own). Add to the backlog or a later phase with a restart-cycle plan.
5. **Plan 01-05 must be rewritten.** No two-entry user docs (standing constraint: one shared `revit` server entry, users cannot copy it). Docs must state the honest scope: serialization applies within one server process, `/status/` is the only unlocked route, overlapping sessions can still cross-wire until d27-c. Keep `REVIT_PORT` documented only as a deployment/dev knob, not as a way for users to add entries.
6. **Per-call target selection to Phase 2 (IDENT-01)**, with **one lock per Revit target** (the lock must be keyed by target, not global, once one server can address several Revit instances).
7. **Open evidence gaps worth carrying into gap plans or verification:** pyRevit 6.5.5 (A2) was not benched; a cross-version Revit pair was not benched; `/model_info/` overlap behaviour was not measured; simultaneous launch was not run.
8. **Debug lead.** `.planning/debug/param-write-rolls-back.md` has an open "wrong process answered" hypothesis; the measured cross-wiring (a mutation answering 200 without its body running) is a second candidate mechanism for lost writes. Worth adding to that file's hypotheses by whoever owns it; this plan did not touch it.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Blocked.** Phase 1 is halted for re-planning after 01-04 (d27-b). Plan 01-05 must not run as written.
- Next action: `/gsd-plan-phase 1 --gaps`.

## Self-Check: PASSED

- `scripts/probe_handler_overlap.py` and `tests/unit/test_probe_handler_overlap.py` FOUND; commit `e44b4dd` FOUND.
- `git rev-list --count ce79645..HEAD` = 1 at SUMMARY write time (the docs commit follows separately).
- No product code changed by this continuation.

---
*Phase: 01-serialization-and-configurable-addressing*
*Completed: 2026-10-07*
