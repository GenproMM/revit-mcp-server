# -*- coding: utf-8 -*-
"""Scaffold a new capability: both halves plus the manifest entry.

    uv run python scripts/new_tool.py <domain> <tool_name> [--get] [--no-mm]

Example:

    uv run python scripts/new_tool.py audit run_model_audit

creates revit_mcp/audit.py and tools/audit_tools.py, adds run_model_audit to
tests/unit/tool_manifest.txt, and prints what to do next.

Why a generator and not a documented recipe: the conventions that keep the
IronPython half loadable (no f-strings, flat helper imports, the exact
registrar signature) and the tool schema usable by a model (async, `-> str`,
`ctx` last, an Args: block naming every parameter) are all invariants a person
has to remember and a code-generating model will happily violate. Generated
files satisfy tests/unit/test_conventions.py by construction, so the developer
is left with the part that actually needs judgement: the algorithm.

The generator never overwrites. To extend an existing domain, add a route and a
tool to the files it already has, then add the tool name to the manifest.
"""

import argparse
import io
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO_ROOT, "tests", "unit", "tool_manifest.txt")

IDENT = re.compile(r"^[a-z][a-z0-9_]*$")


ROUTE_TEMPLATE = '''# -*- coding: utf-8 -*-
"""
{title} module for Revit MCP.

Runs under IronPython 3 inside the Revit process, at the Python 3.4 language
level: "{{}}".format(x) instead of f-strings, no async, no pathlib, no type
hints. Package siblings are imported relatively -- a flat `from utils import`
is an implicit relative import and fails to load.
"""

from .utils import get_element_name, get_element_id_value{suppress_import}
from pyrevit import routes, DB
import logging

logger = logging.getLogger(__name__)
{mm_constant}

def register_{domain}_routes(api):
    """Register {domain} routes with the API."""

    @api.route("/{route}/", methods=["{method}"]){handler_signature}
        """
        TODO describe what this returns, for a developer.

        Payload:
        {{
            "example": "value"
        }}
        """
        try:
            if not doc:
                return routes.make_response(
                    data={{"error": "No active Revit document"}}, status=503
                )
{payload_block}
            # ---------------------------------------------------------------
            # TODO your logic here.
            #
            # Reading elements? Do NOT open a transaction -- a read-only route
            # must not dirty the document.
            #
            # Writing? Use exactly this shape, and keep suppress_warnings on
            # the line after Start(): without it a routine Revit warning opens
            # a modal dialog that blocks this server forever.
            #
            #     t = DB.Transaction(doc, "{title} via MCP")
            #     t.Start()
            #     suppress_warnings(t)
            #     try:
            #         ...
            #         t.Commit()
            #     except Exception:
            #         if t.HasStarted() and not t.HasEnded():
            #             t.RollBack()
            #         raise
            #
            # Element ids: get_element_id_value(elem) to read,
            # make_element_id(value) to build. Never .IntegerValue, never
            # DB.ElementId(<int>) -- that fails on Revit 2027.
            #
            # Names: get_element_name(elem) -- it preserves Cyrillic.
            #
            # Iterating many elements? Catch per element, count what you
            # skipped, and report it. Returning "success" while silently
            # dropping elements is a bug this repo has shipped before.
            # ---------------------------------------------------------------

            results = []
            skipped = 0

            return routes.make_response(
                data={{
                    "status": "success",
                    "results": results,
                    "skipped": skipped,
                }}
            )

        except Exception as e:
            logger.error("{route} failed: {{}}".format(str(e)))
            return routes.make_response(data={{"error": str(e)}}, status=500)

    logger.info("{title} routes registered successfully")
'''


TOOL_TEMPLATE = '''# -*- coding: utf-8 -*-
"""{title} tools."""

from mcp.server.fastmcp import Context
from .utils import format_response


def register_{domain}_tools(mcp, revit_get, revit_post, revit_image=None):
    """Register {domain} tools with the MCP server."""
    _ = revit_image  # Acknowledge unused parameter

    @mcp.tool()
    async def {tool}(
        example: str = None,
        ctx: Context = None,
    ) -> str:
        """TODO one line: what this does and when to reach for it.

        This docstring is the API contract. It is the only thing the model sees
        before calling, so write it for a model, not for a developer:

        Scope rules:
          - TODO what happens when example is omitted.
          - TODO what this does NOT cover.

        TODO the return shape, with units. All dimensions are millimetres.

        Limitations: TODO state them outright. The model cannot infer them, and
        without them it will read an empty result as proof of absence.

        Args:
            example: TODO what it means, with a concrete value,
                e.g. "OST_Walls"
            ctx: MCP context for logging
        """
{call_block}
        return format_response(response)
'''


