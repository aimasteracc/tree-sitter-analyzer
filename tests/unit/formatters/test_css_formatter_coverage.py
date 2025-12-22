"""
Comprehensive tests for CSS Formatter to achieve 90%+ coverage.
"""

import pytest

from tree_sitter_analyzer.formatters.css_formatter import CSSFormatter
from tree_sitter_analyzer.models import AnalysisResult, StyleElement


@pytest.fixture
def formatter():
    return CSSFormatter()


@pytest.fixture
def sample_css_elements():
    """Create sample CSS elements for testing."""
    return [
        {
            "name": ".header",
            "element_type": "rule",
            "selector": ".header",
            "properties": {"color": "red", "font-size": "16px"},
            "element_class": "class_selector",
            "start_line": 1,
            "end_line": 4,
        },
        {
            "name": "#main",
            "element_type": "rule",
            "selector": "#main",
            "properties": {"margin": "0", "padding": "10px"},
            "element_class": "id_selector",
            "start_line": 5,
            "end_line": 8,
        },
        {
            "name": "body",
            "element_type": "rule",
            "selector": "body",
            "properties": {"background": "white"},
            "element_class": "element_selector",
            "start_line": 9,
            "end_line": 11,
        },
        {
            "name": "@media",
            "element_type": "at_rule",
            "selector": "@media screen and (max-width: 768px)",
            "properties": {},
            "element_class": "at_rule",
            "start_line": 12,
            "end_line": 20,
        },
    ]


class TestCSSFormatterInit:
    """Test initialization of CSSFormatter."""

    def test_init_sets_language(self, formatter):
        """Test that init sets language to css."""
        assert formatter.language == "css"


class TestFormatSummary:
    """Test format_summary method."""

    def test_format_summary_basic(self, formatter, sample_css_elements):
        """Test basic format_summary."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
        }
        result = formatter.format_summary(data)
        assert "Summary Results" in result
        assert "test.css" in result

    def test_format_summary_empty_elements(self, formatter):
        """Test format_summary with empty elements."""
        data = {"file_path": "empty.css", "elements": []}
        result = formatter.format_summary(data)
        assert "Summary Results" in result

    def test_format_summary_counts_selectors(self, formatter, sample_css_elements):
        """Test that format_summary counts different selector types."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
        }
        result = formatter.format_summary(data)
        assert "id_selectors" in result
        assert "class_selectors" in result
        assert "element_selectors" in result


class TestFormatStructure:
    """Test format_structure method."""

    def test_format_structure_basic(self, formatter, sample_css_elements):
        """Test basic format_structure."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter.format_structure(data)
        assert "Structure Analysis Results" in result
        assert "test.css" in result

    def test_format_structure_with_rules(self, formatter, sample_css_elements):
        """Test format_structure includes rules."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter.format_structure(data)
        assert "rules" in result

    def test_format_structure_with_at_rules(self, formatter, sample_css_elements):
        """Test format_structure includes at_rules."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter.format_structure(data)
        assert "at_rules" in result


class TestFormatAdvanced:
    """Test format_advanced method."""

    def test_format_advanced_json(self, formatter, sample_css_elements):
        """Test format_advanced with json output."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter.format_advanced(data, "json")
        assert "Advanced Analysis Results" in result
        assert "test.css" in result

    def test_format_advanced_text(self, formatter, sample_css_elements):
        """Test format_advanced with text output."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter.format_advanced(data, "text")
        assert "Advanced Analysis Results" in result

    def test_format_advanced_with_media_queries(self, formatter):
        """Test format_advanced detects media queries."""
        elements = [
            {
                "name": "@media screen",
                "element_type": "at_rule",
                "selector": "@media screen",
                "properties": {},
                "element_class": "at_rule",
                "start_line": 1,
                "end_line": 10,
            }
        ]
        data = {"file_path": "test.css", "elements": elements, "line_count": 10}
        result = formatter.format_advanced(data, "json")
        assert "has_media_queries" in result

    def test_format_advanced_with_keyframes(self, formatter):
        """Test format_advanced detects keyframes."""
        elements = [
            {
                "name": "@keyframes fadeIn",
                "element_type": "at_rule",
                "selector": "@keyframes fadeIn",
                "properties": {},
                "element_class": "at_rule",
                "start_line": 1,
                "end_line": 10,
            }
        ]
        data = {"file_path": "test.css", "elements": elements, "line_count": 10}
        result = formatter.format_advanced(data, "json")
        assert "has_keyframes" in result

    def test_format_advanced_with_imports(self, formatter):
        """Test format_advanced detects imports."""
        elements = [
            {
                "name": "@import url('styles.css')",
                "element_type": "at_rule",
                "selector": "@import",
                "properties": {},
                "element_class": "at_rule",
                "start_line": 1,
                "end_line": 1,
            }
        ]
        data = {"file_path": "test.css", "elements": elements, "line_count": 1}
        result = formatter.format_advanced(data, "json")
        assert "has_imports" in result


class TestFormatAnalysisResult:
    """Test format_analysis_result method."""

    def test_format_analysis_result_basic(self, formatter):
        """Test basic format_analysis_result."""
        element = StyleElement(
            name=".test",
            selector=".test",
            properties={"color": "blue"},
            element_class="class_selector",
            start_line=1,
            end_line=3,
        )
        result = AnalysisResult(
            file_path="test.css",
            elements=[element],
            language="css",
            line_count=10,
        )
        output = formatter.format_analysis_result(result, "full")
        assert isinstance(output, str)

    def test_format_analysis_result_compact(self, formatter):
        """Test format_analysis_result with compact type."""
        element = StyleElement(
            name=".test",
            selector=".test",
            properties={"color": "blue"},
            element_class="class_selector",
            start_line=1,
            end_line=3,
        )
        result = AnalysisResult(
            file_path="test.css",
            elements=[element],
            language="css",
            line_count=10,
        )
        output = formatter.format_analysis_result(result, "compact")
        assert isinstance(output, str)


class TestFormatTable:
    """Test format_table method."""

    def test_format_table_full(self, formatter, sample_css_elements):
        """Test format_table with full type."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter.format_table(data, "full")
        assert "CSS Analysis" in result
        assert "test.css" in result

    def test_format_table_compact(self, formatter, sample_css_elements):
        """Test format_table with compact type."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter.format_table(data, "compact")
        assert "Summary" in result

    def test_format_table_csv(self, formatter, sample_css_elements):
        """Test format_table with csv type."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter.format_table(data, "csv")
        assert "name,element_type,selector" in result


