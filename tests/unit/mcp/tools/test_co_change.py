"""Tests for ``nav action=co_change`` -- RFC-0014 Phase C.

All tests written RED-first (before implementation).
Tests the _compute_co_change function directly and via the nav facade.

Key design decisions from the RFC:
- ONE git log subprocess + one rev-parse (2 total, never a per-commit loop).
- True lift formula: (shared * total_commits) / (target_commits * peer_commits)
- Per-HEAD caching: second call with same (project, file, HEAD) skips subprocess.
- Test files excluded from peer list by default.
- Degrades gracefully (success=True, empty list) when git unavailable.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade
from tree_sitter_analyzer.mcp.tools.utils.co_change import (
    _CO_CHANGE_CACHE,
    _CO_CHANGE_CACHE_MAXSIZE,
    _compute_co_change,
)

# ---------------------------------------------------------------------------
# Helpers: build synthetic git log output
# ---------------------------------------------------------------------------


def _make_git_log(commits: list[tuple[str, list[str]]]) -> str:
    """Build fake ``git log --pretty=format:%H --name-only`` output.

    ``commits`` is a list of (sha, [filenames]) pairs.  Blocks are
    separated by blank lines exactly as the real git output.
    """
    blocks: list[str] = []
    for sha, files in commits:
        block_lines = [sha] + files
        blocks.append("\n".join(block_lines))
    return "\n\n".join(blocks)


def _sha(n: int) -> str:
    """Return a deterministic 40-hex SHA for test n."""
    return format(n, "040x")


# ---------------------------------------------------------------------------
# 1. Basic coupling and lift formula
# ---------------------------------------------------------------------------


def test_basic_coupling_exact_lift() -> None:
    """Peer sharing 5 of 10 target commits, peer_commits=5 ->
    lift = (5 * 10) / (10 * 5) = 1.0 exactly.

    RFC worked example (symmetric case).
    """
    commits = [(_sha(i), ["src/handler.py", "src/schema.py"]) for i in range(5)] + [
        (_sha(i + 5), ["src/handler.py"]) for i in range(5)
    ]
    git_log_out = _make_git_log(commits)
    head_sha = "a" * 40

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),  # rev-parse HEAD
            (0, git_log_out),  # git log
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change("/fake/repo", "src/handler.py", max_commits=10)

    assert result["success"] is True
    assert result["commits_analyzed"] == 10
    peers = result["co_changed_files"]
    schema = next(f for f in peers if f["file"] == "src/schema.py")
    assert schema["shared_commits"] == 5
    assert schema["lift"] == 1.0


def test_different_peers_get_different_lifts() -> None:
    """RFC two-peer differential proof:
    total=100, target_commits=20, schema.py peer_commits=10 shared=8 -> lift=4.0;
    handler.py peer_commits=40 shared=8 -> lift=1.0.

    Proves lift is NOT a per-query constant -- each peer gets its own frequency.
    """
    # Build commits so (full-project log, no -- target_file filter):
    #   target.py appears in commits 0..7 + 10..21 = 20 total
    #   schema.py appears in commits 0..7 + 8..9   = 10 total (8 shared with target)
    #   handler.py appears in commits 0..7 + 22..53 = 40 total (8 shared with target)
    commits: list[tuple[str, list[str]]] = []

    # Commits 0..7: all three files (shared = 8 for both peers)
    for i in range(8):
        commits.append((_sha(i), ["src/target.py", "src/schema.py", "src/handler.py"]))
    # Commits 8..9: schema.py solo (2 more schema commits -> total schema=10)
    for i in range(8, 10):
        commits.append((_sha(i), ["src/schema.py"]))
    # Commits 10..21: target.py solo (12 more target commits -> total target=8+12=20)
    for i in range(10, 22):
        commits.append((_sha(i), ["src/target.py"]))
    # Commits 22..53: handler.py solo (32 more handler commits -> total handler=8+32=40)
    for i in range(22, 54):
        commits.append((_sha(i), ["src/handler.py"]))
    # Commits 54..99: filler (other files)
    for i in range(54, 100):
        commits.append((_sha(i), ["src/other.py"]))

    git_log_out = _make_git_log(commits)
    head_sha = "b" * 40

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change("/fake/repo", "src/target.py", max_commits=100)

    assert result["success"] is True
    peers = {f["file"]: f for f in result["co_changed_files"]}
    schema = peers["src/schema.py"]
    handler = peers["src/handler.py"]
    assert schema["shared_commits"] == 8
    assert handler["shared_commits"] == 8
    # lift = (shared * total) / (target_count * peer_count)
    # schema: (8 * 100) / (20 * 10) = 4.0
    assert schema["lift"] == 4.0
    # handler: (8 * 100) / (20 * 40) = 1.0
    assert handler["lift"] == 1.0
    # schema must rank above handler (higher lift first)
    schema_idx = next(
        i
        for i, f in enumerate(result["co_changed_files"])
        if f["file"] == "src/schema.py"
    )
    handler_idx = next(
        i
        for i, f in enumerate(result["co_changed_files"])
        if f["file"] == "src/handler.py"
    )
    assert schema_idx < handler_idx


# ---------------------------------------------------------------------------
# 2. No git repo -> graceful degradation
# ---------------------------------------------------------------------------


def test_no_git_repo_returns_empty() -> None:
    """git exit code != 0 -> success=True, commits_analyzed=0, co_changed_files=[].

    Per RFC error handling: 'Never surface an error envelope -- the caller asked
    a valid question; the data is simply absent.'
    """
    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.return_value = (128, "")
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change("/no/git", "src/foo.py")

    assert result["success"] is True
    assert result["commits_analyzed"] == 0
    assert result["co_changed_files"] == []


def test_git_log_failure_after_head_returns_empty() -> None:
    """HEAD rev-parse succeeds but git log fails -> graceful empty result.

    Covers the rc_log != 0 path (line 188-190): different from the HEAD-failure
    path -- here git is available but log subprocess fails (e.g. shallow clone).
    """
    head_sha = "a1" * 20
    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),  # rev-parse HEAD succeeds
            (128, ""),  # git log fails (e.g. shallow clone error)
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change("/shallow/repo", "src/foo.py")

    assert result["success"] is True
    assert result["commits_analyzed"] == 0
    assert result["co_changed_files"] == []


# ---------------------------------------------------------------------------
# 3. Cache: second call with same (project, file, HEAD) skips subprocess
# ---------------------------------------------------------------------------


def test_cache_hit_skips_subprocess() -> None:
    """Second call with same (project, file, HEAD) hits cache.

    Total _run_git calls across TWO _compute_co_change calls == 3:
      call 1: rev-parse (first call)
      call 2: git log (first call, populates cache)
      call 3: rev-parse (second call, same HEAD -> cache hit, no log call)
    NOT 4 (no second git log).
    """
    commits = [(_sha(i), ["src/handler.py", "src/schema.py"]) for i in range(3)]
    git_log_out = _make_git_log(commits)
    head_sha = "c" * 40

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),  # call 1: rev-parse
            (0, git_log_out),  # call 2: git log
            (0, head_sha),  # call 3: rev-parse for second _compute_co_change
            # call 4 would be second git log -- must NOT happen
        ]
        _CO_CHANGE_CACHE.clear()
        result1 = _compute_co_change("/fake/repo", "src/handler.py", max_commits=10)
        result2 = _compute_co_change("/fake/repo", "src/handler.py", max_commits=10)

    # Only 3 calls: rev-parse + log + rev-parse (cache hit avoids second log)
    assert mock_run_git.call_count == 3
    assert result1["co_changed_files"] == result2["co_changed_files"]


# ---------------------------------------------------------------------------
# 4. min_shared filter
# ---------------------------------------------------------------------------


def test_min_shared_filter_excludes_rare_peers() -> None:
    """peer_b with shared=1 < min_shared=3 excluded; peer_a with shared=5 included."""
    commits = (
        [(_sha(i), ["src/foo.py", "src/peer_a.py"]) for i in range(5)]
        + [(_sha(5), ["src/foo.py", "src/peer_b.py"])]
        + [(_sha(i + 6), ["src/foo.py"]) for i in range(4)]
    )
    git_log_out = _make_git_log(commits)
    head_sha = "d" * 40

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change("/repo", "src/foo.py", max_commits=10, min_shared=3)

    files = [c["file"] for c in result["co_changed_files"]]
    assert "src/peer_a.py" in files
    assert "src/peer_b.py" not in files


# ---------------------------------------------------------------------------
# 5. Test files excluded from peer list by default
# ---------------------------------------------------------------------------


def test_test_files_excluded_from_peers() -> None:
    """Test-file peers are excluded by default (co_change is about production coupling)."""
    commits = [
        (_sha(i), ["src/target.py", "tests/test_target.py", "src/peer.py"])
        for i in range(5)
    ]
    git_log_out = _make_git_log(commits)
    head_sha = "e" * 40

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change("/repo", "src/target.py", max_commits=10)

    files = [c["file"] for c in result["co_changed_files"]]
    assert "tests/test_target.py" not in files
    assert "src/peer.py" in files


# ---------------------------------------------------------------------------
# 6. No target commits -> empty result
# ---------------------------------------------------------------------------


def test_no_target_commits_returns_empty() -> None:
    """File with no history -> success=True, commits_analyzed=0, empty list."""
    # git log returns output with only unrelated files (target file never appears)
    commits = [(_sha(i), ["src/other.py"]) for i in range(5)]
    git_log_out = _make_git_log(commits)
    head_sha = "f" * 40

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change("/repo", "src/foo.py", max_commits=10)

    assert result["success"] is True
    assert result["commits_analyzed"] == 0
    assert result["co_changed_files"] == []


# ---------------------------------------------------------------------------
# 7. max_results truncation
# ---------------------------------------------------------------------------


def test_max_results_truncation() -> None:
    """When more peers than max_results -> truncated=True, list capped."""
    n_peers = 25
    commits = [
        (_sha(i), ["src/target.py"] + [f"src/peer_{j}.py" for j in range(n_peers)])
        for i in range(5)
    ] + [(_sha(i + 5), ["src/target.py"]) for i in range(5)]
    git_log_out = _make_git_log(commits)
    head_sha = "9" * 40

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change(
            "/repo", "src/target.py", max_commits=10, max_results=20
        )

    assert result["truncated"] is True
    assert len(result["co_changed_files"]) == 20


# ---------------------------------------------------------------------------
# 8. Single subprocess latency invariant (Rule-11 executable invariant)
# ---------------------------------------------------------------------------


def test_single_subprocess_structural_invariant() -> None:
    """RFC structural invariant: exactly 2 _run_git calls (rev-parse + single log).

    The implementation must never issue a per-commit subprocess loop.
    This is the structural guard; the real-repo timing invariant is in
    test_real_repo_co_change_under_2s below.
    """
    commits = [(_sha(i), ["src/target.py", "src/peer.py"]) for i in range(50)]
    git_log_out = _make_git_log(commits)
    head_sha = "0a" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change("/real/repo", "src/target.py", max_commits=50)

    assert result["success"] is True
    # Exactly 2 calls: rev-parse + single git log (no per-commit loop)
    assert mock_run_git.call_count == 2


# ---------------------------------------------------------------------------
# 9. result includes agent_summary
# ---------------------------------------------------------------------------


def test_result_includes_agent_summary() -> None:
    """co_change result must include agent_summary dict for downstream routing."""
    commits = [(_sha(i), ["src/handler.py", "src/schema.py"]) for i in range(5)]
    git_log_out = _make_git_log(commits)
    head_sha = "aa" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change("/repo", "src/handler.py", max_commits=10)

    assert "agent_summary" in result
    assert isinstance(result["agent_summary"], dict)


# ---------------------------------------------------------------------------
# 10. nav facade integration: co_change action dispatches correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nav_facade_co_change_action_dispatches() -> None:
    """nav execute({action: co_change, file_path: ...}) routes to _co_change_route."""
    commits = [(_sha(i), ["src/handler.py", "src/schema.py"]) for i in range(5)]
    git_log_out = _make_git_log(commits)
    head_sha = "bb" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        facade = build_nav_facade(project_root=None)
        result = await facade.execute(
            {
                "action": "co_change",
                "file_path": "src/handler.py",
                "output_format": "json",
            }
        )

    assert result["success"] is True
    assert result["target"] == "src/handler.py"
    peers = {f["file"]: f for f in result["co_changed_files"]}
    assert "src/schema.py" in peers


@pytest.mark.asyncio
async def test_nav_facade_co_change_requires_symbol_or_file_path() -> None:
    """co_change requires symbol OR file_path; missing both -> success=False."""
    facade = build_nav_facade(project_root=None)
    result = await facade.execute({"action": "co_change"})
    assert result["success"] is False
    assert "required" in result.get("error", "").lower()


@pytest.mark.asyncio
async def test_nav_facade_co_change_output_format_toon() -> None:
    """output_format=toon -> toon_content key present (TOON wrapper applied)."""
    commits = [(_sha(i), ["src/target.py", "src/peer.py"]) for i in range(5)]
    git_log_out = _make_git_log(commits)
    head_sha = "cc" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        facade = build_nav_facade(project_root=None)
        result = await facade.execute(
            {
                "action": "co_change",
                "file_path": "src/target.py",
                "output_format": "toon",
            }
        )

    assert "toon_content" in result
    assert result.get("format") == "toon"
    assert result["success"] is True


@pytest.mark.asyncio
async def test_nav_facade_co_change_default_output_format_is_toon() -> None:
    """MCP house rule: default output_format for co_change is toon -- LOCKED sec.1."""
    commits = [(_sha(i), ["src/target.py", "src/peer.py"]) for i in range(5)]
    git_log_out = _make_git_log(commits)
    head_sha = "dd" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        facade = build_nav_facade(project_root=None)
        result = await facade.execute(
            {"action": "co_change", "file_path": "src/target.py"}
        )

    assert "toon_content" in result
    assert result.get("format") == "toon"


# ---------------------------------------------------------------------------
# 11. Schema / action enum includes co_change
# ---------------------------------------------------------------------------


def test_nav_facade_schema_action_enum_includes_co_change() -> None:
    """Schema action enum must include co_change so agents can discover it."""
    facade = build_nav_facade(project_root=None)
    schema = facade.get_tool_schema()
    enum = set(schema["properties"]["action"]["enum"])
    assert "co_change" in enum


# ---------------------------------------------------------------------------
# 12. NEW_ACTION_PARITY contains nav_co_change
# ---------------------------------------------------------------------------


def test_nav_co_change_in_new_action_parity() -> None:
    """nav_co_change lives in NEW_ACTION_PARITY with --co-change CLI flag."""
    from tree_sitter_analyzer.mcp.facade_map import LEGACY_TOOL_MAP, NEW_ACTION_PARITY

    assert "nav_co_change" in NEW_ACTION_PARITY
    assert "nav_co_change" not in LEGACY_TOOL_MAP
    facade, action, cli_flag = NEW_ACTION_PARITY["nav_co_change"]
    assert facade == "nav"
    assert action == "co_change"
    assert cli_flag == "--co-change"


# ---------------------------------------------------------------------------
# 13. CLI parity: --co-change flag exists in argument parser
# ---------------------------------------------------------------------------


def test_cli_co_change_flag_exists() -> None:
    """--co-change must be registered in the argument parser."""
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    flags = {s for a in parser._actions for s in a.option_strings if s.startswith("--")}
    assert "--co-change" in flags


# ---------------------------------------------------------------------------
# 14. _NAV_DESCRIPTION mentions co_change
# ---------------------------------------------------------------------------


def test_nav_description_mentions_co_change() -> None:
    """_NAV_DESCRIPTION must include co_change so agents can discover the action."""
    from tree_sitter_analyzer.mcp.tools.nav_facade import _NAV_DESCRIPTION

    assert "co_change" in _NAV_DESCRIPTION


# ---------------------------------------------------------------------------
# 15. Server instructions mention co_change
# ---------------------------------------------------------------------------


def test_server_instructions_mention_co_change() -> None:
    """MCP server instructions must document co_change."""
    from tree_sitter_analyzer.mcp._server_helpers import _SERVER_INSTRUCTIONS

    assert "co_change" in _SERVER_INSTRUCTIONS


# ---------------------------------------------------------------------------
# 16. co_change is a bespoke route (not action_map)
# ---------------------------------------------------------------------------


def test_co_change_action_in_bespoke_map() -> None:
    """co_change must be registered as a bespoke route (NOT action_map)."""
    facade = build_nav_facade(project_root=None)
    assert "co_change" in facade.bespoke_map
    assert "co_change" not in facade.action_map


# ---------------------------------------------------------------------------
# 17. window string format is correct
# ---------------------------------------------------------------------------


def test_window_string_format() -> None:
    """result['window'] must be 'last N commits' where N == max_commits."""
    commits = [(_sha(i), ["src/target.py"]) for i in range(3)]
    git_log_out = _make_git_log(commits)
    head_sha = "ee" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change("/repo", "src/target.py", max_commits=77)

    assert result["window"] == "last 77 commits"


# ---------------------------------------------------------------------------
# 18. Sorted by lift descending
# ---------------------------------------------------------------------------


def test_sorted_by_lift_descending() -> None:
    """co_changed_files must be sorted by lift descending."""
    # schema_a: lift=4.0 (shared=8, peer_count=10)
    # handler_b: lift=1.0 (shared=8, peer_count=40)
    # rare_c: lift=2.0 (shared=4, peer_count=10) -> 4*100/(20*10)=2.0
    commits: list[tuple[str, list[str]]] = []
    for i in range(8):
        commits.append(
            (_sha(i), ["src/target.py", "src/schema_a.py", "src/handler_b.py"])
        )
    for i in range(8, 10):
        commits.append((_sha(i), ["src/schema_a.py"]))
    for i in range(10, 14):
        commits.append((_sha(i), ["src/target.py", "src/rare_c.py"]))
    for i in range(14, 20):
        commits.append((_sha(i), ["src/rare_c.py"]))
    for i in range(20, 26):
        commits.append((_sha(i), ["src/target.py"]))
    for i in range(26, 58):
        commits.append((_sha(i), ["src/handler_b.py"]))
    for i in range(58, 100):
        commits.append((_sha(i), ["src/other.py"]))

    git_log_out = _make_git_log(commits)
    head_sha = "ff" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change(
            "/repo", "src/target.py", max_commits=100, min_shared=3
        )

    lifts = [f["lift"] for f in result["co_changed_files"]]
    assert lifts == sorted(lifts, reverse=True)
    files = [f["file"] for f in result["co_changed_files"]]
    assert files.index("src/schema_a.py") < files.index("src/rare_c.py")
    assert files.index("src/rare_c.py") < files.index("src/handler_b.py")


# ---------------------------------------------------------------------------
# 19. INFO fix: actual commit count denominator (not max_commits)
# ---------------------------------------------------------------------------


def test_lift_uses_actual_commit_count_not_max_commits() -> None:
    """lift denominator = actual parsed commits, NOT max_commits.

    Regression test for the INFO finding: a repo with 10 commits and
    max_commits=500 must NOT inflate lift by 500/10=50×.

    Setup:
      10 commits total in the log (commits 0-9)
      target.py in commits 0-4 (5 commits)
      peer.py   in commits 0-4 (5 commits, all shared with target)

    Correct lift = (5 * 10) / (5 * 5) = 2.0
    Inflated (wrong) lift = (5 * 500) / (5 * 5) = 100.0
    """
    commits = [(_sha(i), ["src/target.py", "src/peer.py"]) for i in range(5)] + [
        (_sha(i + 5), ["src/other.py"]) for i in range(5)
    ]
    git_log_out = _make_git_log(commits)
    head_sha = "19" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change(
            "/repo", "src/target.py", max_commits=500, min_shared=3
        )

    assert result["success"] is True
    peers = {f["file"]: f for f in result["co_changed_files"]}
    assert "src/peer.py" in peers
    peer = peers["src/peer.py"]
    # actual total = 10 commits; max_commits = 500
    # correct lift = (5 * 10) / (5 * 5) = 2.0
    assert peer["lift"] == 2.0


# ---------------------------------------------------------------------------
# 20. P3-2 cache bound: LRU evicts oldest when maxsize exceeded
# ---------------------------------------------------------------------------


def test_lru_cache_evicts_at_maxsize() -> None:
    """Cache must not grow beyond _CO_CHANGE_CACHE_MAXSIZE entries."""
    from tree_sitter_analyzer.mcp.tools.utils.co_change import (
        _co_change_cache_put,
    )

    _CO_CHANGE_CACHE.clear()
    sentinel: dict = {"success": True, "co_changed_files": []}

    # Fill to exactly maxsize
    for i in range(_CO_CHANGE_CACHE_MAXSIZE):
        _co_change_cache_put((f"/repo{i}", "f.py", f"sha{i:040x}"), sentinel)

    assert len(_CO_CHANGE_CACHE) == _CO_CHANGE_CACHE_MAXSIZE

    # One more entry must evict the oldest
    _co_change_cache_put(("/repo_new", "f.py", "a" * 40), sentinel)
    assert len(_CO_CHANGE_CACHE) == _CO_CHANGE_CACHE_MAXSIZE
    # oldest key evicted
    assert ("/repo0", "f.py", f"{'0' * 40}") not in _CO_CHANGE_CACHE

    _CO_CHANGE_CACHE.clear()


# ---------------------------------------------------------------------------
# 21. P2-2 REAL timing: actual git repo, wall-clock < 2.0 s (Rule-11 invariant)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "fixture builds 10 real git commits; Windows runner subprocess spawn "
        "is ~1.4s each (14.4s measured on CI 2026-06-11) — the rule-11 "
        "invariant is the wall-clock of _compute_co_change itself, which the "
        "linux/macos axes cover; the structural call_count==2 invariant is "
        "platform-independent and runs everywhere"
    ),
)
def test_real_repo_co_change_under_2s(tmp_path: Path) -> None:  # noqa: F821
    """Rule-11: _compute_co_change on a ~10-commit real git repo completes < 2.0 s.

    Builds a real git repo with 10 commits (target.py + peer.py alternate),
    invokes _compute_co_change against real git, and asserts wall-clock < 2.0 s.
    Documented bound: 2.0 s (RFC-0014 Rule-11; single git subprocess).
    """
    import shutil
    import subprocess
    import time

    if shutil.which("git") is None:
        import pytest as _pytest

        _pytest.skip("git not available")

    repo = tmp_path / "repo"
    repo.mkdir()

    def _git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
            env={
                **__import__("os").environ,
                "GIT_TEMPLATE_DIR": "",
                "GIT_CONFIG_NOSYSTEM": "1",
            },
            timeout=10,
        )

    _git("init", "--initial-branch=main")
    _git("config", "user.email", "test@example.com")
    _git("config", "user.name", "Test")
    _git("config", "commit.gpgsign", "false")

    target = repo / "src" / "target.py"
    peer = repo / "src" / "peer.py"
    other = repo / "src" / "other.py"
    target.parent.mkdir(parents=True, exist_ok=True)

    for i in range(10):
        target.write_text(f"# target v{i}\n", encoding="utf-8")
        if i % 2 == 0:
            peer.write_text(f"# peer v{i}\n", encoding="utf-8")
            _git("add", "src/target.py", "src/peer.py")
        else:
            other.write_text(f"# other v{i}\n", encoding="utf-8")
            _git("add", "src/target.py", "src/other.py")
        _git("commit", "-m", f"commit {i}")

    _CO_CHANGE_CACHE.clear()
    start = time.monotonic()
    result = _compute_co_change(str(repo), "src/target.py", max_commits=500)
    elapsed = time.monotonic() - start

    assert result["success"] is True
    assert result["commits_analyzed"] == 10
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# 22. P3-1 CLI execution: --co-change dispatches via _handle_nav_actions
# ---------------------------------------------------------------------------


def test_cli_co_change_execution_dispatches(tmp_path: Path) -> None:  # noqa: F821
    """--co-change FILE_OR_SYMBOL must route through handle_nav_actions and
    return a result dict (success key present) — not fall through as unhandled.

    We mock build_nav_facade.execute to avoid a real git call; the test verifies
    the dispatch path is wired (not just the argparse flag).
    """
    import argparse
    import asyncio
    from unittest.mock import AsyncMock
    from unittest.mock import patch as _patch

    from tree_sitter_analyzer.cli.nav_special_commands import handle_nav_actions
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext

    captured: list[dict] = []

    def _output_json(data: dict) -> None:
        captured.append(data)

    ctx = SpecialCommandContext(
        asyncio_run=asyncio.run,
        output_json=_output_json,
        output_error=lambda msg: None,
        output_info=lambda msg: None,
        output_list=lambda msg: None,
        query_loader=None,
    )

    args = argparse.Namespace(
        co_change="src/target.py",
        test_map=None,
        co_change_max_commits=500,
        project_root=str(tmp_path),
        output_format="json",
    )

    fake_result = {
        "success": True,
        "target": "src/target.py",
        "commits_analyzed": 0,
        "co_changed_files": [],
        "truncated": False,
        "agent_summary": {"next_step": "ok"},
        "window": "last 500 commits",
    }

    with _patch(
        "tree_sitter_analyzer.mcp.tools.nav_facade.build_nav_facade"
    ) as mock_build:
        mock_facade = mock_build.return_value
        mock_facade.execute = AsyncMock(return_value=fake_result)
        rc = handle_nav_actions(args, ctx)

    assert rc == 0
    assert len(captured) == 1
    assert captured[0]["success"] is True
    assert captured[0]["target"] == "src/target.py"


# ---------------------------------------------------------------------------
# 23. P3-1 CLI execution: --test-map dispatches via _handle_nav_actions
# ---------------------------------------------------------------------------


def test_cli_test_map_execution_dispatches(tmp_path: Path) -> None:  # noqa: F821
    """--test-map SYMBOL must route through handle_nav_actions and return a
    result dict (success key present) — not fall through as unhandled.

    We mock build_nav_facade.execute to avoid a real graph call.
    """
    import argparse
    import asyncio
    from unittest.mock import AsyncMock
    from unittest.mock import patch as _patch

    from tree_sitter_analyzer.cli.nav_special_commands import handle_nav_actions
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext

    captured: list[dict] = []

    def _output_json(data: dict) -> None:
        captured.append(data)

    ctx = SpecialCommandContext(
        asyncio_run=asyncio.run,
        output_json=_output_json,
        output_error=lambda msg: None,
        output_info=lambda msg: None,
        output_list=lambda msg: None,
        query_loader=None,
    )

    args = argparse.Namespace(
        test_map="my_function",
        co_change=None,
        test_map_file=None,
        project_root=str(tmp_path),
        output_format="json",
    )

    fake_result = {
        "success": True,
        "symbol": "my_function",
        "test_files": [],
        "test_functions": [],
        "edge_count": 0,
        "unique_function_count": 0,
        "truncated": False,
        "agent_summary": {"next_step": "ok"},
    }

    with _patch(
        "tree_sitter_analyzer.mcp.tools.nav_facade.build_nav_facade"
    ) as mock_build:
        mock_facade = mock_build.return_value
        mock_facade.execute = AsyncMock(return_value=fake_result)
        rc = handle_nav_actions(args, ctx)

    assert rc == 0
    assert len(captured) == 1
    assert captured[0]["success"] is True
    assert captured[0]["symbol"] == "my_function"


# ---------------------------------------------------------------------------
# 24. co_change symbol resolution: symbol -> file via call graph
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nav_facade_co_change_resolves_symbol_to_file_via_call_graph() -> None:
    """When symbol= is given, attempt to resolve via call graph (lines 362-366).

    Tests the symbol resolution path in the try/except block.
    When symbol resolution succeeds, target_file is set to resolved file_path.
    """
    from unittest.mock import MagicMock

    commits = [(_sha(i), ["src/target.py", "src/peer.py"]) for i in range(5)]
    git_log_out = _make_git_log(commits)
    head_sha = "gg" * 20

    # Mock the resolve target to simulate successful symbol resolution
    mock_target = MagicMock()
    mock_target.file_path = "src/resolved_target.py"
    mock_graph = MagicMock()
    mock_graph.resolve_targets.return_value = [mock_target]

    with (
        patch(
            "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
        ) as mock_run_git,
        patch(
            "tree_sitter_analyzer.mcp.tools.codegraph_impact_tool.CodeGraphImpactTool"
        ) as MockImpactTool,
    ):
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        # Setup the mock to return our prepared call graph
        mock_impact_instance = MagicMock()
        mock_impact_instance.get_call_graph.return_value = mock_graph
        MockImpactTool.return_value = mock_impact_instance

        _CO_CHANGE_CACHE.clear()
        facade = build_nav_facade(project_root=None)
        # Pass symbol without file_path; should trigger resolution path
        result = await facade.execute(
            {
                "action": "co_change",
                "symbol": "my_function",
                "output_format": "json",
            }
        )

    assert result["success"] is True
    assert result["target"] == "src/resolved_target.py"


@pytest.mark.asyncio
async def test_nav_facade_co_change_symbol_fallback_when_resolution_fails() -> None:
    """When symbol resolution fails, fall back to treating symbol as file path."""
    commits = [(_sha(i), ["src/handler.py", "src/schema.py"]) for i in range(5)]
    git_log_out = _make_git_log(commits)
    head_sha = "hh" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        facade = build_nav_facade(project_root=None)
        result = await facade.execute(
            {
                "action": "co_change",
                "symbol": "nonexistent_symbol",
                "output_format": "json",
            }
        )

    assert result["success"] is True
    assert result["commits_analyzed"] == 0


# ---------------------------------------------------------------------------
# 25. CLI error handling: --co-change with exception
# ---------------------------------------------------------------------------


def test_cli_co_change_execution_handles_exception() -> None:
    """--co-change must handle exceptions gracefully and return error code 1."""
    import argparse
    import asyncio
    from unittest.mock import AsyncMock
    from unittest.mock import patch as _patch

    from tree_sitter_analyzer.cli.nav_special_commands import handle_nav_actions
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext

    errors_captured: list[str] = []

    def _capture_error(msg: str) -> None:
        errors_captured.append(msg)

    ctx = SpecialCommandContext(
        asyncio_run=asyncio.run,
        output_json=lambda data: None,
        output_error=_capture_error,
        output_info=lambda msg: None,
        output_list=lambda msg: None,
        query_loader=None,
    )

    args = argparse.Namespace(
        co_change="src/target.py",
        test_map=None,
        co_change_max_commits=500,
        project_root="/tmp/test",
        output_format="json",
    )

    with _patch(
        "tree_sitter_analyzer.mcp.tools.nav_facade.build_nav_facade"
    ) as mock_build:
        mock_facade = mock_build.return_value
        mock_facade.execute = AsyncMock(side_effect=RuntimeError("Test error"))
        rc = handle_nav_actions(args, ctx)

    assert rc == 1
    assert len(errors_captured) > 0
    assert "Test error" in errors_captured[0]


# ---------------------------------------------------------------------------
# 26. CLI output format: JSON output path
# ---------------------------------------------------------------------------


def test_cli_co_change_json_output_format() -> None:
    """--co-change with output_format=json must call output_json (not print toon)."""
    import argparse
    import asyncio
    from unittest.mock import AsyncMock
    from unittest.mock import patch as _patch

    from tree_sitter_analyzer.cli.nav_special_commands import handle_nav_actions
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext

    json_captured: list[dict] = []

    def _capture_json(data: dict) -> None:
        json_captured.append(data)

    ctx = SpecialCommandContext(
        asyncio_run=asyncio.run,
        output_json=_capture_json,
        output_error=lambda msg: None,
        output_info=lambda msg: None,
        output_list=lambda msg: None,
        query_loader=None,
    )

    args = argparse.Namespace(
        co_change="src/target.py",
        test_map=None,
        co_change_max_commits=500,
        project_root="/fake/repo",
        output_format="json",
    )

    fake_result = {
        "success": True,
        "target": "src/target.py",
        "commits_analyzed": 0,
        "co_changed_files": [],
        "truncated": False,
        "agent_summary": {"next_step": "ok"},
        "window": "last 500 commits",
    }

    with _patch(
        "tree_sitter_analyzer.mcp.tools.nav_facade.build_nav_facade"
    ) as mock_build:
        mock_facade = mock_build.return_value
        mock_facade.execute = AsyncMock(return_value=fake_result)
        rc = handle_nav_actions(args, ctx)

    assert rc == 0
    assert len(json_captured) == 1
    assert json_captured[0]["target"] == "src/target.py"


# ---------------------------------------------------------------------------
# 27. CLI output format: TOON output path
# ---------------------------------------------------------------------------


def test_cli_co_change_toon_output_format() -> None:
    """--co-change with output_format=toon must extract and print toon_content."""
    import argparse
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from unittest.mock import patch as _patch

    from tree_sitter_analyzer.cli.nav_special_commands import handle_nav_actions
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext

    ctx = SpecialCommandContext(
        asyncio_run=asyncio.run,
        output_json=lambda data: None,
        output_error=lambda msg: None,
        output_info=lambda msg: None,
        output_list=lambda msg: None,
        query_loader=None,
    )

    args = argparse.Namespace(
        co_change="src/target.py",
        test_map=None,
        co_change_max_commits=500,
        project_root="/fake/repo",
        output_format="toon",
    )

    fake_result = {
        "success": True,
        "target": "src/target.py",
        "toon_content": "Target: src/target.py\nPeers: []\n",
        "format": "toon",
    }

    with _patch(
        "tree_sitter_analyzer.mcp.tools.nav_facade.build_nav_facade"
    ) as mock_build:
        mock_facade = mock_build.return_value
        mock_facade.execute = AsyncMock(return_value=fake_result)
        with _patch("sys.stdout", new_callable=MagicMock):
            rc = handle_nav_actions(args, ctx)

    assert rc == 0


# ---------------------------------------------------------------------------
# 28. CLI co_change failure: success=False in result
# ---------------------------------------------------------------------------


def test_cli_co_change_returns_error_code_on_failure() -> None:
    """--co-change with success=False in result must return error code 1."""
    import argparse
    import asyncio
    from unittest.mock import AsyncMock
    from unittest.mock import patch as _patch

    from tree_sitter_analyzer.cli.nav_special_commands import handle_nav_actions
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext

    json_captured: list[dict] = []

    def _capture_json(data: dict) -> None:
        json_captured.append(data)

    ctx = SpecialCommandContext(
        asyncio_run=asyncio.run,
        output_json=_capture_json,
        output_error=lambda msg: None,
        output_info=lambda msg: None,
        output_list=lambda msg: None,
        query_loader=None,
    )

    args = argparse.Namespace(
        co_change="src/target.py",
        test_map=None,
        co_change_max_commits=500,
        project_root="/fake/repo",
        output_format="json",
    )

    fake_result = {
        "success": False,
        "error": "File not found",
    }

    with _patch(
        "tree_sitter_analyzer.mcp.tools.nav_facade.build_nav_facade"
    ) as mock_build:
        mock_facade = mock_build.return_value
        mock_facade.execute = AsyncMock(return_value=fake_result)
        rc = handle_nav_actions(args, ctx)

    assert rc == 1
    assert len(json_captured) == 1


# ---------------------------------------------------------------------------
# 29. _dispatch_test_map helper function with file_path
# ---------------------------------------------------------------------------


def test_cli_test_map_with_file_path() -> None:
    """--test-map --test-map-file should pass file_path to facade."""
    import argparse
    import asyncio
    from unittest.mock import AsyncMock
    from unittest.mock import patch as _patch

    from tree_sitter_analyzer.cli.nav_special_commands import handle_nav_actions
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext

    json_captured: list[dict] = []

    def _capture_json(data: dict) -> None:
        json_captured.append(data)

    ctx = SpecialCommandContext(
        asyncio_run=asyncio.run,
        output_json=_capture_json,
        output_error=lambda msg: None,
        output_info=lambda msg: None,
        output_list=lambda msg: None,
        query_loader=None,
    )

    args = argparse.Namespace(
        test_map="my_function",
        test_map_file="src/mymodule.py",
        co_change=None,
        project_root="/fake/repo",
        output_format="json",
    )

    fake_result = {
        "success": True,
        "symbol": "my_function",
        "test_files": [],
        "test_functions": [],
        "edge_count": 0,
        "unique_function_count": 0,
        "truncated": False,
        "agent_summary": {"next_step": "ok"},
    }

    with _patch(
        "tree_sitter_analyzer.mcp.tools.nav_facade.build_nav_facade"
    ) as mock_build:
        mock_facade = mock_build.return_value
        mock_facade.execute = AsyncMock(return_value=fake_result)
        rc = handle_nav_actions(args, ctx)

    assert rc == 0
    assert len(json_captured) == 1


# ---------------------------------------------------------------------------
# 30. handle_nav_actions returns None when no flags are set
# ---------------------------------------------------------------------------


def test_handle_nav_actions_returns_none_when_no_flags() -> None:
    """handle_nav_actions returns None when neither --test-map nor --co-change set."""
    import argparse
    import asyncio

    from tree_sitter_analyzer.cli.nav_special_commands import handle_nav_actions
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext

    ctx = SpecialCommandContext(
        asyncio_run=asyncio.run,
        output_json=lambda data: None,
        output_error=lambda msg: None,
        output_info=lambda msg: None,
        output_list=lambda msg: None,
        query_loader=None,
    )

    args = argparse.Namespace(
        test_map=None,
        co_change=None,
        project_root="/fake/repo",
        output_format="json",
    )

    result = handle_nav_actions(args, ctx)
    assert result is None


# ---------------------------------------------------------------------------
# 31. Small-sample guard: n < MIN_COMMITS_FOR_COUPLING_ANALYSIS
#     When commits_analyzed < floor, next_step must say "insufficient history"
#     and NEVER say "Safe to edit in isolation".
# ---------------------------------------------------------------------------


def test_small_sample_guard_insufficient_history_next_step() -> None:
    """n=3 commits -> next_step must contain 'insufficient history' and NOT 'Safe to edit'.

    Exact chosen minimum: 10 commits (MIN_COMMITS_FOR_COUPLING_ANALYSIS).
    Rationale: association lift P(A∩B)/(P(A)·P(B)) is statistically
    meaningless at n<10; a null result at n=3 must not claim independence.
    The verdict/next_step must acknowledge it: no evidence ≠ evidence of absence.
    """
    # 3 commits, target in all 3, no peer meets min_shared=3 -> coupled=[]
    # BUT n=3 < 10 -> must say "insufficient history", NOT "Safe to edit in isolation"
    commits = [
        (_sha(0), ["src/target.py", "src/peer_a.py"]),
        (_sha(1), ["src/target.py", "src/peer_b.py"]),
        (_sha(2), ["src/target.py"]),  # solo
    ]
    git_log_out = _make_git_log(commits)
    head_sha = "31" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change(
            "/fake/repo", "src/target.py", max_commits=500, min_shared=3
        )

    assert result["success"] is True
    assert result["commits_analyzed"] == 3
    next_step: str = result["agent_summary"]["next_step"]
    assert "insufficient history" in next_step.lower()
    assert "Safe to edit in isolation" not in next_step


def test_small_sample_guard_adequate_sample_may_say_safe() -> None:
    """n=10 commits AND no candidates at all -> 'Safe to edit in isolation' IS allowed.

    The guard only blocks the safe verdict when the sample is too small.
    An adequate sample with truly no co-changing peers may conclude safety.
    """
    # 10 commits, target always solo -> coupled=[], but n=10 >= 10
    commits = [(_sha(i), ["src/target.py"]) for i in range(10)]
    git_log_out = _make_git_log(commits)
    head_sha = "32" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change(
            "/fake/repo", "src/target.py", max_commits=500, min_shared=3
        )

    assert result["success"] is True
    assert result["commits_analyzed"] == 10
    next_step: str = result["agent_summary"]["next_step"]
    assert "Safe to edit in isolation" in next_step


# ---------------------------------------------------------------------------
# 32. Filtered-evidence visibility: candidates_below_threshold
#     Empty co_changed_files with nonzero below-threshold candidates must
#     carry candidates_below_threshold == exact count in the result.
# ---------------------------------------------------------------------------


def test_candidates_below_threshold_exact_count() -> None:
    """Adequate sample (n=20) but peers below min_shared=3 -> candidates_below_threshold.

    3 peers each share exactly 2 commits with target (< min_shared=3 -> filtered).
    candidates_below_threshold must be exactly 3.
    co_changed_files must be empty (none cleared the threshold).
    """
    # 20 total commits: target in all 20
    # peer_a, peer_b, peer_c each share exactly 2 commits with target
    commits: list[tuple[str, list[str]]] = []
    # Commits 0-1: target + peer_a
    commits.append((_sha(0), ["src/target.py", "src/peer_a.py"]))
    commits.append((_sha(1), ["src/target.py", "src/peer_a.py"]))
    # Commits 2-3: target + peer_b
    commits.append((_sha(2), ["src/target.py", "src/peer_b.py"]))
    commits.append((_sha(3), ["src/target.py", "src/peer_b.py"]))
    # Commits 4-5: target + peer_c
    commits.append((_sha(4), ["src/target.py", "src/peer_c.py"]))
    commits.append((_sha(5), ["src/target.py", "src/peer_c.py"]))
    # Commits 6-19: target solo
    for i in range(6, 20):
        commits.append((_sha(i), ["src/target.py"]))

    git_log_out = _make_git_log(commits)
    head_sha = "33" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change(
            "/fake/repo", "src/target.py", max_commits=500, min_shared=3
        )

    assert result["success"] is True
    assert result["co_changed_files"] == []
    assert result["candidates_below_threshold"] == 3


def test_candidates_below_threshold_zero_when_no_peers_at_all() -> None:
    """No peers at all -> candidates_below_threshold must be exactly 0."""
    # 15 commits, target always solo
    commits = [(_sha(i), ["src/target.py"]) for i in range(15)]
    git_log_out = _make_git_log(commits)
    head_sha = "34" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change(
            "/fake/repo", "src/target.py", max_commits=500, min_shared=3
        )

    assert result["success"] is True
    assert result["candidates_below_threshold"] == 0


def test_candidates_below_threshold_mixed_above_and_below() -> None:
    """peer_a cleared threshold (shared=5), peer_b filtered (shared=2).
    candidates_below_threshold == 1 (only peer_b); co_changed_files has peer_a.
    """
    # 20 commits total
    # peer_a: shared=5 with target -> above min_shared=3 -> in co_changed_files
    # peer_b: shared=2 with target -> below min_shared=3 -> counted in candidates_below_threshold
    commits: list[tuple[str, list[str]]] = []
    # Commits 0-4: target + peer_a (5 shared)
    for i in range(5):
        commits.append((_sha(i), ["src/target.py", "src/peer_a.py"]))
    # Commits 5-6: target + peer_b (2 shared)
    commits.append((_sha(5), ["src/target.py", "src/peer_b.py"]))
    commits.append((_sha(6), ["src/target.py", "src/peer_b.py"]))
    # Commits 7-19: target solo
    for i in range(7, 20):
        commits.append((_sha(i), ["src/target.py"]))

    git_log_out = _make_git_log(commits)
    head_sha = "35" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change(
            "/fake/repo", "src/target.py", max_commits=500, min_shared=3
        )

    assert result["success"] is True
    assert len(result["co_changed_files"]) == 1
    assert result["co_changed_files"][0]["file"] == "src/peer_a.py"
    assert result["candidates_below_threshold"] == 1


# ---------------------------------------------------------------------------
# 33. Filtered-evidence next_step: adequate sample with filtered candidates
#     must say "filtered" / acknowledge sub-threshold signals exist.
# ---------------------------------------------------------------------------


def test_adequate_sample_filtered_candidates_next_step_says_filtered() -> None:
    """Adequate n=20, co_changed_files=[], candidates_below_threshold=3 ->
    next_step must NOT say 'Safe to edit in isolation'.
    It must acknowledge the filtered evidence.
    """
    # Same setup as test_candidates_below_threshold_exact_count
    commits: list[tuple[str, list[str]]] = []
    commits.append((_sha(0), ["src/target.py", "src/peer_a.py"]))
    commits.append((_sha(1), ["src/target.py", "src/peer_a.py"]))
    commits.append((_sha(2), ["src/target.py", "src/peer_b.py"]))
    commits.append((_sha(3), ["src/target.py", "src/peer_b.py"]))
    commits.append((_sha(4), ["src/target.py", "src/peer_c.py"]))
    commits.append((_sha(5), ["src/target.py", "src/peer_c.py"]))
    for i in range(6, 20):
        commits.append((_sha(i), ["src/target.py"]))

    git_log_out = _make_git_log(commits)
    head_sha = "36" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change(
            "/fake/repo", "src/target.py", max_commits=500, min_shared=3
        )

    next_step: str = result["agent_summary"]["next_step"]
    assert "Safe to edit in isolation" not in next_step
    # Exact pin (Codex P2): the filtered-candidate COUNT must be surfaced —
    # the deterministic fixture filters exactly 3 candidates.
    assert result["candidates_below_threshold"] == 3
    assert "3 candidate(s) were filtered" in next_step


# ---------------------------------------------------------------------------
# 34. CLI parity: result carries candidates_below_threshold when dispatched
#     through nav facade (not just _compute_co_change directly).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nav_facade_co_change_carries_candidates_below_threshold() -> None:
    """nav facade co_change result must include candidates_below_threshold field."""
    # 20 commits, 2 sub-threshold peers
    commits: list[tuple[str, list[str]]] = []
    for i in range(2):
        commits.append((_sha(i), ["src/target.py", "src/peer_a.py"]))
    for i in range(2, 4):
        commits.append((_sha(i), ["src/target.py", "src/peer_b.py"]))
    for i in range(4, 20):
        commits.append((_sha(i), ["src/target.py"]))

    git_log_out = _make_git_log(commits)
    head_sha = "37" * 20

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        facade = build_nav_facade(project_root=None)
        result = await facade.execute(
            {
                "action": "co_change",
                "file_path": "src/target.py",
                "output_format": "json",
            }
        )

    assert result["success"] is True
    assert "candidates_below_threshold" in result


# ---------------------------------------------------------------------------
# 36. Codex P2 (#495): coupled peers from a too-small sample carry the
#     small-sample caveat instead of bypassing the guard.
# ---------------------------------------------------------------------------


def test_coupled_peers_small_sample_carries_caveat():
    """n=3 with a peer meeting min_shared=3 must lead with the caution."""
    commits = [(_sha(i), ["a.py", "b.py"]) for i in range(3)]
    git_log_out = _make_git_log(commits)
    head_sha = "b" * 40

    with patch(
        "tree_sitter_analyzer.mcp.tools.utils.co_change._run_git"
    ) as mock_run_git:
        mock_run_git.side_effect = [
            (0, head_sha),
            (0, git_log_out),
        ]
        _CO_CHANGE_CACHE.clear()
        result = _compute_co_change("/fake/repo", "a.py")

    assert result["commits_analyzed"] == 3
    files = [c["file"] for c in result["co_changed_files"]]
    assert files == ["b.py"]
    next_step = result["agent_summary"]["next_step"]
    assert next_step.startswith("Caution: small sample (n=3 commits")
    assert "statistically unreliable" in next_step
