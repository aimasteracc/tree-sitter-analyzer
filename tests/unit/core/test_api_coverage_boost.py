#!/usr/bin/env python3
"""
Coverage boost tests for tree_sitter_analyzer.api module.

Targets uncovered branches in:
- analyze_file error path (lines 97-99, 170, 174, 177)
- analyze_file element attributes (module_path, module_name, imported_names)
- analyze_file class_name assignment loop (lines 148-160)
- analyze_code error path (lines 238-240, 311, 315, 318)
- analyze_code element attributes + class_name loop (lines 256-260, 289-301)
- Exception handlers (lines 322-324, 342-344, 360-362, 378-380, 407-409)
- detect_language edge cases (lines 396, 404)
- get_file_extensions (lines 422-443)
- validate_file (lines 482-501)
- get_framework_info exception (lines 537-539)
- _group_captures_by_main_node list path (lines 608-610)
- execute_query captures path (line 648)
- execute_query error path (lines 667, 674-676)
- extract_elements exception (lines 734-736)
"""

from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer import api

# ============================================================================
# analyze_file error paths
# ============================================================================


class TestAnalyzeFileErrors:
    """Tests for analyze_file error and edge case paths."""

    def test_analyze_failure_with_error_message(self) -> None:
        """Lines 97-99: analysis failure with error_message."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Parse error"
        mock_result.language = "python"

        mock_engine = MagicMock()
        mock_engine.analyze_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_file("test.py")
            assert result["success"] is False
            assert result["error"] == "Parse error"

    def test_analyze_elements_with_module_path(self) -> None:
        """Line 256: elements with module_path attribute."""
        mock_elem = MagicMock()
        mock_elem.name = "MyModule"
        mock_elem.start_line = 1
        mock_elem.end_line = 10
        mock_elem.raw_text = "module MyModule"
        mock_elem.language = "python"
        mock_elem.module_path = "mypackage.mymodule"
        mock_elem.module_name = "mymodule"
        mock_elem.imported_names = ["os", "sys"]
        type(mock_elem).__name__ = "Module"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.language = "python"
        mock_result.node_count = 50
        mock_result.line_count = 10
        mock_result.error_message = ""
        mock_result.elements = [mock_elem]

        mock_engine = MagicMock()
        mock_engine.analyze_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_file("test.py")
            assert result["success"] is True
            elem = result["elements"][0]
            assert elem["module_path"] == "mypackage.mymodule"
            assert elem["module_name"] == "mymodule"
            assert elem["imported_names"] == ["os", "sys"]

    def test_analyze_failure_no_elements_no_queries(self) -> None:
        """Lines 170-177: error when elements/query_results not present."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Analysis failed"
        mock_result.language = "java"
        mock_result.node_count = 0
        mock_result.line_count = 0

        mock_engine = MagicMock()
        mock_engine.analyze_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_file("test.java")
            assert result["success"] is False
            assert result["error"] == "Analysis failed"


# ============================================================================
# analyze_code paths
# ============================================================================


class TestAnalyzeCode:
    """Tests for analyze_code error and edge case paths."""

    def test_analyze_code_failure_with_error_message(self) -> None:
        """Lines 238-240: code analysis failure."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Syntax error"
        mock_result.language = "python"
        mock_result.node_count = 0
        mock_result.line_count = 0

        mock_engine = MagicMock()
        mock_engine.analyze_code_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_code("invalid code", language="python")
            assert result["success"] is False
            assert result["error"] == "Syntax error"

    def test_analyze_code_with_elements(self) -> None:
        """Lines 244-284: elements with all attributes."""
        mock_elem = MagicMock()
        mock_elem.name = "MyClass"
        mock_elem.start_line = 1
        mock_elem.end_line = 20
        mock_elem.raw_text = "class MyClass {}"
        mock_elem.language = "java"
        mock_elem.module_path = "com.example"
        mock_elem.module_name = "MyModule"
        mock_elem.imported_names = ["java.util.*"]
        mock_elem.superclass = "Object"
        mock_elem.class_type = "public"
        type(mock_elem).__name__ = "Class"

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.language = "java"
        mock_result.node_count = 50
        mock_result.line_count = 20
        mock_result.error_message = ""
        mock_result.elements = [mock_elem]

        mock_engine = MagicMock()
        mock_engine.analyze_code_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_code("class MyClass {}", language="java")
            assert result["success"] is True
            elem = result["elements"][0]
            assert elem["name"] == "MyClass"
            assert elem["module_path"] == "com.example"
            assert elem["superclass"] == "Object"

    def test_analyze_code_failure_no_elements(self) -> None:
        """Lines 311-318: code analysis failure removing elements/queries."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error_message = "Failed"
        mock_result.language = "python"
        mock_result.node_count = 0
        mock_result.line_count = 0

        mock_engine = MagicMock()
        mock_engine.analyze_code_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_code("bad code", language="python")
            assert result["success"] is False

    def test_analyze_code_exception(self) -> None:
        """Lines 322-324: analyze_code exception handler."""
        mock_engine = MagicMock()
        mock_engine.analyze_code_sync.side_effect = RuntimeError("Boom")

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze_code("code", language="python")
            assert result["success"] is False
            assert "error" in result


