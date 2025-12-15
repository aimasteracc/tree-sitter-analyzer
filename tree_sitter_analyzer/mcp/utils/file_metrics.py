from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ...encoding_utils import read_file_safe
from ...utils import setup_logger
from .shared_cache import get_shared_cache

logger = setup_logger(__name__)


@dataclass(frozen=True)
class FileMetrics:
    total_lines: int
    code_lines: int
    comment_lines: int
    blank_lines: int
    estimated_tokens: int
    file_size_bytes: int
    content_hash: str

    def as_dict(self) -> dict[str, int | str]:
        return {
            "total_lines": self.total_lines,
            "code_lines": self.code_lines,
            "comment_lines": self.comment_lines,
            "blank_lines": self.blank_lines,
            "estimated_tokens": self.estimated_tokens,
            "file_size_bytes": self.file_size_bytes,
            "content_hash": self.content_hash,
        }


_TOKEN_RE = re.compile(r"\b\w+\b|[^\w\s]", re.UNICODE)


def _estimate_tokens(content: str) -> int:
    # Rough approximation used historically in AnalyzeScaleTool
    tokens = _TOKEN_RE.findall(content)
    return len([t for t in tokens if t.strip()])


def _compute_line_metrics(
    content: str, language: str | None
) -> tuple[int, int, int, int]:
    """
    Compute (total_lines, code_lines, comment_lines, blank_lines).

    This logic is based on the more accurate implementation previously located in
    `mcp/server.py` and is intended to be shared by both server and tools.
    """
    lines = content.split("\n")
    total_lines = len(lines)

    # Remove empty line at the end if file ends with newline
    if lines and not lines[-1]:
        total_lines -= 1

    code_lines = 0
    comment_lines = 0
    blank_lines = 0
    in_multiline_comment = False

    for line in lines:
        stripped = line.strip()

        # Blank line
        if not stripped:
            blank_lines += 1
            continue

        # Multi-line comment continuation
        if in_multiline_comment:
            comment_lines += 1
            if "*/" in stripped or (language in {"html", "xml"} and "-->" in stripped):
                in_multiline_comment = False
            continue

        # Multi-line comment start (C/Java-style)
        if stripped.startswith("/**") or stripped.startswith("/*"):
            comment_lines += 1
            if "*/" not in stripped:
                in_multiline_comment = True
            continue

        # Single-line comments
        if stripped.startswith("//"):
            comment_lines += 1
            continue

        # JavaDoc continuation lines (lines starting with * but not */)
        if stripped.startswith("*") and not stripped.startswith("*/"):
            comment_lines += 1
            continue

        # Language-specific single-line comments
        if language == "python" and stripped.startswith("#"):
            comment_lines += 1
            continue
        if language == "sql" and stripped.startswith("--"):
            comment_lines += 1
            continue

        # HTML/XML comment start
        if language in {"html", "xml"} and stripped.startswith("<!--"):
            comment_lines += 1
            if "-->" not in stripped:
                in_multiline_comment = True
            continue

        # Otherwise treat as code
        code_lines += 1

    calculated_total = code_lines + comment_lines + blank_lines
    if calculated_total != total_lines:
        # Adjust code_lines to match total
        code_lines = total_lines - comment_lines - blank_lines
        code_lines = max(0, code_lines)

    return total_lines, code_lines, comment_lines, blank_lines


def compute_file_metrics(
    file_path: str, *, language: str | None = None, project_root: str | None = None
) -> dict[str, int | str]:
    """
    Compute file metrics and cache the result by (project_root, file_path, content_hash).

    Notes:
    - This uses content_hash to guarantee invalidation when file content changes.
    - This still reads file content to compute the fingerprint; caching avoids recomputing
      line classification and token estimation when the content hash is identical.
    """
    try:
        content, _encoding = read_file_safe(file_path)
    except (FileNotFoundError, OSError) as e:
        # Backward-compatible behavior: metrics computation should not raise for missing files
        # in server/tool flows; callers rely on a zeroed metrics dict.
        logger.error(f"Error reading file for metrics {file_path}: {e}")
        return FileMetrics(
            total_lines=0,
            code_lines=0,
            comment_lines=0,
            blank_lines=0,
            estimated_tokens=0,
            file_size_bytes=0,
            content_hash="",
        ).as_dict()

    # Hash normalized unicode content for deterministic cross-platform behavior
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    cache_key = f"{file_path}::{content_hash}"

    shared_cache = get_shared_cache()
    cached = shared_cache.get_metrics(cache_key, project_root=project_root)
    if cached is not None:
        return cached

    file_size_bytes = len(content.encode("utf-8"))
    estimated_tokens = _estimate_tokens(content)
    total_lines, code_lines, comment_lines, blank_lines = _compute_line_metrics(
        content, language
    )

    metrics = FileMetrics(
        total_lines=total_lines,
        code_lines=code_lines,
        comment_lines=comment_lines,
        blank_lines=blank_lines,
        estimated_tokens=estimated_tokens,
        file_size_bytes=file_size_bytes,
        content_hash=content_hash,
    ).as_dict()

    shared_cache.set_metrics(cache_key, metrics, project_root=project_root)
    return metrics
