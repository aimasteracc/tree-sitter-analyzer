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

from unittest.mock import patch

import pytest

from tree_sitter_analyzer.mcp.tools.nav_facade import build_nav_facade
from tree_sitter_analyzer.mcp.tools.utils.co_change import (
    _CO_CHANGE_CACHE,
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


def test_single_subprocess_latency_invariant() -> None:
    """RFC Rule-11 latency invariant: max_commits=50 completes in < 1 s.

    The implementation issues exactly 2 _run_git calls (rev-parse + single log),
    never a per-commit loop.  We verify this with call_count == 2.
    """
    import time

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
        start = time.monotonic()
        result = _compute_co_change("/real/repo", "src/target.py", max_commits=50)
        elapsed = time.monotonic() - start

    assert elapsed < 1.0
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
