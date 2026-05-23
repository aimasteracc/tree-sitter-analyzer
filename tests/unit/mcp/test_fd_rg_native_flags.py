"""Regression tests for rg/fd native capability coverage.

Background: when fd/rg were first wrapped, we exposed a subset of the
flags that left several agent use cases unreachable. The 2026-05-23
audit (`docs/internal/RG_FD_GAP_AUDIT.md`) added:

- Bug fix: ``hidden=True`` for rg used to set ``-H`` (which is
  ``--with-filename`` and already on for multi-file output). The flag
  to actually descend into hidden directories is the long form
  ``--hidden``.
- New rg flags: ``file_types``, ``exclude_types``, ``files_with_matches``,
  ``only_matching``, ``context``, ``pcre2``, ``max_depth``, ``sort``,
  ``invert_match``, ``include_stats``.
- New fd flags: ``min_depth``, ``prune``, ``threads``,
  ``strip_cwd_prefix``, ``one_file_system``, ``show_errors``.

These tests pin every new flag at the command-builder level so silent
revert (e.g. the linter stripping kwargs as "unused") fails the suite.
"""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.mcp.tools import fd_rg_utils


_BASE_RG_KW: dict = dict(
    query="x",
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
    roots=None,
    files_from=None,
)

_BASE_FD_KW: dict = dict(
    pattern=None,
    glob=False,
    types=None,
    extensions=None,
    exclude=None,
    depth=None,
    follow_symlinks=False,
    hidden=False,
    no_ignore=False,
    size=None,
    changed_within=None,
    changed_before=None,
    full_path_match=False,
    absolute=False,
    limit=None,
    roots=["."],
)


class TestRgHiddenBug:
    """Pain #27: hidden=True must emit --hidden, NOT -H."""

    def test_hidden_true_uses_long_form(self):
        cmd = fd_rg_utils.build_rg_command(**{**_BASE_RG_KW, "hidden": True})
        assert "--hidden" in cmd
        assert "-H" not in cmd, (
            "rg's -H means --with-filename (default on for multi-file). "
            "To search hidden files we need --hidden."
        )

    def test_hidden_false_emits_neither(self):
        cmd = fd_rg_utils.build_rg_command(**{**_BASE_RG_KW, "hidden": False})
        assert "--hidden" not in cmd
        assert "-H" not in cmd


class TestRgNewFlags:
    """Each new keyword propagates to the right ripgrep CLI token."""

    def test_file_types(self):
        cmd = fd_rg_utils.build_rg_command(
            **_BASE_RG_KW, file_types=["py", "rs"]
        )
        # Two distinct -t pairs.
        assert cmd.count("-t") == 2
        py_idx = cmd.index("-t")
        assert cmd[py_idx + 1] == "py"

    def test_exclude_types(self):
        cmd = fd_rg_utils.build_rg_command(
            **_BASE_RG_KW, exclude_types=["test"]
        )
        idx = cmd.index("-T")
        assert cmd[idx + 1] == "test"

    def test_files_with_matches_drops_json(self):
        # rg refuses --json with -l; we must drop the JSON flag.
        cmd = fd_rg_utils.build_rg_command(
            **_BASE_RG_KW, files_with_matches=True
        )
        assert "--files-with-matches" in cmd
        assert "--json" not in cmd

    def test_only_matching(self):
        cmd = fd_rg_utils.build_rg_command(**_BASE_RG_KW, only_matching=True)
        assert "-o" in cmd

    def test_context_combined(self):
        cmd = fd_rg_utils.build_rg_command(**_BASE_RG_KW, context=3)
        idx = cmd.index("-C")
        assert cmd[idx + 1] == "3"
        # Combined -C should not also emit -B / -A.
        assert "-B" not in cmd
        assert "-A" not in cmd

    def test_context_combined_yields_to_explicit_before_after(self):
        # If the caller passed explicit before/after, those win.
        cmd = fd_rg_utils.build_rg_command(
            **{**_BASE_RG_KW, "context_before": 2, "context_after": 4},
            context=99,  # ignored
        )
        assert "-C" not in cmd
        assert "-B" in cmd and cmd[cmd.index("-B") + 1] == "2"
        assert "-A" in cmd and cmd[cmd.index("-A") + 1] == "4"

    def test_pcre2(self):
        cmd = fd_rg_utils.build_rg_command(**_BASE_RG_KW, pcre2=True)
        assert "-P" in cmd

    def test_max_depth(self):
        cmd = fd_rg_utils.build_rg_command(**_BASE_RG_KW, max_depth=5)
        idx = cmd.index("--max-depth")
        assert cmd[idx + 1] == "5"

    @pytest.mark.parametrize("sort_val", ["path", "modified", "accessed", "created", "none"])
    def test_sort(self, sort_val):
        cmd = fd_rg_utils.build_rg_command(**_BASE_RG_KW, sort=sort_val)
        idx = cmd.index("--sort")
        assert cmd[idx + 1] == sort_val

    def test_invert_match(self):
        cmd = fd_rg_utils.build_rg_command(**_BASE_RG_KW, invert_match=True)
        assert "-v" in cmd

    def test_include_stats(self):
        cmd = fd_rg_utils.build_rg_command(**_BASE_RG_KW, include_stats=True)
        assert "--stats" in cmd

    def test_no_config_always_on(self):
        # User's ~/.ripgreprc must NEVER influence agent results.
        cmd = fd_rg_utils.build_rg_command(**_BASE_RG_KW)
        assert "--no-config" in cmd


