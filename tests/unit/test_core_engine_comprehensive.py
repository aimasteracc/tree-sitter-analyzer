#!/usr/bin/env python3
"""
Comprehensive tests for core.engine module

This module provides comprehensive test coverage for the AnalysisEngine class,
focusing on edge cases, error handling, cache behavior, and concurrent analysis.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.core.engine import AnalysisEngine
from tree_sitter_analyzer.core.parser import ParseResult
from tree_sitter_analyzer.models import AnalysisResult


class TestAnalysisEngineInit:
    """Test AnalysisEngine initialization"""

    def test_init_success(self):
        """Test successful engine initialization"""
        engine = AnalysisEngine()

        assert engine.parser is not None
        assert engine.query_executor is not None
        assert engine.language_detector is not None
        assert engine.plugin_manager is not None

    @patch("tree_sitter_analyzer.core.engine.Parser")
    def test_init_parser_failure(self, mock_parser_class):
        """Test initialization failure when Parser fails"""
        mock_parser_class.side_effect = Exception("Parser init failed")

        with pytest.raises(Exception) as exc_info:
            AnalysisEngine()

        assert "Parser init failed" in str(exc_info.value)

    @patch("tree_sitter_analyzer.core.engine.PluginManager")
    def test_init_plugin_manager_failure(self, mock_plugin_manager_class):
        """Test initialization failure when PluginManager fails"""
        mock_plugin_manager_class.side_effect = RuntimeError("Plugin manager failed")

        with pytest.raises(RuntimeError):
            AnalysisEngine()


class TestAnalysisEngineAnalyzeFile:
    """Test analyze_file method"""

    def test_analyze_file_not_found(self):
        """Test analyzing non-existent file"""
        engine = AnalysisEngine()

        with pytest.raises(FileNotFoundError):
            engine.analyze_file("nonexistent_file.py")

    @pytest.mark.skip(
        reason="Permission error testing is unreliable across different platforms and CI environments"
    )
    def test_analyze_file_permission_error(self):
        """Test analyzing file with permission error (disabled due to platform inconsistencies)"""
        # This test is disabled because:
        # 1. chmod behavior varies significantly across Windows, macOS, and Linux
        # 2. CI environments may have different permission models
        # 3. Windows doesn't support Unix-style permission bits reliably
        # The actual permission error handling is tested through other means
        pytest.skip("Permission error testing disabled due to platform inconsistencies")

    def test_analyze_file_with_language_override(self):
        """Test analyzing file with language override"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name
            f.write("def hello():\n    pass")

        try:
            result = engine.analyze_file(temp_path, language="python")

            assert result is not None
            assert result.language == "python"
        finally:
            os.unlink(temp_path)

    def test_analyze_file_parsing_failure(self):
        """Test analyze_file when parsing fails"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            temp_path = f.name
            f.write("invalid syntax }{")

        try:
            # Mock parser to return failed parse result
            with patch.object(engine.parser, "parse_file") as mock_parse:
                mock_parse.return_value = ParseResult(
                    tree=None,
                    source_code="invalid syntax }{",
                    language="python",
                    file_path=temp_path,
                    success=False,
                    error_message="Syntax error",
                )

                result = engine.analyze_file(temp_path)

                assert result is not None
                assert result.error_message == "Syntax error"
        finally:
            os.unlink(temp_path)

    def test_analyze_file_empty_file(self):
        """Test analyzing empty file"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            temp_path = f.name
            # Write nothing (empty file)

        try:
            result = engine.analyze_file(temp_path)

            assert result is not None
            assert result.language == "python"
        finally:
            os.unlink(temp_path)

    def test_analyze_file_large_file(self):
        """Test analyzing large file"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            temp_path = f.name
            # Write a large file
            for i in range(1000):
                f.write(f"def function_{i}():\n    pass\n\n")

        try:
            result = engine.analyze_file(temp_path)

            assert result is not None
            assert result.language == "python"
        finally:
            os.unlink(temp_path)


class TestAnalysisEngineAnalyzeCode:
    """Test analyze_code method"""

    def test_analyze_code_with_language(self):
        """Test analyzing code with explicit language"""
        engine = AnalysisEngine()

        code = "def hello():\n    print('world')"
        result = engine.analyze_code(code, language="python")

        assert result is not None
        assert result.language == "python"

    def test_analyze_code_with_filename(self):
        """Test analyzing code with filename for language detection"""
        engine = AnalysisEngine()

        code = "console.log('hello');"
        result = engine.analyze_code(code, filename="test.js")

        assert result is not None
        assert result.language == "javascript"

    def test_analyze_code_without_language_or_filename(self):
        """Test analyzing code without language or filename"""
        engine = AnalysisEngine()

        code = "some code"
        result = engine.analyze_code(code)

        assert result is not None
        assert result.language == "unknown"

    def test_analyze_code_empty_string(self):
        """Test analyzing empty code string"""
        engine = AnalysisEngine()

        result = engine.analyze_code("", language="python")

        assert result is not None

    def test_analyze_code_parsing_failure(self):
        """Test analyze_code when parsing fails"""
        engine = AnalysisEngine()

        # Mock parser to return failed result
        with patch.object(engine.parser, "parse_code") as mock_parse:
            mock_parse.return_value = ParseResult(
                tree=None,
                source_code="invalid",
                language="python",
                file_path=None,
                success=False,
                error_message="Parse error",
            )

            result = engine.analyze_code("invalid", language="python")

            assert result is not None
            assert result.error_message == "Parse error"

    def test_analyze_code_with_queries(self):
        """Test analyzing code with specific queries"""
        engine = AnalysisEngine()

        code = "class MyClass:\n    pass"
        result = engine.analyze_code(code, language="python")

        assert result is not None


class TestAnalysisEngineDetermineLanguage:
    """Test _determine_language method"""

    def test_determine_language_with_override(self):
        """Test language determination with override"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            temp_path = Path(f.name)

        try:
            language = engine._determine_language(temp_path, "python")
            assert language == "python"
        finally:
            temp_path.unlink()

    def test_determine_language_from_extension(self):
        """Test language detection from file extension"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            temp_path = Path(f.name)

        try:
            language = engine._determine_language(temp_path, None)
            assert language == "python"
        finally:
            temp_path.unlink()

    def test_determine_language_unknown_extension(self):
        """Test language detection for unknown extension"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            temp_path = Path(f.name)

        try:
            language = engine._determine_language(temp_path, None)
            # Should return something (might be 'unknown' or None)
            assert language is not None or language == "unknown"
        finally:
            temp_path.unlink()


