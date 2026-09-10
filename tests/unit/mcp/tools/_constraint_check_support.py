"""Shared fixtures for constraint-check MCP tool tests."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

import tree_sitter_analyzer.diff_snapshot_registry as snapshots
from tests.unit._diff_snapshot_support import install_fake_snapshot_materializer


def run(coro):
    """Drive a coroutine to completion under pytest's per-test event loop."""
    return asyncio.run(coro)


def init_violations_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ast_constraint_violations (
                rule_id TEXT NOT NULL, caller_file TEXT NOT NULL,
                caller_name TEXT NOT NULL, caller_line INTEGER NOT NULL,
                callee_name TEXT NOT NULL, callee_file TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL, detected_at INTEGER NOT NULL,
                PRIMARY KEY (rule_id, caller_file, caller_line, callee_name)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def seed_violation(
    db_path: Path,
    *,
    rule_id: str,
    caller_file: str,
    callee_file: str,
    severity: str,
    caller_line: int = 1,
    callee_name: str = "callee_fn",
    caller_name: str = "caller_fn",
) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO ast_constraint_violations
                (rule_id, caller_file, caller_name, caller_line,
                 callee_name, callee_file, severity, detected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                rule_id,
                caller_file,
                caller_name,
                caller_line,
                callee_name,
                callee_file,
                severity,
                int(time.time()),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def stage_minimal_constraints(project: Path) -> None:
    (project / "architectural-constraints.yml").write_text(
        """
version: 1
constraints:
  - id: test-rule
    severity: error
    rule: forbid
    from: "src/a/**"
    to: "src/b/**"
    reason: "Test fixture rule."
""".lstrip()
    )


def make_tool(project_root: Path):
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ConstraintCheckTool

    tool = ConstraintCheckTool(str(project_root))
    tool.set_project_path(str(project_root))
    return tool


def create_frozen_scope(
    monkeypatch, project: Path, paths: list[str], *, source_scope=None
):
    from contextlib import contextmanager
    from types import SimpleNamespace

    import tree_sitter_analyzer.index_snapshot as index_snapshots
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    source_scope = source_scope or make_source_scope_descriptor()
    index_snapshots.REGISTRY.close_all()
    install_fake_snapshot_materializer(monkeypatch, project)
    registry = snapshots.DiffSnapshotRegistry()
    monkeypatch.setattr(snapshots, "REGISTRY", registry)
    created = registry.create(str(project), "diff", paths)
    assert created["success"] is True

    @contextmanager
    def lease(_root):
        yield SimpleNamespace(
            snapshot_id="is_test",
            completeness="complete",
            source_generation=created["source_generation"],
            reason=None,
            canonical_root=str(project.resolve()),
            index_fingerprint="sha256:" + "1" * 64,
            source_scope=source_scope,
        )

    @contextmanager
    def acquire(_snapshot_id, _root, _generation):
        conn = sqlite3.connect(project / ".ast-cache" / "index.db")
        try:
            yield SimpleNamespace(), conn
        finally:
            conn.close()

    monkeypatch.setattr(index_snapshots, "lease_existing_snapshot", lease)
    monkeypatch.setattr(index_snapshots, "acquire_index_snapshot", acquire)
    return registry, created


def frozen_arguments(created: dict[str, object]) -> dict[str, object]:
    return {
        "persist": False,
        "diff_snapshot_id": created["diff_snapshot_id"],
        "scope_paths": created["assessed_scope_paths"],
        "output_format": "json",
    }


def edges_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE edges(kind TEXT)")
    conn.execute("INSERT INTO edges VALUES ('calls')")
    conn.commit()
    conn.close()
