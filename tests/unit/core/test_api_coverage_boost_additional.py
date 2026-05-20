#!/usr/bin/env python3
"""
Additional coverage boost tests for tree_sitter_analyzer.api module.

Targets uncovered branches in:
- analyze_file method-in-class, exclude flags, exceptions
- analyze_code method-in-class, exclude flags, failure
- validate_file readable/unreadable files
- _group_captures_by_main_node edge cases
- execute_query dict/list/other captures, failure, exception
- extract_elements type filtering, no elements key
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer import api


class TestAnalyzeFileAdditional:
    """Additional tests for analyze_file uncovered paths."""

    def test_method_inside_class_assigns_class_name(self) -> None:
        """Lines 148-160: method element inside a class gets class_name."""
        mock_class = MagicMock()
        mock_class.name = "MyClass"
        mock_class.start_line = 1
        mock_class.end_line = 20
        mock_class.raw_text = "class MyClass"
        mock_class.language = "python"
        mock_class.is_method = False
        type(mock_class).__name__ = "Class"

        mock_method = MagicMock()
        mock_method.name = "my_method"
        mock_method.start_line = 5
        mock_method.end_line = 10
        mock_method.raw_text = "def my_method"
        mock_method.language = "python"
        mock_method.is_method = True
        type(mock_method).__name__ = "Function"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.language = "python"
        mock_result.node_count = 50
        mock_result.line_count = 20
        mock_result.error_message = ""
        mock_result.elements = [mock_class, mock_method]
        mock_result.query_results = {"test": []}

        mock_engine = MagicMock()
        mock_engine.analyze_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_file("test.py")
            assert result["success"] is True
            method_elem = result["elements"][1]
            assert method_elem.get("class_name") == "MyClass"

    def test_method_not_in_class_gets_none(self) -> None:
        """Lines 159-160: method element with no containing class."""
        mock_method = MagicMock()
        mock_method.name = "standalone"
        mock_method.start_line = 1
        mock_method.end_line = 5
        mock_method.raw_text = "def standalone"
        mock_method.language = "python"
        mock_method.is_method = True
        type(mock_method).__name__ = "Function"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.language = "python"
        mock_result.node_count = 10
        mock_result.line_count = 5
        mock_result.error_message = ""
        mock_result.elements = [mock_method]
        mock_result.query_results = {}

        mock_engine = MagicMock()
        mock_engine.analyze_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_file("test.py")
            method_elem = result["elements"][0]
            assert method_elem.get("class_name") is None

    def test_include_elements_false_removes_elements(self) -> None:
        """Line 174: include_elements=False deletes elements key."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.language = "python"
        mock_result.node_count = 10
        mock_result.line_count = 5
        mock_result.error_message = ""
        mock_result.elements = []
        mock_result.query_results = {}

        mock_engine = MagicMock()
        mock_engine.analyze_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_file("test.py", include_elements=False)
            assert "elements" not in result

    def test_include_queries_false_removes_query_results(self) -> None:
        """Line 177: include_queries=False deletes query_results key."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.language = "python"
        mock_result.node_count = 10
        mock_result.line_count = 5
        mock_result.error_message = ""
        mock_result.elements = []
        mock_result.query_results = {"test": []}

        mock_engine = MagicMock()
        mock_engine.analyze_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_file("test.py", include_queries=False)
            assert "query_results" not in result

    def test_generic_exception_returns_error_dict(self) -> None:
        """Lines 181-186: generic exception in analyze_file."""
        mock_engine = MagicMock()
        mock_engine.analyze_sync.side_effect = RuntimeError("Unexpected")

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_file("test.py")
            assert result["success"] is False
            assert "error" in result

    def test_file_not_found_error_is_re_raised(self) -> None:
        """FileNotFoundError is a public API exception, not an error dict."""
        mock_engine = MagicMock()
        mock_engine.analyze_sync.side_effect = FileNotFoundError("missing.py")

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            with pytest.raises(FileNotFoundError, match="missing.py"):
                api.analyze_file("missing.py")


class TestAnalyzeCodeAdditional:
    """Additional tests for analyze_code uncovered paths."""

    def test_method_inside_class_in_code(self) -> None:
        """Lines 289-301: analyze_code method inside class."""
        mock_class = MagicMock()
        mock_class.name = "Svc"
        mock_class.start_line = 1
        mock_class.end_line = 20
        mock_class.raw_text = "class Svc"
        mock_class.language = "java"
        mock_class.is_method = False
        type(mock_class).__name__ = "Class"

        mock_method = MagicMock()
        mock_method.name = "run"
        mock_method.start_line = 5
        mock_method.end_line = 10
        mock_method.raw_text = "void run()"
        mock_method.language = "java"
        mock_method.is_method = True
        type(mock_method).__name__ = "Function"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.language = "java"
        mock_result.node_count = 30
        mock_result.line_count = 20
        mock_result.error_message = ""
        mock_result.elements = [mock_class, mock_method]

        mock_engine = MagicMock()
        mock_engine.analyze_code_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_code("class Svc {}", language="java")
            method_elem = result["elements"][1]
            assert method_elem.get("class_name") == "Svc"

    def test_include_elements_false(self) -> None:
        """Line 315: analyze_code include_elements=False."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.language = "python"
        mock_result.node_count = 10
        mock_result.line_count = 5
        mock_result.error_message = ""
        mock_result.elements = []

        mock_engine = MagicMock()
        mock_engine.analyze_code_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_code(
                "x = 1", language="python", include_elements=False
            )
            assert "elements" not in result

    def test_include_queries_false(self) -> None:
        """Line 318: analyze_code include_queries=False."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.language = "python"
        mock_result.node_count = 10
        mock_result.line_count = 5
        mock_result.error_message = ""
        mock_result.elements = []
        mock_result.query_results = {"q": []}

        mock_engine = MagicMock()
        mock_engine.analyze_code_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_code("x = 1", language="python", include_queries=False)
            assert "query_results" not in result

    def test_failure_returns_error(self) -> None:
        """Lines 238-240: analyze_code failure with error_message."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "bad syntax"
        mock_result.language = "python"

        mock_engine = MagicMock()
        mock_engine.analyze_code_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_code("bad", language="python")
            assert result["success"] is False
            assert result["error"] == "bad syntax"


