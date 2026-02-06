"""Tests for instant understand MCP tools."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer_v2.mcp.tools.instant_understand import (
    CompareProjectsTool,
    InstantUnderstandTool,
)


class TestInstantUnderstandTool:
    """Tests for InstantUnderstandTool class."""

    def test_get_name(self) -> None:
        """Test get_name returns correct name."""
        tool = InstantUnderstandTool()
        assert tool.get_name() == "instant_understand"

    def test_get_description(self) -> None:
        """Test get_description returns meaningful description."""
        tool = InstantUnderstandTool()
        desc = tool.get_description()
        assert "project analysis" in desc.lower()
        assert "3 layers" in desc or "Layer 1" in desc

    def test_get_schema(self) -> None:
        """Test get_schema returns valid schema."""
        tool = InstantUnderstandTool()
        schema = tool.get_schema()
        assert schema["type"] == "object"
        assert "project_path" in schema["properties"]
        assert "project_path" in schema["required"]
        assert "output_file" in schema["properties"]
        assert "force_rebuild" in schema["properties"]

    def test_execute_nonexistent_path(self) -> None:
        """Test execute with non-existent path."""
        tool = InstantUnderstandTool()
        result = tool.execute({"project_path": "/nonexistent/path"})
        assert result["success"] is False
        assert "does not exist" in result["error"]

    def test_execute_file_not_directory(self) -> None:
        """Test execute with file instead of directory."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"x = 1\n")
            f.flush()
            path = f.name

        try:
            tool = InstantUnderstandTool()
            result = tool.execute({"project_path": path})
            assert result["success"] is False
            assert "not a directory" in result["error"]
        finally:
            Path(path).unlink()

    @patch("tree_sitter_analyzer_v2.mcp.tools.instant_understand.InstantUnderstandingEngine")
    def test_execute_success(self, mock_engine_class) -> None:
        """Test successful execution."""
        # Setup mock
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        mock_report = MagicMock()
        mock_report.layer1.project_name = "TestProject"
        mock_report.layer1.summary = "Test summary"
        mock_report.layer1.statistics = {"files": 10, "lines": 500, "functions": 20}
        mock_report.layer1.top_files = []
        mock_report.layer1.entry_points = ["main.py"]
        mock_report.layer2.module_structure = {"total_modules": 3}
        mock_report.layer2.design_patterns = ["Singleton"]
        mock_report.layer2.call_graph = {"total_functions": 20}
        mock_report.layer3.health_score = 85.0
        mock_report.layer3.performance_analysis = {"total_hotspots": 2}
        mock_report.layer3.tech_debt_report = {"total_count": 5, "estimated_fix_hours": 3}
        mock_report.layer3.refactoring_suggestions = []
        mock_report.layer3.learning_path = ["Step 1"]
        mock_report.mermaid_diagrams = []
        mock_report.generated_at = "2024-01-01T00:00:00"

        mock_engine.analyze.return_value = mock_report
        mock_engine.to_markdown.return_value = "# Report"

        with tempfile.TemporaryDirectory() as tmpdir:
            tool = InstantUnderstandTool()
            result = tool.execute({"project_path": tmpdir})

            assert result["success"] is True
            assert result["project_name"] == "TestProject"
            assert result["report_summary"]["files"] == 10
            assert result["layer1_quick_overview"]["summary"] == "Test summary"
            assert result["layer3_deep_insights"]["health_score"] == 85.0
            assert result["markdown_report"] == "# Report"

    @patch("tree_sitter_analyzer_v2.mcp.tools.instant_understand.InstantUnderstandingEngine")
    def test_execute_with_output_file_markdown(self, mock_engine_class) -> None:
        """Test execution with markdown output file."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        mock_report = MagicMock()
        mock_report.layer1.project_name = "Test"
        mock_report.layer1.summary = ""
        mock_report.layer1.statistics = {}
        mock_report.layer1.top_files = []
        mock_report.layer1.entry_points = []
        mock_report.layer2.module_structure = {}
        mock_report.layer2.design_patterns = []
        mock_report.layer2.call_graph = {}
        mock_report.layer3.health_score = 100.0
        mock_report.layer3.performance_analysis = {}
        mock_report.layer3.tech_debt_report = {}
        mock_report.layer3.refactoring_suggestions = []
        mock_report.layer3.learning_path = []
        mock_report.mermaid_diagrams = []
        mock_report.generated_at = ""

        mock_engine.analyze.return_value = mock_report
        mock_engine.to_markdown.return_value = "# Report"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = str(Path(tmpdir) / "report.md")
            tool = InstantUnderstandTool()
            result = tool.execute({
                "project_path": tmpdir,
                "output_file": output_file
            })

            assert result["success"] is True
            assert "output_file" in result
            mock_engine.save_report.assert_called_once()

    @patch("tree_sitter_analyzer_v2.mcp.tools.instant_understand.InstantUnderstandingEngine")
    def test_execute_with_output_file_html(self, mock_engine_class) -> None:
        """Test execution with HTML output file."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        mock_report = MagicMock()
        mock_report.layer1.project_name = "Test"
        mock_report.layer1.summary = ""
        mock_report.layer1.statistics = {}
        mock_report.layer1.top_files = []
        mock_report.layer1.entry_points = []
        mock_report.layer2.module_structure = {}
        mock_report.layer2.design_patterns = []
        mock_report.layer2.call_graph = {}
        mock_report.layer3.health_score = 100.0
        mock_report.layer3.performance_analysis = {}
        mock_report.layer3.tech_debt_report = {}
        mock_report.layer3.refactoring_suggestions = []
        mock_report.layer3.learning_path = []
        mock_report.mermaid_diagrams = []
        mock_report.generated_at = ""

        mock_engine.analyze.return_value = mock_report
        mock_engine.to_markdown.return_value = "# Report"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = str(Path(tmpdir) / "report.html")
            tool = InstantUnderstandTool()
            result = tool.execute({
                "project_path": tmpdir,
                "output_file": output_file,
                "output_format": "html"
            })

            assert result["success"] is True
            mock_engine.save_report.assert_called_once()
            # Check that .html extension is used
            call_args = mock_engine.save_report.call_args
            assert call_args[0][1].suffix == ".html"

    @patch("tree_sitter_analyzer_v2.mcp.tools.instant_understand.InstantUnderstandingEngine")
    def test_execute_with_format_override(self, mock_engine_class) -> None:
        """Test execution with format override (no extension)."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        mock_report = MagicMock()
        mock_report.layer1.project_name = "Test"
        mock_report.layer1.summary = ""
        mock_report.layer1.statistics = {}
        mock_report.layer1.top_files = []
        mock_report.layer1.entry_points = []
        mock_report.layer2.module_structure = {}
        mock_report.layer2.design_patterns = []
        mock_report.layer2.call_graph = {}
        mock_report.layer3.health_score = 100.0
        mock_report.layer3.performance_analysis = {}
        mock_report.layer3.tech_debt_report = {}
        mock_report.layer3.refactoring_suggestions = []
        mock_report.layer3.learning_path = []
        mock_report.mermaid_diagrams = []
        mock_report.generated_at = ""

        mock_engine.analyze.return_value = mock_report
        mock_engine.to_markdown.return_value = "# Report"

        with tempfile.TemporaryDirectory() as tmpdir:
            # Output file without extension + format override
            output_file = str(Path(tmpdir) / "report")
            tool = InstantUnderstandTool()
            result = tool.execute({
                "project_path": tmpdir,
                "output_file": output_file,
                "output_format": "html"
            })

            assert result["success"] is True
            call_args = mock_engine.save_report.call_args
            # Should add .html extension
            assert call_args[0][1].suffix == ".html"

    @patch("tree_sitter_analyzer_v2.mcp.tools.instant_understand.InstantUnderstandingEngine")
    def test_execute_with_custom_language(self, mock_engine_class) -> None:
        """Test execution with custom language."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        mock_report = MagicMock()
        mock_report.layer1.project_name = "Test"
        mock_report.layer1.summary = ""
        mock_report.layer1.statistics = {}
        mock_report.layer1.top_files = []
        mock_report.layer1.entry_points = []
        mock_report.layer2.module_structure = {}
        mock_report.layer2.design_patterns = []
        mock_report.layer2.call_graph = {}
        mock_report.layer3.health_score = 100.0
        mock_report.layer3.performance_analysis = {}
        mock_report.layer3.tech_debt_report = {}
        mock_report.layer3.refactoring_suggestions = []
        mock_report.layer3.learning_path = []
        mock_report.mermaid_diagrams = []
        mock_report.generated_at = ""

        mock_engine.analyze.return_value = mock_report
        mock_engine.to_markdown.return_value = "# Report"

        with tempfile.TemporaryDirectory() as tmpdir:
            tool = InstantUnderstandTool()
            tool.execute({
                "project_path": tmpdir,
                "language": "java"
            })

            mock_engine_class.assert_called_once()
            # Check language was passed
            call_args = mock_engine_class.call_args
            assert call_args[1]["language"] == "java"

    @patch("tree_sitter_analyzer_v2.mcp.tools.instant_understand.InstantUnderstandingEngine")
    def test_execute_with_force_rebuild(self, mock_engine_class) -> None:
        """Test execution with force_rebuild flag."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        mock_report = MagicMock()
        mock_report.layer1.project_name = "Test"
        mock_report.layer1.summary = ""
        mock_report.layer1.statistics = {}
        mock_report.layer1.top_files = []
        mock_report.layer1.entry_points = []
        mock_report.layer2.module_structure = {}
        mock_report.layer2.design_patterns = []
        mock_report.layer2.call_graph = {}
        mock_report.layer3.health_score = 100.0
        mock_report.layer3.performance_analysis = {}
        mock_report.layer3.tech_debt_report = {}
        mock_report.layer3.refactoring_suggestions = []
        mock_report.layer3.learning_path = []
        mock_report.mermaid_diagrams = []
        mock_report.generated_at = ""

        mock_engine.analyze.return_value = mock_report
        mock_engine.to_markdown.return_value = "# Report"

        with tempfile.TemporaryDirectory() as tmpdir:
            tool = InstantUnderstandTool()
            tool.execute({
                "project_path": tmpdir,
                "force_rebuild": True
            })

            mock_engine.analyze.assert_called_once_with(force_rebuild=True)

    @patch("tree_sitter_analyzer_v2.mcp.tools.instant_understand.InstantUnderstandingEngine")
    def test_execute_analysis_exception(self, mock_engine_class) -> None:
        """Test execution handles analysis exception."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine
        mock_engine.analyze.side_effect = Exception("Analysis error")

        with tempfile.TemporaryDirectory() as tmpdir:
            tool = InstantUnderstandTool()
            result = tool.execute({"project_path": tmpdir})

            assert result["success"] is False
            assert "Analysis failed" in result["error"]


