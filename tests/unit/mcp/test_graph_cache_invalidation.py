"""Regression tests for H4 — graph tools must invalidate caches on file edit.

CodeGraphCallTool, DependencyAnalysisTool, and SymbolLineageTool used to
cache their underlying graphs forever once built, returning stale data
after in-place file edits. The H4 fix introduces a cheap fingerprint
(file_count + max_mtime_ns) scanned on every call to detect changes.

Each test runs the documented "cold → warm → touch → rebuilt" lifecycle.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools._graph_cache_fingerprint import (
    GraphFingerprint,
    compute_graph_fingerprint,
)
from tree_sitter_analyzer.mcp.tools.call_graph_tool import CodeGraphCallTool
from tree_sitter_analyzer.mcp.tools.dependency_analysis_tool import (
    DependencyAnalysisTool,
)
from tree_sitter_analyzer.mcp.tools.symbol_lineage_tool import SymbolLineageTool


def _make_small_python_project(root: Path) -> Path:
    """Create a tiny but real python project so the graphs have content."""
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "a.py").write_text(
        "from .b import bar\ndef foo():\n    return bar()\n"
    )
    (root / "pkg" / "b.py").write_text("def bar():\n    return 1\n")
    return root


@pytest.fixture
def project_root() -> Path:
    with tempfile.TemporaryDirectory(prefix="h4_proj_") as tmp:
        root = Path(tmp)
        _make_small_python_project(root)
        yield root


# ============================================================
# Fingerprint primitive
# ============================================================


class TestGraphFingerprint:
    def test_changes_on_modify(self, project_root: Path) -> None:
        """Touching a file's mtime must change the fingerprint."""
        fp1 = compute_graph_fingerprint(str(project_root))
        time.sleep(0.05)  # ensure mtime granularity
        os.utime(project_root / "pkg" / "a.py")
        fp2 = compute_graph_fingerprint(str(project_root))
        assert fp1 != fp2
        assert fp1.file_count == fp2.file_count
        assert fp2.max_mtime_ns > fp1.max_mtime_ns

    def test_changes_on_add_remove(self, project_root: Path) -> None:
        """Adding a file must bump file_count."""
        fp1 = compute_graph_fingerprint(str(project_root))
        new_file = project_root / "pkg" / "c.py"
        new_file.write_text("def baz(): pass\n")
        fp2 = compute_graph_fingerprint(str(project_root))
        assert fp2.file_count == fp1.file_count + 1
        new_file.unlink()
        fp3 = compute_graph_fingerprint(str(project_root))
        assert fp3.file_count == fp1.file_count

    def test_idempotent_when_unchanged(self, project_root: Path) -> None:
        """Calling twice without edits returns the same fingerprint."""
        fp1 = compute_graph_fingerprint(str(project_root))
        fp2 = compute_graph_fingerprint(str(project_root))
        assert fp1 == fp2

    def test_handles_missing_root(self) -> None:
        """Scan over a non-existent root must not raise."""
        fp = compute_graph_fingerprint("/this/path/should/not/exist/abc")
        assert isinstance(fp, GraphFingerprint)
        assert fp.is_empty()


# ============================================================
# H4 — CodeGraphCallTool
# ============================================================


