"""Integration test: AST cache index -> query -> invalidate lifecycle."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A tiny project with one Python file."""
    (tmp_path / "sample.py").write_text(
        textwrap.dedent("""\
        class Foo:
            def bar(self):
                return 42
    """)
    )
    return tmp_path


@pytest.fixture
def cache(project: Path) -> ASTCache:
    c = ASTCache(str(project))
    yield c
    c.close()


class TestASTCacheLifecycle:
    def test_index_and_retrieve(self, cache: ASTCache, project: Path) -> None:
        """Indexing a file makes it visible via get_functions()."""
        result = cache.index_file(str(project / "sample.py"), language="python")
        assert result.get("status") == "indexed"
        funcs = cache.get_functions()
        names = [f["name"] for f in funcs]
        assert "bar" in names

    def test_cache_miss_empty_project(self, tmp_path: Path) -> None:
        """get_functions() on an empty cache returns an empty list."""
        c = ASTCache(str(tmp_path))
        try:
            assert len(c.get_functions()) == 0
        finally:
            c.close()

    def test_invalidate_removes_entry(self, cache: ASTCache, project: Path) -> None:
        """Invalidating a file removes it from the index."""
        fp = str(project / "sample.py")
        cache.index_file(fp, language="python")
        assert len(cache.get_functions()) > 0
        removed = cache.invalidate(fp)
        assert removed is True
        assert len(cache.get_functions()) == 0

    def test_double_index_replaces_entry(self, cache: ASTCache, project: Path) -> None:
        """Re-indexing an updated file replaces the cached version."""
        fp = str(project / "sample.py")
        cache.index_file(fp, language="python")
        (project / "sample.py").write_text("def new_func(): pass\n")
        cache.index_file(fp, language="python")
        names = [f["name"] for f in cache.get_functions()]
        assert "new_func" in names

    def test_stats_reflect_indexed_files(self, cache: ASTCache, project: Path) -> None:
        """get_stats() shows at least one file after indexing."""
        cache.index_file(str(project / "sample.py"), language="python")
        stats = cache.get_stats()
        assert stats.get("total_files", 0) >= 1
