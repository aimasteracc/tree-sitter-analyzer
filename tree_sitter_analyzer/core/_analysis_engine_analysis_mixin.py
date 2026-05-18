"""Analysis workflow mixin for UnifiedAnalysisEngine."""

import hashlib
import os
from typing import Any

from ..models import AnalysisResult
from ._analysis_engine_errors import UnsupportedLanguageError
from .request import AnalysisRequest


class UnifiedAnalysisEngineAnalysisMixin:
    """Core analyze workflow and internal analysis helpers."""

    async def analyze(self, request: AnalysisRequest) -> Any:
        """Unified analysis method (Async)"""
        self._ensure_initialized()
        from ..utils import log_debug, log_info

        log_debug(f"Starting async analysis for {request.file_path}")

        language = self._validate_and_detect_language(request)
        cache_key = self._generate_cache_key(request)
        cached_result = await self._cache_service.get(cache_key)
        if cached_result:
            log_info(f"Cache hit for {request.file_path}")
            return cached_result

        self._ensure_file_exists(request.file_path)
        parse_result = self._parser.parse_file(request.file_path, language)
        if not parse_result.success:
            return self._create_empty_result(
                request.file_path, language, parse_result.error_message
            )

        plugin = self._get_plugin(language)
        result = await self._run_plugin_analysis(request, plugin, language)

        if request.queries and request.include_queries:
            await self._run_queries(request, result, plugin, language)

        await self._cache_service.set(cache_key, result)
        return result

    def _validate_and_detect_language(self, request: AnalysisRequest) -> str:
        self._validate_file_path(request.file_path)
        language = request.language or self._detect_language(request.file_path)
        if language == "unknown" or not self._language_detector.is_supported(language):
            raise UnsupportedLanguageError(f"Unsupported language: {language}")
        return language

    def _validate_file_path(self, file_path: str) -> None:
        from ..utils import log_error

        is_valid, error_msg = self._security_validator.validate_file_path(file_path)
        if not is_valid:
            log_error(f"Security validation failed: {file_path} - {error_msg}")
            raise ValueError(f"Invalid file path: {error_msg}")

    @staticmethod
    def _ensure_file_exists(file_path: str) -> None:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

    def _get_plugin(self, language: str) -> Any:
        plugin = self._plugin_manager.get_plugin(language)
        if not plugin:
            raise UnsupportedLanguageError(f"Plugin not found for language: {language}")
        return plugin

    async def _run_plugin_analysis(
        self, request: AnalysisRequest, plugin: Any, language: str
    ) -> Any:
        with self._performance_monitor.measure_operation(f"analyze_{language}"):
            result = await plugin.analyze_file(request.file_path, request)
        if not result.language:
            result.language = language
        return result

    async def _run_queries(
        self,
        request: AnalysisRequest,
        result: AnalysisResult,
        plugin: Any,
        language: Any,
    ) -> None:
        """Helper to run queries"""
        from ..utils import log_error

        try:
            parse_result = self._parser.parse_file(request.file_path, language)
            if not (parse_result.success and parse_result.tree):
                return

            ts_language = getattr(plugin, "get_tree_sitter_language", lambda: None)()
            if not ts_language:
                return

            result.query_results = self._execute_requested_queries(
                request, parse_result, ts_language, language
            )
        except Exception as e:
            log_error(f"Failed to execute queries: {e}")

    def _execute_requested_queries(
        self,
        request: AnalysisRequest,
        parse_result: Any,
        ts_language: Any,
        language: Any,
    ) -> dict[str, Any]:
        query_results = {}
        for query_name in request.queries or []:
            q_res = self._query_executor.execute_query_with_language_name(
                parse_result.tree,
                ts_language,
                query_name,
                parse_result.source_code,
                language,
            )
            query_results[query_name] = _query_captures_or_result(q_res)
        return query_results

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

    @staticmethod
    def _create_empty_result(
        file_path: str, language: str, error: str | None = None
    ) -> Any:
        """Create empty result on failure"""
        return AnalysisResult(
            file_path=file_path,
            language=language,
            success=False,
            error_message=error,
            elements=[],
            analysis_time=0.0,
        )


def _query_captures_or_result(query_result: Any) -> Any:
    if isinstance(query_result, dict) and "captures" in query_result:
        return query_result["captures"]
    return query_result
