"""Pin the ``mode_used`` field on ``ASTCache.index_project()`` output.

Background
----------
Until 2026-05-23 ``ast_cache --mode index`` returned only counts
(``indexed`` / ``cached`` / ``errors`` / ``skipped``) with no way for
an agent to tell whether it had just run a full or incremental index.

The dogfood verification (docs/internal/TRUST_BUT_VERIFY_2026-05-23.md)
showed the project being claimed to have 1382 files but the cache
holding only 1263 because no-one had ever run ``--force`` after the
new modules landed. Agents were silently working off stale data.

We now report ``mode_used = "full" | "incremental"`` so the agent can
print/log it and decide whether to retry with force when results look
short. This regression test guards against the field disappearing.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.ast_cache import ASTCache


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "a.py").write_text("def a(): return 1\n")
    (tmp_path / "b.py").write_text("def b(): return 2\n")
    return tmp_path


def test_default_index_reports_incremental_mode(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache = ASTCache(str(project))
    try:
        result = cache.index_project(max_files=10)
        assert result.get("mode_used") == "incremental", (
            f"default index_project should report mode_used='incremental', "
            f"got {result.get('mode_used')!r}"
        )
    finally:
        cache.close()


def test_force_index_reports_full_mode(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    cache = ASTCache(str(project))
    try:
        result = cache.index_project(max_files=10, force=True)
        assert result.get("mode_used") == "full", (
            f"force=True should report mode_used='full', got {result.get('mode_used')!r}"
        )
    finally:
        cache.close()


def test_incremental_skips_unchanged_files(tmp_path: Path) -> None:
    """On second incremental call, all files should be cached, none re-indexed."""
    project = _make_project(tmp_path)
    cache = ASTCache(str(project))
    try:
        first = cache.index_project(max_files=10)
        assert first["indexed"] == 2
        assert first["cached"] == 0

        second = cache.index_project(max_files=10)
        assert second["indexed"] == 0, (
            "second incremental should re-use cache for unchanged files"
        )
        assert second["cached"] == 2
        assert second.get("mode_used") == "incremental"
    finally:
        cache.close()


def test_force_re_indexes_everything(tmp_path: Path) -> None:
    """``force=True`` must wipe the index and re-parse every file."""
    project = _make_project(tmp_path)
    cache = ASTCache(str(project))
    try:
        cache.index_project(max_files=10)  # warm
        forced = cache.index_project(max_files=10, force=True)
        assert forced["indexed"] == 2
        assert forced["cached"] == 0
        assert forced.get("mode_used") == "full"
    finally:
        cache.close()
