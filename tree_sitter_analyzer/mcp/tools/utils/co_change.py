"""Git-history co-change coupling for the ``nav action=co_change`` facade route.

RFC-0014 Phase C: files that historically change together with X.

Algorithm: single ``git log --pretty=format:%H --name-only`` subprocess
(no ``-- <target_file>`` path-filter so we see ALL commits in the window and
collect both target-commit SHAs and per-file total commit counts in one pass).
Per-file commit-SHA sets give the true association lift:

    lift = P(A^B) / (P(A) * P(B))
         = (shared_commits * total_commits) / (target_commits * peer_commits)

where ``peer_commits`` is the peer's TOTAL commit count in the window, NOT the
shared count -- the two are different precisely when a peer changes often
without target, making it a common file (low lift).

Results are keyed by (project_root, target_file, HEAD) for zero-cost repeat
calls within one MCP session.
"""

from __future__ import annotations

from typing import Any

from ....utils.test_detection import is_test_file
from .change_impact_git import _run_git

# Module-level cache keyed by (project_root, target_file, HEAD_sha).
# Invalidated when HEAD advances; no persistent storage.
_CO_CHANGE_CACHE: dict[tuple[str, str, str], dict[str, Any]] = {}


def _empty_co_change_result(target_file: str, max_commits: int) -> dict[str, Any]:
    """Return a graceful empty result (git unavailable or no history)."""
    return {
        "success": True,
        "target": target_file,
        "commits_analyzed": 0,
        "window": f"last {max_commits} commits",
        "co_changed_files": [],
        "truncated": False,
        "agent_summary": {
            "next_step": (
                "No co-change history found.  "
                "Either this file has no git history in the specified window, "
                "or git is unavailable in this project."
            ),
        },
    }


def _build_co_change_summary(
    target_file: str,
    coupled: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the agent_summary dict for a co_change result."""
    if not coupled:
        return {
            "next_step": (
                f"{target_file} has no strongly coupled peer files in this window.  "
                "Safe to edit in isolation."
            ),
        }
    top = coupled[0]["file"]
    lift = coupled[0]["lift"]
    return {
        "next_step": (
            f"When editing {target_file}, also review {top} (lift={lift}).  "
            f"{len(coupled)} co-changed peer(s) total."
        ),
    }


def _compute_co_change(
    project_root: str,
    target_file: str,
    max_commits: int = 500,
    min_shared: int = 3,
    max_results: int = 20,
) -> dict[str, Any]:
    """Compute git-history co-change coupling for *target_file*.

    Issues exactly TWO git subprocesses:
      1. ``git rev-parse HEAD`` -- cache-key lookup.
      2. ``git log --max-count=N --pretty=format:%H --name-only``
         -- full project log (no path filter) to capture per-file
         total commit counts alongside shared commit counts.

    The full-project log (vs. ``-- <target_file>``) is needed to get
    ``peer_commits`` (the peer's total commit frequency in the window),
    which is the denominator of the lift formula.  Without it all peers
    would have the same lift value.

    Returns a dict matching the ``CoChangeResult`` schema from RFC-0014.
    """
    # 1. HEAD for cache key
    rc_head, head_raw = _run_git(["rev-parse", "HEAD"], cwd=project_root)
    if rc_head != 0:
        # git unavailable
        return _empty_co_change_result(target_file, max_commits)

    head_sha = head_raw.strip()
    cache_key = (project_root, target_file, head_sha)
    if cache_key in _CO_CHANGE_CACHE:
        return _CO_CHANGE_CACHE[cache_key]

    # 2. Single git log pass -- full project history (no path filter)
    rc_log, log_out = _run_git(
        [
            "log",
            f"--max-count={max_commits}",
            "--pretty=format:%H",
            "--name-only",
        ],
        cwd=project_root,
    )

    if rc_log != 0 or not log_out:
        result = _empty_co_change_result(target_file, max_commits)
        _CO_CHANGE_CACHE[cache_key] = result
        return result

    # 3. Parse commit blocks in Python (one subprocess total after rev-parse)
    # Output format (one block per commit, separated by blank lines):
    #   <40-hex SHA>
    #   src/file_a.py
    #   src/file_b.py
    #
    #   <40-hex SHA>
    #   src/file_c.py
    #
    # We collect:
    #   target_shas: SHAs of commits that include target_file
    #   file_commit_sets[f]: SHAs of ALL commits that include file f
    target_shas: set[str] = set()
    file_commit_sets: dict[str, set[str]] = {}  # file -> set of commit SHAs
    current_sha: str | None = None

    for line in log_out.splitlines():
        stripped = line.strip()
        if not stripped:
            current_sha = None
            continue
        # A 40-hex SHA marks the start of a new commit block.
        if len(stripped) == 40 and all(c in "0123456789abcdef" for c in stripped):
            current_sha = stripped
        elif current_sha is not None:
            if stripped == target_file:
                target_shas.add(current_sha)
            elif not is_test_file(stripped):
                file_commit_sets.setdefault(stripped, set()).add(current_sha)

    if not target_shas:
        result = _empty_co_change_result(target_file, max_commits)
        _CO_CHANGE_CACHE[cache_key] = result
        return result

    # 4. True association lift
    # lift = P(A^B) / (P(A) * P(B))
    #      = (shared_commits / total) / ((target_count/total) * (peer_count/total))
    #      = (shared_commits * total_commits) / (target_count * peer_count)
    #
    # total_commits is approximated as max_commits (per RFC open question 3).
    total_commits = max_commits
    target_freq_count = len(target_shas)

    coupled: list[dict[str, Any]] = []
    for peer, peer_all_shas in file_commit_sets.items():
        # shared = commits where BOTH target and peer changed
        shared_shas = target_shas & peer_all_shas
        shared = len(shared_shas)
        if shared < min_shared:
            continue
        peer_freq_count = len(peer_all_shas)  # peer's TOTAL commits in this window
        denom = target_freq_count * peer_freq_count
        lift = round((shared * total_commits) / denom, 2) if denom else 0.0
        coupled.append(
            {
                "file": peer,
                "shared_commits": shared,
                "lift": lift,
            }
        )

    # Sort: lift descending, then shared_commits descending (tie-break).
    coupled.sort(key=lambda x: (-x["lift"], -x["shared_commits"]))
    truncated = len(coupled) > max_results
    top = coupled[:max_results]

    result = {
        "success": True,
        "target": target_file,
        "commits_analyzed": len(target_shas),
        "window": f"last {max_commits} commits",
        "co_changed_files": top,
        "truncated": truncated,
        "agent_summary": _build_co_change_summary(target_file, top),
    }
    _CO_CHANGE_CACHE[cache_key] = result
    return result
