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
