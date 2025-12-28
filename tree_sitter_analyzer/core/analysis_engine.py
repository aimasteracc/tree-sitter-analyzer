#!/usr/bin/env python3
"""
Unified Analysis Engine - Common Analysis System for CLI and MCP (Fixed Version)

This module provides a unified engine that serves as the center of all analysis processing.
It is commonly used by CLI, MCP, and other interfaces.

Roo Code compliance:
- Type hints: Required for all functions
- MCP logging: Log output at each step
- docstring: Google Style docstring
- Performance-focused: Singleton pattern and cache sharing
"""

import asyncio
import hashlib
import os
from typing import Any, Protocol

from ..language_detector import LanguageDetector
from ..models import AnalysisResult
from ..plugins.manager import PluginManager
from ..security import SecurityValidator
from ..utils import log_debug, log_error, log_info
from .cache_service import CacheService
from .engine_manager import EngineManager
from .parser import Parser
from .performance import PerformanceContext, PerformanceMonitor
from .query import QueryExecutor
from .request import AnalysisRequest  # Re-export for backward compatibility


class UnsupportedLanguageError(Exception):
    """Unsupported language error"""

    pass


class LanguagePlugin(Protocol):
    """Language plugin protocol"""

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """File analysis"""
        ...


class UnifiedAnalysisEngine:
    """
    Unified analysis engine

    Central engine shared by CLI, MCP and other interfaces.
    """

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the engine"""
        # Use a private flag to ensure init only runs once
        if hasattr(self, "_initialized") and self._initialized:
            return

        from ..language_detector import LanguageDetector

        self._cache_service = CacheService()
        self._plugin_manager = PluginManager()
        self._performance_monitor = PerformanceMonitor()
        self._language_detector = LanguageDetector()
        self._security_validator = SecurityValidator(project_root)
        self._parser = Parser()
        self._query_executor = QueryExecutor()
        self._project_root = project_root

        # Auto-load plugins
        self._load_plugins()
        self._initialized = True

    def register_plugin(self, language: str, plugin: Any) -> None:
        """Register a plugin (compatibility method)"""
        self._plugin_manager.register_plugin(plugin)

    def _load_plugins(self) -> None:
        """Auto-load available plugins"""
        log_debug("Loading plugins using PluginManager...")
        try:
            loaded_plugins = self._plugin_manager.load_plugins()
            final_languages = [plugin.get_language_name() for plugin in loaded_plugins]
            log_debug(
                f"Successfully loaded {len(final_languages)} plugins: {', '.join(final_languages)}"
            )
        except Exception as e:
            log_error(f"Failed to load plugins: {e}")

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Unified analysis method (Async)"""
        log_debug(f"Starting async analysis for {request.file_path}")

        # Security validation
        is_valid, error_msg = self._security_validator.validate_file_path(
            request.file_path
        )
        if not is_valid:
            log_error(f"Security validation failed: {request.file_path} - {error_msg}")
            raise ValueError(f"Invalid file path: {error_msg}")

        # Cache check
        cache_key = self._generate_cache_key(request)
        cached_result = await self._cache_service.get(cache_key)
        if cached_result:
            log_info(f"Cache hit for {request.file_path}")
            return cached_result  # type: ignore

        if not os.path.exists(request.file_path):
            raise FileNotFoundError(f"File not found: {request.file_path}")

        language = request.language or self._detect_language(request.file_path)
        if not self.language_detector.is_supported(language):
            raise UnsupportedLanguageError(f"Unsupported language: {language}")

        parse_result = self._parser.parse_file(request.file_path, language)
        if not parse_result.success:
            return self._create_empty_result(
                request.file_path, language, parse_result.error_message
            )

        plugin = self._plugin_manager.get_plugin(language)
        if not plugin:
            raise UnsupportedLanguageError(f"Plugin not found for language: {language}")

        with self._performance_monitor.measure_operation(f"analyze_{language}"):
            result = await plugin.analyze_file(request.file_path, request)

        if not result.language:
            result.language = language

        # Execute queries if requested
        if request.queries and request.include_queries:
            await self._run_queries(request, result, plugin, language)

        await self._cache_service.set(cache_key, result)
        return result

    async def _run_queries(self, request, result, plugin, language):
        """Helper to run queries"""
        try:
            parse_result = self._parser.parse_file(request.file_path, language)
            if parse_result.success and parse_result.tree:
                ts_language = getattr(
                    plugin, "get_tree_sitter_language", lambda: None
                )()
                if ts_language:
                    query_results = {}
                    for query_name in request.queries:
                        q_res = self._query_executor.execute_query_with_language_name(
                            parse_result.tree,
                            ts_language,
                            query_name,
                            parse_result.source_code,
                            language,
                        )
                        query_results[query_name] = (
                            q_res["captures"]
                            if isinstance(q_res, dict) and "captures" in q_res
                            else q_res
                        )
                    result.query_results = query_results
        except Exception as e:
            log_error(f"Failed to execute queries: {e}")

    def _generate_cache_key(self, request: AnalysisRequest) -> str:
        """Generate cache key"""
        key_components = [
            request.file_path,
            str(request.language),
            str(request.include_complexity),
            request.format_type,
        ]
        if os.path.exists(request.file_path):
            stat = os.stat(request.file_path)
            key_components.extend([str(int(stat.st_mtime)), str(stat.st_size)])
        return hashlib.sha256(":".join(key_components).encode("utf-8")).hexdigest()

    def _detect_language(self, file_path: str) -> str:
        """Detect language"""
        try:
            return self._language_detector.detect_from_extension(file_path)
        except Exception:
            return "unknown"

    def _create_empty_result(
        self, file_path: str, language: str, error: str | None = None
    ) -> AnalysisResult:
        """Create empty result on failure"""
        return AnalysisResult(
            file_path=file_path,
            language=language,
            success=False,
            error_message=error,
            elements=[],
            analysis_time=0.0,
        )

    def cleanup(self) -> None:
        """Resource cleanup"""
        self._cache_service.clear()
        self._performance_monitor.clear_metrics()
        log_debug("UnifiedAnalysisEngine cleaned up")

    # Compatibility methods
    def analyze_sync(self, request: AnalysisRequest) -> AnalysisResult:
        return asyncio.run(self.analyze(request))

    def get_supported_languages(self) -> list[str]:
        return self._plugin_manager.get_supported_languages()

    @property
    def language_detector(self) -> LanguageDetector:
        return self._language_detector

    def measure_operation(self, operation_name: str) -> PerformanceContext:
        """Measure an operation using the performance monitor"""
        return self._performance_monitor.measure_operation(operation_name)

    @classmethod
    def _reset_instance(cls) -> None:
        """Compatibility method for resetting instances"""
        EngineManager.reset_instances()


# Simple plugin implementation (for testing) - Re-added for backward compatibility with existing tests
class MockLanguagePlugin:
    """Mock plugin for testing"""

    def __init__(self, language: str) -> None:
        self.language = language

    def get_language_name(self) -> str:
        """Get language name"""
        return self.language

    def get_file_extensions(self) -> list[str]:
        """Get supported file extensions"""
        return [f".{self.language}"]

    def create_extractor(self) -> None:
        """Create extractor (mock)"""
        return None

    async def analyze_file(
        self, file_path: str, request: AnalysisRequest
    ) -> AnalysisResult:
        """Mock analysis implementation"""
        log_info(f"Mock analysis for {file_path} ({self.language})")

        # Return simple analysis result
        return AnalysisResult(
            file_path=file_path,
            line_count=10,
            elements=[],
            node_count=5,
            query_results={},
            source_code="// Mock source code",
            language=self.language,
            package=None,
            analysis_time=0.1,
            success=True,
            error_message=None,
        )


def get_analysis_engine(project_root: str | None = None) -> UnifiedAnalysisEngine:
    return EngineManager.get_instance(UnifiedAnalysisEngine, project_root)