class TestFormatFull:
    """Test _format_full method."""

    def test_format_full_with_rules(self, formatter, sample_css_elements):
        """Test _format_full includes rules section."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter._format_full(data)
        assert "CSS Rules" in result

    def test_format_full_with_at_rules(self, formatter, sample_css_elements):
        """Test _format_full includes at-rules section."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter._format_full(data)
        assert "At-Rules" in result

    def test_format_full_with_top_properties(self, formatter, sample_css_elements):
        """Test _format_full includes top properties section."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter._format_full(data)
        assert "Top Properties" in result

    def test_format_full_empty_elements(self, formatter):
        """Test _format_full with empty elements."""
        data = {"file_path": "empty.css", "elements": [], "line_count": 0}
        result = formatter._format_full(data)
        assert "CSS Analysis" in result


class TestFormatCompact:
    """Test _format_compact method."""

    def test_format_compact_counts_selectors(self, formatter, sample_css_elements):
        """Test _format_compact counts different selector types."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter._format_compact(data)
        assert "ID Selectors" in result
        assert "Class Selectors" in result
        assert "Element Selectors" in result

    def test_format_compact_sample_rules(self, formatter, sample_css_elements):
        """Test _format_compact shows sample rules."""
        data = {
            "file_path": "test.css",
            "elements": sample_css_elements,
            "line_count": 100,
        }
        result = formatter._format_compact(data)
        assert "Sample Rules" in result

    def test_format_compact_filename_extraction(self, formatter):
        """Test _format_compact extracts filename correctly."""
        data = {
            "file_path": "/path/to/styles.css",
            "elements": [],
            "line_count": 0,
        }
        result = formatter._format_compact(data)
        assert "styles" in result


class TestFormatCSV:
    """Test _format_csv method."""

    def test_format_csv_header(self, formatter):
        """Test _format_csv includes header."""
        data = {"file_path": "test.css", "elements": []}
        result = formatter._format_csv(data)
        assert "name,element_type,selector,property_count,start_line,end_line" in result

    def test_format_csv_escapes_commas(self, formatter):
        """Test _format_csv escapes commas in values."""
        elements = [
            {
                "name": "selector,with,commas",
                "element_type": "rule",
                "selector": "a,b,c",
                "properties": {},
                "element_class": "rule",
                "start_line": 1,
                "end_line": 1,
            }
        ]
        data = {"file_path": "test.css", "elements": elements}
        result = formatter._format_csv(data)
        # Commas should be replaced with semicolons
        assert "selector;with;commas" in result


