"""Mixins for query tool: helpers (format_summary, extract_name, categorize, build_next_steps)."""

from unittest.mock import patch


class TestFormatSummaryTestMixin:
    """Tests for _format_summary method."""

    def test_format_summary_basic(self, tool, mock_query_results):
        summary = tool._format_summary(mock_query_results, "methods", "python")
        assert summary["success"] is True
        assert summary["query_type"] == "methods"
        assert summary["language"] == "python"
        assert summary["total_count"] == len(mock_query_results)
        assert "captures" in summary

    def test_format_summary_grouping(self, tool, mock_query_results):
        summary = tool._format_summary(mock_query_results, "methods", "python")
        assert "method" in summary["captures"]
        assert summary["captures"]["method"]["count"] == 2

    def test_format_summary_item_structure(self, tool, mock_query_results):
        summary = tool._format_summary(mock_query_results, "methods", "python")
        items = summary["captures"]["method"]["items"]
        for item in items:
            assert "name" in item
            assert "line_range" in item
            assert "node_type" in item

    def test_format_summary_multiple_captures(self, tool):
        results = [
            {
                "capture_name": "class",
                "content": "class Foo:\n    pass",
                "start_line": 1,
                "end_line": 2,
                "node_type": "class_definition",
            },
            {
                "capture_name": "function",
                "content": "def bar():\n    pass",
                "start_line": 4,
                "end_line": 5,
                "node_type": "function_definition",
            },
        ]
        summary = tool._format_summary(results, "all", "python")
        assert summary["total_count"] == 2
        assert "class" in summary["captures"]
        assert "function" in summary["captures"]
        assert summary["captures"]["class"]["count"] == 1
        assert summary["captures"]["function"]["count"] == 1


class TestExtractNameFromContentTestMixin:
    """Tests for _extract_name_from_content method."""

    def test_extract_method_name(self, tool):
        content = "def method_name(self, arg1):\n    pass"
        name = tool._extract_name_from_content(content)
        assert name == "method_name"

    def test_extract_class_name(self, tool):
        content = "public class ClassName {\n    // class body\n}"
        name = tool._extract_name_from_content(content)
        assert name == "ClassName"

    def test_extract_function_name(self, tool):
        content = "function_name()"
        name = tool._extract_name_from_content(content)
        assert name == "function_name"

    def test_extract_markdown_header(self, tool):
        content = "# Main Title\n\nContent here"
        name = tool._extract_name_from_content(content)
        assert name == "Main Title"

    def test_extract_unnamed(self, tool):
        content = "random content without patterns"
        name = tool._extract_name_from_content(content)
        assert name == "unnamed"

    def test_extract_empty_content(self, tool):
        name = tool._extract_name_from_content("")
        assert name == "unnamed"

    def test_extract_whitespace_only_content(self, tool):
        name = tool._extract_name_from_content("   \n   \n   ")
        assert name == "unnamed"

    def test_extract_private_method(self, tool):
        content = "private static void doSomething(int x) {"
        name = tool._extract_name_from_content(content)
        assert name == "doSomething"

    def test_extract_protected_method(self, tool):
        content = "protected String getName() {"
        name = tool._extract_name_from_content(content)
        assert name == "getName"

    def test_extract_subheading(self, tool):
        content = "## Sub Heading\nMore content"
        name = tool._extract_name_from_content(content)
        assert name == "Sub Heading"


class TestGetAvailableQueriesTestMixin:
    """Tests for get_available_queries method."""

    def test_get_available_queries(self, tool):
        with patch.object(
            tool.query_service,
            "get_available_queries",
            return_value=["methods", "classes"],
        ):
            queries = tool.get_available_queries("python")
            assert queries == ["methods", "classes"]


class TestFormatSummaryAdditionalTestMixin:
    """Additional tests for _format_summary."""

    def test_format_summary_empty_results(self, tool):
        summary = tool._format_summary([], "methods", "python")
        assert summary["success"] is True
        assert summary["total_count"] == 0
        assert summary["captures"] == {}

    def test_format_summary_single_result(self, tool):
        results = [
            {
                "capture_name": "class",
                "content": "class MyClass:\n    pass",
                "start_line": 1,
                "end_line": 2,
                "node_type": "class_definition",
            },
        ]
        summary = tool._format_summary(results, "class", "java")
        assert summary["total_count"] == 1
        assert "class" in summary["captures"]
        assert summary["captures"]["class"]["count"] == 1
        item = summary["captures"]["class"]["items"][0]
        assert "name" in item
        assert item["line_range"] == "1-2"
        assert item["node_type"] == "class_definition"


