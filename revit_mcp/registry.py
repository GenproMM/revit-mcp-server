# -*- coding: UTF-8 -*-
"""
Registration registry for the Revit MCP extension.

startup.py writes the outcome of route discovery here; revit_mcp/status.py
reads it when serving /status/. Keeping the state in the package (rather than
importing startup from status.py) avoids a circular import: startup imports
every route module, and a route module importing startup back would close the
loop at extension load.

This module holds no Revit API code and registers no routes. It is a helper,
and startup.py's discovery treats it as one.
"""

# Domains whose register_*_routes ran without raising.
REGISTERED = []

# Domain name -> "ExceptionType: message" for domains that raised.
FAILED = {}

# Module name -> reason, for modules under revit_mcp/ that exposed no
# register_*_routes callable. Normally helpers; a typo'd registrar name also
# lands here, which is why it is reported rather than ignored.
SKIPPED = {}


def reset():
    """Clear all three collections in place, keeping the same objects."""
    del REGISTERED[:]
    FAILED.clear()
    SKIPPED.clear()


def snapshot(verbose=False):
    """Return a JSON-serializable view for the /status/ route.

    The default is deliberately small: /status/ is the most frequently called
    route, and listing every domain name on every health check is response
    weight that reaches the model on each call. Counts are always reported,
    failures are always reported in full (they are what the caller must act
    on), and the full domain listing is opt-in.
    """
    data = {"domains_registered": len(REGISTERED)}

    # Failures are never abbreviated -- a degraded server has to say what is
    # missing, or the isolation that let it start becomes a silent capability
    # loss, which is the exact failure mode the barrels used to have.
    if FAILED:
        data["failed_domains"] = dict(FAILED)
    if SKIPPED:
        data["skipped_modules"] = dict(SKIPPED)
    if verbose:
        data["registered_domains"] = sorted(REGISTERED)

    return data


def is_degraded():
    """True when at least one domain failed to register."""
    return bool(FAILED)
