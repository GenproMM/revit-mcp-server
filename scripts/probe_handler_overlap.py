# -*- coding: utf-8 -*-
"""D-23 overlap probe: what does pyRevit's shared request handler do when two
requests overlap?

pyRevit Routes hands every route that takes ``doc`` to one shared external
event handler. This probe sends overlapping raw requests to ONE live Revit
instance and records whether each caller got its own answer.

It deliberately bypasses ``bridge.py``'s mutation lock: it talks to pyRevit
Routes with raw ``httpx`` so the overlap actually reaches Revit. Point it only
at a throwaway or untitled model (it POSTs to the unauthenticated
``/execute_code/``), and fully close and reopen Revit afterwards.

It lives in ``scripts/`` so it never ships in the deployed payload.

Phase M (mutation vs mutation): A sleeps on Revit's thread, B follows 0.5 s later.
Phase R (mutation vs read): C sleeps, then ``/list_levels/`` (shared handler) and
``/status/`` (HTTP thread) follow 0.5 s later.

Output tokens: CALLER, RUNS, STATUS_ELAPSED_S, OVERLAP_VERDICT, OVERLAP_REASONS,
D27_TRIGGER, OVERLAP_UNREACHABLE, OVERLAP_NO_DOCUMENT.
Exit codes: 0 experiment completed (the probe records, it does not gate),
2 nothing listening, 3 no active document.

Usage:
    uv run python scripts/probe_handler_overlap.py --port 48884 [--sleep 4.0]
"""
import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
import uuid

NO_MARKER = "no-marker"

# Headline verdict precedence, most serious first.
_PRECEDENCE = (
    "cross-wired-read",
    "cross-wired-mutation",
    "hang",
    "duplicate-run",
    "missing-run",
    "lost-output",
    "error",
)


def build_code(tag, run_id, log_path, sleep_s):
    """IronPython-3-safe source for /execute_code/, joined with a bare newline.

    No f-strings (Python 3.4 language level) and no carriage return (IronPython
    ``exec`` rejects CRLF). The code optionally sleeps on Revit's thread,
    appends its tag to ``log_path`` so the run count can be measured, and
    prints a marker that comes back in the response's ``output`` field.
    """
    lines = ["import time"]
    if sleep_s and sleep_s > 0:
        lines.append("time.sleep({})".format(float(sleep_s)))
    lines.append("with open({}, 'a') as _f:".format(repr(log_path)))
    lines.append("    _f.write({} + chr(10))".format(repr(tag)))
    lines.append('print("MARK-{}-{}")'.format(tag, run_id))
    return "\n".join(lines)


def marker_for(tag, run_id):
    return "MARK-{}-{}".format(tag, run_id)


def classify_phase(observations, markers, runs):
    """Return ``(verdict, reasons)`` for one phase.

    observations: dicts with name, kind (mutation|read), status, body,
        timed_out, error, elapsed.
    markers: mutation name -> the marker its code prints.
    runs: tag -> how many times its code ran (lines in the log file).
    """
    reasons = {}

    def flag(verdict, text):
        reasons.setdefault(verdict, []).append(text)

    has_read = any(o["kind"] == "read" for o in observations)

    for o in observations:
        name, body = o["name"], o["body"] or ""
        if o["timed_out"]:
            flag("hang", "{} timed out".format(name))
            continue
        if o["error"]:
            flag("error", "{} transport error: {}".format(name, o["error"]))
            continue
        if o["kind"] == "mutation":
            own = markers.get(name)
            for other_name, other_marker in markers.items():
                if other_name != name and other_marker in body:
                    flag(
                        "cross-wired-mutation",
                        "{} answered with {}'s marker".format(name, other_name),
                    )
            if o["status"] == 200 and (own is None or own not in body):
                if has_read:
                    flag(
                        "cross-wired-read",
                        "{} answered 200 without its own marker "
                        "(a read-shaped answer)".format(name),
                    )
                elif not any(m in body for m in markers.values()):
                    flag("lost-output", "{} answered 200 with no marker".format(name))
        else:
            held = [m for m in markers.values() if m in body]
            if held:
                flag(
                    "cross-wired-read",
                    "read {} returned a mutation marker ({})".format(name, held[0]),
                )

    for o in observations:
        if o["kind"] != "mutation":
            continue
        count = runs.get(o["name"])
        if count is None:
            continue
        if count > 1:
            flag("duplicate-run", "{} body ran {} times".format(o["name"], count))
        elif count == 0 and o["status"] == 200:
            flag("missing-run", "{} answered 200 but its body never ran".format(o["name"]))

    for verdict in _PRECEDENCE:
        if verdict in reasons:
            flat = []
            for key in _PRECEDENCE:
                flat.extend(reasons.get(key, []))
            return verdict, flat
    return "serialized", []


def d27_triggered(verdict_r):
    """D-27 fires for every read-phase verdict except ``serialized``."""
    return verdict_r != "serialized"


def count_runs(log_path, tags):
    """Lines per tag in the phase's log file (0 when the file is absent)."""
    counts = dict((t, 0) for t in tags)
    try:
        with open(log_path, "r") as handle:
            for line in handle:
                line = line.strip()
                if line in counts:
                    counts[line] += 1
    except (IOError, OSError):
        pass
    return counts


