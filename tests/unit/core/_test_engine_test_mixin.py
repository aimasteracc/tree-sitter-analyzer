#!/usr/bin/env python3
"""Shared mixins for oversized core analysis test file."""

import os
import tempfile

import pytest

from tree_sitter_analyzer.core.analysis_engine import (
    AnalysisRequest,
    MockLanguagePlugin,
    UnifiedAnalysisEngine,
    UnsupportedLanguageError,
)
from tree_sitter_analyzer.models import AnalysisResult


class TestAnalysisEngineTestMixin:
    """Shared tests for core `AnalysisEngine` initialization and file/code APIs."""

    __test__ = False

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


class TestUnifiedAnalysisEngineInitTestMixin:
    """Shared tests for `UnifiedAnalysisEngine` initialization lifecycle."""

    __test__ = False

    def test_singleton_pattern_same_project_root(self):
        """Test that same project root returns same instance."""
        from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine

        engine1 = get_analysis_engine(project_root="/test")
        engine2 = get_analysis_engine(project_root="/test")
        assert engine1 is engine2

    def test_singleton_pattern_different_project_root(self):
        """Test that different project roots return different instances."""
        from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine

        engine1 = get_analysis_engine(project_root="/test1")
        engine2 = get_analysis_engine(project_root="/test2")
        assert engine1 is not engine2

    def test_singleton_pattern_default_project_root(self):
        """Test that default project root returns same instance."""
        from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine

        engine1 = get_analysis_engine()
        engine2 = get_analysis_engine()
        assert engine1 is engine2

    def test_lazy_initialization(self):
        """Test that heavy components are lazily initialized."""
        from tree_sitter_analyzer.core.analysis_engine import UnifiedAnalysisEngine

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
        from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine

        engine1 = get_analysis_engine(project_root="/test")
        engine2 = get_analysis_engine(project_root="/test")
        assert engine1 is engine2


class TestUnifiedAnalysisEnginePluginManagementTestMixin:
    """Shared tests for `UnifiedAnalysisEngine` plugin management."""

    __test__ = False

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


class TestUnifiedAnalysisEngineCacheManagementTestMixin:
    """Shared tests for `UnifiedAnalysisEngine` cache management."""

    __test__ = False

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


class TestUnifiedAnalysisEngineLanguageDetectionTestMixin:
    """Shared tests for language detection behavior."""

    __test__ = False

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
