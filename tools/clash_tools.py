# -*- coding: utf-8 -*-
"""Clash detection tools — hard interference checking for BIM coordination"""

from mcp.server.fastmcp import Context
from .utils import format_response


def _target_options(target):
    """Transport keyword for the per-call process selector; absent when not given."""
    return {} if target is None else {"target": target}


def register_clash_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register clash detection tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def check_clashes(
        set_a_categories: list[str] = None,
        set_b_categories: list[str] = None,
        max_clashes: int = 200,
        target: str = None,
        ctx: Context = None,
    ) -> str:
        """Detect hard clashes (geometric interferences) between model elements.

        Runs Revit's native interference logic to find elements whose solids
        physically overlap — the core of BIM coordination (e.g. ducts running
        through beams, pipes through walls).

        Scope rules:
          - No categories given: a default physical scope (architectural +
            structural + MEP) is checked against itself.
          - Only set_a given: set_a is checked against itself.
          - Both given: set_a is checked against set_b (cross-discipline),
            e.g. structure vs MEP.

        Categories accept BuiltInCategory ids ("OST_DuctCurves") or friendly
        aliases ("ducts", "pipes", "beams", "walls", "structural framing").

        Returns clashing element pairs with ids, names, categories, and the
        approximate clash location in mm. Note: auto-joined concrete and
        geometry-less elements (e.g. rebar) are not reported by Revit.

        This is a read. It checks the document that is active in the selected
        Revit process and changes nothing. It has no document argument, because
        reading an inactive document is supported only by read_document_summary
        and read_document_levels; this tool never checks an inactive document.

        Args:
            set_a_categories: First element set, e.g. ["beams", "OST_StructuralColumns"]
            set_b_categories: Second element set to check against, e.g. ["ducts", "pipes"]
            max_clashes: Maximum clashes to return (defaults to 200)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            ctx: MCP context for logging
        """
        data = {
            "set_a_categories": set_a_categories,
            "set_b_categories": set_b_categories,
            "max_clashes": max_clashes,
        }
        response = await revit_post("/clash_check/", data, ctx, **_target_options(target))
        return format_response(response)
