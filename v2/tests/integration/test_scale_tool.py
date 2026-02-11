"""
Integration tests for check_code_scale MCP tool.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

This is T7.2: check_code_scale Tool
"""

from pathlib import Path

import pytest


class TestCheckCodeScaleTool:
    """Tests for CheckCodeScaleTool MCP tool."""

    def test_tool_initialization(self):
        """Test tool can be initialized."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        assert tool is not None

    def test_tool_schema(self):
        """Test tool has proper schema."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        schema = tool.get_tool_definition()

        assert "name" in schema
        assert schema["name"] == "check_code_scale"
        assert "description" in schema
        assert "inputSchema" in schema

    def test_analyze_python_file_basic(self, analyze_fixtures_dir):
        """Test analyzing Python file returns basic metrics."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(sample_py)})

        assert result["success"] is True
        assert "file_metrics" in result
        assert "structure" in result

        # Check file metrics
        metrics = result["file_metrics"]
        assert "total_lines" in metrics
        assert "total_characters" in metrics
        assert "file_size" in metrics
        assert metrics["total_lines"] > 0

    def test_file_metrics_accuracy(self, analyze_fixtures_dir):
        """Test file metrics are accurate."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"

        # Read file to get actual metrics
        content = sample_py.read_text(encoding="utf-8")
        actual_lines = len(content.splitlines())
        actual_chars = len(content)
        actual_size = sample_py.stat().st_size

        result = tool.execute({"file_path": str(sample_py)})

        metrics = result["file_metrics"]
        assert metrics["total_lines"] == actual_lines
        assert metrics["total_characters"] == actual_chars
        assert metrics["file_size"] == actual_size

    def test_structure_counts(self, analyze_fixtures_dir):
        """Test structure element counts."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(sample_py)})

        structure = result["structure"]
        assert "total_classes" in structure
        assert "total_functions" in structure
        assert "total_imports" in structure

        # Should have at least one class
        assert structure["total_classes"] > 0

    def test_include_details_parameter(self, analyze_fixtures_dir):
        """Test include_details parameter returns element details."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"

        # With details
        result = tool.execute({"file_path": str(sample_py), "include_details": True})

        structure = result["structure"]
        assert "classes" in structure
        assert "functions" in structure
        assert "imports" in structure

        # Classes should have details
        if structure["total_classes"] > 0:
            assert len(structure["classes"]) > 0
            cls = structure["classes"][0]
            assert "name" in cls
            assert "line_start" in cls
            assert "line_end" in cls

    def test_no_details_by_default(self, analyze_fixtures_dir):
        """Test details not included by default."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(sample_py)})

        structure = result["structure"]
        # Should only have counts, not detailed lists
        assert "total_classes" in structure
        assert "classes" not in structure or len(structure.get("classes", [])) == 0

    def test_llm_guidance_included(self, analyze_fixtures_dir):
        """Test LLM guidance is included by default."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(sample_py)})

        assert "guidance" in result
        guidance = result["guidance"]
        assert "size_category" in guidance
        assert "analysis_strategy" in guidance

    def test_llm_guidance_optional(self, analyze_fixtures_dir):
        """Test LLM guidance can be disabled."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(sample_py), "include_guidance": False})

        assert "guidance" not in result

    def test_size_category_small(self, tmp_path):
        """Test size category for small file."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()

        # Create small file (<100 lines)
        small_file = tmp_path / "small.py"
        small_file.write_text("def hello():\n    print('hello')\n")

        result = tool.execute({"file_path": str(small_file)})

        assert result["guidance"]["size_category"] == "small"

    def test_size_category_medium(self, tmp_path):
        """Test size category for medium file."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()

        # Create medium file (100-500 lines)
        medium_file = tmp_path / "medium.py"
        medium_file.write_text("\n".join([f"# Line {i}" for i in range(150)]))

        result = tool.execute({"file_path": str(medium_file)})

        assert result["guidance"]["size_category"] == "medium"

    def test_nonexistent_file_error(self):
        """Test analyzing nonexistent file returns error."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()

        result = tool.execute({"file_path": "nonexistent.py"})

        assert result["success"] is False
        assert "error" in result

    def test_output_format_toon(self, analyze_fixtures_dir):
        """Test TOON output format."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(sample_py), "output_format": "toon"})

        assert result["success"] is True
        assert result["output_format"] == "toon"


class TestBatchMode:
    """Tests for batch metrics mode."""

    def test_batch_multiple_files(self, analyze_fixtures_dir):
        """Test batch mode with multiple files."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = tool.execute(
            {"file_paths": [str(sample_py), str(sample_py)], "metrics_only": True}
        )

        assert result["success"] is True
        assert "files" in result
        assert len(result["files"]) == 2

    def test_batch_metrics_structure(self, analyze_fixtures_dir):
        """Test batch mode returns proper structure."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_paths": [str(sample_py)], "metrics_only": True})

        assert result["success"] is True
        file_result = result["files"][0]
        assert "file_path" in file_result
        assert "metrics" in file_result
        assert "total_lines" in file_result["metrics"]


class TestSizeCategoryExtended:
    """Tests for extended size categories."""

    def test_size_category_large(self, tmp_path):
        """Test size category for large file (500-1500 lines)."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        large_file = tmp_path / "large.py"
        large_file.write_text("\n".join([f"# Line {i}" for i in range(600)]))

        result = tool.execute({"file_path": str(large_file)})
        assert result["guidance"]["size_category"] == "large"

    def test_size_category_very_large(self, tmp_path):
        """Test size category for very large file (>1500 lines)."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        very_large_file = tmp_path / "very_large.py"
        very_large_file.write_text("\n".join([f"# Line {i}" for i in range(2000)]))

        result = tool.execute({"file_path": str(very_large_file)})
        assert result["guidance"]["size_category"] == "very_large"


class TestUnsupportedLanguage:
    """Tests for unsupported language handling."""

    def test_unsupported_language_returns_metrics(self, tmp_path):
        """Unsupported language should return metrics only."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        # .xyz is not a supported language
        unsupported_file = tmp_path / "test.xyz"
        unsupported_file.write_text("some content here\nline 2\n")

        result = tool.execute({"file_path": str(unsupported_file)})

        assert result["success"] is True
        assert result["structure"]["total_classes"] == 0
        assert result["structure"]["total_functions"] == 0


