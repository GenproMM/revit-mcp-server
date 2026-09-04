# -*- coding: utf-8 -*-
"""Parameter tools — read element properties and set parameter values"""

from mcp.server.fastmcp import Context
from .utils import format_response


def register_parameter_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register parameter tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def list_project_parameters(
        shared_only: bool = False,
        prefix: str = None,
        search: str = None,
        summary_only: bool = False,
        ctx: Context = None,
    ) -> str:
        """List the project parameters bound in the current Revit model, marking
        which ones are shared parameters.

        Use this to audit naming conventions and BIM standards compliance — which
        prefixes/namespaces are in use (ADSK_, CPI_, …), whether a parameter is
        shared or project-only, what categories it is bound to, and its GUID.

        Sharedness is determined from the parameter's ForgeTypeId
        ("revit.local.shared:<guid>" vs "revit.local.project:<guid>"), which is the
        only reliable test. A shared parameter gains an internal definition once
        loaded into a project, so the parameter type alone never reveals its origin.

        Scope: only parameters bound via Project Parameters (Document.ParameterBindings).
        Shared parameters that exist inside families but are not bound at project
        level are NOT listed, and neither are built-in parameters. For all parameters
        on one element (including built-ins), use get_element_properties instead.

        Returns a summary block (totals plus a name-prefix breakdown split by
        shared / non-shared) and, unless summary_only is set, the matching parameters
        with: name, is_shared, guid, binding ("instance" or "type"), data_type,
        group, and categories.

        Limitations: is_shared is null for a parameter whose origin the API cannot
        report; such entries are counted under summary.unclassified. Bindings that
        fail to read are skipped and counted under summary.skipped.

        Args:
            shared_only: Return only shared parameters (default: false — return all)
            prefix: Keep only parameters whose name starts with this string, e.g. "ADSK_"
            search: Keep only parameters whose name contains this text (case-insensitive)
            summary_only: Return just the totals and prefix breakdown, omitting the
                parameter list — the cheap option for models with hundreds of parameters
            ctx: MCP context for logging
        """
        params = {}
        if shared_only:
            params["shared_only"] = "true"
        if prefix:
            params["prefix"] = prefix
        if search:
            params["search"] = search
        if summary_only:
            params["summary_only"] = "true"

        response = await revit_get("/project_parameters/", ctx, params=params)
        return format_response(response)

    @mcp.tool()
    async def get_element_properties(
        element_id: int,
        include_type_params: bool = True,
        ctx: Context = None,
    ) -> str:
        """Get all properties and parameters of a Revit element.

        Returns the element's category, family, type, and a complete list of
        both instance and type parameters with their values, storage types,
        and read-only status.

        Args:
            element_id: Revit element ID to inspect
            include_type_params: Include type parameters in addition to instance
                parameters (default: true)
            ctx: MCP context for logging
        """
        response = await revit_get(
            "/element_properties/{}".format(element_id), ctx
        )
        return format_response(response)

    @mcp.tool()
    async def set_parameter(
        element_id: int,
        parameter_name: str,
        value: str,
        ctx: Context = None,
    ) -> str:
        """Set a single parameter value on a Revit element.

        Automatically detects the parameter's storage type (String, Integer,
        Double, ElementId) and converts the value accordingly. Returns old
        and new values for confirmation.

        Args:
            element_id: Target element ID
            parameter_name: Name of the parameter to set (e.g., "Comments", "Mark")
            value: New value as a string — automatically converted to the correct type
            ctx: MCP context for logging
        """
        data = {
            "element_id": element_id,
            "parameter_name": parameter_name,
            "value": value,
        }
        response = await revit_post("/set_parameter/", data, ctx)
        return format_response(response)
