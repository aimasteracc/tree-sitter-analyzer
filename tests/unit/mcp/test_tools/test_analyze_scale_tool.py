"""
Unit tests for AnalyzeScaleTool.

Tests for analyze_code_scale tool which provides code scale analysis
including metrics about complexity, size, and structure.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool


@pytest.fixture
def tool():
    """Create an AnalyzeScaleTool instance for testing."""
    return AnalyzeScaleTool()


@pytest.fixture
def tool_with_project_root():
    """Create an AnalyzeScaleTool instance with a project root."""
    return AnalyzeScaleTool(project_root="/test/project")


class TestAnalyzeScaleToolInit:
    """Tests for AnalyzeScaleTool initialization."""

    def test_init_without_project_root(self, tool):
        """Test initialization without project root."""
        assert tool is not None
        assert tool.project_root is None
        assert tool.analysis_engine is not None

    def test_init_with_project_root(self, tool_with_project_root):
        """Test initialization with project root."""
        assert tool_with_project_root is not None
        assert tool_with_project_root.project_root == "/test/project"
        assert tool_with_project_root.analysis_engine is not None


class TestAnalyzeScaleToolSetProjectPath:
    """Tests for set_project_path method."""

    def test_set_project_path(self, tool):
        """Test setting project path."""
        tool.set_project_path("/new/project")
        assert tool.project_root == "/new/project"


class TestAnalyzeScaleToolGetToolSchema:
    """Tests for get_tool_schema method."""

    def test_get_tool_schema_structure(self, tool):
        """Test tool schema has correct structure."""
        schema = tool.get_tool_schema()
        assert isinstance(schema, dict)
        assert "type" in schema
        assert "properties" in schema
        assert schema["type"] == "object"

    def test_get_tool_schema_has_file_path_property(self, tool):
        """Test schema has file_path property."""
        schema = tool.get_tool_schema()
        assert "file_path" in schema["properties"]
        assert schema["properties"]["file_path"]["type"] == "string"

    def test_get_tool_schema_has_file_paths_property(self, tool):
        """Test schema has file_paths property for batch mode."""
        schema = tool.get_tool_schema()
        assert "file_paths" in schema["properties"]
        assert schema["properties"]["file_paths"]["type"] == "array"

    def test_get_tool_schema_has_metrics_only_property(self, tool):
        """Test schema has metrics_only property."""
        schema = tool.get_tool_schema()
        assert "metrics_only" in schema["properties"]
        assert schema["properties"]["metrics_only"]["type"] == "boolean"

    def test_get_tool_schema_has_language_property(self, tool):
        """Test schema has language property."""
        schema = tool.get_tool_schema()
        assert "language" in schema["properties"]
        assert schema["properties"]["language"]["type"] == "string"

    def test_get_tool_schema_has_include_complexity_property(self, tool):
        """Test schema has include_complexity property."""
        schema = tool.get_tool_schema()
        assert "include_complexity" in schema["properties"]
        assert schema["properties"]["include_complexity"]["type"] == "boolean"

    def test_get_tool_schema_has_include_details_property(self, tool):
        """Test schema has include_details property."""
        schema = tool.get_tool_schema()
        assert "include_details" in schema["properties"]
        assert schema["properties"]["include_details"]["type"] == "boolean"

    def test_get_tool_schema_has_include_guidance_property(self, tool):
        """Test schema has include_guidance property."""
        schema = tool.get_tool_schema()
        assert "include_guidance" in schema["properties"]
        assert schema["properties"]["include_guidance"]["type"] == "boolean"

    def test_get_tool_schema_has_output_format_property(self, tool):
        """Test schema has output_format property."""
        schema = tool.get_tool_schema()
        assert "output_format" in schema["properties"]
        assert schema["properties"]["output_format"]["type"] == "string"
        assert "enum" in schema["properties"]["output_format"]
        assert "json" in schema["properties"]["output_format"]["enum"]
        assert "toon" in schema["properties"]["output_format"]["enum"]


class TestAnalyzeScaleToolGetToolDefinition:
    """Tests for get_tool_definition method."""

    def test_get_tool_definition_name(self, tool):
        """Test tool definition has correct name."""
        definition = tool.get_tool_definition()
        assert definition["name"] == "check_code_scale"

    def test_get_tool_definition_has_description(self, tool):
        """Test tool definition has description."""
        definition = tool.get_tool_definition()
        assert "description" in definition
        assert isinstance(definition["description"], str)
        assert len(definition["description"]) > 0

    def test_get_tool_definition_has_input_schema(self, tool):
        """Test tool definition has input schema."""
        definition = tool.get_tool_definition()
        assert "inputSchema" in definition
        assert isinstance(definition["inputSchema"], dict)


class TestAnalyzeScaleToolValidateArguments:
    """Tests for validate_arguments method."""

    def test_validate_arguments_valid_single_mode(self, tool):
        """Test validation with valid single mode arguments."""
        arguments = {
            "file_path": "test.py",
            "language": "python",
            "include_complexity": True,
            "include_details": False,
            "include_guidance": True,
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_valid_batch_mode(self, tool):
        """Test validation with valid batch mode arguments."""
        arguments = {
            "file_paths": ["test1.py", "test2.py"],
            "metrics_only": True,
        }
        assert tool.validate_arguments(arguments) is True

    def test_validate_arguments_missing_file_path(self, tool):
        """Test validation fails when file_path is missing."""
        arguments = {"language": "python"}
        with pytest.raises(ValueError, match="Required field 'file_path' is missing"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_empty_file_path(self, tool):
        """Test validation fails when file_path is empty."""
        arguments = {"file_path": ""}
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_file_path_type(self, tool):
        """Test validation fails when file_path is not a string."""
        arguments = {"file_path": 123}
        with pytest.raises(ValueError, match="file_path must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_language_type(self, tool):
        """Test validation fails when language is not a string."""
        arguments = {"file_path": "test.py", "language": 123}
        with pytest.raises(ValueError, match="language must be a string"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_include_complexity_type(self, tool):
        """Test validation fails when include_complexity is not a boolean."""
        arguments = {"file_path": "test.py", "include_complexity": "true"}
        with pytest.raises(ValueError, match="include_complexity must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_include_details_type(self, tool):
        """Test validation fails when include_details is not a boolean."""
        arguments = {"file_path": "test.py", "include_details": "true"}
        with pytest.raises(ValueError, match="include_details must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_include_guidance_type(self, tool):
        """Test validation fails when include_guidance is not a boolean."""
        arguments = {"file_path": "test.py", "include_guidance": "true"}
        with pytest.raises(ValueError, match="include_guidance must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_mutually_exclusive(self, tool):
        """Test validation fails when both file_path and file_paths are provided."""
        arguments = {"file_path": "test.py", "file_paths": ["test2.py"]}
        with pytest.raises(
            ValueError, match="file_paths is mutually exclusive with file_path"
        ):
            tool.validate_arguments(arguments)

    def test_validate_arguments_empty_file_paths(self, tool):
        """Test validation fails when file_paths is empty."""
        arguments = {"file_paths": [], "metrics_only": True}
        with pytest.raises(ValueError, match="file_paths must be a non-empty list"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_file_paths_type(self, tool):
        """Test validation fails when file_paths is not a list."""
        arguments = {"file_paths": "test.py", "metrics_only": True}
        with pytest.raises(ValueError, match="file_paths must be a non-empty list"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_invalid_metrics_only_type(self, tool):
        """Test validation fails when metrics_only is not a boolean."""
        arguments = {"file_paths": ["test.py"], "metrics_only": "true"}
        with pytest.raises(ValueError, match="metrics_only must be a boolean"):
            tool.validate_arguments(arguments)

    def test_validate_arguments_metrics_only_required_for_batch(self, tool):
        """Test validation fails when metrics_only is False in batch mode."""
        arguments = {"file_paths": ["test.py"], "metrics_only": False}
        with pytest.raises(
            ValueError,
            match="metrics_only must be true when using file_paths batch mode",
        ):
            tool.validate_arguments(arguments)


class TestAnalyzeScaleToolCalculateFileMetrics:
    """Tests for _calculate_file_metrics method."""

    def test_calculate_file_metrics_success(self, tool):
        """Test successful file metrics calculation."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.compute_file_metrics"
        ) as mock_compute:
            mock_compute.return_value = {
                "total_lines": 100,
                "code_lines": 80,
                "comment_lines": 15,
                "blank_lines": 5,
                "estimated_tokens": 400,
                "file_size_bytes": 2048,
            }
            metrics = tool._calculate_file_metrics("test.py", "python")
            assert metrics["total_lines"] == 100
            assert metrics["file_size_kb"] == 2.0

    def test_calculate_file_metrics_error_handling(self, tool):
        """Test error handling in file metrics calculation."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.compute_file_metrics"
        ) as mock_compute:
            mock_compute.side_effect = Exception("Test error")
            metrics = tool._calculate_file_metrics("test.py", "python")
            assert metrics["total_lines"] == 0
            assert metrics["code_lines"] == 0
            assert metrics["estimated_tokens"] == 0
            assert metrics["file_size_kb"] == 0


class TestAnalyzeScaleToolExtractStructuralOverview:
    """Tests for _extract_structural_overview method."""

    def test_extract_structural_overview_empty(self, tool):
        """Test extraction with empty analysis result."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.package = None

        overview = tool._extract_structural_overview(mock_analysis_result)
        assert overview["classes"] == []
        assert overview["methods"] == []
        assert overview["fields"] == []
        assert overview["imports"] == []
        assert overview["complexity_hotspots"] == []

    def test_extract_structural_overview_with_classes(self, tool):
        """Test extraction with class elements."""
        mock_class_element = MagicMock()
        mock_class_element.name = "TestClass"
        mock_class_element.class_type = "class"
        mock_class_element.start_line = 10
        mock_class_element.end_line = 50
        mock_class_element.visibility = "public"
        mock_class_element.extends_class = "BaseClass"
        mock_class_element.implements_interfaces = ["Interface1"]
        mock_annotation = MagicMock()
        mock_annotation.name = "Dataclass"
        mock_annotation.start_line = 9
        mock_class_element.annotations = [mock_annotation]
        mock_class_element.element_type = (
            "class"  # Set element_type for is_element_of_type
        )

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [mock_class_element]
        mock_analysis_result.package = None

        overview = tool._extract_structural_overview(mock_analysis_result)
        assert len(overview["classes"]) == 1
        assert overview["classes"][0]["name"] == "TestClass"
        assert overview["classes"][0]["start_line"] == 10
        assert overview["classes"][0]["end_line"] == 50
        assert overview["classes"][0]["line_span"] == 41

    def test_extract_structural_overview_with_methods(self, tool):
        """Test extraction with method elements."""
        mock_method_element = MagicMock()
        mock_method_element.name = "test_method"
        mock_method_element.start_line = 20
        mock_method_element.end_line = 30
        mock_method_element.visibility = "public"
        mock_method_element.return_type = "void"
        mock_method_element.parameters = []
        mock_method_element.complexity_score = 5
        mock_method_element.is_constructor = False
        mock_method_element.is_static = False
        mock_method_element.annotations = []
        mock_method_element.element_type = (
            "function"  # Set element_type for is_element_of_type
        )

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [mock_method_element]
        mock_analysis_result.package = None

        overview = tool._extract_structural_overview(mock_analysis_result)
        assert len(overview["methods"]) == 1
        assert overview["methods"][0]["name"] == "test_method"
        assert overview["methods"][0]["complexity"] == 5
        assert overview["methods"][0]["parameter_count"] == 0

    def test_extract_structural_overview_with_high_complexity_method(self, tool):
        """Test extraction tracks complexity hotspots."""
        mock_method_element = MagicMock()
        mock_method_element.name = "complex_method"
        mock_method_element.start_line = 20
        mock_method_element.end_line = 50
        mock_method_element.visibility = "public"
        mock_method_element.return_type = "void"
        mock_method_element.parameters = []
        mock_method_element.complexity_score = 15
        mock_method_element.is_constructor = False
        mock_method_element.is_static = False
        mock_method_element.annotations = []
        mock_method_element.element_type = (
            "function"  # Set element_type for is_element_of_type
        )

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [mock_method_element]
        mock_analysis_result.package = None

        overview = tool._extract_structural_overview(mock_analysis_result)
        assert len(overview["complexity_hotspots"]) == 1
        assert overview["complexity_hotspots"][0]["name"] == "complex_method"
        assert overview["complexity_hotspots"][0]["complexity"] == 15

    def test_extract_structural_overview_with_fields(self, tool):
        """Test extraction with field elements."""
        mock_field_element = MagicMock()
        mock_field_element.name = "test_field"
        mock_field_element.field_type = "int"
        mock_field_element.start_line = 15
        mock_field_element.end_line = 15
        mock_field_element.visibility = "private"
        mock_field_element.is_static = False
        mock_field_element.is_final = True
        mock_field_element.annotations = []
        mock_field_element.element_type = (
            "variable"  # Set element_type for is_element_of_type
        )

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [mock_field_element]
        mock_analysis_result.package = None

        overview = tool._extract_structural_overview(mock_analysis_result)
        assert len(overview["fields"]) == 1
        assert overview["fields"][0]["name"] == "test_field"
        assert overview["fields"][0]["type"] == "int"

    def test_extract_structural_overview_with_imports(self, tool):
        """Test extraction with import elements."""
        mock_import_element = MagicMock()
        mock_import_element.imported_name = "os"
        mock_import_element.import_statement = "import os"
        mock_import_element.line_number = 1
        mock_import_element.is_static = False
        mock_import_element.is_wildcard = False
        mock_import_element.element_type = (
            "import"  # Set element_type for is_element_of_type
        )

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [mock_import_element]
        mock_analysis_result.package = None

        overview = tool._extract_structural_overview(mock_analysis_result)
        assert len(overview["imports"]) == 1
        assert overview["imports"][0]["name"] == "os"
        assert overview["imports"][0]["statement"] == "import os"


