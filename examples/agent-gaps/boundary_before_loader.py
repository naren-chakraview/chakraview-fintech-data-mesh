"""Loads the frozen "before" boundary package (examples/agent-gaps/before/platform/boundary) under its own name.

It is loaded under a unique package name because the live boundary is also called `boundary`.
"""

import importlib
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BEFORE_BOUNDARY = HERE / "before" / "platform" / "boundary"
PACKAGE = "agents_before_boundary"


def load_before_main():
    if PACKAGE not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            PACKAGE, BEFORE_BOUNDARY / "__init__.py", submodule_search_locations=[str(BEFORE_BOUNDARY)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[PACKAGE] = module
        spec.loader.exec_module(module)
    return importlib.import_module(f"{PACKAGE}.main")