def _describe(body, markers):
    found = [m for m in markers.values() if m in (body or "")]
    if found:
        return ",".join(found)
    text = (body or "").replace("\r", " ").replace("\n", " ")
    return text[:60] if text else NO_MARKER


async def _request(client, httpx, name, kind, method, url, timeout, content=None, delay=0.0):
    if delay:
        await asyncio.sleep(delay)
    obs = {
        "name": name,
        "kind": kind,
        "status": None,
        "body": "",
        "timed_out": False,
        "error": None,
        "elapsed": 0.0,
    }
    started = time.monotonic()
    try:
        if method == "POST":
            resp = await client.post(
                url,
                content=content,
                headers={"Content-Type": "text/plain; charset=utf-8"},
                timeout=timeout,
            )
        else:
            resp = await client.get(url, timeout=timeout)
        obs["status"] = resp.status_code
        obs["body"] = resp.text
    except httpx.TimeoutException:
        obs["timed_out"] = True
        obs["error"] = "timeout"
    except httpx.HTTPError as exc:
        obs["error"] = "{}: {}".format(type(exc).__name__, exc)
    obs["elapsed"] = time.monotonic() - started
    return obs


def _payload(tag, run_id, log_path, sleep_s, description):
    code = build_code(tag, run_id, log_path, sleep_s)
    return json.dumps({"code": code, "description": description}).encode("utf-8")


def _report_phase(phase, observations, markers, runs):
    for o in observations:
        print(
            "CALLER phase={} name={} status={} elapsed={:.2f} got={}".format(
                phase, o["name"], o["status"], o["elapsed"], _describe(o["body"], markers)
            )
        )
    print("RUNS phase={} {}".format(phase, " ".join("{}={}".format(k, v) for k, v in sorted(runs.items()))))
    verdict, reasons = classify_phase(observations, markers, runs)
    print("OVERLAP_VERDICT phase={} verdict={}".format(phase, verdict))
    print("OVERLAP_REASONS phase={} {}".format(phase, "; ".join(reasons) if reasons else "none"))
    sys.stdout.flush()
    return verdict


async def _run(host, port, sleep_s):
    import httpx

    base = "http://{}:{}/revit_mcp".format(host, port)
    target = "{}:{}".format(host, port)
    per_request = sleep_s + 60

    async with httpx.AsyncClient(trust_env=False) as client:
        try:
            pre = await client.get(base + "/status/", timeout=5.0)
        except httpx.TransportError:
            print("OVERLAP_UNREACHABLE target={}".format(target))
            return 2
        if pre.status_code != 200:
            print("OVERLAP_NO_DOCUMENT target={} status={}".format(target, pre.status_code))
            return 3

        # Phase M: mutation vs mutation.
        run_m = uuid.uuid4().hex[:8]
        log_m = os.path.join(tempfile.gettempdir(), "rmcp_overlap_{}.log".format(run_m))
        markers_m = {"A": marker_for("A", run_m), "B": marker_for("B", run_m)}
        obs_m = await asyncio.gather(
            _request(client, httpx, "A", "mutation", "POST", base + "/execute_code/", per_request,
                     _payload("A", run_m, log_m, sleep_s, "overlap probe A")),
            _request(client, httpx, "B", "mutation", "POST", base + "/execute_code/", per_request,
                     _payload("B", run_m, log_m, 0, "overlap probe B"), delay=0.5),
        )
        runs_m = count_runs(log_m, ["A", "B"])
        _report_phase("M", obs_m, markers_m, runs_m)

        await asyncio.sleep(2.0)

        # Phase R: mutation vs read.
        run_r = uuid.uuid4().hex[:8]
        log_r = os.path.join(tempfile.gettempdir(), "rmcp_overlap_{}.log".format(run_r))
        markers_r = {"C": marker_for("C", run_r)}
        obs_r = await asyncio.gather(
            _request(client, httpx, "C", "mutation", "POST", base + "/execute_code/", per_request,
                     _payload("C", run_r, log_r, sleep_s, "overlap probe C")),
            _request(client, httpx, "levels", "read", "GET", base + "/list_levels/", per_request, delay=0.5),
            _request(client, httpx, "status", "read", "GET", base + "/status/", per_request, delay=0.5),
        )
        runs_r = count_runs(log_r, ["C"])
        verdict_r = _report_phase("R", obs_r, markers_r, runs_r)
        status_obs = [o for o in obs_r if o["name"] == "status"][0]
        print("STATUS_ELAPSED_S={:.2f}".format(status_obs["elapsed"]))
        print("D27_TRIGGER={}".format("yes" if d27_triggered(verdict_r) else "no"))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="D-23 handler-overlap probe (one live Revit instance)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=48884)
    parser.add_argument("--sleep", type=float, default=4.0, help="seconds the first caller holds Revit's thread")
    args = parser.parse_args(argv)
    return asyncio.run(_run(args.host, args.port, args.sleep))


if __name__ == "__main__":
    sys.exit(main())
