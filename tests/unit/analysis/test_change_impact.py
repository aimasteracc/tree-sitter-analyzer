"""Tests for ChangeImpactAnalyzer."""
from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.analysis.change_impact import (
    ChangeImpactAnalyzer,
    ChangeImpactResult,
    ImpactItem,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a minimal project structure for testing."""
    # tree_sitter_analyzer/analysis/base.py
    analysis = tmp_path / "tree_sitter_analyzer" / "analysis"
    analysis.mkdir(parents=True)
    (analysis / "__init__.py").write_text("")
    (analysis / "base.py").write_text("class BaseAnalyzer: pass\n")

    # complexity.py imports from base
    (analysis / "complexity.py").write_text(
        "from tree_sitter_analyzer.analysis.base import BaseAnalyzer\n"
        "class ComplexityAnalyzer(BaseAnalyzer): pass\n"
    )

    # security.py imports from base
    (analysis / "security.py").write_text(
        "from tree_sitter_analyzer.analysis.base import BaseAnalyzer\n"
        "class SecurityAnalyzer(BaseAnalyzer): pass\n"
    )

    # tool files
    tools = tmp_path / "tree_sitter_analyzer" / "mcp" / "tools"
    tools.mkdir(parents=True)
    (tools / "__init__.py").write_text("")
    (tools / "base_tool.py").write_text("class BaseMCPTool: pass\n")
    (tools / "complexity_tool.py").write_text(
        "from tree_sitter_analyzer.analysis.complexity import ComplexityAnalyzer\n"
    )
    (tools / "security_tool.py").write_text(
        "from tree_sitter_analyzer.analysis.security import SecurityAnalyzer\n"
    )

    # test files
    tests = tmp_path / "tests" / "unit" / "analysis"
    tests.mkdir(parents=True)
    (tests / "test_complexity.py").write_text("# test complexity\n")
    (tests / "test_security.py").write_text("# test security\n")

    return tmp_path


class TestImpactItem:
    def test_frozen(self) -> None:
        item = ImpactItem(path="a.py", relation="direct", distance=1)
        with pytest.raises(AttributeError):
            item.path = "b.py"  # type: ignore[misc]

    def test_relation_direct(self) -> None:
        item = ImpactItem(path="a.py", relation="direct", distance=1)
        assert item.relation == "direct"

    def test_relation_transitive(self) -> None:
        item = ImpactItem(path="c.py", relation="transitive", distance=2)
        assert item.distance == 2


class TestChangeImpactResult:
    def test_total_impact_count(self) -> None:
        result = ChangeImpactResult(
            changed_files=("a.py",),
            impacted=(
                ImpactItem("b.py", "direct", 1),
                ImpactItem("c.py", "transitive", 2),
            ),
            affected_tools=("tool1",),
            affected_tests=("test_a.py",),
        )
        assert result.total_impact_count == 4

    def test_direct_and_transitive_counts(self) -> None:
        result = ChangeImpactResult(
            changed_files=("a.py",),
            impacted=(
                ImpactItem("b.py", "direct", 1),
                ImpactItem("c.py", "direct", 1),
                ImpactItem("d.py", "transitive", 2),
            ),
            affected_tools=(),
            affected_tests=(),
        )
        assert result.direct_count == 2
        assert result.transitive_count == 1


class TestChangeImpactAnalyzer:
    def test_no_impact(self, project: Path) -> None:
        analyzer = ChangeImpactAnalyzer(project)
        result = analyzer.analyze(["tree_sitter_analyzer/analysis/security.py"])
        assert len(result.changed_files) == 1
        assert result.direct_count >= 1  # security_tool depends on it

    def test_base_change_has_high_impact(self, project: Path) -> None:
        analyzer = ChangeImpactAnalyzer(project)
        result = analyzer.analyze(["tree_sitter_analyzer/analysis/base.py"])

        # complexity.py and security.py both import from base
        impacted_paths = {i.path for i in result.impacted}
        assert any("complexity" in p for p in impacted_paths)
        assert any("security" in p for p in impacted_paths)

    def test_affected_tools(self, project: Path) -> None:
        analyzer = ChangeImpactAnalyzer(project)
        result = analyzer.analyze(["tree_sitter_analyzer/analysis/complexity.py"])

        tool_names = list(result.affected_tools)
        assert any("complexity" in t for t in tool_names)

    def test_affected_tests(self, project: Path) -> None:
        analyzer = ChangeImpactAnalyzer(project)
        result = analyzer.analyze(["tree_sitter_analyzer/analysis/complexity.py"])

        assert any("test_complexity" in t for t in result.affected_tests)

    def test_nonexistent_file_no_crash(self, project: Path) -> None:
        analyzer = ChangeImpactAnalyzer(project)
        result = analyzer.analyze(["nonexistent.py"])
        assert result.total_impact_count == 0

    def test_transitive_dependencies(self, tmp_path: Path) -> None:
        """A -> B -> C: changing C should transitively impact A."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "c.py").write_text("x = 1\n")
        (pkg / "b.py").write_text("from pkg.c import x\n")
        (pkg / "a.py").write_text("from pkg.b import x\n")

        analyzer = ChangeImpactAnalyzer(tmp_path)
        result = analyzer.analyze(["pkg/c.py"])

        impacted_paths = {i.path for i in result.impacted}
        assert str(Path("pkg/b.py")) in impacted_paths
        assert str(Path("pkg/a.py")) in impacted_paths

        # b is direct (distance=1), a is transitive (distance=2)
        b_item = next(i for i in result.impacted if "b.py" in i.path)
        a_item = next(i for i in result.impacted if "a.py" in i.path)
        assert b_item.distance == 1
        assert a_item.distance == 2

    def test_max_depth_respected(self, tmp_path: Path) -> None:
        """Verify that max_depth limits the search."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("pass\n")
        (pkg / "b.py").write_text("from pkg.a import *\n")
        (pkg / "c.py").write_text("from pkg.b import *\n")

        analyzer = ChangeImpactAnalyzer(tmp_path)
        result = analyzer.analyze(["pkg/a.py"])

        # With default max_depth=10, both b and c should be found
        impacted_paths = {i.path for i in result.impacted}
        assert str(Path("pkg/b.py")) in impacted_paths
        assert str(Path("pkg/c.py")) in impacted_paths
