# -*- coding: UTF-8 -*-
"""
Revit MCP Extension Startup
Discovers and registers all MCP route modules, then initializes the API.

Route modules are found by convention rather than listed by hand: every
revit_mcp/<domain>.py exposing a register_<domain>_routes callable is
registered automatically. Adding a capability therefore touches no shared
file, which also keeps this module out of every merge with upstream.

Discovery uses os.listdir rather than pkgutil: this runs under IronPython 2.7
and the extension is frequently loaded over a UNC share, where a plain
directory listing is the predictable option.

Registration order is alphabetical and deliberately not significant: no module
in revit_mcp/ imports another module in revit_mcp/ (every cross-module import
goes to the flat `utils` helper), so nothing depends on being registered first.
"""

from pyrevit import routes
import logging
import os
import re

logger = logging.getLogger(__name__)

# Initialize the main API. The namespace is a deployment contract: the sibling
# GenproMCP extension declares routes.API('genpro_mcp') so the two coexist on
# port 48884 without colliding.
api = routes.API("revit_mcp")

_PACKAGE = "revit_mcp"

_REGISTRAR = re.compile(r"^register_\w+_routes$")


def _domain_modules(package):
    """Return sorted module names under revit_mcp/ that may hold a registrar.

    The directory is taken from the imported package's own __path__ rather
    than from __file__: pyRevit decides how startup.py is executed and where
    the extension is loaded from (often a UNC share), and the package itself
    is the only authority on where its modules actually live.

    Leading-underscore files are private by convention and never scanned.
    Everything else is imported and inspected -- a module is classified as a
    helper only after it is seen to expose no registrar, so a misspelled
    register_*_routes cannot hide behind a name-based exclusion list.
    """
    package_dir = package.__path__[0]
    names = []
    for entry in os.listdir(package_dir):
        if not entry.endswith(".py") or entry.startswith("_"):
            continue
        names.append(entry[:-3])
    names.sort()
    return names


def _registrar_in(module):
    """Return the register_*_routes callable in a module, or None.

    Matched by pattern, never derived from the file name: the convention is
    strict but not mechanical -- rooms.py exposes register_room_routes,
    views.py exposes register_views_routes, colors.py register_color_routes.
    """
    for attr in sorted(dir(module)):
        if _REGISTRAR.match(attr) and callable(getattr(module, attr)):
            return getattr(module, attr)
    return None


def register_routes():
    """Discover and register every route domain with the API.

    Each domain is registered independently. One broken module is logged and
    skipped rather than aborting the whole extension: with several people
    adding domains, one person's import error must not remove everyone else's
    routes from every workstation. The failure is not silent -- it is recorded
    in the registry and reported by the /status/ route as "degraded".
    """
    # Imported here, not at module top, matching the convention this file has
    # always followed: everything under revit_mcp/ is imported inside the
    # register function.
    import revit_mcp
    from revit_mcp import registry

    registry.reset()

    for name in _domain_modules(revit_mcp):
        try:
            module = __import__("{}.{}".format(_PACKAGE, name), fromlist=[name])
            registrar = _registrar_in(module)
            if registrar is None:
                # A helper module (utils, registry), or a typo in the
                # registrar name. Reported either way so the second case
                # cannot pass for the first.
                registry.SKIPPED[name] = "no register_*_routes callable"
                logger.info(
                    "revit_mcp.%s exposes no registrar - treated as a helper", name
                )
                continue
            registrar(api)
            registry.REGISTERED.append(name)
        except Exception as exc:
            registry.FAILED[name] = "{}: {}".format(type(exc).__name__, str(exc))
            logger.exception("Failed to register route domain '%s'", name)

    if registry.FAILED:
        logger.error(
            "Registered %d route domains, %d FAILED: %s",
            len(registry.REGISTERED),
            len(registry.FAILED),
            ", ".join(sorted(registry.FAILED.keys())),
        )
    else:
        logger.info(
            "All %d MCP route domains registered successfully",
            len(registry.REGISTERED),
        )

    return registry.REGISTERED, registry.FAILED


# Register all routes when the extension loads
register_routes()
