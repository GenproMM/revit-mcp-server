# -*- coding: utf-8 -*-
"""Shared setup for the Revit-free unit suite.

Everything under tests/unit/ must run with no Revit, no pyRevit and no network,
so that a contributor can prove a change before touching a workstation. The two
standalone scripts in tests/ are a different tier: they drive a real server over
stdio and are excluded from collection by [tool.pytest.ini_options].
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
