#!/usr/bin/env python3
"""
Unit tests for UnderstandCodebaseTool MCP tool.

This is the "one entry point" for codebase understanding.
Tests cover all three depth levels: quick, standard, deep.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from tree_sitter_analyzer.mcp.tools.understand_codebase_tool import (
    UnderstandCodebaseTool,
)
from tree_sitter_analyzer.mcp.utils.error_handler import AnalysisError


class TestUnderstandCodebaseTool:
    """Test UnderstandCodebaseTool MCP tool."""

    @pytest.fixture
    def tool(self) -> UnderstandCodebaseTool:
        """Create tool instance."""
        return UnderstandCodebaseTool()

    @pytest.fixture
    def sample_project(self, tmp_path: Path) -> Path:
        """Create a sample project with multiple files."""
        # Create project structure
        (tmp_path / "src").mkdir()

        # Python files
        (tmp_path / "src" / "main.py").write_text("""
def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
""")

        (tmp_path / "src" / "utils.py").write_text("""
def helper(x):
    return x * 2

class Utils:
    pass
""")

        # JavaScript files
        (tmp_path / "src" / "app.js").write_text("""
function main() {
    console.log("Hello");
}

main();
""")

        return tmp_path

    @pytest.mark.asyncio
    async def test_tool_definition(self, tool: UnderstandCodebaseTool) -> None:
        """Tool has valid definition."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "understand_codebase"
        assert "理解代码库" in definition["description"]
        assert "inputSchema" in definition

    @pytest.mark.asyncio
    async def test_quick_analysis_depth(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """Quick depth analysis returns overview and basic health."""
        result = await tool.execute({
            "project_root": str(sample_project),
            "depth": "quick",
            "output_format": "json",  # Use JSON for structured assertions
        })

        assert "overview" in result
        assert result["overview"]["total_files"] > 0
        assert "languages" in result["overview"]
        assert "health" in result
        assert "overall_grade" in result["health"]

    @pytest.mark.asyncio
    async def test_standard_analysis_depth(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """Standard depth analysis includes metrics."""
        result = await tool.execute({
            "project_root": str(sample_project),
            "depth": "standard",
            "output_format": "json",  # Use JSON for structured assertions
        })

        assert "overview" in result
        assert "metrics" in result
        assert "average_file_lines" in result["metrics"]
        assert "largest_file_lines" in result["metrics"]

    @pytest.mark.asyncio
    async def test_deep_analysis_depth(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """Deep depth analysis includes deep_metrics."""
        result = await tool.execute({
            "project_root": str(sample_project),
            "depth": "deep",
            "output_format": "json",  # Use JSON for structured assertions
        })

        assert "overview" in result
        assert "metrics" in result
        assert "deep_metrics" in result
        assert "total_size_bytes" in result["deep_metrics"]

    @pytest.mark.asyncio
    async def test_default_depth_is_standard(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """Default depth is standard."""
        result = await tool.execute({
            "project_root": str(sample_project),
            "output_format": "json",  # Use JSON for structured assertions
        })

        assert result["depth"] == "standard"

    @pytest.mark.asyncio
    async def test_max_files_limit(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """max_files parameter limits analysis scope."""
        result = await tool.execute({
            "project_root": str(sample_project),
            "depth": "quick",
            "max_files": 2,
            "output_format": "json",  # Use JSON for structured assertions
        })

        assert result["files_analyzed"] <= 2

    @pytest.mark.asyncio
    async def test_file_patterns_filter(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """file_patterns parameter filters which files to analyze."""
        result = await tool.execute({
            "project_root": str(sample_project),
            "depth": "quick",
            "file_patterns": ["**/*.py"],
            "output_format": "json",  # Use JSON for structured assertions
        })

        # Should only analyze Python files
        assert "python" in result["overview"]["languages"]

    @pytest.mark.asyncio
    async def test_toon_output_format(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """TOON format is supported."""
        result = await tool.execute({
            "project_root": str(sample_project),
            "depth": "quick",
            "output_format": "toon",
        })

        # TOON format has specific structure
        assert result["format"] == "toon"
        assert "toon_content" in result
        # TOON format should be compact
        output_str = result["toon_content"]
        assert len(output_str) < 5000  # TOON should be compact

    @pytest.mark.asyncio
    async def test_json_output_format(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """JSON format is supported."""
        result = await tool.execute({
            "project_root": str(sample_project),
            "depth": "quick",
            "output_format": "json",
        })

        # JSON should have structure
        assert "overview" in result
        assert "health" in result

    @pytest.mark.asyncio
    async def test_invalid_project_root_raises_error(
        self, tool: UnderstandCodebaseTool
    ) -> None:
        """Invalid project root raises error."""
        with pytest.raises((ValueError, AnalysisError), match="does not exist"):
            await tool.execute({
                "project_root": "/nonexistent/path",
            })

    @pytest.mark.asyncio
    async def test_invalid_depth_raises_error(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """Invalid depth raises error."""
        with pytest.raises((ValueError, AnalysisError), match="Invalid depth"):
            await tool.execute({
                "project_root": str(sample_project),
                "depth": "invalid",
            })

    @pytest.mark.asyncio
    async def test_empty_project_returns_zero_files(
        self, tool: UnderstandCodebaseTool, tmp_path: Path
    ) -> None:
        """Empty project raises appropriate error."""
        with pytest.raises((ValueError, AnalysisError), match="No source files found"):
            await tool.execute({
                "project_root": str(tmp_path),
            })

    @pytest.mark.asyncio
    async def test_language_detection(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """Tool correctly detects different languages."""
        result = await tool.execute({
            "project_root": str(sample_project),
            "depth": "quick",
            "output_format": "json",  # Use JSON for structured assertions
        })

        languages = result["overview"]["languages"]
        assert "python" in languages
        assert languages["python"] > 0

    @pytest.mark.asyncio
    async def test_health_assessment(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """Health assessment provides meaningful feedback."""
        result = await tool.execute({
            "project_root": str(sample_project),
            "depth": "quick",
            "output_format": "json",  # Use JSON for structured assertions
        })

        health = result["health"]
        assert "overall_grade" in health
        assert "assessment" in health
        assert isinstance(health["overall_grade"], str)
        assert len(health["overall_grade"]) == 1  # Single letter grade

    @pytest.mark.asyncio
    async def test_primary_language_detection(
        self, tool: UnderstandCodebaseTool, sample_project: Path
    ) -> None:
        """Tool correctly identifies primary language."""
        result = await tool.execute({
            "project_root": str(sample_project),
            "depth": "quick",
            "output_format": "json",  # Use JSON for structured assertions
        })

        # Sample project has more Python files
        assert result["overview"]["primary_language"] == "python"

    @pytest.mark.asyncio
    async def test_typescript优先于_javascript(
        self, tool: UnderstandCodebaseTool, tmp_path: Path
    ) -> None:
        """When both JS and TS files exist, TS should be primary."""
        # Create project with both
        (tmp_path / "app.js").write_text("console.log('js');")
        (tmp_path / "app.ts").write_text("console.log('ts');")

        result = await tool.execute({
            "project_root": str(tmp_path),
            "depth": "quick",
            "output_format": "json",  # Use JSON for structured assertions
        })

        # TS should be primary when both present
        assert result["overview"]["primary_language"] == "typescript"

    @pytest.mark.asyncio
    async def test_collect_source_files_with_patterns(
        self, tool: UnderstandCodebaseTool
    ) -> None:
        """_collect_source_files respects file patterns."""
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "test.py").write_text("# python")
            (tmp_path / "test.js").write_text("// javascript")
            (tmp_path / "test.txt").write_text("text")

            # Only collect Python files
            files = await tool._collect_source_files(
                tmp_path, ["**/*.py"], 100
            )

            assert len(files) == 1
            assert files[0].name == "test.py"

    @pytest.mark.asyncio
    async def test_collect_source_files_limits_max_files(
        self, tool: UnderstandCodebaseTool
    ) -> None:
        """_collect_source_files respects max_files limit."""
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for i in range(10):
                (tmp_path / f"file{i}.py").write_text(f"# file {i}")

            # Limit to 3 files
            files = await tool._collect_source_files(
                tmp_path, ["**/*.py"], 3
            )

            assert len(files) == 3

    @pytest.mark.asyncio
    async def test_collect_source_files_deduplicates(
        self, tool: UnderstandCodebaseTool
    ) -> None:
        """_collect_source_files deduplicates files."""
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            test_file = tmp_path / "test.py"
            test_file.write_text("# python")

            # Multiple patterns matching same file
            files = await tool._collect_source_files(
                tmp_path, ["**/*.py", "**/*.py"], 100
            )

            assert len(files) == 1
            assert files[0] == test_file

    def test_detect_language(self, tool: UnderstandCodebaseTool) -> None:
        """_detect_language correctly identifies languages."""
        assert tool._detect_language(Path("test.py")) == "python"
        assert tool._detect_language(Path("test.js")) == "javascript"
        assert tool._detect_language(Path("test.ts")) == "typescript"
        assert tool._detect_language(Path("test.java")) == "java"
        assert tool._detect_language(Path("test.go")) == "go"
        assert tool._detect_language(Path("test.rs")) == "rust"
        assert tool._detect_language(Path("test.c")) == "c"
        assert tool._detect_language(Path("test.cpp")) == "cpp"
        assert tool._detect_language(Path("test.php")) == "php"
        assert tool._detect_language(Path("test.rb")) == "ruby"
        assert tool._detect_language(Path("test.kt")) == "kotlin"
        assert tool._detect_language(Path("test.swift")) == "swift"
        assert tool._detect_language(Path("test.unknown")) == "unknown"

    def test_calculate_basic_health_score(self, tool: UnderstandCodebaseTool) -> None:
        """_calculate_basic_health_score returns valid grades."""
        # Small project
        assert tool._calculate_basic_health_score(10, 500) == "A"
        # Medium project
        assert tool._calculate_basic_health_score(600, 30000) == "B"
        # Large project
        assert tool._calculate_basic_health_score(1200, 80000) == "C"

    def test_get_health_assessment(self, tool: UnderstandCodebaseTool) -> None:
        """_get_health_assessment returns meaningful descriptions."""
        assert "健康" in tool._get_health_assessment("A")
        assert "良好" in tool._get_health_assessment("B")
        assert "需关注" in tool._get_health_assessment("C")
        assert "风险" in tool._get_health_assessment("D")
        assert "严重" in tool._get_health_assessment("F")

    def test_get_primary_language(self, tool: UnderstandCodebaseTool) -> None:
        """_get_primary_language returns most common language."""
        # Python dominant
        counts = {"python": 10, "javascript": 2}
        assert tool._get_primary_language(counts) == "python"

        # JS dominant
        counts = {"javascript": 5, "python": 1}
        assert tool._get_primary_language(counts) == "javascript"

        # Empty
        assert tool._get_primary_language({}) == "unknown"

        # TS + JS mix (TS priority)
        counts = {"javascript": 5, "typescript": 3}
        assert tool._get_primary_language(counts) == "typescript"
