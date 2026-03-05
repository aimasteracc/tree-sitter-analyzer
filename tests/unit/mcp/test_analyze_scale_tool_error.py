"""Tests for AnalyzeScaleTool error handling."""

import pytest


class TestAnalyzeScaleToolErrorHandling:
    """Test error handling for non-Java structural analysis."""

    @pytest.fixture
    def tool(self, tmp_path):
        """Create AnalyzeScaleTool instance."""
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        return AnalyzeScaleTool(str(tmp_path))

    @pytest.mark.asyncio
    async def test_non_java_file_returns_warning(self, tool, tmp_path):
        """Non-Java files should return warning, not empty data."""
        # Create a Python file
        python_file = tmp_path / "test.py"
        python_file.write_text("def hello(): pass")

        arguments = {
            "file_path": str(python_file),
            "include_guidance": False,
        }

        result = await tool.execute(arguments)

        # Should succeed but include warning about limited structural analysis
        assert result.get("success") is True
        # Check for warning about structural analysis limitation
        warnings = result.get("warnings", [])
        assert len(warnings) > 0, "Should have warning about structural analysis"
        assert any(
            "structural" in w.lower() or "python" in w.lower() for w in warnings
        ), f"Warning should mention structural analysis or python, got: {warnings}"

    @pytest.mark.asyncio
    async def test_java_file_works_correctly(self, tool, tmp_path):
        """Java files should work correctly."""
        # Create a Java file
        java_file = tmp_path / "Test.java"
        java_file.write_text(
            """
public class Test {
    public void method() {}
}
"""
        )

        arguments = {
            "file_path": str(java_file),
            "include_guidance": False,
        }

        result = await tool.execute(arguments)

        # Should succeed
        assert result.get("success") is True
        # Should have structural overview or classes in summary
        summary = result.get("summary", {})
        assert "classes" in summary
