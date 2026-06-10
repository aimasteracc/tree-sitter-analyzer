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


# ── P1 CLI flag registration tests (RFC-0015) ──────────────────────────────────


def test_phase1_cli_flags_registered() -> None:
    """Phase-1 flags must be registered in the argument parser."""
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    long_flags = {
        s for a in parser._actions for s in a.option_strings if s.startswith("--")
    }
    for flag in ("--uml-file-path", "--uml-class-name", "--uml-include-tests"):
        assert flag in long_flags, f"Phase-1 CLI flag missing: {flag}"


def test_uml_cli_forwards_file_path(monkeypatch) -> None:
    """--uml-file-path is wired through _build_uml_tool_args → execute."""
    seen: dict[str, Any] = {}

    class FakeUMLTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "mermaid": "classDiagram"}

    monkeypatch.setattr(mcp_commands, "CodeGraphUMLTool", FakeUMLTool)

    # Build a namespace that includes the new P1 flags
    defaults: dict[str, Any] = {
        "project_root": "/repo",
        "file_path": None,
        "uml": "class",
        "uml_source": None,
        "uml_target": None,
        "uml_max_edges": 80,
        "uml_max_depth": 8,
        "uml_max_paths": 3,
        "uml_package_depth": 2,
        "uml_no_external_bases": False,
        "uml_file_path": "src/mymodule.py",
        "uml_class_name": None,
        "uml_include_tests": False,
    }

    result = mcp_commands.handle_mcp_commands(
        Namespace(**defaults),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["file_path"] == "src/mymodule.py"


def test_uml_cli_forwards_class_name(monkeypatch) -> None:
    """--uml-class-name is wired through _build_uml_tool_args → execute."""
    seen: dict[str, Any] = {}

    class FakeUMLTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "mermaid": "classDiagram"}

    monkeypatch.setattr(mcp_commands, "CodeGraphUMLTool", FakeUMLTool)

    defaults: dict[str, Any] = {
        "project_root": "/repo",
        "file_path": None,
        "uml": "class",
        "uml_source": None,
        "uml_target": None,
        "uml_max_edges": 80,
        "uml_max_depth": 8,
        "uml_max_paths": 3,
        "uml_package_depth": 2,
        "uml_no_external_bases": False,
        "uml_file_path": None,
        "uml_class_name": "MyClass",
        "uml_include_tests": False,
    }

    result = mcp_commands.handle_mcp_commands(
        Namespace(**defaults),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["class_name"] == "MyClass"


def test_uml_cli_forwards_include_tests(monkeypatch) -> None:
    """--uml-include-tests is wired through _build_uml_tool_args → execute."""
    seen: dict[str, Any] = {}

    class FakeUMLTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "mermaid": "classDiagram"}

    monkeypatch.setattr(mcp_commands, "CodeGraphUMLTool", FakeUMLTool)

    defaults: dict[str, Any] = {
        "project_root": "/repo",
        "file_path": None,
        "uml": "class",
        "uml_source": None,
        "uml_target": None,
        "uml_max_edges": 80,
        "uml_max_depth": 8,
        "uml_max_paths": 3,
        "uml_package_depth": 2,
        "uml_no_external_bases": False,
        "uml_file_path": None,
        "uml_class_name": None,
        "uml_include_tests": True,
    }

    result = mcp_commands.handle_mcp_commands(
        Namespace(**defaults),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"].get("include_tests") is True
