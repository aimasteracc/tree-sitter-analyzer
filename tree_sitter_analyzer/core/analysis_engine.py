#!/usr/bin/env python3
"""
Unified Analysis Engine - Common Analysis System for CLI and MCP (Fixed & Optimized)

This module provides a unified engine that serves as the center of all analysis processing.
It is commonly used by CLI, MCP, and other interfaces.
"""

import asyncio
import hashlib
import os
import threading
from typing import Any, Protocol

from ..models import AnalysisResult
from .engine_manager import EngineManager
from .performance import PerformanceContext, PerformanceMonitor
from .request import AnalysisRequest


class UnsupportedLanguageError(Exception):
    """Unsupported language error"""

    pass


class LanguagePlugin(Protocol):
    """Language plugin protocol"""

    async def analyze_file(self, file_path: str, request: AnalysisRequest) -> Any:
        """File analysis"""
        ...


class UnifiedAnalysisEngine:
    """
    Unified analysis engine

    Central engine shared by CLI, MCP and other interfaces.
    """

    _instances: dict[str, "UnifiedAnalysisEngine"] = {}
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, project_root: str | None = None) -> "UnifiedAnalysisEngine":
        """Singleton instance management (backward compatible)"""
        instance_key = project_root or "default"
        if instance_key not in cls._instances:
            with cls._lock:
                if instance_key not in cls._instances:
                    instance = super().__new__(cls)
                    cls._instances[instance_key] = instance
                    instance._initialized = False
        return cls._instances[instance_key]

    def __init__(self, project_root: str | None = None) -> None:
        """Initialize the engine"""
        if getattr(self, "_initialized", False):
            return

        # Lazy init attributes
        self._cache_service: Any = None
        self._plugin_manager: Any = None
        self._performance_monitor: Any = None
        self._language_detector: Any = None
        self._security_validator: Any = None
        self._parser: Any = None
        self._query_executor: Any = None
        self._project_root = project_root

        # Initial discovery only (no heavy loading)
        self._load_plugins()
        self._initialized = True

    def _ensure_initialized(self) -> None:
        """Ensure all components are lazily initialized only when needed"""
        if self._cache_service is not None and self._parser is not None:
            return

        # Perform heavy imports only once
        from ..language_detector import LanguageDetector
        from ..plugins.manager import PluginManager
        from ..security import SecurityValidator
        from .cache_service import CacheService
        from .parser import Parser
        from .query import QueryExecutor

        self._cache_service = CacheService()
        self._plugin_manager = PluginManager()
        self._performance_monitor = PerformanceMonitor()
        self._language_detector = LanguageDetector()
        self._security_validator = SecurityValidator(self._project_root)
        self._parser = Parser()
        self._query_executor = QueryExecutor()

    def register_plugin(self, language: str, plugin: Any) -> None:
        """Register a plugin (compatibility method)"""
        self._ensure_initialized()
        self._plugin_manager.register_plugin(plugin)

    def clear_cache(self) -> None:
        """Clear the analysis cache (compatibility method)"""
        self._ensure_initialized()
        if self._cache_service:
            self._cache_service.clear()

    def _load_plugins(self) -> None:
        """Discover available plugins (fast metadata scan)"""
        from ..utils import log_debug, log_error

        # Minimal init for discovery
        if self._plugin_manager is None:
            from ..plugins.manager import PluginManager

            self._plugin_manager = PluginManager()

        log_debug("Discovering plugins using PluginManager...")
        try:
            self._plugin_manager.load_plugins()
        except Exception as e:
            log_error(f"Failed to discover plugins: {e}")

    async def analyze(self, request: AnalysisRequest) -> Any:
        """Unified analysis method (Async)"""
        self._ensure_initialized()
        from ..utils import log_debug, log_error, log_info

        log_debug(f"Starting async analysis for {request.file_path}")

        # Security validation
        is_valid, error_msg = self._security_validator.validate_file_path(
            request.file_path
        )
        if not is_valid:
            log_error(f"Security validation failed: {request.file_path} - {error_msg}")
            raise ValueError(f"Invalid file path: {error_msg}")

        # Language detection
        language = request.language or self._detect_language(request.file_path)
        if language == "unknown":
            # For "unknown" language, we strictly raise error now to match test expectations
            raise UnsupportedLanguageError(f"Unsupported language: {language}")
        elif not self._language_detector.is_supported(language):
            raise UnsupportedLanguageError(f"Unsupported language: {language}")

        # Cache check
        cache_key = self._generate_cache_key(request)
        cached_result = await self._cache_service.get(cache_key)
        if cached_result:
            log_info(f"Cache hit for {request.file_path}")
            return cached_result

        # File existence check
        if not os.path.exists(request.file_path):
            raise FileNotFoundError(f"File not found: {request.file_path}")

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

    async def analyze_file(
        self,
        file_path: str,
        language: str | None = None,
        request: AnalysisRequest | None = None,
        format_type: str | None = None,
        include_details: bool | None = None,
        include_complexity: bool | None = None,
        include_elements: bool | None = None,
        include_queries: bool | None = None,
        queries: list[str] | None = None,
    ) -> Any:
        """Compatibility alias for analyze with additional parameters

        Args:
            file_path: Path to the file to analyze
            language: Programming language (auto-detected if None)
            request: Pre-built AnalysisRequest (if provided, other params are ignored)
            format_type: Output format type ('json' or 'toon')
            include_details: Whether to include detailed structure info
            include_complexity: Whether to include complexity metrics
            include_elements: Whether to extract code elements
            include_queries: Whether to execute queries
            queries: List of query names to execute

        Returns:
            Analysis result
        """
        if request is None:
            request = AnalysisRequest(
                file_path=file_path,
                language=language,
                format_type=format_type or "json",
                include_details=include_details
                if include_details is not None
                else False,
                include_complexity=include_complexity
                if include_complexity is not None
                else True,
                include_elements=include_elements
                if include_elements is not None
                else True,
                include_queries=include_queries
                if include_queries is not None
                else True,
                queries=queries,
            )
        else:
            # Update request with provided parameters
            if language:
                request.language = language
            if format_type:
                request.format_type = format_type
            if include_details is not None:
                request.include_details = include_details
            if include_complexity is not None:
                request.include_complexity = include_complexity
            if include_elements is not None:
                request.include_elements = include_elements
            if include_queries is not None:
                request.include_queries = include_queries
            if queries is not None:
                request.queries = queries
        return await self.analyze(request)

    async def analyze_file_async(
        self,
        file_path: str,
        language: str | None = None,
        request: AnalysisRequest | None = None,
    ) -> Any:
        """Compatibility alias for analyze"""
        return await self.analyze_file(file_path, language, request)

    async def analyze_code(
        self,
        code: str,
        language: str | None = None,
        filename: str = "string",
        request: AnalysisRequest | None = None,
    ) -> Any:
        """Analyze source code string directly"""
        import tempfile

        from .request import AnalysisRequest

        # Default language if not provided
        actual_language = language or "unknown"

        if request is None:
            request = AnalysisRequest(file_path=filename, language=actual_language)
        elif language:
            request.language = language

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f".{actual_language}", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(code)
            temp_path = tf.name

        try:
            new_request = AnalysisRequest(
                file_path=temp_path,
                language=actual_language,
                queries=request.queries,
                include_elements=request.include_elements,
                include_queries=request.include_queries,
                include_complexity=request.include_complexity,
                include_details=request.include_details,
                format_type=request.format_type,
            )
            result = await self.analyze(new_request)
            result.file_path = filename
            return result
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def analyze_code_sync(
        self,
        code: str,
        language: str,
        filename: str = "string",
        request: AnalysisRequest | None = None,
    ) -> Any:
        """Sync version of analyze_code"""
        try:
            # Check if we're already in an event loop
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            return asyncio.run(self.analyze_code(code, language, filename, request))

        # Already in an event loop - create a new thread to run the async code
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run, self.analyze_code(code, language, filename, request)
            )
            return future.result()

    async def _run_queries(
        self,
        request: AnalysisRequest,
        result: AnalysisResult,
        plugin: "LanguagePlugin",
        language: Any,
    ) -> None:
        """Helper to run queries"""
        from ..utils import log_error

        try:
            parse_result = self._parser.parse_file(request.file_path, language)
            if parse_result.success and parse_result.tree:
                ts_language = getattr(
                    plugin, "get_tree_sitter_language", lambda: None
                )()
                if ts_language:
                    query_results = {}
                    if request.queries:
                        for query_name in request.queries:
                            q_res = (
                                self._query_executor.execute_query_with_language_name(
                                    parse_result.tree,
                                    ts_language,
                                    query_name,
                                    parse_result.source_code,
                                    language,
                                )
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
        try:
            if os.path.exists(request.file_path) and os.path.isfile(request.file_path):
                stat = os.stat(request.file_path)
                key_components.extend([str(int(stat.st_mtime)), str(stat.st_size)])
        except (OSError, FileNotFoundError):
            pass
        return hashlib.sha256(":".join(key_components).encode("utf-8")).hexdigest()

    def _detect_language(self, file_path: str) -> str:
        """Detect language"""
        self._ensure_initialized()
        try:
            return self._language_detector.detect_from_extension(file_path)  # type: ignore[no-any-return]
        except Exception:
            return "unknown"

    def _create_empty_result(
        self, file_path: str, language: str, error: str | None = None
    ) -> Any:
        """Create empty result on failure"""
        from ..models import AnalysisResult

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
        if self._cache_service:
            self._cache_service.clear()
        if self._performance_monitor:
            self._performance_monitor.clear_metrics()
        from ..utils import log_debug

        log_debug("UnifiedAnalysisEngine cleaned up")

    def analyze_sync(self, request: AnalysisRequest) -> Any:
        """Sync version of analyze"""
        try:
            # Check if we're already in an event loop
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            return asyncio.run(self.analyze(request))

        # Already in an event loop - create a new thread to run the async code
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, self.analyze(request))
            return future.result()

    def get_supported_languages(self) -> list[str]:
        """Get list of supported languages"""
        self._ensure_initialized()
        return self._plugin_manager.get_supported_languages()  # type: ignore[no-any-return]

    def get_available_queries(self, language: str) -> list[str]:
        """Get available queries for a language"""
        self._ensure_initialized()
        return self._query_executor.get_available_queries(language)  # type: ignore[no-any-return]

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics (compatibility method)"""
        self._ensure_initialized()
        return self._cache_service.get_stats()  # type: ignore[no-any-return]

    @property
    def language_detector(self) -> Any:
        """Expose language detector"""
        self._ensure_initialized()
        return self._language_detector

    @property
    def plugin_manager(self) -> Any:
        """Expose plugin manager"""
        self._ensure_initialized()
        return self._plugin_manager

    @property
    def cache_service(self) -> Any:
        """Expose cache service"""
        self._ensure_initialized()
        return self._cache_service

    @property
    def parser(self) -> Any:
        """Expose parser"""
        self._ensure_initialized()
        return self._parser

    @property
    def query_executor(self) -> Any:
        """Expose query executor"""
        self._ensure_initialized()
        return self._query_executor

    @property
    def security_validator(self) -> Any:
        """Expose security validator"""
        self._ensure_initialized()
        return self._security_validator

    def measure_operation(self, operation_name: str) -> PerformanceContext:
        """Measure an operation using the performance monitor"""
        self._ensure_initialized()
        return self._performance_monitor.measure_operation(operation_name)  # type: ignore[no-any-return]

    @classmethod
    def _reset_instance(cls) -> None:
        """Compatibility method for resetting instances"""
        EngineManager.reset_instances()
        cls._instances.clear()


# Simple plugin implementation (for testing)
class MockLanguagePlugin:
    """Mock plugin for testing"""

    def __init__(self, language: str) -> None:
        self.language = language

    def get_language_name(self) -> str:
        return self.language

    def get_file_extensions(self) -> list[str]:
        return [f".{self.language}"]

    def create_extractor(self) -> None:
        return None

    async def analyze_file(self, file_path: str, request: AnalysisRequest) -> Any:
        from ..models import AnalysisResult

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
    """Get unified analysis engine instance"""
    return UnifiedAnalysisEngine(project_root)
