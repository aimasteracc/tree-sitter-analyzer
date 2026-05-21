"""Tests for MCP-equivalent CLI command handlers."""

from __future__ import annotations

from argparse import Namespace
from typing import Any

import pytest

from tree_sitter_analyzer.cli.commands import mcp_commands

MCP_COMMAND_FLAGS = (
    "file_health",
    "parser_readiness",
    "project_health",
    "overview",
    "safe_to_edit",
    "change_impact",
    "dependencies",
    "refactor",
    "smart_context",
)


def _args(**overrides: Any) -> Namespace:
    defaults = dict.fromkeys(MCP_COMMAND_FLAGS, False)
    defaults["dependencies"] = None
    defaults.update(
        {
            "file_path": "target.py",
            "edit_type": "refactor",
            "project_root": "/repo",
            "min_grade": "C",
            "max_files": 30,
            "change_impact_mode": "diff",
            "change_impact_include_tests": True,
        }
    )
    defaults.update(overrides)
    return Namespace(**defaults)


@pytest.mark.parametrize(
    ("flag_overrides", "tool_attr", "expected_tool_args"),
    [
        (
            {"file_health": True},
            "FileHealthTool",
            {"file_path": "target.py", "output_format": "json"},
        ),
        (
            {"parser_readiness": True},
            "ParserReadinessTool",
            {
                "language": "target.py",
                "include_supported": False,
                "output_format": "json",
            },
        ),
        (
            {"project_health": True},
            "ProjectHealthTool",
            {"min_grade": "C", "max_files": 30, "output_format": "json"},
        ),
        (
            {"overview": True},
            "ProjectOverviewTool",
            {"include_health": True, "output_format": "json"},
        ),
        (
            {"safe_to_edit": True},
            "SafeToEditTool",
            {
                "file_path": "target.py",
                "edit_type": "refactor",
                "output_format": "json",
            },
        ),
        (
            {"change_impact": True},
            "ChangeImpactTool",
            {
                "mode": "diff",
                "pr_url": "",
                "include_tests": True,
                "output_format": "json",
                "scope_paths": [],
                "agent_summary_only": False,
            },
        ),
        (
            {"dependencies": "cycles"},
            "DependencyAnalysisTool",
            {"mode": "cycles", "output_format": "json"},
        ),
        (
            {"dependencies": "file_deps"},
            "DependencyAnalysisTool",
            {"mode": "file_deps", "output_format": "json", "file_path": "target.py"},
        ),
        (
            {"refactor": True},
            "RefactoringSuggestionsTool",
            {"file_path": "target.py", "output_format": "json"},
        ),
        (
            {"smart_context": True},
            "SmartContextTool",
            {"file_path": "target.py", "output_format": "json"},
        ),
    ],
)
def test_mcp_cli_commands_delegate_to_matching_tool(
    monkeypatch,
    flag_overrides: dict[str, Any],
    tool_attr: str,
    expected_tool_args: dict[str, Any],
) -> None:
    seen: dict[str, Any] = {}

    class FakeTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "tool": tool_attr, "toon_content": "compact"}

    monkeypatch.setattr(mcp_commands, tool_attr, FakeTool)

    output: list[dict[str, Any]] = []
    errors: list[str] = []

    result = mcp_commands.handle_mcp_commands(
        _args(**flag_overrides),
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 0
    assert errors == []
    assert output == [{"success": True, "tool": tool_attr, "toon_content": "compact"}]
    assert seen == {
        "project_root": "/repo",
        "arguments": expected_tool_args,
    }


def test_safe_to_edit_cli_forwards_requested_edit_type(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeSafeToEditTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "SafeToEditTool", FakeSafeToEditTool)

    result = mcp_commands.handle_mcp_commands(
        _args(safe_to_edit=True, edit_type="rename"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "file_path": "target.py",
            "edit_type": "rename",
            "output_format": "json",
        },
    }


def test_project_health_cli_forwards_requested_max_files(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeProjectHealthTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "ProjectHealthTool", FakeProjectHealthTool)

    result = mcp_commands.handle_mcp_commands(
        _args(project_health=True, max_files=7),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "min_grade": "C",
            "max_files": 7,
            "output_format": "json",
        },
    }


