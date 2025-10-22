#!/usr/bin/env python3
"""
Tests for CLI-Compatible Analyze Scale Tool

This module tests the CLI-compatible analyze scale tool functionality including
schema validation, execution, error handling, and CLI output format compatibility.
Follows TDD principles and .roo-config.json requirements.
"""

import json
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Import the module under test
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible import (
    AnalyzeScaleToolCLICompatible,
    analyze_scale_tool_cli_compatible,
)


@pytest.fixture
def tool() -> AnalyzeScaleToolCLICompatible:
    """Fixture providing AnalyzeScaleToolCLICompatible instance"""
    return AnalyzeScaleToolCLICompatible()


@pytest.fixture
def sample_java_file() -> str:
    """Fixture providing a temporary Java file for testing"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
        f.write(
            """
package com.example.test;

import java.util.List;
import java.util.Map;

/**
 * Sample class for testing
 */
public class TestClass {
    private String field1;
    private int field2;

    /**
     * Constructor
     */
    public TestClass(String field1, int field2) {
        this.field1 = field1;
        this.field2 = field2;
    }

    /**
     * Public method
     */
    public String getField1() {
        return field1;
    }

    /**
     * Private method
     */
    private void privateMethod() {
        // Implementation
    }
}
"""
        )
        return f.name


@pytest.fixture
def sample_analysis_result() -> MagicMock:
    """Fixture providing mock analysis result"""
    result = MagicMock()
    result.package = MagicMock()
    result.package.name = "com.example.test"

    # Create mock elements with element_type attributes
    import_element1 = MagicMock()
    import_element1.element_type = "import"
    import_element2 = MagicMock()
    import_element2.element_type = "import"

    class_element = MagicMock()
    class_element.element_type = "class"

    method_element1 = MagicMock()
    method_element1.element_type = "function"
    method_element2 = MagicMock()
    method_element2.element_type = "function"
    method_element3 = MagicMock()
    method_element3.element_type = "function"

    field_element1 = MagicMock()
    field_element1.element_type = "variable"
    field_element2 = MagicMock()
    field_element2.element_type = "variable"

    # Set up elements list with proper element_type attributes
    result.elements = [
        import_element1,
        import_element2,  # 2 imports
        class_element,  # 1 class
        method_element1,
        method_element2,
        method_element3,  # 3 methods
        field_element1,
        field_element2,  # 2 fields
        # 0 annotations
    ]

    return result


class TestAnalyzeScaleToolCLICompatibleInitialization:
    """Test cases for tool initialization"""

    def test_initialization(self, tool: AnalyzeScaleToolCLICompatible) -> None:
        """Test tool initializes correctly"""
        assert tool is not None
        assert hasattr(tool, "analysis_engine")
        assert tool.analysis_engine is not None

    def test_module_level_instance(self) -> None:
        """Test module-level tool instance exists"""
        assert analyze_scale_tool_cli_compatible is not None
        assert isinstance(
            analyze_scale_tool_cli_compatible, AnalyzeScaleToolCLICompatible
        )


class TestAnalyzeScaleToolCLICompatibleSchema:
    """Test cases for tool schema"""

    def test_get_tool_schema_structure(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test tool schema has correct structure"""
        schema = tool.get_tool_schema()

        assert isinstance(schema, dict)
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        assert "additionalProperties" in schema
        assert schema["additionalProperties"] is False

    def test_get_tool_schema_properties(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test tool schema properties are correct"""
        schema = tool.get_tool_schema()
        properties = schema["properties"]

        # Check file_path property
        assert "file_path" in properties
        assert properties["file_path"]["type"] == "string"
        assert "description" in properties["file_path"]

        # Check language property
        assert "language" in properties
        assert properties["language"]["type"] == "string"
        assert "description" in properties["language"]

        # Check include_complexity property
        assert "include_complexity" in properties
        assert properties["include_complexity"]["type"] == "boolean"
        assert properties["include_complexity"]["default"] is True

        # Check include_details property
        assert "include_details" in properties
        assert properties["include_details"]["type"] == "boolean"
        assert properties["include_details"]["default"] is False

    def test_get_tool_schema_required_fields(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test tool schema required fields"""
        schema = tool.get_tool_schema()
        required = schema["required"]

        assert isinstance(required, list)
        assert "file_path" in required
        assert len(required) == 1


class TestAnalyzeScaleToolCLICompatibleValidation:
    """Test cases for argument validation"""

    def test_validate_arguments_valid_minimal(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test validation with minimal valid arguments"""
        arguments = {"file_path": "/path/to/file.java"}
        result = tool.validate_arguments(arguments)
        assert result is True

    def test_validate_arguments_valid_complete(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test validation with complete valid arguments"""
        arguments = {
            "file_path": "/path/to/file.java",
            "language": "java",
            "include_complexity": True,
            "include_details": False,
        }
        result = tool.validate_arguments(arguments)
        assert result is True

    def test_validate_arguments_missing_required(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test validation fails with missing required field"""
        arguments = {"language": "java"}

        with pytest.raises(ValueError, match="Required field 'file_path' is missing"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_file_path_type(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test validation fails with invalid file_path type"""
        arguments = {"file_path": 123}

        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_empty_file_path(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test validation fails with empty file_path"""
        arguments = {"file_path": "   "}

        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_language_type(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test validation fails with invalid language type"""
        arguments = {"file_path": "/path/to/file.java", "language": 123}

        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_include_complexity_type(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test validation fails with invalid include_complexity type"""
        arguments = {"file_path": "/path/to/file.java", "include_complexity": "true"}

        with pytest.raises(ValueError, match="include_complexity must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_include_details_type(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test validation fails with invalid include_details type"""
        arguments = {"file_path": "/path/to/file.java", "include_details": "false"}

        with pytest.raises(ValueError, match="include_details must be a boolean"):
            tool.validate_arguments(arguments)


class TestAnalyzeScaleToolCLICompatibleExecution:
    """Test cases for tool execution"""

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        tool: AnalyzeScaleToolCLICompatible,
        sample_java_file: str,
        sample_analysis_result: MagicMock,
    ) -> None:
        """Test successful execution with valid file"""
        with patch.object(
            tool.analysis_engine, "analyze_file", return_value=sample_analysis_result
        ):
            arguments = {"file_path": sample_java_file}
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["file_path"] == sample_java_file
            assert result["package_name"] == "com.example.test"
            assert result["element_counts"]["imports"] == 2
            assert result["element_counts"]["classes"] == 1
            assert result["element_counts"]["methods"] == 3
            assert result["element_counts"]["fields"] == 2
            assert result["element_counts"]["annotations"] == 0
            assert "analysis_time_ms" in result
            assert isinstance(result["analysis_time_ms"], int | float)
            assert result["error_message"] is None

    @pytest.mark.asyncio
    async def test_execute_missing_file_path(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test execution fails with missing file_path"""
        arguments = {"language": "java"}

        with pytest.raises(ValueError, match="file_path is required"):
            await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_nonexistent_file(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test execution fails with nonexistent file"""
        arguments = {"file_path": "/nonexistent/file.java"}

        with pytest.raises(
            FileNotFoundError, match="File not found: /nonexistent/file.java"
        ):
            await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_with_language_detection(
        self,
        tool: AnalyzeScaleToolCLICompatible,
        sample_java_file: str,
        sample_analysis_result: MagicMock,
    ) -> None:
        """Test execution with automatic language detection"""
        with (
            patch.object(
                tool.analysis_engine,
                "analyze_file",
                return_value=sample_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible.detect_language_from_file",
                return_value="java",
            ),
        ):
            arguments = {"file_path": sample_java_file}
            result = await tool.execute(arguments)

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_unknown_language(
        self, tool: AnalyzeScaleToolCLICompatible, sample_java_file: str
    ) -> None:
        """Test execution fails with unknown language"""
        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_scale_tool_cli_compatible.detect_language_from_file",
            return_value="unknown",
        ):
            arguments = {"file_path": sample_java_file}

            # Escape backslashes for Windows paths in regex
            escaped_path = sample_java_file.replace("\\", "\\\\")
            with pytest.raises(
                ValueError, match=f"Could not detect language for file: {escaped_path}"
            ):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_with_explicit_language(
        self,
        tool: AnalyzeScaleToolCLICompatible,
        sample_java_file: str,
        sample_analysis_result: MagicMock,
    ) -> None:
        """Test execution with explicitly specified language"""
        with patch.object(
            tool.analysis_engine, "analyze_file", return_value=sample_analysis_result
        ):
            arguments = {"file_path": sample_java_file, "language": "java"}
            result = await tool.execute(arguments)

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_with_optional_parameters(
        self,
        tool: AnalyzeScaleToolCLICompatible,
        sample_java_file: str,
        sample_analysis_result: MagicMock,
    ) -> None:
        """Test execution with optional parameters"""
        with patch.object(
            tool.analysis_engine, "analyze_file", return_value=sample_analysis_result
        ):
            arguments = {
                "file_path": sample_java_file,
                "language": "java",
                "include_complexity": True,
                "include_details": True,
            }
            result = await tool.execute(arguments)

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_analysis_failure(
        self, tool: AnalyzeScaleToolCLICompatible, sample_java_file: str
    ) -> None:
        """Test execution when analysis returns None"""
        with patch.object(tool.analysis_engine, "analyze_file", return_value=None):
            arguments = {"file_path": sample_java_file}
            result = await tool.execute(arguments)

            assert result["success"] is False
            assert result["file_path"] == sample_java_file
            assert result["package_name"] is None
            assert result["element_counts"]["imports"] == 0
            assert result["element_counts"]["classes"] == 0
            assert result["element_counts"]["methods"] == 0
            assert result["element_counts"]["fields"] == 0
            assert result["element_counts"]["annotations"] == 0
            assert "analysis_time_ms" in result
            assert (
                result["error_message"] == f"Failed to analyze file: {sample_java_file}"
            )

    @pytest.mark.asyncio
    async def test_execute_analysis_exception(
        self, tool: AnalyzeScaleToolCLICompatible, sample_java_file: str
    ) -> None:
        """Test execution when analysis raises exception"""
        with patch.object(
            tool.analysis_engine,
            "analyze_file",
            side_effect=Exception("Analysis error"),
        ):
            arguments = {"file_path": sample_java_file}
            result = await tool.execute(arguments)

            assert result["success"] is False
            assert result["file_path"] == sample_java_file
            assert result["package_name"] is None
            assert result["element_counts"]["imports"] == 0
            assert result["element_counts"]["classes"] == 0
            assert result["element_counts"]["methods"] == 0
            assert result["element_counts"]["fields"] == 0
            assert result["element_counts"]["annotations"] == 0
            assert result["analysis_time_ms"] == 0.0
            assert result["error_message"] == "Analysis error"

    @pytest.mark.asyncio
    async def test_execute_no_package(
        self, tool: AnalyzeScaleToolCLICompatible, sample_java_file: str
    ) -> None:
        """Test execution with analysis result having no package"""
        result_no_package = MagicMock()
        result_no_package.package = None
        result_no_package.imports = []
        result_no_package.classes = []
        result_no_package.methods = []
        result_no_package.fields = []

        with patch.object(
            tool.analysis_engine, "analyze_file", return_value=result_no_package
        ):
            arguments = {"file_path": sample_java_file}
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["package_name"] is None

    @pytest.mark.asyncio
    async def test_execute_no_annotations_attribute(
        self, tool: AnalyzeScaleToolCLICompatible, sample_java_file: str
    ) -> None:
        """Test execution with analysis result having no annotations attribute"""
        result_no_annotations = MagicMock()
        result_no_annotations.package = None
        result_no_annotations.imports = []
        result_no_annotations.classes = []
        result_no_annotations.methods = []
        result_no_annotations.fields = []
        # Remove annotations attribute
        if hasattr(result_no_annotations, "annotations"):
            delattr(result_no_annotations, "annotations")

        with patch.object(
            tool.analysis_engine, "analyze_file", return_value=result_no_annotations
        ):
            arguments = {"file_path": sample_java_file}
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["element_counts"]["annotations"] == 0


class TestAnalyzeScaleToolCLICompatibleToolDefinition:
    """Test cases for tool definition"""

    def test_get_tool_definition_with_mcp(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test tool definition when MCP is available"""
        mock_tool = MagicMock()

        with patch("mcp.types.Tool", return_value=mock_tool):
            result = tool.get_tool_definition()
            assert result == mock_tool

    def test_get_tool_definition_without_mcp(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test tool definition fallback when MCP is not available"""
        with patch("mcp.types.Tool", side_effect=ImportError):
            result = tool.get_tool_definition()

            assert isinstance(result, dict)
            assert result["name"] == "analyze_code_scale"
            assert "description" in result
            assert "inputSchema" in result
            assert result["inputSchema"] == tool.get_tool_schema()


class TestAnalyzeScaleToolCLICompatibleIntegration:
    """Integration tests for the tool"""

    @pytest.mark.asyncio
    async def test_full_workflow_success(
        self,
        tool: AnalyzeScaleToolCLICompatible,
        sample_java_file: str,
        sample_analysis_result: MagicMock,
    ) -> None:
        """Test complete workflow from validation to execution"""
        arguments = {
            "file_path": sample_java_file,
            "language": "java",
            "include_complexity": True,
            "include_details": False,
        }

        # Validate arguments
        assert tool.validate_arguments(arguments) is True

        # Execute analysis
        with patch.object(
            tool.analysis_engine, "analyze_file", return_value=sample_analysis_result
        ):
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert "analysis_time_ms" in result
            assert result["error_message"] is None

    def test_cli_output_format_compatibility(
        self, tool: AnalyzeScaleToolCLICompatible, sample_analysis_result: MagicMock
    ) -> None:
        """Test that output format matches CLI --advanced --statistics exactly"""
        # This test verifies the exact structure expected by CLI compatibility
        expected_keys = {
            "file_path",
            "success",
            "package_name",
            "element_counts",
            "analysis_time_ms",
            "error_message",
        }

        expected_element_count_keys = {
            "imports",
            "classes",
            "methods",
            "fields",
            "annotations",
        }

        # Test success case structure with mocked file existence
        with (
            patch.object(
                tool.analysis_engine,
                "analyze_file",
                return_value=sample_analysis_result,
            ),
            patch("pathlib.Path.exists", return_value=True),
        ):
            import asyncio

            result = asyncio.run(tool.execute({"file_path": "/test/file.java"}))

            assert set(result.keys()) == expected_keys
            assert set(result["element_counts"].keys()) == expected_element_count_keys
            assert isinstance(result["success"], bool)
            assert isinstance(result["analysis_time_ms"], int | float)

    @pytest.mark.asyncio
    async def test_error_case_format_compatibility(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test that error output format matches CLI expectations"""
        with (
            patch.object(tool.analysis_engine, "analyze_file", return_value=None),
            patch("pathlib.Path.exists", return_value=True),
        ):
            result = await tool.execute({"file_path": "/test/file.java"})

            # Verify error case has same structure as success case
            expected_keys = {
                "file_path",
                "success",
                "package_name",
                "element_counts",
                "analysis_time_ms",
                "error_message",
            }
            assert set(result.keys()) == expected_keys
            assert result["success"] is False
            assert result["error_message"] is not None


class TestAnalyzeScaleToolCLICompatiblePerformance:
    """Performance and resource management tests"""

    @pytest.mark.asyncio
    async def test_timing_accuracy(
        self,
        tool: AnalyzeScaleToolCLICompatible,
        sample_java_file: str,
        sample_analysis_result: MagicMock,
    ) -> None:
        """Test that timing measurements are accurate"""

        def slow_analysis(file_path):
            import time

            time.sleep(0.1)  # Simulate 100ms analysis
            return sample_analysis_result

        with patch.object(
            tool.analysis_engine, "analyze_file", side_effect=slow_analysis
        ):
            arguments = {"file_path": sample_java_file}
            result = await tool.execute(arguments)

            # Should be at least 100ms
            assert result["analysis_time_ms"] >= 100
            # Should be reasonable (less than 1 second for this test)
            assert result["analysis_time_ms"] < 1000

    @pytest.mark.asyncio
    async def test_memory_efficiency(
        self, tool: AnalyzeScaleToolCLICompatible, sample_java_file: str
    ) -> None:
        """Test that tool doesn't leak memory or resources"""
        # Create large mock result
        large_result = MagicMock()
        large_result.package = MagicMock()
        large_result.package.name = "com.example.large"

        # Create mock elements with proper element_type attributes
        import_elements = []
        for _ in range(1000):
            elem = MagicMock()
            elem.element_type = "import"
            import_elements.append(elem)

        class_elements = []
        for _ in range(100):
            elem = MagicMock()
            elem.element_type = "class"
            class_elements.append(elem)

        method_elements = []
        for _ in range(500):
            elem = MagicMock()
            elem.element_type = "function"
            method_elements.append(elem)

        field_elements = []
        for _ in range(200):
            elem = MagicMock()
            elem.element_type = "variable"
            field_elements.append(elem)

        annotation_elements = []
        for _ in range(50):
            elem = MagicMock()
            elem.element_type = "annotation"
            annotation_elements.append(elem)

        # Set up elements list
        large_result.elements = (
            import_elements
            + class_elements
            + method_elements
            + field_elements
            + annotation_elements
        )

        with patch.object(
            tool.analysis_engine, "analyze_file", return_value=large_result
        ):
            arguments = {"file_path": sample_java_file}
            result = await tool.execute(arguments)

            # Should handle large results correctly
            assert result["success"] is True
            assert result["element_counts"]["imports"] == 1000
            assert result["element_counts"]["classes"] == 100
            assert result["element_counts"]["methods"] == 500
            assert result["element_counts"]["fields"] == 200
            assert result["element_counts"]["annotations"] == 50


class TestAnalyzeScaleToolCLICompatibleErrorHandling:
    """Test cases for comprehensive error handling"""

    @pytest.mark.asyncio
    async def test_file_permission_error(
        self, tool: AnalyzeScaleToolCLICompatible
    ) -> None:
        """Test handling of file permission errors"""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze_file",
                side_effect=PermissionError("Permission denied"),
            ),
        ):
            arguments = {"file_path": "/restricted/file.java"}
            result = await tool.execute(arguments)

            assert result["success"] is False
            assert "Permission denied" in result["error_message"]

    @pytest.mark.asyncio
    async def test_unicode_file_path(
        self, tool: AnalyzeScaleToolCLICompatible, sample_analysis_result: MagicMock
    ) -> None:
        """Test handling of Unicode file paths"""
        unicode_path = "/path/to/ファイル.java"

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool.analysis_engine,
                "analyze_file",
                return_value=sample_analysis_result,
            ),
        ):
            arguments = {"file_path": unicode_path}
            result = await tool.execute(arguments)

            assert result["success"] is True
            assert result["file_path"] == unicode_path

    def test_schema_edge_cases(self, tool: AnalyzeScaleToolCLICompatible) -> None:
        """Test schema validation with edge cases"""
        schema = tool.get_tool_schema()

        # Verify schema is JSON serializable
        json_str = json.dumps(schema)
        parsed_schema = json.loads(json_str)
        assert parsed_schema == schema


# Additional test markers for categorization
pytestmark = [pytest.mark.unit]
