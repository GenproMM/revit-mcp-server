# -*- coding: utf-8 -*-
"""
Read-only reader for the payload integrity manifest.

deploy/make_manifest.py writes <extension root>/_manifest.json at publish time.
check_integrity(root) reads it, hashes the files it lists plus every revit_mcp/*.py
actually present, and hands both to trust.evaluate_integrity for the verdict.

This module only ever opens files in mode "rb": it never writes, renames, deletes
or creates anything (INTG-03). It imports nothing from pyRevit, clr or the Revit
API, and it registers no routes, so startup.py's discovery imports it at load and
reports it as a helper. Phase 5 calls check_integrity once at extension load and
caches the answer; there is deliberately no caching or module state here.

hash_normalized is the single hashing function: the generator imports it from here,
so the two sides can never hash differently. Only CRLF is normalized to LF, so a
checkout with either line ending gives the same digest; every other byte, a BOM
included, counts.

An absence is reported as missing only after it was confirmed (WR-01): a share that
drops mid-check also answers ENOENT, so see unconfirmed_absences.

Dialect: IronPython 3 at the Python 3.4 language level (CLAUDE.md two-runtime rule).
"""

import errno
import hashlib
import json
import os

from .trust import (
    REASON_MANIFEST_MISSING,
    REASON_MANIFEST_UNREADABLE,
    REASON_READ_ERROR,
    evaluate_integrity,
    unverifiable,
    valid_manifest_path,
)

MANIFEST_NAME = "_manifest.json"
SCOPE_DIR = "revit_mcp"

_OK = "ok"
_ABSENT = "absent"
_ERROR = "error"


def hash_normalized(data):
    """SHA-256 hex digest of bytes with CRLF replaced by LF and nothing else changed.

    Live-verified 2026-10-23 (plan 03-08): the same CRLF-normalized hash in pyRevit's
    routes engine, py=3.4.2 (lf_ok, integrity_ok).
    """
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _read_bytes(path):
    """(status, data): ("ok", bytes), ("absent", None) for ENOENT, ("error", None) otherwise."""
    try:
        handle = open(path, "rb")
    except (IOError, OSError) as exc:
        if getattr(exc, "errno", None) == errno.ENOENT:
            return _ABSENT, None
        return _ERROR, None
    try:
        return _OK, handle.read()
    except (IOError, OSError):
        return _ERROR, None
    finally:
        handle.close()


def _list_names(path):
    """(status, names): ("ok", list), ("absent", []) for ENOENT, ("error", []) otherwise.

    The listing twin of _read_bytes.
    """
    try:
        names = os.listdir(path)
    except (IOError, OSError) as exc:
        if getattr(exc, "errno", None) == errno.ENOENT:
            return _ABSENT, []
        return _ERROR, []
    return _OK, names


def read_manifest(root):
    """(manifest, None) or (None, reason): manifest_missing, read_error, manifest_unreadable."""
    status, data = _read_bytes(os.path.join(root, MANIFEST_NAME))
    if status == _ABSENT:
        return None, REASON_MANIFEST_MISSING
    if status == _ERROR:
        return None, REASON_READ_ERROR
    try:
        manifest = json.loads(data.decode("utf-8"))
    except ValueError:  # UnicodeDecodeError and JSON errors both subclass ValueError
        return None, REASON_MANIFEST_UNREADABLE
    if manifest is None:  # a literal null is a present but unusable manifest
        return None, REASON_MANIFEST_UNREADABLE
    return manifest, None


