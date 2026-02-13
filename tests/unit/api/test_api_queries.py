#!/usr/bin/env python3
"""
Unit tests for API get_available_queries, execute_query, extract_elements,
and _group_captures_by_main_node.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import tree_sitter_analyzer.api as api_module


@pytest.fixture(autouse=True)
def reset_api_engine():
    """Reset api module engine singleton before and after each test."""
    api_module._engine = None
    yield
    api_module._engine = None


class TestGetAvailableQueries:
    """Tests for get_available_queries function."""

    def test_get_available_queries_success(self):
        """Returns query list from engine."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.get_available_queries.return_value = [
                "classes", "functions", "imports"
            ]
            result = api_module.get_available_queries("python")
            assert result == ["classes", "functions", "imports"]
            mock_engine.get_available_queries.assert_called_once_with("python")

    def test_get_available_queries_exception_returns_empty_list(self):
        """Exception returns empty list."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.get_available_queries.side_effect = RuntimeError("fail")
            result = api_module.get_available_queries("python")
            assert result == []

    def test_get_available_queries_empty_result(self):
        """Returns empty list when language has no queries."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.get_available_queries.return_value = []
            result = api_module.get_available_queries("unknown")
            assert result == []


class TestGroupCapturesByMainNode:
    """Tests for _group_captures_by_main_node internal helper."""

    def test_empty_captures_returns_empty_list(self):
        """Empty captures list returns []."""
        result = api_module._group_captures_by_main_node([])
        assert result == []

    def test_none_captures_returns_empty_list(self):
        """None-like input handled (empty list path)."""
        result = api_module._group_captures_by_main_node([])
        assert result == []

    def test_single_main_capture_method(self):
        """Single @method capture creates one result group."""
        captures = [
            {
                "capture_name": "method",
                "start_byte": 0,
                "end_byte": 20,
                "text": "def foo():",
                "line_number": 1,
                "node_type": "function_definition",
            }
        ]
        result = api_module._group_captures_by_main_node(captures)
        assert len(result) == 1
        assert "method" in result[0]["captures"]
        assert result[0]["captures"]["method"] == captures[0]
        assert result[0]["text"] == "def foo():"
        assert result[0]["start_line"] == 1

    def test_single_main_capture_class(self):
        """Single @class capture creates one result group."""
        captures = [
            {
                "capture_name": "class",
                "start_byte": 0,
                "end_byte": 50,
                "text": "class Foo:\n    pass",
                "line_number": 1,
                "node_type": "class_definition",
            }
        ]
        result = api_module._group_captures_by_main_node(captures)
        assert len(result) == 1
        assert "class" in result[0]["captures"]

    def test_single_main_capture_function(self):
        """Single @function capture creates one result group."""
        captures = [
            {
                "capture_name": "function",
                "start_byte": 0,
                "end_byte": 15,
                "text": "def bar():",
                "line_number": 1,
                "node_type": "function_definition",
            }
        ]
        result = api_module._group_captures_by_main_node(captures)
        assert len(result) == 1
        assert "function" in result[0]["captures"]

    def test_main_capture_with_sub_capture(self):
        """Sub-capture is grouped under main node."""
        captures = [
            {
                "capture_name": "method",
                "start_byte": 0,
                "end_byte": 30,
                "text": "def foo():",
                "line_number": 1,
                "node_type": "function_definition",
            },
            {
                "capture_name": "name",
                "start_byte": 4,
                "end_byte": 7,
                "text": "foo",
                "line_number": 1,
                "node_type": "identifier",
            },
        ]
        result = api_module._group_captures_by_main_node(captures)
        assert len(result) == 1
        assert "method" in result[0]["captures"]
        assert "name" in result[0]["captures"]
        assert result[0]["captures"]["name"]["text"] == "foo"

    def test_duplicate_sub_capture_converted_to_list(self):
        """Duplicate sub-capture name converts to list."""
        captures = [
            {
                "capture_name": "method",
                "start_byte": 0,
                "end_byte": 50,
                "text": "def foo():",
                "line_number": 1,
                "node_type": "function_definition",
            },
            {
                "capture_name": "decorator",
                "start_byte": 0,
                "end_byte": 10,
                "text": "@wrap",
                "line_number": 1,
                "node_type": "decorator",
            },
            {
                "capture_name": "decorator",
                "start_byte": 11,
                "end_byte": 20,
                "text": "@other",
                "line_number": 2,
                "node_type": "decorator",
            },
        ]
        result = api_module._group_captures_by_main_node(captures)
        assert len(result) == 1
        dec = result[0]["captures"]["decorator"]
        assert isinstance(dec, list)
        assert len(dec) == 2
        assert dec[0]["text"] == "@wrap"
        assert dec[1]["text"] == "@other"

    def test_multiple_main_captures_create_multiple_groups(self):
        """Multiple main captures create separate result groups."""
        captures = [
            {
                "capture_name": "function",
                "start_byte": 0,
                "end_byte": 15,
                "text": "def a():",
                "line_number": 1,
                "node_type": "function_definition",
            },
            {
                "capture_name": "function",
                "start_byte": 20,
                "end_byte": 35,
                "text": "def b():",
                "line_number": 2,
                "node_type": "function_definition",
            },
        ]
        result = api_module._group_captures_by_main_node(captures)
        assert len(result) == 2
        assert result[0]["captures"]["function"]["text"] == "def a():"
        assert result[1]["captures"]["function"]["text"] == "def b():"

    def test_sorted_by_start_byte_asc_end_byte_desc(self):
        """Captures sorted by start_byte asc, end_byte desc for nesting."""
        captures = [
            {
                "capture_name": "method",
                "start_byte": 10,
                "end_byte": 50,
                "text": "inner",
                "line_number": 2,
                "node_type": "function",
            },
            {
                "capture_name": "class",
                "start_byte": 0,
                "end_byte": 60,
                "text": "outer",
                "line_number": 1,
                "node_type": "class",
            },
        ]
        result = api_module._group_captures_by_main_node(captures)
        assert len(result) == 2
        assert result[0]["captures"]["class"]["start_byte"] == 0
        assert result[1]["captures"]["method"]["start_byte"] == 10

    def test_stack_pop_when_capture_outside_parent(self):
        """Nodes popped from stack when current capture outside parent."""
        captures = [
            {
                "capture_name": "class",
                "start_byte": 0,
                "end_byte": 30,
                "text": "class A:",
                "line_number": 1,
                "node_type": "class",
            },
            {
                "capture_name": "class",
                "start_byte": 40,
                "end_byte": 70,
                "text": "class B:",
                "line_number": 3,
                "node_type": "class",
            },
        ]
        result = api_module._group_captures_by_main_node(captures)
        assert len(result) == 2

    def test_interface_and_field_main_types(self):
        """interface and field are main capture types."""
        for main_type in ["interface", "field"]:
            captures = [
                {
                    "capture_name": main_type,
                    "start_byte": 0,
                    "end_byte": 20,
                    "text": "x",
                    "line_number": 1,
                    "node_type": main_type,
                }
            ]
            result = api_module._group_captures_by_main_node(captures)
            assert len(result) == 1
            assert main_type in result[0]["captures"]

    def test_end_line_computed_from_newlines(self):
        """end_line = start_line + newline count in text."""
        captures = [
            {
                "capture_name": "function",
                "start_byte": 0,
                "end_byte": 20,
                "text": "def x():\n    pass",
                "line_number": 1,
                "node_type": "function",
            }
        ]
        result = api_module._group_captures_by_main_node(captures)
        assert result[0]["end_line"] == 2

    def test_missing_keys_default_values(self):
        """Missing start_byte, end_byte etc use defaults."""
        captures = [
            {
                "capture_name": "method",
            }
        ]
        result = api_module._group_captures_by_main_node(captures)
        assert len(result) == 1
        assert result[0]["start_byte"] == 0
        assert result[0]["end_byte"] == 0
        assert result[0]["start_line"] == 0
        assert result[0]["end_line"] == 0
        assert result[0]["text"] == ""


