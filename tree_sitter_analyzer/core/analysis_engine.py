#!/usr/bin/env python3
"""
Unified Analysis Engine - Core Component for CLI and MCP

This module provides a unified analysis engine with dependency injection,
singleton pattern support, and comprehensive error handling.

Architecture:
- Dependency Injection: Recommended for new code
- Singleton Pattern: For backward compatibility
- Lazy Initialization: For performance optimization
- Type Safety: Full type hints (PEP 484)
- Error Handling: Comprehensive error handling and recovery
"""

import asyncio
import hashlib
import os
import threading
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Union, Callable, Type
from functools import lru_cache
from pathlib import Path

from ..models import AnalysisResult, Element, Function, Import, Class
from .performance import PerformanceContext, PerformanceMonitor
from .request import AnalysisRequest
from ..utils import log_debug, log_info, log_error, log_warning, log_performance

if TYPE_CHECKING:
    from ..language_detector import LanguageDetector, LanguageInfo, LanguageType
    from ..plugins.manager import PluginManager, PluginConfig
    from ..security import SecurityValidator
    from .cache_service import CacheService, CacheConfig
    from .parser import Parser
    from .query import QueryExecutor, QueryConfig


class UnsupportedLanguageError(Exception):
    """Raised when an unsupported language is requested."""

    pass


class InitializationError(Exception):
    """Raised when engine initialization fails."""

    pass


