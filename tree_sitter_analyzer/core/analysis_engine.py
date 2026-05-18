#!/usr/bin/env python3
"""
Unified Analysis Engine - Common Analysis System for CLI and MCP (Fixed & Optimized)

This module provides a unified engine that serves as the center of all analysis processing.
It is commonly used by CLI, MCP, and other interfaces.
"""

import threading
from typing import Any, Protocol

from ..models import AnalysisResult
from ._analysis_engine_analysis_mixin import UnifiedAnalysisEngineAnalysisMixin
from ._analysis_engine_code_mixin import UnifiedAnalysisEngineCodeMixin
from ._analysis_engine_errors import UnsupportedLanguageError
from ._analysis_engine_file_mixin import UnifiedAnalysisEngineFileMixin
from ._analysis_engine_runtime_mixin import UnifiedAnalysisEngineRuntimeMixin
from .performance import PerformanceMonitor
from .request import AnalysisRequest

__all__ = [
    "AnalysisRequest",
    "LanguagePlugin",
    "UnifiedAnalysisEngine",
    "UnsupportedLanguageError",
]


class LanguagePlugin(Protocol):
    """Language plugin protocol"""

    async def analyze_file(self, file_path: str, request: AnalysisRequest) -> Any:
        """File analysis"""
        ...


class UnifiedAnalysisEngine(
    UnifiedAnalysisEngineAnalysisMixin,
    UnifiedAnalysisEngineFileMixin,
    UnifiedAnalysisEngineCodeMixin,
    UnifiedAnalysisEngineRuntimeMixin,
):
    """
    Unified analysis engine

    Central engine shared by CLI, MCP and other interfaces.
    """

    _instances: dict[str, "UnifiedAnalysisEngine"] = {}
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, project_root: str | None = None) -> "UnifiedAnalysisEngine":
        """Singleton instance management (backward compatible)"""
        instance_key = project_root or "default"
        instance = cls._instances.get(instance_key)
        if instance is not None:
            return instance

        with cls._lock:
            return _get_or_create_engine_instance(cls, instance_key)

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

    # Handler: clear_cache
    def clear_cache(self) -> None:
        """Clear the analysis cache (compatibility method)"""
        self._ensure_initialized()
        if self._cache_service:
            self._cache_service.clear()

    # Handler: _load_plugins
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


# Simple plugin implementation (for testing)
class MockLanguagePlugin:
    """Mock plugin for testing"""

    def __init__(self, language: str) -> None:
        self.language = language

    def get_language_name(self) -> str:
        return self.language

    def get_file_extensions(self) -> list[str]:
        return [f".{self.language}"]

    @staticmethod
    def create_extractor() -> None:
        return None

    # Analyze source code structure: analyze_file
    async def analyze_file(self, file_path: str, request: AnalysisRequest) -> Any:

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


def _get_or_create_engine_instance(
    engine_cls: type[UnifiedAnalysisEngine], instance_key: str
) -> UnifiedAnalysisEngine:
    instance = engine_cls._instances.get(instance_key)
    if instance is not None:
        return instance

    instance = object.__new__(engine_cls)
    engine_cls._instances[instance_key] = instance
    instance._initialized = False
    return instance