# ============================================================================
# Exception handlers for utility functions
# ============================================================================


class TestExceptionPaths:
    """Tests for exception handling paths in various API functions."""

    def test_get_supported_languages_exception(self) -> None:
        """Lines 342-344: get_supported_languages exception."""
        mock_engine = MagicMock()
        mock_engine.get_supported_languages.side_effect = RuntimeError("No langs")

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.get_supported_languages()
            assert result == []

    def test_get_available_queries_exception(self) -> None:
        """Lines 360-362: get_available_queries exception."""
        mock_engine = MagicMock()
        mock_engine.get_available_queries.side_effect = RuntimeError("No queries")

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.get_available_queries("python")
            assert result == []

    def test_is_language_supported_exception(self) -> None:
        """Lines 378-380: is_language_supported exception."""
        mock_engine = MagicMock()
        mock_engine.is_language_supported.side_effect = RuntimeError("Bad check")

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.is_language_supported("python")
            assert result is False

    def test_detect_language_exception(self) -> None:
        """Lines 407-409: detect_language exception."""
        mock_engine = MagicMock()
        mock_engine.language_detector = MagicMock()
        mock_engine.language_detector.detect_from_extension.side_effect = RuntimeError(
            "Bad"
        )

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.detect_language("test.py")
            assert result == "unknown"

    def test_get_file_extensions_exception(self) -> None:
        """Lines 441-443: get_file_extensions exception."""
        mock_engine = MagicMock()
        mock_engine.language_detector.side_effect = RuntimeError("Bad")

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.get_file_extensions("python")
            assert result == []

    def test_get_framework_info_exception(self) -> None:
        """Lines 537-539: get_framework_info exception."""
        with patch("tree_sitter_analyzer.api.__version__", "1.0.0"):
            with patch(
                "tree_sitter_analyzer.api.get_engine", side_effect=RuntimeError("Boom")
            ):
                result = api.get_framework_info()
                assert result["name"] == "tree-sitter-analyzer"
                assert "error" in result


# ============================================================================
# detect_language edge cases
# ============================================================================


class TestDetectLanguageEdgeCases:
    """Tests for detect_language edge cases."""

    def test_empty_file_path(self) -> None:
        """Line 396: empty file_path returns 'unknown'."""
        result = api.detect_language("")
        assert result == "unknown"

    def test_nonexistent_file(self) -> None:
        """Line 404: empty detection result returns 'unknown'."""
        mock_engine = MagicMock()
        mock_engine.language_detector = MagicMock()
        mock_engine.language_detector.detect_from_extension.return_value = ""

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.detect_language("/nonexistent/file")
            assert result == "unknown"

    def test_whitespace_result(self) -> None:
        """Line 404: whitespace-only result returns 'unknown'."""
        mock_engine = MagicMock()
        mock_engine.language_detector = MagicMock()
        mock_engine.language_detector.detect_from_extension.return_value = "   "

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.detect_language("test.file")
            assert result == "unknown"


# ============================================================================
# get_file_extensions
# ============================================================================


class TestGetFileExtensions:
    """Tests for get_file_extensions edge cases."""

    def test_with_get_extensions_method(self) -> None:
        """Lines 425-427: hasattr get_extensions_for_language."""
        mock_ld = MagicMock()
        mock_ld.get_extensions_for_language.return_value = None

        mock_engine = MagicMock()
        mock_engine.language_detector = mock_ld

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.get_file_extensions("python")
            assert result == []

    def test_fallback_extension_map(self) -> None:
        """Lines 430-440: fallback to extension_map."""
        mock_ld = MagicMock()
        del mock_ld.get_extensions_for_language

        mock_engine = MagicMock()
        mock_engine.language_detector = mock_ld

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.get_file_extensions("python")
            assert ".py" in result

    def test_fallback_unknown_language(self) -> None:
        """Fallback for unknown language returns empty list."""
        mock_ld = MagicMock()
        del mock_ld.get_extensions_for_language

        mock_engine = MagicMock()
        mock_engine.language_detector = mock_ld

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.get_file_extensions("unknownlang")
            assert result == []