class AnalysisError(Exception):
    """Raised when code analysis fails."""

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

    Features:
    - Type-safe operations
    - Comprehensive error handling
    - Performance monitoring
    - Caching for optimization
    - Lazy initialization for performance
    - Backward compatibility with singleton pattern
    """

    _instances: Dict[str, "UnifiedAnalysisEngine"] = {}
    _lock: threading.Lock = threading.Lock()

    def __new__(
        cls,
        project_root: str | None = None,
        **kwargs: Any,
    ) -> "UnifiedAnalysisEngine":
        """
        Singleton instance management with dependency injection support.

        If dependencies are provided via kwargs, creates a new instance.
        Otherwise, returns singleton instance.

        Args:
            project_root: Project root path for singleton key
            **kwargs: Dependencies (parser, language_detector, etc.)

        Returns:
            UnifiedAnalysisEngine instance

        Note:
            - For new code, use `create_analysis_engine()` factory function
            - Singleton pattern is for backward compatibility only
        """
        # Skip singleton if dependencies are provided
        if any(k in kwargs for k in [
            "parser", "language_detector", "plugin_manager",
            "cache_service", "security_validator", "query_executor",
            "performance_monitor"
        ]):
            return super().__new__(cls)

        # Singleton pattern for backward compatibility
        instance_key = project_root or "default"
        with cls._lock:
            if instance_key not in cls._instances:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instances[instance_key] = instance
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
        **kwargs: Any,
    ) -> None:
        """
        Initialize engine with optional dependency injection.

        Args:
            project_root: Project root path for security validation
            parser: Parser instance for code files
            language_detector: Language detection service
            plugin_manager: Plugin management service
            cache_service: Caching service
            security_validator: Security validation service
            query_executor: Query execution service
            performance_monitor: Performance monitoring service
            **kwargs: Additional configuration for future extensibility

        Note:
            - Dependencies provided via constructor are used directly
            - Dependencies not provided are lazily loaded (backward compatible)
            - Performance monitor defaults to `PerformanceMonitor()` if not provided
        """
        # Skip re-initialization for singleton instances
        if getattr(self, "_initialized", False):
            return

        self._project_root = project_root

        # Use provided dependencies or create them lazily
        if all([
            parser,
            language_detector,
            plugin_manager,
            cache_service,
            security_validator,
            query_executor,
            performance_monitor,
        ]):
            # Direct injection mode (recommended)
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
            self._performance_monitor = None
            self._lazy_mode = True

            # Only perform lightweight initialization (to avoid heavy loading)
            self._plugin_manager = PluginManager() if not plugin_manager else None

        self._initialized = True

    def _ensure_initialized(self) -> None:
        """
        Ensure all components are lazily initialized only when needed.

        Raises:
            InitializationError: If lazy initialization fails
        """
        if not self._lazy_mode:
            return

        if self._parser is not None:
            return

        try:
            # Import dependencies
            from ..language_detector import LanguageDetector
            from ..plugins.manager import PluginManager
            from ..security import SecurityValidator
            from .cache_service import CacheService
            from .parser import Parser
            from .query import QueryExecutor
            from ..utils import log_error

            # Create all dependencies
            self._parser = Parser()
            self._language_detector = LanguageDetector()
            self._plugin_manager = PluginManager()
            self._cache_service = CacheService()
            self._security_validator = SecurityValidator(self._project_root)
            self._query_executor = QueryExecutor()
            self._performance_monitor = PerformanceMonitor()

            # Load plugins
            self._plugin_manager.load_plugins()

        except ImportError as e:
            log_error(f"Failed to import dependencies: {e}")
            raise InitializationError(
                f"Tree-sitter analyzer dependencies not found. "
                f"Please install: pip install tree-sitter-analyzer[core]"
            ) from e
        except Exception as e:
            log_error(f"Failed to initialize engine: {e}")
            raise InitializationError(
                f"Failed to initialize analysis engine: {e}"
            ) from e

    def _load_plugins(self) -> None:
        """
        Discover available plugins (lightweight metadata scan).

        Note:
            - This performs a lightweight scan to avoid heavy loading
            - Only plugin metadata is loaded, not plugin code
            - Actual plugin code is loaded on-demand
        """
        from ..utils import log_debug, log_error

        # Minimal init for discovery
        if self._plugin_manager is None:
            from ..plugins.manager import PluginManager

            try:
                self._plugin_manager = PluginManager()
                log_debug("PluginManager initialized (for discovery)")
            except Exception as e:
                log_error(f"Failed to initialize PluginManager: {e}")
                return

        log_debug("Discovering plugins using PluginManager...")
        try:
            self._plugin_manager.discover_plugins()
        except Exception as e:
            log_error(f"Failed to discover plugins: {e}")

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """
        Unified analysis method with performance monitoring and caching.

        Args:
            request: Analysis request with file path and options

        Returns:
            Analysis result with file analysis

        Raises:
            ValueError: If file path is invalid
            UnsupportedLanguageError: If language is not supported
            FileNotFoundError: If file does not exist
            AnalysisError: If analysis fails

        Note:
            - Supports both file and code analysis
            - Automatically detects language if not specified
            - Uses caching to optimize repeated analyses
            - Performance monitoring is built-in
        """
        from ..utils import log_debug, log_info, log_error

        # Start performance monitoring
        operation_name = f"analyze_{Path(request.file_path).name}"
        with self._performance_monitor.measure_operation(operation_name):
            log_debug(f"Starting analysis for {request.file_path}")

            # 1. Validate path
            self._validate_path(request.file_path)

            # 2. Detect and validate language
            language = self._get_validated_language(request)

            # 3. Check cache
            cache_key = self._generate_cache_key(request)
            cached_result = await self._cache_service.get(cache_key)
            if cached_result:
                log_info(f"Cache hit for {request.file_path}")
                return cached_result

            # 4. Parse file
            if not os.path.exists(request.file_path):
                raise FileNotFoundError(f"File not found: {request.file_path}")

            parse_result = self._parser.parse_file(request.file_path, language)
            if not parse_result.success:
                return self._create_empty_result(
                    request.file_path, language, parse_result.error_message
                )

            # 5. Get plugin and analyze
            plugin = self._plugin_manager.get_plugin(language)
            if not plugin:
                raise UnsupportedLanguageError(f"Plugin not found for language: {language}")

            # 6. Execute queries if requested
            if request.queries and request.include_queries:
                await self._run_queries(request, parse_result.tree, language)

            # 7. Create result
            result = await plugin.analyze_file(request.file_path, request)

            if not result.language:
                result.language = language

            # 8. Update cache
            await self._cache_service.set(cache_key, result)

            return result

    def _validate_path(self, file_path: str) -> None:
        """
        Validate file path for security.

        Args:
            file_path: Path to file

        Raises:
            ValueError: If file path is invalid

        Note:
            - Security validator prevents path traversal attacks
            - Validates file is within allowed directories
        """
        from ..utils import log_error

        self._ensure_initialized()

        is_valid, error_msg = self._security_validator.validate_file_path(file_path)
        if not is_valid:
            log_error(f"Security validation failed: {file_path} - {error_msg}")
            raise ValueError(f"Invalid file path: {error_msg}")

    def _get_validated_language(self, request: AnalysisRequest) -> str:
        """
        Detect and validate language support.

        Args:
            request: Analysis request with optional language

        Returns:
            Language name

        Raises:
            UnsupportedLanguageError: If language is not supported

        Note:
            - Auto-detects language if not specified
            - Validates language is supported by plugins
        """
        from ..utils import log_debug

        self._ensure_initialized()

        language = request.language or self._detect_language(request.file_path)
        if language == "unknown":
            raise UnsupportedLanguageError(f"Unsupported language: {language}")
        elif not self._language_detector.is_supported(language):
            raise UnsupportedLanguageError(f"Unsupported language: {language}")

        log_debug(f"Validated language: {language}")
        return str(language)

    def _detect_language(self, file_path: str) -> str:
        """
        Detect language from file path.

        Args:
            file_path: Path to file

        Returns:
            Language name or "unknown"

        Note:
            - Uses file extension for detection
            - Falls back to content analysis if needed
        """
        self._ensure_initialized()

        try:
            return self._language_detector.detect_from_extension(file_path)
        except Exception:
            return "unknown"

    def _generate_cache_key(self, request: AnalysisRequest) -> str:
        """
        Generate deterministic cache key from request parameters.

        Args:
            request: Analysis request

        Returns:
            SHA-256 hash string

        Note:
            - Includes file path, language, options, and file metadata
            - File metadata (mtime, size) ensures cache is invalidated on change
        """
        key_components = [
            request.file_path,
            str(request.language),
            str(request.include_complexity),
            request.format_type,
        ]

        # Add file metadata for cache invalidation
        try:
            if os.path.exists(request.file_path) and os.path.isfile(request.file_path):
                stat = os.stat(request.file_path)
                key_components.extend([
                    str(int(stat.st_mtime)),  # Modification time
                    str(stat.st_size),     # File size
                ])
        except (OSError, FileNotFoundError):
            pass

        # Generate SHA-256 hash
        key_str = ":".join(key_components)
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    async def _run_queries(
        self,
        request: AnalysisRequest,
        tree: Any,
        plugin: Any,
        language: str,
    ) -> None:
        """
        Execute queries on parsed tree.

        Args:
            request: Analysis request
            tree: Parsed tree-sitter tree
            plugin: Language plugin
            language: Language name

        Note:
            - Executes all requested queries
            - Supports both capture and syntax queries
            - Query results are added to analysis result
        """
        from ..utils import log_error

        self._ensure_initialized()

        try:
            ts_language = getattr(
                plugin, "get_tree_sitter_language", lambda: None
            )()
            if ts_language:
                query_results = {}
                for query_name in request.queries:
                    try:
                        q_res = self._query_executor.execute_query_with_language_name(
                            tree,
                            ts_language,
                            query_name,
                            getattr(plugin, "get_source_code", lambda: None)(),
                            language,
                        )
                        query_results[query_name] = (
                            q_res["captures"] if isinstance(q_res, dict) and "captures" in q_res else q_res
                        )
                    except Exception as e:
                        log_error(f"Query {query_name} failed: {e}")
                        query_results[query_name] = {"error": str(e)}

                # Add query results to request
                if not hasattr(request, "query_results"):
                    request.query_results = {}
                request.query_results.update(query_results)

        except Exception as e:
            log_error(f"Failed to run queries: {e}")

    def _create_empty_result(
        self,
        file_path: str,
        language: str,
        error: str | None = None,
    ) -> AnalysisResult:
        """
        Create empty result on failure.

        Args:
            file_path: Path to file
            language: Language name
            error: Error message

        Returns:
            Empty AnalysisResult

        Note:
            - Used when parsing or analysis fails
            - Preserves file_path and language
            - Includes error message for debugging
        """
        from ..models import AnalysisResult

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
        Analyze a single file.

        Args:
            file_path: Path to file
            language: Optional language (auto-detect if not provided)
            request: Optional pre-built request
            **kwargs: Additional request parameters

        Returns:
            Analysis result with file analysis

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file path is invalid
            UnsupportedLanguageError: If language is not supported
            AnalysisError: If analysis fails

        Note:
            - Backward compatibility method
            - Auto-detects language if not specified
            - Supports both file and code analysis
        """
        from ..utils import log_debug

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
            filename: Virtual filename for the code
            request: Optional pre-built request

        Returns:
            Analysis result

        Raises:
            UnsupportedLanguageError: If language is not supported
            AnalysisError: If analysis fails

        Note:
            - Useful for analyzing code without a file
            - Filename is used for language detection
        """
        import tempfile

        from ..utils import log_debug

        # Determine language
        actual_language = language or "unknown"

        # Create temporary file for analysis
        suffix = f".{actual_language}" if actual_language != "unknown" else ".txt"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, encoding="utf-8"
        ) as tf:
            tf.write(code)
            temp_path = tf.name

        try:
            # Create request if not provided
            if request is None:
                request = AnalysisRequest(file_path=temp_path, language=actual_language)
            elif language:
                request.language = language

            # Analyze temporary file
            result = await self.analyze(request)
            result.file_path = filename  # Replace temp path with virtual filename

            return result
        finally:
            # Clean up temporary file
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception as e:
                log_error(f"Failed to remove temp file {temp_path}: {e}")

    def analyze_sync(self, request: AnalysisRequest) -> AnalysisResult:
        """
        Synchronous version of analyze.

        Args:
            request: Analysis request

        Returns:
            Analysis result

        Note:
            - Compatibility method for non-async code
            - Runs async code in a new thread
            - Not recommended for performance-critical code
        """
        try:
            # Try to get existing loop
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
        """
        Helper to ensure AnalysisRequest is properly built from parameters.

        Args:
            file_path: Path to file
            language: Optional language (auto-detect if not provided)
            request: Optional pre-built request
            **kwargs: Additional request parameters

        Returns:
            AnalysisRequest instance

        Note:
            - Creates request if not provided
            - Auto-detects language if not specified
            - Updates request with provided parameters
        """
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

    @property
    def language_detector(self) -> Any:
        """Expose language detector instance."""
        self._ensure_initialized()
        return self._language_detector

    @property
    def plugin_manager(self) -> Any:
        """Expose plugin manager instance."""
        self._ensure_initialized()
        return self._plugin_manager

    @property
    def cache_service(self) -> Any:
        """Expose cache service instance."""
        self._ensure_initialized()
        return self._cache_service

    @property
    def parser(self) -> Any:
        """Expose parser instance."""
        self._ensure_initialized()
        return self._parser

    @property
    def query_executor(self) -> Any:
        """Expose query executor instance."""
        self._ensure_initialized()
        return self._query_executor

    @property
    def security_validator(self) -> Any:
        """Expose security validator instance."""
        self._ensure_initialized()
        return self._security_validator

    def cleanup(self) -> None:
        """
        Clean up resources (cache, metrics, etc.).

        Note:
            - Clears analysis cache
            - Clears performance metrics
            - Resets internal state if needed
        """
        self._ensure_initialized()

        # Clear cache
        if self._cache_service:
            self._cache_service.clear()

        # Clear performance metrics
        if self._performance_monitor:
            self._performance_monitor.clear_metrics()

        from ..utils import log_debug

        log_debug("UnifiedAnalysisEngine cleaned up")


# Factory functions
def create_analysis_engine(
    project_root: str | None = None,
    parser: Optional["Parser"] = None,
    language_detector: Optional["LanguageDetector"] = None,
    plugin_manager: Optional["PluginManager"] = None,
    cache_service: Optional["CacheService"] = None,
    security_validator: Optional["SecurityValidator"] = None,
    query_executor: Optional["QueryExecutor"] = None,
    performance_monitor: PerformanceMonitor | None = None,
) -> UnifiedAnalysisEngine:
    """
    Factory function to create a properly configured analysis engine.

    This function creates all necessary dependencies and injects them
    into the engine, providing a clean dependency injection pattern.

    Args:
        project_root: Project root path for security validation
        parser: Parser instance
        language_detector: Language detector instance
        plugin_manager: Plugin manager instance
        cache_service: Cache service instance
        security_validator: Security validator instance
        query_executor: Query executor instance
        performance_monitor: Performance monitor instance

    Returns:
        Configured UnifiedAnalysisEngine instance

    Raises:
        InitializationError: If dependency initialization fails

    Note:
        - Recommended for new code
        - Provides clean dependency injection
        - All dependencies are properly initialized
        - Plugin manager loads plugins during initialization
    """
    # Import dependencies
    from ..language_detector import LanguageDetector
    from ..plugins.manager import PluginManager
    from ..security import SecurityValidator
    from .cache_service import CacheService
    from .parser import Parser
    from .query import QueryExecutor
    from ..utils import log_error

    try:
        # Create parser
        parser = parser or Parser()

        # Create language detector
        language_detector = language_detector or LanguageDetector()

        # Create plugin manager
        plugin_manager = plugin_manager or PluginManager()

        # Create cache service
        cache_service = cache_service or CacheService()

        # Create security validator
        security_validator = security_validator or SecurityValidator(project_root)

        # Create query executor
        query_executor = query_executor or QueryExecutor()

        # Create performance monitor
        performance_monitor = performance_monitor or PerformanceMonitor()

        # Load plugins
        plugin_manager.load_plugins()

        # Create engine
        engine = UnifiedAnalysisEngine(
            project_root=project_root,
            parser=parser,
            language_detector=language_detector,
            plugin_manager=plugin_manager,
            cache_service=cache_service,
            security_validator=security_validator,
            query_executor=query_executor,
            performance_monitor=performance_monitor,
        )

        return engine

    except ImportError as e:
        log_error(f"Failed to import module: {e}")
        raise InitializationError(
            f"Tree-sitter analyzer dependencies not found. "
            f"Please install: pip install tree-sitter-analyzer[core]"
        ) from e
    except Exception as e:
        log_error(f"Failed to create analysis engine: {e}")
        raise InitializationError(
            f"Failed to create analysis engine: {e}"
        ) from e


def get_analysis_engine(
    project_root: str | None = None,
) -> UnifiedAnalysisEngine:
    """
    Get unified analysis engine instance (backward compatible).

    This function returns singleton instance and is provided for
    backward compatibility. For new code, prefer `create_analysis_engine()`.

    Args:
        project_root: Project root path

    Returns:
        UnifiedAnalysisEngine instance

    Note:
        - Returns singleton instance
        - Creates instance if it doesn't exist
        - Not recommended for new code
    """
    return UnifiedAnalysisEngine(project_root)


# Export for convenience
__all__ = [
    "UnifiedAnalysisEngine",
    "UnsupportedLanguageError",
    "InitializationError",
    "AnalysisError",
    "create_analysis_engine",
    "get_analysis_engine",
]
