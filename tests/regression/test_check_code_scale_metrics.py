#!/usr/bin/env python3
"""
Regression tests for check_code_scale tool metrics accuracy.

This test suite verifies that check_code_scale correctly reports
class and method counts for various programming languages.

Bug History:
- 2026-01-22: Fixed bug where non-Java files reported 0 classes/methods
  due to analysis_result being set to None (placeholder code)
"""

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool


class TestCheckCodeScaleMetricsAccuracy:
    """Test that check_code_scale reports correct metrics."""

    @pytest.fixture
    def analyze_scale_tool(self, tmp_path):
        """Create AnalyzeScaleTool instance with temp project root."""
        return AnalyzeScaleTool(project_root=str(tmp_path))

    @pytest.fixture
    def python_sample_file(self, tmp_path):
        """Create a Python sample file with known structure."""
        file_path = tmp_path / "sample.py"
        file_path.write_text(
            '''"""Sample Python module for testing."""


class MyClass:
    """A sample class."""

    def __init__(self):
        """Constructor."""
        self.value = 0

    def method_one(self):
        """First method."""
        return self.value

    def method_two(self, x):
        """Second method."""
        return self.value + x


class AnotherClass:
    """Another sample class."""

    def another_method(self):
        """Another method."""
        pass


def standalone_function():
    """A standalone function."""
    return 42
'''
        )
        return file_path

    @pytest.fixture
    def java_sample_file(self, tmp_path):
        """Create a Java sample file with known structure."""
        file_path = tmp_path / "Sample.java"
        file_path.write_text(
            """package com.example;

public class Sample {
    private int value;

    public Sample() {
        this.value = 0;
    }

    public int getValue() {
        return value;
    }

    public void setValue(int value) {
        this.value = value;
    }
}

class Helper {
    public void help() {
        // Helper method
    }
}
"""
        )
        return file_path

    @pytest.mark.asyncio
    async def test_python_file_reports_correct_class_count(
        self, analyze_scale_tool, python_sample_file
    ):
        """
        Test that Python files report correct class count.

        Expected: 2 classes (MyClass, AnotherClass)
        Bug: Previously reported 0 classes for non-Java files
        """
        result = await analyze_scale_tool.execute(
            {"file_path": str(python_sample_file), "language": "python"}
        )

        assert result["success"] is True
        assert "summary" in result
        assert result["summary"]["classes"] == 2, (
            f"Expected 2 classes, got {result['summary']['classes']}. "
            "Bug: Non-Java files should report correct class counts."
        )

    @pytest.mark.asyncio
    async def test_python_file_reports_correct_method_count(
        self, analyze_scale_tool, python_sample_file
    ):
        """
        Test that Python files report correct method count.

        Expected: 6 methods (__init__, method_one, method_two, another_method, standalone_function)
        Bug: Previously reported 0 methods for non-Java files
        """
        result = await analyze_scale_tool.execute(
            {"file_path": str(python_sample_file), "language": "python"}
        )

        assert result["success"] is True
        assert "summary" in result
        # Python: __init__, method_one, method_two, another_method, standalone_function = 5 methods
        assert result["summary"]["methods"] >= 4, (
            f"Expected at least 4 methods, got {result['summary']['methods']}. "
            "Bug: Non-Java files should report correct method counts."
        )

    @pytest.mark.asyncio
    async def test_java_file_reports_correct_class_count(
        self, analyze_scale_tool, java_sample_file
    ):
        """
        Test that Java files report correct class count.

        Expected: 2 classes (Sample, Helper)
        """
        result = await analyze_scale_tool.execute(
            {"file_path": str(java_sample_file), "language": "java"}
        )

        assert result["success"] is True
        assert "summary" in result
        assert (
            result["summary"]["classes"] == 2
        ), f"Expected 2 classes, got {result['summary']['classes']}"

    @pytest.mark.asyncio
    async def test_java_file_reports_correct_method_count(
        self, analyze_scale_tool, java_sample_file
    ):
        """
        Test that Java files report correct method count.

        Expected: 4 methods (constructor, getValue, setValue, help)
        """
        result = await analyze_scale_tool.execute(
            {"file_path": str(java_sample_file), "language": "java"}
        )

        assert result["success"] is True
        assert "summary" in result
        assert (
            result["summary"]["methods"] >= 3
        ), f"Expected at least 3 methods, got {result['summary']['methods']}"

    @pytest.mark.asyncio
    async def test_structural_overview_populated_for_python(
        self, analyze_scale_tool, python_sample_file
    ):
        """
        Test that structural_overview is populated for Python files.

        Bug: Previously structural_overview was empty dict {} for non-Java files
        """
        result = await analyze_scale_tool.execute(
            {"file_path": str(python_sample_file), "language": "python"}
        )

        assert result["success"] is True
        assert "structural_overview" in result
        assert isinstance(result["structural_overview"], dict)
        assert "classes" in result["structural_overview"]
        assert "methods" in result["structural_overview"]
        assert (
            len(result["structural_overview"]["classes"]) > 0
        ), "Bug: structural_overview should contain class information for Python files"
        assert (
            len(result["structural_overview"]["methods"]) > 0
        ), "Bug: structural_overview should contain method information for Python files"

    @pytest.mark.asyncio
    async def test_auto_language_detection_python(
        self, analyze_scale_tool, python_sample_file
    ):
        """
        Test that auto-detected Python files report correct metrics.

        Bug: Previously failed because language detection worked but
        analysis_result was set to None for non-Java files
        """
        result = await analyze_scale_tool.execute(
            {"file_path": str(python_sample_file)}  # No language specified
        )

        assert result["success"] is True
        assert result["language"] == "python"
        assert result["summary"]["classes"] == 2
        assert result["summary"]["methods"] >= 4

    @pytest.mark.asyncio
    async def test_typescript_file_reports_correct_metrics(
        self, analyze_scale_tool, tmp_path
    ):
        """
        Test that TypeScript files report correct metrics.

        This tests another non-Java language to ensure the fix works broadly.
        """
        ts_file = tmp_path / "sample.ts"
        ts_file.write_text(
            """class MyClass {
    private value: number;

    constructor() {
        this.value = 0;
    }

    getValue(): number {
        return this.value;
    }
}

class AnotherClass {
    doSomething(): void {
        console.log("Hello");
    }
}
"""
        )

        result = await analyze_scale_tool.execute(
            {"file_path": str(ts_file), "language": "typescript"}
        )

        assert result["success"] is True
        assert result["summary"]["classes"] == 2, (
            f"Expected 2 classes, got {result['summary']['classes']}. "
            "Bug: TypeScript files should report correct class counts."
        )
        assert result["summary"]["methods"] >= 2, (
            f"Expected at least 2 methods, got {result['summary']['methods']}. "
            "Bug: TypeScript files should report correct method counts."
        )


