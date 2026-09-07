# -*- coding: utf-8 -*-
"""Family and placement tools"""

from mcp.server.fastmcp import Context
from typing import Dict, Any
from .utils import format_response


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
            ctx: MCP context for logging
        """
        data = {
            "family_name": family_name,
            "type_name": type_name,
            "location": {"x": x, "y": y, "z": z},
            "rotation": rotation,
            "level_name": level_name,
            "properties": properties or {},
        }
        response = await revit_post("/place_family/", data, ctx)
        return format_response(response)

    @mcp.tool()
    async def list_families(
        contains: str = None, limit: int = 50, ctx: Context = None
    ) -> str:
        """List loadable family types present in the current Revit model.

        Returns a flat list of family_name / type_name / category / is_active,
        which is how you find the exact pair place_family needs.

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
            ctx: MCP context for logging
        """
        params = {}
        if contains:
            params["contains"] = contains
        if limit != 50:
            params["limit"] = str(limit)

        result = await revit_get("/list_families/", ctx, params=params)
        return format_response(result)

    @mcp.tool()
    async def list_family_categories(ctx: Context = None) -> str:
        """List the family categories present in the current Revit model.

        Cheaper and more complete than list_families when you only need to know
        which kinds of loadable families exist (Doors, Windows, Furniture, …).
        Scope: categories of loadable families in this document — not every
        Revit BuiltInCategory, and not system families such as walls or floors.

        Args:
            ctx: MCP context for logging
        """
        response = await revit_get("/list_family_categories/", ctx)
        return format_response(response)

    @mcp.tool()
    async def load_family(file_path: str, ctx: Context = None) -> str:
        """Load a Revit family (.rfa file) from disk into the active document.

        Use this when a needed family (furniture, doors, windows, equipment) is
        not already loaded in the project — load it first, then place_family can
        place its types. The file_path must be a full path to a .rfa file
        accessible to the machine running Revit.

        Args:
            file_path: Full path to the .rfa family file, e.g.
                "C:\\ProgramData\\Autodesk\\RVT 2027\\Libraries\\English\\Furniture\\Chair.rfa"
            ctx: MCP context for logging
        """
        response = await revit_post("/load_family/", {"file_path": file_path}, ctx)
        return format_response(response)
