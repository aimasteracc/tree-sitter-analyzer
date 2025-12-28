#!/usr/bin/env python3
"""
Comprehensive tests for core.engine module (Fixed for Async and Unified Engine)

This module provides comprehensive test coverage for the AnalysisEngine class,
focusing on edge cases, error handling, cache behavior, and concurrent analysis.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.core import AnalysisEngine
from tree_sitter_analyzer.core.parser import ParseResult
from tree_sitter_analyzer.models import AnalysisResult


class TestAnalysisEngineInit:
    """Test AnalysisEngine initialization"""

    @patch(
        "tree_sitter_analyzer.core.analysis_engine.UnifiedAnalysisEngine._load_plugins"
    )
    def test_init_success(self, _):
        """Test successful engine initialization"""
        engine = AnalysisEngine()

        # Components are lazily initialized, so we need to access them to trigger init
        assert engine.parser is not None
        assert engine.query_executor is not None
        assert engine.language_detector is not None
        assert engine.plugin_manager is not None

    @patch("tree_sitter_analyzer.core.parser.Parser")
    def test_init_parser_failure(self, mock_parser_class):
        """Test initialization failure when Parser fails"""
        mock_parser_class.side_effect = Exception("Parser init failed")

        # Reset instances to force re-initialization
        AnalysisEngine._reset_instance()
        engine = AnalysisEngine()

        with pytest.raises(Exception) as exc_info:
            # Trigger lazy initialization
            _ = engine.parser

        assert "Parser init failed" in str(exc_info.value)

    @patch("tree_sitter_analyzer.plugins.manager.PluginManager")
    def test_init_plugin_manager_failure(self, mock_plugin_manager_class):
        """Test initialization failure when PluginManager fails"""
        mock_plugin_manager_class.side_effect = RuntimeError("Plugin manager failed")

        # Reset instances to force re-initialization
        AnalysisEngine._reset_instance()

        # In UnifiedAnalysisEngine._load_plugins, if PluginManager() call fails,
        # it will propagate up during __init__.
        with pytest.raises(RuntimeError) as exc_info:
            AnalysisEngine()

        assert "Plugin manager failed" in str(exc_info.value)


@pytest.mark.asyncio
class TestAnalysisEngineAnalyzeFile:
    """Test analyze_file method"""

    async def test_analyze_file_not_found(self):
        """Test analyzing non-existent file"""
        engine = AnalysisEngine()

        # The engine checks file existence before analysis
        with pytest.raises(FileNotFoundError):
            await engine.analyze_file("nonexistent_file.py")

    @pytest.mark.skip(
        reason="Permission error testing is unreliable across different platforms and CI environments"
    )
    async def test_analyze_file_permission_error(self):
        """Test analyzing file with permission error (disabled due to platform inconsistencies)"""
        pytest.skip("Permission error testing disabled due to platform inconsistencies")

    async def test_analyze_file_with_language_override(self):
        """Test analyzing file with language override"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            temp_path = f.name
            f.write("def hello():\n    pass")

        try:
            result = await engine.analyze_file(temp_path, language="python")

            assert result is not None
            assert result.language == "python"
        finally:
            os.unlink(temp_path)

    async def test_analyze_file_parsing_failure(self):
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

                result = await engine.analyze_file(temp_path)

                assert result is not None
                assert result.error_message == "Syntax error"
        finally:
            os.unlink(temp_path)

    async def test_analyze_file_empty_file(self):
        """Test analyzing empty file"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            temp_path = f.name
            # Write nothing (empty file)

        try:
            result = await engine.analyze_file(temp_path)

            assert result is not None
            assert result.language == "python"
        finally:
            os.unlink(temp_path)

    async def test_analyze_file_large_file(self):
        """Test analyzing large file"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
            temp_path = f.name
            # Write a large file
            for i in range(1000):
                f.write(f"def function_{i}():\n    pass\n\n")

        try:
            result = await engine.analyze_file(temp_path)

            assert result is not None
            assert result.language == "python"
        finally:
            os.unlink(temp_path)


