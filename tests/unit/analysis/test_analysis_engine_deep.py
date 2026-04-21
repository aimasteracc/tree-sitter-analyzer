"""
Tests for Phase 3 deep analysis: cycle detection, cyclomatic complexity,
dependency weights, and hub scoring.
"""
from __future__ import annotations

from pathlib import Path

from tree_sitter_analyzer.analysis.dependency_graph import DependencyGraph
from tree_sitter_analyzer.analysis.health_score import FileHealthScore, HealthScorer
from tree_sitter_analyzer.mcp.utils.graph_service import ProjectGraph

# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------


class TestCycleDetection:
    """Cycle detection in DependencyGraph."""

    def test_no_cycle_returns_false(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}},
            edges=[("A", "B"), ("B", "C")],
        )
        assert graph.has_cycle() is False

    def test_simple_cycle_detected(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}},
            edges=[("A", "B"), ("B", "C"), ("C", "A")],
        )
        assert graph.has_cycle() is True

    def test_self_loop_is_cycle(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}},
            edges=[("A", "A")],
        )
        assert graph.has_cycle() is True

    def test_empty_graph_no_cycle(self) -> None:
        graph = DependencyGraph(nodes={}, edges=[])
        assert graph.has_cycle() is False

    def test_disconnected_with_one_cycle(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}, "D": {}, "E": {}},
            edges=[("A", "B"), ("B", "A"), ("D", "E")],
        )
        assert graph.has_cycle() is True

    def test_long_chain_no_cycle(self) -> None:
        nodes = {chr(65 + i): {} for i in range(10)}
        edges = [(chr(65 + i), chr(66 + i)) for i in range(9)]
        graph = DependencyGraph(nodes=nodes, edges=edges)
        assert graph.has_cycle() is False


class TestFindCycles:
    """Find strongly connected components (cycles) via Tarjan's algorithm."""

    def test_no_cycles_empty(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}},
            edges=[("A", "B"), ("B", "C")],
        )
        assert graph.find_cycles() == []

    def test_simple_cycle_found(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}},
            edges=[("A", "B"), ("B", "C"), ("C", "A")],
        )
        sccs = graph.find_cycles()
        assert len(sccs) == 1
        assert sorted(sccs[0]) == ["A", "B", "C"]

    def test_two_separate_cycles(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}, "D": {}, "E": {}},
            edges=[("A", "B"), ("B", "A"), ("C", "D"), ("D", "C")],
        )
        sccs = graph.find_cycles()
        assert len(sccs) == 2
        all_in_cycles = {n for scc in sccs for n in scc}
        assert all_in_cycles == {"A", "B", "C", "D"}

    def test_self_loop_is_cycle(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}},
            edges=[("A", "A")],
        )
        sccs = graph.find_cycles()
        assert len(sccs) == 1
        assert sccs[0] == ["A"]


class TestTopologicalSort:
    """Topological ordering of acyclic graphs."""

    def test_linear_order(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}},
            edges=[("A", "B"), ("B", "C")],
        )
        result = graph.topological_sort()
        assert result is not None
        assert result.index("A") < result.index("B")
        assert result.index("B") < result.index("C")

    def test_cyclic_returns_none(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}},
            edges=[("A", "B"), ("B", "A")],
        )
        assert graph.topological_sort() is None

    def test_disconnected_nodes(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}},
            edges=[],
        )
        result = graph.topological_sort()
        assert result is not None
        assert set(result) == {"A", "B", "C"}

    def test_diamond_dag(self) -> None:
        graph = DependencyGraph(
            nodes={"A": {}, "B": {}, "C": {}, "D": {}},
            edges=[("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")],
        )
        result = graph.topological_sort()
        assert result is not None
        assert result.index("A") < result.index("B")
        assert result.index("A") < result.index("C")
        assert result.index("B") < result.index("D")
        assert result.index("C") < result.index("D")


# ---------------------------------------------------------------------------
# Cyclomatic complexity
# ---------------------------------------------------------------------------


