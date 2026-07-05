"""Unit tests for _api_query_helpers — capture grouping and element filtering."""

from tree_sitter_analyzer.internal_api.query_helpers import (
    filter_elements_by_type,
    group_captures_by_main_node,
    query_captures_for_result,
    query_execution_result,
)


class TestGroupCapturesByMainNode:
    """Tests for group_captures_by_main_node."""

    def test_empty_captures_returns_empty_list(self):
        assert group_captures_by_main_node([]) == []

    def test_single_main_capture(self):
        captures = [
            {
                "capture_name": "class",
                "start_byte": 0,
                "end_byte": 100,
                "text": "class Foo",
                "line_number": 1,
                "node_type": "class_declaration",
            }
        ]
        result = group_captures_by_main_node(captures)
        assert len(result) == 1
        assert result[0]["node_type"] == "class_declaration"
        assert "class" in result[0]["captures"]

    def test_nested_child_attached_to_parent(self):
        captures = [
            {
                "capture_name": "class",
                "start_byte": 0,
                "end_byte": 200,
                "text": "class Foo",
                "line_number": 1,
                "node_type": "class_declaration",
            },
            {
                "capture_name": "method.name",
                "start_byte": 50,
                "end_byte": 60,
                "text": "bar",
                "line_number": 3,
                "node_type": "identifier",
            },
        ]
        result = group_captures_by_main_node(captures)
        assert len(result) == 1
        assert "method.name" in result[0]["captures"]

    def test_overlapping_main_nodes_stacked(self):
        captures = [
            {
                "capture_name": "class",
                "start_byte": 0,
                "end_byte": 200,
                "text": "class Foo",
                "line_number": 1,
                "node_type": "class_declaration",
            },
            {
                "capture_name": "method",
                "start_byte": 30,
                "end_byte": 150,
                "text": "def bar()",
                "line_number": 2,
                "node_type": "method_declaration",
            },
        ]
        result = group_captures_by_main_node(captures)
        assert len(result) == 2
        # Class first (lower start_byte), then method

    def test_multiple_children_same_capture_name_becomes_list(self):
        captures = [
            {
                "capture_name": "class",
                "start_byte": 0,
                "end_byte": 200,
                "text": "class Foo",
                "line_number": 1,
                "node_type": "class_declaration",
            },
            {
                "capture_name": "parameter",
                "start_byte": 20,
                "end_byte": 30,
                "text": "x",
                "line_number": 2,
                "node_type": "identifier",
            },
            {
                "capture_name": "parameter",
                "start_byte": 35,
                "end_byte": 45,
                "text": "y",
                "line_number": 3,
                "node_type": "identifier",
            },
        ]
        result = group_captures_by_main_node(captures)
        assert len(result) == 1
        params = result[0]["captures"]["parameter"]
        assert isinstance(params, list)
        assert len(params) == 2

    def test_child_without_active_parent_is_ignored(self):
        captures = [
            {
                "capture_name": "parameter",
                "start_byte": 0,
                "end_byte": 10,
                "text": "x",
                "line_number": 1,
                "node_type": "identifier",
            },
        ]
        result = group_captures_by_main_node(captures)
        assert len(result) == 0

    def test_end_line_calculation_counts_newlines(self):
        captures = [
            {
                "capture_name": "function",
                "start_byte": 0,
                "end_byte": 50,
                "text": "line1\nline2\nline3",
                "line_number": 1,
                "node_type": "function_declaration",
            },
        ]
        result = group_captures_by_main_node(captures)
        assert result[0]["start_line"] == 1
        assert result[0]["end_line"] == 1 + 2  # 2 newlines

    def test_sorted_by_start_byte_then_nested_first(self):
        captures = [
            {
                "capture_name": "function",
                "start_byte": 10,
                "end_byte": 50,
                "text": "fn",
                "line_number": 2,
                "node_type": "function_declaration",
            },
            {
                "capture_name": "class",
                "start_byte": 0,
                "end_byte": 100,
                "text": "cls",
                "line_number": 1,
                "node_type": "class_declaration",
            },
        ]
        result = group_captures_by_main_node(captures)
        # Sorted: class (0, -100) before function (10, -50)
        assert result[0]["node_type"] == "class_declaration"
        assert result[1]["node_type"] == "function_declaration"


