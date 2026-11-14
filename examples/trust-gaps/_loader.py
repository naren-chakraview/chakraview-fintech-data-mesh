"""Loads the frozen "before" code and starts the "before" OPA, next to the live "after" stack.

The before code lives in examples/trust-gaps/before/ (frozen from f949583, tag trust-before). Both
versions are loaded under unique names, because the live discovery backend and the frozen one are both
called `backend`.
"""

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BEFORE = HERE / "before"

for entry in (REPO, REPO / "platform"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

# Demo-only values. Real runs set these themselves.
os.environ.setdefault("FINTECH_IRI_KEY", "demo-only-key-not-for-production")


def _load(name: str, directory: Path):
    spec = importlib.util.spec_from_file_location(
        name, directory / "__init__.py", submodule_search_locations=[str(directory)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_before_discovery():
    """The frozen discovery backend's main module. OPA_URL must point at the before OPA before the first import."""
    import importlib

    _load("trust_before_backend", BEFORE / "backend")
    return importlib.import_module("trust_before_backend.main")


def load_before_enforce():
    """The frozen enforcement module (mask_rows and its audit hook)."""
    spec = importlib.util.spec_from_file_location("trust_before_enforce", BEFORE / "governance" / "enforce.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["trust_before_enforce"] = module
    spec.loader.exec_module(module)
    return module


def before_policy_dir() -> Path:
    return BEFORE / "opa-policies"


def line(title: str) -> None:
    print(f"\n== {title}")


def section(label: str) -> None:
    print(f"\n--- {label}")
