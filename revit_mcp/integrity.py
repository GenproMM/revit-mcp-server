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
    """SHA-256 hex digest of bytes with CRLF replaced by LF and nothing else changed."""
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
    """What is on disk: {"hashes", "present_py", "unreadable"} for the given relative paths.

    A listed path that does not exist is left out of hashes (the evaluation reads
    that as missing); any other read failure is added to unreadable. present_py is
    every *.py file directly in revit_mcp/, sorted, '/'-separated.
    """
    hashes = {}
    unreadable = []
    for relpath in paths:
        status, data = _read_bytes(os.path.join(root, *relpath.split("/")))
        if status == _OK:
            hashes[relpath] = hash_normalized(data)
        elif status == _ERROR:
            unreadable.append(relpath)
    present = []
    scope = os.path.join(root, SCOPE_DIR)
    try:
        names = os.listdir(scope)
    except (IOError, OSError) as exc:
        names = []
        if getattr(exc, "errno", None) != errno.ENOENT:
            unreadable.append(SCOPE_DIR + "/")
    for name in names:
        if name.endswith(".py") and os.path.isfile(os.path.join(scope, name)):
            present.append(SCOPE_DIR + "/" + name)
    return {
        "hashes": hashes,
        "present_py": sorted(present),
        "unreadable": sorted(unreadable),
    }


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
        return evaluate_integrity(manifest, observed)
    except Exception:
        return unverifiable(REASON_READ_ERROR)
