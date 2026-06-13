"""Execution helpers for the find_and_grep fd/rg pipeline."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from ..utils.gitignore_detector import get_default_detector
from . import fd_rg_utils

logger = logging.getLogger(__name__)

# Time budget (ms) for the follow-up rg --count-matches pass that resolves
# the real pre-truncation total when ``apply_match_limits`` truncated the
# first pass. Mirrors the H2 fix in search_content_response.py.
RECOUNT_BUDGET_MS = 500


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
    """Build the ripgrep command for the discovered files.

    H5 fix (REQ-U-006): Pass exact file paths as positional arguments to rg.
    ripgrep does NOT support --files-from; appending deduplicated paths after
    the query is the correct way to eliminate parent-dir double-counting.

    For very large file lists the caller should use
    ``build_rg_commands_batched`` which chunks the list to avoid OS
    command-line length limits and merges results.
    """
    no_ignore = bool(arguments.get("no_ignore", False))
    include_globs = arguments.get("include_globs") or []

    return fd_rg_utils.build_rg_command(
        query=arguments["query"],
        case=arguments.get("case", "smart"),
        fixed_strings=bool(arguments.get("fixed_strings", False)),
        word=bool(arguments.get("word", False)),
        multiline=bool(arguments.get("multiline", False)),
        include_globs=include_globs,
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
        roots=None,
        file_paths=files,
        count_only_matches=bool(arguments.get("count_only_matches", False))
        or bool(arguments.get("total_only", False)),
    )


# OS command-line length limit guard: on Windows the practical limit is
# ~8 191 characters; on Linux/macOS ~2 MB.  Use a conservative path-budget
# (characters, not bytes) so we never hit the limit on any platform.
_RG_PATH_CHUNK_CHARS = 6000


def build_rg_commands_batched(
    arguments: dict[str, Any],
    files: list[str],
    *,
    count_only: bool = False,
) -> list[list[str]]:
    """Split a large file list into batches and return one rg command per batch.

    Each batch's total path length stays under ``_RG_PATH_CHUNK_CHARS`` so we
    never exceed OS command-line limits.  For small lists this returns a single
    command identical to ``build_rg_command_from_arguments``.
    """
    if not files:
        return []

    batches: list[list[str]] = []
    current_batch: list[str] = []
    current_len = 0

    for path in files:
        path_len = len(path) + 1  # +1 for the space separator
        if current_batch and current_len + path_len > _RG_PATH_CHUNK_CHARS:
            batches.append(current_batch)
            current_batch = [path]
            current_len = path_len
        else:
            current_batch.append(path)
            current_len += path_len

    if current_batch:
        batches.append(current_batch)

    no_ignore = bool(arguments.get("no_ignore", False))
    include_globs = arguments.get("include_globs") or []

    cmds: list[list[str]] = []
    for batch in batches:
        cmd = fd_rg_utils.build_rg_command(
            query=arguments["query"],
            case=arguments.get("case", "smart"),
            fixed_strings=bool(arguments.get("fixed_strings", False)),
            word=bool(arguments.get("word", False)),
            multiline=bool(arguments.get("multiline", False)),
            include_globs=include_globs,
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
            roots=None,
            file_paths=batch,
            count_only_matches=count_only,
        )
        cmds.append(cmd)
    return cmds


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


def build_rg_recount_command(
    arguments: dict[str, Any],
    files: list[str],
) -> list[str]:
    """Build a ripgrep --count-matches command on the same fd-discovered files.

    Mirrors ``build_rg_command_from_arguments`` but forces ``max_count=None``
    and ``count_only_matches=True`` so the response counts every match (no
    per-file truncation). Used to compute the honest pre-truncation total
    when ``apply_match_limits`` truncated the primary pass.

    H5 fix (REQ-U-006): Passes exact file paths as positional arguments to
    eliminate double-counting.  No temp file needed.
    """
    no_ignore = bool(arguments.get("no_ignore", False))
    include_globs = arguments.get("include_globs") or []

    return fd_rg_utils.build_rg_command(
        query=arguments["query"],
        case=arguments.get("case", "smart"),
        fixed_strings=bool(arguments.get("fixed_strings", False)),
        word=bool(arguments.get("word", False)),
        multiline=bool(arguments.get("multiline", False)),
        include_globs=include_globs,
        exclude_globs=arguments.get("exclude_globs"),
        follow_symlinks=bool(arguments.get("follow_symlinks", False)),
        hidden=bool(arguments.get("hidden", False)),
        no_ignore=no_ignore,
        max_filesize=arguments.get("max_filesize"),
        context_before=None,
        context_after=None,
        encoding=arguments.get("encoding"),
        max_count=None,
        timeout_ms=arguments.get("timeout_ms"),
        roots=None,
        file_paths=files,
        count_only_matches=True,
    )


async def resolve_real_total(
    *,
    truncated: bool,
    displayed_count: int,
    arguments: dict[str, Any],
    files: list[str],
) -> tuple[int, bool]:
    """Return ``(real_total, total_count_known)`` for find_and_grep.

    Mirrors the H2 fix from ``search_content_response._resolve_real_total``:
    when ``truncated`` is True we re-run ripgrep with ``--count-matches`` and
    no ``max_count`` against the same fd-discovered files. If the recount
    exceeds ``RECOUNT_BUDGET_MS`` or fails, return the displayed count with
    ``total_count_known=False`` so callers can surface uncertainty honestly.
    """
    if not truncated:
        return displayed_count, True

    if not files:
        # Nothing to recount over; honest about uncertainty.
        return displayed_count, False

    try:
        cmd = build_rg_recount_command(arguments, files)
        started = time.perf_counter()
        rc, out_bytes, _err = await fd_rg_utils.run_command_capture(
            cmd, timeout_ms=RECOUNT_BUDGET_MS
        )
        recount_ms = int((time.perf_counter() - started) * 1000)

        if rc not in (0, 1):
            logger.debug(
                "find_and_grep recount failed (rc=%s, %sms); dropping to estimate.",
                rc,
                recount_ms,
            )
            return displayed_count, False

        if recount_ms > RECOUNT_BUDGET_MS:
            logger.debug(
                "find_and_grep recount exceeded budget (%sms > %sms); using estimate.",
                recount_ms,
                RECOUNT_BUDGET_MS,
            )
            return displayed_count, False

        file_counts = fd_rg_utils.parse_rg_count_output(out_bytes)
        real_total = int(file_counts.get("__total__", 0))
        if real_total < displayed_count:
            # Defensive: race/IO undercounts — trust visible matches.
            return displayed_count, False
        return real_total, True
    except Exception as exc:  # noqa: BLE001
        logger.debug("find_and_grep recount raised %s; using estimate.", exc)
        return displayed_count, False
