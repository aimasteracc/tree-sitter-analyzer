from __future__ import annotations

import os
from typing import Any

from tree_sitter_analyzer.cli.commands import mcp_commands
from tree_sitter_analyzer.cli_main import create_argument_parser


def test_text_search_cli_delegates_exact_arguments(tmp_path, monkeypatch) -> None:
    parser = create_argument_parser()
    args = parser.parse_args(
        [
            "--project-root",
            str(tmp_path),
            "--text-search",
            "needle",
            "--text-search-root",
            "src",
            "--text-search-case",
            "insensitive",
            "--text-search-word",
            "--text-search-include",
            "*.py",
            "--text-search-exclude",
            "generated/**",
            "--text-search-limit",
            "7",
            "--format",
            "json",
        ]
    )
    seen: dict[str, Any] = {}

    class FakeTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "verdict": "INFO"}

    monkeypatch.setattr(mcp_commands, "TextSearchTool", FakeTool)
    output: list[dict[str, Any]] = []

    result = mcp_commands.handle_mcp_commands(
        args,
        output.append,
        lambda _message: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": str(tmp_path),
        "arguments": {
            "query": "needle",
            "root": "src",
            "case_mode": "insensitive",
            "word_match": True,
            "include_globs": ["*.py"],
            "exclude_globs": ["generated/**"],
            "limit": 7,
            "output_format": "json",
        },
    }


def test_text_search_has_declared_cli_and_facade_parity() -> None:
    from tree_sitter_analyzer.mcp.facade_map import NEW_ACTION_PARITY
    from tree_sitter_analyzer.mcp.tools.search_facade import build_search_facade

    parser = create_argument_parser()
    flags = {option for action in parser._actions for option in action.option_strings}

    assert NEW_ACTION_PARITY["search_text"] == (
        "search",
        "text",
        "--text-search",
    )
    assert "--text-search" in flags
    assert type(build_search_facade().action_map["text"]).__name__ == "TextSearchTool"


def test_text_search_cli_rejects_symlink_scope(tmp_path) -> None:
    if os.name == "nt":
        return

    source = tmp_path / "src"
    source.mkdir()
    (source / "a.py").write_text("needle\n", encoding="utf-8")
    os.symlink(source, tmp_path / "linked-src")
    parser = create_argument_parser()
    args = parser.parse_args(
        [
            "--project-root",
            str(tmp_path),
            "--text-search",
            "needle",
            "--text-search-root",
            "linked-src",
            "--format",
            "json",
        ]
    )
    output: list[dict[str, Any]] = []

    result = mcp_commands.handle_mcp_commands(
        args,
        output.append,
        lambda _message: None,
        lambda: "json",
    )

    assert result == 1
    assert output[0]["success"] is False
    assert output[0]["error_code"] == "SOURCE_ROOT_SYMLINK"


def test_text_search_cli_emits_json_for_missing_scope(tmp_path) -> None:
    parser = create_argument_parser()
    args = parser.parse_args(
        [
            "--project-root",
            str(tmp_path),
            "--text-search",
            "needle",
            "--text-search-root",
            "missing",
            "--format",
            "json",
        ]
    )
    output: list[dict[str, Any]] = []
    errors: list[str] = []

    result = mcp_commands.handle_mcp_commands(
        args,
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 1
    assert errors == []
    assert output[0]["success"] is False
    assert output[0]["error_code"] == "SOURCE_ROOT_UNAVAILABLE"
    assert output[0]["results"] == []


def test_text_search_cli_emits_json_for_outside_scope(tmp_path) -> None:
    parser = create_argument_parser()
    args = parser.parse_args(
        [
            "--project-root",
            str(tmp_path),
            "--text-search",
            "needle",
            "--text-search-root",
            "../outside",
            "--format",
            "json",
        ]
    )
    output: list[dict[str, Any]] = []
    errors: list[str] = []

    result = mcp_commands.handle_mcp_commands(
        args,
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 1
    assert errors == []
    assert output[0]["success"] is False
    assert output[0]["error_code"] == "INVALID_ARGUMENT"
    assert output[0]["results"] == []


def test_text_search_cli_emits_json_for_external_symlink(tmp_path) -> None:
    if os.name == "nt":
        return

    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    os.symlink(outside, tmp_path / "outside-link")
    parser = create_argument_parser()
    args = parser.parse_args(
        [
            "--project-root",
            str(tmp_path),
            "--text-search",
            "needle",
            "--text-search-root",
            "outside-link",
            "--format",
            "json",
        ]
    )
    output: list[dict[str, Any]] = []
    errors: list[str] = []

    result = mcp_commands.handle_mcp_commands(
        args,
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 1
    assert errors == []
    assert output[0]["success"] is False
    assert output[0]["error_code"] == "SOURCE_ROOT_OUTSIDE_PROJECT"
    assert output[0]["results"] == []


def test_text_search_cli_rejects_symlink_project_root(tmp_path) -> None:
    if os.name == "nt":
        return

    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("needle\n", encoding="utf-8")
    link = tmp_path / "project-link"
    os.symlink(project, link)
    parser = create_argument_parser()
    args = parser.parse_args(
        [
            "--project-root",
            str(link),
            "--text-search",
            "needle",
            "--format",
            "json",
        ]
    )
    output: list[dict[str, Any]] = []
    errors: list[str] = []

    result = mcp_commands.handle_mcp_commands(
        args,
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 1
    assert errors == []
    assert output[0]["success"] is False
    assert output[0]["error_code"] == "SOURCE_ROOT_SYMLINK"
    assert output[0]["results"] == []