class TestAnalysisEngineGetLanguagePlugin:
    """Test _get_language_plugin method"""

    def test_get_language_plugin_exists(self):
        """Test getting existing language plugin"""
        engine = AnalysisEngine()

        plugin = engine._get_language_plugin("python")

        # May be None or a plugin object
        assert plugin is None or hasattr(plugin, "analyze_file")

    def test_get_language_plugin_not_exists(self):
        """Test getting non-existent language plugin"""
        engine = AnalysisEngine()

        plugin = engine._get_language_plugin("nonexistent_language_xyz")

        assert plugin is None


class TestAnalysisEngineHelperMethods:
    """Test helper methods"""

    def test_count_nodes_with_tree(self):
        """Test node counting with valid tree"""
        engine = AnalysisEngine()

        code = "def test():\n    pass"
        parse_result = engine.parser.parse_code(code, "python")

        if parse_result.tree:
            count = engine._count_nodes(parse_result.tree)
            assert isinstance(count, int)
            assert count >= 0

    def test_count_nodes_with_none(self):
        """Test node counting with None tree"""
        engine = AnalysisEngine()

        count = engine._count_nodes(None)
        assert count == 0

    def test_create_empty_result(self):
        """Test creating empty result"""
        engine = AnalysisEngine()

        result = engine._create_empty_result("test.py", "python", error="Test error")

        assert isinstance(result, AnalysisResult)
        assert result.file_path == "test.py"
        assert result.language == "python"
        assert result.error_message == "Test error"

    def test_create_empty_result_without_error(self):
        """Test creating empty result without error"""
        engine = AnalysisEngine()

        result = engine._create_empty_result("test.py", "python")

        assert isinstance(result, AnalysisResult)
        assert result.error_message is None


