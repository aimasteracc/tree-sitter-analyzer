#!/usr/bin/env python3
"""
Unit tests for API utility functions: get_supported_languages,
is_language_supported, detect_language, get_file_extensions, validate_file,
get_framework_info, get_engine, get_languages, analyze alias.
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


class TestGetSupportedLanguages:
    """Tests for get_supported_languages function."""

    def test_get_supported_languages_success(self):
        """Returns list from engine."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.get_supported_languages.return_value = [
                "python", "javascript", "java"
            ]
            result = api_module.get_supported_languages()
            assert result == ["python", "javascript", "java"]

    def test_get_supported_languages_exception_returns_empty_list(self):
        """Exception returns empty list."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_get_engine.side_effect = RuntimeError("engine error")
            result = api_module.get_supported_languages()
            assert result == []


class TestGetLanguages:
    """Tests for get_languages alias."""

    def test_get_languages_is_alias_for_get_supported_languages(self):
        """get_languages returns same result as get_supported_languages."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.get_supported_languages.return_value = ["python"]
            result = api_module.get_languages()
            assert result == ["python"]
            mock_engine.get_supported_languages.assert_called_once()


class TestIsLanguageSupported:
    """Tests for is_language_supported function."""

    def test_is_language_supported_true(self):
        """Returns True when language is supported."""
        with patch("tree_sitter_analyzer.api.get_supported_languages") as mock_get:
            mock_get.return_value = ["python", "JavaScript", "Java"]
            assert api_module.is_language_supported("python") is True
            assert api_module.is_language_supported("Python") is True

    def test_is_language_supported_case_insensitive(self):
        """Comparison is case insensitive."""
        with patch("tree_sitter_analyzer.api.get_supported_languages") as mock_get:
            mock_get.return_value = ["python"]
            assert api_module.is_language_supported("PYTHON") is True
            assert api_module.is_language_supported("Python") is True

    def test_is_language_supported_false(self):
        """Returns False when language not supported."""
        with patch("tree_sitter_analyzer.api.get_supported_languages") as mock_get:
            mock_get.return_value = ["python"]
            assert api_module.is_language_supported("unknown") is False

    def test_is_language_supported_exception_returns_false(self):
        """Exception returns False."""
        with patch("tree_sitter_analyzer.api.get_supported_languages") as mock_get:
            mock_get.side_effect = ValueError("fail")
            assert api_module.is_language_supported("python") is False


class TestDetectLanguage:
    """Tests for detect_language function."""

    def test_detect_language_success(self):
        """Returns detected language from engine."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.language_detector.detect_from_extension.return_value = "python"
            result = api_module.detect_language("/path/to/file.py")
            assert result == "python"

    def test_detect_language_empty_file_path_returns_unknown(self):
        """Empty file_path returns 'unknown'."""
        result = api_module.detect_language("")
        assert result == "unknown"

    def test_detect_language_none_file_path_returns_unknown(self):
        """None file_path returns 'unknown' (falsy check)."""
        result = api_module.detect_language(None)
        assert result == "unknown"

    def test_detect_language_empty_result_returns_unknown(self):
        """Empty or whitespace result returns 'unknown'."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.language_detector.detect_from_extension.return_value = ""
            result = api_module.detect_language("/file.txt")
            assert result == "unknown"

    def test_detect_language_whitespace_result_returns_unknown(self):
        """Whitespace-only result returns 'unknown'."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.language_detector.detect_from_extension.return_value = "   "
            result = api_module.detect_language("/file.txt")
            assert result == "unknown"

    def test_detect_language_exception_returns_unknown(self):
        """Exception returns 'unknown'."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_get_engine.side_effect = RuntimeError("engine fail")
            result = api_module.detect_language("/file.py")
            assert result == "unknown"

    def test_detect_language_converts_path_to_string(self):
        """Path object is converted to string."""
        path_arg = Path("src/file.py")
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.language_detector.detect_from_extension.return_value = "python"
            api_module.detect_language(path_arg)
            mock_engine.language_detector.detect_from_extension.assert_called_once_with(
                str(path_arg)
            )


