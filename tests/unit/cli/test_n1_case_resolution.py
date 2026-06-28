#!/usr/bin/env python3
"""N1 (round-28): ``--case`` last-wins detection + ``meta.case_sensitive`` echo.

Reproduces the round-28 dogfood bug:

* ``--case sensitive --case insensitive`` silently overrode the first value.
* The response had no ``case_sensitive`` echo, so the caller couldn't tell
  which mode actually won.

The fix:

* CLI helper emits a stderr warning when ``--case`` is passed more than once,
  using last-wins (argparse's default).
* The MCP tool response's ``meta.case_sensitive`` is now a strict ``bool``
  (never ``None``): ``True`` only when the resolved case is ``"sensitive"``.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.cli.commands._case_resolution import (
    case_to_sensitive_bool,
    collect_case_args,
    warn_on_duplicate_case,
)
from tree_sitter_analyzer.mcp.tools.find_and_grep_helpers import build_search_meta

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class TestN1CaseResolutionHelpers:
    """Unit tests for the ``--case`` resolution helper."""

    def test_collect_case_args_space_form(self) -> None:
        argv = ["find-and-grep", "--case", "sensitive", "--query", "foo"]
        assert collect_case_args(argv) == ["sensitive"]

    def test_collect_case_args_equals_form(self) -> None:
        argv = ["find-and-grep", "--case=insensitive", "--query", "foo"]
        assert collect_case_args(argv) == ["insensitive"]

    def test_collect_case_args_duplicates(self) -> None:
        argv = [
            "find-and-grep",
            "--case",
            "sensitive",
            "--query",
            "foo",
            "--case",
            "insensitive",
        ]
        assert collect_case_args(argv) == ["sensitive", "insensitive"]

    def test_case_to_sensitive_bool_returns_bool(self) -> None:
        assert case_to_sensitive_bool("sensitive") is True
        assert case_to_sensitive_bool("insensitive") is False
        assert case_to_sensitive_bool("smart") is False
        assert case_to_sensitive_bool(None) is False
        # Strict bool — never None — even for unrecognized values.
        assert case_to_sensitive_bool("bogus") is False
        assert isinstance(case_to_sensitive_bool(None), bool)

    def test_warn_on_duplicate_case_no_duplicate(self) -> None:
        buf = io.StringIO()
        warned = warn_on_duplicate_case(
            "sensitive",
            argv=["find-and-grep", "--case", "sensitive"],
            stream=buf,
        )
        assert warned is False
        assert buf.getvalue() == ""

    def test_warn_on_duplicate_case_emits_warning(self) -> None:
        buf = io.StringIO()
        warned = warn_on_duplicate_case(
            "insensitive",
            argv=[
                "find-and-grep",
                "--case",
                "sensitive",
                "--case",
                "insensitive",
            ],
            stream=buf,
        )
        assert warned is True
        message = buf.getvalue()
        assert "warning:" in message
        assert "--case" in message
        assert "sensitive" in message
        assert "insensitive" in message
        # The resolved value (last-wins) is echoed so the caller knows
        # which one won.
        assert "insensitive" in message.rsplit("using last value:", 1)[-1]


class TestN1FindAndGrepCaseEcho:
    """find_and_grep emits a strict bool ``case_sensitive`` in ``meta``."""

    def test_case_sensitive_echoed_in_response(self) -> None:
        meta = build_search_meta(
            searched_file_count=10,
            truncated=False,
            fd_elapsed_ms=1,
            rg_elapsed_ms=2,
            case="sensitive",
        )
        assert meta["case_sensitive"] is True
        assert isinstance(meta["case_sensitive"], bool)

    def test_case_insensitive_echoed(self) -> None:
        meta = build_search_meta(
            searched_file_count=10,
            truncated=False,
            fd_elapsed_ms=1,
            rg_elapsed_ms=2,
            case="insensitive",
        )
        assert meta["case_sensitive"] is False
        assert isinstance(meta["case_sensitive"], bool)

    def test_default_case_echoed_as_bool(self) -> None:
        """Default ``--case`` (smart / missing) must echo as ``False`` — never None."""
        meta_smart = build_search_meta(
            searched_file_count=10,
            truncated=False,
            fd_elapsed_ms=1,
            rg_elapsed_ms=2,
            case="smart",
        )
        meta_missing = build_search_meta(
            searched_file_count=10,
            truncated=False,
            fd_elapsed_ms=1,
            rg_elapsed_ms=2,
            # case omitted on purpose — must still produce a bool.
        )
        for meta in (meta_smart, meta_missing):
            assert meta["case_sensitive"] is False
            assert isinstance(meta["case_sensitive"], bool)
            # The brief is explicit: NEVER None.
            assert meta["case_sensitive"] is not None


@pytest.mark.requires_ripgrep
class TestN1DuplicateCaseFlagsEmitWarning:
    """End-to-end check via subprocess for the CLI warning."""

    @pytest.mark.timeout(60)
    def test_duplicate_case_flags_emit_warning(self) -> None:
        """``--case sensitive --case insensitive`` warns on stderr.

        Verifies BOTH that the warning lands on stderr AND that the
        response echoes the last value (``case_sensitive=False`` since
        ``insensitive`` wins).
        """
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "tree_sitter_analyzer.cli.commands.find_and_grep_cli",
                "--roots",
                str(PROJECT_ROOT / "tree_sitter_analyzer"),
                "--query",
                "Foo",
                "--case",
                "sensitive",
                "--case",
                "insensitive",
                "--output-format",
                "json",
                "--project-root",
                str(PROJECT_ROOT),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=PROJECT_ROOT,
        )

        # The find-and-grep CLI is executed directly through the module
        # path. If the script fails for environmental reasons we still
        # want the test to fail loudly with the captured output so a
        # human can see what went wrong.
        assert proc.returncode == 0, (
            f"find-and-grep exited {proc.returncode}\n"
            f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}"
        )
        # The warning lands on stderr — last-wins is preserved.
        assert "warning:" in proc.stderr.lower(), (
            f"expected duplicate --case warning on stderr — got {proc.stderr!r}"
        )
        assert "--case" in proc.stderr
        # The response echoes the LAST value (insensitive → False).
        data: dict[str, Any] = json.loads(proc.stdout)
        assert data["meta"]["case_sensitive"] is False, (
            f"meta.case_sensitive must match the last --case value "
            f"(insensitive → False) — got {data['meta']['case_sensitive']!r}"
        )
        assert isinstance(data["meta"]["case_sensitive"], bool)


@pytest.mark.requires_ripgrep
class TestN1SearchContentCaseEcho:
    """search_content also emits a strict bool ``case_sensitive``."""

    @pytest.mark.asyncio
    async def test_search_content_default_case_is_bool_false(
        self, tmp_path: Path
    ) -> None:
        """Default ``case`` (no flag) → top-level ``case_sensitive=False bool``."""
        src = tmp_path / "src.py"
        src.write_text("def foo():\n    return 'FOO'\n")

        from tree_sitter_analyzer.mcp.tools.search_content_tool import (
            SearchContentTool,
        )

        tool = SearchContentTool(str(tmp_path))
        result = await tool.execute(
            {
                "roots": [str(tmp_path)],
                "query": "FOO",
                "output_format": "json",
            }
        )
        assert isinstance(result, dict)
        assert isinstance(result.get("case_sensitive"), bool), (
            f"search_content must echo a strict bool case_sensitive — "
            f"got {result.get('case_sensitive')!r}"
        )
        assert result["case_sensitive"] is False

    @pytest.mark.asyncio
    async def test_search_content_case_sensitive_is_bool_true(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "src.py"
        src.write_text("def foo():\n    return 'FOO'\n")

        from tree_sitter_analyzer.mcp.tools.search_content_tool import (
            SearchContentTool,
        )

        tool = SearchContentTool(str(tmp_path))
        result = await tool.execute(
            {
                "roots": [str(tmp_path)],
                "query": "FOO",
                "case": "sensitive",
                "output_format": "json",
            }
        )
        assert isinstance(result, dict)
        assert result["case_sensitive"] is True
        assert isinstance(result["case_sensitive"], bool)
