#!/usr/bin/env python3
"""
Unit tests for UnifiedAnalysisEngine.

This module provides comprehensive tests for the core analysis engine,
including singleton management, plugin handling, caching, and analysis operations.
"""

import os
import tempfile

import pytest

from tree_sitter_analyzer.core.analysis_engine import (
    MockLanguagePlugin,
    UnifiedAnalysisEngine,
    UnsupportedLanguageError,
    get_analysis_engine,
)
from tree_sitter_analyzer.core.request import AnalysisRequest


class TestUnifiedAnalysisEngineInit:
    """Test cases for UnifiedAnalysisEngine initialization and singleton pattern."""

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
