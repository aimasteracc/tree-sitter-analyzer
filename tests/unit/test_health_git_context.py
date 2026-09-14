"""The repo root and history state are resolved once per project scan.

Both are properties of the repository, not of a file, but the per-file path
asked git for them per file: `git rev-parse --show-toplevel` and
`git rev-parse --is-shallow-repository` cost ~18 ms of the ~37 ms each file
spent in git, so a 2,276-file scan paid them 2,276 times for two constants.

Measured on this repository: `find_git_root` calls 2,277 -> 1, cold
`health action=project` 49.1 s -> 26.0 s, warm unchanged at ~4.5 s.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tree_sitter_analyzer import health_scorer as health
from tree_sitter_analyzer.registry import health_scorer_helpers as helpers

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="requires git on PATH"
)


def _git_repo(root: Path, files: int = 6) -> None:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    for index in range(files):
        (root / f"f{index}.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env={**env})
    subprocess.run(
        ["git", "commit", "-q", "-m", "add sources"], cwd=root, check=True, env={**env}
    )


def _counting_find_git_root(monkeypatch) -> list:
    calls: list = []
    real = helpers.find_git_root

    def counting(start_dir):
        calls.append(start_dir)
        return real(start_dir)

    monkeypatch.setattr(helpers, "find_git_root", counting)
    return calls


def test_the_repo_root_is_resolved_once_for_the_whole_scan(tmp_path, monkeypatch):
    _git_repo(tmp_path)
    calls = _counting_find_git_root(monkeypatch)

    scores, _stats = health.HealthScorer().score_project_with_stats(
        str(tmp_path), use_cache=False
    )

    assert len(scores) == 6
    assert len(calls) == 1, (
        f"the repository root was resolved {len(calls)} times for "
        f"{len(scores)} files; it is a property of the repository and must be "
        "resolved once per scan, or every file pays a git subprocess for it"
    )
    assert all(score.dimensions.get("git_hotspot") is not None for score in scores)


def test_the_scan_still_scores_git_hotspot_inside_a_repository(tmp_path, monkeypatch):
    """Hoisting the probes must not skip the query that produces the score."""
    _git_repo(tmp_path)
    _counting_find_git_root(monkeypatch)
    seen: list[str] = []
    real_count = helpers.count_recent_commits

    def counting_count(repo_root, pathspec, *, complete_history=None):
        seen.append(pathspec)
        return real_count(repo_root, pathspec, complete_history=complete_history)

    monkeypatch.setattr(helpers, "count_recent_commits", counting_count)

    scores, _stats = health.HealthScorer().score_project_with_stats(
        str(tmp_path), use_cache=False
    )

    assert sorted(seen) == [f"f{index}.py" for index in range(6)], (
        "every file must still get its own churn query; only the two per-repo "
        "probes are hoisted"
    )
    assert all(score.dimensions["git_hotspot"] == 100.0 for score in scores)


def test_a_directory_outside_a_repository_keeps_the_per_file_fallback(
    tmp_path, monkeypatch
):
    """No repository means no context, and the per-file path must still run."""
    (tmp_path / "solo.py").write_text("value = 1\n", encoding="utf-8")
    calls = _counting_find_git_root(monkeypatch)

    scores, _stats = health.HealthScorer().score_project_with_stats(
        str(tmp_path), use_cache=False
    )

    assert len(scores) == 1
    assert scores[0].dimensions.get("git_hotspot") is None
    # Exactly two: one scan-level resolution that finds no repository, then one
    # from the per-file fallback. Pinned rather than bounded so that a fallback
    # which stops running — and a score that is then reported as unavailable
    # rather than computed — cannot pass.
    assert len(calls) == 2, (
        f"expected one scan-level resolution plus one per-file fallback, saw "
        f"{len(calls)}; a non-repository scan must still attempt the query"
    )
