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
without target, making it a common file (low lift).  ``total_commits`` is the
ACTUAL number of unique commit SHAs seen in the parsed log (not ``max_commits``),
so a 43-commit repo with max_commits=500 gets the true lift (RFC-0014 INFO fix).

Results are keyed by (project_root, target_file, HEAD) for zero-cost repeat
calls within one MCP session (LRU maxsize=256).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from ....utils.test_detection import is_test_file
from .change_impact_git import _run_git

# Module-level LRU cache keyed by (project_root, target_file, HEAD_sha).
# Invalidated when HEAD advances; no persistent storage.
# maxsize=256: bounds memory in long-running MCP sessions (RFC-0014 §P3-2).
_CO_CHANGE_CACHE_MAXSIZE = 256
_CO_CHANGE_CACHE: OrderedDict[tuple[str, str, str], dict[str, Any]] = OrderedDict()

# Minimum commits touching the target file required before the result may
# claim "Safe to edit in isolation".  Below this floor the null-result is
# statistically meaningless: a 3-commit sample cannot prove independence.
# Chosen at 10: association lift P(A∩B)/(P(A)·P(B)) is unreliable at n<10
# (RFC-0014 §honesty, issue #469).
MIN_COMMITS_FOR_COUPLING_ANALYSIS = 10


def _co_change_cache_get(
    key: tuple[str, str, str],
) -> dict[str, Any] | None:
    """LRU get: move hit to end (most-recently-used)."""
    if key not in _CO_CHANGE_CACHE:
        return None
    _CO_CHANGE_CACHE.move_to_end(key)
    return _CO_CHANGE_CACHE[key]


def _co_change_cache_put(
    key: tuple[str, str, str],
    value: dict[str, Any],
) -> None:
    """LRU put: evict oldest entry if at capacity."""
    if key in _CO_CHANGE_CACHE:
        _CO_CHANGE_CACHE.move_to_end(key)
    _CO_CHANGE_CACHE[key] = value
    if len(_CO_CHANGE_CACHE) > _CO_CHANGE_CACHE_MAXSIZE:
        _CO_CHANGE_CACHE.popitem(last=False)  # evict LRU (oldest)


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
    commits_analyzed: int,
    candidates_below_threshold: int,
) -> dict[str, Any]:
    """Build the agent_summary dict for a co_change result.

    Honesty layering (issue #469):
    1. Small-sample guard: n < MIN_COMMITS_FOR_COUPLING_ANALYSIS -> say
       "insufficient history"; NEVER "Safe to edit in isolation".
    2. Filtered-evidence visibility: empty co_changed_files with nonzero
       candidates_below_threshold -> acknowledge filtered signals exist.
    3. "Safe to edit in isolation" only when: n >= floor AND no candidates.
    """
    if coupled:
        top = coupled[0]["file"]
        lift = coupled[0]["lift"]
        return {
            "next_step": (
                f"When editing {target_file}, also review {top} (lift={lift}).  "
                f"{len(coupled)} co-changed peer(s) total."
            ),
        }

    # No coupled files above threshold.
    if commits_analyzed < MIN_COMMITS_FOR_COUPLING_ANALYSIS:
        return {
            "next_step": (
                f"Insufficient history for coupling analysis "
                f"(n={commits_analyzed} commits in window, minimum is "
                f"{MIN_COMMITS_FOR_COUPLING_ANALYSIS}).  "
                "Treat as unknown, not safe — the sample is too small to "
                "distinguish no coupling from undetected coupling."
            ),
        }

    if candidates_below_threshold > 0:
        return {
            "next_step": (
                f"{target_file} has no strongly coupled peers above the "
                f"co-occurrence threshold, but {candidates_below_threshold} "
                f"candidate(s) were filtered as below-threshold weak signals.  "
                "Review those manually before editing in isolation."
            ),
        }

    # Adequate sample AND truly no candidates at all.
    return {
        "next_step": (
            f"{target_file} has no strongly coupled peer files in this window.  "
            "Safe to edit in isolation."
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
    cached = _co_change_cache_get(cache_key)
    if cached is not None:
        return cached

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
        _co_change_cache_put(cache_key, result)
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
    #   all_shas: every unique commit SHA seen in the log
    #   target_shas: SHAs of commits that include target_file
    #   file_commit_sets[f]: SHAs of ALL commits that include file f
    all_shas: set[str] = set()
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
            all_shas.add(current_sha)
        elif current_sha is not None:
            if stripped == target_file:
                target_shas.add(current_sha)
            elif not is_test_file(stripped):
                file_commit_sets.setdefault(stripped, set()).add(current_sha)

    if not target_shas:
        result = _empty_co_change_result(target_file, max_commits)
        _co_change_cache_put(cache_key, result)
        return result

    # 4. True association lift
    # lift = P(A^B) / (P(A) * P(B))
    #      = (shared_commits / total) / ((target_count/total) * (peer_count/total))
    #      = (shared_commits * total_commits) / (target_count * peer_count)
    #
    # total_commits = actual commits parsed from the log (resolves RFC open
    # question 3 — using max_commits as the denominator inflates lift when
    # the repo has fewer commits than the window, e.g. a 43-commit repo with
    # max_commits=500 would give a lift ~11.6× too high).
    total_commits = len(all_shas)
    target_freq_count = len(target_shas)

    coupled: list[dict[str, Any]] = []
    candidates_below_threshold = 0
    for peer, peer_all_shas in file_commit_sets.items():
        # shared = commits where BOTH target and peer changed
        shared_shas = target_shas & peer_all_shas
        shared = len(shared_shas)
        if shared < min_shared:
            # Count peers that co-changed but didn't clear the threshold
            # (shared >= 1 means there was genuine co-change, just too rare).
            if shared >= 1:
                candidates_below_threshold += 1
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
    commits_analyzed = len(target_shas)

    result = {
        "success": True,
        "target": target_file,
        "commits_analyzed": commits_analyzed,
        "window": f"last {max_commits} commits",
        "co_changed_files": top,
        "candidates_below_threshold": candidates_below_threshold,
        "truncated": truncated,
        "agent_summary": _build_co_change_summary(
            target_file, top, commits_analyzed, candidates_below_threshold
        ),
    }
    _co_change_cache_put(cache_key, result)
    return result
