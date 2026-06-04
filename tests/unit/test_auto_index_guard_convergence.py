"""Cold-start fast path: ensure_indexed must not re-run a converged resolve.

A fully-indexed, unchanged cache is already queryable. The cross-file resolve
pass converges in one pass and is re-run by the indexing path on every file
change, so re-running it on a cold ``ensure_indexed`` when the index is
unchanged is a ~40 s no-op that blocks the first retrieval. These tests pin the
convergence fingerprint + skip behaviour.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer._ast_cache_unresolved import (
    index_resolution_fingerprint,
    resolution_converged,
)
from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.utils import auto_index_guard


def _project(root: Path) -> None:
    (root / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (root / "b.py").write_text(
        "from a import f\n\ndef g():\n    return f()\n", encoding="utf-8"
    )
    # A class extending an EXTERNAL base keeps pending_unresolved_count > 0
    # (it never resolves — base not in the project), so the OLD cold-start path
    # would re-run the resolve-only pass on every ensure_indexed. This is what
    # the convergence skip must short-circuit.
    (root / "c.py").write_text("class C(Exception):\n    pass\n", encoding="utf-8")


def test_index_project_marks_resolution_converged(tmp_path: Path) -> None:
    _project(tmp_path)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(max_files=10, workers=0)
        # _post_index_backfill records the convergence fingerprint.
        assert resolution_converged(cache.get_conn()) is True
        assert index_resolution_fingerprint(cache.get_conn())
    finally:
        cache.close()


def test_converged_false_after_a_file_is_reindexed(tmp_path: Path) -> None:
    _project(tmp_path)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(max_files=10, workers=0)
        assert resolution_converged(cache.get_conn()) is True
        # Re-index one file → indexed_at moves → fingerprint differs → the stored
        # convergence marker no longer matches, so a resolve is warranted again.
        time.sleep(0.01)
        (tmp_path / "a.py").write_text(
            "def f():\n    return 2\n\ndef h():\n    return 3\n", encoding="utf-8"
        )
        cache.index_file(str(tmp_path / "a.py"))
        assert resolution_converged(cache.get_conn()) is False
    finally:
        cache.close()


def test_ensure_indexed_skips_resolve_when_converged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(max_files=10, workers=0)
    finally:
        cache.close()

    auto_index_guard.reset()
    resolve_only_calls: list[int] = []
    real_index_project = ASTCache.index_project

    def spy(self: Any, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get("resolve_only"):
            resolve_only_calls.append(1)
        return real_index_project(self, *args, **kwargs)

    monkeypatch.setattr(ASTCache, "index_project", spy)
    try:
        cache = auto_index_guard.ensure_indexed(str(tmp_path), max_files=20)
        assert cache is not None
        # Converged → the cold path must NOT run a resolve-only pass.
        assert resolve_only_calls == []
    finally:
        auto_index_guard.reset()


def test_ensure_indexed_resolves_when_not_converged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path)
    cache = ASTCache(str(tmp_path))
    try:
        cache.index_project(max_files=10, workers=0)
        # Wipe the convergence marker to simulate an index built without the
        # final mark (legacy cache / partial build).
        cache.get_conn().execute("DROP TABLE IF EXISTS ast_resolve_state")
        cache.get_conn().commit()
        assert resolution_converged(cache.get_conn()) is False
    finally:
        cache.close()

    auto_index_guard.reset()
    resolve_only_calls: list[int] = []
    real_index_project = ASTCache.index_project

    def spy(self: Any, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get("resolve_only"):
            resolve_only_calls.append(1)
        return real_index_project(self, *args, **kwargs)

    monkeypatch.setattr(ASTCache, "index_project", spy)
    try:
        cache = auto_index_guard.ensure_indexed(str(tmp_path), max_files=20)
        assert cache is not None
        # Not converged → resolve runs once, and the marker is then persisted.
        assert resolution_converged(cache.get_conn()) is True
    finally:
        auto_index_guard.reset()
