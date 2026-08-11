"""Fail-closed boundary tests for the index snapshot owner."""

from __future__ import annotations

import os
import sqlite3

import pytest

requires_posix_fd = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


def _fd_is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


class TestSnapshotFailureContracts:
    @staticmethod
    def _certified_cache(root):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

        source = root / "sample.py"
        source.write_text("value = 1\n")
        cache = ASTCache(str(root))
        cache.index_file(str(source))
        stamp_full_index_manifest(cache.get_conn(), str(root))
        cache.close()

    @pytest.fixture(autouse=True)
    def _close_registry(self):
        yield
        from tree_sitter_analyzer.index_snapshot import REGISTRY

        REGISTRY.close_all()

    def test_schema_validation_rejects_missing_tables(self):
        from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE ast_schema_version(version INTEGER)")
        conn.execute("INSERT INTO ast_schema_version VALUES(13)")
        with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
            validate_snapshot_schema(conn)
        conn.close()

    def test_schema_validation_rejects_missing_columns(self):
        from tree_sitter_analyzer.index_snapshot_schema import validate_snapshot_schema

        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE ast_schema_version(version INTEGER)")
        conn.execute("INSERT INTO ast_schema_version VALUES(13)")
        for table in (
            "ast_index",
            "ast_symbol_rows",
            "ast_imports",
            "edges",
            "ast_index_snapshot_manifest",
        ):
            conn.execute(f'CREATE TABLE "{table}"(wrong INTEGER)')
        with pytest.raises(ValueError, match="INCOMPATIBLE_SCHEMA"):
            validate_snapshot_schema(conn)
        conn.close()

    def test_fingerprint_row_budget_is_bounded(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_schema as schema

        self._certified_cache(tmp_path)
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        monkeypatch.setattr(schema, "_FINGERPRINT_ROW_BUDGET", -1)
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_BUDGET"):
            schema.index_fingerprint(conn, str(tmp_path.resolve()))
        conn.close()

    def test_fingerprint_byte_budget_is_bounded(self, tmp_path, monkeypatch):
        import tree_sitter_analyzer.index_snapshot_schema as schema

        self._certified_cache(tmp_path)
        conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
        monkeypatch.setattr(schema, "_FINGERPRINT_BYTE_BUDGET", -1)
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_BUDGET"):
            schema.index_fingerprint(conn, str(tmp_path.resolve()))
        conn.close()

    def test_snapshot_migration_ignores_unsupported_database(self):
        from tree_sitter_analyzer.index_snapshot_schema import apply_snapshot_migration

        class Broken:
            def executescript(self, _sql):
                raise sqlite3.OperationalError("unsupported")

        apply_snapshot_migration(Broken(), lambda *_args: None)

    def test_index_fingerprint_deadline_is_enforced(self, monkeypatch):
        from types import SimpleNamespace

        import tree_sitter_analyzer.index_snapshot_schema as schema

        monkeypatch.setattr(schema, "time", SimpleNamespace(monotonic=lambda: 2.0))
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
            schema._check_deadline(1.0)

    def test_bounded_sort_emits_multiple_canonical_runs(self, monkeypatch):
        # PR #1253: inventories larger than one run use the heap merge path.
        import tree_sitter_analyzer.index_source_snapshot as source

        monkeypatch.setattr(source, "_SORT_CHUNK_SIZE", 2)
        ordered = tuple(source._bounded_sorted((3, 1, 2), deadline=float("inf")))
        assert ordered == (1, 2, 3)

    def test_bounded_sort_checks_deadline_for_each_merged_row(self, monkeypatch):
        # PR #1253: merge work cannot extend past the advertised scan deadline.
        from types import SimpleNamespace

        import tree_sitter_analyzer.index_source_snapshot as source

        ticks = iter((0.0, 0.0, 2.0))
        monkeypatch.setattr(
            source, "time", SimpleNamespace(monotonic=lambda: next(ticks))
        )
        with pytest.raises(TimeoutError):
            tuple(source._bounded_sorted((1,), deadline=1.0))

    def test_inventory_fingerprint_checks_deadline_inside_each_row(self, monkeypatch):
        # PR #1253: per-value framing remains within the same deadline.
        from types import SimpleNamespace

        import tree_sitter_analyzer.index_source_snapshot as source

        ticks = iter((0.0, 0.0, 0.0, 2.0))
        monkeypatch.setattr(
            source, "time", SimpleNamespace(monotonic=lambda: next(ticks))
        )
        with pytest.raises(TimeoutError):
            source.inventory_fingerprint((("a", "b", "c"),), deadline=1.0)

    def test_source_capture_maps_fingerprint_deadline_to_unknown(self, monkeypatch):
        # PR #1253: canonical hashing shares the source scan deadline.
        import tree_sitter_analyzer.index_source_snapshot as source

        inventories = iter(
            [
                (("a.py", "meta|hash", "python"),),
                (("a.py", "meta", "python"),),
            ]
        )
        monkeypatch.setattr(
            source, "_inventory", lambda *_a, **_k: (next(inventories), False)
        )
        monkeypatch.setattr(
            source,
            "inventory_fingerprint",
            lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError()),
        )
        result = source.capture_current_source_snapshot(".")
        assert (result.state, result.reason) == ("unknown", "SOURCE_SCAN_DEADLINE")

    def test_recorded_fingerprint_deadline_is_fail_closed(self, monkeypatch):
        # PR #1253: writer-side canonical inventory hashing has the same deadline.
        import tree_sitter_analyzer.index_snapshot_schema as schema

        monkeypatch.setattr(
            schema,
            "recorded_source_rows",
            lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError()),
        )
        with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
            schema.source_fingerprint(sqlite3.connect(":memory:"), ".")

    def test_manifest_stamp_rejects_nonbuilt_marker(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest

        cache = ASTCache(str(tmp_path))
        try:
            conn = cache.get_conn()
            conn.execute(
                "CREATE TABLE ast_call_graph_state "
                "(id INTEGER PRIMARY KEY, built INTEGER, built_at REAL)"
            )
            conn.execute("INSERT INTO ast_call_graph_state VALUES (1, 0, 0)")
            with pytest.raises(
                sqlite3.OperationalError, match="^CALL_GRAPH_INCOMPLETE$"
            ):
                stamp_full_index_manifest(conn, str(tmp_path))
        finally:
            cache.close()

    def test_typed_fingerprint_frames_float_exactly(self):
        import struct

        from tree_sitter_analyzer.index_snapshot_schema import _typed

        raw = struct.pack(">d", 1.5)
        assert _typed((1.5,)) == b"f" + len(raw).to_bytes(8, "big") + raw