# ============================================================================
# validate_file
# ============================================================================


class TestValidateFile:
    """Tests for validate_file."""

    def test_nonexistent_file(self) -> None:
        """File doesn't exist."""
        result = api.validate_file("/nonexistent/file12345.py")
        assert result["exists"] is False

    def test_validation_exception(self) -> None:
        """Lines 500-501: top-level validation exception."""
        with patch("pathlib.Path.is_file", side_effect=RuntimeError("Disk error")):
            result = api.validate_file("/some/file.py")
            assert result["valid"] is False
            assert len(result["errors"]) > 0


# ============================================================================
# execute_query
# ============================================================================


class TestExecuteQuery:
    """Tests for execute_query edge cases."""

    def test_execute_query_error(self) -> None:
        """Lines 667-676: execute_query error path."""
        mock_result = {
            "success": True,
            "query_results": {
                "class": [("node1", "@class")],
            },
            "language_info": {"language": "java"},
        }

        # analyze_file returns result where query_results has list captures
        with patch("tree_sitter_analyzer.api.analyze_file", return_value=mock_result):
            result = api.execute_query("test.java", "class")
            assert isinstance(result, dict)


# ============================================================================
# extract_elements
# ============================================================================


class TestExtractElements:
    """Tests for extract_elements edge cases."""

    def test_extract_elements_error(self) -> None:
        """Lines 734-736: extract_elements error."""
        mock_result = {
            "success": False,
            "error": "Analysis failed",
        }

        with patch("tree_sitter_analyzer.api.analyze_file", return_value=mock_result):
            result = api.extract_elements("test.py")
            assert result["success"] is False
            assert result["error"] == "Analysis failed"

    def test_extract_elements_exception(self) -> None:
        """Exception handler."""
        with patch(
            "tree_sitter_analyzer.api.analyze_file", side_effect=RuntimeError("Boom")
        ):
            result = api.extract_elements("test.py")
            assert result["success"] is False


# ============================================================================
# Convenience functions
# ============================================================================


class TestConvenienceFunctions:
    """Tests for convenience/alias functions."""

    def test_analyze_alias(self) -> None:
        """Line 742: analyze() aliases to analyze_file()."""
        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.language = "python"
        mock_result.node_count = 10
        mock_result.line_count = 5
        mock_result.error_message = ""
        mock_result.elements = []
        mock_engine.analyze_sync.return_value = mock_result

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.analyze("test.py")
            assert result["success"] is True

    def test_get_languages_alias(self) -> None:
        """Line 747: get_languages() aliases to get_supported_languages()."""
        mock_engine = MagicMock()
        mock_engine.get_supported_languages.return_value = ["python", "java"]

        with patch("tree_sitter_analyzer.api.get_engine", return_value=mock_engine):
            result = api.get_languages()
            assert "python" in result


# ============================================================================
# _group_captures_by_main_node (lines 608-610)
# ============================================================================


class TestGroupCaptures:
    """Tests for _group_captures_by_main_node internal function."""

    def test_list_capture_path(self) -> None:
        """Lines 608-610: existing capture is a list (multiple sub-captures)."""
        from tree_sitter_analyzer.api import _group_captures_by_main_node

        captures = [
            {
                "capture_name": "method",
                "text": "foo()",
                "start_byte": 10,
                "end_byte": 100,
                "line_number": 3,
                "node_type": "method_declaration",
            },
            {
                "capture_name": "doc",
                "text": "first doc",
                "start_byte": 15,
                "end_byte": 40,
                "line_number": 4,
                "node_type": "comment",
            },
            {
                "capture_name": "doc",
                "text": "second doc",
                "start_byte": 45,
                "end_byte": 60,
                "line_number": 5,
                "node_type": "comment",
            },
        ]
        result = _group_captures_by_main_node(captures)
        assert len(result) == 1
        assert len(result[0]["captures"]) >= 2


# ============================================================================
# Additional coverage: analyze_file method-in-class, exclude flags, exceptions
# ============================================================================


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
        import os
        import tempfile

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
        import os
        import tempfile

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
