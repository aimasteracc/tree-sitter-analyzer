#!/usr/bin/env python3
"""Tests for token optimization in analyze_scale_tool."""
import os
import tempfile

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool


class TestAnalyzeScaleToolTokenOptimization:
    """Tests for analyze_scale_tool token optimization."""

    @pytest.mark.asyncio
    async def test_non_java_file_no_structural_overview_when_no_guidance(self):
        """Non-Java files should not include structural_overview when guidance is disabled."""
        # Create a Python file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello():\n    print("hello")\n')
            temp_path = f.name

        try:
            tool = AnalyzeScaleTool()
            result = await tool.execute({
                "file_path": temp_path,
                "output_format": "json",
                "include_guidance": False,  # Disable guidance so structural_overview won't be populated
            })

            # Should not have structural_overview key at all, or it should be None
            # The optimization is to NOT include empty placeholder dicts
            assert "structural_overview" not in result or result["structural_overview"] is None, (
                f"structural_overview should not be present or should be None for non-Java files, "
                f"got: {result.get('structural_overview')}"
            )
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_structural_overview_not_empty_placeholder(self):
        """structural_overview should either have real data or be omitted entirely."""
        # Create a simple Python file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('# Simple file\nx = 1\n')
            temp_path = f.name

        try:
            tool = AnalyzeScaleTool()
            result = await tool.execute({
                "file_path": temp_path,
                "output_format": "json",
                "include_guidance": False,  # Disable guidance
            })

            # Check that we don't have an empty structural_overview
            if "structural_overview" in result:
                so = result["structural_overview"]
                # Should be None (no data) rather than empty dict placeholder
                assert so is None or (isinstance(so, dict) and len(so) > 0), (
                    f"structural_overview should be None or have data, not empty dict. Got: {so}"
                )
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_java_file_still_has_structural_overview(self):
        """Java files should still have structural_overview with data."""
        # Create a simple Java file
        java_code = '''
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            tool = AnalyzeScaleTool()
            result = await tool.execute({
                "file_path": temp_path,
                "output_format": "json",
                "include_guidance": False,  # Even without guidance, Java should have structural data
            })

            # Java files should have structural_overview with data
            assert "structural_overview" in result, (
                "Java files should have structural_overview"
            )
            so = result["structural_overview"]
            assert so is not None, "structural_overview should not be None for Java files"
            assert isinstance(so, dict), "structural_overview should be a dict for Java files"
            # Should have at least classes or methods populated
            assert len(so) > 0, "structural_overview should have data for Java files"
        finally:
            os.unlink(temp_path)

    @pytest.mark.asyncio
    async def test_structural_overview_omitted_for_non_java(self):
        """For non-Java files, structural_overview field should be omitted entirely when no data."""
        # Create a simple Python file with no complex structure
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('# Empty file\n')
            temp_path = f.name

        try:
            tool = AnalyzeScaleTool()
            result = await tool.execute({
                "file_path": temp_path,
                "output_format": "json",
                "include_guidance": False,
            })

            # The optimization: structural_overview should be omitted entirely
            # rather than being an empty dict that wastes tokens
            assert "structural_overview" not in result or result["structural_overview"] is None, (
                f"structural_overview should be omitted for non-Java files without structure data. "
                f"Got: {result.get('structural_overview')}"
            )
        finally:
            os.unlink(temp_path)
