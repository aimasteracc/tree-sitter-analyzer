#!/usr/bin/env python3
"""
Unified Analysis Engine - Common Analysis System for CLI and MCP

This module provides a unified analysis engine with both dependency injection
and backward-compatible singleton pattern support.
"""

import asyncio
import hashlib
import os
import threading
from typing import TYPE_CHECKING, Any, Optional

from ..models import AnalysisResult
from .performance import PerformanceContext, PerformanceMonitor
from .request import AnalysisRequest

if TYPE_CHECKING:
    from ..language_detector import LanguageDetector
    from ..plugins.manager import PluginManager
    from ..security import SecurityValidator
    from .cache_service import CacheService
    from .parser import Parser
    from .query import QueryExecutor


class UnsupportedLanguageError(Exception):
    """Unsupported language error"""

    pass


class UnifiedAnalysisEngine:
    """
    Unified analysis engine with dependency injection and singleton support.

    This engine supports two usage patterns:

    1. Dependency Injection (Recommended):
    ```python
    engine = create_analysis_engine(project_root="/path/to/project")
    result = await engine.analyze(request)
    ```

    2. Singleton Pattern (Backward Compatible):
    ```python
    engine = UnifiedAnalysisEngine(project_root="/path/to/project")
    result = await engine.analyze(request)
    ```
    """

    _instances: dict[str, "UnifiedAnalysisEngine"] = {}
    _lock: threading.Lock = threading.Lock()

    def __new__(
        cls, project_root: str | None = None, **kwargs: Any
    ) -> "UnifiedAnalysisEngine":
        """
        Singleton instance management (backward compatible).

        If dependencies are provided via kwargs, creates a new instance without singleton.
        Otherwise, returns singleton instance.
        """
        # If dependencies are provided, skip singleton pattern
        if any(k in kwargs for k in ["parser", "language_detector", "plugin_manager"]):
            return super().__new__(cls)

        # Singleton pattern for backward compatibility
        instance_key = project_root or "default"
        if instance_key not in cls._instances:
            with cls._lock:
                if instance_key not in cls._instances:
                    instance = super().__new__(cls)
                    cls._instances[instance_key] = instance
                    instance._initialized = False
        return cls._instances[instance_key]

    def __init__(
        self,
        project_root: str | None = None,
        parser: Optional["Parser"] = None,
        language_detector: Optional["LanguageDetector"] = None,
        plugin_manager: Optional["PluginManager"] = None,
        cache_service: Optional["CacheService"] = None,
        security_validator: Optional["SecurityValidator"] = None,
        query_executor: Optional["QueryExecutor"] = None,
        performance_monitor: PerformanceMonitor | None = None,
    ) -> None:
        """
        Initialize the engine with optional dependency injection.

        Args:
            project_root: Optional project root path for security validation
            parser: Optional parser for code files
            language_detector: Optional language detection service
            plugin_manager: Optional plugin management service
            cache_service: Optional caching service
            security_validator: Optional security validation service
            query_executor: Optional query execution service
            performance_monitor: Optional performance monitoring service
        """
        # Skip re-initialization for singleton instances
        if getattr(self, "_initialized", False):
            return

        self._project_root = project_root

        # Use provided dependencies or create them lazily
        if all(
            [
                parser,
                language_detector,
                plugin_manager,
                cache_service,
                security_validator,
                query_executor,
            ]
        ):
            # Direct injection mode
            self._parser = parser
            self._language_detector = language_detector
            self._plugin_manager = plugin_manager
            self._cache_service = cache_service
            self._security_validator = security_validator
            self._query_executor = query_executor
            self._performance_monitor = performance_monitor or PerformanceMonitor()
            self._lazy_mode = False
        else:
            # Lazy initialization mode (backward compatible)
            self._parser = None
            self._language_detector = None
            self._plugin_manager = None
            self._cache_service = None
            self._security_validator = None
            self._query_executor = None
            self._performance_monitor = None  # type: ignore[assignment]
            self._lazy_mode = True

            # Initial plugin discovery only (no heavy loading)
            self._load_plugins()

        self._initialized = True

    def _ensure_initialized(self) -> None:
        """Ensure all components are lazily initialized only when needed"""
        if not self._lazy_mode:
            return

        if self._parser is not None:
            return

        # Create all dependencies
        from ..language_detector import LanguageDetector
        from ..plugins.manager import PluginManager
        from ..security import SecurityValidator
        from .cache_service import CacheService
        from .parser import Parser
        from .query import QueryExecutor

        self._parser = Parser()
        self._language_detector = LanguageDetector()
        self._plugin_manager = PluginManager()
        self._cache_service = CacheService()
        self._security_validator = SecurityValidator(self._project_root)
        self._query_executor = QueryExecutor()
        self._performance_monitor = PerformanceMonitor()

        # Load plugins
        self._plugin_manager.load_plugins()

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

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """
        Unified analysis method.

        Args:
            request: Analysis request with file path and options

        Returns:
            Analysis result

        Raises:
            ValueError: If file path is invalid
            UnsupportedLanguageError: If language is not supported
            FileNotFoundError: If file does not exist
        """
        from ..utils import log_debug, log_info

        self._ensure_initialized()

        log_debug(f"Starting analysis for {request.file_path}")

        # 1. Validate path
        self._validate_path(request.file_path)

        # 2. Detect and validate language
        language = self._get_validated_language(request)

        # 3. Check cache
        cache_key = self._generate_cache_key(request)
        cached_result = await self._cache_service.get(cache_key)  # type: ignore[union-attr]
        if cached_result:
            log_info(f"Cache hit for {request.file_path}")
            return cached_result  # type: ignore[no-any-return]

        # 4. Parse file
        if not os.path.exists(request.file_path):
            raise FileNotFoundError(f"File not found: {request.file_path}")

        parse_result = self._parser.parse_file(request.file_path, language)  # type: ignore[union-attr]
        if not parse_result.success:
            return self._create_empty_result(
                request.file_path, language, parse_result.error_message
            )

        # 5. Get plugin and analyze
        plugin = self._plugin_manager.get_plugin(language)  # type: ignore[union-attr]
        if not plugin:
            raise UnsupportedLanguageError(f"Plugin not found for language: {language}")

        with self._performance_monitor.measure_operation(f"analyze_{language}"):
            result = await plugin.analyze_file(request.file_path, request)

        if not result.language:
            result.language = language

        # 6. Execute queries if requested
        if request.queries and request.include_queries:
            await self._run_queries(request, result, plugin, language)

        # 7. Update cache
        await self._cache_service.set(cache_key, result)  # type: ignore[union-attr]
        return result

    def _validate_path(self, file_path: str) -> None:
        """Validate file path for security."""
        from ..utils import log_error

        self._ensure_initialized()

        is_valid, error_msg = self._security_validator.validate_file_path(file_path)  # type: ignore[union-attr]
        if not is_valid:
            log_error(f"Security validation failed: {file_path} - {error_msg}")
            raise ValueError(f"Invalid file path: {error_msg}")

    def _get_validated_language(self, request: AnalysisRequest) -> str:
        """Detect and validate language support."""
        self._ensure_initialized()

        language = request.language or self._detect_language(request.file_path)
        if language == "unknown":
            raise UnsupportedLanguageError(f"Unsupported language: {language}")
        elif not self._language_detector.is_supported(language):  # type: ignore[union-attr]
            raise UnsupportedLanguageError(f"Unsupported language: {language}")
        return str(language)

    def _detect_language(self, file_path: str) -> str:
        """Detect language from file path."""
        self._ensure_initialized()

        try:
            return self._language_detector.detect_from_extension(file_path)  # type: ignore[union-attr]
        except Exception:
            return "unknown"

    def _generate_cache_key(self, request: AnalysisRequest) -> str:
        """Generate cache key from request."""
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

    async def _run_queries(
        self,
        request: AnalysisRequest,
        result: AnalysisResult,
        plugin: Any,
        language: str,
    ) -> None:
        """Execute queries on the parsed tree."""
        from ..utils import log_error

        self._ensure_initialized()

        try:
            parse_result = self._parser.parse_file(request.file_path, language)  # type: ignore[union-attr]
            if parse_result.success and parse_result.tree:
                ts_language = getattr(
                    plugin, "get_tree_sitter_language", lambda: None
                )()
                if ts_language:
                    query_results = {}
                    if request.queries:
                        for query_name in request.queries:
                            q_res = (
                                self._query_executor.execute_query_with_language_name(  # type: ignore[union-attr]
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

    def _create_empty_result(
        self, file_path: str, language: str, error: str | None = None
    ) -> AnalysisResult:
        """Create empty result on failure."""
        return AnalysisResult(
            file_path=file_path,
            language=language,
            success=False,
            error_message=error,
            elements=[],
            analysis_time=0.0,
        )

    async def analyze_file(
        self,
        file_path: str,
        language: str | None = None,
        request: AnalysisRequest | None = None,
        **kwargs: Any,
    ) -> AnalysisResult:
        """
        Compatibility method for analyze with additional parameters.

        Args:
            file_path: Path to file to analyze
            language: Optional language override
            request: Optional pre-built request
            **kwargs: Additional request parameters

        Returns:
            Analysis result
        """
        request = self._ensure_request(file_path, language, request, **kwargs)
        return await self.analyze(request)

    async def analyze_code(
        self,
        code: str,
        language: str | None = None,
        filename: str = "string",
        request: AnalysisRequest | None = None,
    ) -> AnalysisResult:
        """
        Analyze source code string directly.

        Args:
            code: Source code to analyze
            language: Programming language
            filename: Virtual filename
            request: Optional pre-built request

        Returns:
            Analysis result
        """
        import tempfile

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

    def analyze_sync(self, request: AnalysisRequest) -> AnalysisResult:
        """
        Synchronous version of analyze.

        Args:
            request: Analysis request

        Returns:
            Analysis result
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            return asyncio.run(self.analyze(request))

        # Already in an event loop - create a new thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, self.analyze(request))
            return future.result()

    def _ensure_request(
        self,
        file_path: str,
        language: str | None = None,
        request: AnalysisRequest | None = None,
        **kwargs: Any,
    ) -> AnalysisRequest:
        """Helper to ensure AnalysisRequest is properly built from parameters."""
        if request is None:
            return AnalysisRequest(
                file_path=file_path,
                language=language,
                format_type=str(kwargs.get("format_type") or "json"),
                include_details=bool(kwargs.get("include_details") or False),
                include_complexity=bool(
                    kwargs.get("include_complexity")
                    if kwargs.get("include_complexity") is not None
                    else True
                ),
                include_elements=bool(
                    kwargs.get("include_elements")
                    if kwargs.get("include_elements") is not None
                    else True
                ),
                include_queries=bool(
                    kwargs.get("include_queries")
                    if kwargs.get("include_queries") is not None
                    else True
                ),
                queries=kwargs.get("queries"),
            )

        # Update existing request with provided parameters
        if language:
            request.language = language

        for key in [
            "format_type",
            "include_details",
            "include_complexity",
            "include_elements",
            "include_queries",
            "queries",
        ]:
            if key in kwargs and kwargs[key] is not None:
                setattr(request, key, kwargs[key])

        return request

    def get_supported_languages(self) -> list[str]:
        """Get list of supported languages."""
        self._ensure_initialized()
        return self._plugin_manager.get_supported_languages()  # type: ignore[union-attr]

    def get_available_queries(self, language: str) -> list[str]:
        """Get available queries for a language."""
        self._ensure_initialized()
        return self._query_executor.get_available_queries(language)  # type: ignore[union-attr]

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        self._ensure_initialized()
        return self._cache_service.get_stats()  # type: ignore[union-attr]

    def clear_cache(self) -> None:
        """Clear the analysis cache."""
        self._ensure_initialized()
        self._cache_service.clear()  # type: ignore[union-attr]

    def register_plugin(self, language: str, plugin: Any) -> None:
        """Register a plugin (compatibility method)"""
        self._ensure_initialized()
        self._plugin_manager.register_plugin(plugin)  # type: ignore[union-attr]

    def cleanup(self) -> None:
        """Resource cleanup."""
        if self._cache_service:
            self._cache_service.clear()
        if self._performance_monitor:
            self._performance_monitor.clear_metrics()
        from ..utils import log_debug

        log_debug("UnifiedAnalysisEngine cleaned up")

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
        return self._performance_monitor.measure_operation(operation_name)

    @classmethod
    def _reset_instance(cls) -> None:
        """
        Reset all singleton instances (for testing).

        注意: EngineManager.reset_instances() も同じ _instances をクリアするため、
        どちらのメソッドを呼んでも同じ結果になります。
        """
        with cls._lock:
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


def create_analysis_engine(project_root: str | None = None) -> UnifiedAnalysisEngine:
    """
    Factory function to create a properly configured analysis engine.

    This function creates all necessary dependencies and injects them
    into the engine, providing a clean dependency injection pattern.

    Args:
        project_root: Optional project root path for security validation

    Returns:
        Configured UnifiedAnalysisEngine instance
    """
    from ..language_detector import LanguageDetector
    from ..plugins.manager import PluginManager
    from ..security import SecurityValidator
    from .cache_service import CacheService
    from .parser import Parser
    from .query import QueryExecutor

    # Create dependencies
    parser = Parser()
    language_detector = LanguageDetector()
    plugin_manager = PluginManager()
    cache_service = CacheService()
    security_validator = SecurityValidator(project_root)
    query_executor = QueryExecutor()
    performance_monitor = PerformanceMonitor()

    # Load plugins
    plugin_manager.load_plugins()

    # Create and return engine
    return UnifiedAnalysisEngine(
        project_root=project_root,
        parser=parser,
        language_detector=language_detector,
        plugin_manager=plugin_manager,
        cache_service=cache_service,
        security_validator=security_validator,
        query_executor=query_executor,
        performance_monitor=performance_monitor,
    )


def get_analysis_engine(project_root: str | None = None) -> UnifiedAnalysisEngine:
    """
    Get unified analysis engine instance (backward compatible).

    This function maintains backward compatibility with the singleton pattern.
    For new code, prefer using create_analysis_engine() instead.

    Args:
        project_root: Optional project root path

    Returns:
        UnifiedAnalysisEngine instance
    """
    return UnifiedAnalysisEngine(project_root)