def test_parser_readiness_cli_forwards_language_option(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeParserReadinessTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "ParserReadinessTool", FakeParserReadinessTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            parser_readiness=True,
            file_path=None,
            parser_readiness_language="swift",
            parser_readiness_include_supported=True,
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "language": "swift",
            "include_supported": True,
            "output_format": "json",
        },
    }


def test_safe_to_edit_cli_falls_back_to_schema_default_for_legacy_namespaces(
    monkeypatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeSafeToEditTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "SafeToEditTool", FakeSafeToEditTool)

    args = _args(safe_to_edit=True)
    delattr(args, "edit_type")

    result = mcp_commands.handle_mcp_commands(
        args,
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["edit_type"] == "refactor"


@pytest.mark.parametrize(
    ("flag_overrides", "expected_error"),
    [
        ({"file_health": True}, "--file-health requires a file path"),
        ({"safe_to_edit": True}, "--safe-to-edit requires a file path"),
        (
            {"dependencies": "file_deps"},
            "--dependencies requires a file path for file_deps and blast_radius modes",
        ),
        (
            {"dependencies": "blast_radius"},
            "--dependencies requires a file path for file_deps and blast_radius modes",
        ),
        ({"refactor": True}, "--refactor requires a file path"),
        ({"smart_context": True}, "--smart-context requires a file path"),
    ],
)
def test_file_scoped_mcp_cli_commands_require_file_path(
    flag_overrides: dict[str, Any],
    expected_error: str,
) -> None:
    output: list[dict[str, Any]] = []
    errors: list[str] = []

    result = mcp_commands.handle_mcp_commands(
        _args(file_path=None, **flag_overrides),
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 1
    assert output == []
    assert errors == [expected_error]


@pytest.mark.parametrize(
    ("mode", "expected_mode"),
    [
        ("summary", "summary"),
        ("cycles", "cycles"),
        ("full", "summary"),
    ],
)
def test_project_scoped_dependency_modes_do_not_require_file_path(
    monkeypatch,
    mode: str,
    expected_mode: str,
) -> None:
    seen: dict[str, Any] = {}

    class FakeDependencyAnalysisTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(
        mcp_commands, "DependencyAnalysisTool", FakeDependencyAnalysisTool
    )

    result = mcp_commands.handle_mcp_commands(
        _args(file_path=None, dependencies=mode),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {"mode": expected_mode, "output_format": "json"},
    }


def test_mcp_cli_toon_output_prints_tool_toon_content(monkeypatch, capsys) -> None:
    class FakeProjectOverviewTool:
        def __init__(self, project_root: str | None = None) -> None:
            pass

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            return {"success": True, "toon_content": "project:compact"}

    monkeypatch.setattr(mcp_commands, "ProjectOverviewTool", FakeProjectOverviewTool)

    output: list[dict[str, Any]] = []
    errors: list[str] = []

    result = mcp_commands.handle_mcp_commands(
        _args(overview=True),
        output.append,
        errors.append,
        lambda: "toon",
    )

    assert result == 0
    assert errors == []
    assert output == []
    assert capsys.readouterr().out == "project:compact\n"


def test_change_impact_cli_does_not_require_file_path(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    output: list[dict[str, Any]] = []
    errors: list[str] = []
    args = Namespace(
        change_impact=True,
        file_path=None,
        project_root="/repo",
    )

    result = mcp_commands.handle_mcp_commands(
        args,
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 0
    assert errors == []
    assert output == [{"success": True, "changed_files": []}]
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "diff",
            "pr_url": "",
            "include_tests": True,
            "output_format": "json",
            "scope_paths": [],
            "agent_summary_only": False,
        },
    }


def test_change_impact_cli_forwards_scope_paths(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "changed_files": []}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            change_impact=True,
            change_impact_scope=[
                "tree_sitter_analyzer/mcp/tools",
                "tests/unit/mcp",
            ],
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "diff",
            "pr_url": "",
            "include_tests": True,
            "output_format": "json",
            "scope_paths": [
                "tree_sitter_analyzer/mcp/tools",
                "tests/unit/mcp",
            ],
            "agent_summary_only": False,
        },
    }


