"""Helper functions for project statistics resource generation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
from tree_sitter_analyzer.encoding_utils import read_file_safe

SupportedFilePredicate = Callable[[Path], bool]
LanguageResolver = Callable[[Path], str]


def require_project_dir(project_path: str | None) -> Path:
    """Return the configured project directory or raise the legacy error."""
    if project_path is None:
        raise ValueError("Project path is not set")
    return Path(project_path)


def current_timestamp() -> str:
    """Return a consistent timestamp for stats responses."""
    return datetime.now().isoformat()


def iter_supported_code_files(
    project_dir: Path,
    is_supported_file: SupportedFilePredicate,
) -> list[Path]:
    """Collect supported code files under a project directory."""
    return [
        file_path
        for file_path in project_dir.rglob("*")
        if file_path.is_file() and is_supported_file(file_path)
    ]


def read_line_count(
    file_path: Path,
    *,
    logger: logging.Logger,
    failure_message: str,
    default: int | None,
) -> int | None:
    """Read a file line count with caller-selected failure behavior."""
    try:
        content, _ = read_file_safe(file_path)
    except Exception as exc:
        logger.debug(f"{failure_message}: {file_path} ({exc})")
        return default
    return len(content.splitlines())


def collect_overview_scan(
    project_dir: Path,
    is_supported_file: SupportedFilePredicate,
    get_language: LanguageResolver,
    *,
    logger: logging.Logger,
) -> tuple[int, int, dict[str, int]]:
    """Collect file, line, and language counts for overview stats."""
    total_files = 0
    total_lines = 0
    language_counts: dict[str, int] = {}

    for file_path in iter_supported_code_files(project_dir, is_supported_file):
        total_files += 1
        line_count = read_line_count(
            file_path,
            logger=logger,
            failure_message="Skipping unreadable file during overview scan",
            default=None,
        )
        if line_count is None:
            continue

        total_lines += line_count
        language = get_language(file_path)
        if language != "unknown":
            language_counts[language] = language_counts.get(language, 0) + 1

    return total_files, total_lines, language_counts


def build_overview_stats(
    project_path: str | None,
    total_files: int,
    total_lines: int,
    language_counts: dict[str, int],
) -> dict[str, Any]:
    """Build the public overview response payload."""
    return {
        "total_files": total_files,
        "total_lines": total_lines,
        "languages": list(language_counts),
        "project_path": project_path,
        "last_updated": current_timestamp(),
    }


def collect_language_scan(
    project_dir: Path,
    is_supported_file: SupportedFilePredicate,
    get_language: LanguageResolver,
    *,
    logger: logging.Logger,
) -> tuple[int, dict[str, dict[str, int]]]:
    """Collect per-language file and line counts."""
    total_lines = 0
    language_data: dict[str, dict[str, int]] = {}

    for file_path in iter_supported_code_files(project_dir, is_supported_file):
        line_count = read_line_count(
            file_path,
            logger=logger,
            failure_message="Failed to count lines",
            default=0,
        )
        file_lines = line_count if line_count is not None else 0
        total_lines += file_lines

        language = get_language(file_path)
        if language == "unknown":
            continue
        data = language_data.setdefault(language, {"file_count": 0, "line_count": 0})
        data["file_count"] += 1
        data["line_count"] += file_lines

    return total_lines, language_data


def build_languages_list(
    total_lines: int, language_data: dict[str, dict[str, int]]
) -> list[dict[str, Any]]:
    """Convert language counters to the public list format."""
    languages = []
    for language, data in language_data.items():
        percentage = (
            round((data["line_count"] / total_lines) * 100, 2)
            if total_lines > 0
            else 0.0
        )
        languages.append(
            {
                "name": language,
                "file_count": data["file_count"],
                "line_count": data["line_count"],
                "percentage": percentage,
            }
        )
    return languages


def build_languages_stats(languages_list: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the public languages response payload."""
    return {
        "languages": languages_list,
        "total_languages": len(languages_list),
        "last_updated": current_timestamp(),
    }


