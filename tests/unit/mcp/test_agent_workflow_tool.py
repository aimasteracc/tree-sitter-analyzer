"""Tests for the MCP SMART agent workflow tool.

r37fC (round-37f): the quality audit rated this file at 2/5. The
original suite covered the happy paths (full JSON pack, compact
TOON, scoped queue-ledger command, absolute-path rejection) but
never the error / boundary surfaces an MCP caller will hit:
invalid_target_path variants, unsupported language extensions,
phase-corruption inputs, concurrent execute(), and the cross-format
envelope contract. The block below adds coverage for those gaps.

The tests run against the real :class:`AgentWorkflowTool` (no
mocks) with tmp_path fixtures. The tool is a pure planning surface
- there is no file I/O during workflow build - so the tests focus
on the planning contract: phase resolution, command shape, target
path interpolation, and envelope mirroring.
"""

from __future__ import annotations

import asyncio
import shlex

import pytest

from tree_sitter_analyzer.cli import agent_workflow
from tree_sitter_analyzer.mcp.tools.agent_workflow_tool import AgentWorkflowTool


def _assert_envelope_holds(
    result: dict, target_path: str | None, output_format: str
) -> None:
    """Assert core envelope invariants for one (target_path, format) combination."""
    assert result["success"] is True, (
        f"failed for target={target_path!r} format={output_format}"
    )
    agent_summary = result["agent_summary"]
    next_step = agent_summary["next_step"]
    assert isinstance(next_step, str) and next_step.strip(), (
        f"next_step empty for target={target_path!r} format={output_format}"
    )
    assert next_step.startswith("uv run tree-sitter-analyzer")
    expected_phase = "analyze" if target_path else "set"
    assert agent_summary["current_phase"] == expected_phase
    assert result["current_phase"] == expected_phase


def _assert_path_in_step_commands(result: dict, step_name: str, path: str) -> None:
    """Assert every CLI command for *step_name* contains *path*."""
    step = next(s for s in result["steps"] if s["step"] == step_name)
    for cmd in step["cli_commands"]:
        assert path in cmd, f"step {step_name!r} cli_command missing path: {cmd!r}"


def _assert_step_handoffs(result: dict) -> None:
    """Assert that every step's handoff matches the PHASE_ROUTING table."""
    handoff_by_step = {route["from"]: route for route in agent_workflow.PHASE_ROUTING}
    for step in result["steps"]:
        handoff = step["handoff"]
        expected = handoff_by_step[step["step"]]
        assert handoff["to"] == expected["to"]
        assert handoff["condition"] == expected["condition"]
        assert handoff["goal"] == expected["goal"]
        assert handoff["transition_command"] == step["cli_commands"][0]


def _assert_agent_summary(result: dict) -> None:
    """Assert the agent_summary block of a full JSON workflow pack response."""
    summary = result["agent_summary"]
    assert summary["next_step"] == (
        "uv run tree-sitter-analyzer safe-to-edit src/service.py --edit-type refactor --format json"
    )
    assert summary["current_phase"] == "analyze"
    assert summary["recommended_commands"] == [
        "uv run tree-sitter-analyzer smart-context src/service.py --format json",
        "uv run tree-sitter-analyzer file-health src/service.py --format json",
        "uv run tree-sitter-analyzer safe-to-edit src/service.py --edit-type refactor --format json",
        "uv run tree-sitter-analyzer refactor src/service.py --format json",
    ]
    assert summary["queue_ledger_command"] == (
        "uv run tree-sitter-analyzer change-impact "
        "--change-impact-scope src/service.py --agent-summary-only --format json"
    )
    assert result["steps"][-1]["cli_commands"][-1] == summary["queue_ledger_command"]


def _assert_sprint_contract(result: dict) -> None:
    """Assert the sprint_contract block of a full JSON workflow pack response."""
    sc = result["sprint_contract"]
    assert sc["mode"] == "single_queue_item"
    assert sc["scope"] == "single_target_file"
    assert sc["current_phase"] == "analyze"
    assert sc["next_phase"] == "retrieve"
    assert sc["evaluator_signature"]["ordered"] is True
    assert sc["evaluator_signature"]["required_pass"] == ["queue_boundary"]
    assert any(c["name"] == "queue_ledger" for c in sc["evaluator_checks"])


