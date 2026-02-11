"""
Typed contracts for MCP tool arguments and results.

Replaces dict[str, Any] in execute() signatures with explicit TypedDicts
so that callers and implementations share a well-defined schema.

Usage:
    from tree_sitter_analyzer_v2.mcp.tools.types import (
        AnalyzeArgs, AnalyzeResult,
        ScaleArgs, ScaleResult,
        ...
    )
"""

from __future__ import annotations

from typing import Any, TypedDict


# ── Shared ──


class ToolErrorResult(TypedDict):
    """Standard error response from any tool."""

    success: bool  # always False
    error: str
    error_code: str


class MetaEnvelope(TypedDict, total=False):
    """Metadata envelope attached to JSON-RPC responses (not in business result)."""

    timing_ms: float


# ── analyze_code_structure ──


class AnalyzeArgs(TypedDict, total=False):
    """Arguments for analyze_code_structure tool."""

    file_path: str
    output_format: str  # "toon" | "markdown"


class AnalyzeResult(TypedDict, total=False):
    """Result from analyze_code_structure tool."""

    success: bool
    language: str
    output_format: str
    data: str
    error: str | None


# ── check_code_scale ──


class ScaleArgs(TypedDict, total=False):
    """Arguments for check_code_scale tool."""

    file_path: str
    file_paths: list[str]
    metrics_only: bool
    include_details: bool
    include_guidance: bool
    output_format: str  # "toon" | "markdown"


class ScaleResult(TypedDict, total=False):
    """Result from check_code_scale tool."""

    success: bool
    file_path: str
    language: str
    total_lines: int
    total_characters: int
    file_size_bytes: int
    classes_count: int
    functions_count: int
    imports_count: int
    guidance: str
    structural_overview: dict[str, Any]
    toon_content: str
    error: str | None


# ── query_code ──


class QueryFilters(TypedDict, total=False):
    """Filters for query_code tool."""

    name: str
    use_regex: bool
    visibility: str
    class_name: str


class QueryArgs(TypedDict, total=False):
    """Arguments for query_code tool."""

    file_path: str
    element_type: str  # "classes" | "functions" | "methods" | "imports"
    filters: QueryFilters
    output_format: str  # "toon" | "markdown"


class QueryResult(TypedDict, total=False):
    """Result from query_code tool."""

    success: bool
    file_path: str
    language: str
    element_type: str
    count: int
    results: list[dict[str, Any]]
    toon_content: str
    error: str | None


# ── extract_code_section ──


class ExtractSectionSpec(TypedDict, total=False):
    """Specification for a single section extraction."""

    start_line: int
    end_line: int


class ExtractBatchFileRequest(TypedDict, total=False):
    """Single file batch request for extract_code_section."""

    file_path: str
    sections: list[ExtractSectionSpec]


class ExtractArgs(TypedDict, total=False):
    """Arguments for extract_code_section tool."""

    # Single mode
    file_path: str
    start_line: int
    end_line: int
    # Batch mode
    requests: list[ExtractBatchFileRequest]
    # Common
    output_format: str  # "toon" | "markdown"


class ExtractResult(TypedDict, total=False):
    """Result from extract_code_section tool."""

    success: bool
    file_path: str
    start_line: int
    end_line: int
    total_lines: int
    content: str
    error: str | None


# ── find_files ──


class FindFilesArgs(TypedDict, total=False):
    """Arguments for find_files tool."""

    root_dir: str
    pattern: str
    file_type: str


class FindFilesResult(TypedDict, total=False):
    """Result from find_files tool."""

    success: bool
    files: list[str]
    count: int
    error: str | None


# ── search_content ──


class SearchContentArgs(TypedDict, total=False):
    """Arguments for search_content tool."""

    root_dir: str
    query: str
    file_type: str
    case_sensitive: bool
    is_regex: bool
    max_results: int
    output_format: str  # "toon" | "markdown"


class SearchContentResult(TypedDict, total=False):
    """Result from search_content tool."""

    success: bool
    matches: list[dict[str, Any]]
    count: int
    truncated: bool
    toon_content: str
    error: str | None


# ── find_and_grep ──


class FindAndGrepArgs(TypedDict, total=False):
    """Arguments for find_and_grep tool."""

    roots: list[str]
    pattern: str
    extensions: list[str]
    query: str
    case_sensitive: bool
    is_regex: bool
    output_format: str  # "toon" | "markdown"


class FindAndGrepResult(TypedDict, total=False):
    """Result from find_and_grep tool."""

    success: bool
    files_found: int
    matches: list[dict[str, Any]]
    count: int
    toon_content: str
    error: str | None


# ── code_intelligence ──


class IntelligenceArgs(TypedDict, total=False):
    """Arguments for code_intelligence tool."""

    action: str
    project_path: str
    name: str
    query: str
    max_tokens: int
    max_depth: int
    extensions: list[str]
    limit: int


class IntelligenceResult(TypedDict, total=False):
    """Result from code_intelligence tool."""

    success: bool
    total_files: int
    total_symbols: int
    total_classes: int
    total_functions: int
    total_lines: int
    toon: str
    error: str | None
    error_code: str


# ── analyze_code_graph ──


class AnalyzeCodeGraphArgs(TypedDict, total=False):
    """Arguments for analyze_code_graph tool."""

    file_path: str
    directory: str
    include_patterns: list[str]
    exclude_patterns: list[str]
    cross_file: bool
    output_format: str  # "toon" | "markdown"


class AnalyzeCodeGraphResult(TypedDict, total=False):
    """Result from analyze_code_graph tool."""

    success: bool
    modules: int
    classes: int
    functions: int
    calls: int
    toon_content: str
    error: str | None
