# -*- coding: utf-8 -*-
"""Code execution tools for the MCP server."""

from mcp.server.fastmcp import Context
from .utils import format_response


def register_code_execution_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register code execution tools with the MCP server."""
    # Note: revit_get and revit_image are unused but kept for interface consistency
    _ = revit_get, revit_image  # Acknowledge unused parameters

    @mcp.tool()
    async def execute_revit_code(
        code: str,
        description: str = "Code execution",
        target: str = None,
        ctx: Context = None,
    ) -> str:
        """
        Execute IronPython code directly in a Revit process.

        This is a trusted arbitrary-code exception. It is not confined to one document,
        and it is kept for work the typed tools cannot do. Read these limits before you
        use it:

        - The code runs as IronPython 3 (the Python 3.4 language level: no f-strings)
          with full access to the targeted Revit process: doc, DB, revit, clr and System.
        - doc is only the starting context: the document that was current when the call
          arrived. It is not a selected document and it is not guaranteed to be the one
          you intend; the active document may not be the one you meant.
        - The code can reach and change other open documents (through revit, DB, clr,
          System or builtins). There is no document guard, no inactive-document refusal
          and no confinement.
        - The documents the code changes are not identified or attributed in the reply.
          The reply says which process ran the code (process_identity) and repeats this
          exception in its document_scope field; it never names a changed document. If
          the work matters, verify the result with a read tool afterwards.
        - target selects which Revit process runs the code and nothing more. It is not
          authentication and it does not select, guard or confine a document.
        - The code is wrapped in one transaction that is rolled back if Revit vetoes the
          commit (a rolled_back reply is an error, not a success).

        Use this when the existing MCP tools cannot accomplish what you need, and prefer a
        typed tool whenever one exists: typed mutation tools take a document and refuse when
        it is not the active one.

        Args:
            code: The IronPython code to execute (as a string)
            description: Optional description of what the code does
            target: Optional opaque process selector from discover_revit_targets; omit it
                only when exactly one Revit process is usable. It names the process that
                runs the code and nothing else.
            ctx: MCP context for logging

        Returns:
            Execution results including any output or errors, the process that ran the
            code and the document_scope exception notice

        Example:
            code = '''
                    # encoding: utf-8
                    # Hello World example
                    print("Hello from Revit!")
                    from pyrevit import revit, DB, forms, script
                    output = script.get_output()
                    output.close_others()
                    doc = revit.doc
                    print("Document title:", doc.Title)
                    print("Number of walls:", len(list(DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Walls).WhereElementIsNotElementType())))
                    collector = DB.FilteredElementCollector(doc).OfClass(DB.TextNoteType).ToElements()
                    print("Number of text note types:", len(collector))
                    '''

        Tips for writing IronPython code in Revit:
        -----------------------------------------
        1. Accessing Element.Name property:
           Some Revit elements don't expose the 'Name' property directly in IronPython.
           Use defensive access patterns:

           # Option 1: Use getattr with a default value
           name = getattr(element, 'Name', 'N/A')

           # Option 2: Use try-except
           try:
               name = element.Name
           except AttributeError:
               name = 'Unable to retrieve name'

           # Option 3: Use BuiltInParameter for element types
           param = element_type.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
           name = param.AsString() if param else 'N/A'

        2. Always check if elements exist before accessing properties:
           element = doc.GetElement(element_id)
           if element:
               # Safe to access element properties

        3. Use hasattr() before accessing optional properties:
           if hasattr(element_type, 'FamilyName'):
               family_name = element_type.FamilyName

        4. The Tool already wraps the code around a transaction.
        """
        try:
            payload = {"code": code, "description": description}
            options = {} if target is None else {"target": target}

            if ctx:
                await ctx.info("Executing code: {}".format(description))

            response = await revit_post("/execute_code/", payload, ctx, **options)
            return format_response(response)

        except (ConnectionError, ValueError, RuntimeError) as e:
            error_msg = "Error during code execution: {}".format(str(e))
            if ctx:
                await ctx.error(error_msg)
            return error_msg
