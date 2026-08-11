"""Exact behavioral tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

requires_posix_snapshot = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


@requires_posix_snapshot
class TestAuthoritativeSnapshotOracle:
    @pytest.fixture(autouse=True)
    def _close_snapshot_capabilities(self):
        yield
        from tree_sitter_analyzer.index_snapshot import REGISTRY

        REGISTRY.close_all()

    @staticmethod
    def _certified_cache(root):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

        source = root / "sample.py"
        source.write_text("def answer():\n    return 42\n")
        cache = ASTCache(str(root))
        cache.index_file(str(source))
        stamp_full_index_manifest(cache.get_conn(), str(root))
        cache.close()

    def test_exact_paths_without_strict_marker_preserve_stale_manifest(
        self, tmp_path, monkeypatch
    ):
        from types import SimpleNamespace

        import tree_sitter_analyzer.cache.indexer as indexer
        import tree_sitter_analyzer.index_snapshot_schema as schema
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_source_snapshot import (
            make_source_scope_descriptor,
        )

        source = tmp_path / "sample.py"
        source.write_text("value = 1\n")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        conn = cache.get_conn()
        conn.execute("DELETE FROM ast_call_graph_state")
        conn.execute(
            "INSERT INTO ast_index_snapshot_manifest VALUES "
            "(1, 'root', 'source', 'index', 1, '{}', 2)"
        )
        conn.commit()
        candidate = SimpleNamespace(
            selected_entries=(SimpleNamespace(rel_path="sample.py"),),
            limited=0,
            errors=0,
        )
        stats = {"errors": 0, "changed_during_run": 0, "backfill_errors": 0}
        monkeypatch.setattr(
            schema,
            "stamp_full_index_manifest",
            lambda *_args: pytest.fail("strict-marker stamp was called"),
        )

        indexer._update_authoritative_manifest(
            cache, candidate, stats, make_source_scope_descriptor()
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
        ).fetchone()[0]
        cache.close()

        assert (stats["manifest_warning"], count) == ("CALL_GRAPH_INCOMPLETE", 1)

    def test_indexer_stamp_failure_only_records_warning(self, tmp_path, monkeypatch):
        # PR #1253 review 3755736546: failed certifiers retain later manifests.
        from types import SimpleNamespace

        import tree_sitter_analyzer.cache.indexer as indexer
        import tree_sitter_analyzer.index_snapshot_schema as schema
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.cache.callgraph_state import mark_call_graph_built
        from tree_sitter_analyzer.index_source_snapshot import (
            make_source_scope_descriptor,
        )

        source = tmp_path / "sample.py"
        source.write_text("value = 1\n")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(source))
        conn = cache.get_conn()
        mark_call_graph_built(conn)
        conn.execute(
            "INSERT INTO ast_index_snapshot_manifest VALUES "
            "(1, 'root', 'source', 'later', 1, '{}', 2)"
        )
        conn.commit()
        candidate = SimpleNamespace(
            selected_entries=(SimpleNamespace(rel_path="sample.py"),),
            limited=0,
            errors=0,
        )
        stats = {"errors": 0, "changed_during_run": 0, "backfill_errors": 0}
        monkeypatch.setattr(
            schema,
            "stamp_full_index_manifest",
            lambda *_args: (_ for _ in ()).throw(RuntimeError("busy")),
        )

        indexer._update_authoritative_manifest(
            cache, candidate, stats, make_source_scope_descriptor()
        )
        manifest = conn.execute(
            "SELECT index_fingerprint FROM ast_index_snapshot_manifest"
        ).fetchone()[0]
        cache.close()

        assert (stats["manifest_warning"], manifest) == (
            "INDEX_MANIFEST_CERTIFICATION_FAILED",
            "later",
        )

    def test_portable_full_index_succeeds_without_manifest(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.cache.indexer as indexer
        from tree_sitter_analyzer.ast_cache import ASTCache

        real_os = indexer.os

        class PortableOS:
            name = "nt"
            path = real_os.path

            def __getattr__(self, name):
                return getattr(real_os, name)

        source = tmp_path / "sample.py"
        source.write_text("value = 1\n")
        monkeypatch.setattr(indexer, "os", PortableOS())
        cache = ASTCache(str(tmp_path))
        try:
            result = cache.index_project(workers=0)
            count = int(
                cache.get_conn()
                .execute("SELECT COUNT(*) FROM ast_index_snapshot_manifest")
                .fetchone()[0]
            )
        finally:
            cache.close()

        assert result["errors"] == 0
        assert result["manifest_warning"] == "SOURCE_SCOPE_UNSUPPORTED"
        assert count == 0

    def test_manifest_stamp_rejects_unsupported_source_scope(
        self, tmp_path, monkeypatch
    ):
        import tree_sitter_analyzer.index_snapshot_schema as schema
        from tree_sitter_analyzer.ast_cache import ASTCache

        cache = ASTCache(str(tmp_path))
        try:

            class UnsupportedOS:
                name = "nt"
                path = schema.os.path

            monkeypatch.setattr(schema, "os", UnsupportedOS())
            with pytest.raises(
                sqlite3.OperationalError, match="^SOURCE_SCOPE_UNSUPPORTED$"
            ):
                schema.stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
            count = int(
                cache.get_conn()
                .execute("SELECT COUNT(*) FROM ast_index_snapshot_manifest")
                .fetchone()[0]
            )
        finally:
            cache.close()

        assert count == 0

    def test_manifest_stamp_rejects_missing_call_graph_marker(self, tmp_path):
        import tree_sitter_analyzer.index_snapshot_schema as schema
        from tree_sitter_analyzer.ast_cache import ASTCache

        cache = ASTCache(str(tmp_path))
        try:
            with pytest.raises(
                sqlite3.OperationalError, match="^CALL_GRAPH_INCOMPLETE$"
            ):
                schema.stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
            count = int(
                cache.get_conn()
                .execute("SELECT COUNT(*) FROM ast_index_snapshot_manifest")
                .fetchone()[0]
            )
        finally:
            cache.close()

        assert count == 0


@requires_posix_snapshot
@pytest.mark.asyncio
async def test_final_pinned_path_identity_mismatch_is_concurrent_writer(
    tmp_path, monkeypatch
):
    import tree_sitter_analyzer.index_snapshot as owner
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    owner.stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    cache.close()
    matches = iter((True, False))
    monkeypatch.setattr(
        owner, "_path_matches_pinned_database", lambda *_args: next(matches)
    )

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})
    assert result["oracle_reason"] == "CONCURRENT_WRITER"
    assert result["hint"].endswith("Do NOT start another index operation.")
    assert result["agent_summary"]["next_step"] == result["hint"]


@pytest.mark.asyncio
@requires_posix_snapshot
async def test_bounded_stats_runtime_failure_returns_stable_envelope(
    tmp_path, monkeypatch
):
    # PR #1253: bounded fallback exhaustion must not escape the MCP handler.
    import tree_sitter_analyzer.index_snapshot as owner

    snapshot = owner.IndexSnapshot(
        "idxsnap_test",
        "source",
        "index",
        "generation",
        "complete",
        None,
        str(tmp_path),
        1,
    )
    monkeypatch.setattr(owner, "read_existing_snapshot", lambda _root: snapshot)
    monkeypatch.setattr(
        owner,
        "read_snapshot_stats",
        lambda *_args: (_ for _ in ()).throw(
            RuntimeError("INDEX_SYMBOL_FALLBACK_BUDGET")
        ),
    )

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "unknown",
        "SNAPSHOT_READ_FAILED",
    )


@pytest.mark.asyncio
@requires_posix_snapshot
async def test_malformed_stats_schema_returns_stable_envelope(tmp_path, monkeypatch):
    # PR #1253 review thread 3755591659: SQLite schema errors never escape MCP.
    import tree_sitter_analyzer.index_snapshot as owner

    snapshot = owner.IndexSnapshot(
        "idxsnap_test",
        "source",
        "index",
        "generation",
        "complete",
        None,
        str(tmp_path),
        1,
    )
    monkeypatch.setattr(owner, "read_existing_snapshot", lambda _root: snapshot)
    monkeypatch.setattr(
        owner,
        "read_snapshot_stats",
        lambda *_args: (_ for _ in ()).throw(
            sqlite3.OperationalError("no such column")
        ),
    )

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (
        result["completeness"],
        result["oracle_reason"],
        result["total_symbols"],
    ) == (
        "unknown",
        "SNAPSHOT_READ_FAILED",
        0,
    )


@requires_posix_snapshot
@pytest.mark.parametrize(
    ("marker_id", "built"),
    [("1", 1), (1, "1"), (1, float("inf")), (1, float("nan"))],
)
@pytest.mark.asyncio
async def test_call_graph_marker_requires_exact_sqlite_integers(
    tmp_path, marker_id, built
):
    # PR #1253 thread 3756001905: coercible and non-finite markers fail closed.
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    conn = cache.get_conn()
    conn.execute("DROP TABLE ast_call_graph_state")
    conn.execute("CREATE TABLE ast_call_graph_state(id, built, built_at)")
    conn.execute(
        "INSERT INTO ast_call_graph_state VALUES (?, ?, 0)", (marker_id, built)
    )
    conn.commit()
    cache.close()

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "partial",
        "CALL_GRAPH_INCOMPLETE",
    )


def test_collect_final_stats_without_stamp_preserves_existing_manifest(tmp_path):
    # PR #1253 thread 3756001890: stats collection is never a cleanup writer.
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    cache = ASTCache(str(tmp_path))
    conn = cache.get_conn()
    conn.execute(
        "INSERT INTO ast_index_snapshot_manifest VALUES "
        "(1, 'old', 'source', 'index', 0, '{}', 2)"
    )
    conn.commit()
    cache.close()

    CodeGraphFullIndexTool(str(tmp_path))._collect_final_stats(stamp_manifest=False)

    conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
    row = conn.execute(
        "SELECT canonical_root FROM ast_index_snapshot_manifest WHERE singleton=1"
    ).fetchone()
    conn.close()
    assert row == ("old",)


def test_module_exports_exact_focused_surface() -> None:
    from tree_sitter_analyzer import index_status_certification

    assert index_status_certification.__all__ == ["build_index_status_response"]
