# -*- coding: utf-8 -*-
"""Parameter tools — read element properties and set parameter values"""

from mcp.server.fastmcp import Context
from .utils import read_options, format_response


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


def register_parameter_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register parameter tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def list_project_parameters(
        shared_only: bool = False,
        prefix: str = None,
        search: str = None,
        summary_only: bool = False,
        target: str = None,
        document: str = None,
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

        This is a read of document (an opaque selector from list_documents),
        active or inactive. Without document, reads the active document. Never
        activates a document. Invalid or closed selectors never fall back.
        UI selection/current-view reads and visible_in_view require the active document.

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
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional opaque document selector from list_documents; omitted means active
            ctx: MCP context for logging
        """
        if document is not None and (not isinstance(document, str) or not document.strip()):
            return format_response({"error": "document must be a non-blank selector from list_documents. Nothing was sent to Revit."})
        params = {}
        if document is not None:
            params["document"] = document
        if shared_only:
            params["shared_only"] = "true"
        if prefix:
            params["prefix"] = prefix
        if search:
            params["search"] = search
        if summary_only:
            params["summary_only"] = "true"

        response = await revit_get(
            "/project_parameters/", ctx, params=params, **_target_options(target)
        )
        return format_response(response)

    @mcp.tool()
    async def get_element_properties(
        element_id: int,
        include_type_params: bool = True,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Get all properties and parameters of a Revit element.

        Returns the element's category, family, type, and a complete list of
        both instance and type parameters with their values, storage types,
        and read-only status.

        This is a read of document (an opaque selector from list_documents),
        active or inactive. Without document, reads the active document. Never
        activates a document. Invalid or closed selectors never fall back.
        UI selection/current-view reads and visible_in_view require the active document.

        Args:
            element_id: Revit element ID to inspect
            include_type_params: Include type parameters in addition to instance
                parameters (default: true)
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional opaque document selector from list_documents; omitted means active
            ctx: MCP context for logging
        """
        if document is not None and (not isinstance(document, str) or not document.strip()):
            return format_response({"error": "document must be a non-blank selector from list_documents. Nothing was sent to Revit."})
        response = await revit_get(
            "/element_properties/{}".format(element_id), ctx, **read_options(target, document)
        )
        return format_response(response)

    @mcp.tool()
    async def set_parameter(
        element_id: int,
        parameter_name: str,
        value: str,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Set a single parameter value on a Revit element.

        Automatically detects the parameter's storage type (String, Integer,
        Double, ElementId) and converts the value accordingly. Returns old
        and new values for confirmation.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. Element ids belong to one document, so name the document the
        id was read from.

        A write that Revit rolls back is reported as an error (HTTP 409 with
        status "rolled_back"), never as a success; treat that reply as a failed
        write and read the reason it gives.

        A confirmation window opens when the write changes a type parameter,
        overwrites a non-empty value, touches more than one element, targets an
        element in a group, or when the facts cannot be read. Filling an empty
        instance parameter of one element is sent directly. A DENIED, DECLINED,
        NOT CONFIRMED, EXPIRED or UNAVAILABLE reply means nothing was sent to
        Revit; do not retry blindly.

        Args:
            element_id: Target element ID
            parameter_name: Name of the parameter to set (e.g., "Comments", "Mark")
            value: New value as a string — automatically converted to the correct type
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {
            "element_id": element_id,
            "parameter_name": parameter_name,
            "value": value,
        }
        if document is not None:
            data["document"] = document
        response = await revit_post("/set_parameter/", data, ctx, **_target_options(target))
        return format_response(response)
