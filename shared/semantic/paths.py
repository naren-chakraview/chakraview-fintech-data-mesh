"""Filesystem locations of shared semantic artifacts."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_ONTOLOGY_PATH = REPO_ROOT / "semantics" / "core" / "fintech-core.ttl"
SHAPES_DIR = REPO_ROOT / "semantics" / "shapes"