class TestExtractNameAdditionalTestMixin:
    """Additional tests for _extract_name_from_content."""

    def test_extract_interface_name(self, tool):
        content = "public interface MyService {\n    void process();\n}"
        name = tool._extract_name_from_content(content)
        assert name == "MyService"

    def test_extract_static_method_name(self, tool):
        content = "public static void main(String[] args) {"
        name = tool._extract_name_from_content(content)
        assert name == "main"

    def test_extract_deep_subheading(self, tool):
        content = "### Deep Section Title\nSome details"
        name = tool._extract_name_from_content(content)
        assert name == "Deep Section Title"


class TestFormatSummaryCoverageBoostTestMixin:
    """Tests targeting uncovered _format_summary branches."""

    def test_format_summary_multi_capture_with_items(self, tool):
        results = [
            {
                "capture_name": "class",
                "content": "class MyClass:\n    pass",
                "start_line": 1,
                "end_line": 2,
                "node_type": "class_definition",
            },
            {
                "capture_name": "class",
                "content": "class OtherClass:\n    pass",
                "start_line": 10,
                "end_line": 11,
                "node_type": "class_definition",
            },
            {
                "capture_name": "method",
                "content": "def my_method(self):\n    pass",
                "start_line": 5,
                "end_line": 6,
                "node_type": "function_definition",
            },
        ]
        summary = tool._format_summary(results, "all", "python")

        assert summary["total_count"] == 3
        assert summary["captures"]["class"]["count"] == 2
        assert summary["captures"]["method"]["count"] == 1
        class_items = summary["captures"]["class"]["items"]
        assert class_items[0]["name"] == "MyClass"
        assert class_items[1]["name"] == "OtherClass"
        assert class_items[0]["line_range"] == "1-2"
        method_items = summary["captures"]["method"]["items"]
        assert method_items[0]["name"] == "my_method"


class TestExtractNameCoverageBoostTestMixin:
    """Tests targeting uncovered _extract_name_from_content branches."""

    def test_extract_simple_function_call(self, tool):
        name = tool._extract_name_from_content("process(data)")
        assert name == "process"

    def test_extract_private_static_class(self, tool):
        name = tool._extract_name_from_content("private static class Singleton {")
        assert name == "Singleton"

    def test_extract_unnamed_no_pattern_match(self, tool):
        name = tool._extract_name_from_content("return 42")
        assert name == "unnamed"


