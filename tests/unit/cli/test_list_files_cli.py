"""H1 regression tests: list_files CLI exit code contract.

The standalone ``list-files`` wrapper previously had a typo —
``return 0 if ... else 0`` — which made ``set -e`` pipelines blind to
``{"success": false, "error": "..."}`` responses. The fix returns
``rc=1`` whenever the response envelope has ``success: false`` while
keeping ``rc=0`` for genuine successes (including int-valued count-only
returns).

Reproduce (pre-fix):
    uv run list-files tree_sitter_analyzer \
        --pattern "[" --output-format json
    # stdout: {"success": false, "error": "..."}
    # rc=0  (BUG)
"""

from __future__ import annotations

import argparse
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tree_sitter_analyzer.cli.commands.list_files_cli import _run


def _base_args() -> argparse.Namespace:
    """Build a minimal but complete Namespace for ``_run``."""
    return argparse.Namespace(
        roots=["root1"],
        output_format="json",
        quiet=False,
        project_root=None,
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
        limit=None,
        count_only=False,
    )


async def _run_with_mock_result(result: Any) -> int:
    """Run the CLI with a mocked tool result, return exit code."""
    args = _base_args()
    with (
        patch(
            "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root",
            return_value="/project/root",
        ),
        patch(
            "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
        ) as mock_tool_class,
        patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
        patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_data"),
    ):
        mock_tool = AsyncMock()
        mock_tool.execute = AsyncMock(return_value=result)
        mock_tool_class.return_value = mock_tool
        return await _run(args)


class TestH1ListFilesExitCode:
    """H1: standalone ``list-files`` exit code must reflect ``success``."""

    @pytest.mark.asyncio
    async def test_success_payload_returns_zero(self) -> None:
        """A normal successful listing → rc=0."""
        rc = await _run_with_mock_result(
            {"success": True, "files": ["a.py", "b.py"], "total_count": 2}
        )
        assert rc == 0, f"success payload must return rc=0, got {rc}"

    @pytest.mark.asyncio
    async def test_success_without_explicit_flag_returns_zero(self) -> None:
        """A dict with no ``success`` key (legacy shape) is treated as success."""
        rc = await _run_with_mock_result({"files": [], "total_count": 0})
        assert rc == 0, f"dict without success key must default to rc=0, got {rc}"

    @pytest.mark.asyncio
    async def test_failure_payload_returns_one(self) -> None:
        """H1 regression: ``success: false`` payload → rc=1, not rc=0.

        Pre-fix: ``return 0 if ... else 0`` made this an always-zero return,
        masking real failures from ``set -e``.
        """
        rc = await _run_with_mock_result(
            {"success": False, "error": "fd regex parse error"}
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
                "tree_sitter_analyzer.cli.commands.list_files_cli.detect_project_root",
                return_value="/project/root",
            ),
            patch(
                "tree_sitter_analyzer.cli.commands.list_files_cli.ListFilesTool"
            ) as mock_tool_class,
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.set_output_mode"),
            patch("tree_sitter_analyzer.cli.commands.list_files_cli.output_error"),
        ):
            mock_tool = AsyncMock()
            mock_tool.execute = AsyncMock(side_effect=RuntimeError("boom"))
            mock_tool_class.return_value = mock_tool
            rc = await _run(args)
        assert rc == 1, f"exception must produce rc=1, got {rc}"
