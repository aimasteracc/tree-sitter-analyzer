"""RFC-0026 NO1-010B: the benchmark surface stays internal-only.

A change-outcome benchmark is measurement infrastructure, not a product
surface. It must not acquire an MCP facade, a CLI flag, or a codemap surface —
RFC-0022's public-surface menu gate and the codemap-sync gate both apply. This
contract mirrors ``test_task_internal_only_contract.py`` and fails if any
future change registers the benchmark publicly.
"""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_no_benchmark_facade_is_registered() -> None:
    from tree_sitter_analyzer.mcp._tool_registry import create_tool_registry

    tools, _ = create_tool_registry(".")
    facade_names = {name for name, _ in tools}
    assert facade_names == {
        "search",
        "nav",
        "structure",
        "health",
        "edit",
        "project",
        "index",
        "viz",
    }


def test_no_benchmark_actions_hide_inside_the_edit_facade() -> None:
    from tree_sitter_analyzer.mcp.tools.edit_facade import build_edit_facade

    facade = build_edit_facade(None)
    actions = set(facade.action_map) | set(facade.bespoke_map)
    assert not {"benchmark", "vcsr", "no1_010b"} & actions


def test_cli_parser_has_no_benchmark_flags() -> None:
    from tree_sitter_analyzer.cli_main import create_argument_parser

    parser = create_argument_parser()
    flags = {option for action in parser._actions for option in action.option_strings}
    assert not {"--vcsr", "--benchmark", "--no1-010b"} & flags
    assert not any("vcsr" in flag for flag in flags)


def test_benchmark_package_declares_internal_only_status() -> None:
    package_init = REPO_ROOT / "tree_sitter_analyzer" / "no1_010b" / "__init__.py"
    docstring = package_init.read_text(encoding="utf-8").split('"""')[1]
    assert "internal experiment only" in docstring
    assert (
        "Not registered as an MCP facade, CLI command, or codemap surface" in docstring
    )


def test_module_route_is_the_only_entry_point() -> None:
    """No console script may expose the benchmark to end users."""
    import tomllib

    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    scripts = pyproject["project"].get("scripts", {})
    assert [name for name, target in scripts.items() if "no1_010b" in target] == []


def test_benchmark_runner_never_calls_a_model() -> None:
    """The runner is model-free; model spend is a human-gated ROADMAP decision."""
    package_dir = REPO_ROOT / "tree_sitter_analyzer" / "no1_010b"
    forbidden = ("anthropic", "openai", "litellm", "httpx", "requests", "urllib")
    for module in package_dir.glob("*.py"):
        for line in module.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            lowered = stripped.lower()
            assert not any(term in lowered for term in forbidden), (
                f"{module.name} reaches for a model client: {stripped}"
            )