class TestValidateFileAdditional:
    """Additional tests for validate_file uncovered paths."""

    def test_readable_valid_file(self) -> None:
        """Lines 475-503: validate_file with existing readable file."""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n")
            tmp = f.name
        try:
            result = api.validate_file(tmp)
            assert result["exists"] is True
            assert result["readable"] is True
            assert result["language"] is not None
            assert isinstance(result["valid"], bool)
        finally:
            os.unlink(tmp)

    def test_unreadable_file(self) -> None:
        """Lines 482-484: validate_file with unreadable file."""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("x = 1\n")
            tmp = f.name
        try:
            os.chmod(tmp, 0o000)
            result = api.validate_file(tmp)
            assert result["readable"] is False
        finally:
            os.chmod(tmp, 0o644)
            os.unlink(tmp)


class TestGroupCapturesAdditional:
    """Additional tests for _group_captures_by_main_node."""

    def test_empty_captures(self) -> None:
        """Line 559: empty captures list."""
        from tree_sitter_analyzer.api import _group_captures_by_main_node

        result = _group_captures_by_main_node([])
        assert result == []

    def test_stack_pop_when_child_beyond_parent(self) -> None:
        """Line 582: stack pop when child extends beyond parent."""
        from tree_sitter_analyzer.api import _group_captures_by_main_node

        captures = [
            {
                "capture_name": "class",
                "text": "class A",
                "start_byte": 0,
                "end_byte": 50,
                "line_number": 1,
                "node_type": "class_declaration",
            },
            {
                "capture_name": "method",
                "text": "void foo()",
                "start_byte": 20,
                "end_byte": 80,
                "line_number": 3,
                "node_type": "method_declaration",
            },
        ]
        result = _group_captures_by_main_node(captures)
        assert len(result) == 2

    def test_sub_capture_without_parent(self) -> None:
        """Sub-capture with no containing main node is ignored."""
        from tree_sitter_analyzer.api import _group_captures_by_main_node

        captures = [
            {
                "capture_name": "name",
                "text": "foo",
                "start_byte": 10,
                "end_byte": 20,
                "line_number": 1,
                "node_type": "identifier",
            },
        ]
        result = _group_captures_by_main_node(captures)
        assert len(result) == 0


