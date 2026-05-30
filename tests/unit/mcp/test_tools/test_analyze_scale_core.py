"""
Unit tests for AnalyzeScaleTool.

Tests for analyze_code_scale tool which provides code scale analysis
including metrics about complexity, size, and structure.
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.unit.mcp.test_tools._test_analyze_scale_tool_execute_mixins import (
    AnalyzeScaleToolCreateJsonFileAnalysisMixin,
    AnalyzeScaleToolExecuteMetricsBatchMixin,
    AnalyzeScaleToolExecuteMixin,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool


@pytest.fixture
def tool():
    """Create an AnalyzeScaleTool instance for testing."""
    return AnalyzeScaleTool()


@pytest.fixture
def tool_with_project_root():
    """Create an AnalyzeScaleTool instance with a project root."""
    return AnalyzeScaleTool(project_root="/test/project")


class TestAnalyzeScaleToolCalculateFileMetrics:
    """Tests for _calculate_file_metrics method."""

    def test_calculate_file_metrics_success(self, tool):
        """Test successful file metrics calculation."""
        with patch(
            "tree_sitter_analyzer.mcp.tools.analyze_scale_helpers.compute_file_metrics"
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
            "tree_sitter_analyzer.mcp.tools.analyze_scale_helpers.compute_file_metrics"
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


class TestAnalyzeScaleToolExecute(AnalyzeScaleToolExecuteMixin):
    """Tests for execute method (single mode)."""

    __test__ = True


class TestAnalyzeScaleToolExecuteMetricsBatch(AnalyzeScaleToolExecuteMetricsBatchMixin):
    """Tests for _execute_metrics_batch method."""

    __test__ = True


class TestAnalyzeScaleToolCreateJsonFileAnalysis(
    AnalyzeScaleToolCreateJsonFileAnalysisMixin
):
    """Tests for _create_json_file_analysis method."""

    __test__ = True


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
