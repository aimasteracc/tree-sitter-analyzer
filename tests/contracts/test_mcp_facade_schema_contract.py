"""Contract test: 8-facade inputSchema must match the golden snapshot.

REQ-FACADE-001, REQ-CI-002 — Phase 3 Step 1.

Run:
    pytest tests/contracts/test_mcp_facade_schema_contract.py -v

To update the snapshot after an intentional schema change:
    python scripts/update_facade_snapshots.py --update-snapshots
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "mcp_facade_input_schema.json"

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


def _load_snapshot() -> dict[str, dict]:
    """Return {facade_name: schema} from the snapshot file."""
    if not SNAPSHOT_PATH.exists():
        pytest.fail(
            f"Snapshot file missing: {SNAPSHOT_PATH}\n"
            "Run: python scripts/update_facade_snapshots.py --update-snapshots"
        )
    raw = json.loads(SNAPSHOT_PATH.read_text())
    return {entry["facade"]: entry["schema"] for entry in raw}


def _build_facade(module_path: str, builder_fn: str) -> object:
    import importlib

    module = importlib.import_module(module_path)
    builder = getattr(module, builder_fn)
    return builder(project_root=".")


def _schema_key_fields(schema: dict) -> dict:
    """Extract the fields we care about for drift detection."""
    return {
        "properties": set(schema.get("properties", {}).keys()),
        "required": set(schema.get("required", [])),
        "additionalProperties": schema.get("additionalProperties"),
    }


@pytest.mark.parametrize("facade_name,module_path,builder_fn", FACADE_BUILDERS)
def test_facade_schema_matches_snapshot(
    facade_name: str, module_path: str, builder_fn: str
) -> None:
    """inputSchema for each facade must match the golden snapshot."""
    snapshots = _load_snapshot()
    assert facade_name in snapshots, (
        f"Facade '{facade_name}' not found in snapshot. "
        "Run: python scripts/update_facade_snapshots.py --update-snapshots"
    )

    facade = _build_facade(module_path, builder_fn)
    current_schema = facade.get_tool_schema()
    snapshot_schema = snapshots[facade_name]

    current_fields = _schema_key_fields(current_schema)
    snapshot_fields = _schema_key_fields(snapshot_schema)

    added_props = current_fields["properties"] - snapshot_fields["properties"]
    removed_props = snapshot_fields["properties"] - current_fields["properties"]
    added_req = current_fields["required"] - snapshot_fields["required"]
    removed_req = snapshot_fields["required"] - current_fields["required"]

    diffs = []
    if added_props:
        diffs.append(f"  + new properties: {sorted(added_props)}")
    if removed_props:
        diffs.append(f"  - removed properties: {sorted(removed_props)}")
    if added_req:
        diffs.append(f"  + new required fields: {sorted(added_req)}")
    if removed_req:
        diffs.append(f"  - removed required fields: {sorted(removed_req)}")
    if (
        current_fields["additionalProperties"]
        != snapshot_fields["additionalProperties"]
    ):
        diffs.append(
            f"  additionalProperties changed: "
            f"{snapshot_fields['additionalProperties']} -> {current_fields['additionalProperties']}"
        )

    if diffs:
        pytest.fail(
            f"Facade '{facade_name}' inputSchema drifted from snapshot:\n"
            + "\n".join(diffs)
            + "\n\nIf this is intentional, update the snapshot:\n"
            "  python scripts/update_facade_snapshots.py --update-snapshots"
        )


def test_all_8_facades_present_in_snapshot() -> None:
    """Snapshot must contain all 8 facades — no more, no fewer."""
    snapshots = _load_snapshot()
    expected = {name for name, _, _ in FACADE_BUILDERS}
    actual = set(snapshots.keys())
    assert actual == expected, (
        f"Snapshot facade mismatch.\n"
        f"  Expected: {sorted(expected)}\n"
        f"  Actual:   {sorted(actual)}"
    )
