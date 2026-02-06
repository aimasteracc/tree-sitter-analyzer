"""Tests for instant understanding engine."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer_v2.features.instant_understanding import (
    InstantUnderstandingEngine,
    Layer1Overview,
    Layer2Architecture,
    Layer3DeepInsights,
    UnderstandingReport,
    instant_understand,
)


class TestDataclasses:
    """Tests for dataclass creation."""

    def test_layer1_overview(self) -> None:
        """Test Layer1Overview dataclass."""
        layer = Layer1Overview(
            project_name="test",
            summary="Test summary",
            statistics={"files": 10},
            top_files=[{"file": "main.py"}],
            tech_stack={"framework": "pytest"},
            entry_points=["main.py"],
        )
        assert layer.project_name == "test"
        assert layer.summary == "Test summary"
        assert layer.statistics["files"] == 10

    def test_layer2_architecture(self) -> None:
        """Test Layer2Architecture dataclass."""
        layer = Layer2Architecture(
            module_structure={"total_modules": 5},
            call_graph={"total_functions": 20},
            design_patterns=["Singleton"],
            hotspot_chart="chart",
            dependency_graph="deps",
        )
        assert layer.module_structure["total_modules"] == 5
        assert "Singleton" in layer.design_patterns

    def test_layer3_deep_insights(self) -> None:
        """Test Layer3DeepInsights dataclass."""
        layer = Layer3DeepInsights(
            performance_analysis={"total_hotspots": 3},
            tech_debt_report={"total_count": 5},
            refactoring_suggestions=[],
            learning_path=["step1"],
            health_score=85.0,
        )
        assert layer.health_score == 85.0
        assert layer.performance_analysis["total_hotspots"] == 3

    def test_understanding_report(self) -> None:
        """Test UnderstandingReport dataclass."""
        layer1 = Layer1Overview(
            project_name="test",
            summary="",
            statistics={},
            top_files=[],
            tech_stack={},
            entry_points=[],
        )
        layer2 = Layer2Architecture(
            module_structure={},
            call_graph={},
            design_patterns=[],
            hotspot_chart="",
            dependency_graph="",
        )
        layer3 = Layer3DeepInsights(
            performance_analysis={},
            tech_debt_report={},
            refactoring_suggestions=[],
            learning_path=[],
            health_score=100.0,
        )
        report = UnderstandingReport(
            layer1=layer1,
            layer2=layer2,
            layer3=layer3,
            mermaid_diagrams=["diagram1"],
        )
        assert report.layer1.project_name == "test"
        assert len(report.mermaid_diagrams) == 1
        assert report.generated_at  # Auto-generated


class TestInstantUnderstandingEngine:
    """Tests for InstantUnderstandingEngine class."""

    def test_init(self) -> None:
        """Test engine initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            assert engine.project_path.exists()
            assert engine.language == "python"

    def test_init_with_language(self) -> None:
        """Test engine initialization with custom language."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir), language="java")
            assert engine.language == "java"

    def test_detect_tech_stack_empty(self) -> None:
        """Test tech stack detection in empty project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            tech_stack = engine._detect_tech_stack()
            assert tech_stack["framework"] == "Unknown"
            assert tech_stack["tools"] == []

    def test_detect_tech_stack_with_files(self) -> None:
        """Test tech stack detection with config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "pyproject.toml").write_text("[project]\n")
            (tmppath / "requirements.txt").write_text("pytest\n")

            engine = InstantUnderstandingEngine(tmppath)
            tech_stack = engine._detect_tech_stack()
            assert "uv/poetry" in tech_stack["tools"]
            assert "pip" in tech_stack["tools"]
            assert "pytest" in tech_stack["tools"]

    def test_detect_tech_stack_mcp(self) -> None:
        """Test tech stack detection with MCP project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "mcp").mkdir()
            (tmppath / "mcp" / "server.py").write_text("# MCP\n")

            engine = InstantUnderstandingEngine(tmppath)
            tech_stack = engine._detect_tech_stack()
            assert tech_stack["framework"] == "MCP (Model Context Protocol)"

    def test_find_entry_points_empty(self) -> None:
        """Test entry point finding in empty project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            entry_points = engine._find_entry_points()
            assert entry_points == []

    def test_find_entry_points_with_files(self) -> None:
        """Test entry point finding with standard files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "main.py").write_text("# Main\n")
            (tmppath / "__main__.py").write_text("# Entry\n")

            engine = InstantUnderstandingEngine(tmppath)
            entry_points = engine._find_entry_points()
            assert "main.py" in entry_points
            assert "__main__.py" in entry_points

    def test_build_module_structure_empty(self) -> None:
        """Test module structure building in empty project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            structure = engine._build_module_structure()
            assert structure["total_modules"] == 0

    def test_build_module_structure_with_modules(self) -> None:
        """Test module structure building with modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "src").mkdir()
            (tmppath / "src" / "__init__.py").write_text("")
            (tmppath / "src" / "core.py").write_text("x = 1\n")
            (tmppath / "src" / "utils.py").write_text("y = 2\n")

            engine = InstantUnderstandingEngine(tmppath)
            structure = engine._build_module_structure()
            assert structure["total_modules"] >= 1
            assert "src" in structure["modules"]

    def test_detect_design_patterns_empty(self) -> None:
        """Test design pattern detection in empty project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            patterns = engine._detect_design_patterns()
            assert isinstance(patterns, list)

    def test_detect_design_patterns_singleton(self) -> None:
        """Test Singleton pattern detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "singleton.py").write_text(
                "class Singleton:\n"
                "    _instance = None\n"
                "    def __new__(cls):\n"
                "        pass\n"
            )

            engine = InstantUnderstandingEngine(tmppath)
            patterns = engine._detect_design_patterns()
            assert "Singleton" in patterns

    def test_detect_design_patterns_factory(self) -> None:
        """Test Factory pattern detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "factory.py").write_text(
                "class Factory:\n" "    def create_item(self):\n" "        pass\n"
            )

            engine = InstantUnderstandingEngine(tmppath)
            patterns = engine._detect_design_patterns()
            assert "Factory" in patterns

    def test_detect_design_patterns_observer(self) -> None:
        """Test Observer pattern detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "watcher.py").write_text("# Watcher\n")

            engine = InstantUnderstandingEngine(tmppath)
            patterns = engine._detect_design_patterns()
            assert "Observer" in patterns

    def test_detect_design_patterns_strategy(self) -> None:
        """Test Strategy/Protocol pattern detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "protocols.py").write_text("from typing import Protocol\n")

            engine = InstantUnderstandingEngine(tmppath)
            patterns = engine._detect_design_patterns()
            assert "Strategy/Protocol" in patterns

    def test_generate_hotspot_chart_empty(self) -> None:
        """Test hotspot chart generation with no hotspots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            chart = engine._generate_hotspot_chart([])
            assert chart == "No hotspots detected"

    def test_generate_hotspot_chart_with_data(self) -> None:
        """Test hotspot chart generation with data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            hotspots = [
                {"function": "func1", "impact_score": 10},
                {"function": "func2", "impact_score": 5},
            ]
            chart = engine._generate_hotspot_chart(hotspots)
            assert "func1" in chart
            assert "func2" in chart
            assert "#" in chart

    def test_describe_dependencies_none(self) -> None:
        """Test dependency description with no dep files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            deps = engine._describe_dependencies()
            assert "No standard dependency" in deps

    def test_describe_dependencies_with_files(self) -> None:
        """Test dependency description with dep files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "requirements.txt").write_text("pytest\n")

            engine = InstantUnderstandingEngine(tmppath)
            deps = engine._describe_dependencies()
            assert "requirements.txt" in deps

    def test_generate_learning_path_empty(self) -> None:
        """Test learning path generation in empty project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            path = engine._generate_learning_path()
            assert isinstance(path, list)

    def test_generate_learning_path_with_structure(self) -> None:
        """Test learning path generation with project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "core").mkdir()
            (tmppath / "core" / "types.py").write_text("# Types\n")
            (tmppath / "core" / "protocols.py").write_text("# Protocols\n")
            (tmppath / "features").mkdir()
            (tmppath / "features" / "feature1.py").write_text("# Feature\n")

            engine = InstantUnderstandingEngine(tmppath)
            path = engine._generate_learning_path()
            assert any("types.py" in p for p in path)
            assert any("protocols.py" in p for p in path)

    def test_calculate_health_score_perfect(self) -> None:
        """Test health score calculation with no issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            results = {"tech_debt": [], "performance": []}
            score = engine._calculate_health_score(results)
            assert score == 100.0

    def test_calculate_health_score_with_debt(self) -> None:
        """Test health score calculation with tech debt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))

            # Create mock debt objects
            mock_high_debt = MagicMock()
            mock_high_debt.severity = "high"
            mock_medium_debt = MagicMock()
            mock_medium_debt.severity = "medium"

            results = {
                "tech_debt": [mock_high_debt, mock_medium_debt],
                "performance": [],
            }
            score = engine._calculate_health_score(results)
            assert score < 100.0
            assert score == 100.0 - 5 - 2  # -5 for high, -2 for medium

    def test_calculate_health_score_with_hotspots(self) -> None:
        """Test health score with performance hotspots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))

            mock_hotspot = MagicMock()
            mock_hotspot.complexity = 20  # > 15 threshold

            results = {"tech_debt": [], "performance": [mock_hotspot]}
            score = engine._calculate_health_score(results)
            assert score == 100.0 - 3  # -3 for critical hotspot

    def test_calculate_health_score_minimum(self) -> None:
        """Test health score cannot go below 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))

            # Create many high severity debts
            mock_debts = []
            for _ in range(30):
                debt = MagicMock()
                debt.severity = "high"
                mock_debts.append(debt)

            results = {"tech_debt": mock_debts, "performance": []}
            score = engine._calculate_health_score(results)
            assert score == 0.0

    def test_generate_architecture_mermaid_empty(self) -> None:
        """Test architecture Mermaid generation for empty project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            diagram = engine._generate_architecture_mermaid()
            assert "graph TD" in diagram

    def test_generate_architecture_mermaid_with_dirs(self) -> None:
        """Test architecture Mermaid generation with directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "cli").mkdir()
            (tmppath / "api").mkdir()
            (tmppath / "core").mkdir()
            (tmppath / "mcp").mkdir()

            engine = InstantUnderstandingEngine(tmppath)
            diagram = engine._generate_architecture_mermaid()
            assert "CLI[CLI Entry]" in diagram
            assert "MCP[MCP Server]" in diagram

    def test_generate_call_graph_mermaid_empty(self) -> None:
        """Test call graph Mermaid generation with no hotspots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            diagram = engine._generate_call_graph_mermaid([])
            assert "graph LR" in diagram

    def test_generate_call_graph_mermaid_with_data(self) -> None:
        """Test call graph Mermaid generation with hotspots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            hotspots = [
                {"function": "func1", "file": "mod.py", "called_by_count": 5},
                {"function": "func2", "file": "mod.py", "called_by_count": 0},
            ]
            diagram = engine._generate_call_graph_mermaid(hotspots)
            assert "func1" in diagram
            assert "5 callers" in diagram

    def test_generate_performance_heatmap_mermaid(self) -> None:
        """Test performance heatmap Mermaid generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))

            mock_hotspot = MagicMock()
            mock_hotspot.function = "process_data"
            mock_hotspot.complexity = 15

            diagram = engine._generate_performance_heatmap_mermaid([mock_hotspot])
            assert "graph TD" in diagram
            assert "PerformanceHotspots" in diagram
            assert "process_data" in diagram
            assert "15" in diagram

    @patch.object(InstantUnderstandingEngine, "_collect_analysis_data")
    def test_analyze(self, mock_collect) -> None:
        """Test full analysis."""
        mock_collect.return_value = {
            "knowledge": {"snapshot": None, "hotspots": []},
            "performance": [],
            "tech_debt": [],
            "statistics": {"total_files": 5, "total_lines": 100, "language": "python"},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            report = engine.analyze()

            assert isinstance(report, UnderstandingReport)
            assert report.layer1.project_name == Path(tmpdir).name
            assert isinstance(report.layer3.health_score, float)

    def test_to_markdown(self) -> None:
        """Test Markdown conversion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))

            layer1 = Layer1Overview(
                project_name="TestProject",
                summary="Test summary",
                statistics={"files": 10, "lines": 500},
                top_files=[{"file": "main.py", "impact": "high"}],
                tech_stack={"framework": "Django", "tools": ["pytest"]},
                entry_points=["main.py"],
            )
            layer2 = Layer2Architecture(
                module_structure={"total_modules": 3},
                call_graph={
                    "total_functions": 20,
                    "high_impact": 2,
                    "medium_impact": 5,
                    "low_impact": 13,
                },
                design_patterns=["Singleton"],
                hotspot_chart="func1  ### 10",
                dependency_graph="deps",
            )
            layer3 = Layer3DeepInsights(
                performance_analysis={
                    "total_hotspots": 3,
                    "top_5": [
                        {
                            "function": "process",
                            "file": "mod.py",
                            "complexity": 15,
                            "score": 25.0,
                            "recommendation": "Refactor",
                        }
                    ],
                },
                tech_debt_report={
                    "total_count": 5,
                    "by_severity": {"high": 1, "medium": 2, "low": 2},
                    "by_type": {"TODO": 3},
                    "estimated_fix_hours": 2.5,
                },
                refactoring_suggestions=[
                    {
                        "function": "old_func",
                        "file": "legacy.py",
                        "reason": "High impact",
                        "priority": "high",
                    }
                ],
                learning_path=["Step 1", "Step 2"],
                health_score=85.0,
            )
            report = UnderstandingReport(
                layer1=layer1,
                layer2=layer2,
                layer3=layer3,
                mermaid_diagrams=["graph TD\n    A --> B"],
            )

            markdown = engine.to_markdown(report)

            assert "# TestProject" in markdown
            assert "Quick Overview" in markdown
            assert "Architecture Understanding" in markdown
            assert "Deep Insights" in markdown
            assert "files: 10" in markdown
            assert "Health Score: 85.0/100" in markdown

    def test_save_report_markdown(self) -> None:
        """Test saving report as Markdown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            engine = InstantUnderstandingEngine(tmppath)

            layer1 = Layer1Overview(
                project_name="Test",
                summary="",
                statistics={},
                top_files=[],
                tech_stack={},
                entry_points=[],
            )
            layer2 = Layer2Architecture(
                module_structure={},
                call_graph={},
                design_patterns=[],
                hotspot_chart="",
                dependency_graph="",
            )
            layer3 = Layer3DeepInsights(
                performance_analysis={"total_hotspots": 0, "top_5": []},
                tech_debt_report={
                    "total_count": 0,
                    "by_severity": {},
                    "estimated_fix_hours": 0,
                },
                refactoring_suggestions=[],
                learning_path=[],
                health_score=100.0,
            )
            report = UnderstandingReport(
                layer1=layer1, layer2=layer2, layer3=layer3, mermaid_diagrams=[]
            )

            output_path = tmppath / "report.md"
            engine.save_report(report, output_path)

            assert output_path.exists()
            content = output_path.read_text(encoding="utf-8")
            assert "# Test" in content

    def test_save_report_html(self) -> None:
        """Test saving report as HTML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            engine = InstantUnderstandingEngine(tmppath)

            layer1 = Layer1Overview(
                project_name="Test",
                summary="",
                statistics={},
                top_files=[],
                tech_stack={},
                entry_points=[],
            )
            layer2 = Layer2Architecture(
                module_structure={},
                call_graph={},
                design_patterns=[],
                hotspot_chart="",
                dependency_graph="",
            )
            layer3 = Layer3DeepInsights(
                performance_analysis={"total_hotspots": 0, "top_5": []},
                tech_debt_report={
                    "total_count": 0,
                    "by_severity": {},
                    "estimated_fix_hours": 0,
                },
                refactoring_suggestions=[],
                learning_path=[],
                health_score=100.0,
            )
            report = UnderstandingReport(
                layer1=layer1, layer2=layer2, layer3=layer3, mermaid_diagrams=[]
            )

            output_path = tmppath / "report.html"
            engine.save_report(report, output_path)

            assert output_path.exists()
            content = output_path.read_text(encoding="utf-8")
            assert "<html>" in content
            assert "mermaid" in content

    def test_save_report_unsupported_format(self) -> None:
        """Test saving report with unsupported format raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            engine = InstantUnderstandingEngine(tmppath)

            layer1 = Layer1Overview(
                project_name="Test",
                summary="",
                statistics={},
                top_files=[],
                tech_stack={},
                entry_points=[],
            )
            layer2 = Layer2Architecture(
                module_structure={},
                call_graph={},
                design_patterns=[],
                hotspot_chart="",
                dependency_graph="",
            )
            layer3 = Layer3DeepInsights(
                performance_analysis={},
                tech_debt_report={},
                refactoring_suggestions=[],
                learning_path=[],
                health_score=100.0,
            )
            report = UnderstandingReport(
                layer1=layer1, layer2=layer2, layer3=layer3, mermaid_diagrams=[]
            )

            output_path = tmppath / "report.pdf"
            with pytest.raises(ValueError, match="Unsupported output format"):
                engine.save_report(report, output_path)


class TestConvenienceFunction:
    """Tests for instant_understand convenience function."""

    @patch.object(InstantUnderstandingEngine, "analyze")
    def test_instant_understand_basic(self, mock_analyze) -> None:
        """Test basic instant_understand call."""
        mock_report = MagicMock()
        mock_analyze.return_value = mock_report

        with tempfile.TemporaryDirectory() as tmpdir:
            result = instant_understand(Path(tmpdir))
            assert result == mock_report
            mock_analyze.assert_called_once()

    @patch.object(InstantUnderstandingEngine, "analyze")
    @patch.object(InstantUnderstandingEngine, "save_report")
    def test_instant_understand_with_output(
        self, mock_save, mock_analyze
    ) -> None:
        """Test instant_understand with output path."""
        mock_report = MagicMock()
        mock_analyze.return_value = mock_report

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.md"
            result = instant_understand(Path(tmpdir), output_path=output_path)

            assert result == mock_report
            mock_save.assert_called_once_with(mock_report, output_path)

    @patch.object(InstantUnderstandingEngine, "analyze")
    def test_instant_understand_force_rebuild(self, mock_analyze) -> None:
        """Test instant_understand with force_rebuild."""
        mock_report = MagicMock()
        mock_analyze.return_value = mock_report

        with tempfile.TemporaryDirectory() as tmpdir:
            instant_understand(Path(tmpdir), force_rebuild=True)
            mock_analyze.assert_called_once_with(force_rebuild=True)


class TestCollectAnalysisData:
    """Tests for _collect_analysis_data method."""

    def test_collect_statistics(self) -> None:
        """Test statistics collection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "file1.py").write_text("x = 1\ny = 2\n")
            (tmppath / "file2.py").write_text("z = 3\n")

            engine = InstantUnderstandingEngine(tmppath)
            # Mock other analyzers to avoid complex setup
            with patch.object(engine.knowledge_engine, "build_snapshot", side_effect=Exception("skip")):
                with patch.object(engine.knowledge_engine, "get_hotspots", side_effect=Exception("skip")):
                    results = engine._collect_analysis_data(False)

            assert "statistics" in results
            assert results["statistics"]["total_files"] == 2
            assert results["statistics"]["total_lines"] >= 3


class TestGenerateLayer1Overview:
    """Tests for _generate_layer1_overview method."""

    def test_generate_with_empty_results(self) -> None:
        """Test layer1 generation with empty results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            results = {"statistics": {}, "knowledge": None}
            layer = engine._generate_layer1_overview(results)

            assert isinstance(layer, Layer1Overview)
            assert layer.project_name == Path(tmpdir).name
            assert layer.statistics["files"] == 0


class TestGenerateLayer2Architecture:
    """Tests for _generate_layer2_architecture method."""

    def test_generate_with_hotspots(self) -> None:
        """Test layer2 generation with hotspots."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))
            results = {
                "knowledge": {
                    "hotspots": [
                        {"function": "func1", "impact_level": "high", "impact_score": 10},
                        {"function": "func2", "impact_level": "medium", "impact_score": 5},
                    ]
                }
            }
            layer = engine._generate_layer2_architecture(results)

            assert isinstance(layer, Layer2Architecture)
            assert layer.call_graph["total_functions"] == 2
            assert layer.call_graph["high_impact"] == 1


class TestGenerateLayer3Insights:
    """Tests for _generate_layer3_insights method."""

    def test_generate_with_performance_data(self) -> None:
        """Test layer3 generation with performance data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))

            mock_hotspot = MagicMock()
            mock_hotspot.function = "slow_func"
            mock_hotspot.file = "mod.py"
            mock_hotspot.complexity = 20
            mock_hotspot.hotspot_score = 30.0
            mock_hotspot.recommendation = "Refactor"

            results = {
                "performance": [mock_hotspot],
                "tech_debt": [],
                "knowledge": {"hotspots": []},
            }
            layer = engine._generate_layer3_insights(results)

            assert isinstance(layer, Layer3DeepInsights)
            assert layer.performance_analysis["total_hotspots"] == 1
            assert layer.performance_analysis["top_5"][0]["function"] == "slow_func"

    def test_generate_with_tech_debt(self) -> None:
        """Test layer3 generation with tech debt data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = InstantUnderstandingEngine(Path(tmpdir))

            from tree_sitter_analyzer_v2.features.tech_debt_tracker import (
                DebtType,
                TechDebt,
            )

            mock_debt = TechDebt(
                file="mod.py",
                line_number=10,
                debt_type=DebtType.TODO,
                severity="high",
                description="Fix this",
                estimated_fix_time=30,
            )

            results = {
                "performance": [],
                "tech_debt": [mock_debt],
                "knowledge": {"hotspots": []},
            }
            layer = engine._generate_layer3_insights(results)

            assert layer.tech_debt_report["total_count"] == 1
            assert layer.tech_debt_report["by_severity"]["high"] == 1
            assert layer.tech_debt_report["by_type"]["todo"] == 1