def observe_tree(root, paths):
    """What is on disk: {"hashes", "present_py", "unreadable", "absent"} for the given paths.

    A listed path that does not exist is left out of hashes (the evaluation reads
    that as missing) and is added to absent; any other read failure is added to
    unreadable. present_py is every *.py file directly in revit_mcp/, sorted,
    '/'-separated. absent is sorted: every listed relative path that read as ENOENT,
    plus "revit_mcp/" when the listing of that directory read as ENOENT. An absence
    is only an observation here; check_integrity corroborates it before it counts.
    """
    hashes = {}
    unreadable = []
    absent = []
    for relpath in paths:
        status, data = _read_bytes(os.path.join(root, *relpath.split("/")))
        if status == _OK:
            hashes[relpath] = hash_normalized(data)
        elif status == _ABSENT:
            absent.append(relpath)
        else:
            unreadable.append(relpath)
    present = []
    scope = os.path.join(root, SCOPE_DIR)
    status, names = _list_names(scope)
    if status == _ABSENT:
        absent.append(SCOPE_DIR + "/")
    elif status == _ERROR:
        unreadable.append(SCOPE_DIR + "/")
    for name in names:
        if name.endswith(".py") and os.path.isfile(os.path.join(scope, name)):
            present.append(SCOPE_DIR + "/" + name)
    return {
        "hashes": hashes,
        "present_py": sorted(present),
        "unreadable": sorted(unreadable),
        "absent": sorted(absent),
    }


def unconfirmed_absences(root, manifest, absent):
    """The sorted subset of ``absent`` whose absence could not be confirmed.

    WR-01: on Windows, CPython maps ERROR_BAD_NETPATH (53) and ERROR_BAD_NET_NAME
    (67) to errno ENOENT, so a network share that drops after _manifest.json was
    read makes every later open() and listing answer "absent". Reported as missing
    files that is a false verified_mismatch, which Phase 5 caches at load and turns
    into a 423 on every mutation until Revit restarts. An observed absence therefore
    counts as missing only once it is confirmed, in a fixed order. First the manifest
    is read again and must parse to a manifest equal to the first one, which also
    shows the root is reachable again. If that fails nothing else is touched, so a
    dead share costs one extra open. Only then is each absent entry read again, and
    it must be absent again ("revit_mcp/" through its listing, a file through
    _read_bytes). Whatever the timing of a single outage, it is either still going at
    the manifest re-read, which fails, or already over, so the absent files read
    successfully the second time; both leave the absence unconfirmed. A real deletion
    on a reachable tree reproduces on the second read and stays a mismatch. There are
    no retries and no sleeps, and a matching tree costs no extra I/O.

    Residuals. Two separate outages, one covering the first scan and one covering the
    re-read of the absent entries with the share reachable for the manifest re-read in
    between, can still produce a false mismatch. And which errno IronPython 3.4, in
    pyRevit's routes engine, raises for a dropped network path was not observed live:
    only CPython on Windows was observed, ENOENT for open and for os.listdir. The
    verdict is unverifiable either way, because an ENOENT goes through this
    corroboration and any other errno or a non-OSError is read_error; that claim rests
    on reasoning plus CPython unit tests, not on a live observation.
    """
    again, reason = read_manifest(root)
    if reason is not None or again != manifest:
        return sorted(absent)
    unconfirmed = []
    for relpath in absent:
        if relpath == SCOPE_DIR + "/":
            status, _ = _list_names(os.path.join(root, SCOPE_DIR))
        else:
            status, _ = _read_bytes(os.path.join(root, *relpath.split("/")))
        if status != _ABSENT:
            unconfirmed.append(relpath)
    return sorted(unconfirmed)


def check_integrity(root):
    """The integrity verdict for the extension tree at ``root``; never raises.

    Returns the result dict of trust.evaluate_integrity. A manifest key that is not
    a safe relative path is never opened: the evaluation turns it into
    unverifiable/manifest_unreadable.
    """
    try:
        manifest, reason = read_manifest(root)
        if manifest is None:
            return unverifiable(reason)
        files = manifest.get("files") if isinstance(manifest, dict) else None
        paths = []
        if isinstance(files, dict):
            paths = sorted(k for k in files if valid_manifest_path(k))
        observed = observe_tree(root, paths)
        absent = observed.get("absent")
        if absent:
            observed["unconfirmed"] = unconfirmed_absences(root, manifest, absent)
        return evaluate_integrity(manifest, observed)
    except Exception:
        return unverifiable(REASON_READ_ERROR)
