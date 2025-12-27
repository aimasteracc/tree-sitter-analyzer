#!/usr/bin/env python3
"""
Test cases for analyze_code_scale MCP tool

Tests the enhanced code scale analysis tool that provides metrics about
code complexity, size, and structure with LLM-optimized guidance.
"""

import tempfile
from pathlib import Path

# Mock functionality now provided by pytest-mock
import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool


class TestAnalyzeScaleToolEnhanced:
    """Test enhanced analyze_code_scale tool functionality"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.tool = AnalyzeScaleTool()
        self.sample_java_code = """
package com.example;

import java.util.List;
import java.util.ArrayList;

/**
 * Sample class for testing enhanced analysis
 */
public class SampleClass {
    private String name;
    private int value;

    /**
     * Constructor
     */
    public SampleClass(String name, int value) {
        this.name = name;
        this.value = value;
    }

    /**
     * Get name
     */
    public String getName() {
        return name;
    }

    /**
     * Complex calculation method
     */
    public int complexCalculation(int input) {
        if (input > 0) {
            for (int i = 0; i < input; i++) {
                if (i % 2 == 0) {
                    value += i;
                } else {
                    value -= i;
                }
            }
            return value * input;
        } else if (input < 0) {
            return Math.abs(input);
        } else {
            return 0;
        }
    }
}
"""

    def test_tool_schema_structure(self) -> None:
        """Test that enhanced tool schema has required structure"""
        schema = self.tool.get_tool_schema()

        # Test schema structure
        assert "type" in schema
        assert "properties" in schema
        # Required fields are expressed via oneOf to support batch mode
        assert "oneOf" in schema

        # Test schema type
        assert schema["type"] == "object"

        # Ensure single-mode requirement includes file_path
        one_of = schema["oneOf"]
        assert any(
            "required" in opt and "file_path" in opt["required"] for opt in one_of
        )

        # Test properties
        properties = schema["properties"]
        assert "file_path" in properties
        assert "language" in properties
        assert "include_complexity" in properties
        assert "include_details" in properties
        assert "include_guidance" in properties  # New field

    def test_validate_arguments_valid(self) -> None:
        """Test argument validation with valid arguments"""
        valid_args = {
            "file_path": "/path/to/file.java",
            "language": "java",
            "include_complexity": True,
            "include_details": False,
            "include_guidance": True,
        }

        # Should not raise exception
        result = self.tool.validate_arguments(valid_args)
        assert result is True

    def test_validate_arguments_missing_required(self) -> None:
        """Test argument validation with missing required field"""
        invalid_args = {"language": "java"}

        with pytest.raises(ValueError) as exc_info:
            self.tool.validate_arguments(invalid_args)

        assert "file_path" in str(exc_info.value)

    def test_validate_arguments_invalid_types(self) -> None:
        """Test argument validation with invalid types"""
        invalid_args = {
            "file_path": 123,  # Should be string
            "include_complexity": "yes",  # Should be boolean
            "include_guidance": "true",  # Should be boolean
        }

        with pytest.raises(ValueError):
            self.tool.validate_arguments(invalid_args)

    @pytest.mark.asyncio
    async def test_execute_with_java_file(self) -> None:
        """Test executing enhanced analysis on a real Java file"""
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(self.sample_java_code)
            temp_path = f.name

        try:
            # Execute analysis (use JSON format for test assertions)
            result = await self.tool.execute(
                {
                    "file_path": temp_path,
                    "include_guidance": True,
                    "output_format": "json",
                }
            )

            # Test result structure
            expected_keys = [
                "file_path",
                "language",
                "file_metrics",
                "summary",
                "structural_overview",
                "llm_guidance",
            ]
            for key in expected_keys:
                assert key in result

            # Test file metrics
            metrics = result["file_metrics"]
            assert "total_lines" in metrics
            assert "code_lines" in metrics
            assert "comment_lines" in metrics
            assert "blank_lines" in metrics
            assert "estimated_tokens" in metrics
            assert "file_size_bytes" in metrics
            assert "file_size_kb" in metrics

            # Test summary
            summary = result["summary"]
            assert "classes" in summary
            assert "methods" in summary
            assert "fields" in summary
            assert "imports" in summary
            assert summary["classes"] == 1  # SampleClass
            assert summary["methods"] >= 3  # Constructor + getName + complexCalculation

            # Test structural overview
            overview = result["structural_overview"]
            assert "classes" in overview
            assert "methods" in overview
            assert "fields" in overview
            assert "imports" in overview
            assert "complexity_hotspots" in overview

            # Test LLM guidance
            guidance = result["llm_guidance"]
            assert "size_category" in guidance
            assert "analysis_strategy" in guidance
            assert "recommended_tools" in guidance
            assert "complexity_assessment" in guidance

            # Test that guidance provides meaningful information
            assert guidance["size_category"] in [
                "small",
                "medium",
                "large",
                "very_large",
            ]
            assert isinstance(guidance["recommended_tools"], list)

        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_execute_without_guidance(self) -> None:
        """Test executing analysis without LLM guidance"""
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(self.sample_java_code)
            temp_path = f.name

        try:
            # Execute analysis without guidance (use JSON format for test assertions)
            result = await self.tool.execute(
                {
                    "file_path": temp_path,
                    "include_guidance": False,
                    "output_format": "json",
                }
            )

            # Should not include guidance
            assert "llm_guidance" not in result

            # Should still include other sections
            assert "file_metrics" in result
            assert "summary" in result
            assert "structural_overview" in result

        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_execute_with_details(self) -> None:
        """Test executing analysis with detailed information"""
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(self.sample_java_code)
            temp_path = f.name

        try:
            # Execute analysis with details (use JSON format for test assertions)
            result = await self.tool.execute(
                {
                    "file_path": temp_path,
                    "include_details": True,
                    "output_format": "json",
                }
            )

            # Should include detailed analysis
            assert "detailed_analysis" in result

            detailed = result["detailed_analysis"]
            assert "statistics" in detailed
            assert "classes" in detailed
            assert "methods" in detailed
            assert "fields" in detailed

        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_execute_with_nonexistent_file(self) -> None:
        """Test error handling for nonexistent file"""
        with pytest.raises(ValueError):
            await self.tool.execute({"file_path": "/nonexistent/file.java"})

    @pytest.mark.asyncio
    async def test_execute_with_missing_file_path(self) -> None:
        """Test error handling for missing file_path argument"""
        with pytest.raises(ValueError) as exc_info:
            await self.tool.execute({"language": "java"})

        assert "file_path is required" in str(exc_info.value)

    def test_file_metrics_calculation(self) -> None:
        """Test file metrics calculation functionality"""
        # Create temporary file with known content
        test_content = """// Comment line
