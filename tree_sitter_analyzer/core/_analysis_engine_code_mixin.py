"""Code-string analysis entry points for UnifiedAnalysisEngine."""

import asyncio
import os
import tempfile
from typing import Any

from .request import AnalysisRequest


class UnifiedAnalysisEngineCodeMixin:
    """Compatibility code-analysis methods."""

    async def analyze_code(
        self,
        code: str,
        language: str | None = None,
        filename: str = "string",
        request: AnalysisRequest | None = None,
    ) -> Any:
        """Analyze source code string directly"""
        actual_language = language or "unknown"
        request = _prepare_code_request(request, filename, actual_language, language)
        temp_path = _write_temp_source(code, actual_language)

        try:
            result = await self.analyze(
                _clone_request_for_temp_path(request, temp_path)
            )
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
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.analyze_code(code, language, filename, request))

        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run, self.analyze_code(code, language, filename, request)
            )
            return future.result()


def _prepare_code_request(
    request: AnalysisRequest | None,
    filename: str,
    actual_language: str,
    explicit_language: str | None,
) -> AnalysisRequest:
    if request is None:
        return AnalysisRequest(file_path=filename, language=actual_language)
    if explicit_language:
        request.language = explicit_language
    return request


def _write_temp_source(code: str, language: str) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=f".{language}", delete=False, encoding="utf-8"
    ) as temp_file:
        temp_file.write(code)
        return temp_file.name


def _clone_request_for_temp_path(
    request: AnalysisRequest, temp_path: str
) -> AnalysisRequest:
    return AnalysisRequest(
        file_path=temp_path,
        language=request.language,
        queries=request.queries,
        include_elements=request.include_elements,
        include_queries=request.include_queries,
        include_complexity=request.include_complexity,
        include_details=request.include_details,
        format_type=request.format_type,
    )
