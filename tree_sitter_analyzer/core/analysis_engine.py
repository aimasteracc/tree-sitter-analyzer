#!/usr/bin/env python3
"""
Unified Analysis Engine - Common Analysis System for CLI and MCP (Fixed Version)

This module provides a unified engine that serves as the center of all analysis processing.
It is commonly used by CLI, MCP, and other interfaces.
"""

import asyncio
import hashlib
import os
import threading
from typing import Any, Protocol

from .engine_manager import EngineManager
from .performance import PerformanceContext, PerformanceMonitor

# Import internal components early to avoid late NameErrors during async execution
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

        # Lazy imports to avoid circular dependencies
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

    def clear_cache(self) -> None:
        """Clear the analysis cache (compatibility method)"""
        self._cache_service.clear()

    def _load_plugins(self) -> None:
        """Auto-load available plugins"""
        from ..utils import log_debug, log_error

        log_debug("Loading plugins using PluginManager...")
        try:
            loaded_plugins = self._plugin_manager.load_plugins()
            final_languages = [plugin.get_language_name() for plugin in loaded_plugins]
            log_debug(
                f"Successfully loaded {len(final_languages)} plugins: {', '.join(final_languages)}"
            )
        except Exception as e:
            log_error(f"Failed to load plugins: {e}")

    async def analyze(self, request: AnalysisRequest) -> Any:
        """Unified analysis method (Async)"""
        from ..utils import log_debug, log_error, log_info

        log_debug(f"Starting async analysis for {request.file_path}")

        # Security validation
        is_valid, error_msg = self._security_validator.validate_file_path(
            request.file_path
        )
        if not is_valid:
            log_error(f"Security validation failed: {request.file_path} - {error_msg}")
            raise ValueError(f"Invalid file path: {error_msg}")

        # Language detection (Early detection for backward compatibility with tests)
        language = request.language or self._detect_language(request.file_path)
        if not self._language_detector.is_supported(language):
            raise UnsupportedLanguageError(f"Unsupported language: {language}")

        # Cache check (Performed BEFORE existence check to allow cached results for non-existent files in tests)
        cache_key = self._generate_cache_key(request)
        cached_result = await self._cache_service.get(cache_key)
        if cached_result:
            log_info(f"Cache hit for {request.file_path}")
            return cached_result

        # File existence check (Only if cache miss)
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
        self, file_path: str, request: AnalysisRequest | None = None
    ) -> Any:
        """Compatibility alias for analyze"""
        if request is None:
            request = AnalysisRequest(file_path=file_path)
        elif request.file_path != file_path:
            # Handle mismatch if needed, but usually we just use the provided request
            pass
        return await self.analyze(request)

    async def analyze_file_async(
        self, file_path: str, request: AnalysisRequest | None = None
    ) -> Any:
        """Compatibility alias for analyze"""
        return await self.analyze_file(file_path, request)

    async def analyze_code(
        self,
        code: str,
        language: str,
        filename: str = "string",
        request: AnalysisRequest | None = None,
    ) -> Any:
        """Analyze source code string directly"""
        import tempfile

        from .request import AnalysisRequest

        # Create default request if not provided
        if request is None:
            request = AnalysisRequest(file_path=filename, language=language)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f".{language}", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(code)
            temp_path = tf.name

        try:
            # Create new request with temp path to bypass frozen dataclass
            new_request = AnalysisRequest(
                file_path=temp_path,
                language=language,
                queries=request.queries,
                include_elements=request.include_elements,
                include_queries=request.include_queries,
                include_complexity=request.include_complexity,
                include_details=request.include_details,
                format_type=request.format_type,
            )
            result = await self.analyze(new_request)
            # Restore original path in result
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
        return asyncio.run(self.analyze_code(code, language, filename, request))

    async def _run_queries(self, request, result, plugin, language):
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
        # In test environments, os.path.exists might be mocked, but physical file might not exist.
        # We wrap in try-except to be safe and avoid FileNotFoundError during key generation.
        try:
            if os.path.exists(request.file_path) and os.path.isfile(request.file_path):
                stat = os.stat(request.file_path)
                key_components.extend([str(int(stat.st_mtime)), str(stat.st_size)])
        except (OSError, FileNotFoundError):
            # If we can't get stat, just use the basic components
            pass
        return hashlib.sha256(":".join(key_components).encode("utf-8")).hexdigest()

    def _detect_language(self, file_path: str) -> str:
        """Detect language"""
        try:
            return self._language_detector.detect_from_extension(file_path)
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
        self._cache_service.clear()
        self._performance_monitor.clear_metrics()
        from ..utils import log_debug

        log_debug("UnifiedAnalysisEngine cleaned up")

    def analyze_sync(self, request: AnalysisRequest) -> Any:
        """Sync version of analyze"""
        return asyncio.run(self.analyze(request))

    def get_supported_languages(self) -> list[str]:
        """Get list of supported languages"""
        return self._plugin_manager.get_supported_languages()

    def get_available_queries(self, language: str) -> list[str]:
        """Get available queries for a language"""
        return self._query_executor.get_available_queries(language)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics (compatibility method)"""
        return self._cache_service.get_stats()

    @property
    def language_detector(self) -> Any:
        """Expose language detector"""
        return self._language_detector

    @property
    def plugin_manager(self) -> Any:
        """Expose plugin manager"""
        return self._plugin_manager

    def measure_operation(self, operation_name: str) -> PerformanceContext:
        """Measure an operation using the performance monitor"""
        return self._performance_monitor.measure_operation(operation_name)

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
