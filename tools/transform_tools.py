# -*- coding: utf-8 -*-
"""Transform tools — move, copy, rotate, and mirror elements"""

from mcp.server.fastmcp import Context
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


def register_transform_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register transform tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def transform_elements(
        element_ids: list[int],
        operation: str,
        vector: dict = None,
        axis_point: dict = None,
        angle: float = None,
        mirror_plane: dict = None,
        target: str = None,
        document: str = None,
        ctx: Context = None,
    ) -> str:
        """Move, copy, rotate, or mirror elements in the Revit model.

        Performs geometric transformations on one or more elements.
        All coordinates and distances are in millimeters, angles in degrees.

        This changes the model. Document choice: pass document (a value from
        list_documents) to name the document to change. Without it the call uses
        the only open document; if several documents are open it is refused and
        the candidates are listed, and the document active in the UI is never
        assumed. A document that is open but not active is refused (HTTP 412) and
        nothing is activated: use activate_document, then retry with the same
        selector. element_ids are looked up in that document.

        Args:
            element_ids: List of element IDs to transform
            operation: Transform type — "move", "copy", "rotate", or "mirror"
            vector: Translation vector {"x", "y", "z"} in mm (required for move/copy)
            axis_point: Rotation center {"x", "y", "z"} in mm (required for rotate)
            angle: Rotation angle in degrees (required for rotate)
            mirror_plane: Mirror definition (required for mirror):
                - origin (dict): {"x", "y", "z"} point on the mirror plane in mm
                - normal (dict): {"x", "y", "z"} plane normal direction
            target: Optional opaque process selector from discover_revit_targets;
                omit it only when exactly one Revit process is usable
            document: Optional document selector from list_documents; omit it only
                when exactly one document is open (see the document choice rule above)
            ctx: MCP context for logging
        """
        if _blank_document(document):
            return format_response(dict(_BLANK_DOCUMENT_REFUSAL))
        data = {
            "element_ids": element_ids,
            "operation": operation,
        }
        if vector is not None:
            data["vector"] = vector
        if axis_point is not None:
            data["axis_point"] = axis_point
        if angle is not None:
            data["angle"] = angle
        if mirror_plane is not None:
            data["mirror_plane"] = mirror_plane
        if document is not None:
            data["document"] = document
        response = await revit_post("/transform_elements/", data, ctx, **_target_options(target))
        return format_response(response)
