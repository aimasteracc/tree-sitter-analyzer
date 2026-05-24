"""Re-export aggregator for split test modules + H1 regression tests.

The H1 regression covers the exit-code contract: ``search-content`` must
return ``rc=1`` whenever the underlying tool response has
``success: false`` (was silently ``rc=0`` pre-fix, breaking ``set -e``
pipelines and CI gates).

Reproduce (pre-fix):
    uv run search-content --roots tree_sitter_analyzer \
        --query "[" --output-format json
    # stdout: {"success": false, "error": "..."}
    # rc=0  (BUG)
"""

from __future__ import annotations

import argparse
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# Keep the legacy aggregator re-exports working so other suites importing
# these names from ``test_search_content_cli`` keep finding them.
from test_search_content_cli_main import (  # noqa: F401
    TestEdgeCases,
    TestMainFunction,
)
from test_search_content_cli_parser import TestBuildParser  # noqa: F401
from test_search_content_cli_run import TestRunFunction  # noqa: F401

from tree_sitter_analyzer.cli.commands.search_content_cli import _run


def _base_args() -> argparse.Namespace:
    """Build a minimal but complete Namespace for ``_run``.

    Uses cwd as root for the same reason as test_find_and_grep_cli:
    keeps the test resilient against patch-leak from sibling tests
    on xdist workers — if SearchContentTool's patch ever doesn't
    apply, the real _validate_roots won't fail because cwd exists.
    """
    import os

    return argparse.Namespace(
        roots=[os.getcwd()],
        files=None,
        query="test",
        output_format="json",
        quiet=False,
        project_root=None,
        case="smart",
        fixed_strings=False,
        word=False,
        multiline=False,
        follow_symlinks=False,
        hidden=False,
        no_ignore=False,
        include_globs=None,
        exclude_globs=None,
        max_filesize=None,
        context_before=None,
        context_after=None,
        encoding=None,
        max_count=None,
        timeout_ms=None,
        count_only_matches=False,
        summary_only=False,
        optimize_paths=False,
        group_by_file=False,
        total_only=False,
    )


async def _run_with_mock_result(result: Any) -> int:
    """Run the CLI with a mocked tool result, return exit code."""
    args = _base_args()
    with (
        patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
            return_value="/project/root",
        ),
        patch(
            "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
        ) as mock_tool_class,
        patch("tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"),
        patch("tree_sitter_analyzer.cli.commands.search_content_cli.output_data"),
    ):
        mock_tool = AsyncMock()
        mock_tool.execute = AsyncMock(return_value=result)
        mock_tool_class.return_value = mock_tool
        return await _run(args)


class TestH1SearchContentExitCode:
    """H1: standalone ``search-content`` exit code must reflect ``success``."""

    @pytest.mark.asyncio
    async def test_success_payload_returns_zero(self) -> None:
        """A normal successful match → rc=0."""
        rc = await _run_with_mock_result(
            {"success": True, "matches": 5, "files": ["a.py"]}
        )
        assert rc == 0, f"success payload must return rc=0, got {rc}"

    @pytest.mark.asyncio
    async def test_success_without_explicit_flag_returns_zero(self) -> None:
        """A dict with no ``success`` key (legacy shape) is treated as success."""
        rc = await _run_with_mock_result({"matches": 0, "files": []})
        assert rc == 0, f"dict without success key must default to rc=0, got {rc}"

    @pytest.mark.asyncio
    async def test_failure_payload_returns_one(self) -> None:
        """H1 regression: ``success: false`` payload → rc=1, not rc=0."""
        rc = await _run_with_mock_result(
            {"success": False, "error": "ripgrep regex parse error"}
        )
        assert rc == 1, (
            f"H1 regression: success:false payload must return rc=1, got {rc}"
        )

    @pytest.mark.asyncio
    async def test_int_count_only_returns_zero(self) -> None:
        """Count-only mode legacy shape returns int — that's success, rc=0."""
        rc = await _run_with_mock_result(42)
        assert rc == 0, f"int count-only return must yield rc=0, got {rc}"

    @pytest.mark.asyncio
    async def test_exception_returns_one(self) -> None:
        """An exception during execute → rc=1 via the except branch."""
        args = _base_args()
        with (
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.detect_project_root",
                return_value="/project/root",
            ),
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.SearchContentTool"
            ) as mock_tool_class,
            patch(
                "tree_sitter_analyzer.cli.commands.search_content_cli.set_output_mode"
            ),
            patch("tree_sitter_analyzer.cli.commands.search_content_cli.output_error"),
        ):
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(side_effect=RuntimeError("boom"))
            mock_tool_class.return_value = mock_tool
            rc = await _run(args)
        assert rc == 1, f"exception must produce rc=1, got {rc}"