class TestExecuteQuery:
    """Tests for execute_query function."""

    def test_execute_query_success_with_dict_captures(self):
        """Success when query_result is dict with captures."""
        analyze_result = {
            "success": True,
            "query_results": {
                "classes": {
                    "captures": [
                        {
                            "capture_name": "class",
                            "start_byte": 0,
                            "end_byte": 20,
                            "text": "class Foo",
                            "line_number": 1,
                        }
                    ]
                }
            },
            "language_info": {"language": "python"},
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.execute_query(
                "/test.py", "classes", language="python"
            )
            assert result["success"] is True
            assert result["query_name"] == "classes"
            assert result["count"] == 1
            assert result["language"] == "python"
            assert result["file_path"] == "/test.py"
            mock_analyze.assert_called_once_with(
                "/test.py",
                language="python",
                queries=["classes"],
                include_elements=False,
                include_queries=True,
            )

    def test_execute_query_success_with_list_captures(self):
        """Success when query_result is list (raw captures)."""
        analyze_result = {
            "success": True,
            "query_results": {
                "functions": [
                    {
                        "capture_name": "function",
                        "start_byte": 0,
                        "end_byte": 15,
                        "text": "def bar",
                        "line_number": 1,
                    }
                ]
            },
            "language_info": {"language": "python"},
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.execute_query("/test.py", "functions")
            assert result["success"] is True
            assert result["count"] == 1
            assert len(result["results"]) == 1

    def test_execute_query_empty_captures(self):
        """Empty captures returns count 0."""
        analyze_result = {
            "success": True,
            "query_results": {"classes": {"captures": []}},
            "language_info": {"language": "python"},
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.execute_query("/test.py", "classes")
            assert result["success"] is True
            assert result["count"] == 0
            assert result["results"] == []

    def test_execute_query_no_captures_key_uses_empty_list(self):
        """When query_result dict has no captures, use empty list."""
        analyze_result = {
            "success": True,
            "query_results": {"classes": {}},
            "language_info": {"language": "python"},
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.execute_query("/test.py", "classes")
            assert result["success"] is True
            assert result["count"] == 0

    def test_execute_query_analysis_failed(self):
        """Analysis failure returns success=False."""
        analyze_result = {
            "success": False,
            "error": "Parse error",
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.execute_query("/test.py", "classes")
            assert result["success"] is False
            assert result["error"] == "Parse error"

    def test_execute_query_no_query_results_key(self):
        """When success but no query_results, returns failure."""
        analyze_result = {
            "success": True,
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.execute_query("/test.py", "classes")
            assert result["success"] is False

    def test_execute_query_exception_returns_error_dict(self):
        """Exception returns error dict."""
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.side_effect = OSError("permission denied")
            result = api_module.execute_query("/test.py", "classes")
            assert result["success"] is False
            assert result["error"] == "permission denied"

    def test_execute_query_path_converted_to_string(self):
        """File path converted to string in result."""
        analyze_result = {
            "success": True,
            "query_results": {"classes": {"captures": []}},
            "language_info": {"language": "python"},
        }
        path_arg = Path("some/file.py")
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.execute_query(path_arg, "classes")
            assert result["file_path"] == str(path_arg)


class TestExtractElements:
    """Tests for extract_elements function."""

    def test_extract_elements_success(self):
        """Success returns elements and count."""
        analyze_result = {
            "success": True,
            "elements": [
                {"name": "foo", "type": "function", "start_line": 1},
                {"name": "Bar", "type": "class", "start_line": 5},
            ],
            "language_info": {"language": "python"},
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.extract_elements("/test.py")
            assert result["success"] is True
            assert result["count"] == 2
            assert len(result["elements"]) == 2
            mock_analyze.assert_called_once_with(
                "/test.py",
                language=None,
                include_elements=True,
                include_queries=False,
            )

    def test_extract_elements_with_language(self):
        """Passes language to analyze_file."""
        analyze_result = {
            "success": True,
            "elements": [],
            "language_info": {"language": "javascript"},
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            api_module.extract_elements("/test.js", language="javascript")
            mock_analyze.assert_called_once_with(
                "/test.js",
                language="javascript",
                include_elements=True,
                include_queries=False,
            )

    def test_extract_elements_filter_by_element_types(self):
        """Filters elements by element_types when provided."""
        analyze_result = {
            "success": True,
            "elements": [
                {"name": "foo", "type": "function", "start_line": 1},
                {"name": "Bar", "type": "class", "start_line": 5},
                {"name": "x", "type": "variable", "start_line": 10},
            ],
            "language_info": {"language": "python"},
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.extract_elements(
                "/test.py", element_types=["function", "class"]
            )
            assert result["success"] is True
            assert result["count"] == 2
            assert all(
                e["type"] in ("function", "class") for e in result["elements"]
            )

    def test_extract_elements_filter_case_insensitive(self):
        """Element type filter is case insensitive."""
        analyze_result = {
            "success": True,
            "elements": [
                {"name": "Foo", "type": "Class", "start_line": 1},
            ],
            "language_info": {"language": "python"},
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.extract_elements(
                "/test.py", element_types=["CLASS"]
            )
            assert result["count"] == 1

    def test_extract_elements_filter_partial_match(self):
        """Filter matches if etype is substring of element type."""
        analyze_result = {
            "success": True,
            "elements": [
                {"name": "x", "type": "function_definition", "start_line": 1},
            ],
            "language_info": {"language": "python"},
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.extract_elements(
                "/test.py", element_types=["function"]
            )
            assert result["count"] == 1

    def test_extract_elements_analysis_failed(self):
        """Analysis failure returns success=False."""
        analyze_result = {
            "success": False,
            "error": "File not found",
        }
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.extract_elements("/test.py")
            assert result["success"] is False
            assert result["error"] == "File not found"

    def test_extract_elements_no_elements_key(self):
        """When success but no elements key, returns failure."""
        analyze_result = {"success": True}
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.return_value = analyze_result
            result = api_module.extract_elements("/test.py")
            assert result["success"] is False

    def test_extract_elements_exception_returns_error_dict(self):
        """Exception returns error dict."""
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze:
            mock_analyze.side_effect = ValueError("bad path")
            result = api_module.extract_elements("/test.py")
            assert result["success"] is False
            assert result["error"] == "bad path"
