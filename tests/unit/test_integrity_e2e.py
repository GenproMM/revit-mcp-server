# -*- coding: utf-8 -*-
"""Tracer: payload integrity end to end, from a git checkout to a visible 423.

A temporary git repository is the build checkout and a separate temporary
directory is the published copy (DEST). deploy/make_manifest.py writes
DEST/_manifest.json from ``git ls-files`` and the hashes of the DEST copies,
revit_mcp.integrity.check_integrity(DEST) reads it back, and a mismatch becomes
the HTTP 423 body that travels through the unchanged bridge._send and
tools.utils.format_response. Needs no Revit. Everything is written under
pytest's tmp_path, never inside this repository.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess

import httpx
import pytest

import bridge
from revit_mcp import integrity, trust
from tools.utils import format_response

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GENERATOR = os.path.join(REPO_ROOT, "deploy", "make_manifest.py")

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not on PATH"
)

TRACKED = [
    "extension.json",
    "revit_mcp/__init__.py",
    "revit_mcp/alpha.py",
    "revit_mcp/beta.py",
    "startup.py",
]

FILES = {
    "startup.py": u"# -*- coding: utf-8 -*-\nSTARTUP = 1\n",
    "extension.json": u'{"name": "genpro_revit_mcp"}\n',
    "revit_mcp/__init__.py": u"# -*- coding: utf-8 -*-\n",
    "revit_mcp/alpha.py": u"# -*- coding: utf-8 -*-\nNAME = u'Стена'\n",
    "revit_mcp/beta.py": u"# -*- coding: utf-8 -*-\nBETA = 2\n",
}


@pytest.fixture(scope="module")
def anyio_backend():
    # trio is not installed and must not be added: pin asyncio.
    return "asyncio"


@pytest.fixture(scope="module")
def make_manifest():
    spec = importlib.util.spec_from_file_location("make_manifest_under_test", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(root, relpath, text):
    path = os.path.join(root, *relpath.split("/"))
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
    return path


def _git(repo, *args):
    return subprocess.run(
        ["git"] + list(args), cwd=repo, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.decode("utf-8").strip()


@pytest.fixture()
def built(tmp_path, make_manifest):
    """(repo, dest, manifest dict): a committed repo and a published copy with a manifest."""
    repo = str(tmp_path / "repo")
    dest = str(tmp_path / "dest")
    os.makedirs(repo)
    os.makedirs(dest)
    for relpath, text in FILES.items():
        _write(repo, relpath, text)
        _write(dest, relpath, text)
    # Published-tree noise that must never be listed.
    _write(dest, "revit_mcp/__pycache__/alpha.cpython-313.pyc", u"not python")
    _write(dest, "LICENSE", u"licence text\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "core.autocrlf", "false")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    assert make_manifest.main(["--repo", repo, "--dest", dest]) == 0
    with open(os.path.join(dest, "_manifest.json"), "rb") as handle:
        manifest = json.loads(handle.read().decode("utf-8"))
    return repo, dest, manifest


def test_manifest_has_schema_commit_and_exactly_the_tracked_files(built):
    repo, dest, manifest = built
    assert manifest["schema"] == 1
    assert "generated_at" in manifest
    assert re.match(r"^[0-9a-f]{40}$", manifest["commit"])
    assert manifest["commit"] == _git(repo, "rev-parse", "HEAD")
    assert sorted(manifest["files"]) == TRACKED
    assert not any("pycache" in k or k.endswith(".pyc") or "LICENSE" in k
                   for k in manifest["files"])
    assert not os.path.exists(os.path.join(repo, "_manifest.json"))


def test_untouched_published_tree_is_verified_match(built):
    _, dest, _ = built
    result = integrity.check_integrity(dest)
    assert result["state"] == trust.INTEGRITY_MATCH
    assert result["modified"] == [] and result["missing"] == [] and result["unexpected"] == []


def test_crlf_rewrite_after_generation_still_matches(built):
    _, dest, _ = built
    path = os.path.join(dest, "revit_mcp", "beta.py")
    with open(path, "rb") as handle:
        data = handle.read()
    with open(path, "wb") as handle:
        handle.write(data.replace(b"\n", b"\r\n"))
    assert b"\r\n" in open(path, "rb").read()
    assert integrity.check_integrity(dest)["state"] == trust.INTEGRITY_MATCH


def test_edited_deleted_and_added_files_are_named(built):
    _, dest, _ = built
    with open(os.path.join(dest, "revit_mcp", "alpha.py"), "ab") as handle:
        handle.write(b"EVIL = 1\n")
    os.remove(os.path.join(dest, "revit_mcp", "beta.py"))
    _write(dest, "revit_mcp/rogue.py", u"x = 1\n")
    _write(dest, "revit_mcp/_hidden.py", u"y = 1\n")
    result = integrity.check_integrity(dest)
    assert result["state"] == trust.INTEGRITY_MISMATCH
    assert result["modified"] == ["revit_mcp/alpha.py"]
    assert result["missing"] == ["revit_mcp/beta.py"]
    assert result["unexpected"] == ["revit_mcp/_hidden.py", "revit_mcp/rogue.py"]


def test_deleted_manifest_is_unverifiable_never_mismatch(built):
    _, dest, _ = built
    os.remove(os.path.join(dest, "_manifest.json"))
    result = integrity.check_integrity(dest)
    assert result["state"] == trust.INTEGRITY_UNVERIFIABLE
    assert result["reason"] == trust.REASON_MANIFEST_MISSING


def test_generator_uses_the_verifier_hash_function(make_manifest):
    assert make_manifest.hash_normalized is integrity.hash_normalized
    assert make_manifest.MANIFEST_NAME == integrity.MANIFEST_NAME


def test_generator_refuses_an_untracked_py_and_a_dest_inside_the_repo(built, make_manifest):
    repo, dest, _ = built
    _write(dest, "revit_mcp/rogue.py", u"x = 1\n")
    assert make_manifest.main(["--repo", repo, "--dest", dest]) == 1
    inside = os.path.join(repo, "published")
    os.makedirs(inside)
    assert make_manifest.main(["--repo", repo, "--dest", inside]) == 1
    assert not os.path.exists(os.path.join(inside, "_manifest.json"))


def _revit_handler(body, status):
    def handler(request):
        return httpx.Response(status, json=body)
    return handler


@pytest.mark.anyio
async def test_mismatch_reaches_the_model_as_a_visible_423(built):
    _, dest, _ = built
    with open(os.path.join(dest, "revit_mcp", "alpha.py"), "ab") as handle:
        handle.write(b"EVIL = 1\n")
    result = integrity.check_integrity(dest)
    body, status = trust.integrity_failure(trust.mismatch_files(result))
    assert status == 423
    assert body["integrity"] == "verified_mismatch"
    assert body["files"] == ["revit_mcp/alpha.py"]
    transport = httpx.MockTransport(_revit_handler(body, status))
    async with httpx.AsyncClient(base_url="http://revit.test/genpro_revit_mcp/",
                                 transport=transport) as client:
        text = await bridge._send(client, "POST", "/delete_elements/", {"a": 1}, 5.0, None)
    assert isinstance(text, str)
    assert text.startswith("Error: 423 - ")
    assert "verified_mismatch" in text
    assert "revit_mcp/alpha.py" in text
    assert format_response(text) == text
