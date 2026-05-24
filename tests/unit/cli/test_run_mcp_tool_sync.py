#!/usr/bin/env python3
"""Regression tests for the shared ``_run_mcp_tool_sync`` helper.

r37at (dogfood): consolidates the inline 4-step boilerplate
``tool = X(project_root=...); result = asyncio_run(tool.execute(payload));
_print_result(...); return 0/1`` previously duplicated in
``cli/special_commands.py`` at the partial-read / health-check /
batch-metrics handlers.

The helper itself is tiny; the tests cover:
  * tool_cls is instantiated with ``project_root=``
  * ``context.asyncio_run`` is invoked with ``tool.execute(payload)``
  * ``_print_result`` is called with the awaited result
  * exit code is 0 when ``result["success"] is True``
  * exit code is 1 when ``result["success"] is False``
  * exit code is 1 when the ``success`` key is absent
  * anti-duplication: ``asyncio_run(... tool.execute(...))`` only appears in
    the helper itself, not anywhere else in ``cli/special_commands.py``.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from tree_sitter_analyzer.cli import special_commands
from tree_sitter_analyzer.cli.special_commands import (
    SpecialCommandContext,
    _run_mcp_tool_sync,
)


def _make_context(
    asyncio_run: MagicMock, output_json: MagicMock
) -> SpecialCommandContext:
    """Build a SpecialCommandContext whose dependencies are mocks."""
    return SpecialCommandContext(
        asyncio_run=asyncio_run,
        output_json=output_json,
        output_error=MagicMock(),
        output_info=MagicMock(),
        output_list=MagicMock(),
        query_loader=MagicMock(),
    )


def _make_args(format_: str = "json") -> SimpleNamespace:
    """Build an argparse-like Namespace stub for ``_print_result``."""
    return SimpleNamespace(format=format_, output_format=format_)


class TestRunMcpToolSync:
    """Cover the four observable behaviours of ``_run_mcp_tool_sync``."""

    def test_instantiates_tool_with_project_root(self) -> None:
        tool_cls = MagicMock(name="ToolCls")
        tool_cls.return_value.execute = MagicMock(return_value="awaitable")
        asyncio_run = MagicMock(return_value={"success": True})
        output_json = MagicMock()
        context = _make_context(asyncio_run, output_json)
        payload = {"foo": "bar"}

        rc = _run_mcp_tool_sync(
            tool_cls,
            payload,
            project_root="/tmp/proj",
            args=_make_args(),
            context=context,
        )

        tool_cls.assert_called_once_with(project_root="/tmp/proj")
        # ``tool.execute`` is called with the exact payload dict.
        tool_cls.return_value.execute.assert_called_once_with(payload)
        # ``context.asyncio_run`` receives the awaitable returned by
        # ``tool.execute(payload)``.
        asyncio_run.assert_called_once_with("awaitable")
        assert rc == 0

    def test_returns_one_when_success_false(self) -> None:
        tool_cls = MagicMock(name="ToolCls")
        tool_cls.return_value.execute = MagicMock(return_value="awaitable")
        asyncio_run = MagicMock(return_value={"success": False, "error": "boom"})
        context = _make_context(asyncio_run, MagicMock())

        rc = _run_mcp_tool_sync(
            tool_cls,
            {},
            project_root=".",
            args=_make_args(),
            context=context,
        )

        assert rc == 1

    def test_returns_one_when_success_key_absent(self) -> None:
        tool_cls = MagicMock(name="ToolCls")
        tool_cls.return_value.execute = MagicMock(return_value="awaitable")
        asyncio_run = MagicMock(return_value={"other": "field"})
        context = _make_context(asyncio_run, MagicMock())

        rc = _run_mcp_tool_sync(
            tool_cls,
            {},
            project_root=".",
            args=_make_args(),
            context=context,
        )

        assert rc == 1

    def test_print_result_receives_full_envelope_in_json(self, monkeypatch) -> None:
        """The helper hands the awaited envelope to ``_print_result``."""
        result_payload = {"success": True, "data": [1, 2, 3]}
        tool_cls = MagicMock(name="ToolCls")
        tool_cls.return_value.execute = MagicMock(return_value="awaitable")
        asyncio_run = MagicMock(return_value=result_payload)
        output_json = MagicMock()
        context = _make_context(asyncio_run, output_json)

        # JSON path: ``_print_result`` calls ``output_json(result)`` directly.
        rc = _run_mcp_tool_sync(
            tool_cls,
            {},
            project_root=".",
            args=_make_args("json"),
            context=context,
        )

        output_json.assert_called_once_with(result_payload)
        assert rc == 0

    def test_print_result_uses_output_toon_in_toon_mode(self, monkeypatch) -> None:
        """TOON path: ``_print_result`` routes through ``output_toon`` helper."""
        result_payload = {"success": True, "toon_content": "k:v"}
        tool_cls = MagicMock(name="ToolCls")
        tool_cls.return_value.execute = MagicMock(return_value="awaitable")
        asyncio_run = MagicMock(return_value=result_payload)
        output_json = MagicMock()
        context = _make_context(asyncio_run, output_json)

        captured_toon: list[str] = []
        monkeypatch.setattr(
            "tree_sitter_analyzer.output_manager.output_toon",
            lambda s: captured_toon.append(s),
        )

        rc = _run_mcp_tool_sync(
            tool_cls,
            {},
            project_root=".",
            args=_make_args("toon"),
            context=context,
        )

        assert captured_toon == ["k:v"]
        # JSON output channel is NOT called when TOON is active.
        output_json.assert_not_called()
        assert rc == 0


class TestAntiDuplicationGuard:
    """Lock down the helper as the only inline-asyncio-execute site.

    r37at (dogfood): without this guard, a future refactor could quietly
    re-introduce ``context.asyncio_run(tool.execute(...))`` boilerplate
    in the handler bodies. Allow exactly one match — the helper itself.
    """

    _PATTERN = re.compile(r"asyncio_run\([^)]*tool\.execute\(")

    def test_only_helper_contains_inline_asyncio_run_execute(self) -> None:
        source = Path(special_commands.__file__).read_text(encoding="utf-8")
        matches = self._PATTERN.findall(source)
        # The single allowed match is inside ``_run_mcp_tool_sync`` itself
        # (the canonical helper). If you add another, you are reintroducing
        # the duplication r37at consolidated.
        assert len(matches) == 1, (
            f"r37at guard broken: ``asyncio_run(... tool.execute(...))`` now "
            f"appears {len(matches)} times in special_commands.py. Route new "
            f"call sites through ``_run_mcp_tool_sync``."
        )