class TestExecuteQueryAdditional:
    """Additional tests for execute_query uncovered paths."""

    def test_execute_query_with_dict_captures(self) -> None:
        """Line 648: captures from dict query_result_dict."""
        with patch(
            "tree_sitter_analyzer.api.analyze_file",
            return_value={
                "success": True,
                "query_results": {
                    "class": {
                        "captures": [
                            {
                                "capture_name": "class",
                                "text": "class Foo",
                                "start_byte": 0,
                                "end_byte": 50,
                                "line_number": 1,
                                "node_type": "class_declaration",
                            }
                        ]
                    }
                },
                "language_info": {"language": "java"},
            },
        ):
            result = api.execute_query("test.java", "class")
            assert result["success"] is True
            assert result["count"] >= 1

    def test_execute_query_with_list_captures(self) -> None:
        """Line 649-650: captures as plain list."""
        with patch(
            "tree_sitter_analyzer.api.analyze_file",
            return_value={
                "success": True,
                "query_results": {
                    "method": [
                        {
                            "capture_name": "method",
                            "text": "void run()",
                            "start_byte": 0,
                            "end_byte": 40,
                            "line_number": 1,
                            "node_type": "method_declaration",
                        }
                    ]
                },
                "language_info": {"language": "java"},
            },
        ):
            result = api.execute_query("test.java", "method")
            assert result["success"] is True

    def test_execute_query_with_other_type_captures(self) -> None:
        """Line 651-652: captures is neither dict-with-captures nor list."""
        with patch(
            "tree_sitter_analyzer.api.analyze_file",
            return_value={
                "success": True,
                "query_results": {"test": "not_a_list"},
                "language_info": {"language": "python"},
            },
        ):
            result = api.execute_query("test.py", "test")
            assert result["success"] is True
            assert result["count"] == 0

    def test_execute_query_failure(self) -> None:
        """Lines 666-672: execute_query when analyze_file fails."""
        with patch(
            "tree_sitter_analyzer.api.analyze_file",
            return_value={
                "success": False,
                "error": "File not found",
            },
        ):
            result = api.execute_query("missing.py", "class")
            assert result["success"] is False

    def test_execute_query_exception(self) -> None:
        """Lines 674-681: execute_query exception handler."""
        with patch(
            "tree_sitter_analyzer.api.analyze_file", side_effect=RuntimeError("Boom")
        ):
            result = api.execute_query("test.py", "class")
            assert result["success"] is False
            assert result["error"] == "Boom"


class TestExtractElementsAdditional:
    """Additional tests for extract_elements uncovered paths."""

    def test_extract_with_type_filtering(self) -> None:
        """Lines 707-720: extract_elements filters by element_types."""
        with patch(
            "tree_sitter_analyzer.api.analyze_file",
            return_value={
                "success": True,
                "elements": [
                    {"name": "Foo", "type": "class"},
                    {"name": "bar", "type": "function"},
                    {"name": "x", "type": "variable"},
                ],
                "language_info": {"language": "python"},
            },
        ):
            result = api.extract_elements("test.py", element_types=["class"])
            assert result["success"] is True
            assert all(e["type"] == "class" for e in result["elements"])
            assert result["count"] == 1

    def test_extract_no_matching_types(self) -> None:
        """No elements match the filter."""
        with patch(
            "tree_sitter_analyzer.api.analyze_file",
            return_value={
                "success": True,
                "elements": [
                    {"name": "Foo", "type": "class"},
                ],
                "language_info": {"language": "python"},
            },
        ):
            result = api.extract_elements("test.py", element_types=["function"])
            assert result["count"] == 0

    def test_extract_elements_no_elements_key(self) -> None:
        """Lines 727-732: successful analysis but no elements key."""
        with patch(
            "tree_sitter_analyzer.api.analyze_file",
            return_value={
                "success": True,
                "language_info": {"language": "python"},
            },
        ):
            result = api.extract_elements("test.py")
            assert result["success"] is False
