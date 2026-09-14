"""Pure helper functions for file health scoring."""

import os
import subprocess  # nosec
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path


def read_source_file(path: Path) -> str | None:
    """Return file text, or None when the file cannot be read."""
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def calculate_weighted_total(
    dimensions: Mapping[str, float | None],
    weights: Mapping[str, float],
) -> float:
    """Combine available dimension scores using normalized active weights."""
    total = 0.0
    active_weight_sum = 0.0
    for dimension, score in dimensions.items():
        if score is None:
            continue
        weight = weights.get(dimension, 0) / 100.0
        total += score * weight
        active_weight_sum += weight

    if 0 < active_weight_sum < 1.0:
        return total / active_weight_sum
    return total


def round_available_scores(dimensions: Mapping[str, float | None]) -> dict[str, float]:
    """Round available scores and drop unavailable dimensions."""
    return {
        dimension: round(score, 1)
        for dimension, score in dimensions.items()
        if score is not None
    }


@dataclass(frozen=True)
class GitHistoryContext:
    """Repo root and history completeness, resolved once per project scan.

    Both are properties of the repository, not of a file, but the per-file path
    resolved them with a ``git`` subprocess each: ``rev-parse --show-toplevel``
    and ``rev-parse --is-shallow-repository`` cost ~18 ms of the ~37 ms a file
    spent in git, so a 2,276-file scan paid them 2,276 times for one answer.
    Hoisting them is behaviour-preserving by construction: the per-file
    ``git log -- <path>`` query, which is what the count actually depends on,
    is unchanged.
    """

    repo_root: Path
    complete_history: bool


#: Set by ``HealthScorer.score_project_with_stats`` for the duration of one
#: project scan. ``None`` means "not in a project scan", and the per-file path
#: resolves both values itself.
_PROJECT_GIT_CONTEXT: ContextVar[GitHistoryContext | None] = ContextVar(
    "project_git_history_context", default=None
)


def project_git_context(context: GitHistoryContext | None) -> object:
    """Install the scan-scoped git context and return its reset token."""
    return _PROJECT_GIT_CONTEXT.set(context)


def reset_project_git_context(token: object) -> None:
    """Restore the previous scan-scoped git context."""
    _PROJECT_GIT_CONTEXT.reset(token)  # type: ignore[arg-type]


def resolve_git_history_context(project_root: str | Path) -> GitHistoryContext | None:
    """Resolve repo root and history completeness once, for a whole scan.

    Returns ``None`` when the path is not in a git repository, which is also
    what the per-file path reports.
    """
    root = find_git_root(Path(project_root))
    if root is None:
        return None
    return GitHistoryContext(repo_root=root, complete_history=is_complete_history(root))


def calculate_git_hotspot(
    file_path: str,
    low_commit_threshold: int,
    high_commit_threshold: int,
    *,
    context: GitHistoryContext | None = None,
) -> float | None:
    """Score a file by recent git commit frequency.

    ``context`` is resolved once per project scan and passed explicitly. A
    ``ContextVar`` alone is not enough: ``ThreadPoolExecutor`` workers do not
    inherit the submitting thread's context, and the prefetch submits every file
    to that pool, so the per-file resolution would survive in exactly the place
    that matters.
    """
    path = Path(file_path).resolve()
    repo_root: Path | None
    complete_history: bool | None
    if context is None:
        context = _PROJECT_GIT_CONTEXT.get()
    if context is not None:
        repo_root = context.repo_root
        complete_history = context.complete_history
    else:
        repo_root = find_git_root(path.parent)
        if repo_root is None:
            return None
        complete_history = None

    try:
        pathspec = str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return None

    commit_count = count_recent_commits(
        repo_root, pathspec, complete_history=complete_history
    )
    if commit_count is None:
        return None

    return score_commit_frequency(
        commit_count,
        low_commit_threshold,
        high_commit_threshold,
    )


def find_git_root(start_dir: Path) -> Path | None:
    """Return the git repository root for start_dir."""
    result = subprocess.run(  # nosec
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        cwd=str(start_dir),
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def is_complete_history(repo_root: Path) -> bool:
    """Whether the repository has full history (not a shallow clone).

    2026-09-09：浅克隆的少量可见提交不能作为稳定满分的依据。
    """
    history = subprocess.run(  # nosec
        ["git", "rev-parse", "--is-shallow-repository"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        cwd=str(repo_root),
        env=_history_env(),
    )
    return history.returncode == 0 and history.stdout.strip() == "false"


def _history_env() -> dict[str, str]:
    return {
        **os.environ,
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_GRAFT_FILE": os.devnull,
    }


def count_recent_commits(
    repo_root: Path,
    pathspec: str,
    *,
    complete_history: bool | None = None,
) -> int | None:
    """仅在历史完整时统计最近九十天修改指定路径的提交。

    ``complete_history`` lets a project scan supply the shallow probe it already
    performed; ``None`` means resolve it here, which is the per-file path.
    """
    history_env = _history_env()
    if complete_history is None:
        complete_history = is_complete_history(repo_root)
    if not complete_history:
        return None
    result = subprocess.run(  # nosec
        [
            "git",
            "--no-replace-objects",
            "log",
            "--format=%H",
            "--after=90 days ago",
            "--",
            pathspec,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        cwd=str(repo_root),
        env=history_env,
    )
    if result.returncode != 0:
        return None
    return len([line for line in result.stdout.strip().splitlines() if line])


def score_commit_frequency(
    commit_count: int,
    low_commit_threshold: int,
    high_commit_threshold: int,
) -> float:
    """Convert recent commit count into a 0-100 stability score."""
    if commit_count <= low_commit_threshold:
        return 100.0
    if commit_count >= high_commit_threshold:
        return 0.0
    ratio = (commit_count - low_commit_threshold) / (
        high_commit_threshold - low_commit_threshold
    )
    return max(0.0, 100.0 * (1.0 - ratio))
