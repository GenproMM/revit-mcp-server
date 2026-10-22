# -*- coding: utf-8 -*-
"""Family and placement tools"""

from mcp.server.fastmcp import Context
from typing import Dict, Any
from .utils import describe_broken_path, format_response


def _target_options(target):
    """Transport keyword for the per-call process selector; absent when not given."""
    return {} if target is None else {"target": target}


def _blank_document(document):
    """True for a document selector that was given but is not a usable string.

    A blank value must refuse, never decay into the one-open-document default.
    """
    return document is not None and (not isinstance(document, str) or not document.strip())


_BLANK_DOCUMENT_REFUSAL = {
    "error": "document must be a non-blank selector: pass the 'document' value of one document "
             "from list_documents, or omit it. Nothing was sent to Revit."
}


def register_family_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register family-related tools"""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def place_family(
        family_name: str,
        type_name: str = None,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        rotation: float = 0.0,
        level_name: str = None,
        properties: Dict[str, Any] = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Place one family instance at a point in the Revit model.

        Use list_families first to find an exact family_name/type_name pair; if
        the family is not loaded yet, call load_family before this.

        Scope rules:
          - type_name omitted: the family's first available type is used.
          - level_name omitted: the element is placed without an explicit host
            level, which for level-hosted categories puts it at Z=0 rather than
            at the level elevation. Pass level_name whenever it matters.
          - Hosted families (doors, windows) need a host at the given point; with
            no host they land at the project origin.

        Coordinates are MILLIMETRES in project coordinates, converted to Revit's
        internal feet by the route. Rotation is in DEGREES, counter-clockwise
        about the vertical axis through the insertion point; rotation is
        best-effort and is skipped for elements that do not support it.

        Returns the new element's id, the resolved family/type, the rotation
        applied and the level used.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. The family must be loaded in that document.

        Args:
            family_name: Exact family name, e.g. "Basic Wall" or "Chair"
            type_name: Exact type within the family, e.g. "1830mm x 610mm".
                Omit to use the family's first type.
            x: X position in millimetres (defaults to 0.0)
            y: Y position in millimetres (defaults to 0.0)
            z: Z position in millimetres (defaults to 0.0)
            rotation: Rotation in degrees about the vertical axis (defaults to 0.0)
            level_name: Exact level name to host the instance on, e.g. "Level 1"
            properties: Parameter name to value map applied after placement,
                e.g. {"Comments": "placed by MCP"}
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {
            "family_name": family_name,
            "type_name": type_name,
            "location": {"x": x, "y": y, "z": z},
            "rotation": rotation,
            "level_name": level_name,
            "properties": properties or {},
        }
        if document is not None:
            data["document"] = document
        response = await revit_post("/place_family/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def list_families(
        contains: str = None,
        limit: int = 50,
        target: str = None,
        ctx: Context = None,
    ) -> str:
        """List loadable family types present in the current Revit model.

        Returns a flat list of family_name / type_name / category / is_active,
        which is how you find the exact pair place_family needs.

        This is a read. It reads the active document of the selected Revit
        process; it has no document argument, because reading an inactive
        document is supported only by read_document_summary and
        read_document_levels.

        Known limitation: the route currently ignores both arguments. It always
        returns the first 50 family types it encounters, unfiltered and in no
        particular order, and reports that count as "truncated_total". Do not
        read an absent family as proof it is not loaded — narrow the question
        with list_family_categories instead, or raise the cap in
        revit_mcp/placement.py.

        Args:
            contains: Intended as a case-insensitive name filter. NOT currently
                applied by the route — passing it changes nothing.
            limit: Intended as a maximum result count. NOT currently applied by
                the route, which caps at 50 regardless.
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            ctx: MCP context for logging
        """
        params = {}
        if contains:
            params["contains"] = contains
        if limit != 50:
            params["limit"] = str(limit)

        result = await revit_get("/list_families/", ctx, params=params, **_target_options(target))
        return format_response(result)

    @mcp.tool()
    async def list_family_categories(target: str = None, ctx: Context = None) -> str:
        """List the family categories present in the current Revit model.

        Cheaper and more complete than list_families when you only need to know
        which kinds of loadable families exist (Doors, Windows, Furniture, …).
        Scope: categories of loadable families in this document — not every
        Revit BuiltInCategory, and not system families such as walls or floors.

        This is a read. It reads the active document of the selected Revit
        process; it has no document argument, because reading an inactive
        document is supported only by read_document_summary and
        read_document_levels.

        Args:
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            ctx: MCP context for logging
        """
        response = await revit_get("/list_family_categories/", ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def load_family(
        file_path: str,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Load a Revit family (.rfa file) from disk into a project document.

        Use this when a needed family (furniture, doors, windows, equipment) is
        not already loaded in the project — load it first, then place_family can
        place its types. The file_path must be a full path to a .rfa file
        accessible to the machine running Revit.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to load into. Without it the call
        uses the only open document; if several documents are open it is refused
        and the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector.

        Args:
            file_path: Full path to the .rfa family file, e.g.
                "C:\\ProgramData\\Autodesk\\RVT 2027\\Libraries\\English\\Furniture\\Chair.rfa"
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        problem = describe_broken_path(file_path)
        if problem:
            return format_response({"error": problem})
        data = {"file_path": file_path}
        if document is not None:
            data["document"] = document
        response = await revit_post("/load_family/", data, ctx, **_target_options(target))
        return format_response(response)

    @mcp.tool()
    async def edit_family(
        family_name: str,
        type_name: str = None,
        parameters: Dict[str, Any] = None,
        new_type_name: str = None,
        reload: bool = True,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Edit a family already loaded in the project and load it back.

        Opens the family in Revit's family editor, changes its type parameters,
        then reloads it into the project so every placed instance updates. Use
        this to correct a family's dimensions or data without leaving Revit, or
        to add a new type to an existing family.

        Returns the family's available types, the type now current, which
        parameters were applied, and which failed with the reason for each — a
        parameter that does not exist or is read-only is reported per name
        rather than failing the whole call.

        Scope: type parameters of a loadable family. It cannot change instance
        parameters (use set_parameter), family geometry, or system families such
        as walls, floors and roofs, which have no editable family document.
        In-place families are rejected too.

        Limitations: lengths are millimetres and are converted using each
        parameter's own unit type, so a value written to a non-length parameter
        is stored as given. The reload overwrites the project copy and its
        parameter values by design. A large family can exceed the 30s bridge
        timeout; the edit usually completes in Revit even when the call does not
        return.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the project document that holds the family.
        Without it the call uses the only open document; if several documents
        are open it is refused and the candidates are listed, and the document
        active in the UI is never assumed. A document that is open but not active
        is refused (HTTP 412) and nothing is activated: use activate_document,
        then retry with the same selector. This tool makes no activation call.

        Args:
            family_name: Name of the loaded family, as list_families reports it
            type_name: Which existing family type to edit; defaults to the
                family's current type
            parameters: Family type parameters to set, as {name: value} —
                lengths in millimetres, e.g. {"Ширина": 1200}
            new_type_name: Create a type with this name and edit that instead of
                an existing one
            reload: Load the edited family back into the project (defaults to
                True); False edits and discards, which is only useful to probe
                what a family exposes
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {"family_name": family_name, "reload": reload}
        if type_name is not None:
            data["type_name"] = type_name
        if parameters is not None:
            data["parameters"] = parameters
        if new_type_name is not None:
            data["new_type_name"] = new_type_name
        if document is not None:
            data["document"] = document
        response = await revit_post("/edit_family/", data, ctx, **_target_options(target))
        return format_response(response)
