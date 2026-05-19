"""Tests for the pre-indexed AST cache (ast_cache module)."""


import pytest

from tree_sitter_analyzer.ast_cache import (
    _EXT_TO_LANG,
    ASTCache,
    _content_hash,
    _extract_symbols,
)


@pytest.fixture
def tmp_project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        "def hello():\n    print('hello')\n\nclass Foo:\n    pass\n"
    )
    (src / "util.js").write_text(
        "function add(a, b) { return a + b; }\n"
    )
    (src / "readme.md").write_text("# Readme\n")
    return tmp_path


@pytest.fixture
def cache(tmp_project):
    c = ASTCache(str(tmp_project))
    yield c
    c.close()


class TestContentHash:
    def test_deterministic(self):
        assert _content_hash("hello") == _content_hash("hello")

    def test_different_content(self):
        assert _content_hash("hello") != _content_hash("world")

    def test_bytes_input(self):
        assert _content_hash(b"hello") == _content_hash("hello")


class TestIndexFile:
    def test_index_python_file(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        result = cache.index_file(f)
        assert result["status"] == "indexed"
        assert result["symbols"] > 0

    def test_index_unsupported_language(self, cache, tmp_project):
        f = str(tmp_project / "readme.md")
        result = cache.index_file(f)
        assert result["status"] == "skipped"

    def test_index_nonexistent_file(self, cache, tmp_project):
        f = str(tmp_project / "nonexistent.py")
        result = cache.index_file(f)
        assert result["status"] == "error"

    def test_cached_on_second_index(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        result = cache.index_file(f)
        assert result["status"] == "cached"

    def test_index_with_explicit_language(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        result = cache.index_file(f, language="python")
        assert result["status"] == "indexed"


class TestIndexProject:
    def test_index_project(self, cache):
        result = cache.index_project()
        assert result["total_files"] >= 2
        assert result["indexed"] >= 2

    def test_index_project_cached(self, cache):
        cache.index_project()
        result = cache.index_project()
        assert result["cached"] >= 2

    def test_index_project_force(self, cache):
        cache.index_project()
        result = cache.index_project(force=True)
        assert result["indexed"] >= 2

    def test_index_project_max_files(self, cache):
        result = cache.index_project(max_files=1)
        assert result["total_files"] <= 1


class TestLookup:
    def test_lookup_indexed_file(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        result = cache.lookup(f)
        assert result is not None
        assert result["language"] == "python"
        assert "symbols" in result
        assert "structure" in result

    def test_lookup_missing_file(self, cache):
        result = cache.lookup("/nonexistent/file.py")
        assert result is None


class TestSearchSymbols:
    def test_search_by_name(self, cache, tmp_project):
        cache.index_project()
        results = cache.search_symbols("hello")
        assert len(results) >= 1
        assert any(r["name"] == "hello" for r in results)

    def test_search_by_language(self, cache, tmp_project):
        cache.index_project()
        results = cache.search_symbols("add", language="javascript")
        assert len(results) >= 1

    def test_search_no_results(self, cache, tmp_project):
        cache.index_project()
        results = cache.search_symbols("zzz_nonexistent_xyz")
        assert len(results) == 0


class TestStats:
    def test_stats_empty(self, cache):
        stats = cache.get_stats()
        assert stats["total_files"] == 0
        assert stats["total_symbols"] == 0

    def test_stats_after_index(self, cache):
        cache.index_project()
        stats = cache.get_stats()
        assert stats["total_files"] >= 2
        assert stats["total_symbols"] > 0
        assert "python" in stats["by_language"]


class TestInvalidate:
    def test_invalidate_existing(self, cache, tmp_project):
        f = str(tmp_project / "src" / "main.py")
        cache.index_file(f)
        assert cache.invalidate(f) is True
        assert cache.lookup(f) is None

    def test_invalidate_nonexistent(self, cache):
        assert cache.invalidate("/nonexistent.py") is False


class TestExtractSymbols:
    def test_extract_from_none_tree(self):
        result = _extract_symbols(None, "x = 1", "python")
        assert result["symbols"] == []
        assert result["node_count"] == 0


class TestExtToLang:
    def test_common_extensions(self):
        assert _EXT_TO_LANG[".py"] == "python"
        assert _EXT_TO_LANG[".js"] == "javascript"
        assert _EXT_TO_LANG[".ts"] == "typescript"
        assert _EXT_TO_LANG[".java"] == "java"
        assert _EXT_TO_LANG[".go"] == "go"
        assert _EXT_TO_LANG[".c"] == "c"
        assert _EXT_TO_LANG[".cpp"] == "cpp"


class TestDbPersistence:
    def test_cache_persists_across_instances(self, tmp_project):
        c1 = ASTCache(str(tmp_project))
        f = str(tmp_project / "src" / "main.py")
        c1.index_file(f)
        stats1 = c1.get_stats()
        c1.close()

        c2 = ASTCache(str(tmp_project), db_path=c1.db_path)
        stats2 = c2.get_stats()
        assert stats2["total_files"] == stats1["total_files"]
        c2.close()
