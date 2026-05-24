"""Analysis request builders — extracted from analysis_engine.py."""

from .request import AnalysisRequest


def build_request_from_params(
    file_path: str,
    language: str | None = None,
    format_type: str | None = None,
    include_details: bool | None = None,
    include_complexity: bool | None = None,
    include_elements: bool | None = None,
    include_queries: bool | None = None,
    queries: list[str] | None = None,
) -> AnalysisRequest:
    """Build an AnalysisRequest from individual parameters."""
    return AnalysisRequest(
        file_path=file_path,
        language=language,
        format_type=format_type or "json",
        include_details=include_details if include_details is not None else False,
        include_complexity=include_complexity
        if include_complexity is not None
        else True,
        include_elements=include_elements if include_elements is not None else True,
        include_queries=include_queries if include_queries is not None else True,
        queries=queries,
    )


def update_request_from_params(
    request: AnalysisRequest,
    language: str | None = None,
    format_type: str | None = None,
    include_details: bool | None = None,
    include_complexity: bool | None = None,
    include_elements: bool | None = None,
    include_queries: bool | None = None,
    queries: list[str] | None = None,
) -> None:
    """Update an existing AnalysisRequest with provided parameters."""
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