class TestCompareProjectsTool:
    """Tests for CompareProjectsTool class."""

    def test_get_name(self) -> None:
        """Test get_name returns correct name."""
        tool = CompareProjectsTool()
        assert tool.get_name() == "compare_projects"

    def test_get_description(self) -> None:
        """Test get_description returns meaningful description."""
        tool = CompareProjectsTool()
        desc = tool.get_description()
        assert "compare" in desc.lower()
        assert "side-by-side" in desc.lower()

    def test_get_schema(self) -> None:
        """Test get_schema returns valid schema."""
        tool = CompareProjectsTool()
        schema = tool.get_schema()
        assert schema["type"] == "object"
        assert "project_a" in schema["properties"]
        assert "project_b" in schema["properties"]
        assert "project_a" in schema["required"]
        assert "project_b" in schema["required"]

    def test_execute_invalid_project_a(self) -> None:
        """Test execute with invalid project A."""
        tool = CompareProjectsTool()
        result = tool.execute({
            "project_a": "/nonexistent/a",
            "project_b": "/nonexistent/b"
        })
        assert result["success"] is False
        assert "Invalid project A" in result["error"]

    def test_execute_invalid_project_b(self) -> None:
        """Test execute with invalid project B."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = CompareProjectsTool()
            result = tool.execute({
                "project_a": tmpdir,
                "project_b": "/nonexistent/b"
            })
            assert result["success"] is False
            assert "Invalid project B" in result["error"]

    @patch("tree_sitter_analyzer_v2.mcp.tools.instant_understand.InstantUnderstandingEngine")
    def test_execute_success(self, mock_engine_class) -> None:
        """Test successful comparison."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        # Create mock reports for both projects
        mock_report = MagicMock()
        mock_report.layer1.project_name = "ProjectA"
        mock_report.layer1.statistics = {"files": 10, "lines": 500, "functions": 20}
        mock_report.layer3.health_score = 85.0
        mock_report.layer3.tech_debt_report = {"estimated_fix_hours": 3}
        mock_report.layer3.performance_analysis = {"total_hotspots": 2}

        mock_engine.analyze.return_value = mock_report

        with tempfile.TemporaryDirectory() as tmpdir_a:
            with tempfile.TemporaryDirectory() as tmpdir_b:
                tool = CompareProjectsTool()
                result = tool.execute({
                    "project_a": tmpdir_a,
                    "project_b": tmpdir_b
                })

                assert result["success"] is True
                assert "project_a" in result
                assert "project_b" in result
                assert "differences" in result
                assert "markdown_report" in result

    @patch("tree_sitter_analyzer_v2.mcp.tools.instant_understand.InstantUnderstandingEngine")
    def test_execute_with_output_file(self, mock_engine_class) -> None:
        """Test comparison with output file."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine

        mock_report = MagicMock()
        mock_report.layer1.project_name = "Project"
        mock_report.layer1.statistics = {"files": 5, "lines": 200, "functions": 10}
        mock_report.layer3.health_score = 90.0
        mock_report.layer3.tech_debt_report = {"estimated_fix_hours": 1}
        mock_report.layer3.performance_analysis = {"total_hotspots": 1}

        mock_engine.analyze.return_value = mock_report

        with tempfile.TemporaryDirectory() as tmpdir:
            project_a = Path(tmpdir) / "a"
            project_b = Path(tmpdir) / "b"
            project_a.mkdir()
            project_b.mkdir()
            output_file = str(Path(tmpdir) / "comparison.md")

            tool = CompareProjectsTool()
            result = tool.execute({
                "project_a": str(project_a),
                "project_b": str(project_b),
                "output_file": output_file
            })

            assert result["success"] is True
            assert result["output_file"] == output_file
            assert Path(output_file).exists()

    @patch("tree_sitter_analyzer_v2.mcp.tools.instant_understand.InstantUnderstandingEngine")
    def test_execute_analysis_exception(self, mock_engine_class) -> None:
        """Test comparison handles analysis exception."""
        mock_engine = MagicMock()
        mock_engine_class.return_value = mock_engine
        mock_engine.analyze.side_effect = Exception("Analysis error")

        with tempfile.TemporaryDirectory() as tmpdir:
            project_a = Path(tmpdir) / "a"
            project_b = Path(tmpdir) / "b"
            project_a.mkdir()
            project_b.mkdir()

            tool = CompareProjectsTool()
            result = tool.execute({
                "project_a": str(project_a),
                "project_b": str(project_b)
            })

            assert result["success"] is False
            assert "Comparison failed" in result["error"]

    def test_generate_comparison_markdown(self) -> None:
        """Test markdown generation for comparison."""
        tool = CompareProjectsTool()
        comparison = {
            "project_a": {
                "name": "ProjectA",
                "files": 10,
                "lines": 500,
                "functions": 20,
                "health_score": 85.0,
                "tech_debt_hours": 3.0,
                "hotspots": 2
            },
            "project_b": {
                "name": "ProjectB",
                "files": 15,
                "lines": 800,
                "functions": 30,
                "health_score": 75.0,
                "tech_debt_hours": 5.0,
                "hotspots": 4
            },
            "differences": {
                "files_delta": 5,
                "lines_delta": 300,
                "health_score_delta": -10.0,
                "tech_debt_delta_hours": 2.0
            }
        }

        markdown = tool._generate_comparison_markdown(comparison)

        assert "Project Comparison Report" in markdown
        assert "ProjectA" in markdown
        assert "ProjectB" in markdown
        assert "Size Comparison" in markdown
        assert "Quality Comparison" in markdown
        assert "+5" in markdown  # files delta
        assert "+300" in markdown  # lines delta
