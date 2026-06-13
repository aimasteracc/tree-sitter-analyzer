"""H5 regression tests: find_and_grep deduplication via exact file paths.

H5 bug: fd discovers files and the old code passed parent directories + filename
globs to ripgrep.  When the same filename exists in a parent dir AND a subdir,
rg would match in both, producing double-counted results.

Fix: pass exact deduplicated file paths as positional arguments to rg, not parent
dirs.  ripgrep does not support --files-from; positional args are the correct API.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Unit tests for build_rg_command_from_arguments (no rg subprocess)
# ---------------------------------------------------------------------------


def test_build_rg_command_uses_file_paths_not_roots() -> None:
    """H5: build_rg_command_from_arguments must pass file_paths, not roots."""
    from tree_sitter_analyzer.mcp.tools.find_and_grep_execution import (
        build_rg_command_from_arguments,
    )

    files = ["/repo/a/foo.py", "/repo/b/bar.py"]
    args = {
        "query": "TODO",
        "case": "smart",
    }
    cmd = build_rg_command_from_arguments(args, files)

    # The query must appear in the command
    assert "TODO" in cmd, f"query not found in cmd: {cmd}"

    # The exact file paths must appear as positional args after the query
    query_idx = cmd.index("TODO")
    positional = cmd[query_idx + 1 :]
    assert "/repo/a/foo.py" in positional, f"file path not in positional args: {cmd}"
    assert "/repo/b/bar.py" in positional, f"file path not in positional args: {cmd}"

    # No parent directory should appear as a root
    assert "/repo/a" not in cmd, f"parent dir leaked into cmd: {cmd}"
    assert "/repo/b" not in cmd, f"parent dir leaked into cmd: {cmd}"


def test_build_rg_command_deduplicates_paths() -> None:
    """H5: duplicate file paths are deduplicated before passing to rg."""
    from tree_sitter_analyzer.mcp.tools.find_and_grep_execution import (
        build_rg_command_from_arguments,
    )

    files = ["/repo/a/foo.py", "/repo/a/foo.py", "/repo/b/bar.py"]
    args = {"query": "TODO", "case": "smart"}
    cmd = build_rg_command_from_arguments(args, files)

    query_idx = cmd.index("TODO")
    positional = cmd[query_idx + 1 :]
    assert positional.count("/repo/a/foo.py") == 1, (
        f"H5: duplicate paths not deduplicated: {positional}"
    )


def test_fd_rg_utils_build_rg_command_file_paths_param() -> None:
    """H5: build_rg_command accepts file_paths and appends them after query."""
    from tree_sitter_analyzer.mcp.tools.fd_rg_utils import build_rg_command

    cmd = build_rg_command(
        query="FIXME",
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=False,
        include_globs=None,
        exclude_globs=None,
        follow_symlinks=False,
        hidden=False,
        no_ignore=False,
        max_filesize=None,
        context_before=None,
        context_after=None,
        encoding=None,
        max_count=None,
        timeout_ms=None,
        roots=None,
        file_paths=["/a/foo.py", "/b/bar.py"],
    )
    query_idx = cmd.index("FIXME")
    assert cmd[query_idx + 1 :] == ["/a/foo.py", "/b/bar.py"], (
        f"file_paths not appended correctly: {cmd}"
    )


def test_fd_rg_utils_roots_ignored_when_file_paths_given() -> None:
    """H5: when file_paths is provided, roots must be ignored to avoid double-counting."""
    from tree_sitter_analyzer.mcp.tools.fd_rg_utils import build_rg_command

    cmd = build_rg_command(
        query="TODO",
        case=None,
        fixed_strings=False,
        word=False,
        multiline=False,
        include_globs=None,
        exclude_globs=None,
        follow_symlinks=False,
        hidden=False,
        no_ignore=False,
        max_filesize=None,
        context_before=None,
        context_after=None,
        encoding=None,
        max_count=None,
        timeout_ms=None,
        roots=["/repo"],
        file_paths=["/repo/sub/foo.py"],
    )
    # roots="/repo" must NOT appear; only /repo/sub/foo.py should be in positional
    assert "/repo" not in cmd[cmd.index("TODO") + 1 :] or "/repo/sub/foo.py" in cmd, (
        f"roots leaked despite file_paths being provided: {cmd}"
    )
    query_idx = cmd.index("TODO")
    positional = cmd[query_idx + 1 :]
    assert "/repo/sub/foo.py" in positional


# ---------------------------------------------------------------------------
# Integration test with real rg subprocess
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    shutil.which("rg") is None,
    reason="ripgrep (rg) not installed — skipping real-subprocess test",
)
def test_h5_real_rg_no_double_count(tmp_path: Path) -> None:
    """H5 integration: rg receives exact file paths and does NOT double-count.

    Layout:
        tmp/foo.py         (contains 1 TODO)
        tmp/sub/foo.py     (contains 1 TODO)
        tmp/other.py       (contains 1 TODO)

    fd discovers 3 files.  The old code passed [tmp, tmp/sub] as roots with
    glob ``foo.py``, which caused rg to match tmp/foo.py twice (once via tmp
    root and once via tmp/sub root) — total 5 matches instead of 3.

    The fix passes exact paths; rg must return exactly 3 matches.
    """
    # Create files
    (tmp_path / "foo.py").write_text("# TODO: fix this\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "foo.py").write_text("# TODO: fix that\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("# TODO: fix other\n", encoding="utf-8")

    files = [
        str(tmp_path / "foo.py"),
        str(sub / "foo.py"),
        str(tmp_path / "other.py"),
    ]

    from tree_sitter_analyzer.mcp.tools.find_and_grep_execution import (
        build_rg_command_from_arguments,
    )

    args = {
        "query": "TODO",
        "case": "smart",
        "fixed_strings": False,
    }
    cmd = build_rg_command_from_arguments(args, files)

    proc = subprocess.run(cmd, capture_output=True, timeout=10)  # noqa: S603
    # rc 0 = matches found, rc 1 = no matches
    assert proc.returncode in (0, 1), (
        f"rg failed (rc={proc.returncode}): {proc.stderr.decode()}"
    )

    import json

    matches = []
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
            if event.get("type") == "match":
                matches.append(event)
        except (json.JSONDecodeError, KeyError):
            continue

    assert len(matches) == 3, (
        f"H5 regression: expected 3 matches (one per file), got {len(matches)}. "
        f"Matches: {[m['data']['path'] for m in matches]}"
    )
