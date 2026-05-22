"""Tests for call-graph-aware change impact analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.mcp.tools.utils.call_graph_impact import (
    CallGraphImpactResult,
    FunctionImpact,
    compute_call_graph_impact,
)


class TestFunctionImpact:
    def test_to_dict_minimal(self):
        fi = FunctionImpact(name="foo", file="a.py", line=10)
        d = fi.to_dict()
        assert d["name"] == "foo"
        assert d["file"] == "a.py"
        assert d["line"] == 10
        assert d["fan_in"] == 0
        assert "upstream_callers" not in d

    def test_to_dict_with_callers(self):
        fi = FunctionImpact(
            name="bar",
            file="b.py",
            line=20,
            upstream_callers=[{"name": "caller1", "file": "c.py"}],
            fan_in=3,
        )
        d = fi.to_dict()
        assert d["fan_in"] == 3
        assert len(d["upstream_callers"]) == 1

    def test_to_dict_truncates_long_lists(self):
        fi = FunctionImpact(
            name="baz",
            file="d.py",
            line=30,
            upstream_callers=[{"name": f"caller_{i}"} for i in range(100)],
            downstream_callees=[{"name": f"callee_{i}"} for i in range(100)],
        )
        d = fi.to_dict()
        assert len(d["upstream_callers"]) == 50
        assert len(d["downstream_callees"]) == 50


class TestCallGraphImpactResult:
    def test_to_dict(self):
        r = CallGraphImpactResult(
            functions_analyzed=5,
            total_upstream=10,
            total_downstream=3,
            high_risk_functions=["a.py:main (fan_in=8)"],
            cross_file_callers={"a.py": [{"name": "x", "file": "b.py"}]},
            cross_file_callees={"a.py": [{"name": "y", "file": "c.py"}]},
            function_impacts=[{"name": "main", "file": "a.py"}],
            affected_functions_by_file={"b.py": ["x -> main"]},
        )
        d = r.to_dict()
        assert d["functions_analyzed"] == 5
        assert d["total_upstream_callers"] == 10
        assert d["total_downstream_callees"] == 3
        assert len(d["high_risk_functions"]) == 1
        assert "b.py" in d["affected_functions_by_file"]

    def test_empty(self):
        r = CallGraphImpactResult()
        d = r.to_dict()
        assert d["functions_analyzed"] == 0
        assert d["function_impacts"] == []


class TestComputeCallGraphImpact:
    def test_returns_none_for_empty_files(self):
        result = compute_call_graph_impact("/tmp/nonexistent", [])
        assert result is None

    @patch("tree_sitter_analyzer.mcp.tools.utils.call_graph_impact._build_call_graph")
    def test_returns_none_when_cg_fails(self, mock_build):
        mock_build.return_value = None
        result = compute_call_graph_impact("/tmp/nonexistent", ["a.py"])
        assert result is None

    @patch("tree_sitter_analyzer.mcp.tools.utils.call_graph_impact._build_call_graph")
    def test_basic_impact(self, mock_build):
        cg = MagicMock()
        cg.all_functions.return_value = [
            {"name": "foo", "file": "a.py", "line": 10},
            {"name": "bar", "file": "b.py", "line": 5},
        ]
        cg.callers_of.return_value = [
            {"name": "bar", "file": "b.py", "line": 7}
        ]
        cg.callees_of.return_value = []
        mock_build.return_value = cg

        result = compute_call_graph_impact("/tmp/project", ["a.py"])
        assert result is not None
        assert result.functions_analyzed == 1
        assert result.total_upstream == 1
        assert result.total_downstream == 0
        assert "b.py" in result.affected_functions_by_file

    @patch("tree_sitter_analyzer.mcp.tools.utils.call_graph_impact._build_call_graph")
    def test_high_fan_in_detected(self, mock_build):
        cg = MagicMock()
        cg.all_functions.return_value = [
            {"name": "critical_fn", "file": "core.py", "line": 42},
        ]
        cg.callers_of.return_value = [
            {"name": f"caller_{i}", "file": f"mod_{i}.py", "line": i}
            for i in range(6)
        ]
        cg.callees_of.return_value = []
        mock_build.return_value = cg

        result = compute_call_graph_impact("/tmp/project", ["core.py"])
        assert result is not None
        assert len(result.high_risk_functions) == 1
        assert "fan_in=6" in result.high_risk_functions[0]

    @patch("tree_sitter_analyzer.mcp.tools.utils.call_graph_impact._build_call_graph")
    def test_no_functions_in_changed_file(self, mock_build):
        cg = MagicMock()
        cg.all_functions.return_value = [
            {"name": "foo", "file": "other.py", "line": 10},
        ]
        mock_build.return_value = cg

        result = compute_call_graph_impact("/tmp/project", ["empty.py"])
        assert result is not None
        assert result.functions_analyzed == 0


class TestChangeImpactIntegration:
    def test_build_result_includes_call_graph(self):
        import os
        import tempfile

        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            ChangeImpactRequest,
            _build_change_impact_result,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = os.path.join(tmpdir, "src")
            os.makedirs(src_dir)
            with open(os.path.join(src_dir, "app.py"), "w") as f:
                f.write("def hello():\n    pass\n")

            with patch(
                "tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis.compute_call_graph_impact"
            ) as mock_cg:
                cg_result = CallGraphImpactResult(
                    functions_analyzed=1,
                    total_upstream=2,
                    total_downstream=0,
                    function_impacts=[{"name": "hello", "file": "src/app.py"}],
                )
                mock_cg.return_value = cg_result

                req = ChangeImpactRequest(
                    mode="diff",
                    changed_files=["src/app.py"],
                    diff_stat="1 file changed",
                    project_root=tmpdir,
                    include_tests=True,
                )
                result = _build_change_impact_result(req)
                assert "call_graph_impact" in result
                assert result["call_graph_impact"]["functions_analyzed"] == 1

    def test_build_result_without_call_graph(self):
        from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
            ChangeImpactRequest,
            _build_change_impact_result,
        )

        req = ChangeImpactRequest(
            mode="diff",
            changed_files=["README.md"],
            diff_stat="1 file changed",
            project_root=None,
            include_tests=False,
        )
        result = _build_change_impact_result(req)
        assert "call_graph_impact" not in result