package com.test;

public class Test {
    private int field;

    public void method() {
        // Another comment
        System.out.println("Hello");
    }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(test_content)
            temp_path = f.name

        try:
            metrics = self.tool._calculate_file_metrics(temp_path)

            # Test that metrics are calculated
            assert metrics["total_lines"] > 0
            assert metrics["code_lines"] > 0
            assert metrics["comment_lines"] > 0
            assert metrics["blank_lines"] >= 0
            assert metrics["estimated_tokens"] > 0
            assert metrics["file_size_bytes"] > 0
            assert metrics["file_size_kb"] > 0

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_llm_guidance_generation(self) -> None:
        """Test LLM guidance generation"""
        # Mock file metrics and structural overview
        file_metrics = {
            "total_lines": 150,
            "code_lines": 100,
            "comment_lines": 30,
            "blank_lines": 20,
            "estimated_tokens": 500,
            "file_size_bytes": 3000,
            "file_size_kb": 3.0,
        }

        structural_overview = {
            "classes": [{"name": "TestClass", "start_line": 10, "end_line": 100}],
            "methods": [
                {"name": "method1", "complexity": 5},
                {"name": "method2", "complexity": 15},  # High complexity
            ],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [
                {"name": "method2", "complexity": 15, "start_line": 50, "end_line": 80}
            ],
        }

        guidance = self.tool._generate_llm_guidance(file_metrics, structural_overview)