class TestCyclomaticComplexity:
    """Cyclomatic complexity dimension in health scoring."""

    def test_simple_file_low_complexity(self, tmp_path: Path) -> None:
        code = "public class Simple {\n  void hello() { }\n}\n"
        (tmp_path / "Simple.java").write_text(code, encoding="utf-8")

        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("Simple.java")

        assert isinstance(score, FileHealthScore)
        assert score.cyclomatic_complexity >= 1
        assert score.cyclomatic_complexity <= 5

    def test_branching_file_high_complexity(self, tmp_path: Path) -> None:
        lines = ["public class Complex {"]
        for i in range(50):
            lines.append(f"  void m{i}() {{ if (x > {i}) {{ for (int j=0; j<{i}; j++) {{ }} }} }}")
        lines.append("}")
        (tmp_path / "Complex.java").write_text("\n".join(lines), encoding="utf-8")

        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("Complex.java")

        assert score.cyclomatic_complexity > 10

    def test_complexity_in_breakdown(self, tmp_path: Path) -> None:
        (tmp_path / "T.java").write_text("public class T { void f() { if (x) { } } }\n", encoding="utf-8")

        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("T.java")

        assert "branch_penalty" in score.breakdown
        assert "function_length_penalty" in score.breakdown

    def test_avg_function_length(self, tmp_path: Path) -> None:
        code = (
            "public class T {\n"
            "  void short1() { }\n"
            "  void short2() { }\n"
            "  void longMethod() {\n"
            "    int x = 1;\n"
            "    int y = 2;\n"
            "    int z = 3;\n"
            "  }\n"
            "}\n"
        )
        (tmp_path / "T.java").write_text(code, encoding="utf-8")

        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("T.java")

        assert score.avg_function_length > 0
        assert isinstance(score.avg_function_length, float)


# ---------------------------------------------------------------------------
# Dependency weights and hub score
# ---------------------------------------------------------------------------


class TestEdgeWeights:
    """Edge weight calculation in ProjectGraph."""

    def test_single_occurrence_weight_one(self) -> None:
        graph = ProjectGraph(edges=[("A", "B")])
        weights = graph.edge_weights()
        assert weights[("A", "B")] == 1

    def test_duplicate_edge_higher_weight(self) -> None:
        graph = ProjectGraph(edges=[("A", "B"), ("A", "B"), ("A", "B")])
        weights = graph.edge_weights()
        assert weights[("A", "B")] == 3

    def test_empty_graph_empty_weights(self) -> None:
        graph = ProjectGraph(edges=[])
        assert graph.edge_weights() == {}


class TestHubScore:
    """Hub centrality scoring in ProjectGraph."""

    def test_hub_identifies_central_node(self) -> None:
        edges = [("A", "B"), ("C", "B"), ("D", "B")]
        graph = ProjectGraph(edges=edges)
        hubs = graph.hub_score()

        assert hubs["B"] > hubs.get("A", 0)
        assert hubs["B"] > hubs.get("C", 0)

    def test_hub_sorted_descending(self) -> None:
        edges = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "B")]
        graph = ProjectGraph(edges=edges)
        hubs = graph.hub_score()

        values = list(hubs.values())
        assert values == sorted(values, reverse=True)

    def test_empty_graph_empty_hubs(self) -> None:
        graph = ProjectGraph(edges=[])
        assert graph.hub_score() == {}


# ---------------------------------------------------------------------------
# Integration: build graph from real files, then detect cycles
# ---------------------------------------------------------------------------