def test_change_impact_cli_forwards_agent_summary_only(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(change_impact=True, agent_summary_only=True),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "diff",
            "pr_url": "",
            "include_tests": True,
            "output_format": "json",
            "scope_paths": [],
            "agent_summary_only": True,
        },
    }


@pytest.mark.parametrize(
    "requested_mode",
    ["summary", "all_functions", "callers", "callees", "chain"],
)
def test_call_graph_cli_forwards_requested_mode(
    monkeypatch, requested_mode: str
) -> None:
    """G1: ``--call-graph <mode>`` must reach the tool with the requested mode.

    Before the fix, the dispatcher read ``args.call_graph_mode`` which does
    not exist (argparse stores the value into ``args.call_graph`` because the
    ``--call-graph`` definition does not set ``dest=``). The fallback default
    ``"summary"`` always won, so non-summary modes were silently ignored.
    """
    seen: dict[str, Any] = {}

    class FakeCodeGraphCallTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            # Echo the mode back so the test can assert on a real
            # ``response["mode"]`` field too.
            return {
                "success": True,
                "mode": arguments["mode"],
                "function_count": 0,
                "call_edge_count": 0,
            }

    monkeypatch.setattr(mcp_commands, "CodeGraphCallTool", FakeCodeGraphCallTool)

    output: list[dict[str, Any]] = []
    errors: list[str] = []

    # ``find_selected_mcp_command`` treats truthy ``args.call_graph`` as the
    # selector; argparse sets that to the chosen mode string when the flag
    # is present.
    result = mcp_commands.handle_mcp_commands(
        _args(call_graph=requested_mode, call_graph_function="execute"),
        output.append,
        errors.append,
        lambda: "json",
    )

    assert result == 0
    assert errors == []
    assert seen["arguments"]["mode"] == requested_mode
    assert output and output[0]["mode"] == requested_mode


def test_call_graph_cli_defaults_to_summary_when_no_mode_value(monkeypatch) -> None:
    """Bare ``--call-graph`` (no value) selects ``summary`` via argparse's
    ``const="summary"``. The dispatcher must preserve that and not crash on
    the missing attribute path."""
    seen: dict[str, Any] = {}

    class FakeCodeGraphCallTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True, "mode": arguments["mode"]}

    monkeypatch.setattr(mcp_commands, "CodeGraphCallTool", FakeCodeGraphCallTool)

    result = mcp_commands.handle_mcp_commands(
        _args(call_graph="summary"),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen["arguments"]["mode"] == "summary"


def test_change_impact_cli_forwards_mode_and_test_discovery_toggle(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class FakeChangeImpactTool:
        def __init__(self, project_root: str | None = None) -> None:
            seen["project_root"] = project_root

        async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
            seen["arguments"] = arguments
            return {"success": True}

    monkeypatch.setattr(mcp_commands, "ChangeImpactTool", FakeChangeImpactTool)

    result = mcp_commands.handle_mcp_commands(
        _args(
            change_impact=True,
            change_impact_mode="staged",
            change_impact_include_tests=False,
        ),
        lambda payload: None,
        lambda error: None,
        lambda: "json",
    )

    assert result == 0
    assert seen == {
        "project_root": "/repo",
        "arguments": {
            "mode": "staged",
            "pr_url": "",
            "include_tests": False,
            "output_format": "json",
            "scope_paths": [],
            "agent_summary_only": False,
        },
    }