class TestCalculateComplexity:
    """Test _calculate_complexity method."""

    def test_complexity_simple(self, formatter):
        """Test complexity calculation for simple CSS."""
        rules = [{"properties": {"color": "red"}}]
        at_rules = []
        result = formatter._calculate_complexity(rules, at_rules)
        assert result == "Simple"

    def test_complexity_moderate(self, formatter):
        """Test complexity calculation for moderate CSS."""
        rules = [{"properties": {f"prop{i}": "value"}} for i in range(50)]
        at_rules = [{"name": "@media"} for _ in range(10)]
        result = formatter._calculate_complexity(rules, at_rules)
        assert result in ["Moderate", "Complex"]

    def test_complexity_complex(self, formatter):
        """Test complexity calculation for complex CSS."""
        rules = [
            {"properties": {f"prop{i}": "value" for i in range(10)}} for _ in range(100)
        ]
        at_rules = [{"name": "@media"} for _ in range(20)]
        result = formatter._calculate_complexity(rules, at_rules)
        assert result in ["Complex", "Very Complex"]


class TestHelperMethods:
    """Test helper methods."""

    def test_is_rule_with_dict(self, formatter):
        """Test _is_rule with dictionary element."""
        element = {"element_type": "rule", "element_class": "class_selector"}
        assert formatter._is_rule(element) is True

    def test_is_rule_with_at_rule(self, formatter):
        """Test _is_rule returns False for at_rule."""
        element = {"element_type": "at_rule", "element_class": "at_rule"}
        assert formatter._is_rule(element) is False

    def test_is_at_rule_with_dict(self, formatter):
        """Test _is_at_rule with dictionary element."""
        element = {"element_class": "at_rule"}
        assert formatter._is_at_rule(element) is True

    def test_is_at_rule_with_rule(self, formatter):
        """Test _is_at_rule returns False for regular rule."""
        element = {"element_class": "class_selector"}
        assert formatter._is_at_rule(element) is False

    def test_get_name_with_dict(self, formatter):
        """Test _get_name with dictionary element."""
        element = {"name": "test_name"}
        assert formatter._get_name(element) == "test_name"

    def test_get_name_with_object(self, formatter):
        """Test _get_name with object element."""

        class MockElement:
            name = "object_name"

        assert formatter._get_name(MockElement()) == "object_name"

    def test_get_element_type_with_dict(self, formatter):
        """Test _get_element_type with dictionary element."""
        element = {"element_type": "rule"}
        assert formatter._get_element_type(element) == "rule"

    def test_get_selector_with_dict(self, formatter):
        """Test _get_selector with dictionary element."""
        element = {"selector": ".test-selector"}
        assert formatter._get_selector(element) == ".test-selector"

    def test_get_properties_with_dict(self, formatter):
        """Test _get_properties with dictionary element."""
        element = {"properties": {"color": "red"}}
        assert formatter._get_properties(element) == {"color": "red"}

    def test_get_element_class_with_dict(self, formatter):
        """Test _get_element_class with dictionary element."""
        element = {"element_class": "class_selector"}
        assert formatter._get_element_class(element) == "class_selector"

    def test_get_start_line_with_dict(self, formatter):
        """Test _get_start_line with dictionary element."""
        element = {"start_line": 10}
        assert formatter._get_start_line(element) == 10

    def test_get_end_line_with_dict(self, formatter):
        """Test _get_end_line with dictionary element."""
        element = {"end_line": 20}
        assert formatter._get_end_line(element) == 20

    def test_get_methods_with_missing_attributes(self, formatter):
        """Test helper methods return defaults for missing attributes."""
        element = {}
        assert formatter._get_name(element) == ""
        assert formatter._get_element_type(element) == ""
        assert formatter._get_selector(element) == ""
        assert formatter._get_properties(element) == {}
        assert formatter._get_element_class(element) == ""
        assert formatter._get_start_line(element) == 0
        assert formatter._get_end_line(element) == 0


class TestConvertAnalysisResultToFormat:
    """Test _convert_analysis_result_to_format method."""

    def test_convert_analysis_result(self, formatter):
        """Test conversion of AnalysisResult."""
        element = StyleElement(
            name=".test",
            selector=".test",
            properties={"color": "blue"},
            element_class="class_selector",
            start_line=1,
            end_line=3,
        )
        result = AnalysisResult(
            file_path="test.css",
            elements=[element],
            language="css",
            line_count=10,
        )
        converted = formatter._convert_analysis_result_to_format(result)
        assert converted["file_path"] == "test.css"
        assert converted["language"] == "css"
        assert converted["line_count"] == 10
        assert len(converted["elements"]) == 1