class TestAnalyzeScaleToolGenerateLLMGuidance:
    """Tests for _generate_llm_guidance method."""

    def test_generate_llm_guidance_small_file(self, tool):
        """Test LLM guidance for small file."""
        file_metrics = {"total_lines": 50}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert guidance["size_category"] == "small"
        assert "small file" in guidance["analysis_strategy"].lower()

    def test_generate_llm_guidance_medium_file(self, tool):
        """Test LLM guidance for medium file."""
        file_metrics = {"total_lines": 300}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert guidance["size_category"] == "medium"
        assert "medium-sized" in guidance["analysis_strategy"].lower()

    def test_generate_llm_guidance_large_file(self, tool):
        """Test LLM guidance for large file."""
        file_metrics = {"total_lines": 1000}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert guidance["size_category"] == "large"
        assert "large file" in guidance["analysis_strategy"].lower()

    def test_generate_llm_guidance_very_large_file(self, tool):
        """Test LLM guidance for very large file."""
        file_metrics = {"total_lines": 2000}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert guidance["size_category"] == "very_large"
        assert "very large file" in guidance["analysis_strategy"].lower()

    def test_generate_llm_guidance_with_complexity_hotspots(self, tool):
        """Test LLM guidance includes complexity hotspots."""
        file_metrics = {"total_lines": 500}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [
                {"type": "method", "name": "complex_func", "complexity": 15}
            ],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "complexity hotspots" in guidance["complexity_assessment"].lower()
        assert "analyze_code_structure" in guidance["recommended_tools"]

    def test_generate_llm_guidance_without_complexity_hotspots(self, tool):
        """Test LLM guidance without complexity hotspots."""
        file_metrics = {"total_lines": 500}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "no significant complexity" in guidance["complexity_assessment"].lower()

    def test_generate_llm_guidance_multiple_classes(self, tool):
        """Test LLM guidance identifies multiple classes."""
        file_metrics = {"total_lines": 500}
        structural_overview = {
            "classes": ["class1", "class2", "class3"],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert any("multiple classes" in area.lower() for area in guidance["key_areas"])

    def test_generate_llm_guidance_many_methods(self, tool):
        """Test LLM guidance identifies many methods."""
        file_metrics = {"total_lines": 500}
        structural_overview = {
            "classes": [],
            "methods": list(range(25)),
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert any("many methods" in area.lower() for area in guidance["key_areas"])

    def test_generate_llm_guidance_many_imports(self, tool):
        """Test LLM guidance identifies many imports."""
        file_metrics = {"total_lines": 500}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": list(range(15)),
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert any("many imports" in area.lower() for area in guidance["key_areas"])


class TestAnalyzeScaleToolExecute:
    """Tests for execute method (single mode)."""

    @pytest.mark.asyncio
    async def test_execute_missing_file_path(self, tool):
        """Test execute fails when file_path is missing."""
        arguments = {"language": "python"}
        with pytest.raises(ValueError, match="file_path is required"):
            await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, tool):
        """Test execute fails when file doesn't exist."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/nonexistent.py"
            ),
            patch("pathlib.Path.exists", return_value=False),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(ValueError, match="Invalid file path: File not found"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_unsupported_language(self, tool):
        """Test execute fails when language is not supported."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.unknown"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="unknown",
            ),
        ):
            arguments = {"file_path": "test.unknown"}
            with pytest.raises(ValueError, match="Unsupported language"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_json_file(self, tool):
        """Test execute handles JSON files specially."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.json"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 10,
                    "code_lines": 10,
                    "comment_lines": 0,
                    "blank_lines": 0,
                    "estimated_tokens": 40,
                    "file_size_bytes": 100,
                },
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.json", "include_guidance": True}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_success_python(self, tool):
        """Test execute succeeds for Python file."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_package = MagicMock()
        mock_package.name = "test_package"
        mock_analysis_result.package = mock_package
        mock_analysis_result.success = True
        mock_analysis_result.get_statistics = MagicMock(return_value={})

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "include_guidance": True}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_with_include_details(self, tool):
        """Test execute with include_details=True."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_package = MagicMock()
        mock_package.name = "test_package"
        mock_analysis_result.package = mock_package
        mock_analysis_result.success = True
        mock_analysis_result.get_statistics = MagicMock(return_value={})

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "include_details": True}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_without_include_guidance(self, tool):
        """Test execute with include_guidance=False."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_package = MagicMock()
        mock_package.name = "test_package"
        mock_analysis_result.package = mock_package
        mock_analysis_result.success = True
        mock_analysis_result.get_statistics = MagicMock(return_value={})

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "include_guidance": False}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_with_json_output_format(self, tool):
        """Test execute with output_format='json'."""
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_package = MagicMock()
        mock_package.name = "test_package"
        mock_analysis_result.package = mock_package
        mock_analysis_result.success = True
        mock_analysis_result.get_statistics = MagicMock(return_value={})

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_path": "test.py", "output_format": "json"}
            result = await tool.execute(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_analysis_failure(self, tool):
        """Test execute handles analysis engine failure."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(RuntimeError, match="Failed to analyze file"):
                await tool.execute(arguments)


class TestAnalyzeScaleToolExecuteMetricsBatch:
    """Tests for _execute_metrics_batch method."""

    @pytest.mark.asyncio
    async def test_execute_batch_missing_metrics_only(self, tool):
        """Test batch mode fails when metrics_only is False."""
        arguments = {"file_paths": ["test1.py", "test2.py"], "metrics_only": False}
        with pytest.raises(ValueError, match="metrics_only must be true"):
            await tool._execute_metrics_batch(arguments)

    @pytest.mark.asyncio
    async def test_execute_batch_empty_file_paths(self, tool):
        """Test batch mode fails when file_paths is empty."""
        arguments = {"file_paths": [], "metrics_only": True}
        with pytest.raises(ValueError, match="file_paths must be a non-empty list"):
            await tool._execute_metrics_batch(arguments)

    @pytest.mark.asyncio
    async def test_execute_batch_invalid_file_paths_type(self, tool):
        """Test batch mode fails when file_paths is not a list."""
        arguments = {"file_paths": "test.py", "metrics_only": True}
        with pytest.raises(ValueError, match="file_paths must be a non-empty list"):
            await tool._execute_metrics_batch(arguments)

    @pytest.mark.asyncio
    async def test_execute_batch_too_many_files(self, tool):
        """Test batch mode fails when too many files."""
        arguments = {
            "file_paths": [f"test{i}.py" for i in range(201)],
            "metrics_only": True,
        }
        with pytest.raises(ValueError, match="Too many files"):
            await tool._execute_metrics_batch(arguments)

    @pytest.mark.asyncio
    async def test_execute_batch_success(self, tool):
        """Test batch mode succeeds."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_paths": ["test1.py", "test2.py"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_batch_with_errors(self, tool):
        """Test batch mode handles errors gracefully."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_paths": ["test.py", ""], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert "formatted" in result

    @pytest.mark.asyncio
    async def test_execute_batch_file_not_found(self, tool):
        """Test batch mode handles file not found."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=False),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                return_value={"formatted": True},
            ),
        ):
            arguments = {"file_paths": ["test.py"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert "formatted" in result


class TestAnalyzeScaleToolCreateJsonFileAnalysis:
    """Tests for _create_json_file_analysis method."""

    def test_create_json_file_analysis_small(self, tool):
        """Test JSON file analysis for small file."""
        file_metrics = {
            "total_lines": 50,
            "code_lines": 50,
            "comment_lines": 0,
            "blank_lines": 0,
            "estimated_tokens": 200,
            "file_size_bytes": 1000,
        }
        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
            return_value={"formatted": True},
        ):
            result = tool._create_json_file_analysis(
                "/test.json", file_metrics, True, "toon"
            )
            assert "formatted" in result

    def test_create_json_file_analysis_medium(self, tool):
        """Test JSON file analysis for medium file."""
        file_metrics = {
            "total_lines": 500,
            "code_lines": 500,
            "comment_lines": 0,
            "blank_lines": 0,
            "estimated_tokens": 2000,
            "file_size_bytes": 10000,
        }
        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
            return_value={"formatted": True},
        ):
            result = tool._create_json_file_analysis(
                "/test.json", file_metrics, True, "toon"
            )
            assert "formatted" in result

    def test_create_json_file_analysis_large(self, tool):
        """Test JSON file analysis for large file."""
        file_metrics = {
            "total_lines": 1500,
            "code_lines": 1500,
            "comment_lines": 0,
            "blank_lines": 0,
            "estimated_tokens": 6000,
            "file_size_bytes": 30000,
        }
        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
            return_value={"formatted": True},
        ):
            result = tool._create_json_file_analysis(
                "/test.json", file_metrics, True, "toon"
            )
            assert "formatted" in result

    def test_create_json_file_analysis_without_guidance(self, tool):
        """Test JSON file analysis without guidance."""
        file_metrics = {
            "total_lines": 100,
            "code_lines": 100,
            "comment_lines": 0,
            "blank_lines": 0,
            "estimated_tokens": 400,
            "file_size_bytes": 2000,
        }
        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
            return_value={"formatted": True},
        ):
            result = tool._create_json_file_analysis(
                "/test.json", file_metrics, False, "toon"
            )
            assert "formatted" in result

    def test_create_json_file_analysis_json_format(self, tool):
        """Test JSON file analysis with JSON output format."""
        file_metrics = {
            "total_lines": 100,
            "code_lines": 100,
            "comment_lines": 0,
            "blank_lines": 0,
            "estimated_tokens": 400,
            "file_size_bytes": 2000,
        }
        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
            return_value={"formatted": True},
        ):
            result = tool._create_json_file_analysis(
                "/test.json", file_metrics, True, "json"
            )
            assert "formatted" in result