class TestCategorizeQueriesTestMixin:
    """Tests for _categorize_queries helper function."""

    def test_common_keys_categorized(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(
            ["classes", "methods", "functions", "imports", "variables"], "python"
        )
        assert "common" in result
        assert result["common"] == [
            "classes",
            "methods",
            "functions",
            "imports",
            "variables",
        ]

    def test_declaration_keys_categorized(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(
            ["struct_definitions", "enum_members", "interface_declarations"],
            "typescript",
        )
        assert "declarations" in result
        assert "struct_definitions" in result["declarations"]

    def test_control_flow_keys_categorized(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(
            ["for_loops", "while_loops", "switch_statements"], "java"
        )
        assert "control_flow" in result
        assert "for_loops" in result["control_flow"]

    def test_framework_keys_categorized(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(
            ["spring_controller", "react_component", "goroutine_definitions"], "go"
        )
        assert "framework" in result
        assert "spring_controller" in result["framework"]

    def test_other_keys_categorized(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(["comments", "strings", "misc_stuff"], "python")
        assert "other" in result
        assert "comments" in result["other"]

    def test_empty_categories_removed(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(["classes"], "python")
        assert "common" in result
        assert "control_flow" not in result
        assert "framework" not in result

    def test_mixed_categorization(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries(
            [
                "classes",
                "for_loops",
                "spring_service",
                "struct_defs",
                "random_thing",
            ],
            "java",
        )
        assert result["common"] == ["classes"]
        assert "for_loops" in result["control_flow"]
        assert "spring_service" in result["framework"]
        assert "struct_defs" in result["declarations"]
        assert "random_thing" in result["other"]

    def test_empty_query_list(self):
        from tree_sitter_analyzer.mcp.tools.query_tool import _categorize_queries

        result = _categorize_queries([], "python")
        assert result == {}


class TestBuildNextStepsTestMixin:
    """Tests for _build_next_steps method."""

    def test_empty_results_returns_empty(self, tool):
        results = []
        steps = tool._build_next_steps(results, "test.py", "methods")
        assert steps == []

    def test_single_result_suggests_other_queries(self, tool):
        results = [
            {
                "capture_name": "method",
                "start_line": 1,
                "end_line": 5,
                "name": "foo",
                "node_type": "func",
            }
        ]
        steps = tool._build_next_steps(results, "test.py", "methods")
        assert any("Try other query keys" in s for s in steps)

    def test_many_results_suggests_filter(self, tool):
        results = [
            {
                "capture_name": "method",
                "start_line": i,
                "end_line": i + 1,
                "name": f"m{i}",
                "node_type": "func",
            }
            for i in range(5)
        ]
        steps = tool._build_next_steps(results, "test.py", "methods")
        assert any("filter" in s.lower() for s in steps)

    def test_named_results_with_method_query_suggests_search(self, tool):
        results = [
            {
                "capture_name": "method",
                "start_line": 1,
                "end_line": 3,
                "name": "doWork",
                "node_type": "func",
            },
            {
                "capture_name": "method",
                "start_line": 5,
                "end_line": 7,
                "name": "process",
                "node_type": "func",
            },
        ]
        steps = tool._build_next_steps(results, "test.py", "methods")
        assert any("search_content" in s for s in steps)

    def test_named_results_with_function_query_suggests_search(self, tool):
        results = [
            {
                "capture_name": "func",
                "start_line": 1,
                "end_line": 3,
                "name": "handler",
                "node_type": "func",
            },
        ]
        steps = tool._build_next_steps(results, "test.py", "functions")
        assert any("search_content" in s for s in steps)

    def test_unnamed_results_no_search_suggestion(self, tool):
        results = [
            {
                "capture_name": "method",
                "start_line": 1,
                "end_line": 3,
                "node_type": "func",
            },
        ]
        steps = tool._build_next_steps(results, "test.py", "methods")
        assert not any("search_content" in s for s in steps)

    def test_non_method_function_query_no_search(self, tool):
        results = [
            {
                "capture_name": "class",
                "start_line": 1,
                "end_line": 3,
                "name": "Foo",
                "node_type": "class",
            },
        ]
        steps = tool._build_next_steps(results, "test.py", "classes")
        assert not any("search_content" in s for s in steps)

    def test_returns_at_most_three_steps(self, tool):
        results = [
            {
                "capture_name": "m",
                "start_line": i,
                "end_line": i + 2,
                "name": f"n{i}",
                "node_type": "func",
            }
            for i in range(10)
        ]
        steps = tool._build_next_steps(results, "test.py", "methods")
        assert len(steps) <= 3

    def test_extractable_result_generates_extract_step(self, tool):
        results = [
            {
                "capture_name": "m",
                "start_line": 10,
                "end_line": 20,
                "name": "myFunc",
                "node_type": "func",
            }
        ]
        steps = tool._build_next_steps(results, "app.py", "methods")
        assert any("extract_code_section" in s for s in steps)

    def test_no_line_range_no_extract_step(self, tool):
        results = [{"capture_name": "m", "name": "myFunc", "node_type": "func"}]
        steps = tool._build_next_steps(results, "app.py", "methods")
        assert not any("extract_code_section" in s for s in steps)

    def test_same_start_end_line_no_extract(self, tool):
        results = [
            {
                "capture_name": "m",
                "start_line": 5,
                "end_line": 5,
                "name": "myFunc",
                "node_type": "func",
            }
        ]
        steps = tool._build_next_steps(results, "app.py", "methods")
        assert not any("extract_code_section" in s for s in steps)