class TestFdNewFlags:
    """Each new fd keyword propagates to the right fd CLI token."""

    def test_min_depth(self):
        cmd = fd_rg_utils.build_fd_command(**_BASE_FD_KW, min_depth=2)
        idx = cmd.index("--min-depth")
        assert cmd[idx + 1] == "2"

    def test_prune(self):
        cmd = fd_rg_utils.build_fd_command(**_BASE_FD_KW, prune=True)
        assert "--prune" in cmd

    def test_threads(self):
        cmd = fd_rg_utils.build_fd_command(**_BASE_FD_KW, threads=4)
        idx = cmd.index("-j")
        assert cmd[idx + 1] == "4"

    def test_threads_zero_omitted(self):
        cmd = fd_rg_utils.build_fd_command(**_BASE_FD_KW, threads=0)
        assert "-j" not in cmd  # zero / negative should not be emitted

    def test_strip_cwd_prefix(self):
        cmd = fd_rg_utils.build_fd_command(**_BASE_FD_KW, strip_cwd_prefix=True)
        assert "--strip-cwd-prefix" in cmd

    def test_one_file_system(self):
        cmd = fd_rg_utils.build_fd_command(**_BASE_FD_KW, one_file_system=True)
        assert "--one-file-system" in cmd

    def test_show_errors(self):
        cmd = fd_rg_utils.build_fd_command(**_BASE_FD_KW, show_errors=True)
        assert "--show-errors" in cmd


class TestBackwardCompat:
    """The new kwargs must default to off — existing call sites unaffected."""

    def test_rg_minimal_call_unchanged(self):
        # Pre-audit invocation must still produce a valid plain rg command.
        cmd = fd_rg_utils.build_rg_command(**_BASE_RG_KW)
        assert cmd[0] == "rg"
        assert "--json" in cmd  # still default
        # None of the new flags should leak into the output.
        for new in [
            "-t", "-T", "--files-with-matches", "-o", "-C",
            "-P", "--max-depth", "--sort", "-v", "--stats",
        ]:
            assert new not in cmd, f"unexpected {new} when not requested"

    def test_fd_minimal_call_unchanged(self):
        cmd = fd_rg_utils.build_fd_command(**_BASE_FD_KW)
        assert cmd[0] == "fd"
        for new in [
            "--min-depth", "--prune", "-j", "--strip-cwd-prefix",
            "--one-file-system", "--show-errors",
        ]:
            assert new not in cmd, f"unexpected {new} when not requested"
