# -*- coding: utf-8 -*-
"""Tool registration system for Revit MCP Server.

Tool modules are discovered by convention rather than listed by hand: every
``tools/<domain>_tools.py`` that exposes a ``register_<domain>_tools`` callable
is registered automatically. A new domain is therefore two new files and no
edit to any shared file — which also keeps this module out of every merge with
upstream, where a hand-maintained list conflicts on each new capability.

Registration order is alphabetical and deliberately not significant: no tool
module imports another, so nothing depends on being registered first.
"""

import logging
import pkgutil
import re

logger = logging.getLogger(__name__)

_REGISTRAR = re.compile(r"^register_\w+_tools$")

# Populated by register_tools() so a caller can tell a healthy server from one
# that came up with a domain missing.
REGISTERED = []
FAILED = {}

# Module name -> reason, for modules under tools/ that exposed no
# register_*_tools callable. Normally helpers (utils); a typo'd registrar name
# also lands here, which is why it is reported rather than ignored.
SKIPPED = {}


def _discover():
    """Yield importable ``tools.*`` module names that may hold a registrar.

    Leading-underscore modules are private by convention and never scanned.
    Everything else is imported and inspected -- a module is classified as a
    helper only after it is seen to expose no registrar, so a misspelled
    register_*_tools cannot hide behind a name-based exclusion list.
    """
    for _finder, name, ispkg in pkgutil.iter_modules(__path__):
        _ = ispkg  # a domain may be a package (e.g. tools/audit/) or a module
        if name.startswith("_"):
            continue
        yield name


def _registrar_in(module):
    """Return the register_*_tools callable in a module, or None.

    The name is matched by pattern, never derived from the module name: the
    convention is strict but not mechanical (``colors_tools`` exposes
    ``register_colors_tools``, and a future package may differ).
    """
    for attr in sorted(dir(module)):
        if _REGISTRAR.match(attr) and callable(getattr(module, attr)):
            return getattr(module, attr)
    return None


def register_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func):
    """Discover and register every tool domain with the MCP server.

    Each domain is registered independently: one broken module is logged and
    skipped instead of preventing the server from starting. What failed is kept
    in FAILED so it can be surfaced rather than silently missing.
    """
    del REGISTERED[:]
    FAILED.clear()
    SKIPPED.clear()

    # Imports stay inside this function, as they always have: it keeps stdio
    # cold start low (gated at 2.0 s by deploy/gate.py) and confines an import
    # error to the domain that caused it.
    import importlib

    for name in sorted(_discover()):
        try:
            module = importlib.import_module("." + name, __name__)
            registrar = _registrar_in(module)
            if registrar is None:
                # A helper module (utils), or a typo in the registrar name.
                # Reported either way so the second case cannot pass for the
                # first.
                SKIPPED[name] = "no register_*_tools callable"
                logger.debug("tools.%s exposes no registrar - treated as a helper", name)
                continue
            registrar(mcp_server, revit_get_func, revit_post_func, revit_image_func)
            REGISTERED.append(name)
        except Exception as exc:  # noqa: BLE001 - one domain must not sink the rest
            FAILED[name] = "{}: {}".format(type(exc).__name__, exc)
            logger.exception("Failed to register tool domain '%s'", name)

    if FAILED:
        logger.error(
            "Registered %d tool domains, %d FAILED: %s",
            len(REGISTERED),
            len(FAILED),
            ", ".join(sorted(FAILED)),
        )
    else:
        logger.info("Registered %d tool domains", len(REGISTERED))

    return REGISTERED, FAILED
