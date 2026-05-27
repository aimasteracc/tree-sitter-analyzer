"""CLI mapping contracts for UML Export Suite phase 1."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

import pytest

from tree_sitter_analyzer.cli.argument_parser_builder import create_argument_parser
from tree_sitter_analyzer.cli.commands import mcp_commands


def _args(**overrides: Any) -> Namespace:
    defaults: dict[str, Any] = {
        "file_path": "target.py",
        "project_root": "/repo",
        "class_hierarchy": False,
        "class_hierarchy_mode": "summary",
        "class_hierarchy_class": None,
        "class_hierarchy_depth": 10,
        "codegraph_visualize": False,
        "codegraph_visualize_mode": "full",
        "codegraph_visualize_file": None,
        "codegraph_visualize_function": None,
        "codegraph_visualize_depth": 3,
        "codegraph_visualize_max_edges": 150,
        "codegraph_visualize_direction": "TD",
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


def test_existing_class_hierarchy_all_mode_is_uml_class_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeClassHierarchyTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "classes": [], "toon_content": "class data"}

    monkeypatch.setattr(mcp_commands, "ClassHierarchyTool", FakeClassHierarchyTool)

    result = mcp_commands.handle_mcp_commands(
        _args(class_hierarchy=True, class_hierarchy_mode="all"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "all",
            "class_name": None,
            "max_depth": 10,
            "output_format": "json",
        },
    }


def test_existing_codegraph_visualize_cli_maps_function_diagram_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeCodeGraphVisualizeTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "mermaid": "flowchart LR"}

    monkeypatch.setattr(
        mcp_commands, "CodeGraphVisualizeTool", FakeCodeGraphVisualizeTool
    )

    result = mcp_commands.handle_mcp_commands(
        _args(
            codegraph_visualize=True,
            codegraph_visualize_mode="function",
            codegraph_visualize_function="parse_file",
            codegraph_visualize_depth=4,
            codegraph_visualize_max_edges=25,
            codegraph_visualize_direction="LR",
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "function",
            "file_path": None,
            "function": "parse_file",
            "depth": 4,
            "max_edges": 25,
            "direction": "LR",
            "output_format": "json",
        },
    }


@pytest.mark.parametrize("diagram", ["class", "package", "sequence", "component"])
def test_uml_parser_accepts_phase1_diagram_types(diagram: str) -> None:
    parser = create_argument_parser()

    args = parser.parse_args(["--uml", diagram, "--uml-max-edges", "50"])

    assert args.uml == diagram
    assert args.uml_max_edges == 50


def test_uml_parser_accepts_sequence_source_target_and_limits() -> None:
    parser = create_argument_parser()

    args = parser.parse_args(
        [
            "--uml",
            "sequence",
            "--uml-source",
            "handler",
            "--uml-target",
            "repository",
            "--uml-max-depth",
            "5",
            "--uml-max-paths",
            "2",
        ]
    )

    assert args.uml == "sequence"
    assert args.uml_source == "handler"
    assert args.uml_target == "repository"
    assert args.uml_max_depth == 5
    assert args.uml_max_paths == 2


def test_uml_parser_accepts_package_and_class_tuning_flags() -> None:
    parser = create_argument_parser()

    args = parser.parse_args(
        [
            "--uml",
            "class",
            "--uml-package-depth",
            "3",
            "--uml-no-external-bases",
        ]
    )

    assert args.uml == "class"
    assert args.uml_package_depth == 3
    assert args.uml_no_external_bases is True


def test_uml_cli_delegates_to_codegraph_uml_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeUMLTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "mermaid": "classDiagram"}

    monkeypatch.setattr(mcp_commands, "CodeGraphUMLTool", FakeUMLTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            uml="class",
            uml_max_edges=50,
            uml_package_depth=3,
            uml_no_external_bases=True,
        ),
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
            "max_edges": 50,
            "max_depth": 8,
            "max_paths": 3,
            "package_depth": 3,
            "include_external_bases": False,
            "output_format": "json",
        },
    }


def test_uml_sequence_cli_forwards_source_target_and_path_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
