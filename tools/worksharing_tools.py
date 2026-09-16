# -*- coding: utf-8 -*-
"""Worksharing tools — opening models with detach and workset configuration."""

import json
from functools import lru_cache

from mcp.server.fastmcp import Context
from .utils import describe_broken_path, format_response


_MODEL_JOURNAL = "//srv-dfs/BIM/01_Ресурсы плагинов/10_Облегченные модели/RevitModelLiteProcessorJournal.json"
_DEFAULT_CLOSE_WORKSETS = ["__ALL_USER_WORKSETS__"]


def _is_revit_server_path(file_path: str) -> bool:
    """Return whether file_path is an RSN Revit Server URI."""
    return isinstance(file_path, str) and file_path.strip().lower().startswith("rsn://")


@lru_cache(maxsize=1)
def _revit_server_models() -> tuple[tuple[str, str, str], ...]:
    """Read canonical Revit Server model locations from the shared journal."""
    with open(_MODEL_JOURNAL, "r", encoding="utf-8-sig") as stream:
        payload = json.load(stream)

    models: list[tuple[str, str, str]] = []

    def visit(node: object) -> None:
        if isinstance(node, dict):
            if node.get("IsFile") is True and node.get("Name") and node.get("Path"):
                server = node.get("ServerName")
                if server:
                    models.append((str(server), str(node["Path"]), str(node["Name"])))
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(payload)
    return tuple(models)


def _resolve_revit_server_path(file_path: str) -> str:
    """Resolve an RSN URI by model filename using the shared journal."""
    if not _is_revit_server_path(file_path):
        return file_path

    normalized = file_path.strip().replace("\\", "/")
    requested_name = normalized.rstrip("/").rsplit("/", 1)[-1].lower()
    matches = [model for model in _revit_server_models() if model[2].lower() == requested_name]
    if not matches:
        raise FileNotFoundError(
            "Revit Server model was not found in the model journal by filename: "
            + requested_name
        )
    if len(matches) > 1:
        locations = ", ".join(server + path for server, path, _ in matches)
        raise ValueError(
            "Model filename is ambiguous in the model journal; matching locations: "
            + locations
        )

    server, model_path, _ = matches[0]
    canonical_path = "/" + model_path.lstrip("/\\").replace("\\", "/")
    return "RSN://" + server + canonical_path


def _resolve_path_or_error(file_path: str) -> tuple[str, str | None]:
    """Resolve RSN input, returning a tool-friendly error instead of raising."""
    try:
        return _resolve_revit_server_path(file_path), None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return file_path, str(exc)


