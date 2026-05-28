"""Tests for change_impact_analysis helpers — previously only indirect coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
    ChangeImpactRequest,
    _append_large_dirty_hint,
    _assess_risk,
    _build_file_impacts,
    _build_test_plan,
    _find_test_files,
    _is_runnable_test_file,
    _is_test_only_change_set,
    _load_dependency_graph,
    _test_file_matches_change,
)


class TestChangeImpactRequest:
    def test_construction(self):
        req = ChangeImpactRequest(
            mode="diff",
            changed_files=["a.py", "b.py"],
            diff_stat="2 files changed",
            project_root="/src",
            include_tests=True,
            scope_paths=["src/"],
        )
        assert req.mode == "diff"
        assert req.project_root == "/src"

    def test_default_scope_paths(self):
        req = ChangeImpactRequest(
            mode="diff",
            changed_files=[],
            diff_stat="",
            project_root="/src",
            include_tests=False,
        )
        assert req.scope_paths is None


class TestFindTestFiles:
    def test_maps_changed_to_tests(self):
        graph_nodes = {"src/foo.py", "tests/test_foo.py", "src/bar.py"}
        mapping = _find_test_files(["src/foo.py"], graph_nodes)
        assert "src/foo.py" in mapping

    def test_no_test_nodes(self):
        mapping = _find_test_files(["foo.py"], {"foo.py"})
        assert "foo.py" in mapping


class TestTestFileMatchesChange:
    def test_matching_stem(self):
        assert _test_file_matches_change("test_foo.py", "foo.py") is True

    def test_non_matching(self):
        assert _test_file_matches_change("test_bar.py", "foo.py") is False


class TestIsRunnableTestFile:
    def test_pytest_style(self):
        assert (
            _is_runnable_test_file("tests/test_example.py", {"tests/"}, ("_test.py",))
            is True
        )

    def test_conftest_excluded(self):
        assert (
            _is_runnable_test_file("tests/conftest.py", {"tests/"}, ("_test.py",))
            is False
        )

    def test_init_excluded(self):
        assert (
            _is_runnable_test_file("tests/__init__.py", {"tests/"}, ("_test.py",))
            is False
        )

    def test_non_test_file(self):
        assert (
            _is_runnable_test_file("src/example.py", {"tests/"}, ("_test.py",)) is False
        )


class TestIsTestOnlyChangeSet:
    def test_true_for_runnable_test_files(self):
        assert _is_test_only_change_set(
            ["tests/unit/test_alpha.py", "tests/unit/beta_test.py"]
        )

    def test_false_for_runtime_or_test_support_files(self):
        assert not _is_test_only_change_set(["tree_sitter_analyzer/runtime.py"])
        assert not _is_test_only_change_set(["tests/conftest.py"])
        assert not _is_test_only_change_set([])


class TestAssessRisk:
    def test_no_changes(self):
        graph = MagicMock()
        assert _assess_risk([], set(), graph) == "none"

    def test_low_risk(self):
        graph = MagicMock()
        assert _assess_risk(["a.py"], {"a.py", "b.py"}, graph) == "low"

    def test_high_risk(self):
        graph = MagicMock()
        affected = {f"file_{i}.py" for i in range(20)}
        assert _assess_risk(["a.py"], affected, graph) == "high"


class TestBuildFileImpacts:
    def test_none_graph(self):
        affected, impacts = _build_file_impacts(["a.py", "b.py"], None)
        assert affected == set()
        assert len(impacts) == 2
        assert impacts[0]["file"] == "a.py"

    def test_with_mock_graph(self):
        graph = MagicMock()
        blast = MagicMock()
        blast.forward.return_value = {"b.py", "c.py"}
        with patch(
            "tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis.BlastRadius",
            return_value=blast,
        ):
            graph.dependents_of.return_value = ["b.py"]
            affected, impacts = _build_file_impacts(["a.py"], graph)
            assert len(impacts) == 1


class TestBuildTestPlan:
    def test_include_tests_false(self):
        mapping, tests = _build_test_plan(["a.py"], None, include_tests=False)
        assert mapping == {}
        assert tests == []

    def test_none_graph(self):
        mapping, tests = _build_test_plan(["a.py"], None, include_tests=True)
        assert mapping == {}
        assert tests == []


class TestLoadDependencyGraph:
    # Perf note (2026-05-23): these two tests used to take ~21s combined
    # because ``_load_dependency_graph(None)`` falls back to ``"."``
    # (current working directory) — which is the full ~1100-file project
    # tree when run from the repo root. We were testing "None is handled
    # gracefully" but accidentally also exercising "scan 1100 files". Use
    # ``tmp_path`` (empty dir) to keep the original contract — None /
    # bogus paths return a graph not None — but in O(1).

    def test_none_root_with_empty_cwd(self, tmp_path, monkeypatch):
        # Run with cwd=tmp_path so the None-fallback hits an empty dir
        # instead of scanning the entire repo. Preserves the test intent
        # (None falls back to ".") while making it run in milliseconds.
        monkeypatch.chdir(tmp_path)
        result = _load_dependency_graph(None)
        assert result is not None

    def test_nonexistent_root(self):
        # DependencyGraph doesn't raise for nonexistent paths — returns a graph.
        # An obviously-bogus path scans nothing, so this is already fast.
        result = _load_dependency_graph("/nonexistent/path")
        assert result is not None


class TestAppendLargeDirtyHint:
    def test_small_count(self):
        assert _append_large_dirty_hint("hint", 3) == "hint"

    def test_large_count_appends(self):
        result = _append_large_dirty_hint("hint", 999)
        assert len(result) > len("hint")


class TestEnsureASTCache:
    def test_returns_none_for_none_root(self):
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            _ensure_ast_cache,
        )

        assert _ensure_ast_cache(None, ["a.py"]) is None

    def test_returns_none_for_empty_files(self):
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            _ensure_ast_cache,
        )

        assert _ensure_ast_cache("/tmp", []) is None

    def test_auto_indexes_empty_cache(self, tmp_path):
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            _ensure_ast_cache,
        )

        src = tmp_path / "example.py"
        src.write_text("def hello(): pass\n")
        cache = _ensure_ast_cache(str(tmp_path), ["example.py"])
        try:
            assert cache is not None
            stats = cache.get_stats()
            assert stats["total_files"] >= 1
        finally:
            if cache is not None:
                cache.close()


class TestEnrichWithCacheSymbols:
    def test_returns_empty_for_none_cache(self):
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            _enrich_with_cache_symbols,
        )

        assert _enrich_with_cache_symbols(["a.py"], None) == []

    def test_enriches_changed_files(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            _enrich_with_cache_symbols,
        )

        src = tmp_path / "mod.py"
        src.write_text("def foo(): pass\nclass Bar: pass\n")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(src))
        try:
            result = _enrich_with_cache_symbols(["mod.py"], cache)
            assert len(result) == 1
            assert result[0]["file"] == "mod.py"
            assert result[0]["symbol_count"] >= 2
            assert any(s["name"] == "foo" for s in result[0]["symbols"])
            assert any(s["name"] == "Bar" for s in result[0]["symbols"])
        finally:
            cache.close()


class TestFindAffectedSymbols:
    def test_returns_empty_for_none_cache(self):
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            _find_affected_symbols,
        )

        assert _find_affected_symbols({"a.py"}, None) == []

    def test_finds_symbols_in_affected_files(self, tmp_path):
        from tree_sitter_analyzer.ast_cache import ASTCache
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            _find_affected_symbols,
        )

        dep = tmp_path / "dep.py"
        dep.write_text("def helper(): pass\n")
        cache = ASTCache(str(tmp_path))
        cache.index_file(str(dep))
        try:
            result = _find_affected_symbols({"dep.py"}, cache)
            assert len(result) >= 1
            assert any(s["name"] == "helper" for s in result)
        finally:
            cache.close()


class TestSummaryOnlyFastPath:
    def test_summary_only_skips_ast_cache_enrichment(self, tmp_path, monkeypatch):
        from tree_sitter_analyzer.mcp.tools.utils import change_impact_analysis as ci

        class FakeGraph:
            _nodes = {"src/app.py", "tests/test_app.py"}

            def nodes(self):
                return sorted(self._nodes)

            def dependents_of(self, file_rel):
                return []

            def dependencies_of(self, file_rel):
                return []

            def has_node(self, file_rel):
                return file_rel in self._nodes

        monkeypatch.setattr(ci, "_load_dependency_graph", lambda _: FakeGraph())
        monkeypatch.setattr(ci, "compute_call_graph_impact", lambda *_, **__: None)

        def fail_enrichment(*args, **kwargs):
            raise AssertionError("summary-only should not sync AST cache")

        monkeypatch.setattr(ci, "_ensure_ast_cache", fail_enrichment)

        result = ci._build_change_impact_result(
            ci.ChangeImpactRequest(
                mode="diff",
                changed_files=["src/app.py"],
                diff_stat="src/app.py | 1 +",
                project_root=str(tmp_path),
                include_tests=True,
                agent_summary_only=True,
            )
        )

        assert result["success"] is True
        assert result["affected_count"] == 0
