"""Tests for UML CLI parity with the codegraph_uml MCP tool."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

from tree_sitter_analyzer.cli.commands import mcp_commands


def _args(**overrides: Any) -> Namespace:
    defaults: dict[str, Any] = {
        "project_root": "/repo",
        "file_path": None,
        "uml": None,
        "uml_source": None,
        "uml_target": None,
        "uml_max_edges": 200,
        "uml_max_depth": 8,
        "uml_max_paths": 3,
        "uml_package_depth": 2,
        "uml_no_external_bases": False,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def test_uml_class_cli_forwards_arguments(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeUMLTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "mermaid": "classDiagram"}

    monkeypatch.setattr(mcp_commands, "CodeGraphUMLTool", FakeUMLTool)

    result = mcp_commands.handle_mcp_commands(
        _args(uml="class", uml_max_edges=25, uml_no_external_bases=True),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "diagram": "class",
            "source": None,
            "target": None,
            "max_edges": 25,
            "max_depth": 8,
            "max_paths": 3,
            "package_depth": 2,
            "include_external_bases": False,
            "output_format": "json",
        },
    }


def test_uml_sequence_cli_forwards_source_target(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeUMLTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "mermaid": "sequenceDiagram"}

    monkeypatch.setattr(mcp_commands, "CodeGraphUMLTool", FakeUMLTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            uml="sequence",
            uml_source="handler",
            uml_target="repository",
            uml_max_depth=5,
            uml_max_paths=2,
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["diagram"] == "sequence"
    assert seen["arguments"]["source"] == "handler"
    assert seen["arguments"]["target"] == "repository"
    assert seen["arguments"]["max_depth"] == 5
    assert seen["arguments"]["max_paths"] == 2