def register_worksharing_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register worksharing / model-open tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def list_model_worksets(
        file_path: str,
        close_worksets_matching: list[str] = None,
        ctx: Context = None,
    ) -> str:
        """Inspect a Revit model's worksets without opening it.

        Reads the .rvt header and its workset table straight from disk, so it is
        cheap and safe to call on a heavy federated model before deciding how to
        open it. Use it to confirm a model is workshared and to preview which
        worksets open_model would close. The safe default for a central model is
        to detach, preserve worksets, and close every user workset.

        Returns the file's workshared/central flags, the Revit version it was
        saved in, every user workset with its id and name, and a would_close
        list. A model that is not workshared returns an empty workset list with
        an explanatory message rather than an error.

        Limitations: reports user worksets only, not families or view worksets.
        A model already open in Revit is still read from disk, so unsaved
        workset changes are not reflected.

        Args:
            file_path: Full path to the .rvt file, or an RSN:// Revit Server
                URI. Escape backslashes ("G:\\\\Models\\\\Tower.rvt") or use forward
                slashes ("G:/Models/Tower.rvt"); a single backslash before a
                digit or letter becomes a control character and the file is
                reported missing. Non-ASCII names (Cyrillic etc.) are fully
                supported.
            close_worksets_matching: Substrings marking worksets to leave closed,
                matched case-insensitively. The default sentinel
                ["__ALL_USER_WORKSETS__"] closes every user workset. Pass an
                explicit list such as ["#_RVT_LINK"] to close only matching
                worksets, or [] to preview with every workset open.
            ctx: MCP context for logging
        """
        # Check for a mangled path first: it is a client-side mistake and the
        # RSN journal lookup below would only report it as "not found".
        problem = describe_broken_path(file_path)
        if problem:
            return format_response({"error": problem})
        resolved_path, resolution_error = _resolve_path_or_error(file_path)
        if resolution_error:
            return "Error: " + resolution_error
        data = {
            "file_path": resolved_path,
            "close_worksets_matching": (
                _DEFAULT_CLOSE_WORKSETS
                if close_worksets_matching is None
                else close_worksets_matching
            ),
        }
        response = await revit_post("/model_worksets/", data, ctx)
        return format_response(response)

    @mcp.tool()
    async def open_model(
        file_path: str,
        detach: str = "preserve",
        close_worksets_matching: list[str] = None,
        activate: bool = True,
        audit: bool = False,
        ctx: Context = None,
    ) -> str:
        """Open a Revit model from disk, detaching from central and choosing worksets.

        This is the way to get a model into Revit for the other tools to work on.
        By default it detaches from central while preserving worksets — the Revit
        dialog's "Detach and preserve worksets" — and closes every user workset.
        This preserves the worksharing data without loading model contents.

        Closing link worksets matters on federated models: left open, Revit loads
        every attached RVT as its own document, which on a large model means
        roughly ten extra discipline models and ten times the memory.

        A model that is not workshared is opened plainly, with neither detach nor
        workset configuration, because Revit rejects both on such a file; the
        response says so via is_workshared.

        Returns the opened document's title, the detach mode actually applied,
        whether it became the active document, and the worksets opened vs closed.
        For a central/workshared model, the default result is all user worksets
        closed while the worksharing data remains preserved.

        Limitations: a closed workset cannot be opened later without reopening
        the model, so choose close_worksets_matching deliberately. Opening is
        synchronous and a large model can exceed the 30s bridge timeout — the
        open usually completes in Revit even when the call times out, so check
        get_revit_status rather than retrying blindly. Detaching leaves an unsaved
        document; use save_document with a file_path to persist it.

        Args:
            file_path: Full path to the .rvt file, or an RSN:// Revit Server
                URI. Escape backslashes
                ("G:\\\\Models\\\\Tower.rvt") or use forward slashes
                ("G:/Models/Tower.rvt"); a single backslash before a digit or
                letter becomes a control character and the file is reported
                missing. Non-ASCII names (Cyrillic etc.) are fully supported.
            detach: "preserve" keeps worksets (default), "discard" drops them,
                "none" opens the central file itself without detaching
            close_worksets_matching: Substrings marking worksets to leave closed,
                matched case-insensitively. The default sentinel
                ["__ALL_USER_WORKSETS__"] closes every user workset. Pass an
                explicit list such as ["#_RVT_LINK"] to close only matching
                worksets, or [] to open every workset.
            activate: Make the opened model the active document, which the other
                tools operate on (defaults to True)
            audit: Run Revit's audit while opening — slow, for suspect files
            ctx: MCP context for logging
        """
        # Check for a mangled path first: it is a client-side mistake and the
        # RSN journal lookup below would only report it as "not found".
        problem = describe_broken_path(file_path)
        if problem:
            return format_response({"error": problem})
        resolved_path, resolution_error = _resolve_path_or_error(file_path)
        if resolution_error:
            return "Error: " + resolution_error
        data = {
            "file_path": resolved_path,
            "detach": detach,
            "activate": activate,
            "audit": audit,
        }
        data["close_worksets_matching"] = (
            _DEFAULT_CLOSE_WORKSETS
            if close_worksets_matching is None
            else close_worksets_matching
        )
        response = await revit_post("/open_model/", data, ctx)
        return format_response(response)