class TestBatchModeExtended:
    """Extended tests for batch mode."""

    def test_batch_nonexistent_file(self, tmp_path):
        """Batch mode should handle nonexistent files gracefully."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        result = tool.execute({
            "file_paths": [str(tmp_path / "nonexistent.py")],
            "metrics_only": True,
        })

        assert result["success"] is True
        assert "error" in result["files"][0]

    def test_batch_with_structure(self, analyze_fixtures_dir):
        """Batch mode without metrics_only should include structure."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"

        result = tool.execute({
            "file_paths": [str(sample_py)],
            "metrics_only": False,
        })

        assert result["success"] is True
        file_result = result["files"][0]
        assert "structure" in file_result
        assert file_result["structure"]["total_classes"] > 0

    def test_batch_mixed_files(self, analyze_fixtures_dir, tmp_path):
        """Batch mode with mix of valid and invalid files."""
        from tree_sitter_analyzer_v2.mcp.tools.scale import CheckCodeScaleTool

        tool = CheckCodeScaleTool()
        sample_py = analyze_fixtures_dir / "sample.py"
        nonexistent = tmp_path / "nope.py"

        result = tool.execute({
            "file_paths": [str(sample_py), str(nonexistent)],
            "metrics_only": True,
        })

        assert result["success"] is True
        assert len(result["files"]) == 2
        assert "metrics" in result["files"][0]
        assert "error" in result["files"][1]


@pytest.fixture
def analyze_fixtures_dir():
    """Return path to analyze test fixtures."""
    return Path(__file__).parent.parent / "fixtures" / "analyze_fixtures"
