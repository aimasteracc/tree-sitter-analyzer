"""Runtime/accessor methods for UnifiedAnalysisEngine."""

import asyncio
from typing import Any

from .engine_manager import EngineManager
from .performance import PerformanceContext
from .request import AnalysisRequest


class UnifiedAnalysisEngineRuntimeMixin:
    """Sync wrappers, resource cleanup, and compatibility accessors."""

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
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.analyze(request))

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