def _fail(message):
    sys.stderr.write("error: {}\n".format(message))
    raise SystemExit(2)


def _write(path, content):
    if os.path.exists(path):
        _fail("{} already exists -- add to it by hand instead".format(path))
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return os.path.relpath(path, REPO_ROOT).replace("\\", "/")


def _add_to_manifest(tool):
    with io.open(MANIFEST, encoding="utf-8") as handle:
        names = [line.strip() for line in handle if line.strip()]
    if tool in names:
        _fail("{} is already in the manifest -- pick another tool name".format(tool))
    names.append(tool)
    with io.open(MANIFEST, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(sorted(names)) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Scaffold a new Revit MCP capability (both halves)."
    )
    parser.add_argument("domain", help="domain name, snake_case, e.g. audit")
    parser.add_argument("tool", help="first tool name, snake_case, e.g. run_model_audit")
    parser.add_argument(
        "--get",
        action="store_true",
        help="read-only capability: generate a GET route with query params "
             "instead of a POST route with a JSON body",
    )
    parser.add_argument(
        "--no-mm",
        action="store_true",
        help="omit the MM_TO_FEET constant (no geometry involved)",
    )
    args = parser.parse_args()

    for label, value in (("domain", args.domain), ("tool", args.tool)):
        if not IDENT.match(value):
            _fail("{} must be lower snake_case, got {!r}".format(label, value))

    route_path = os.path.join(REPO_ROOT, "revit_mcp", args.domain + ".py")
    tool_path = os.path.join(REPO_ROOT, "tools", args.domain + "_tools.py")
    title = args.domain.replace("_", " ").capitalize()

    if args.get:
        handler_signature = (
            "\n    def {}_handler(doc, example=None):".format(args.domain)
        )
        payload_block = (
            "\n            # Query params arrive as named keyword arguments.\n"
            "            example = example if example else None\n"
        )
        # % formatting, not .format(): the generated code contains literal
        # braces (`params = {}`) that .format() would try to substitute.
        call_block = (
            "        params = {}\n"
            "        if example:\n"
            "            params[\"example\"] = example\n\n"
            "        response = await revit_get(\"/%s/\", ctx, params=params)"
            % args.domain
        )
        method = "GET"
    else:
        handler_signature = (
            "\n    def {}_handler(doc, request):".format(args.domain)
        )
        payload_block = (
            "\n            data = {}\n"
            "            if request and request.data:\n"
            "                data = parse_request_data(request.data)\n"
            "            example = data.get(\"example\")\n"
        )
        call_block = (
            "        data = {\"example\": example}\n"
            "        response = await revit_post(\"/%s/\", data, ctx)" % args.domain
        )
        method = "POST"

    route_source = ROUTE_TEMPLATE.format(
        title=title,
        domain=args.domain,
        route=args.domain,
        method=method,
        handler_signature=handler_signature,
        payload_block=payload_block,
        suppress_import=(
            ""
            if args.get
            else ", make_element_id, parse_request_data, suppress_warnings"
        ),
        mm_constant="" if args.no_mm else "\nMM_TO_FEET = 1.0 / 304.8\n",
    )
    tool_source = TOOL_TEMPLATE.format(
        title=title, domain=args.domain, tool=args.tool, call_block=call_block
    )

    created = [_write(route_path, route_source), _write(tool_path, tool_source)]
    _add_to_manifest(args.tool)

    print("Created:")
    for path in created:
        print("  " + path)
    print("  tests/unit/tool_manifest.txt  (+ {})".format(args.tool))
    print("")
    print("Nothing to register -- discovery finds both halves automatically.")
    print("")
    print("Next:")
    print("  1. Fill in the TODOs. The algorithm is the only decision left.")
    print("  2. uv run pytest tests/unit          # conventions + manifest")
    print("  3. Fully close and reopen Revit      # Reload is NOT enough")
    print("  4. http://localhost:48884/revit_mcp/status/?verbose=true")
    print("     -> your domain listed, health: healthy")
    print("  5. mcp dev main.py                   # call the tool for real")


if __name__ == "__main__":
    main()
