#!/usr/bin/env python3
"""Tests for ``tree_sitter_analyzer.cli.capability_commands`` (RFC-0027 §L7/§L8).

These pin the CLI half of the Three-Surface table: each flag routes to the same
facade action its MCP twin uses, so parity is structural rather than a second
implementation that can drift.
"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from tree_sitter_analyzer.cli.capability_commands import handle_capability_actions


@dataclass
class _Recorder:
    """Captures what the handler emitted, standing in for the real context."""

    payloads: list[dict[str, Any]]
    errors: list[str]

    def output_json(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)

    def output_error(self, message: Any) -> None:
        self.errors.append(str(message))


def _ctx() -> _Recorder:
    return _Recorder(payloads=[], errors=[])


def _args(**overrides: Any) -> Namespace:
    base: dict[str, Any] = {
        "project_root": ".",
        "output_format": "json",
        "project_card": False,
        "plan_rename": None,
        "plan_rename_to": None,
        "refactor_queue": False,
        "refactor_queue_top_n": 5,
    }
    base.update(overrides)
    return Namespace(**base)


class _FakeFacade:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute(self, tool_args: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(tool_args)
        return {"success": True}


def test_no_flag_returns_none() -> None:
    assert handle_capability_actions(_args(), _ctx()) is None


class TestProjectCard:
    def test_routes_to_project_action_card(self) -> None:
        fake = _FakeFacade()
        with patch(
            "tree_sitter_analyzer.mcp.tools.project_facade.build_project_facade",
            return_value=fake,
        ):
            handle_capability_actions(_args(project_card=True), _ctx())
        assert fake.calls[0]["action"] == "card"

    def test_returns_zero_on_success(self) -> None:
        fake = _FakeFacade()
        with patch(
            "tree_sitter_analyzer.mcp.tools.project_facade.build_project_facade",
            return_value=fake,
        ):
            code = handle_capability_actions(_args(project_card=True), _ctx())
        assert code == 0


class TestPlanRename:
    def test_missing_new_name_is_an_error(self) -> None:
        ctx = _ctx()
        code = handle_capability_actions(_args(plan_rename="foo"), ctx)
        assert code == 1

    def test_missing_new_name_says_which_flag_to_add(self) -> None:
        ctx = _ctx()
        handle_capability_actions(_args(plan_rename="foo"), ctx)
        assert ctx.errors == ["--plan-rename requires --plan-rename-to NEW_NAME"]

    def test_routes_to_edit_action_plan_rename(self) -> None:
        fake = _FakeFacade()
        with patch(
            "tree_sitter_analyzer.mcp.tools.edit_facade.build_edit_facade",
            return_value=fake,
        ):
            handle_capability_actions(
                _args(plan_rename="foo", plan_rename_to="bar"), _ctx()
            )
        assert fake.calls[0]["action"] == "plan_rename"

    def test_sends_no_mode_argument(self) -> None:
        """The CLI cannot express an apply — there is no mode on the wire."""
        fake = _FakeFacade()
        with patch(
            "tree_sitter_analyzer.mcp.tools.edit_facade.build_edit_facade",
            return_value=fake,
        ):
            handle_capability_actions(
                _args(plan_rename="foo", plan_rename_to="bar"), _ctx()
            )
        assert set(fake.calls[0]) == {
            "action",
            "symbol",
            "new_name",
            "output_format",
        }

    def test_real_preview_writes_no_source_file(self, tmp_path: Path) -> None:
        # The write-freedom claim, at the CLI surface too.
        (tmp_path / "m.py").write_text(
            "def target():\n    return 1\n", encoding="utf-8"
        )
        before = {
            p.relative_to(tmp_path).as_posix(): p.read_bytes()
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file()
        }
        handle_capability_actions(
            _args(
                project_root=str(tmp_path),
                plan_rename="target",
                plan_rename_to="renamed",
            ),
            _ctx(),
        )
        after = {
            p.relative_to(tmp_path).as_posix(): p.read_bytes()
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file()
        }
        assert {k: v for k, v in after.items() if k in before} == before


class TestRefactorQueue:
    def test_routes_to_health_action_refactor_queue(self) -> None:
        fake = _FakeFacade()
        with patch(
            "tree_sitter_analyzer.mcp.tools.health_facade.build_health_facade",
            return_value=fake,
        ):
            handle_capability_actions(_args(refactor_queue=True), _ctx())
        assert fake.calls[0]["action"] == "refactor_queue"

    def test_forwards_top_n(self) -> None:
        fake = _FakeFacade()
        with patch(
            "tree_sitter_analyzer.mcp.tools.health_facade.build_health_facade",
            return_value=fake,
        ):
            handle_capability_actions(
                _args(refactor_queue=True, refactor_queue_top_n=3), _ctx()
            )
        assert fake.calls[0]["top_n"] == 3


class TestFailureHandling:
    def test_facade_exception_returns_one(self) -> None:
        class _Boom:
            async def execute(self, tool_args: dict[str, Any]) -> dict[str, Any]:
                raise RuntimeError("kaboom")

        with patch(
            "tree_sitter_analyzer.mcp.tools.project_facade.build_project_facade",
            return_value=_Boom(),
        ):
            code = handle_capability_actions(_args(project_card=True), _ctx())
        assert code == 1

    def test_unsuccessful_result_returns_one(self) -> None:
        class _Sad:
            async def execute(self, tool_args: dict[str, Any]) -> dict[str, Any]:
                return {"success": False, "error": "nope"}

        with patch(
            "tree_sitter_analyzer.mcp.tools.project_facade.build_project_facade",
            return_value=_Sad(),
        ):
            code = handle_capability_actions(_args(project_card=True), _ctx())
        assert code == 1