class TestQueryCapturesForResult:
    """Tests for query_captures_for_result."""

    def test_dict_captures_key(self):
        result = {"query_results": {"functions": {"captures": [{"name": "foo"}]}}}
        captures = query_captures_for_result(result, "functions")
        assert len(captures) == 1

    def test_list_query_result(self):
        result = {"query_results": {"functions": [{"name": "foo"}]}}
        captures = query_captures_for_result(result, "functions")
        assert len(captures) == 1

    def test_missing_query_name_returns_empty(self):
        result = {"query_results": {}}
        assert query_captures_for_result(result, "nonexistent") == []

    def test_non_dict_non_list_returns_empty(self):
        result = {"query_results": {"q": "string"}}
        assert query_captures_for_result(result, "q") == []


class TestQueryExecutionResult:
    """Tests for query_execution_result."""

    def test_failed_analysis(self):
        result = {"success": False, "error": "Parse failed"}
        output = query_execution_result(result, "functions", "test.py")
        assert output["success"] is False
        assert output["error"] == "Parse failed"

    def test_successful_execution(self):
        result = {
            "success": True,
            "query_results": {
                "functions": {
                    "captures": [
                        {
                            "capture_name": "function",
                            "start_byte": 0,
                            "end_byte": 50,
                            "text": "def foo(): pass",
                            "line_number": 1,
                            "node_type": "function_definition",
                        }
                    ]
                }
            },
            "language_info": {"language": "python"},
        }
        output = query_execution_result(result, "functions", "test.py")
        assert output["success"] is True
        assert output["count"] == 1
        assert output["language"] == "python"

    def test_no_query_results_key(self):
        result = {"success": True}
        output = query_execution_result(result, "functions", "test.py")
        assert output["success"] is False

    def test_file_path_preserved(self):
        result = {"success": False, "error": "err"}
        output = query_execution_result(result, "q", "/path/to/file.py")
        assert output["file_path"] == "/path/to/file.py"


class TestFilterElementsByType:
    """Tests for filter_elements_by_type."""

    def test_none_types_returns_all(self):
        elements = [{"type": "function"}, {"type": "class"}]
        assert filter_elements_by_type(elements, None) == elements

    def test_empty_types_returns_all(self):
        elements = [{"type": "function"}]
        assert filter_elements_by_type(elements, []) == elements

    def test_case_insensitive_match(self):
        elements = [{"type": "Function"}, {"type": "Class"}]
        result = filter_elements_by_type(elements, ["function"])
        assert len(result) == 1
        assert result[0]["type"] == "Function"

    def test_fuzzy_substring_match(self):
        elements = [{"type": "class_method"}, {"type": "function"}]
        result = filter_elements_by_type(elements, ["class"])
        assert len(result) == 1
        assert result[0]["type"] == "class_method"

    def test_multiple_types_any_match(self):
        elements = [{"type": "function"}, {"type": "class"}, {"type": "variable"}]
        result = filter_elements_by_type(elements, ["function", "class"])
        assert len(result) == 2

    def test_no_match_returns_empty(self):
        elements = [{"type": "function"}]
        result = filter_elements_by_type(elements, ["class"])
        assert result == []

    # --- #795 backward-compat: element_types=["class"] must include subtypes ---

    def test_class_filter_includes_interface(self):
        """#795 P2: filtering by 'class' must still return interface elements."""
        elements = [{"type": "interface"}, {"type": "function"}]
        result = filter_elements_by_type(elements, ["class"])
        assert len(result) == 1
        assert result[0]["type"] == "interface"

    def test_class_filter_includes_enum(self):
        elements = [{"type": "enum"}, {"type": "function"}]
        result = filter_elements_by_type(elements, ["class"])
        assert len(result) == 1
        assert result[0]["type"] == "enum"

    def test_class_filter_includes_namespace(self):
        elements = [{"type": "namespace"}, {"type": "function"}]
        result = filter_elements_by_type(elements, ["class"])
        assert len(result) == 1
        assert result[0]["type"] == "namespace"

    def test_class_filter_includes_type_alias(self):
        elements = [{"type": "type"}, {"type": "function"}]
        result = filter_elements_by_type(elements, ["class"])
        assert len(result) == 1
        assert result[0]["type"] == "type"

    def test_class_filter_includes_abstract_class(self):
        elements = [{"type": "abstract_class"}, {"type": "class"}]
        result = filter_elements_by_type(elements, ["class"])
        assert len(result) == 2

    def test_interface_filter_does_not_widen_to_all_class_family(self):
        """Filtering by 'interface' should NOT return plain 'class' elements."""
        elements = [{"type": "class"}, {"type": "interface"}, {"type": "enum"}]
        result = filter_elements_by_type(elements, ["interface"])
        assert len(result) == 1
        assert result[0]["type"] == "interface"
