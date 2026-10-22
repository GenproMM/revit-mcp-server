# -*- coding: utf-8 -*-
"""Color tools"""

from mcp.server.fastmcp import Context
from typing import Dict, Any, Optional, List
from .utils import format_response


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


def register_colors_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register color tools with the MCP server."""

    @mcp.tool()
    async def color_splash(
        category_name: str,
        parameter_name: str,
        use_gradient: bool = False,
        custom_colors: Optional[List[str]] = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """
        Color elements in a category based on parameter values

        This tool applies color coding to Revit elements within a specified category
        based on their parameter values. Elements with the same parameter value
        will receive the same color.

        This changes the model (it writes color overrides). Document choice: pass
        document (a value from list_documents) to name the document to change.
        Without it the call uses the only open document; if several documents are
        open it is refused and the candidates are listed, and the document active
        in the UI is never assumed. A document that is open but not active is
        refused (HTTP 412) and nothing is activated: use activate_document, then
        retry with the same selector.

        Args:
            category_name: Name of the category to color (e.g., "Walls", "Doors", "Windows")
            parameter_name: Name of the parameter to use for coloring (e.g., "Mark", "Type Name")
            use_gradient: Whether to use gradient coloring instead of distinct colors (default: False)
            custom_colors: Optional list of custom colors in hex format (e.g., ["#FF0000", "#00FF00"])
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging

        Returns:
            Results of the coloring operation including statistics and color assignments
        """
        try:
            if _blank_document(document):
                return format_response(dict(_BLANK_DOCUMENT_REFUSAL))

            data = {
                "category_name": category_name,
                "parameter_name": parameter_name,
                "use_gradient": use_gradient,
            }

            if custom_colors:
                data["custom_colors"] = custom_colors
            if document is not None:
                data["document"] = document

            if ctx:
                await ctx.info(
                    "Color splashing {} elements by {}".format(
                        category_name, parameter_name
                    )
                )
            response = await revit_post("/color_splash/", data, ctx, **_target_options(target))
            return format_response(response)

        except Exception as e:
            error_msg = "Error applying color splash: {}".format(str(e))
            if ctx:
                await ctx.error(error_msg)
            return error_msg

    @mcp.tool()
    async def clear_colors(
        category_name: str,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """
        Clear color overrides for elements in a category

        This tool removes all color overrides that have been applied to elements
        in the specified category, returning them to their default appearance.

        This changes the model (it removes color overrides). Document choice: pass
        document (a value from list_documents) to name the document to change.
        Without it the call uses the only open document; if several documents are
        open it is refused and the candidates are listed, and the document active
        in the UI is never assumed. A document that is open but not active is
        refused (HTTP 412) and nothing is activated: use activate_document, then
        retry with the same selector.

        Args:
            category_name: Name of the category to clear colors from (e.g., "Walls", "Doors")
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging

        Returns:
            Results of the clear operation including count of elements processed
        """
        try:
            if _blank_document(document):
                return format_response(dict(_BLANK_DOCUMENT_REFUSAL))

            data = {"category_name": category_name}
            if document is not None:
                data["document"] = document

            if ctx:
                await ctx.info("Clearing color overrides for {} elements".format(category_name))
            response = await revit_post("/clear_colors/", data, ctx, **_target_options(target))
            return format_response(response)

        except Exception as e:
            error_msg = "Error clearing colors: {}".format(str(e))
            if ctx:
                await ctx.error(error_msg)
            return error_msg

    @mcp.tool()
    async def list_category_parameters(
        category_name: str,
        target: str = None,
        ctx: Context = None,
    ) -> str:
        """
        Get available parameters for elements in a category

        This tool helps you discover what parameters are available for coloring
        by listing all parameters found on elements in the specified category.

        This is a read, although it is sent as a POST: it changes nothing. It reads
        the document that is active in the selected Revit process and has no
        document argument, because reading an inactive document is supported only
        by read_document_summary and read_document_levels.

        Args:
            category_name: Name of the category to check parameters for (e.g., "Walls", "Doors")
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            ctx: MCP context for logging

        Returns:
            List of available parameters with their types and sample values
        """
        try:
            data = {"category_name": category_name}

            if ctx:
                await ctx.info(
                    "Getting available parameters for {} category".format(category_name)
                )
            response = await revit_post(
                "/list_category_parameters/", data, ctx, **_target_options(target))
            return format_response(response)

        except Exception as e:
            error_msg = "Error listing category parameters: {}".format(str(e))
            if ctx:
                await ctx.error(error_msg)
            return error_msg
