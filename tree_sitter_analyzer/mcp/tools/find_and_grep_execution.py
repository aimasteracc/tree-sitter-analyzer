"""Execution helpers for the find_and_grep fd/rg pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..utils.gitignore_detector import get_default_detector
from . import fd_rg_utils

logger = logging.getLogger(__name__)


def resolve_fd_no_ignore(
    arguments: dict[str, Any],
    project_root: str | None,
    *,
    detector_factory: Any = get_default_detector,
) -> bool:
    """Resolve whether fd should bypass ignore rules for this search."""
    no_ignore = bool(arguments.get("no_ignore", False))
    if no_ignore:
        return True

    detector = detector_factory()
    original_roots = arguments.get("roots", [])
    if not detector.should_use_no_ignore(original_roots, project_root):
        return False

    detection_info = detector.get_detection_info(original_roots, project_root)
    logger.info(
        f"Auto-enabled --no-ignore due to .gitignore interference: "
        f"{detection_info['reason']}"
    )
    return True


def _looks_like_glob(pattern: Any) -> bool:
    """Return True if ``pattern`` looks like a filename glob (``*.py``,
    ``**/test_*.py``, ``foo?.txt``) rather than a regex.

    fd treats unspecified patterns as regex by default; users routinely
    pass ``*.py`` expecting glob, which crashes fd's regex parser. Auto-
    detect the common cases so the tool DTRT without surprising regex
    users (real regex starts with ``^``, ``.``, ``\\``, ``[``, ``(``).
    """
    if not isinstance(pattern, str) or not pattern:
        return False
    # Heuristics: contains ``*``/``?`` but no regex anchors and no escapes
    if "*" not in pattern and "?" not in pattern:
        return False
    if pattern.startswith(("^", "(", "[")) or "\\" in pattern:
        return False
    return True


def build_fd_command_from_arguments(
    arguments: dict[str, Any],
    roots: list[str],
    *,
    fd_limit: int,
    no_ignore: bool,
) -> list[str]:
    """Build the fd command from validated find_and_grep arguments."""
    pattern = arguments.get("pattern")
    # Auto-set glob=True when the pattern obviously means glob.
    glob_explicit = arguments.get("glob")
    glob = (
        bool(glob_explicit) if glob_explicit is not None else _looks_like_glob(pattern)
    )
    return fd_rg_utils.build_fd_command(
        pattern=pattern,
        glob=glob,
        types=arguments.get("types"),
        extensions=arguments.get("extensions"),
        exclude=arguments.get("exclude"),
        depth=arguments.get("depth"),
        follow_symlinks=bool(arguments.get("follow_symlinks", False)),
        hidden=bool(arguments.get("hidden", False)),
        no_ignore=no_ignore,
        size=arguments.get("size"),
        changed_within=arguments.get("changed_within"),
        changed_before=arguments.get("changed_before"),
        full_path_match=bool(arguments.get("full_path_match", False)),
        absolute=True,
        limit=fd_limit,
        roots=roots,
    )


def build_fd_error_response(err: bytes, rc: int) -> dict[str, Any]:
    """Build the error response returned when fd fails."""
    return {
        "success": False,
        "error": err.decode("utf-8", errors="replace").strip() or "fd failed",
        "returncode": rc,
    }


def parse_fd_output(out: bytes, fd_limit: int) -> tuple[list[str], bool]:
    """Parse fd stdout into a capped file list and truncation flag."""
    files = [
        line.strip()
        for line in out.decode("utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    truncated = len(files) > fd_limit
    if truncated:
        files = files[:fd_limit]
    return files, truncated


def sort_files(files: list[str], sort_mode: str | None) -> None:
    """Sort files by path, mtime, or size."""
    if sort_mode not in ("path", "mtime", "size"):
        return
    try:
        if sort_mode == "path":
            files.sort()
        elif sort_mode == "mtime":
            files.sort(
                key=lambda p: Path(p).stat().st_mtime if Path(p).exists() else 0,
                reverse=True,
            )
        elif sort_mode == "size":
            files.sort(
                key=lambda p: Path(p).stat().st_size if Path(p).exists() else 0,
                reverse=True,
            )
    except (OSError, ValueError):  # nosec B110
        pass


def build_rg_command_from_arguments(
    arguments: dict[str, Any],
    files: list[str],
) -> list[str]:
    """Build the ripgrep command for the discovered files."""
    parent_dirs, file_globs = _build_rg_targets(files)
    combined_globs = (arguments.get("include_globs") or []) + file_globs
    no_ignore = bool(arguments.get("no_ignore", False))

    return fd_rg_utils.build_rg_command(
        query=arguments["query"],
        case=arguments.get("case", "smart"),
        fixed_strings=bool(arguments.get("fixed_strings", False)),
        word=bool(arguments.get("word", False)),
        multiline=bool(arguments.get("multiline", False)),
        include_globs=combined_globs,
        exclude_globs=arguments.get("exclude_globs"),
        follow_symlinks=bool(arguments.get("follow_symlinks", False)),
        hidden=bool(arguments.get("hidden", False)),
        no_ignore=no_ignore,
        max_filesize=arguments.get("max_filesize"),
        context_before=arguments.get("context_before"),
        context_after=arguments.get("context_after"),
        encoding=arguments.get("encoding"),
        max_count=arguments.get("max_count"),
        timeout_ms=arguments.get("timeout_ms"),
        roots=list(parent_dirs),
        files_from=None,
        count_only_matches=bool(arguments.get("count_only_matches", False))
        or bool(arguments.get("total_only", False)),
    )


def build_rg_error_response(err: bytes, rc: int) -> dict[str, Any]:
    """Build the error response returned when ripgrep fails."""
    return {
        "success": False,
        "error": err.decode("utf-8", errors="replace").strip() or "ripgrep failed",
        "returncode": rc,
    }


def apply_match_limits(
    matches: list[dict[str, Any]], arguments: dict[str, Any]
) -> tuple[list[dict[str, Any]], bool]:
    """Truncate matches to user max_count or the hard cap."""
    user_max = arguments.get("max_count")
    if user_max is not None and len(matches) > user_max:
        return matches[:user_max], True
    truncated = len(matches) >= fd_rg_utils.MAX_RESULTS_HARD_CAP
    if truncated:
        return matches[: fd_rg_utils.MAX_RESULTS_HARD_CAP], True
    return matches, False


def _build_rg_targets(files: list[str]) -> tuple[set[str], list[str]]:
    """Return parent directories and exact filename globs for ripgrep."""
    parent_dirs: set[str] = set()
    file_globs: list[str] = []
    for file_path in files:
        path = Path(file_path)
        parent_dirs.add(str(path.parent))
        escaped_name = path.name.replace("[", "[[]").replace("]", "[]]")
        file_globs.append(escaped_name)
    return parent_dirs, file_globs