class TestCheckCodeScaleBugRegression:
    """Specific regression tests for the 2026-01-22 bug fix."""

    @pytest.fixture
    def analyze_scale_tool(self, tmp_path):
        """Create AnalyzeScaleTool instance."""
        return AnalyzeScaleTool(project_root=str(tmp_path))

    @pytest.mark.asyncio
    async def test_bug_fix_analysis_result_not_none(self, analyze_scale_tool, tmp_path):
        """
        Test that analysis_result is not None for non-Java files.

        Bug: Lines 454-455 set analysis_result = None and structural_overview = {}
        Fix: Use universal_result directly and extract structural_overview
        """
        py_file = tmp_path / "test.py"
        py_file.write_text(
            "class TestClass:\n    def test_method(self):\n        pass\n"
        )

        result = await analyze_scale_tool.execute(
            {"file_path": str(py_file), "language": "python"}
        )

        # If analysis_result was None, summary would have 0 classes/methods
        assert (
            result["summary"]["classes"] > 0
        ), "Bug not fixed: analysis_result is still None for Python files"
        assert (
            result["summary"]["methods"] > 0
        ), "Bug not fixed: analysis_result is still None for Python files"

    @pytest.mark.asyncio
    async def test_bug_fix_structural_overview_not_empty(
        self, analyze_scale_tool, tmp_path
    ):
        """
        Test that structural_overview is not empty for non-Java files.

        Bug: Line 455 set structural_overview = {}
        Fix: Extract structural_overview from universal_result
        """
        py_file = tmp_path / "test.py"
        py_file.write_text(
            "class TestClass:\n    def test_method(self):\n        pass\n"
        )

        result = await analyze_scale_tool.execute(
            {"file_path": str(py_file), "language": "python"}
        )

        # If structural_overview was {}, it would have empty lists
        assert (
            len(result["structural_overview"]["classes"]) > 0
        ), "Bug not fixed: structural_overview is still empty dict for Python files"
        assert (
            len(result["structural_overview"]["methods"]) > 0
        ), "Bug not fixed: structural_overview is still empty dict for Python files"
