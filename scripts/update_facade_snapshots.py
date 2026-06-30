#!/usr/bin/env python3
"""Update facade input-schema snapshots.

Usage:
    python scripts/update_facade_snapshots.py [--update-snapshots]

Without --update-snapshots: prints the current schemas (read-only).
With --update-snapshots: writes tests/contracts/snapshots/mcp_facade_input_schema.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

SNAPSHOT_PATH = (
    REPO_ROOT / "tests" / "contracts" / "snapshots" / "mcp_facade_input_schema.json"
)

# (facade_name, builder_module, builder_function)
FACADE_BUILDERS = [
    ("search", "tree_sitter_analyzer.mcp.tools.search_facade", "build_search_facade"),
    ("nav", "tree_sitter_analyzer.mcp.tools.nav_facade", "build_nav_facade"),
    (
        "structure",
        "tree_sitter_analyzer.mcp.tools.structure_facade",
        "build_structure_facade",
    ),
    ("health", "tree_sitter_analyzer.mcp.tools.health_facade", "build_health_facade"),
    ("edit", "tree_sitter_analyzer.mcp.tools.edit_facade", "build_edit_facade"),
    (
        "project",
        "tree_sitter_analyzer.mcp.tools.project_facade",
        "build_project_facade",
    ),
    ("index", "tree_sitter_analyzer.mcp.tools.index_facade", "build_index_facade"),
    ("viz", "tree_sitter_analyzer.mcp.tools.viz_facade", "build_viz_facade"),
]


def collect_schemas(project_root: str = ".") -> list[dict]:
    """Instantiate all 8 facades and collect their inputSchema."""
    import importlib

    results = []
    for facade_name, module_path, builder_fn in FACADE_BUILDERS:
        module = importlib.import_module(module_path)
        builder = getattr(module, builder_fn)
        instance = builder(project_root=project_root)
        schema = instance.get_tool_schema()
        results.append({"facade": facade_name, "schema": schema})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Update facade input-schema snapshots")
    parser.add_argument(
        "--update-snapshots",
        action="store_true",
        help="Write the snapshot file (otherwise just prints)",
    )
    args = parser.parse_args()

    schemas = collect_schemas()

    if args.update_snapshots:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(schemas, indent=2, sort_keys=True) + "\n")
        print(f"Snapshot written to {SNAPSHOT_PATH}")
    else:
        print(json.dumps(schemas, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    sys.exit(main())
