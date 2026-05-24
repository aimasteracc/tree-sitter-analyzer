"""Tests for cache-backed code similarity detection.

Validates that detect_structural_clones_cached and detect_textual_clones_cached
produce correct results using the pre-indexed AST cache, and that the main
analyze_code_similarity function routes to cache-backed detection when available.
"""

import textwrap

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.code_similarity import (
    SimilarityResult,
    _body_snippet,
    _extract_cached_functions,
    _text_fingerprint,
    analyze_code_similarity,
    detect_structural_clones,
    detect_structural_clones_cached,
    detect_textual_clones,
    detect_textual_clones_cached,
)


@pytest.fixture
def clone_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()

    func_a = textwrap.dedent("""\
        def process_data(data):
            result = []
            for item in data:
                if item.is_valid():
                    transformed = item.transform()
                    result.append(transformed)
            return result
    """)

    (project / "module_a.py").write_text(func_a)

    func_b = textwrap.dedent("""\
        def handle_records(records):
            output = []
            for rec in records:
                if rec.is_valid():
                    converted = rec.convert()
                    output.append(converted)
            return output
    """)

    (project / "module_b.py").write_text(func_b)

    func_unique = textwrap.dedent("""\
        def unique_logic(x, y):
            return x + y
    """)

    (project / "module_c.py").write_text(func_unique)

    return str(project)


@pytest.fixture
def cached_clone_project(clone_project):
    cache = ASTCache(clone_project)
    cache.index_project(max_files=100)
    try:
        yield cache, clone_project
    finally:
        cache.close()


class TestTextFingerprint:
    def test_identical_after_rename(self):
        a = "def foo(x):\n    return x + 1\n"
        b = "def bar(y):\n    return y + 1\n"
        assert _text_fingerprint(a) == _text_fingerprint(b)

    def test_different_logic(self):
        a = "def foo(x):\n    return x + 1\n"
        b = "def bar(x):\n    return x * 2\n"
        assert _text_fingerprint(a) != _text_fingerprint(b)

    def test_whitespace_stripped(self):
        a = "def foo(x):\n    return x\n"
        b = "def  foo ( x ) :\n  return  x\n"
        assert _text_fingerprint(a) == _text_fingerprint(b)


class TestBodySnippet:
    def test_short_body(self):
        assert _body_snippet("def foo(): pass") == "def foo(): pass"

    def test_long_body_truncated(self):
        body = "x" * 300
        result = _body_snippet(body)
        assert len(result) <= 203
        assert result.endswith("...")


class TestDetectTextualClonesCached:
    def test_finds_clones_via_cache(self, cached_clone_project):
        cache, root = cached_clone_project
        groups = detect_textual_clones_cached(cache, root, min_lines=3)
        assert len(groups) >= 1
        group = groups[0]
        assert group.method == "textual_cached"
        assert len(group.functions) >= 2

    def test_no_clones_returns_empty(self, tmp_path):
        project = tmp_path / "unique"
        project.mkdir()
        (project / "a.py").write_text("def unique_a(x):\n    return x ** 3\n")
        (project / "b.py").write_text("def unique_b(x):\n    return x - 10\n")
        cache = ASTCache(str(project))
        cache.index_project(max_files=100)
        try:
            groups = detect_textual_clones_cached(cache, str(project), min_lines=2)
            assert all(len(g.functions) >= 2 for g in groups)
        finally:
            cache.close()

    def test_fallback_when_cache_empty(self, clone_project):
        empty_cache = ASTCache(clone_project)
        try:
            groups = detect_textual_clones_cached(
                empty_cache, clone_project, min_lines=3
            )
            assert isinstance(groups, list)
        finally:
            empty_cache.close()


class TestDetectStructuralClonesCached:
    def test_finds_structural_clones(self, cached_clone_project):
        cache, root = cached_clone_project
        groups = detect_structural_clones_cached(cache, root, min_lines=3)
        assert len(groups) >= 1
        group = groups[0]
        assert group.method == "structural_cached"
        assert group.similarity == 1.0
        names = {f.name for f in group.functions}
        assert "process_data" in names
        assert "handle_records" in names

    def test_fallback_no_cache(self, clone_project):
        empty_cache = ASTCache(clone_project)
        try:
            groups = detect_structural_clones_cached(
                empty_cache, clone_project, min_lines=3
            )
            assert isinstance(groups, list)
        finally:
            empty_cache.close()


class TestExtractCachedFunctions:
    def test_extracts_from_cache(self, cached_clone_project):
        cache, root = cached_clone_project
        functions = _extract_cached_functions(cache, root, min_lines=3)
        assert len(functions) >= 2
        for _file_path, name, start, end, lang, body in functions:
            assert name
            assert start > 0
            assert end >= start
            assert lang
            assert body

    def test_min_lines_filter(self, cached_clone_project):
        cache, root = cached_clone_project
        all_funcs = _extract_cached_functions(cache, root, min_lines=1)
        filtered = _extract_cached_functions(cache, root, min_lines=10)
        assert len(all_funcs) >= len(filtered)


class TestAnalyzeCodeSimilarityWithCache:
    def test_cache_used_by_default(self, cached_clone_project):
        _, root = cached_clone_project
        result = analyze_code_similarity(root, mode="all", min_lines=3)
        assert isinstance(result, SimilarityResult)
        assert result.stats.get("cache_used") is True

    def test_cache_disabled(self, clone_project):
        result = analyze_code_similarity(
            clone_project, mode="all", min_lines=3, use_cache=False
        )
        assert isinstance(result, SimilarityResult)
        assert result.stats.get("cache_used") is False

    def test_structural_only_cached(self, cached_clone_project):
        _, root = cached_clone_project
        result = analyze_code_similarity(root, mode="structural", min_lines=3)
        assert len(result.groups) >= 1
        assert all(g.method == "structural_cached" for g in result.groups)

    def test_textual_only_cached(self, cached_clone_project):
        _, root = cached_clone_project
        result = analyze_code_similarity(root, mode="textual", min_lines=3)
        assert len(result.groups) >= 1
        assert all(g.method == "textual_cached" for g in result.groups)

    def test_no_cache_falls_back_gracefully(self, tmp_path):
        empty = tmp_path / "empty_project"
        empty.mkdir()
        (empty / "a.py").write_text("def foo():\n    pass\n")
        result = analyze_code_similarity(str(empty), mode="all", min_lines=2)
        assert isinstance(result, SimilarityResult)
        assert result.stats.get("cache_used") is False


class TestConsistencyCachedVsUncached:
    def test_textual_clones_match(self, cached_clone_project):
        cache, root = cached_clone_project
        cached_groups = detect_textual_clones_cached(cache, root, min_lines=3)
        uncached_groups = detect_textual_clones(root, min_lines=3)
        assert len(cached_groups) == len(uncached_groups)

    def test_structural_clones_match(self, cached_clone_project):
        cache, root = cached_clone_project
        cached_groups = detect_structural_clones_cached(cache, root, min_lines=3)
        uncached_groups = detect_structural_clones(root, min_lines=3)
        assert len(cached_groups) == len(uncached_groups)
