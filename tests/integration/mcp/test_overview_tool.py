"""
Integration tests for overview MCP tool.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tree_sitter_analyzer.mcp.tools.overview_tool import OverviewTool
from tree_sitter_analyzer.overview.aggregator import OverviewAggregator
from tree_sitter_analyzer.overview.reporter import OverviewReporter


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a sample project for testing."""
    # Create a simple Python file
    (tmp_path / "main.py").write_text("""
def hello():
    print("Hello, world!")

class Foo:
    def method(self):
        pass
""")

    # Create a JavaScript file
    (tmp_path / "script.js").write_text("""
function hello() {
    console.log("Hello");
}
""")

    return tmp_path


class TestOverviewTool:
    """Integration tests for OverviewTool."""

    @pytest.fixture
    def tool(self, sample_project: Path) -> OverviewTool:
        """Create overview tool instance."""
        return OverviewTool(project_root=str(sample_project))

    def test_tool_name(self, tool: OverviewTool) -> None:
        """Should have correct tool name."""
        assert tool.get_name() == "overview"

    def test_tool_definition(self, tool: OverviewTool) -> None:
        """Should have correct tool definition."""
        definition = tool.get_tool_definition()

        assert definition["name"] == "overview"
        assert "include" in definition["inputSchema"]["properties"]
        assert "format" in definition["inputSchema"]["properties"]
        assert "parallel" in definition["inputSchema"]["properties"]

    def test_get_parameters(self, tool: OverviewTool) -> None:
        """Should return correct parameters schema."""
        params = tool.get_parameters()

        assert "properties" in params
        assert "include" in params["properties"]
        assert "format" in params["properties"]
        assert "parallel" in params["properties"]

    def test_execute_markdown_format(self, tool: OverviewTool) -> None:
        """Should generate markdown format report."""
        result = tool.execute({"format": "markdown"})

        assert "# Project Overview Report" in result
        assert "## Summary" in result

    def test_execute_json_format(self, tool: OverviewTool) -> None:
        """Should generate JSON format report."""
        result = tool.execute({"format": "json"})

        import json
        data = json.loads(result)
        assert "project_path" in data
        assert isinstance(data, dict)

    def test_execute_toon_format(self, tool: OverviewTool) -> None:
        """Should generate TOON format report."""
        result = tool.execute({"format": "toon"})

        assert isinstance(result, str)
        assert len(result) > 0

    def test_execute_with_include_filter(self, tool: OverviewTool) -> None:
        """Should support include filter."""
        result = tool.execute({
            "format": "json",
            "include": ["health_score"],
        })

        import json
        data = json.loads(result)
        # Should have project_path and health_scores
        assert "project_path" in data

    def test_execute_with_parallel_disabled(self, tool: OverviewTool) -> None:
        """Should support parallel parameter."""
        result = tool.execute({
            "format": "markdown",
            "parallel": False,
        })

        assert "# Project Overview Report" in result

    def test_get_description(self, tool: OverviewTool) -> None:
        """Should return description."""
        description = tool.get_description()
        assert "unified" in description.lower()
        assert "overview" in description.lower()


class TestOverviewAggregator:
    """Integration tests for OverviewAggregator."""

    @pytest.fixture
    def aggregator(self, sample_project: Path) -> OverviewAggregator:
        """Create aggregator instance."""
        return OverviewAggregator(str(sample_project))

    def test_generate_overview(self, aggregator: OverviewAggregator) -> None:
        """Should generate overview report."""
        report = aggregator.generate_overview()

        assert report.project_path == str(aggregator.project_path)
        assert hasattr(report, "to_dict")

    def test_generate_overview_with_include(self, aggregator: OverviewAggregator) -> None:
        """Should generate overview with specific analyses."""
        report = aggregator.generate_overview(include=["health_score"])

        assert report.project_path == str(aggregator.project_path)

    def test_generate_overview_sequential(self, sample_project: Path) -> None:
        """Should generate overview sequentially."""
        aggregator = OverviewAggregator(str(sample_project), parallel=False)
        report = aggregator.generate_overview()

        assert report.project_path == str(sample_project)


class TestOverviewReporter:
    """Integration tests for OverviewReporter."""

    @pytest.fixture
    def report(self, sample_project: Path) -> Any:
        """Create a sample report."""
        from tree_sitter_analyzer.overview.aggregator import OverviewReport
        return OverviewReport(project_path=str(sample_project))

    @pytest.fixture
    def reporter(self, report: Any) -> OverviewReporter:
        """Create reporter instance."""
        return OverviewReporter(report)

    def test_generate_markdown(self, reporter: OverviewReporter) -> None:
        """Should generate markdown report."""
        markdown = reporter.generate_markdown()

        assert "# Project Overview Report" in markdown
        assert "## Summary" in markdown
        assert "Project" in markdown

    def test_generate_json(self, reporter: OverviewReporter) -> None:
        """Should generate JSON report."""
        import json
        json_output = reporter.generate_json()

        data = json.loads(json_output)
        assert "project_path" in data

    def test_generate_toon(self, reporter: OverviewReporter) -> None:
        """Should generate TOON report."""
        toon = reporter.generate_toon()

        assert isinstance(toon, str)
        assert len(toon) > 0


class TestEndToEndFlow:
    """End-to-end tests for the overview flow."""

    def test_full_overview_flow(self, sample_project: Path) -> None:
        """Should complete full overview flow."""
        # Step 1: Create aggregator
        aggregator = OverviewAggregator(str(sample_project))

        # Step 2: Generate overview
        report = aggregator.generate_overview()

        # Step 3: Create reporter
        reporter = OverviewReporter(report)

        # Step 4: Generate output in multiple formats
        markdown = reporter.generate_markdown()
        json_output = reporter.generate_json()
        toon = reporter.generate_toon()

        assert "# Project Overview Report" in markdown
        assert "project_path" in json_output
        assert len(toon) > 0

    def test_mcp_tool_flow(self, sample_project: Path) -> None:
        """Should work as MCP tool."""
        tool = OverviewTool(project_root=str(sample_project))

        # Test all formats
        for output_format in ["markdown", "json", "toon"]:
            result = tool.execute({"format": output_format})
            assert isinstance(result, str)
            assert len(result) > 0

    def test_filtered_overview_flow(self, sample_project: Path) -> None:
        """Should work with filtered analyses."""
        tool = OverviewTool(project_root=str(sample_project))

        result = tool.execute({
            "format": "json",
            "include": ["health_score"],
        })

        import json
        data = json.loads(result)
        assert "project_path" in data
