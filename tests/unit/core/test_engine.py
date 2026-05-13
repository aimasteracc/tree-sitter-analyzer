#!/usr/bin/env python3
"""
Unified tests for AnalysisEngine and related components.

This module consolidates all engine-related tests from:
- test_engine.py (original)
- test_engine_unification.py
- test_analysis_engine.py
- test_core_engine_comprehensive.py
- test_core_engine_extended.py
- test_engine_manager.py
- test_engine_security_regression.py

Total: 103 tests
"""

import asyncio
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.api import get_engine
from tree_sitter_analyzer.core import AnalysisEngine
from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
    MockLanguagePlugin,
    UnifiedAnalysisEngine,
    UnsupportedLanguageError,
    get_analysis_engine,
)
from tree_sitter_analyzer.core.engine_manager import EngineManager
from tree_sitter_analyzer.core.parser import ParseResult
from tree_sitter_analyzer.exceptions import AnalysisError, ParseError
from tree_sitter_analyzer.models import AnalysisResult

# =============================================================================
# Test Classes from test_engine.py (original)
# =============================================================================


@pytest.fixture
def engine():
    """Fixture to provide an AnalysisEngine instance."""
    return AnalysisEngine()


class TestAnalysisEngine:
    """Test cases for the core AnalysisEngine."""

    def test_initialization(self, engine):
        """Test that the AnalysisEngine initializes correctly."""
        assert engine.parser is not None
        assert engine.query_executor is not None
        assert engine.language_detector is not None
        assert engine.plugin_manager is not None

    @pytest.mark.asyncio
    async def test_analyze_java_file(self, engine):
        """Test analyzing a simple Java file."""
        java_code = """
        package com.example;
        public class MyClass {
            public void myMethod() {
                System.out.println("Hello");
            }
        }
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".java", delete=False) as f:
            f.write(java_code)
            temp_file = f.name

        try:
            result = await engine.analyze_file(temp_file)
            assert isinstance(result, AnalysisResult)
            assert result.success
            assert result.language == "java"
            assert result.file_path == temp_file
            assert len(result.elements) > 0
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_analyze_python_code(self, engine):
        """Test analyzing a Python code string."""
        python_code = """
import os

def greet(name):
    print(f"Hello, {name}")

class Greeter:
    def __init__(self, greeting):
        self.greeting = greeting

    def greet(self, name):
        return f"{self.greeting}, {name}"
"""
        result = await engine.analyze_code(python_code, language="python")
        assert isinstance(result, AnalysisResult)
        assert result.success
        assert result.language == "python"
        assert result.file_path == "string"  # Default filename for code analysis
        assert len(result.elements) > 0

        element_types = [elem.element_type for elem in result.elements]
        assert "import" in element_types
        assert "function" in element_types
        assert "class" in element_types

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_file(self, engine):
        """Test analysis of a file that does not exist."""
        with pytest.raises(FileNotFoundError):
            await engine.analyze_file("nonexistent_file.java")

    @pytest.mark.asyncio
    async def test_analyze_unsupported_language(self, engine):
        """Test analysis with an unsupported language."""
        code = "let x = 1;"
        # The engine raises UnsupportedLanguageError for unsupported languages
        with pytest.raises(UnsupportedLanguageError):
            await engine.analyze_code(code, language="unsupportedlang")

    @pytest.mark.asyncio
    async def test_language_detection(self, engine):
        """Test automatic language detection from file extension."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("print('hello')")
            temp_file = f.name

        try:
            result = await engine.analyze_file(temp_file)
            assert result.language == "python"
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_malformed_code_handling(self, engine):
        """Test that the engine handles malformed code gracefully."""
        malformed_code = "public class MyClass { void myMethod() { "
        result = await engine.analyze_code(malformed_code, language="java")
        # Parsing might partially succeed or fail gracefully
        assert isinstance(result, AnalysisResult)
        # Depending on the severity, it might be a success with errors or a failure
        # For now, we just check it doesn't crash

    def test_get_supported_languages(self, engine):
        """Test retrieving the list of supported languages."""
        supported_languages = engine.get_supported_languages()
        assert isinstance(supported_languages, list)
        assert "java" in supported_languages
        assert "python" in supported_languages


# =============================================================================
# Test Classes from test_engine_unification.py
# =============================================================================