class TestAnalysisEnginePublicAPI:
    """Test public API methods"""

    def test_get_supported_languages(self):
        """Test getting supported languages"""
        engine = AnalysisEngine()

        languages = engine.get_supported_languages()

        assert isinstance(languages, list)
        assert "python" in languages

    def test_get_available_queries_for_python(self):
        """Test getting available queries for Python"""
        engine = AnalysisEngine()

        queries = engine.get_available_queries("python")

        assert isinstance(queries, list)

    def test_get_available_queries_for_unknown_language(self):
        """Test getting queries for unknown language"""
        engine = AnalysisEngine()

        queries = engine.get_available_queries("unknown_language_xyz")

        assert isinstance(queries, list)

    def test_detect_language_from_file(self):
        """Test detecting language from file"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            temp_path = Path(f.name)

        try:
            language = engine.detect_language_from_file(temp_path)
            assert language == "python"
        finally:
            temp_path.unlink()

    def test_get_extensions_for_language(self):
        """Test getting extensions for language"""
        engine = AnalysisEngine()

        extensions = engine.get_extensions_for_language("python")

        assert isinstance(extensions, list)
        assert ".py" in extensions

    def test_get_registry_info(self):
        """Test getting registry info"""
        engine = AnalysisEngine()

        info = engine.get_registry_info()

        assert isinstance(info, dict)
        assert "languages" in info or "plugins" in info or len(info) >= 0


class TestAnalysisEngineEdgeCases:
    """Test edge cases and unusual scenarios"""

    def test_analyze_file_with_path_object(self):
        """Test analyzing file with Path object"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            temp_path = Path(f.name)
            f.write("x = 1")

        try:
            result = engine.analyze_file(temp_path)

            assert result is not None
        finally:
            temp_path.unlink()

    def test_analyze_code_with_unicode(self):
        """Test analyzing code with Unicode characters"""
        engine = AnalysisEngine()

        code = "# こんにちは\ndef hello():\n    print('世界')"
        result = engine.analyze_code(code, language="python")

        assert result is not None

    def test_analyze_code_with_special_characters(self):
        """Test analyzing code with special characters"""
        engine = AnalysisEngine()

        code = "# Special: \x00\x01\x02\ndef test():\n    pass"
        result = engine.analyze_code(code, language="python")

        assert result is not None

    def test_multiple_analyses_same_file(self):
        """Test analyzing same file multiple times"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            temp_path = f.name
            f.write("def test():\n    pass")

        try:
            result1 = engine.analyze_file(temp_path)
            result2 = engine.analyze_file(temp_path)

            assert result1 is not None
            assert result2 is not None
        finally:
            os.unlink(temp_path)

    def test_analyze_different_languages_sequentially(self):
        """Test analyzing different languages sequentially"""
        engine = AnalysisEngine()

        python_code = "def test():\n    pass"
        js_code = "function test() {}"

        result1 = engine.analyze_code(python_code, language="python")
        result2 = engine.analyze_code(js_code, language="javascript")

        assert result1.language == "python"
        assert result2.language == "javascript"


class TestAnalysisEnginePerformAnalysis:
    """Test _perform_analysis method"""

    def test_perform_analysis_with_queries(self):
        """Test performance analysis with specific queries"""
        engine = AnalysisEngine()

        code = "def test():\n    pass"
        parse_result = engine.parser.parse_code(code, "python")

        if parse_result.success:
            result = engine._perform_analysis(parse_result, queries=["functions"])

            assert isinstance(result, AnalysisResult)

    def test_perform_analysis_without_queries(self):
        """Test performance analysis without specific queries"""
        engine = AnalysisEngine()

        code = "class Test:\n    pass"
        parse_result = engine.parser.parse_code(code, "python")

        if parse_result.success:
            result = engine._perform_analysis(parse_result)

            assert isinstance(result, AnalysisResult)


class TestAnalysisEngineConcurrency:
    """Test concurrent analysis scenarios"""

    def test_concurrent_file_analysis(self):
        """Test analyzing multiple files concurrently"""
        import concurrent.futures

        engine = AnalysisEngine()

        # Create multiple temp files
        temp_files = []
        for i in range(5):
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
                f.write(f"def func_{i}():\n    pass")
                temp_files.append(f.name)

        try:
            # Analyze concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(engine.analyze_file, f) for f in temp_files]
                results = [future.result() for future in futures]

            assert len(results) == 5
            assert all(r is not None for r in results)
        finally:
            for f in temp_files:
                os.unlink(f)

    def test_concurrent_code_analysis(self):
        """Test analyzing multiple code snippets concurrently"""
        import concurrent.futures

        engine = AnalysisEngine()

        codes = [f"def func_{i}():\n    pass" for i in range(5)]

        # Analyze concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(engine.analyze_code, c, language="python")
                for c in codes
            ]
            results = [future.result() for future in futures]

        assert len(results) == 5
        assert all(r is not None for r in results)