class TestGetFileExtensions:
    """Tests for get_file_extensions function."""

    def test_get_file_extensions_uses_get_extensions_for_language(self):
        """Uses language_detector.get_extensions_for_language when available."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_detector = MagicMock()
            mock_detector.get_extensions_for_language.return_value = [".py", ".pyw"]
            mock_engine.language_detector = mock_detector
            result = api_module.get_file_extensions("python")
            assert result == [".py", ".pyw"]
            mock_detector.get_extensions_for_language.assert_called_once_with(
                "python"
            )

    def test_get_file_extensions_empty_result_returns_empty_list(self):
        """Empty result from get_extensions_for_language returns []."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_detector = MagicMock()
            mock_detector.get_extensions_for_language.return_value = None
            mock_engine.language_detector = mock_detector
            result = api_module.get_file_extensions("python")
            assert result == []

    def test_get_file_extensions_fallback_extension_map(self):
        """Falls back to extension_map when no get_extensions_for_language."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_detector = object()  # No get_extensions_for_language attr
            mock_engine.language_detector = mock_detector
            result = api_module.get_file_extensions("python")
            assert result == [".py"]

    def test_get_file_extensions_fallback_java(self):
        """Fallback map returns .java for java."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_detector = object()
            mock_engine.language_detector = mock_detector
            result = api_module.get_file_extensions("java")
            assert result == [".java"]

    def test_get_file_extensions_fallback_cpp(self):
        """Fallback map returns multiple extensions for cpp."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_detector = object()
            mock_engine.language_detector = mock_detector
            result = api_module.get_file_extensions("cpp")
            assert result == [".cpp", ".cxx", ".cc"]

    def test_get_file_extensions_fallback_unknown_returns_empty(self):
        """Fallback for unknown language returns []."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_detector = object()
            mock_engine.language_detector = mock_detector
            result = api_module.get_file_extensions("unknown_lang")
            assert result == []

    def test_get_file_extensions_exception_returns_empty_list(self):
        """Exception returns empty list."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_get_engine.side_effect = RuntimeError("fail")
            result = api_module.get_file_extensions("python")
            assert result == []


class TestValidateFile:
    """Tests for validate_file function."""

    def test_validate_file_not_exists(self):
        """File that does not exist returns valid=False."""
        result = api_module.validate_file("/nonexistent/path/file.py")
        assert result["valid"] is False
        assert result["exists"] is False
        assert "File does not exist" in result["errors"]

    def test_validate_file_exists_and_readable(self, tmp_path):
        """Existing readable file gets language and supported check."""
        f = tmp_path / "test.py"
        f.write_text("print(1)")
        with patch("tree_sitter_analyzer.api.detect_language") as mock_detect:
            with patch("tree_sitter_analyzer.api.is_language_supported") as mock_sup:
                mock_detect.return_value = "python"
                mock_sup.return_value = True
                result = api_module.validate_file(str(f))
                assert result["exists"] is True
                assert result["readable"] is True
                assert result["language"] == "python"
                assert result["supported"] is True
                assert result["valid"] is True
                assert result["size"] > 0

    def test_validate_file_language_not_supported(self, tmp_path):
        """Unsupported language adds error."""
        f = tmp_path / "test.xyz"
        f.write_text("x")
        with patch("tree_sitter_analyzer.api.detect_language") as mock_detect:
            with patch("tree_sitter_analyzer.api.is_language_supported") as mock_sup:
                mock_detect.return_value = "xyz"
                mock_sup.return_value = False
                result = api_module.validate_file(str(f))
                assert result["valid"] is False
                assert any("not supported" in e for e in result["errors"])

    def test_validate_file_read_fails(self, tmp_path):
        """Unreadable file adds error when read_file_safe raises."""
        f = tmp_path / "test.py"
        f.write_text("x")
        with patch(
            "tree_sitter_analyzer.encoding_utils.read_file_safe"
        ) as mock_read:
            mock_read.side_effect = PermissionError("denied")
            result = api_module.validate_file(str(f))
            assert result["valid"] is False
            assert result["readable"] is False
            assert any("not readable" in e for e in result["errors"])

    def test_validate_file_accepts_path_object(self, tmp_path):
        """Accepts Path object as file_path."""
        f = tmp_path / "test.py"
        f.write_text("x")
        with patch("tree_sitter_analyzer.api.detect_language") as mock_detect:
            with patch("tree_sitter_analyzer.api.is_language_supported") as mock_sup:
                mock_detect.return_value = "python"
                mock_sup.return_value = True
                result = api_module.validate_file(f)
                assert result["exists"] is True

    def test_validate_file_initial_result_structure(self):
        """Result has expected initial keys."""
        result = api_module.validate_file("/nonexistent")
        assert "valid" in result
        assert "exists" in result
        assert "readable" in result
        assert "language" in result
        assert "supported" in result
        assert "size" in result
        assert "errors" in result


class TestGetFrameworkInfo:
    """Tests for get_framework_info function."""

    def test_get_framework_info_success(self):
        """Returns full framework info dict on success."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.get_supported_languages.return_value = ["python", "java"]
            mock_engine.plugin_manager = MagicMock()
            mock_engine.plugin_manager.get_supported_languages.return_value = [
                "python", "java"
            ]
            result = api_module.get_framework_info()
            assert result["name"] == "tree-sitter-analyzer"
            assert "version" in result
            assert result["supported_languages"] == ["python", "java"]
            assert result["total_languages"] == 2
            assert "plugin_info" in result
            assert result["plugin_info"]["manager_available"] is True
            assert result["plugin_info"]["loaded_plugins"] == 2
            assert "core_components" in result

    def test_get_framework_info_plugin_manager_none(self):
        """Handles plugin_manager being None."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.get_supported_languages.return_value = []
            mock_engine.plugin_manager = None
            result = api_module.get_framework_info()
            assert result["plugin_info"]["manager_available"] is False
            assert result["plugin_info"]["loaded_plugins"] == 0

    def test_get_framework_info_exception_returns_minimal_dict(self):
        """Exception returns minimal dict with error."""
        with patch("tree_sitter_analyzer.api.get_engine") as mock_get_engine:
            mock_get_engine.side_effect = RuntimeError("engine failed")
            result = api_module.get_framework_info()
            assert result["name"] == "tree-sitter-analyzer"
            assert "version" in result
            assert "error" in result
            assert result["error"] == "engine failed"


class TestGetEngine:
    """Tests for get_engine (utility perspective)."""

    def test_get_engine_returns_engine_instance(self):
        """get_engine returns an engine instance."""
        with patch("tree_sitter_analyzer.api.UnifiedAnalysisEngine") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            result = api_module.get_engine()
            assert result is mock_instance


class TestAnalyzeAlias:
    """Tests for analyze() alias function."""

    def test_analyze_calls_analyze_file(self):
        """analyze() delegates to analyze_file."""
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze_file:
            mock_analyze_file.return_value = {"success": True}
            result = api_module.analyze("/test.py")
            mock_analyze_file.assert_called_once_with("/test.py")
            assert result == {"success": True}

    def test_analyze_passes_kwargs(self):
        """analyze() passes kwargs to analyze_file."""
        with patch("tree_sitter_analyzer.api.analyze_file") as mock_analyze_file:
            mock_analyze_file.return_value = {}
            api_module.analyze("/test.py", language="python", include_elements=False)
            mock_analyze_file.assert_called_once_with(
                "/test.py", language="python", include_elements=False
            )
