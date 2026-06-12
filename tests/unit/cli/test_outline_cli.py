#!/usr/bin/env python3
"""Tests for the ``--outline FILE`` CLI flag (Issue #539).

RED-first: these tests are written BEFORE the implementation.
They verify:
  1. Parser accepts ``--outline FILE`` and stores the file path.
  2. ``handle_special_commands`` dispatches to ``_handle_outline``
     and returns the exit code from ``_run_mcp_tool_sync``.
  3. Missing/non-existent file yields exit code 1 with a JSON error envelope.
  4. Parity: MCP ``GetCodeOutlineTool.execute`` and the CLI path produce the
     same core schema keys on the same file.
  5. ``--outline-listed-cap`` is forwarded to the tool.
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


class TestOutlineParser:
    """Parser wiring: ``--outline FILE`` must parse cleanly."""

    def test_parser_accepts_outline_file(self, tmp_path: Path) -> None:
        """``--outline FILE`` sets ``args.outline`` to the file path."""
        target = tmp_path / "sample.py"
        target.write_text("x = 1\n", newline="\n")
        parser = create_argument_parser()
        args = parser.parse_args(["--outline", str(target)])
        assert args.outline == str(target)

    def test_outline_in_help(self) -> None:
        """``--outline`` must appear in ``--help`` output."""
        import io

        parser = create_argument_parser()
        buf = io.StringIO()
        try:
            parser.print_help(buf)
        except SystemExit:
            pass
        assert "--outline" in buf.getvalue()

    def test_outline_absent_by_default(self) -> None:
        """Without the flag, ``args.outline`` is ``None``."""
        parser = create_argument_parser()
        args = parser.parse_args(["somefile.py"])
        assert args.outline is None

    def test_outline_listed_cap_default(self) -> None:
        """``--outline-listed-cap`` defaults to 50."""
        parser = create_argument_parser()
        args = parser.parse_args([])
        assert args.outline_listed_cap == 50

    def test_outline_listed_cap_override(self, tmp_path: Path) -> None:
        """``--outline-listed-cap N`` sets the cap."""
        target = tmp_path / "big.py"
        target.write_text("", newline="\n")
        parser = create_argument_parser()
        args = parser.parse_args(
            ["--outline", str(target), "--outline-listed-cap", "100"]
        )
        assert args.outline_listed_cap == 100


# ── dispatch tests ──────────────────────────────────────────────────────────


class TestOutlineDispatch:
    """handle_special_commands dispatches ``--outline`` correctly."""

    def _base_args(self, outline=None, project_root=None, **kwargs):
        return SimpleNamespace(
            outline=outline,
            outline_listed_cap=50,
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
            check_scale=None,
            **kwargs,
        )

    def test_returns_none_when_outline_absent(self) -> None:
        """When ``outline`` is ``None``, handler returns ``None``."""
        from tree_sitter_analyzer.cli.special_commands import _handle_outline

        args = self._base_args()
        ctx = _make_context()
        result = _handle_outline(args, ctx)
        assert result is None

    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        """Handler returns ``0`` when GetCodeOutlineTool returns success."""
        from tree_sitter_analyzer.cli.special_commands import _handle_outline

        target = tmp_path / "sample.py"
        target.write_text("def foo(): pass\n", newline="\n")

        success_result = {
            "success": True,
            "file_path": str(target),
            "language": "python",
            "classes": [],
            "top_level_functions": [{"name": "foo", "line_start": 1, "line_end": 1}],
            "statistics": {"class_count": 0, "method_count": 1},
            "output_format": "json",
        }

        output_json_calls: list = []
        ctx = _make_context(
            asyncio_run=MagicMock(return_value=success_result),
            output_json=lambda d: output_json_calls.append(d),
        )
        args = self._base_args(outline=str(target))
        rc = _handle_outline(args, ctx)
        assert rc == 0
        assert len(output_json_calls) == 1
        assert output_json_calls[0]["success"] is True

    def test_returns_1_on_tool_failure(self, tmp_path: Path) -> None:
        """Handler returns ``1`` when GetCodeOutlineTool returns success=False."""
        from tree_sitter_analyzer.cli.special_commands import _handle_outline

        target = tmp_path / "broken.py"
        target.write_text("", newline="\n")

        fail_result = {"success": False, "error": "parse error"}
        ctx = _make_context(asyncio_run=MagicMock(return_value=fail_result))
        args = self._base_args(outline=str(target))
        rc = _handle_outline(args, ctx)
        assert rc == 1

    def test_missing_file_returns_1_with_json_error(self, tmp_path: Path) -> None:
        """Nonexistent file → exit 1 with a JSON error envelope."""
        from tree_sitter_analyzer.cli.special_commands import _handle_outline

        output_json_calls: list = []
        output_error_calls: list = []
        ctx = _make_context(
            output_json=lambda d: output_json_calls.append(d),
            output_error=lambda m: output_error_calls.append(m),
        )
        args = self._base_args(outline="not_here.py", project_root=str(tmp_path))
        rc = _handle_outline(args, ctx)
        assert rc == 1
        # JSON format → error envelope on stdout
        assert len(output_json_calls) == 1
        env = output_json_calls[0]
        assert env["success"] is False
        assert env["verdict"] == "ERROR"
        assert "not_here.py" in env.get("error", "")

    def test_project_root_resolves_relative_path(self, tmp_path: Path) -> None:
        """--project-root /repo --outline rel/path.py works from any CWD."""
        from tree_sitter_analyzer.cli.special_commands import _handle_outline

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text(
            "class Foo:\n    def bar(self): pass\n", newline="\n"
        )

        output_json_calls: list = []
        ctx = _make_context(output_json=lambda d: output_json_calls.append(d))
        args = self._base_args(outline="src/foo.py", project_root=str(tmp_path))
        rc = _handle_outline(args, ctx)
        assert rc == 0
        env = output_json_calls[0]
        assert env["success"] is True
        assert env["class_count"] == 1

    def test_language_override_forwarded(self, tmp_path: Path) -> None:
        """--language reaches GetCodeOutlineTool."""
        from tree_sitter_analyzer.cli.special_commands import _handle_outline

        target = tmp_path / "script.txt"
        target.write_text("def foo(): pass\n", newline="\n")

        output_json_calls: list = []
        ctx = _make_context(output_json=lambda d: output_json_calls.append(d))
        args = self._base_args(
            outline="script.txt",
            project_root=str(tmp_path),
            language="python",
        )
        rc = _handle_outline(args, ctx)
        assert rc == 0
        env = output_json_calls[0]
        assert env["success"] is True
        assert env["language"] == "python"

    def test_listed_cap_forwarded(self, tmp_path: Path) -> None:
        """--outline-listed-cap is forwarded to GetCodeOutlineTool."""
        from tree_sitter_analyzer.cli.special_commands import _handle_outline

        target = tmp_path / "sample.py"
        target.write_text("def foo(): pass\n", newline="\n")

        captured_calls = []

        def fake_asyncio_run(coro):
            # Capture the tool's execute arguments via a thin wrapper
            import asyncio as _asyncio

            result = _asyncio.run(coro)
            captured_calls.append(result)
            return result

        output_json_calls: list = []
        ctx = _make_context(
            asyncio_run=fake_asyncio_run,
            output_json=lambda d: output_json_calls.append(d),
        )
        args = SimpleNamespace(
            outline=str(target),
            outline_listed_cap=10,
            project_root=str(tmp_path),
            format="json",
            output_format="json",
            quiet=False,
        )
        rc = _handle_outline(args, ctx)
        assert rc == 0
        env = output_json_calls[0]
        # The tool should have honoured listed_cap=10
        assert env.get("listed_cap") == 10


# ── parity test ─────────────────────────────────────────────────────────────


class TestOutlineMcpCliParity:
    """CLI path and MCP GetCodeOutlineTool.execute must agree on core schema keys."""

    def test_core_schema_keys_match_mcp_output(self, tmp_path: Path) -> None:
        """CLI JSON output contains the same core keys as MCP execute response."""
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            GetCodeOutlineTool,
        )

        target = tmp_path / "subject.py"
        target.write_text(
            "class Foo:\n"
            "    def bar(self):\n"
            "        return 42\n"
            "\n"
            "def baz():\n"
            "    pass\n",
            newline="\n",
        )

        # MCP path
        tool = GetCodeOutlineTool(project_root=str(tmp_path))
        mcp_result = asyncio.run(
            tool.execute({"file_path": str(target), "output_format": "json"})
        )
        assert mcp_result["success"] is True

        # CLI path via _handle_outline
        from tree_sitter_analyzer.cli.special_commands import _handle_outline

        cli_result_holder: list = []
        ctx = _make_context(
            asyncio_run=asyncio.run,
            output_json=lambda d: cli_result_holder.append(d),
        )
        args = SimpleNamespace(
            outline=str(target),
            outline_listed_cap=50,
            project_root=str(tmp_path),
            format="json",
            output_format="json",
            quiet=False,
        )
        rc = _handle_outline(args, ctx)
        assert rc == 0
        assert len(cli_result_holder) == 1
        cli_result = cli_result_holder[0]

        # Core keys that both paths must share (rich MCP schema)
        CORE_KEYS = {
            "success",
            "file_path",
            "language",
            "classes",
            "top_level_functions",
            "class_count",
            "method_count",
        }
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

        # Core values must agree
        assert cli_result["file_path"] == mcp_result["file_path"]
        assert cli_result["language"] == mcp_result["language"]
        assert cli_result["class_count"] == mcp_result["class_count"]
        assert cli_result["method_count"] == mcp_result["method_count"]
        # The rich schema: class has methods, extends, implements
        if cli_result["classes"]:
            cls = cli_result["classes"][0]
            assert "methods" in cls
            assert "extends" in cls
            assert "implements" in cls