        # Test guidance structure
        assert "size_category" in guidance
        assert "analysis_strategy" in guidance
        assert "recommended_tools" in guidance
        assert "complexity_assessment" in guidance

        # Test that guidance is meaningful
        assert guidance["size_category"] == "medium"  # 150 lines
        assert "complexity hotspots" in guidance["complexity_assessment"]
        assert isinstance(guidance["recommended_tools"], list)

    def test_tool_definition(self) -> None:
        """Test tool definition structure"""
        definition = self.tool.get_tool_definition()

        # Test that definition has required fields
        if isinstance(definition, dict):
            assert "name" in definition
            assert "description" in definition
            assert "inputSchema" in definition
            assert definition["name"] == "check_code_scale"
        else:
            # MCP Tool object
            assert definition.name == "analyze_code_scale"
            assert definition.description is not None
            assert definition.inputSchema is not None


class TestAnalyzeScaleToolIntegration:
    """Test integration with existing analyzer components"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.tool = AnalyzeScaleTool()

    @pytest.mark.asyncio
    async def test_integration_with_advanced_analyzer(self) -> None:
        """Test integration with AdvancedAnalyzer"""
        # Create a simple Java file
        java_code = """
package com.test;

public class SimpleClass {
    public void simpleMethod() {
        System.out.println("Hello");
    }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            # Use JSON format for test assertions
            result = await self.tool.execute(
                {"file_path": temp_path, "output_format": "json"}
            )

            # Test that AdvancedAnalyzer integration works
            assert "summary" in result
            assert "structural_overview" in result

            # Test that we get expected analysis results
            summary = result["summary"]
            assert summary["classes"] == 1
            assert summary["methods"] >= 1

        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_language_detection_integration(self) -> None:
        """Test integration with language detection"""
        # Create a Java file without specifying language
        java_code = """
public class Test {
    public static void main(String[] args) {
        System.out.println("Hello World");
    }
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            # Don't specify language - should be auto-detected (use JSON format for test assertions)
            result = await self.tool.execute(
                {"file_path": temp_path, "output_format": "json"}
            )

            # Test that language was detected
            assert result["language"] == "java"

        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestAnalyzeScaleToolPerformance:
    """Test performance characteristics of enhanced analyze_code_scale tool"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.tool = AnalyzeScaleTool()

    @pytest.mark.asyncio
    async def test_performance_monitoring_integration(self) -> None:
        """Test that performance monitoring is properly integrated"""
        # Create a simple test file
        java_code = """
public class PerfTest {
    public void method() {}
}
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_path = f.name

        try:
            # Execute analysis - should not raise any performance monitoring errors (use JSON format)
            result = await self.tool.execute(
                {"file_path": temp_path, "output_format": "json"}
            )

            # Test that analysis completed successfully
            assert "file_metrics" in result
            assert "summary" in result

        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestAnalyzeScaleToolErrorHandling:
    """Test error handling in enhanced analyze_code_scale tool"""

    def setup_method(self) -> None:
        """Set up test fixtures"""
        self.tool = AnalyzeScaleTool()

    @pytest.mark.asyncio
    async def test_invalid_file_path(self) -> None:
        """Test handling of invalid file paths"""
        with pytest.raises(ValueError):
            await self.tool.execute({"file_path": "/invalid/path/file.java"})

    @pytest.mark.asyncio
    async def test_unsupported_language(self) -> None:
        """Test handling of unsupported language"""
        # Create a file with unknown extension
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".unknown", delete=False
        ) as f:
            f.write("some content")
            temp_path = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                await self.tool.execute({"file_path": temp_path})

            assert "Invalid file path" in str(exc_info.value)

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_file_metrics_error_handling(self) -> None:
        """Test error handling in file metrics calculation"""
        # Test with non-existent file
        metrics = self.tool._calculate_file_metrics("/nonexistent/file.java")

        # Should return default values instead of raising exception
        assert metrics["total_lines"] == 0
        assert metrics["code_lines"] == 0
        assert metrics["estimated_tokens"] == 0


if __name__ == "__main__":
    pytest.main([__file__])