def java_analysis_complexity(file_analysis: Any) -> int:
    """Extract complexity from Java analysis result shapes."""
    if file_analysis and hasattr(file_analysis, "methods"):
        return sum(method.complexity_score or 0 for method in file_analysis.methods)
    if file_analysis and hasattr(file_analysis, "elements"):
        methods = [
            element
            for element in file_analysis.elements
            if hasattr(element, "complexity_score")
        ]
        return sum(getattr(method, "complexity_score", 0) or 0 for method in methods)
    return 0


def analysis_result_complexity(file_analysis_result: Any) -> int:
    """Extract total complexity from the generic analysis result shape."""
    if not (file_analysis_result and file_analysis_result.success):
        return 0
    analysis_dict = file_analysis_result.to_dict()
    metrics = analysis_dict.get("metrics")
    if not isinstance(metrics, dict):
        return 0
    complexity = metrics.get("complexity")
    if not isinstance(complexity, dict):
        return 0
    value = complexity.get("total", 0)
    return value if isinstance(value, int) else 0


async def file_complexity(
    file_path: Path,
    language: str,
    analysis_engine: Any,
) -> int:
    """Analyze a single file and return its total complexity."""
    if language == "java":
        return java_analysis_complexity(
            await analysis_engine.analyze_file_async(str(file_path))
        )

    request = AnalysisRequest(file_path=str(file_path), language=language)
    return analysis_result_complexity(await analysis_engine.analyze(request))


async def collect_complexity_data(
    project_dir: Path,
    analysis_engine: Any,
    is_supported_file: SupportedFilePredicate,
    get_language: LanguageResolver,
    *,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    """Analyze supported files and collect positive complexity scores."""
    complexity_data = []
    for file_path in iter_supported_code_files(project_dir, is_supported_file):
        try:
            language = get_language(file_path)
            complexity = await file_complexity(file_path, language, analysis_engine)
        except Exception as exc:
            logger.warning(f"Failed to analyze complexity for {file_path}: {exc}")
            continue

        if complexity > 0:
            complexity_data.append(
                {
                    "file": str(file_path.relative_to(project_dir)),
                    "language": language,
                    "complexity": complexity,
                }
            )
    return complexity_data


def build_complexity_stats(complexity_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the public complexity response payload."""
    complexities = [
        int(cast(int, item.get("complexity", 0))) for item in complexity_data
    ]
    file_count = len(complexities)
    total_complexity = sum(complexities)
    avg_complexity = total_complexity / file_count if file_count > 0 else 0
    max_complexity = max(complexities, default=0)

    return {
        "average_complexity": round(avg_complexity, 2),
        "max_complexity": max_complexity,
        "total_files_analyzed": file_count,
        "files_by_complexity": sorted(
            complexity_data,
            key=lambda x: int(cast(int, x.get("complexity", 0))),
            reverse=True,
        ),
        "last_updated": current_timestamp(),
    }


def collect_files_data(
    project_dir: Path,
    is_supported_file: SupportedFilePredicate,
    get_language: LanguageResolver,
    *,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    """Collect per-file metadata for supported code files."""
    files_data = []
    for file_path in iter_supported_code_files(project_dir, is_supported_file):
        try:
            file_stats = file_path.stat()
            line_count = read_line_count(
                file_path,
                logger=logger,
                failure_message="Failed to count lines",
                default=0,
            )
            files_data.append(
                {
                    "path": str(file_path.relative_to(project_dir)),
                    "language": get_language(file_path),
                    "line_count": line_count if line_count is not None else 0,
                    "size_bytes": file_stats.st_size,
                    "modified": datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
                }
            )
        except Exception as exc:
            logger.warning(f"Failed to get stats for {file_path}: {exc}")
            continue
    return files_data


def build_files_stats(files_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the public files response payload."""
    return {
        "files": sorted(
            files_data,
            key=lambda x: int(cast(int, x.get("line_count", 0))),
            reverse=True,
        ),
        "total_count": len(files_data),
        "last_updated": current_timestamp(),
    }
