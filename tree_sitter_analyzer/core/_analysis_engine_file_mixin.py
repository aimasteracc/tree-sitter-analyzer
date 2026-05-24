"""File analysis entry points for UnifiedAnalysisEngine."""

from typing import Any

from .request import AnalysisRequest
from .request_builder import build_request_from_params, update_request_from_params


class UnifiedAnalysisEngineFileMixin:
    """Compatibility file-analysis methods."""

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
        """Compatibility alias for analyze with additional parameters."""
        if request is None:
            request = build_request_from_params(
                file_path=file_path,
                language=language,
                format_type=format_type,
                include_details=include_details,
                include_complexity=include_complexity,
                include_elements=include_elements,
                include_queries=include_queries,
                queries=queries,
            )
        else:
            update_request_from_params(
                request,
                language=language,
                format_type=format_type,
                include_details=include_details,
                include_complexity=include_complexity,
                include_elements=include_elements,
                include_queries=include_queries,
                queries=queries,
            )
        return await self.analyze(request)

    async def analyze_file_async(
        self,
        file_path: str,
        language: str | None = None,
        request: AnalysisRequest | None = None,
    ) -> Any:
        """Compatibility alias for analyze"""
        return await self.analyze_file(file_path, language, request)