class TestAnalyzeScaleToolExtractStructuralOverviewUniversal:
    """Tests for _extract_structural_overview_universal method."""

    def test_extract_universal_none_result(self, tool):
        """Test with None analysis result."""
        overview = tool._extract_structural_overview_universal(None)
        assert overview["classes"] == []
        assert overview["methods"] == []

    def test_extract_universal_no_elements_attr(self, tool):
        """Test with result that has no elements attribute."""
        overview = tool._extract_structural_overview_universal("not_an_object")
        assert overview["classes"] == []

    def test_extract_universal_with_class(self, tool):
        """Test extraction of class element."""
        mock_elem = MagicMock()
        mock_elem.element_type = "class"
        mock_elem.name = "MyClass"
        mock_elem.start_line = 1
        mock_elem.end_line = 50
        mock_result = MagicMock()
        mock_result.elements = [mock_elem]
        overview = tool._extract_structural_overview_universal(mock_result)
        assert len(overview["classes"]) == 1
        assert overview["classes"][0]["name"] == "MyClass"
        assert overview["classes"][0]["line_span"] == 50

    def test_extract_universal_with_function(self, tool):
        """Test extraction of function element."""
        mock_elem = MagicMock()
        mock_elem.element_type = "function"
        mock_elem.name = "my_func"
        mock_elem.start_line = 10
        mock_elem.end_line = 20
        mock_elem.complexity_score = 5
        mock_result = MagicMock()
        mock_result.elements = [mock_elem]
        overview = tool._extract_structural_overview_universal(mock_result)
        assert len(overview["methods"]) == 1
        assert overview["methods"][0]["name"] == "my_func"
        assert overview["complexity_hotspots"] == []

    def test_extract_universal_with_method(self, tool):
        """Test extraction of method element."""
        mock_elem = MagicMock()
        mock_elem.element_type = "method"
        mock_elem.name = "my_method"
        mock_elem.start_line = 10
        mock_elem.end_line = 20
        mock_elem.complexity_score = 5
        mock_result = MagicMock()
        mock_result.elements = [mock_elem]
        overview = tool._extract_structural_overview_universal(mock_result)
        assert len(overview["methods"]) == 1
        assert overview["methods"][0]["name"] == "my_method"

    def test_extract_universal_high_complexity_hotspot(self, tool):
        """Test extraction tracks complexity hotspots for universal."""
        mock_elem = MagicMock()
        mock_elem.element_type = "function"
        mock_elem.name = "complex_func"
        mock_elem.start_line = 5
        mock_elem.end_line = 40
        mock_elem.complexity_score = 15
        mock_result = MagicMock()
        mock_result.elements = [mock_elem]
        overview = tool._extract_structural_overview_universal(mock_result)
        assert len(overview["complexity_hotspots"]) == 1
        assert overview["complexity_hotspots"][0]["name"] == "complex_func"

    def test_extract_universal_with_variable(self, tool):
        """Test extraction of variable element."""
        mock_elem = MagicMock()
        mock_elem.element_type = "variable"
        mock_elem.name = "my_var"
        mock_elem.start_line = 3
        mock_elem.end_line = 3
        mock_result = MagicMock()
        mock_result.elements = [mock_elem]
        overview = tool._extract_structural_overview_universal(mock_result)
        assert len(overview["fields"]) == 1
        assert overview["fields"][0]["name"] == "my_var"

    def test_extract_universal_with_import(self, tool):
        """Test extraction of import element."""
        mock_elem = MagicMock()
        mock_elem.element_type = "import"
        mock_elem.name = "os"
        mock_elem.start_line = 1
        mock_elem.end_line = 1
        mock_result = MagicMock()
        mock_result.elements = [mock_elem]
        overview = tool._extract_structural_overview_universal(mock_result)
        assert len(overview["imports"]) == 1
        assert overview["imports"][0]["name"] == "os"

    def test_extract_universal_unknown_type(self, tool):
        """Test element with unknown type is ignored."""
        mock_elem = MagicMock()
        mock_elem.element_type = "comment"
        mock_elem.name = "a_comment"
        mock_elem.start_line = 1
        mock_elem.end_line = 1
        mock_result = MagicMock()
        mock_result.elements = [mock_elem]
        overview = tool._extract_structural_overview_universal(mock_result)
        assert overview["classes"] == []
        assert overview["methods"] == []
        assert overview["fields"] == []
        assert overview["imports"] == []


