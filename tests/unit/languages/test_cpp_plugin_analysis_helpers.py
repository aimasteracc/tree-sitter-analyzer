"""Tests for _cpp_plugin_analysis — parser creation, language loading, result building."""

from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.languages._cpp_plugin_analysis import (
    build_cpp_analysis_result,
    cpp_analysis_error_result,
    cpp_parser_failure_result,
    create_cpp_parser,
    empty_cpp_analysis_result,
    flatten_cpp_elements,
    load_cpp_tree_sitter_language,
)
from tree_sitter_analyzer.models import AnalysisResult


class TestEmptyCppAnalysisResult:
    def test_returns_correct_result(self):
        result = empty_cpp_analysis_result("main.cpp", "int x;\nint y;")
        assert isinstance(result, AnalysisResult)
        assert result.file_path == "main.cpp"
        assert result.language == "cpp"
        assert result.line_count == 2
        assert result.elements == []
        assert result.source_code == "int x;\nint y;"
        assert result.success is True

    def test_single_line(self):
        result = empty_cpp_analysis_result("a.cpp", "hello")
        assert result.line_count == 1

    def test_empty_content(self):
        # splitlines() of "" returns [], matching wc -l on an empty file.
        # (Old N+1 behavior pinned 1; corrected to 0 in the line_count parity fix.)
        result = empty_cpp_analysis_result("a.cpp", "")
        assert result.line_count == 0


class TestCppParserFailureResult:
    def test_includes_error_message(self):
        err = RuntimeError("parse error")
        result = cpp_parser_failure_result("f.cpp", "code", err)
        assert result.success is False
        assert "parse error" in result.error_message
        assert result.elements == []

    def test_line_count(self):
        result = cpp_parser_failure_result("f.cpp", "a\nb\nc", ValueError("x"))
        assert result.line_count == 3


class TestCreateCppParser:
    @patch("tree_sitter.Parser")
    def test_set_language_path(self, MockParser):
        lang = MagicMock()
        mock_instance = MagicMock()
        MockParser.return_value = mock_instance
        result, err = create_cpp_parser(lang, "f.cpp", "c")
        assert result is mock_instance
        assert err is None
        mock_instance.set_language.assert_called_once_with(lang)

    @patch("tree_sitter.Parser")
    def test_language_attr_path(self, MockParser):
        lang = MagicMock()
        mock_instance = MagicMock(spec=["language"])
        MockParser.return_value = mock_instance
        result, err = create_cpp_parser(lang, "f.cpp", "c")
        assert result is mock_instance
        assert err is None
        assert mock_instance.language == lang

    @patch("tree_sitter.Parser")
    def test_constructor_fallback_success(self, MockParser):
        lang = MagicMock()
        mock_no_attrs = MagicMock(spec=[])
        mock_fallback = MagicMock()
        MockParser.side_effect = [mock_no_attrs, mock_fallback]
        result, err = create_cpp_parser(lang, "f.cpp", "c")
        assert result is mock_fallback
        assert err is None

    @patch("tree_sitter.Parser")
    def test_constructor_fallback_failure(self, MockParser):
        lang = MagicMock()
        mock_no_attrs = MagicMock(spec=[])
        MockParser.side_effect = [mock_no_attrs, TypeError("nope")]
        result, err = create_cpp_parser(lang, "f.cpp", "c")
        assert result is None
        assert err is not None
        assert err.success is False


class TestLoadCppTreeSitterLanguage:
    def test_import_error_returns_none(self):
        with patch.dict("sys.modules", {"tree_sitter_cpp": None}):
            result = load_cpp_tree_sitter_language()
        assert result is None

    def test_general_exception_returns_none(self):
        with (
            patch(
                "tree_sitter_analyzer.languages._cpp_plugin_analysis._coerce_cpp_language",
                side_effect=RuntimeError("boom"),
            ),
            patch.dict(
                "sys.modules",
                {"tree_sitter": MagicMock(), "tree_sitter_cpp": MagicMock()},
            ),
        ):
            result = load_cpp_tree_sitter_language()
        assert result is None


class TestFlattenCppElements:
    def test_merges_all_keys(self):
        d = {
            "functions": ["f1"],
            "classes": ["c1"],
            "variables": ["v1"],
            "imports": ["i1"],
            "packages": ["p1"],
        }
        result = flatten_cpp_elements(d)
        assert result == ["f1", "c1", "v1", "i1", "p1"]

    def test_missing_keys_default_empty(self):
        result = flatten_cpp_elements({"functions": ["f"]})
        assert result == ["f"]

    def test_empty_dict(self):
        assert flatten_cpp_elements({}) == []


class TestBuildCppAnalysisResult:
    def test_builds_result(self):
        result = build_cpp_analysis_result("f.cpp", "a\nb", {"functions": ["main"]}, 42)
        assert result.file_path == "f.cpp"
        assert result.language == "cpp"
        assert result.line_count == 2
        assert result.node_count == 42
        assert result.elements == ["main"]


class TestCppAnalysisErrorResult:
    def test_error_result(self):
        result = cpp_analysis_error_result("f.cpp", ValueError("bad"))
        assert result.success is False
        assert result.file_path == "f.cpp"
        assert "bad" in result.error_message
        assert result.line_count == 0