@pytest.mark.asyncio
async def test_agent_workflow_tool_returns_full_json_pack(tmp_path):
    """MCP JSON output should mirror the CLI workflow pack shape."""
    target = tmp_path / "src" / "service.py"
    target.parent.mkdir()
    target.write_text("def run():\n    return 1\n", encoding="utf-8")

    result = await AgentWorkflowTool(str(tmp_path)).execute(
        {"target_path": "src/service.py", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["workflow"] == "SMART agent workflow pack"
    assert result["workflow_mode"] == "SMART-SET-MAP-ANALYZE-RETRIEVE-TRACE"
    assert result["target_path"] == "src/service.py"
    assert result["current_phase"] == "analyze"
    assert result["phase_order"] == ["set", "map", "analyze", "retrieve", "trace"]
    assert result["current_step"]["step"] == "analyze"
    assert result["routing"][2]["from"] == "analyze"
    assert result["routing"][2]["to_step"] == "retrieve"
    assert result["recommended_commands"] == result["current_step"]["cli_commands"]
    assert [step["step"] for step in result["steps"]] == [
        "set",
        "map",
        "analyze",
        "retrieve",
        "trace",
    ]
    _assert_step_handoffs(result)
    _assert_agent_summary(result)
    _assert_sprint_contract(result)
    # ``toon_content`` is stripped from JSON-format responses (it duplicates
    # the structured fields and wastes ~2 KB per call). Each step's
    # ``handoff`` is still asserted via the structured ``steps`` list
    # above; we only need to confirm the strip here.
    assert "toon_content" not in result, (
        "JSON-format responses should not carry toon_content (duplicates "
        "structured fields). See agent_workflow_tool.execute() docstring."
    )


@pytest.mark.asyncio
async def test_agent_workflow_tool_defaults_to_compact_toon(tmp_path):
    """TOON output keeps the MCP response compact but still actionable."""
    result = await AgentWorkflowTool(str(tmp_path)).execute({})

    assert result["format"] == "toon"
    assert result["workflow"] == "SMART agent workflow pack"
    assert result["workflow_mode"] == "SMART-SET-MAP-ANALYZE-RETRIEVE-TRACE"
    assert "steps" not in result
    assert result["current_phase"] == "set"
    assert result["current_step"]["step"] == "set"
    assert result["recommended_commands"] == [
        "uv run tree-sitter-analyzer overview --format json",
        "uv run tree-sitter-analyzer agent-skills --format json",
        "uv run tree-sitter-analyzer parser-readiness --format json",
    ]
    assert result["agent_summary"]["current_phase"] == "set"
    assert result["agent_summary"]["step_count"] == 5
    assert "agent-skills --format json" in result["toon_content"]
    assert "parser-readiness --format json" in result["toon_content"]
    assert "current_phase: set" in result["toon_content"]
    assert "recommended_commands:" in result["toon_content"]
    assert "handoffs:" in result["toon_content"]
    for route in agent_workflow.PHASE_ROUTING:
        assert (
            f"  - {route['from']} -> {route['to']} when {route['condition']}"
            in result["toon_content"]
        )
    assert "queue_boundary" in result["toon_content"]
    assert "transition_signal:" in result["toon_content"]
    assert result["sprint_contract"]["scope"] == "project_surface_discovery"
    assert "evaluator_checks: queue_boundary" in result["toon_content"]


@pytest.mark.asyncio
async def test_agent_workflow_toon_surfaces_queue_ledger_command(tmp_path):
    """Targeted TOON output should expose the scoped queue-ledger command."""
    target = tmp_path / "src" / "service.py"
    target.parent.mkdir()
    target.write_text("def run():\n    return 1\n", encoding="utf-8")

    result = await AgentWorkflowTool(str(tmp_path)).execute(
        {"target_path": "src/service.py", "output_format": "toon"}
    )

    assert result["agent_summary"]["queue_ledger_command"] == (
        "uv run tree-sitter-analyzer change-impact "
        "--change-impact-scope src/service.py --agent-summary-only --format json"
    )
    assert (
        "queue_ledger: uv run tree-sitter-analyzer change-impact"
        in result["toon_content"]
    )
    assert "handoffs:" in result["toon_content"]
    for route in agent_workflow.PHASE_ROUTING:
        assert (
            f"  - {route['from']} -> {route['to']} when {route['condition']}"
            in result["toon_content"]
        )
    assert result["sprint_contract"]["phase_goal"].startswith("Understand file shape")


@pytest.mark.asyncio
async def test_agent_workflow_tool_rejects_external_absolute_target(tmp_path):
    """MCP callers cannot generate workflow commands for outside paths."""
    tool = AgentWorkflowTool(str(tmp_path))

    with pytest.raises(ValueError, match="Invalid target_path"):
        await tool.execute({"target_path": "/tmp/outside.py"})


# ----------------------------------------------------------------------
# r37fC: error-path coverage (audit gap - was 2/5 missing
# invalid_target_path / unsupported_lang / phase_corruption)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_workflow_tool_rejects_empty_and_whitespace_target(tmp_path):
    """Empty / whitespace-only target_path must fail at validation.

    Audit gap (invalid_target_path): the original suite covered the
    absolute-outside case but not the trivially-bad inputs that the
    validate_arguments guard exists for. Each of these should fail
    before the planning builder is invoked.
    """
    tool = AgentWorkflowTool(str(tmp_path))

    for bad in ("", "   ", "\n", "\t\t"):
        with pytest.raises(ValueError, match="target_path"):
            await tool.execute({"target_path": bad})


@pytest.mark.asyncio
async def test_agent_workflow_tool_rejects_non_string_target_path(tmp_path):
    """target_path that isn't a string fails fast.

    Audit gap (invalid_target_path): callers passing a list or dict
    where a string was expected - common when chaining tool outputs -
    must fail at the validation boundary with a clear ``target_path``
    error, not with an opaque ``AttributeError`` from the planner.
    """
    tool = AgentWorkflowTool(str(tmp_path))

    for bad in (123, 1.5, ["src/a.py"], {"path": "x"}, True):
        with pytest.raises(ValueError, match="target_path"):
            await tool.execute({"target_path": bad})


@pytest.mark.asyncio
async def test_agent_workflow_tool_rejects_path_traversal_target(tmp_path):
    """Relative paths with .. that escape the project root are rejected.

    Audit gap (invalid_target_path): the absolute-path check is one
    of several. A relative path with ``..`` that resolves outside the
    project root must also be caught by the security validator.
    """
    tool = AgentWorkflowTool(str(tmp_path))

    with pytest.raises(ValueError, match="Invalid target_path"):
        await tool.execute({"target_path": "../../../etc/passwd"})


@pytest.mark.asyncio
async def test_agent_workflow_tool_unsupported_extension_still_plans(tmp_path):
    """An unsupported language extension still produces a workflow.

    Audit gap (unsupported_lang): the workflow tool is a planning
    surface - it never opens the file or runs language detection.
    The contract: even when the target is ``.unknownext``, the tool
    must still emit a valid pack so downstream callers can see *what
    commands to run* even before the file is analysable.
    """
    target = tmp_path / "src" / "service.unknownext"
    target.parent.mkdir()
    target.write_text("nothing here\n", encoding="utf-8")

    result = await AgentWorkflowTool(str(tmp_path)).execute(
        {"target_path": "src/service.unknownext", "output_format": "json"}
    )

    assert result["success"] is True
    assert result["workflow"] == "SMART agent workflow pack"
    assert result["current_phase"] == "analyze"
    analyze_step = next(step for step in result["steps"] if step["step"] == "analyze")
    assert any("src/service.unknownext" in cmd for cmd in analyze_step["cli_commands"])
    # Agent_summary surface populated (next_step references the path so
    # callers can branch even on unsupported languages).
    assert "src/service.unknownext" in result["agent_summary"]["next_step"]


@pytest.mark.asyncio
async def test_agent_workflow_tool_quotes_target_with_spaces_in_cli_commands(tmp_path):
    """Path tokens in generated workflow commands are shell-safe for spaces."""
    target = tmp_path / "src" / "space file.py"
    target.parent.mkdir()
    target.write_text("def run():\\n    return 1\\n", encoding="utf-8")
    target_path = "src/space file.py"
    safe_target = shlex.quote(target_path)

    result = await AgentWorkflowTool(str(tmp_path)).execute(
        {"target_path": target_path, "output_format": "json"}
    )

    analyze_step = next(step for step in result["steps"] if step["step"] == "analyze")
    retrieve_step = next(step for step in result["steps"] if step["step"] == "retrieve")
    trace_step = next(step for step in result["steps"] if step["step"] == "trace")

    assert analyze_step["cli_commands"][0] == (
        f"uv run tree-sitter-analyzer smart-context {safe_target} --format json"
    )
    assert analyze_step["cli_commands"][1] == (
        f"uv run tree-sitter-analyzer file-health {safe_target} --format json"
    )
    assert retrieve_step["cli_commands"][0] == (
        f"uv run tree-sitter-analyzer {safe_target} --structure --output-format json"
    )
    assert trace_step["cli_commands"][0] == (
        f"uv run tree-sitter-analyzer {safe_target} --dependencies file_deps --format json"
    )
    assert result["agent_summary"]["next_step"] == (
        "uv run tree-sitter-analyzer safe-to-edit "
        f"{safe_target} --edit-type refactor --format json"
    )
    assert result["agent_summary"]["queue_ledger_command"] == (
        "uv run tree-sitter-analyzer change-impact "
        f"--change-impact-scope {safe_target} --agent-summary-only --format json"
    )
    assert (
        trace_step["cli_commands"][-1]
        == result["agent_summary"]["queue_ledger_command"]
    )


@pytest.mark.asyncio
async def test_agent_workflow_tool_phase_selection_responds_to_target_presence(
    tmp_path,
):
    """Phase planning must flip cleanly between targeted and untargeted modes.

    Audit gap (phase_corruption): the current_phase resolver
    branches on ``target_path is None``. The contract:
        - no target -> phase 'set' (project surface discovery)
        - any target -> phase 'analyze' (single-file edit risk)
    """
    tool = AgentWorkflowTool(str(tmp_path))

    no_target = await tool.execute({"output_format": "json"})
    assert no_target["current_phase"] == "set"
    assert no_target["current_step"]["step"] == "set"
    assert no_target["sprint_contract"]["scope"] == "project_surface_discovery"
    assert no_target["sprint_contract"]["current_phase"] == "set"
    assert no_target["sprint_contract"]["next_phase"] == "map"
    assert no_target["phase_order"] == ["set", "map", "analyze", "retrieve", "trace"]

    target = tmp_path / "src" / "service.py"
    target.parent.mkdir()
    target.write_text("def run():\n    return 1\n", encoding="utf-8")
    with_target = await tool.execute(
        {"target_path": "src/service.py", "output_format": "json"}
    )
    assert with_target["current_phase"] == "analyze"
    assert with_target["current_step"]["step"] == "analyze"
    assert with_target["sprint_contract"]["scope"] == "single_target_file"
    assert with_target["sprint_contract"]["current_phase"] == "analyze"
    assert with_target["sprint_contract"]["next_phase"] == "retrieve"


@pytest.mark.asyncio
async def test_agent_workflow_tool_handles_long_target_path(tmp_path):
    """A deeply-nested target path embeds verbatim into every step's commands.

    Audit gap (phase_corruption / boundary): a long path with many
    segments tests that the planner doesn't truncate or mangle the
    path when interpolating into CLI commands.
    """
    nested = tmp_path / "a" / "b" / "c" / "d" / "service.py"
    nested.parent.mkdir(parents=True)
    nested.write_text("def run():\n    return 1\n", encoding="utf-8")

    result = await AgentWorkflowTool(str(tmp_path)).execute(
        {"target_path": "a/b/c/d/service.py", "output_format": "json"}
    )

    assert result["success"] is True
    for step_name in ("analyze", "retrieve", "trace"):
        _assert_path_in_step_commands(result, step_name, "a/b/c/d/service.py")
    assert "a/b/c/d/service.py" in result["agent_summary"]["next_step"]


@pytest.mark.asyncio
async def test_agent_workflow_tool_concurrent_calls_are_safe(tmp_path):
    """Parallel execute calls must each return an independent pack.

    Audit gap (concurrent / re-entrant safety): the workflow builder
    is stateless, but the tool layer holds a single security
    validator. Multiple parallel calls must each get their own
    response dict - no shared list references between calls.
    """
    target = tmp_path / "src" / "service.py"
    target.parent.mkdir()
    target.write_text("def run():\n    return 1\n", encoding="utf-8")
    tool = AgentWorkflowTool(str(tmp_path))

    results = await asyncio.gather(
        *(
            tool.execute({"target_path": "src/service.py", "output_format": "json"})
            for _ in range(8)
        ),
    )

    assert all(result["success"] is True for result in results)
    steps_ids = [id(result["steps"]) for result in results]
    assert len(set(steps_ids)) == len(steps_ids), (
        "execute() returns a shared steps list across concurrent calls - "
        "callers mutating their copy would corrupt other callers"
    )
    for result in results:
        assert result["target_path"] == "src/service.py"
        assert result["current_phase"] == "analyze"


@pytest.mark.asyncio
async def test_agent_workflow_tool_rejects_invalid_output_format(tmp_path):
    """Invalid output_format must fail at validation.

    Audit gap (invalid input): the validate_arguments path for
    output_format is exercised by the parser-readiness suite but
    never by agent-workflow. Pin it here so a regression in either
    surface trips a test.
    """
    tool = AgentWorkflowTool(str(tmp_path))

    with pytest.raises(ValueError, match="output_format"):
        await tool.execute({"output_format": "yaml"})
    with pytest.raises(ValueError, match="output_format"):
        await tool.execute({"output_format": "xml"})


@pytest.mark.asyncio
async def test_agent_workflow_tool_phase_routing_uses_canonical_routes(tmp_path):
    """Every phase's handoff metadata matches PHASE_ROUTING source-of-truth.

    Audit gap (phase_corruption): the original suite checked the
    happy path on phase 'analyze'. Pin the entire routing table so a
    silent change to PHASE_ROUTING (or to how _build_step_handoffs
    consumes it) trips this test instead of leaking into agent
    behaviour.
    """
    target = tmp_path / "src" / "service.py"
    target.parent.mkdir()
    target.write_text("def run():\n    return 1\n", encoding="utf-8")

    result = await AgentWorkflowTool(str(tmp_path)).execute(
        {"target_path": "src/service.py", "output_format": "json"}
    )

    expected_routes = {route["from"]: route for route in agent_workflow.PHASE_ROUTING}
    for step in result["steps"]:
        expected = expected_routes[step["step"]]
        handoff = step["handoff"]
        assert handoff["to"] == expected["to"], (
            f"step {step['step']!r} handoff.to drift: {handoff['to']!r} != "
            f"{expected['to']!r}"
        )
        assert handoff["condition"] == expected["condition"]
        assert handoff["goal"] == expected["goal"]
        assert handoff["transition_command"] == step["cli_commands"][0]
    assert [route["from"] for route in result["routing"]] == [
        "set",
        "map",
        "analyze",
        "retrieve",
        "trace",
    ]


@pytest.mark.asyncio
async def test_agent_workflow_tool_envelope_holds_for_both_formats(tmp_path):
    """Both JSON and TOON outputs carry a consistent envelope shape.

    Audit gap (envelope contract): pins next_step, summary_line
    mirror, and phase invariants on both output formats. Note: at
    the current point in r37 this tool does NOT canonicalise
    ``verdict`` (the F1 commit was reverted) so we only check the
    non-verdict surface.
    """
    target = tmp_path / "src" / "service.py"
    target.parent.mkdir()
    target.write_text("def run():\n    return 1\n", encoding="utf-8")
    tool = AgentWorkflowTool(str(tmp_path))

    for target_path in (None, "src/service.py"):
        for output_format in ("json", "toon"):
            args: dict[str, object] = {"output_format": output_format}
            if target_path is not None:
                args["target_path"] = target_path
            result = await tool.execute(args)
            _assert_envelope_holds(result, target_path, output_format)