class TestAnalyzeScaleToolCountElements:
    """Tests for _count_elements static method."""

    def test_count_elements_java_style(self, tool):
        """Test counting Java-style elements."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_elem = MagicMock()
        mock_elem.element_type = "class"
        mock_elem.name = "TestClass"
        count = tool._count_elements([mock_elem], ELEMENT_TYPE_CLASS, "class")
        assert count == 1

    def test_count_elements_universal_style(self, tool):
        """Test counting universal-style elements."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_elem = MagicMock(spec=[])
        mock_elem.element_type = "class"
        count = tool._count_elements([mock_elem], ELEMENT_TYPE_CLASS, "class")
        assert count >= 1

    def test_count_elements_no_match(self, tool):
        """Test counting with no matching elements."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        mock_elem = MagicMock()
        mock_elem.element_type = "function"
        count = tool._count_elements([mock_elem], ELEMENT_TYPE_CLASS, "class")
        assert count == 0

    def test_count_elements_empty_list(self, tool):
        """Test counting with empty list."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        count = tool._count_elements([], ELEMENT_TYPE_CLASS, "class")
        assert count == 0


class TestAnalyzeScaleToolGenerateLLMGuidanceAdvanced:
    """Tests for _generate_llm_guidance advanced branches."""

    def test_generate_guidance_recommended_tools_for_large_file(self, tool):
        """Test recommended tools include extract_code_section for large files."""
        file_metrics = {"total_lines": 250, "language": "python"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "extract_code_section" in guidance["recommended_tools"]
        assert "query_code" in guidance["recommended_tools"]

    def test_generate_guidance_language_queries_java(self, tool):
        """Test language-specific queries for Java."""
        file_metrics = {"total_lines": 100, "language": "java"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "methods" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_python(self, tool):
        """Test language-specific queries for Python."""
        file_metrics = {"total_lines": 100, "language": "python"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "functions" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_javascript(self, tool):
        """Test language-specific queries for JavaScript."""
        file_metrics = {"total_lines": 100, "language": "javascript"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "react_component" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_typescript(self, tool):
        """Test language-specific queries for TypeScript."""
        file_metrics = {"total_lines": 100, "language": "typescript"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "interfaces" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_go(self, tool):
        """Test language-specific queries for Go."""
        file_metrics = {"total_lines": 100, "language": "go"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "struct" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_rust(self, tool):
        """Test language-specific queries for Rust."""
        file_metrics = {"total_lines": 100, "language": "rust"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "trait" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_c(self, tool):
        """Test language-specific queries for C."""
        file_metrics = {"total_lines": 100, "language": "c"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "function" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_cpp(self, tool):
        """Test language-specific queries for C++."""
        file_metrics = {"total_lines": 100, "language": "cpp"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "namespace" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_kotlin(self, tool):
        """Test language-specific queries for Kotlin."""
        file_metrics = {"total_lines": 100, "language": "kotlin"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "data_class" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_ruby(self, tool):
        """Test language-specific queries for Ruby."""
        file_metrics = {"total_lines": 100, "language": "ruby"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert "methods" in guidance["suggested_queries"]

    def test_generate_guidance_language_queries_unknown(self, tool):
        """Test no queries for unknown language."""
        file_metrics = {"total_lines": 100, "language": "cobol"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert guidance["suggested_queries"] == []

    def test_generate_guidance_workflow_small_file(self, tool):
        """Test workflow steps for small file."""
        file_metrics = {"total_lines": 50, "language": "python"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert (
            "analyze_code_structure for full structure table"
            in guidance["workflow_steps"]
        )

    def test_generate_guidance_workflow_very_large_file(self, tool):
        """Test workflow steps for very large file."""
        file_metrics = {"total_lines": 2000, "language": "python"}
        structural_overview = {
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
            "complexity_hotspots": [],
        }
        guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
        assert (
            "extract_code_section for targeted line ranges"
            in guidance["workflow_steps"]
        )

    def test_generate_guidance_missing_structural_fields(self, tool):
        """Test guidance adds missing structural overview fields."""
        file_metrics = {"total_lines": 100, "language": "python"}
        structural_overview = {}
        tool._generate_llm_guidance(file_metrics, structural_overview)
        assert structural_overview["complexity_hotspots"] == []
        assert structural_overview["classes"] == []


class TestAnalyzeScaleToolExecuteJava:
    """Tests for execute method with Java language path."""

    @pytest.mark.asyncio
    async def test_execute_java_success(self, tool):
        """Test execute succeeds for Java file."""
        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.element_type = "class"
        mock_class.start_line = 1
        mock_class.end_line = 10
        mock_class.visibility = "public"
        mock_class.extends_class = None
        mock_class.implements_interfaces = []
        mock_class.annotations = []

        mock_method = MagicMock()
        mock_method.name = "doStuff"
        mock_method.element_type = "function"
        mock_method.start_line = 3
        mock_method.end_line = 8
        mock_method.visibility = "public"
        mock_method.return_type = "void"
        mock_method.parameters = []
        mock_method.complexity_score = 3
        mock_method.is_constructor = False
        mock_method.is_static = False
        mock_method.annotations = []

        mock_field = MagicMock()
        mock_field.name = "count"
        mock_field.element_type = "variable"
        mock_field.start_line = 2
        mock_field.end_line = 2
        mock_field.visibility = "private"
        mock_field.field_type = "int"
        mock_field.is_static = False
        mock_field.is_final = False
        mock_field.annotations = []

        mock_import = MagicMock()
        mock_import.element_type = "import"
        mock_import.imported_name = "java.util.List"
        mock_import.import_statement = "import java.util.List"
        mock_import.line_number = 1
        mock_import.is_static = False
        mock_import.is_wildcard = False

        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = [
            mock_class,
            mock_method,
            mock_field,
            mock_import,
        ]
        mock_analysis_result.package = None
        mock_analysis_result.annotations = []
        mock_analysis_result.get_statistics = MagicMock(return_value={"total": 4})

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/Test.java"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {
                "file_path": "Test.java",
                "language": "java",
                "include_details": True,
                "include_guidance": True,
            }
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["language"] == "java"
            assert len(result["structural_overview"]["classes"]) == 1
            assert len(result["structural_overview"]["methods"]) == 1
            assert len(result["structural_overview"]["fields"]) == 1
            assert len(result["structural_overview"]["imports"]) == 1
            assert "detailed_analysis" in result
            assert "llm_guidance" in result

    @pytest.mark.asyncio
    async def test_execute_java_analysis_none(self, tool):
        """Test execute handles None result from Java analysis."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/Test.java"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            arguments = {"file_path": "Test.java", "language": "java"}
            with pytest.raises(RuntimeError, match="Failed to analyze file"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_non_java_universal_failure(self, tool):
        """Test execute handles universal engine failure."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Parse error"
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(RuntimeError, match="Failed to analyze file"):
                await tool.execute(arguments)


class TestAnalyzeScaleToolExecuteBatchAdvanced:
    """Advanced tests for _execute_metrics_batch method."""

    @pytest.mark.asyncio
    async def test_execute_batch_with_invalid_path_entries(self, tool):
        """Test batch mode with invalid file path strings."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_paths": [123], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_errors"] >= 1

    @pytest.mark.asyncio
    async def test_execute_batch_with_resolve_error(self, tool):
        """Test batch mode handles resolve error."""
        with (
            patch.object(
                tool,
                "resolve_and_validate_file_path",
                side_effect=ValueError("Path traversal detected"),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_paths": ["../etc/passwd"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_errors"] == 1
            assert result["count_ok"] == 0

    @pytest.mark.asyncio
    async def test_execute_batch_unknown_language(self, tool):
        """Test batch mode handles unknown language detection."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.xyz"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="unknown",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 50,
                    "code_lines": 50,
                    "comment_lines": 0,
                    "blank_lines": 0,
                    "estimated_tokens": 200,
                    "file_size_bytes": 1024,
                },
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_paths": ["test.xyz"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_ok"] == 1

    @pytest.mark.asyncio
    async def test_execute_batch_all_errors(self, tool):
        """Test batch mode where all files fail."""
        with (
            patch.object(
                tool,
                "resolve_and_validate_file_path",
                side_effect=ValueError("Invalid"),
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_paths": ["a.py", "b.py"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["success"] is False
            assert result["count_errors"] == 2


class TestAnalyzeScaleToolCreateJsonFileAnalysisAdvanced:
    """Advanced tests for _create_json_file_analysis method."""

    def test_create_json_file_analysis_without_toon_mock(self, tool):
        """Test JSON file analysis returns actual structure without mock."""
        file_metrics = {
            "total_lines": 50,
            "code_lines": 50,
            "comment_lines": 0,
            "blank_lines": 5,
            "estimated_tokens": 200,
            "file_size_bytes": 1000,
        }
        result = tool._create_json_file_analysis(
            "/test.json", file_metrics, True, "json"
        )
        assert result["success"] is True
        assert result["language"] == "json"
        assert result["total_lines"] == 50
        assert result["non_empty_lines"] == 45
        assert result["scale_category"] == "small"
        assert "llm_analysis_guidance" in result

    def test_create_json_file_analysis_medium_without_mock(self, tool):
        """Test JSON file analysis for medium file without mock."""
        file_metrics = {
            "total_lines": 500,
            "code_lines": 500,
            "comment_lines": 0,
            "blank_lines": 10,
            "estimated_tokens": 2000,
            "file_size_bytes": 10000,
        }
        result = tool._create_json_file_analysis(
            "/test.json", file_metrics, False, "json"
        )
        assert result["scale_category"] == "medium"
        assert "llm_analysis_guidance" not in result

    def test_create_json_file_analysis_large_without_mock(self, tool):
        """Test JSON file analysis for large file without mock."""
        file_metrics = {
            "total_lines": 1500,
            "code_lines": 1500,
            "comment_lines": 0,
            "blank_lines": 20,
            "estimated_tokens": 6000,
            "file_size_bytes": 30000,
        }
        result = tool._create_json_file_analysis(
            "/test.json", file_metrics, True, "json"
        )
        assert result["scale_category"] == "large"
        assert result["analysis_recommendations"]["suitable_for_full_analysis"] is False


class TestAnalyzeScaleToolValidateArgumentsAdvanced:
    """Additional validation tests for edge cases."""

    def test_validate_arguments_minimal_single(self, tool):
        """Test validation with minimal valid arguments."""
        assert tool.validate_arguments({"file_path": "test.py"}) is True

    def test_validate_arguments_whitespace_file_path(self, tool):
        """Test validation fails for whitespace-only file_path."""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            tool.validate_arguments({"file_path": "   "})

    def test_validate_arguments_valid_batch_with_all_fields(self, tool):
        """Test valid batch mode with all optional fields."""
        arguments = {
            "file_paths": ["a.py", "b.py"],
            "metrics_only": True,
            "output_format": "json",
        }
        assert tool.validate_arguments(arguments) is True


class TestCountElementsUniversalBranch:
    """Tests targeting the universal elif branch in _count_elements (line 279)."""

    def test_count_elements_matches_via_getattr_not_is_element_of_type(self, tool):
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_FUNCTION

        class FakeElement:
            element_type = "function"

        elem = FakeElement()
        count = tool._count_elements([elem], ELEMENT_TYPE_FUNCTION, "function")
        assert count == 1


class TestGenerateLLMGuidanceQueryLoader:
    """Tests targeting query_loader integration in _generate_llm_guidance (lines 424-431)."""

    def test_guidance_includes_available_queries_from_loader(self, tool):
        file_metrics = {"total_lines": 100, "language": "python"}
        structural_overview = {
            "complexity_hotspots": [],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
        }
        with patch(
            "tree_sitter_analyzer.query_loader.get_query_loader"
        ) as mock_get_loader:
            mock_loader = MagicMock()
            mock_loader.list_queries_for_language.return_value = [
                "classes",
                "methods",
                "decorator",
            ]
            mock_get_loader.return_value = mock_loader
            guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
            assert guidance["available_queries"] == ["classes", "decorator", "methods"]

    def test_guidance_no_queries_from_loader(self, tool):
        file_metrics = {"total_lines": 100, "language": "brainfuck"}
        structural_overview = {
            "complexity_hotspots": [],
            "classes": [],
            "methods": [],
            "fields": [],
            "imports": [],
        }
        with patch(
            "tree_sitter_analyzer.query_loader.get_query_loader"
        ) as mock_get_loader:
            mock_loader = MagicMock()
            mock_loader.list_queries_for_language.return_value = []
            mock_get_loader.return_value = mock_loader
            guidance = tool._generate_llm_guidance(file_metrics, structural_overview)
            assert "available_queries" not in guidance


class TestExecuteLanguageSanitization:
    """Tests targeting language sanitization path in execute (line 521)."""

    @pytest.mark.asyncio
    async def test_execute_with_language_sanitization(self, tool):
        mock_analysis_result = MagicMock()
        mock_analysis_result.elements = []
        mock_analysis_result.package = None
        mock_analysis_result.success = True
        mock_analysis_result.get_statistics = MagicMock(return_value={})

        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 50,
                    "code_lines": 40,
                    "comment_lines": 5,
                    "blank_lines": 5,
                    "estimated_tokens": 200,
                    "file_size_bytes": 1024,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_analysis_result,
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_path": "test.py", "language": "python"}
            result = await tool.execute(arguments)
            assert result["success"] is True
            assert result["language"] == "python"

    @pytest.mark.asyncio
    async def test_execute_batch_mode_via_execute(self, tool):
        arguments = {"file_paths": ["a.py"], "metrics_only": True}
        with patch.object(
            tool, "_execute_metrics_batch", new_callable=AsyncMock
        ) as mock_batch:
            mock_batch.return_value = {"success": True}
            result = await tool.execute(arguments)
            assert result["success"] is True
            mock_batch.assert_called_once_with(arguments)

    @pytest.mark.asyncio
    async def test_execute_exception_reraise(self, tool):
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 50,
                    "code_lines": 40,
                    "comment_lines": 5,
                    "blank_lines": 5,
                    "estimated_tokens": 200,
                    "file_size_bytes": 1024,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                side_effect=RuntimeError("engine crashed"),
            ),
        ):
            arguments = {"file_path": "test.py", "language": "python"}
            with pytest.raises(RuntimeError, match="engine crashed"):
                await tool.execute(arguments)


class TestExecuteMetricsBatchFullBody:
    """Tests targeting _execute_metrics_batch body (lines 765-830)."""

    @pytest.mark.asyncio
    async def test_batch_with_resolved_file_not_found(self, tool):
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=False),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_paths": ["missing.py"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_errors"] == 1

    @pytest.mark.asyncio
    async def test_batch_with_non_string_path_entry(self, tool):
        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
            side_effect=lambda r, f: r,
        ):
            arguments = {"file_paths": [None], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_errors"] >= 1

    @pytest.mark.asyncio
    async def test_batch_with_resolved_path_exists(self, tool):
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.apply_toon_format_to_response",
                side_effect=lambda r, f: r,
            ),
        ):
            arguments = {"file_paths": ["test.py"], "metrics_only": True}
            result = await tool._execute_metrics_batch(arguments)
            assert result["count_ok"] == 1
            assert result["results"][0]["language"] == "python"


class TestCreateJsonFileAnalysisGuidance:
    """Tests targeting _create_json_file_analysis guidance and toon paths."""

    def test_json_file_with_guidance_toon_format(self, tool):
        file_metrics = {
            "total_lines": 100,
            "code_lines": 100,
            "comment_lines": 0,
            "blank_lines": 10,
            "estimated_tokens": 400,
            "file_size_bytes": 2000,
        }
        result = tool._create_json_file_analysis(
            "/test.json", file_metrics, True, "json"
        )
        assert result["success"] is True
        assert "llm_analysis_guidance" in result

    def test_json_file_without_guidance(self, tool):
        file_metrics = {
            "total_lines": 100,
            "code_lines": 100,
            "comment_lines": 0,
            "blank_lines": 5,
            "estimated_tokens": 400,
            "file_size_bytes": 2000,
        }
        result = tool._create_json_file_analysis(
            "/test.json", file_metrics, False, "json"
        )
        assert result["success"] is True
        assert "llm_analysis_guidance" not in result


class TestModuleLevelInstance:
    """Test that module-level instance exists."""

    def test_module_level_instance(self):
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import (
            analyze_scale_tool,
        )

        assert analyze_scale_tool is not None
        assert isinstance(analyze_scale_tool, AnalyzeScaleTool)


class TestCoverageBoost:
    """Tests targeting the last uncovered lines."""

    def test_count_elements_universal_string_fallback(self, tool):
        """Test _count_elements falls back to string match when is_element_of_type fails."""
        from tree_sitter_analyzer.constants import ELEMENT_TYPE_CLASS

        class _FakeElem:
            pass

        elem = _FakeElem()
        elem.element_type = "class"
        count = tool._count_elements([elem], ELEMENT_TYPE_CLASS, "class")
        assert count == 1

    @pytest.mark.asyncio
    async def test_execute_dispatches_to_batch(self, tool):
        """Test execute() dispatches to _execute_metrics_batch when file_paths given."""
        with patch.object(
            tool,
            "_execute_metrics_batch",
            new_callable=AsyncMock,
            return_value={"success": True, "count_files": 1},
        ):
            result = await tool.execute(
                {"file_paths": ["test.py"], "metrics_only": True}
            )
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_non_java_none_universal_result(self, tool):
        """Test execute handles None result from universal engine (non-Java)."""
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(RuntimeError, match="Failed to analyze file"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_non_java_falsy_result_with_no_error_msg(self, tool):
        """Test execute handles universal result with success=False and no error_message."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = None
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(RuntimeError, match="Failed to analyze file"):
                await tool.execute(arguments)

    @pytest.mark.asyncio
    async def test_execute_non_java_falsy_result_with_error_msg(self, tool):
        """Test execute handles universal result with success=False and error_message."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Parse error in file"
        with (
            patch.object(
                tool, "resolve_and_validate_file_path", return_value="/test.py"
            ),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "tree_sitter_analyzer.mcp.tools.analyze_scale_tool.detect_language_from_file",
                return_value="python",
            ),
            patch.object(
                tool,
                "_calculate_file_metrics",
                return_value={
                    "total_lines": 100,
                    "code_lines": 80,
                    "comment_lines": 15,
                    "blank_lines": 5,
                    "estimated_tokens": 400,
                    "file_size_bytes": 2048,
                },
            ),
            patch.object(
                tool.analysis_engine,
                "analyze",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
        ):
            arguments = {"file_path": "test.py"}
            with pytest.raises(
                RuntimeError, match="Failed to analyze file with universal engine"
            ):
                await tool.execute(arguments)