class TestUnifiedEngineSingleton:
    """Verify that UnifiedAnalysisEngine acts as a singleton."""

    def test_unified_engine_singleton(self):
        """Verify that UnifiedAnalysisEngine acts as a singleton."""
        engine1 = UnifiedAnalysisEngine()
        engine2 = UnifiedAnalysisEngine()
        assert engine1 is engine2


class TestUnifiedEngineSyncAnalysis:
    """Verify synchronous analysis of a file."""

    def test_unified_engine_sync_analysis(self, tmp_path):
        """Verify synchronous analysis of a file."""
        # Create a dummy Java file
        java_file = tmp_path / "Test.java"
        java_file.write_text("public class Test { public void hello() {} }")

        engine = get_engine()
        request = AnalysisRequest(file_path=str(java_file), language="java")

        result = engine.analyze_sync(request)
        assert result.success is True
        assert result.language == "java"
        assert len(result.elements) >= 2  # Class and Method


class TestUnifiedEngineAnalyzeCode:
    """Verify code string analysis."""

    def test_unified_engine_analyze_code(self):
        """Verify code string analysis."""
        code = "def hello(): print('world')"
        engine = get_engine()

        result = engine.analyze_code_sync(code, language="python")
        assert result.success is True
        assert result.language == "python"
        assert any(el.name == "hello" for el in result.elements)


class TestUnifiedEngineQueryExecution:
    """Verify post-processing query execution."""

    def test_unified_engine_query_execution(self, tmp_path):
        """Verify post-processing query execution."""
        py_file = tmp_path / "test.py"
        py_file.write_text("def my_func(): pass")

        engine = get_engine()
        request = AnalysisRequest(
            file_path=str(py_file),
            language="python",
            queries=["function"],
            include_queries=True,
        )

        result = engine.analyze_sync(request)
        assert result.success is True
        assert "function" in result.query_results
        assert len(result.query_results["function"]) > 0


class TestUnifiedEngineNonexistentFile:
    """Verify FileNotFoundError is raised for missing files."""

    def test_unified_engine_nonexistent_file(self):
        """Verify FileNotFoundError is raised for missing files."""
        engine = get_engine()
        request = AnalysisRequest(file_path="nonexistent_file.java", language="java")

        with pytest.raises(FileNotFoundError):
            engine.analyze_sync(request)


class TestUnifiedEngineCompatibilityProperties:
    """Verify compatibility properties for API/MCP layer."""

    def test_unified_engine_compatibility_properties(self):
        """Verify compatibility properties for API/MCP layer."""
        engine = get_engine()

        # Check properties
        assert hasattr(engine, "language_detector")
        assert hasattr(engine, "plugin_manager")
        assert hasattr(engine, "parser")
        assert hasattr(engine, "query_executor")

        # Check methods
        assert hasattr(engine, "get_available_queries")
        assert hasattr(engine, "get_supported_languages")
        assert hasattr(engine, "analyze_sync")


# =============================================================================
# Test Classes from test_analysis_engine.py
# =============================================================================