class TestCallGraphCacheInvalidatesOnFileChange:
    def test_call_graph_cache_invalidates_on_file_change(
        self, project_root: Path
    ) -> None:
        """Cold build → warm reuse → mtime touch → rebuilt."""
        tool = CodeGraphCallTool(project_root=str(project_root))

        # Cold build
        r1 = asyncio.run(tool.execute({"mode": "summary", "output_format": "json"}))
        assert r1.get("cache_invalidated_reason") == "cold"
        cold_graph = tool._call_graph
        assert cold_graph is not None

        # Warm reuse
        r2 = asyncio.run(tool.execute({"mode": "summary", "output_format": "json"}))
        assert r2.get("cache_invalidated_reason") is None
        assert tool._call_graph is cold_graph

        # Touch a source file mtime
        time.sleep(0.05)
        os.utime(project_root / "pkg" / "a.py")

        # Should invalidate and rebuild
        r3 = asyncio.run(tool.execute({"mode": "summary", "output_format": "json"}))
        assert r3.get("cache_invalidated_reason") == "source_modified", (
            f"expected source_modified, got {r3.get('cache_invalidated_reason')}"
        )
        assert tool._call_graph is not cold_graph

    def test_call_graph_cache_age_reported(self, project_root: Path) -> None:
        """cache_age_s should be present and grow on warm reuse."""
        tool = CodeGraphCallTool(project_root=str(project_root))
        r1 = asyncio.run(tool.execute({"mode": "summary", "output_format": "json"}))
        assert "cache_age_s" in r1
        time.sleep(0.05)
        r2 = asyncio.run(tool.execute({"mode": "summary", "output_format": "json"}))
        # On warm reuse age must be larger than at cold-build time.
        assert r2["cache_age_s"] > r1["cache_age_s"]


# ============================================================
# H4 — DependencyAnalysisTool
# ============================================================


class TestDependencyAnalysisCacheInvalidatesOnFileChange:
    def test_dep_graph_cache_invalidates_on_file_change(
        self, project_root: Path
    ) -> None:
        tool = DependencyAnalysisTool(project_root=str(project_root))

        r1 = asyncio.run(tool.execute({"mode": "summary", "output_format": "json"}))
        assert r1.get("cache_invalidated_reason") == "cold"
        cold_graph = tool._graph

        r2 = asyncio.run(tool.execute({"mode": "summary", "output_format": "json"}))
        assert r2.get("cache_invalidated_reason") is None
        assert tool._graph is cold_graph

        time.sleep(0.05)
        os.utime(project_root / "pkg" / "a.py")

        r3 = asyncio.run(tool.execute({"mode": "summary", "output_format": "json"}))
        assert r3.get("cache_invalidated_reason") == "source_modified"
        assert tool._graph is not cold_graph


# ============================================================
# H4 — SymbolLineageTool
# ============================================================


class TestSymbolLineageCacheInvalidatesOnFileChange:
    def test_symbol_lineage_cache_invalidates_on_file_change(
        self, project_root: Path
    ) -> None:
        tool = SymbolLineageTool(project_root=str(project_root))

        r1 = asyncio.run(tool.execute({"symbol": "bar", "output_format": "json"}))
        assert r1.get("cache_invalidated_reason") == "cold"
        assert r1.get("from_cache") is False
        cold_graph = tool._dep_graph

        # Warm reuse should be served from the per-symbol cache.
        r2 = asyncio.run(tool.execute({"symbol": "bar", "output_format": "json"}))
        assert r2.get("from_cache") is True
        assert tool._dep_graph is cold_graph

        time.sleep(0.05)
        os.utime(project_root / "pkg" / "a.py")

        r3 = asyncio.run(tool.execute({"symbol": "bar", "output_format": "json"}))
        # Rebuild must wipe the symbol cache too, so from_cache should be
        # False even though the same symbol was queried before.
        assert r3.get("cache_invalidated_reason") == "source_modified"
        assert r3.get("from_cache") is False
        assert tool._dep_graph is not cold_graph


# ============================================================
# H4 — DependencyGraph._cache_key_for now uses the fingerprint
# ============================================================


class TestDependencyGraphGlobalCacheRespectsFingerprint:
    def test_global_cache_invalidates_on_file_mtime(self, project_root: Path) -> None:
        from tree_sitter_analyzer.project_graph import DependencyGraph

        g1 = DependencyGraph(str(project_root))

        time.sleep(0.05)
        os.utime(project_root / "pkg" / "a.py")

        g2 = DependencyGraph(str(project_root))
        # Different fingerprints -> different cache keys -> different objects.
        assert g2 is not g1