@pytest.mark.asyncio
class TestAnalysisEngineAnalyzeCode:
    """Test analyze_code method"""

    async def test_analyze_code_with_language(self):
        """Test analyzing code with explicit language"""
        engine = AnalysisEngine()

        code = "def hello():\n    print('world')"
        result = await engine.analyze_code(code, language="python")

        assert result is not None
        assert result.language == "python"

    async def test_analyze_code_with_filename(self):
        """Test analyzing code with filename for language detection"""
        engine = AnalysisEngine()

        # Note: UnifiedAnalysisEngine.analyze_code requires language if it can't detect it perfectly from filename in some modes,
        # but here we test its ability to handle it.
        code = "console.log('hello');"
        # We need to provide language or ensure it can be detected.
        # In current implementation, analyze_code defaults language to "unknown" if not provided.
        result = await engine.analyze_code(
            code, filename="test.js", language="javascript"
        )

        assert result is not None
        assert result.language == "javascript"

    async def test_analyze_code_without_language_or_filename(self):
        """Test analyzing code without language or filename"""
        engine = AnalysisEngine()

        code = "some code"
        result = await engine.analyze_code(code)

        assert result is not None
        # It should default to "unknown" as per implementation
        assert result.language == "unknown"

    async def test_analyze_code_empty_string(self):
        """Test analyzing empty code string"""
        engine = AnalysisEngine()

        result = await engine.analyze_code("", language="python")

        assert result is not None

    async def test_analyze_code_parsing_failure(self):
        """Test analyze_code when parsing fails"""
        engine = AnalysisEngine()

        # Mock parser to return failed result
        with patch.object(engine.parser, "parse_file") as mock_parse:
            mock_parse.return_value = ParseResult(
                tree=None,
                source_code="invalid",
                language="python",
                file_path=None,
                success=False,
                error_message="Parse error",
            )

            result = await engine.analyze_code("invalid", language="python")

            assert result is not None
            assert result.error_message == "Parse error"

    async def test_analyze_code_with_queries(self):
        """Test analyzing code with specific queries"""
        engine = AnalysisEngine()

        code = "class MyClass:\n    pass"
        result = await engine.analyze_code(code, language="python")

        assert result is not None


class TestAnalysisEngineDetermineLanguage:
    """Test _determine_language method"""

    def test_determine_language_from_extension(self):
        """Test language detection from file extension"""
        engine = AnalysisEngine()

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            temp_path = Path(f.name)

        try:
            # UnifiedAnalysisEngine uses _detect_language (private)
            language = engine._detect_language(str(temp_path))
            assert language == "python"
        finally:
            temp_path.unlink()


class TestAnalysisEngineHelperMethods:
    """Test helper methods"""

    def test_create_empty_result(self):
        """Test creating empty result"""
        engine = AnalysisEngine()

        result = engine._create_empty_result("test.py", "python", error="Test error")

        assert isinstance(result, AnalysisResult)
        assert result.file_path == "test.py"
        assert result.language == "python"
        assert result.error_message == "Test error"


@pytest.mark.asyncio
class TestAnalysisEnginePublicAPI:
    """Test public API methods"""

    async def test_get_supported_languages(self):
        """Test getting supported languages"""
        engine = AnalysisEngine()

        languages = engine.get_supported_languages()

        assert isinstance(languages, list)
        assert "python" in languages

    async def test_get_available_queries_for_python(self):
        """Test getting available queries for Python"""
        engine = AnalysisEngine()

        queries = engine.get_available_queries("python")

        assert isinstance(queries, list)


@pytest.mark.asyncio
class TestAnalysisEngineConcurrency:
    """Test concurrent analysis scenarios"""

    async def test_concurrent_file_analysis(self):
        """Test analyzing multiple files concurrently"""
        engine = AnalysisEngine()

        # Create multiple temp files
        temp_files = []
        for i in range(5):
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".py") as f:
                f.write(f"def func_{i}():\n    pass")
                temp_files.append(f.name)

        try:
            # Analyze concurrently using asyncio.gather
            tasks = [engine.analyze_file(f) for f in temp_files]
            results = await asyncio.gather(*tasks)

            assert len(results) == 5
            assert all(r is not None for r in results)
        finally:
            for f in temp_files:
                os.unlink(f)

    async def test_concurrent_code_analysis(self):
        """Test analyzing multiple code snippets concurrently"""
        engine = AnalysisEngine()

        codes = [f"def func_{i}():\n    pass" for i in range(5)]

        # Analyze concurrently using asyncio.gather
        tasks = [engine.analyze_code(c, language="python") for c in codes]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert all(r is not None for r in results)
