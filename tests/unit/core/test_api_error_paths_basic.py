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
