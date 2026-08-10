"""Certified source-scope replay tests for codegraph status."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.mcp.tools.codegraph_status_tool import CodeGraphStatusTool

requires_posix_snapshot = pytest.mark.skipif(os.name != "posix", reason="GH-1253")


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
async def test_default_scope_excludes_golden_corpus_and_stays_complete(tmp_path):
    # PR #1253: status must replay the exact scope certified by full-index.
    golden = tmp_path / "tests" / "golden"
    golden.mkdir(parents=True)
    (golden / "corpus_generated.py").write_text("ignored = True\n")
    (tmp_path / "sample.py").write_text("included = True\n")
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "output_format": "json"}
    )
    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["total_files"]) == ("complete", 1)


@pytest.mark.asyncio
@requires_posix_snapshot
async def test_no_default_excludes_scope_includes_golden_corpus(tmp_path):
    # PR #1253: no_default_excludes is persisted rather than hard-coded away.
    golden = tmp_path / "tests" / "golden"
    golden.mkdir(parents=True)
    (golden / "corpus_generated.py").write_text("included = True\n")
    (tmp_path / "sample.py").write_text("also_included = True\n")
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {
            "mode": "full",
            "no_default_excludes": True,
            "output_format": "json",
        }
    )
    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["total_files"]) == ("complete", 2)


@pytest.mark.asyncio
@requires_posix_snapshot
async def test_new_file_inside_certified_scope_is_detected(tmp_path):
    # PR #1253: replaying a descriptor must detect later in-scope additions.
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "sample.py").write_text("value = 1\n")
    await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {"mode": "full", "output_format": "json"}
    )
    (tmp_path / "new.py").write_text("value = 2\n")
    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "partial",
        "SOURCE_INDEX_MISMATCH",
    )


@pytest.mark.asyncio
@requires_posix_snapshot
async def test_excluded_supported_file_beyond_certified_max_is_bounded(tmp_path):
    # PR #1253: max_files is charged before persisted exclusions during replay.
    from tree_sitter_analyzer.mcp.tools.full_index_tool import CodeGraphFullIndexTool

    (tmp_path / "a.py").write_text("value = 1\n")
    await CodeGraphFullIndexTool(str(tmp_path)).execute(
        {
            "mode": "full",
            "max_files": 1,
            "exclude_patterns": ["z_excluded.py"],
            "output_format": "json",
        }
    )
    (tmp_path / "z_excluded.py").write_text("value = 2\n")

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "unknown",
        "SOURCE_SCOPE_UNBOUNDED",
    )


@requires_posix_snapshot
@pytest.mark.asyncio
async def test_invalid_persisted_scope_cannot_certify_complete(tmp_path):
    # PR #1253: malformed discovery policy is not trusted by status.
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.index_snapshot import stamp_full_index_manifest

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    cache.get_conn().execute(
        "UPDATE ast_index_snapshot_manifest SET source_scope_descriptor = ?",
        ('{"roots":["."]}',),
    )
    cache.get_conn().commit()
    cache.close()

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "partial",
        "SOURCE_SCOPE_DESCRIPTOR_INVALID",
    )


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


def test_source_inventory_charges_actual_growth_chunks(tmp_path, monkeypatch):
    # PR #1253: a post-stat growth race cannot allocate beyond the source budget.
    import tree_sitter_analyzer.index_source_snapshot as source_owner

    (tmp_path / "sample.py").write_bytes(b"x")
    chunks = iter((b"1234", b"56"))
    monkeypatch.setattr(source_owner, "_SOURCE_BYTE_BUDGET", 5)
    monkeypatch.setattr(source_owner.os, "read", lambda _fd, _size: next(chunks))

    with pytest.raises(OverflowError):
        source_owner._inventory(str(tmp_path), float("inf"), with_content=True)


@requires_posix_snapshot
@pytest.mark.asyncio
async def test_missing_scope_manifest_cannot_certify_complete(tmp_path):
    # PR #1253: absent descriptor evidence degrades to partial.
    from tree_sitter_analyzer.ast_cache import ASTCache

    source = tmp_path / "sample.py"
    source.write_text("value = 1\n")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    cache.close()

    result = await CodeGraphStatusTool(str(tmp_path)).execute({"output_format": "json"})

    assert (result["completeness"], result["oracle_reason"]) == (
        "partial",
        "SOURCE_SCOPE_DESCRIPTOR_MISSING",
    )


@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        '{"certification_max_files":20000,"discovery_policy":"wrong","discovery_policy_version":2,"exclude_patterns":[],"no_default_excludes":false,"roots":["."]}',
        '{"certification_max_files":20000,"discovery_policy":"tsa-full-index-walk","discovery_policy_version":2,"exclude_patterns":[],"no_default_excludes":false,"roots":["../escape"]}',
        '{ "certification_max_files":20000,"discovery_policy":"tsa-full-index-walk","discovery_policy_version":2,"exclude_patterns":[],"no_default_excludes":false,"roots":["."]}',
    ],
)
def test_source_scope_descriptor_rejects_noncanonical_policy(raw):
    # PR #1253: status only replays the exact known canonical policy.
    from tree_sitter_analyzer.index_source_snapshot import parse_source_scope_descriptor

    with pytest.raises(ValueError, match="SOURCE_SCOPE_DESCRIPTOR_INVALID"):
        parse_source_scope_descriptor(raw)


def test_fingerprint_ordering_interrupts_expired_sqlite_sort(monkeypatch):
    # PR #1253: SQLite's internal ORDER BY cannot run past the deadline.

    import tree_sitter_analyzer.index_snapshot_schema as schema

    class InterruptedConnection:
        def set_progress_handler(self, callback, _steps):
            self.callback = callback

        def execute(self, _query):
            assert self.callback() == 1
            raise sqlite3.OperationalError("interrupted")

    monkeypatch.setattr(schema.time, "monotonic", lambda: 2.0)
    with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
        list(schema._deadline_ordered_rows(InterruptedConnection(), "SELECT 1", 1.0))


def test_fingerprint_ordering_maps_sqlite_interrupt_before_deadline(monkeypatch):
    # PR #1253: an interrupt is exposed through the same stable budget reason.

    import tree_sitter_analyzer.index_snapshot_schema as schema

    class InterruptedConnection:
        def set_progress_handler(self, callback, _steps):
            self.callback = callback

        def execute(self, _query):
            raise sqlite3.OperationalError("interrupted")

    monkeypatch.setattr(schema.time, "monotonic", lambda: 0.0)
    with pytest.raises(RuntimeError, match="INDEX_FINGERPRINT_DEADLINE"):
        list(schema._deadline_ordered_rows(InterruptedConnection(), "SELECT 1", 1.0))


@requires_posix_snapshot
def test_open_bound_database_reports_missing_file_after_cache_open(tmp_path):
    # PR #1253: the secure fd seam closes parent handles on an index-file race.
    from tree_sitter_analyzer.index_snapshot import _open_bound_database

    (tmp_path / ".ast-cache").mkdir()
    with pytest.raises(FileNotFoundError, match="MISSING_INDEX"):
        _open_bound_database(str(tmp_path))


def test_fingerprint_ordering_preserves_non_budget_sqlite_error(monkeypatch):
    # PR #1253: unrelated database faults are not mislabeled as deadlines.

    import tree_sitter_analyzer.index_snapshot_schema as schema

    class BrokenConnection:
        def set_progress_handler(self, callback, _steps):
            self.callback = callback

        def execute(self, _query):
            raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(schema.time, "monotonic", lambda: 0.0)
    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        list(schema._deadline_ordered_rows(BrokenConnection(), "SELECT 1", 1.0))


@requires_posix_snapshot
def test_open_bound_database_reports_missing_cache_directory(tmp_path):
    # PR #1253: secure descriptor setup closes the root on a missing cache.
    from tree_sitter_analyzer.index_snapshot import _open_bound_database

    with pytest.raises(FileNotFoundError, match="MISSING_INDEX"):
        _open_bound_database(str(tmp_path))


def test_full_index_scope_validation_rejects_mismatched_effective_excludes():
    # PR #1253: writers cannot certify a descriptor different from their walk.
    from tree_sitter_analyzer.index_source_snapshot import (
        make_source_scope_descriptor,
        validate_full_index_source_scope,
    )

    scope = make_source_scope_descriptor(certification_max_files=40_000)
    assert scope.certification_max_files == 40_000
    with pytest.raises(ValueError, match="SOURCE_SCOPE_DESCRIPTOR_MISMATCH"):
        validate_full_index_source_scope(scope, frozenset(), 20_000)