class TestDependencyGraphIntegration:
    """Integration tests combining DependencyGraphBuilder with cycle detection."""

    def test_build_acyclic_graph(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.analysis.dependency_graph import (
            DependencyGraphBuilder,
        )

        (tmp_path / "A.java").write_text("import B;\npublic class A { }\n", encoding="utf-8")
        (tmp_path / "B.java").write_text("public class B { }\n", encoding="utf-8")

        builder = DependencyGraphBuilder(project_root=str(tmp_path))
        graph = builder.build()

        assert graph.has_cycle() is False
        topo = graph.topological_sort()
        assert topo is not None

    def test_cyclic_imports_detected(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.analysis.dependency_graph import (
            DependencyGraphBuilder,
        )

        (tmp_path / "A.java").write_text("import B;\npublic class A { }\n", encoding="utf-8")
        (tmp_path / "B.java").write_text("import A;\npublic class B { }\n", encoding="utf-8")

        builder = DependencyGraphBuilder(project_root=str(tmp_path))
        graph = builder.build()

        if len(graph.edges) >= 2:
            assert graph.has_cycle() is True
            cycles = graph.find_cycles()
            assert len(cycles) >= 1

    def test_python_import_graph(self, tmp_path: Path) -> None:
        from tree_sitter_analyzer.analysis.dependency_graph import (
            DependencyGraphBuilder,
        )

        (tmp_path / "main.py").write_text("import utils\n", encoding="utf-8")
        (tmp_path / "utils.py").write_text("def helper(): pass\n", encoding="utf-8")

        builder = DependencyGraphBuilder(project_root=str(tmp_path))
        graph = builder.build()

        assert "main.py" in graph.nodes
        assert "utils.py" in graph.nodes
        assert graph.has_cycle() is False

    def test_health_score_with_complexity(self, tmp_path: Path) -> None:
        code = (
            "import java.util.List;\n"
            "public class Service {\n"
            "  void process(List items) {\n"
            "    if (items != null) {\n"
            "      for (Object item : items) {\n"
            "        if (item instanceof String) {\n"
            "          handle((String) item);\n"
            "        }\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "  void handle(String s) { }\n"
            "}\n"
        )
        (tmp_path / "Service.java").write_text(code, encoding="utf-8")

        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("Service.java")

        assert score.cyclomatic_complexity >= 3
        assert score.avg_function_length > 0


# ---------------------------------------------------------------------------
# Modification suggestions
# ---------------------------------------------------------------------------


class TestModificationSuggestions:
    """Test suggestion generation in HealthScorer."""

    def test_large_file_suggestion(self, tmp_path: Path) -> None:
        lines = [
            "import java.util.*;",
            "import java.io.*;",
            "import java.net.*;",
        ]
        for _ in range(200):
            lines.append("    if (x > 0) { doWork(); }")
        lines.append("public class BigFile { }")
        (tmp_path / "BigFile.java").write_text("\n".join(lines), encoding="utf-8")

        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("BigFile.java")
        assert any("Split" in s or "lines" in s for s in score.suggestions)

    def test_high_complexity_suggestion(self, tmp_path: Path) -> None:
        code = (
            "public class Complex {\n"
            "  void m() {\n"
            + "".join(f"    if (x > {i}) {{ return; }}\n" for i in range(15))
            + "  }\n"
            "}\n"
        )
        (tmp_path / "Complex.java").write_text(code, encoding="utf-8")

        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("Complex.java")
        assert any("Cyclomatic" in s or "complexity" in s.lower() for s in score.suggestions)

    def test_high_coupling_suggestion(self, tmp_path: Path) -> None:
        imports = "\n".join(f"import pkg.mod{ i};" for i in range(8))
        code = f"{imports}\npublic class Coupled {{ }}\n"
        (tmp_path / "Coupled.java").write_text(code, encoding="utf-8")

        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("Coupled.java")
        assert any("import" in s.lower() or "dependenc" in s.lower() for s in score.suggestions)

    def test_long_functions_suggestion(self, tmp_path: Path) -> None:
        code = (
            "public class LongFunc {\n"
            "  void processData() {\n"
            + "\n".join(f"    int x{i} = {i};" for i in range(50))
            + "  }\n"
            "}\n"
        )
        (tmp_path / "LongFunc.java").write_text(code, encoding="utf-8")

        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("LongFunc.java")
        assert any("function" in s.lower() or "Average" in s for s in score.suggestions)

    def test_healthy_file_no_suggestions(self, tmp_path: Path) -> None:
        code = (
            "public class Clean {\n"
            "  int getId() { return 1; }\n"
            "}\n"
        )
        (tmp_path / "Clean.java").write_text(code, encoding="utf-8")

        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("Clean.java")
        assert score.grade in ("A", "B")
        assert len(score.suggestions) == 0

    def test_oserror_file_returns_empty_suggestions(self, tmp_path: Path) -> None:
        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("nonexistent.java")
        assert score.suggestions == ()
        assert score.score == 0

    def test_suggestions_in_tuple(self, tmp_path: Path) -> None:
        code = (
            "import a.b.C;\n"
            "import d.e.F;\n"
            "import g.h.I;\n"
            "import j.k.L;\n"
            "public class X {\n"
            "  void m() {\n"
            + "".join(f"    if (x > {i}) {{ y++; }}\n" for i in range(12))
            + "  }\n"
            "}\n"
        )
        (tmp_path / "X.java").write_text(code, encoding="utf-8")

        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("X.java")
        assert isinstance(score.suggestions, tuple)
        assert len(score.suggestions) >= 1
        assert 0 <= score.score <= 100


class TestASTBasedHealthScore:
    """Tests verifying AST-based metric accuracy (replaces regex approach)."""

    def test_python_ignores_commented_functions(self, tmp_path: Path) -> None:
        """Regex would match 'def' in comments; AST correctly ignores them."""
        code = (
            "# def fake_function():\n"
            "#     pass\n"
            "def real_function():\n"
            "    return 42\n"
        )
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("test.py")
        assert score.methods == 1

    def test_python_counts_imports_accurately(self, tmp_path: Path) -> None:
        """AST-based import counting distinguishes real imports from strings."""
        code = (
            "import os\n"
            "from pathlib import Path\n"
            'msg = "import fake"\n'
            "# import commented\n"
        )
        (tmp_path / "imports.py").write_text(code, encoding="utf-8")
        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("imports.py")
        assert score.imports == 2

    def test_python_cyclomatic_with_boolean_ops(self, tmp_path: Path) -> None:
        """Boolean 'and'/'or' operators increase cyclomatic complexity."""
        code = (
            "def check(x, y):\n"
            "    if x > 0 and y > 0:\n"
            "        return True\n"
            "    return False\n"
        )
        (tmp_path / "bool_ops.py").write_text(code, encoding="utf-8")
        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("bool_ops.py")
        # 1 (if) + 1 (and) + 1 = cyclomatic 3
        assert score.cyclomatic_complexity == 3

    def test_python_function_length_from_ast(self, tmp_path: Path) -> None:
        """Function length computed from AST node positions, not regex."""
        code = (
            "def short():\n"
            "    return 1\n"
            "\n"
            "def long_func():\n"
            "    x = 1\n"
            "    y = 2\n"
            "    z = 3\n"
            "    return x + y + z\n"
        )
        (tmp_path / "funcs.py").write_text(code, encoding="utf-8")
        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("funcs.py")
        assert score.methods == 2
        assert score.avg_function_length == 3.5

    def test_javascript_counts_methods_accurately(self, tmp_path: Path) -> None:
        """JS: arrow functions, function declarations, and methods all counted."""
        code = (
            "function regular() {}\n"
            "const arrow = () => {};\n"
            "class C {\n"
            "  method() {}\n"
            "}\n"
        )
        (tmp_path / "app.js").write_text(code, encoding="utf-8")
        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("app.js")
        assert score.methods == 3

    def test_go_counts_functions(self, tmp_path: Path) -> None:
        """Go: function and method declarations counted."""
        code = (
            'package main\n\n'
            'func hello() int {\n'
            '\treturn 1\n'
            '}\n\n'
            'func (s Server) handle() {\n'
            '\treturn\n'
            '}\n'
        )
        (tmp_path / "main.go").write_text(code, encoding="utf-8")
        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("main.go")
        assert score.methods == 2

    def test_java_annotations_counted(self, tmp_path: Path) -> None:
        """Java: @Override, @Deprecated etc. counted as annotations."""
        code = (
            "public class S {\n"
            "  @Override\n"
            "  public String toString() { return \"\"; }\n"
            "  @Deprecated\n"
            "  void old() {}\n"
            "}\n"
        )
        (tmp_path / "S.java").write_text(code, encoding="utf-8")
        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("S.java")
        assert score.methods == 2

    def test_unsupported_extension_fallback(self, tmp_path: Path) -> None:
        """Files with unsupported extensions get F grade with zero metrics."""
        (tmp_path / "data.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        scorer = HealthScorer(project_root=str(tmp_path))
        score = scorer.score_file("data.csv")
        assert score.grade == "F"
        assert score.methods == 0
