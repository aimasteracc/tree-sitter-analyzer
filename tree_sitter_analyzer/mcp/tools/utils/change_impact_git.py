"""Git diff readers for change-impact analysis."""

from __future__ import annotations

import subprocess  # nosec B404

from .._graph_cache_fingerprint import _EXCLUDE_DIRS as _PROJECT_EXCLUDE_DIRS


def _path_is_excluded(path: str) -> bool:
    """Return True when ``path`` lies inside a tool-owned / cache directory.

    K6: ``analyze_change_impact`` reported its own cache artefacts
    (``.ast-cache/index.db``, ``.tree-sitter-cache/project-index.json``) as
    "changed files", inflating ``changed_count``, ``affected_count`` and the
    risk grade even when the user only touched source. We drop any path that
    has a segment matching the canonical project-wide exclude list (the same
    one the dependency graph + project overview honour).
    """
    normalized = path.replace("\\", "/")
    parts = [segment for segment in normalized.split("/") if segment]
    return any(segment in _PROJECT_EXCLUDE_DIRS for segment in parts)


def _filter_excluded_paths(paths: list[str]) -> list[str]:
    """Drop paths that live inside tool-owned cache directories (K6).

    Order is preserved so caller-visible ``changed_files`` matches the
    git output for non-cache files.
    """
    return [p for p in paths if not _path_is_excluded(p)]


def _run_git(args: list[str], cwd: str | None = None) -> tuple[int, str]:
    """Run a git subprocess and return (returncode, stdout)."""
    try:
        result = subprocess.run(  # nosec B603
            ["git"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            timeout=10,
        )
        return result.returncode, result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 1, ""


def _split_git_lines(output: str) -> list[str]:
    """Split git output into non-empty path lines."""
    return [line for line in output.splitlines() if line.strip()]


def _unique_preserve_order(paths: list[str]) -> list[str]:
    """Return paths without duplicates while preserving git output order."""
    seen = set()
    unique_paths = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique_paths.append(path)
    return unique_paths


def _normalize_scope_paths(scope_paths: list[str] | None) -> list[str]:
    """Normalize optional git pathspecs while preserving caller order."""
    if not scope_paths:
        return []
    return _unique_preserve_order([path for path in scope_paths if path])


def _with_pathspec(args: list[str], scope_paths: list[str] | None) -> list[str]:
    """Append git pathspec arguments when the caller requests scoped output."""
    normalized_scope = _normalize_scope_paths(scope_paths)
    if not normalized_scope:
        return args
    return [*args, "--", *normalized_scope]


def _get_untracked_files(
    project_root: str | None, scope_paths: list[str] | None = None
) -> list[str]:
    """Get untracked files that are not ignored by git."""
    rc, out = _run_git(
        _with_pathspec(["ls-files", "--others", "--exclude-standard"], scope_paths),
        cwd=project_root,
    )
    if rc != 0 or not out:
        return []
    # K6: ``git ls-files --others`` honours .gitignore, but the project may
    # still have tool-owned cache directories committed (or tracked) — drop
    # those defensively so they never surface as untracked "changes".
    return _filter_excluded_paths(_split_git_lines(out))


def _get_changed_files(
    mode: str, project_root: str | None, scope_paths: list[str] | None = None
) -> list[str]:
    """Get list of changed file paths from git diff."""
    if mode == "staged":
        rc, out = _run_git(
            _with_pathspec(["diff", "--cached", "--name-only"], scope_paths),
            cwd=project_root,
        )
    elif mode == "branch":
        rc, out = _run_git(
            _with_pathspec(["diff", "--name-only", "HEAD~1", "HEAD"], scope_paths),
            cwd=project_root,
        )
    else:
        rc, out = _run_git(
            _with_pathspec(["diff", "--name-only"], scope_paths),
            cwd=project_root,
        )

    changed = _split_git_lines(out) if rc == 0 and out else []
    if mode == "diff":
        changed.extend(_get_untracked_files(project_root, scope_paths))
    # K6: filter tool-owned cache artefacts before dedup so we don't
    # spend O(N) memory on rows we're about to drop.
    return _unique_preserve_order(_filter_excluded_paths(changed))


def _get_diff_stat(
    mode: str, project_root: str | None, scope_paths: list[str] | None = None
) -> str:
    """Get diff stat summary from git."""
    if mode == "staged":
        rc, out = _run_git(
            _with_pathspec(["diff", "--cached", "--stat"], scope_paths),
            cwd=project_root,
        )
    elif mode == "branch":
        rc, out = _run_git(
            _with_pathspec(["diff", "--stat", "HEAD~1", "HEAD"], scope_paths),
            cwd=project_root,
        )
    else:
        rc, out = _run_git(
            _with_pathspec(["diff", "--stat"], scope_paths),
            cwd=project_root,
        )
        untracked = _get_untracked_files(project_root, scope_paths)
        if untracked:
            untracked_stat = "\n".join(
                ["Untracked files:"] + [f"  {path}" for path in untracked[:20]]
            )
            out = f"{out}\n{untracked_stat}".strip() if out else untracked_stat
    return out if rc == 0 else ""
