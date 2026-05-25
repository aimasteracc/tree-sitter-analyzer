"""Pure helper functions for file health scoring."""

import subprocess  # nosec
from collections.abc import Mapping
from pathlib import Path


def read_source_file(path: Path) -> str | None:
    """Return file text, or None when the file cannot be read."""
    if not path.exists():
        return None
    try:
        return path.read_text()
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


def calculate_git_hotspot(
    file_path: str,
    low_commit_threshold: int,
    high_commit_threshold: int,
) -> float | None:
    """Score a file by recent git commit frequency."""
    path = Path(file_path).resolve()
    repo_root = find_git_root(path.parent)
    if repo_root is None:
        return None

    try:
        pathspec = str(path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        return None

    commit_count = count_recent_commits(repo_root, pathspec)
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


def count_recent_commits(repo_root: Path, pathspec: str) -> int | None:
    """Count commits touching pathspec in the last 90 days."""
    result = subprocess.run(  # nosec
        [
            "git",
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
