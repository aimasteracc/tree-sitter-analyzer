"""Claim invariant: 5 layers of safety.

README claim (Key Features section):
    "5 layers of safety. edit action=safe + edit action=guard + constraint DSL +
    edit action=impact + verdict envelopes — designed so agents *know* before
    they touch."

This smoke test asserts that:
    1. All 5 safety layers exist and are reachable.
    2. Each layer returns a response with the expected shape (verdict envelope).
    3. No layer throws an unhandled exception on a minimal invocation.

Layers:
    Layer 1: edit action=safe  (SafeToEditTool)
    Layer 2: edit action=guard (ModificationGuardTool)
    Layer 3: constraint DSL    (ConstraintCheckTool / check_constraints)
    Layer 4: edit action=impact (ChangeImpactTool)
    Layer 5: verdict envelopes (present on every tool response)
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

pytestmark = [pytest.mark.benchmark, pytest.mark.claims_benchmark]

_SAMPLE_PY = "def greet(name):\n    return f'Hello {name}'\n"


def _make_project(tmp: str) -> str:
    path = os.path.join(tmp, "sample.py")
    with open(path, "w") as f:
        f.write(_SAMPLE_PY)
    return path


# ─── Layer 1: edit action=safe ────────────────────────────────────────────────

def test_safety_layer_1_safe_to_edit_exists_and_returns_verdict():
    """Layer 1: SafeToEditTool must exist and return a verdict envelope."""
    from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool
    with tempfile.TemporaryDirectory() as tmp:
        fpath = _make_project(tmp)
        tool = SafeToEditTool(tmp)
        result = asyncio.run(tool.execute({"file_path": fpath, "output_format": "json"}))
        assert result.get("success") is not None, f"Missing 'success' key: {result}"
        assert "verdict" in result or "agent_summary" in result, (
            f"Layer 1 (safe_to_edit) response has no verdict envelope: {list(result.keys())}"
        )


# ─── Layer 2: edit action=guard ───────────────────────────────────────────────

def test_safety_layer_2_modification_guard_exists_and_returns_verdict():
    """Layer 2: ModificationGuardTool must exist and return a verdict envelope."""
    from tree_sitter_analyzer.mcp.tools.modification_guard_tool import ModificationGuardTool
    with tempfile.TemporaryDirectory() as tmp:
        _make_project(tmp)
        tool = ModificationGuardTool(tmp)
        result = asyncio.run(tool.execute({
            "symbol": "greet",
            "modification_type": "refactor",
            "output_format": "json",
        }))
        assert result.get("success") is not None, f"Missing 'success' key: {result}"
        assert "verdict" in result or "agent_summary" in result, (
            f"Layer 2 (modification_guard) response has no verdict envelope: {list(result.keys())}"
        )


# ─── Layer 3: constraint DSL ──────────────────────────────────────────────────

def test_safety_layer_3_constraint_check_exists_and_returns_verdict():
    """Layer 3: ConstraintCheckTool must exist and handle a project with no constraints."""
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ConstraintCheckTool
    with tempfile.TemporaryDirectory() as tmp:
        _make_project(tmp)
        tool = ConstraintCheckTool(tmp)
        result = asyncio.run(tool.execute({"output_format": "json"}))
        assert result.get("success") is not None, f"Missing 'success' key: {result}"
        # With no architectural-constraints.yml, verdict should be SAFE or INFO
        assert "verdict" in result or "agent_summary" in result, (
            f"Layer 3 (constraint_check) response has no verdict envelope: {list(result.keys())}"
        )


# ─── Layer 4: edit action=impact ─────────────────────────────────────────────

def test_safety_layer_4_change_impact_exists_and_returns_verdict():
    """Layer 4: ChangeImpactTool must exist and return a verdict envelope."""
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool
    with tempfile.TemporaryDirectory() as tmp:
        fpath = _make_project(tmp)
        tool = ChangeImpactTool(tmp)
        result = asyncio.run(tool.execute({"scope_paths": [fpath], "output_format": "json"}))
        assert result.get("success") is not None, f"Missing 'success' key: {result}"
        assert "verdict" in result or "agent_summary" in result, (
            f"Layer 4 (change_impact) response has no verdict envelope: {list(result.keys())}"
        )


# ─── Layer 5: verdict envelopes on ALL tools ─────────────────────────────────

def test_safety_layer_5_verdict_envelopes_present_on_all_safety_tools():
    """Layer 5: The verdict envelope must be present on all 4 safety tool responses.

    Asserts that the combined response surface (safe + guard + constraints + impact)
    always includes 'verdict' or 'agent_summary.verdict' so orchestrators can branch
    on outcomes without re-prompting.
    """
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ConstraintCheckTool
    from tree_sitter_analyzer.mcp.tools.modification_guard_tool import ModificationGuardTool
    from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

    with tempfile.TemporaryDirectory() as tmp:
        fpath = _make_project(tmp)
        tools_and_args = [
            (SafeToEditTool, {"file_path": fpath, "output_format": "json"}),
            (ModificationGuardTool, {"symbol": "greet", "modification_type": "refactor", "output_format": "json"}),
            (ConstraintCheckTool, {"output_format": "json"}),
            (ChangeImpactTool, {"scope_paths": [fpath], "output_format": "json"}),
        ]
        for tool_cls, args in tools_and_args:
            tool = tool_cls(tmp)
            result = asyncio.run(tool.execute(args))
            has_verdict = (
                "verdict" in result
                or ("agent_summary" in result and "verdict" in result.get("agent_summary", {}))
            )
            assert has_verdict, (
                f"{tool_cls.__name__} response missing verdict envelope. "
                f"Keys: {list(result.keys())}. "
                f"README claims '5 layers of safety' with verdict envelopes on every response."
            )


def test_all_five_safety_layer_classes_are_importable():
    """All 5 safety layers must be importable — presence is a prerequisite."""
    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool  # noqa: F401
    from tree_sitter_analyzer.mcp.tools.constraint_check_tool import ConstraintCheckTool  # noqa: F401
    from tree_sitter_analyzer.mcp.tools.modification_guard_tool import ModificationGuardTool  # noqa: F401
    from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool  # noqa: F401

    # Verdict envelope is a cross-cutting concern — all BaseMCPTool subclasses
    # are expected to include it (tested by test_safety_layer_5_*).
    from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool  # noqa: F401
