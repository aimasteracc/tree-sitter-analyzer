#!/usr/bin/env python3
"""Tests for the ``--check-scale FILE`` CLI flag (Issue #513 leg 1).

RED-first: these tests are written BEFORE the implementation.
They verify:
  1. Parser accepts ``--check-scale FILE`` and stores the file path.
  2. ``handle_special_commands`` dispatches to ``_handle_check_scale``
     and returns the exit code from ``_run_mcp_tool_sync``.
  3. Missing/non-existent file yields exit code 1 with a JSON error envelope.
  4. Parity: MCP ``AnalyzeScaleTool.execute`` and the CLI path produce the
     same core metric keys on the same file.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from tree_sitter_analyzer.cli_main import (
    create_argument_parser,
)

# ── helpers ────────────────────────────────────────────────────────────────


def _make_context(**overrides) -> object:
    """Return a minimal SpecialCommandContext-like namespace."""
    from tree_sitter_analyzer.cli.special_commands import SpecialCommandContext

    defaults = {
        "asyncio_run": asyncio.run,
        "output_json": MagicMock(),
        "output_error": MagicMock(),
        "output_info": MagicMock(),
        "output_list": MagicMock(),
        "query_loader": MagicMock(),
    }
    defaults.update(overrides)
    return SpecialCommandContext(**defaults)


# ── parser tests ────────────────────────────────────────────────────────────


class TestCheckScaleParser:
    """Parser wiring: ``--check-scale FILE`` must parse cleanly."""

    def test_parser_accepts_check_scale(self, tmp_path: Path) -> None:
        """``--check-scale FILE`` sets ``args.check_scale`` to the file path."""
        target = tmp_path / "sample.py"
        target.write_text("x = 1\n")
        parser = create_argument_parser()
        args = parser.parse_args(["--check-scale", str(target)])
        assert args.check_scale == str(target)

    def test_check_scale_in_help(self) -> None:
        """``--check-scale`` must appear in ``--help`` output."""
        import io

        parser = create_argument_parser()
        buf = io.StringIO()
        try:
            parser.print_help(buf)
        except SystemExit:
            pass
        assert "--check-scale" in buf.getvalue()

    def test_check_scale_absent_by_default(self) -> None:
        """Without the flag, ``args.check_scale`` is ``None``."""
        parser = create_argument_parser()
        args = parser.parse_args(["somefile.py"])
        assert args.check_scale is None


# ── dispatch tests ──────────────────────────────────────────────────────────


class TestCheckScaleDispatch:
    """handle_special_commands dispatches ``--check-scale`` correctly."""

    def _base_args(self, check_scale=None, project_root=None, **kwargs):
        return SimpleNamespace(
            check_scale=check_scale,
            metrics_only=False,
            project_root=project_root,
            format="json",
            output_format="json",
            quiet=False,
            health_check=False,
            agent_skills=False,
            agent_workflow=False,
            install_skills=None,
            install_skills_global=False,
            partial_read=False,
            partial_read_requests_json=None,
            partial_read_requests_file=None,
            check_constraints=False,
            clean_state=False,
            clean_state_dry_run=False,
            autoindex=False,
            full_index=False,
            codegraph_metrics=False,
            incremental_sync=False,
            watch=False,
            watch_health=False,
            affected=None,
            show_query_languages=False,
            show_common_queries=False,
            sql_platform_info=False,
            record_sql_profile=False,
            compare_sql_profiles=None,
            **kwargs,
        )

    def test_returns_none_when_check_scale_absent(self) -> None:
        """When ``check_scale`` is ``None``, handler returns ``None``."""
        from tree_sitter_analyzer.cli.special_commands import _handle_check_scale

        args = self._base_args()
        ctx = _make_context()
        result = _handle_check_scale(args, ctx)
        assert result is None

    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        """Handler returns ``0`` when AnalyzeScaleTool returns success."""
        from tree_sitter_analyzer.cli.special_commands import _handle_check_scale

        target = tmp_path / "sample.py"
        target.write_text("def foo(): pass\n")

        success_result = {
            "success": True,
            "file_path": str(target),
            "language": "python",
            "file_metrics": {"total_lines": 1, "estimated_tokens": 5},
            "summary": {"classes": 0, "methods": 1, "fields": 0, "imports": 0},
            "mode": "single",
            "output_format": "json",
        }

        output_json_calls: list = []
        ctx = _make_context(
            asyncio_run=MagicMock(return_value=success_result),
            output_json=lambda d: output_json_calls.append(d),
        )
        args = self._base_args(check_scale=str(target))
        rc = _handle_check_scale(args, ctx)
        assert rc == 0
        assert len(output_json_calls) == 1
        assert output_json_calls[0]["success"] is True

    def test_returns_1_on_tool_failure(self, tmp_path: Path) -> None:
        """Handler returns ``1`` when AnalyzeScaleTool returns success=False."""
        from tree_sitter_analyzer.cli.special_commands import _handle_check_scale

        target = tmp_path / "broken.py"
        target.write_text("")

        fail_result = {"success": False, "error": "parse error"}
        ctx = _make_context(asyncio_run=MagicMock(return_value=fail_result))
        args = self._base_args(check_scale=str(target))
        rc = _handle_check_scale(args, ctx)
        assert rc == 1

    def test_missing_file_returns_1_with_json_error(self, tmp_path: Path) -> None:
        """Nonexistent file → exit 1 with a JSON error envelope."""
        from tree_sitter_analyzer.cli.special_commands import _handle_check_scale

        # Existence validation is delegated to AnalyzeScaleTool (so that
        # --project-root resolution applies); the tool reports the miss.
        output_json_calls: list = []
        output_error_calls: list = []
        ctx = _make_context(
            output_json=lambda d: output_json_calls.append(d),
            output_error=lambda m: output_error_calls.append(m),
        )
        args = self._base_args(check_scale="not_here.py", project_root=str(tmp_path))
        rc = _handle_check_scale(args, ctx)
        assert rc == 1
        # JSON format → error envelope on stdout
        assert len(output_json_calls) == 1
        env = output_json_calls[0]
        assert env["success"] is False
        assert env["verdict"] == "ERROR"
        assert "File not found: not_here.py" in env.get("error", "")

    def test_project_root_resolves_relative_path(self, tmp_path: Path) -> None:
        """--project-root /repo --check-scale rel/path.py works from any CWD
        (Codex P2 on #527: no CWD-relative preflight)."""
        from tree_sitter_analyzer.cli.special_commands import _handle_check_scale

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text("def foo(): pass\n")

        output_json_calls: list = []
        ctx = _make_context(output_json=lambda d: output_json_calls.append(d))
        args = self._base_args(check_scale="src/foo.py", project_root=str(tmp_path))
        rc = _handle_check_scale(args, ctx)
        assert rc == 0
        assert output_json_calls[0]["success"] is True
        assert output_json_calls[0]["summary"]["methods"] == 1

    def test_language_override_forwarded(self, tmp_path: Path) -> None:
        """--language reaches AnalyzeScaleTool (Codex P2 on #527)."""
        from tree_sitter_analyzer.cli.special_commands import _handle_check_scale

        target = tmp_path / "script.txt"
        target.write_text("def foo(): pass\n")

        output_json_calls: list = []
        ctx = _make_context(output_json=lambda d: output_json_calls.append(d))
        args = self._base_args(
            check_scale="script.txt",
            project_root=str(tmp_path),
            language="python",
        )
        rc = _handle_check_scale(args, ctx)
        assert rc == 0
        env = output_json_calls[0]
        assert env["success"] is True
        assert env["language"] == "python"
        assert env["summary"]["methods"] == 1


# ── parity test ─────────────────────────────────────────────────────────────


class TestCheckScaleMcpCliParity:
    """CLI path and MCP AnalyzeScaleTool.execute must agree on core metrics."""

    def test_core_metric_keys_match_mcp_output(self, tmp_path: Path) -> None:
        """CLI JSON output contains the same core keys as MCP execute response."""
        from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool

        target = tmp_path / "subject.py"
        target.write_text(
            "class Foo:\n"
            "    def bar(self):\n"
            "        return 42\n"
            "\n"
            "def baz():\n"
            "    pass\n",
        )

        # MCP path
        tool = AnalyzeScaleTool(project_root=str(tmp_path))
        mcp_result = asyncio.run(
            tool.execute({"file_path": str(target), "output_format": "json"})
        )
        assert mcp_result["success"] is True

        # CLI path via _handle_check_scale
        from tree_sitter_analyzer.cli.special_commands import _handle_check_scale

        cli_result_holder: list = []
        ctx = _make_context(
            asyncio_run=asyncio.run,
            output_json=lambda d: cli_result_holder.append(d),
        )
        args = SimpleNamespace(
            check_scale=str(target),
            project_root=str(tmp_path),
            format="json",
            output_format="json",
            quiet=False,
        )
        rc = _handle_check_scale(args, ctx)
        assert rc == 0
        assert len(cli_result_holder) == 1
        cli_result = cli_result_holder[0]

        # Core keys that both paths must share
        CORE_KEYS = {"success", "file_path", "language", "file_metrics", "summary"}
        mcp_keys = set(mcp_result.keys())
        cli_keys = set(cli_result.keys())
        missing_from_cli = CORE_KEYS - cli_keys
        assert missing_from_cli == set(), (
            f"CLI result missing core keys: {missing_from_cli}"
        )
        missing_from_mcp = CORE_KEYS - mcp_keys
        assert missing_from_mcp == set(), (
            f"MCP result missing core keys: {missing_from_mcp}"
        )

        # Core metric values must agree
        assert cli_result["file_path"] == mcp_result["file_path"]
        assert cli_result["language"] == mcp_result["language"]
        assert (
            cli_result["file_metrics"]["total_lines"]
            == mcp_result["file_metrics"]["total_lines"]
        )
        assert cli_result["summary"]["methods"] == mcp_result["summary"]["methods"]
