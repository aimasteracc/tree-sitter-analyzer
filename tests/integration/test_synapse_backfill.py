"""RED integration test for Feature 1 (Synapse): resolve-only backfill.

The implementation of ``ASTCache.index_project(resolve_only=True)`` does
not exist yet. This test pre-populates the cache with edges that look
exactly like they did before the resolver shipped (callee_resolution=
'unknown', callee_resolved_file='', callee_symbol_id=NULL), invokes the
backfill, and asserts that:

  1. The resolution columns are populated (no edge remains 'unknown' when
     we know the answer).
  2. The tree-sitter parser is NEVER invoked. Backfill must derive its
     answer purely from ast_index, ast_symbol_rows, and ast_imports — it
     must not re-parse source. This is the whole point of the path: cheap
     re-resolution after schema/policy changes.

The parse-counter monkeypatch wraps ``tree_sitter_analyzer.ast_cache.Parser
.parse_file`` so any call site (per-instance or worker) increments it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer import ast_cache as ac
from tree_sitter_analyzer.ast_cache import ASTCache


@pytest.fixture
def seeded_project(tmp_path: Path) -> Path:
    """Build a real Python project on disk and index it once, normally."""
    pkg = tmp_path / "synapse_backfill_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("# backfill test pkg\n")
    (pkg / "b.py").write_text("def baz():\n    pass\n")
    (pkg / "a.py").write_text("from .b import baz\n\ndef caller():\n    baz()\n")
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project()
    finally:
        cache.close()
    return tmp_path


def _reset_resolution_columns(cache: ASTCache) -> None:
    """Force every edge back to 'unknown' so backfill has work to do.

    This simulates the migration-time state: the new columns exist (the
    schema migration ran), but they are all at default. Without this the
    backfill could no-op and the test would still pass.
    """
    conn = cache._get_conn()
    conn.execute(
        "UPDATE edges SET callee_resolution = 'unknown', "
        "callee_resolved_file = '', callee_symbol_id = NULL WHERE kind = 'calls'"
    )
    conn.commit()


@pytest.mark.integration
def test_backfill_no_reparse(
    seeded_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resolve_only=True populates the columns without calling the parser."""
    cache = ASTCache(str(seeded_project))
    try:
        _reset_resolution_columns(cache)

        # Wrap Parser.parse_file with a counting sentinel. Any call —
        # serial OR worker path — should surface here, because workers
        # inherit the module-level symbol when spawned via fork on POSIX.
        # On spawn-based platforms the worker imports the module fresh,
        # so the resolve-only path MUST avoid going through the worker
        # pool at all. Either way: zero calls is the spec.
        calls: list[tuple[str, str | None]] = []
        real_parse_file = ac.Parser.parse_file

        def counting_parse(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            calls.append((str(args[0]) if args else "", kwargs.get("language")))
            return real_parse_file(self, *args, **kwargs)

        monkeypatch.setattr(ac.Parser, "parse_file", counting_parse)

        result = cache.index_project(resolve_only=True)

        # Spec: the resolver wrote at least one non-'unknown' row.
        conn = cache._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM edges "
            "WHERE kind = 'calls' AND callee_resolution != 'unknown'"
        ).fetchone()
        assert row["c"] > 0, (
            "resolve_only=True must populate at least one edge's "
            "resolution column — got zero, so the backfill is a no-op."
        )

        # Spec: the cross-file edge specifically resolved to b.py.
        edge = conn.execute(
            "SELECT callee_resolution, callee_resolved_file "
            "FROM edges WHERE kind = 'calls' AND callee_name = 'baz'"
        ).fetchone()
        assert edge is not None
        assert edge["callee_resolution"] == "project"
        assert edge["callee_resolved_file"].endswith("b.py")

        # Spec: parser was NOT invoked. This is the load-bearing assertion.
        assert calls == [], (
            f"resolve_only=True must not call Parser.parse_file; got "
            f"{len(calls)} calls: {calls[:3]}"
        )

        # And the response should clearly indicate the mode used.
        assert isinstance(result, dict)
        # 'mode_used' or a dedicated 'resolve_only' flag — either signal
        # is acceptable, but SOMETHING must distinguish this from a full
        # index so agents can detect the cheap path.
        mode = str(result.get("mode_used") or result.get("mode") or "")
        assert "resolve" in mode.lower() or result.get("resolve_only") is True, (
            f"index_project(resolve_only=True) response must advertise the "
            f"mode, got: {result!r}"
        )
    finally:
        cache.close()