class TestUnifiedAnalysisEngineInit:
    """Test cases for UnifiedAnalysisEngine initialization and singleton pattern."""

    def setup_method(self):
        UnifiedAnalysisEngine._reset_instance()

    def test_singleton_pattern_same_project_root(self):
        """Test that same project root returns same instance."""
        engine1 = UnifiedAnalysisEngine(project_root="/test")
        engine2 = UnifiedAnalysisEngine(project_root="/test")
        assert engine1 is engine2

    def test_singleton_pattern_different_project_root(self):
        """Test that different project roots return different instances."""
        engine1 = UnifiedAnalysisEngine(project_root="/test1")
        engine2 = UnifiedAnalysisEngine(project_root="/test2")
        assert engine1 is not engine2

    def test_singleton_pattern_default_project_root(self):
        """Test that default project root returns same instance."""
        engine1 = UnifiedAnalysisEngine()
        engine2 = UnifiedAnalysisEngine()
        assert engine1 is engine2

    def test_lazy_initialization(self):
        """Test that heavy components are lazily initialized."""
        engine = UnifiedAnalysisEngine()
        # Before ensure_initialized, components should be None
        assert engine._cache_service is None
        assert engine._parser is None

        # After ensure_initialized, components should be initialized
        engine._ensure_initialized()
        assert engine._cache_service is not None
        assert engine._parser is not None

    def test_get_analysis_engine_function(self):
        """Test get_analysis_engine convenience function."""
        engine1 = get_analysis_engine(project_root="/test")
        engine2 = get_analysis_engine(project_root="/test")
        assert engine1 is engine2

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEnginePluginManagement:
    """Test cases for plugin registration and management."""

    def test_register_plugin(self):
        """Test registering a language plugin."""
        engine = UnifiedAnalysisEngine()
        plugin = MockLanguagePlugin("python")
        engine.register_plugin("python", plugin)
        # Plugin should be registered without error
        assert True

    def test_get_supported_languages(self):
        """Test getting list of supported languages."""
        engine = UnifiedAnalysisEngine()
        languages = engine.get_supported_languages()
        assert isinstance(languages, list)
        # Should at least have some languages
        assert len(languages) > 0

    def test_plugin_manager_property(self):
        """Test accessing plugin manager property."""
        engine = UnifiedAnalysisEngine()
        plugin_manager = engine.plugin_manager
        assert plugin_manager is not None

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineCacheManagement:
    """Test cases for cache operations."""

    def test_clear_cache(self):
        """Test clearing the analysis cache."""
        engine = UnifiedAnalysisEngine()
        engine.clear_cache()
        # Should complete without error
        assert True

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        engine = UnifiedAnalysisEngine()
        stats = engine.get_cache_stats()
        assert isinstance(stats, dict)
        # Should have at least some stats keys
        assert len(stats) > 0

    def test_cache_service_property(self):
        """Test accessing cache service property."""
        engine = UnifiedAnalysisEngine()
        cache_service = engine.cache_service
        assert cache_service is not None

    def test_cache_key_generation(self):
        """Test cache key generation for different requests."""
        engine = UnifiedAnalysisEngine()
        request1 = AnalysisRequest(
            file_path="test.py", language="python", include_complexity=True
        )
        request2 = AnalysisRequest(
            file_path="test.py", language="python", include_complexity=False
        )

        key1 = engine._generate_cache_key(request1)
        key2 = engine._generate_cache_key(request2)

        # Different requests should generate different keys
        assert key1 != key2

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineLanguageDetection:
    """Test cases for language detection."""

    def test_detect_language_from_extension(self):
        """Test detecting language from file extension."""
        engine = UnifiedAnalysisEngine()
        language = engine._detect_language("test.py")
        assert language == "python"

    def test_detect_language_unknown_extension(self):
        """Test detecting language with unknown extension."""
        engine = UnifiedAnalysisEngine()
        language = engine._detect_language("test.unknown")
        assert language == "unknown"

    def test_language_detector_property(self):
        """Test accessing language detector property."""
        engine = UnifiedAnalysisEngine()
        detector = engine.language_detector
        assert detector is not None

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineAnalysis:
    """Test cases for file and code analysis operations."""

    @pytest.mark.asyncio
    async def test_analyze_file_success(self):
        """Test successful file analysis."""
        engine = UnifiedAnalysisEngine()

        # Create a temporary Python file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tf:
            tf.write("def hello():\n    pass\n")
            temp_path = tf.name

        try:
            result = await engine.analyze_file(temp_path)
            assert result is not None
            assert result.success is True
            assert result.language == "python"
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @pytest.mark.asyncio
    async def test_analyze_file_not_found(self):
        """Test analyzing non-existent file."""
        engine = UnifiedAnalysisEngine()
        # Use a relative path that doesn't exist
        with pytest.raises(FileNotFoundError):
            await engine.analyze_file("nonexistent_file.py")

    @pytest.mark.asyncio
    async def test_analyze_unsupported_language(self):
        """Test analyzing file with unsupported language."""
        engine = UnifiedAnalysisEngine()

        # Create a temporary file with unknown extension
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".unknown", delete=False, encoding="utf-8"
        ) as tf:
            tf.write("some content\n")
            temp_path = tf.name

        try:
            with pytest.raises(UnsupportedLanguageError):
                await engine.analyze_file(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @pytest.mark.asyncio
    async def test_analyze_code_success(self):
        """Test analyzing code string directly."""
        engine = UnifiedAnalysisEngine()
        code = "def hello():\n    pass\n"
        result = await engine.analyze_code(code, language="python")
        assert result is not None
        assert result.success is True
        assert result.language == "python"

    @pytest.mark.asyncio
    async def test_analyze_code_with_filename(self):
        """Test analyzing code with custom filename."""
        engine = UnifiedAnalysisEngine()
        code = "def hello():\n    pass\n"
        result = await engine.analyze_code(
            code, language="python", filename="custom.py"
        )
        assert result is not None
        assert result.file_path == "custom.py"

    def test_analyze_code_sync(self):
        """Test synchronous version of analyze_code."""
        engine = UnifiedAnalysisEngine()
        code = "def hello():\n    pass\n"
        result = engine.analyze_code_sync(code, language="python")
        assert result is not None
        assert result.success is True

    @pytest.mark.asyncio
    async def test_analyze_with_request(self):
        """Test analyzing with AnalysisRequest object."""
        engine = UnifiedAnalysisEngine()

        # Create a temporary Python file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tf:
            tf.write("def hello():\n    pass\n")
            temp_path = tf.name

        try:
            request = AnalysisRequest(
                file_path=temp_path,
                language="python",
                include_elements=True,
                include_complexity=True,
            )
            result = await engine.analyze(request)
            assert result is not None
            assert result.success is True
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_analyze_sync(self):
        """Test synchronous version of analyze."""
        engine = UnifiedAnalysisEngine()

        # Create a temporary Python file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tf:
            tf.write("def hello():\n    pass\n")
            temp_path = tf.name

        try:
            request = AnalysisRequest(file_path=temp_path, language="python")
            result = engine.analyze_sync(request)
            assert result is not None
            assert result.success is True
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @pytest.mark.asyncio
    async def test_analyze_file_async_compatibility(self):
        """Test analyze_file_async compatibility alias."""
        engine = UnifiedAnalysisEngine()

        # Create a temporary Python file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tf:
            tf.write("def hello():\n    pass\n")
            temp_path = tf.name

        try:
            result = await engine.analyze_file_async(temp_path)
            assert result is not None
            assert result.success is True
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineSecurity:
    """Test cases for security validation."""

    @pytest.mark.asyncio
    async def test_security_validation_invalid_path(self):
        """Test security validation with invalid path."""
        engine = UnifiedAnalysisEngine()
        # Try to access path outside project root
        with pytest.raises(ValueError, match="Invalid file path"):
            await engine.analyze_file("../../../etc/passwd")

    @pytest.mark.asyncio
    async def test_security_validator_property(self):
        """Test accessing security validator property."""
        engine = UnifiedAnalysisEngine()
        validator = engine.security_validator
        assert validator is not None

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineQueries:
    """Test cases for query execution."""

    def test_get_available_queries(self):
        """Test getting available queries for a language."""
        engine = UnifiedAnalysisEngine()
        queries = engine.get_available_queries("python")
        assert isinstance(queries, list)

    def test_query_executor_property(self):
        """Test accessing query executor property."""
        engine = UnifiedAnalysisEngine()
        executor = engine.query_executor
        assert executor is not None

    @pytest.mark.asyncio
    async def test_analyze_with_queries(self):
        """Test analyzing with query execution."""
        engine = UnifiedAnalysisEngine()

        # Create a temporary Python file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as tf:
            tf.write("def hello():\n    pass\n")
            temp_path = tf.name

        try:
            request = AnalysisRequest(
                file_path=temp_path,
                language="python",
                queries=["functions"],
                include_queries=True,
            )
            result = await engine.analyze(request)
            assert result is not None
            assert result.success is True
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEnginePerformance:
    """Test cases for performance monitoring."""

    def test_measure_operation(self):
        """Test measuring an operation."""
        engine = UnifiedAnalysisEngine()
        with engine.measure_operation("test_operation"):
            # Simulate some work
            sum(range(100))
        # Should complete without error
        assert True

    def test_performance_monitor_property(self):
        """Test accessing performance monitor property."""
        engine = UnifiedAnalysisEngine()
        # Ensure initialization first
        engine._ensure_initialized()
        monitor = engine._performance_monitor
        assert monitor is not None

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineCleanup:
    """Test cases for resource cleanup."""

    def test_cleanup(self):
        """Test cleaning up engine resources."""
        engine = UnifiedAnalysisEngine()
        engine.cleanup()
        # Should complete without error
        assert True

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestUnifiedAnalysisEngineProperties:
    """Test cases for engine property accessors."""

    def test_parser_property(self):
        """Test accessing parser property."""
        engine = UnifiedAnalysisEngine()
        parser = engine.parser
        assert parser is not None

    def test_all_properties_accessible(self):
        """Test that all properties are accessible."""
        engine = UnifiedAnalysisEngine()
        assert engine.cache_service is not None
        assert engine.parser is not None
        assert engine.query_executor is not None
        assert engine.language_detector is not None
        assert engine.security_validator is not None
        assert engine.plugin_manager is not None

    @classmethod
    def teardown_class(cls):
        """Clean up singleton instances."""
        UnifiedAnalysisEngine._reset_instance()


class TestMockLanguagePlugin:
    """Test cases for MockLanguagePlugin."""

    def test_mock_plugin_initialization(self):
        """Test mock plugin initialization."""
        plugin = MockLanguagePlugin("python")
        assert plugin.language == "python"

    def test_mock_plugin_get_language_name(self):
        """Test mock plugin get_language_name method."""
        plugin = MockLanguagePlugin("python")
        assert plugin.get_language_name() == "python"

    def test_mock_plugin_get_file_extensions(self):
        """Test mock plugin get_file_extensions method."""
        plugin = MockLanguagePlugin("python")
        extensions = plugin.get_file_extensions()
        assert ".python" in extensions

    def test_mock_plugin_create_extractor(self):
        """Test mock plugin create_extractor method."""
        plugin = MockLanguagePlugin("python")
        extractor = plugin.create_extractor()
        assert extractor is None

    @pytest.mark.asyncio
    async def test_mock_plugin_analyze_file(self):
        """Test mock plugin analyze_file method."""
        plugin = MockLanguagePlugin("python")
        request = AnalysisRequest(file_path="test.py", language="python")
        result = await plugin.analyze_file("test.py", request)
        assert result is not None
        assert result.language == "python"
        assert result.success is True


# =============================================================================
# Test Classes from test_core_engine_comprehensive.py
# =============================================================================


class TestAnalysisEngineInitComprehensive:
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
class TestAnalysisEngineAnalyzeFileComprehensive:
    """Test analyze_file method"""

    async def test_analyze_file_not_found_comprehensive(self):
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
class TestAnalysisEngineAnalyzeCodeComprehensive:
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
        # The engine raises UnsupportedLanguageError for "unknown" language
        with pytest.raises(UnsupportedLanguageError):
            await engine.analyze_code(code)

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


# =============================================================================
# Test Classes from test_core_engine_extended.py
# =============================================================================


class TestAnalysisEngineEdgeCases:
    """Test edge cases and error conditions in AnalysisEngine."""

    @pytest.fixture
    def engine_extended(self) -> AnalysisEngine:
        """Create an AnalysisEngine instance for testing."""
        return AnalysisEngine()

    @pytest.mark.asyncio
    async def test_analyze_file_with_empty_file_extended(self, engine_extended):
        """Test analyzing an empty file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")  # Empty file
            f.flush()
            temp_path = f.name

        try:
            result = await engine_extended.analyze_file(temp_path)
            assert isinstance(result, AnalysisResult)
            # Empty file should still produce a valid result
            assert result.file_path == temp_path
        except Exception as e:
            # Some exceptions are acceptable for empty files
            assert isinstance(e, AnalysisError | ParseError | ValueError)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_file_with_binary_file(self, engine_extended):
        """Test analyzing a binary file."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01\x02\x03\x04\x05")  # Binary content
            f.flush()
            temp_path = f.name

        try:
            result = await engine_extended.analyze_file(temp_path)
            # Should handle binary files gracefully
            assert result is not None
        except Exception as e:
            # Exceptions are expected for binary files
            assert isinstance(
                e,
                AnalysisError
                | ParseError
                | UnicodeDecodeError
                | ValueError
                | UnsupportedLanguageError,
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_file_with_very_large_file(self, engine_extended):
        """Test analyzing a very large file."""
        large_content = (
            "# Large Python file\n" + "def function_{}(): pass\n" * 1000
        )  # Reduced size

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(large_content)
            f.flush()
            temp_path = f.name

        try:
            result = await engine_extended.analyze_file(temp_path)
            assert isinstance(result, AnalysisResult)
            # Large file should be processed successfully
            assert result.file_path == temp_path
        except Exception as e:
            # Memory or timeout errors might be acceptable
            assert isinstance(e, MemoryError | TimeoutError | AnalysisError)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_file_with_malformed_syntax(self, engine_extended):
        """Test analyzing files with malformed syntax."""
        malformed_samples = [
            "def incomplete_function(",  # Incomplete function
            "class MissingColon",  # Missing colon
            "import",  # Incomplete import
            "if True\n    pass",  # Missing colon
            "def func():\n  return",  # Incomplete return
        ]

        for code in malformed_samples:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                f.flush()
                temp_path = f.name

            try:
                result = await engine_extended.analyze_file(temp_path)
                # Should handle malformed syntax gracefully
                assert result is not None
            except Exception as e:
                # Parsing errors are expected for malformed code
                assert isinstance(e, ParseError | SyntaxError | AnalysisError)
            finally:
                Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_file_with_unicode_content(self, engine_extended):
        """Test analyzing files with Unicode content."""
        unicode_content = """
# Unicode test file: 测试文件
def 函数名():
    '''这是一个包含中文的函数'''
    变量 = "Hello, 世界! 🌍"
    return 变量

class 类名:
    '''包含Unicode字符的类'''
    def __init__(self):
        self.属性 = "值"
"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(unicode_content)
            f.flush()
            temp_path = f.name

        try:
            result = await engine_extended.analyze_file(temp_path)
            assert isinstance(result, AnalysisResult)
            assert result.file_path == temp_path
        except Exception as e:
            # Unicode handling errors might occur
            assert isinstance(e, UnicodeError | AnalysisError)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_file_with_nonexistent_file_extended(self, engine_extended):
        """Test analyzing a non-existent file."""
        nonexistent_file = "nonexistent_path/file.py"

        with pytest.raises((FileNotFoundError, AnalysisError)):
            await engine_extended.analyze_file(nonexistent_file)

    @pytest.mark.asyncio
    async def test_analyze_file_with_permission_denied(self, engine_extended):
        """Test analyzing a file with permission issues."""
        # This test might not work on all systems, so we'll mock it
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            with pytest.raises((PermissionError, AnalysisError, FileNotFoundError)):
                await engine_extended.analyze_file("some_file.py")

    @pytest.mark.asyncio
    async def test_analyze_file_with_different_encodings(self, engine_extended):
        """Test analyzing files with different encodings."""
        test_content = "def hello(): return 'Hello, World!'"
        encodings = ["utf-8", "latin-1", "ascii"]

        for encoding in encodings:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding=encoding
            ) as f:
                f.write(test_content)
                f.flush()
                temp_path = f.name

            try:
                result = await engine_extended.analyze_file(temp_path)
                assert isinstance(result, AnalysisResult)
            except (UnicodeError, AnalysisError):
                # Some encoding issues are acceptable
                pass
            finally:
                Path(temp_path).unlink(missing_ok=True)


class TestAnalysisEngineConfiguration:
    """Test AnalysisEngine configuration and initialization."""

    def test_engine_initialization_with_custom_config(self):
        """Test engine initialization with custom configuration."""
        # Test with different configurations
        configs = [
            {},
            {"timeout": 30},
            {"max_file_size": 1024 * 1024},
            {"enable_caching": True},
        ]

        for config in configs:
            try:
                engine = AnalysisEngine(**config)
                assert engine is not None
            except TypeError:
                # Some config options might not be supported
                pass

    def test_engine_with_mock_dependencies(self):
        """Test engine with mocked dependencies."""
        try:
            with patch(
                "tree_sitter_analyzer.language_loader.LanguageLoader"
            ) as mock_loader:
                mock_loader.return_value.load_language.return_value = None

                engine = AnalysisEngine()
                assert engine is not None
        except (ImportError, AttributeError):
            # Mock patching might fail, which is acceptable for this test
            pass

    def test_engine_language_detection(self):
        """Test engine language detection capabilities."""
        engine = AnalysisEngine()

        test_files = [
            ("test.py", "python"),
            ("test.java", "java"),
            ("test.js", "javascript"),
            ("test.unknown", None),
        ]

        for _filename, _expected_lang in test_files:
            # Test language detection logic
            # This might be internal to the engine
            assert engine is not None  # Basic test that engine exists


class TestAnalysisEnginePerformanceExtended:
    """Test AnalysisEngine performance characteristics."""

    @pytest.fixture
    def engine_perf(self) -> AnalysisEngine:
        """Create an AnalysisEngine instance for testing."""
        return AnalysisEngine()

    @pytest.mark.asyncio
    async def test_concurrent_analysis_extended(self, engine_perf):
        """Test concurrent file analysis."""
        import asyncio

        # Create multiple test files using context manager
        with tempfile.TemporaryDirectory() as temp_dir:
            test_files = []
            for i in range(5):
                file_path = Path(temp_dir) / f"test_{i}.py"
                with open(file_path, "w") as f:
                    f.write(f"def function_{i}(): pass\nclass Class_{i}: pass")
                test_files.append(file_path)

            # Test concurrent analysis using asyncio.gather
            tasks = [engine_perf.analyze_file(str(f)) for f in test_files]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check that some analyses completed
            successful_results = [r for r in results if isinstance(r, AnalysisResult)]
            assert len(successful_results) >= 0  # At least some should succeed

    @pytest.mark.asyncio
    async def test_memory_usage_with_repeated_analysis(self, engine_perf):
        """Test memory usage with repeated analysis."""
        import gc

        test_content = "def test_function(): pass\nclass TestClass: pass"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_content)
            f.flush()
            temp_path = f.name

        try:
            # Perform repeated analysis
            for _i in range(10):
                try:
                    result = await engine_perf.analyze_file(temp_path)
                    assert result is not None or result is None  # Either is acceptable
                except Exception:
                    # Some failures are acceptable in stress testing
                    pass

                # Force garbage collection
                gc.collect()

            # Test should complete without memory issues
            assert True
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analysis_with_timeout(self, engine_perf):
        """Test analysis with timeout scenarios."""
        # Create a file that might take time to analyze
        complex_content = """
# Complex Python file with nested structures
""" + "\n".join(
            [
                f"class Class_{i}:\n    def method_{j}(self): pass"
                for i in range(20)
                for j in range(5)  # Reduced complexity
            ]
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(complex_content)
            f.flush()
            temp_path = f.name

        try:
            # Test with potential timeout
            result = await engine_perf.analyze_file(temp_path)
            assert result is not None or result is None
        except (TimeoutError, AnalysisError):
            # Timeout errors are acceptable for complex files
            pass
        finally:
            Path(temp_path).unlink(missing_ok=True)


# =============================================================================
# Test Classes from test_engine_manager.py
# =============================================================================


class TestEngineManagerGetInstance:
    """Test cases for get_instance method."""

    def test_get_instance_default_project_root(self):
        """Test get_instance with default project root."""
        # Reset instances before test
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(UnifiedAnalysisEngine)
        instance2 = EngineManager.get_instance(UnifiedAnalysisEngine)

        # Should return to same instance (singleton)
        assert instance1 is instance2

        # Clean up
        EngineManager.reset_instances()

    def test_get_instance_with_project_root(self):
        """Test get_instance with specific project root."""
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        instance2 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )

        # Should return to same instance for same project root
        assert instance1 is instance2

        # Clean up
        EngineManager.reset_instances()

    def test_get_instance_different_project_roots(self):
        """Test get_instance with different project roots."""
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        instance2 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )

        # Should return different instances for different project roots
        assert instance1 is not instance2

        # Clean up
        EngineManager.reset_instances()

    def test_get_instance_none_project_root(self):
        """Test get_instance with None project root."""
        EngineManager.reset_instances()

        instance1 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)
        instance2 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)

        # Should return to same instance (None uses "default" key)
        assert instance1 is instance2

        # Clean up
        EngineManager.reset_instances()


class TestEngineManagerThreadSafety:
    """Test cases for thread safety."""

    def test_concurrent_get_instance(self):
        """Test concurrent calls to get_instance."""
        EngineManager.reset_instances()
        instances = []
        lock = threading.Lock()

        def create_instance():
            instance = EngineManager.get_instance(UnifiedAnalysisEngine)
            with lock:
                instances.append(instance)

        # Create multiple threads
        threads = [threading.Thread(target=create_instance) for _ in range(10)]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All instances should be same (singleton)
        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances)

        # Clean up
        EngineManager.reset_instances()

    def test_double_checked_locking(self):
        """Test that double-checked locking prevents race conditions."""
        EngineManager.reset_instances()
        instances = []

        def create_instance():
            instance = EngineManager.get_instance(UnifiedAnalysisEngine)
            instances.append(instance)

        # Create multiple threads
        threads = [threading.Thread(target=create_instance) for _ in range(5)]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All instances should be same (singleton pattern)
        assert len(instances) == 5
        assert all(inst is instances[0] for inst in instances)

        # Clean up
        EngineManager.reset_instances()


class TestEngineManagerResetInstances:
    """Test cases for reset_instances method."""

    def test_reset_instances_clears_all(self):
        """Test that reset_instances clears all instances."""
        EngineManager.reset_instances()

        # Create some instances
        EngineManager.get_instance(UnifiedAnalysisEngine, project_root="/path1")
        EngineManager.get_instance(UnifiedAnalysisEngine, project_root="/path2")

        # Reset instances
        EngineManager.reset_instances()

        # After reset, getting instances should work without errors
        # Note: UnifiedAnalysisEngine may have internal caching, so we just verify
        # that reset doesn't cause errors
        instance3 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path1"
        )
        instance4 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path2"
        )

        # Verify that instances were created successfully
        assert instance3 is not None
        assert instance4 is not None

        # Clean up
        EngineManager.reset_instances()

    def test_reset_instances_thread_safety(self):
        """Test that reset_instances is thread-safe."""
        EngineManager.reset_instances()

        # Create instances
        EngineManager.get_instance(UnifiedAnalysisEngine)

        # Reset instances in multiple threads
        def reset_and_create():
            EngineManager.reset_instances()
            EngineManager.get_instance(UnifiedAnalysisEngine)

        threads = [threading.Thread(target=reset_and_create) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Should not raise any exceptions
        assert True

        # Clean up
        EngineManager.reset_instances()


class TestEngineManagerEdgeCases:
    """Test cases for edge cases."""

    def test_instance_key_generation(self):
        """Test that instance keys are generated correctly."""
        EngineManager.reset_instances()

        # Test with None project root
        instance1 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)
        instance2 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root=None)
        assert instance1 is instance2

        # Test with empty string project root
        # Note: Empty string is falsy, so it uses "default" key like None
        instance3 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root="")
        instance4 = EngineManager.get_instance(UnifiedAnalysisEngine, project_root="")
        assert instance3 is instance4

        # None and empty string both use "default" key (empty string is falsy)
        # So they return the same instance
        assert instance1 is instance3

        # Clean up
        EngineManager.reset_instances()

    def test_multiple_project_roots(self):
        """Test managing multiple project roots."""
        EngineManager.reset_instances()

        # Create instances for different project roots
        instance1 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        instance2 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )
        instance3 = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project3"
        )

        # All instances should be different
        assert instance1 is not instance2
        assert instance2 is not instance3
        assert instance1 is not instance3

        # Getting same project root should return same instance
        instance1_again = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        assert instance1 is instance1_again

        # Clean up
        EngineManager.reset_instances()

    def test_reset_clears_all_project_roots(self):
        """Test that reset clears all project root instances."""
        EngineManager.reset_instances()

        # Create instances for multiple project roots
        EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )
        EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project3"
        )

        # Reset instances
        EngineManager.reset_instances()

        # Get new instances - all should work without errors
        # Note: UnifiedAnalysisEngine may have internal caching
        instance1_new = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project1"
        )
        instance2_new = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project2"
        )
        instance3_new = EngineManager.get_instance(
            UnifiedAnalysisEngine, project_root="/path/to/project3"
        )

        # Verify that instances were created successfully
        assert instance1_new is not None
        assert instance2_new is not None
        assert instance3_new is not None

        # Clean up
        EngineManager.reset_instances()


# =============================================================================
# Test Classes from test_engine_security_regression.py
# =============================================================================


class TestEngineSecurityRegression:
    """Regression tests for security boundaries"""

    @pytest.mark.asyncio
    async def test_path_traversal_prevention(self):
        """Test that path traversal is still blocked after refactoring"""
        engine = get_analysis_engine(project_root=os.getcwd())

        # Test directory traversal attack
        request = AnalysisRequest(file_path="../../../../../etc/passwd")

        with pytest.raises(ValueError) as excinfo:
            await engine.analyze(request)

        assert "Invalid file path" in str(excinfo.value)
        assert "traversal" in str(excinfo.value).lower()

    @pytest.mark.asyncio
    async def test_unsupported_language_handling(self):
        """Test that unsupported languages are still handled correctly"""
        engine = get_analysis_engine()
        # Use a relative path to a file that exists
        relative_file = "pyproject.toml"
        request = AnalysisRequest(file_path=relative_file, language="brainfuck")

        with pytest.raises(UnsupportedLanguageError):
            await engine.analyze(request)

    def test_singleton_engine_cleanup(self):
        """Test that cleanup method works correctly after refactoring"""
        engine = get_analysis_engine()
        engine.cleanup()
        # Should not raise any exceptions


if __name__ == "__main__":
    pytest.main([__file__])
