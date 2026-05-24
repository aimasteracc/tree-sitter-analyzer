"""Tests for the repeatable agent workflow comparison demo."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "examples"
    / "agent_workflow_comparison_demo.py"
)
SPEC = importlib.util.spec_from_file_location(
    "agent_workflow_comparison_demo", MODULE_PATH
)
assert SPEC and SPEC.loader
demo = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = demo
SPEC.loader.exec_module(demo)


def _comparison() -> demo.Comparison:
    return demo.Comparison(
        target_path="examples/BigService.java",
        symbol_name="updateCustomerName",
        source_lines=1419,
        focused_lines=17,
        baseline_tokens=1000,
        guided_tokens=100,
        reduction_tokens=900,
        reduction_percent=90.0,
        workflow_next_step="safe-to-edit examples/BigService.java",
        queue_boundary="uv run pytest -q",
        focused_range="601-617",
        guided_context={},
    )


def test_estimate_tokens_uses_four_character_heuristic():
    assert demo.estimate_tokens("abcd") == 1
    assert demo.estimate_tokens("abcde") == 2
    assert demo.estimate_tokens("") == 1


def test_build_guided_context_keeps_only_agent_decision_surface():
    workflow_pack = {
        "agent_summary": {"next_step": "safe-to-edit target.java"},
        "queue_boundary_commands": ["change-impact", "uv run pytest -q"],
    }
    method_result = {
        "name": "updateCustomerName",
        "parent": "BigService",
        "start_line": 601,
        "end_line": 617,
        "line_span": 17,
        "content": "public void updateCustomerName() {}",
    }

    context = demo.build_guided_context(workflow_pack, method_result)

    assert context == {
        "workflow_next_step": "safe-to-edit target.java",
        "queue_boundary": "uv run pytest -q",
        "target_symbol": {
            "name": "updateCustomerName",
            "parent": "BigService",
            "start_line": 601,
            "end_line": 617,
            "line_span": 17,
        },
        "focused_code": "public void updateCustomerName() {}",
    }


def test_format_markdown_reports_reduction():
    output = demo.format_markdown(_comparison())

    assert "Without Tree-sitter Analyzer" in output
    assert "With SMART workflow context" in output
    assert "Reduction: 900 estimated tokens (90.0%)." in output


def test_format_asciicast_returns_asciinema_v2_json_lines():
    output = demo.format_asciicast(_comparison())

    lines = output.splitlines()
    header = json.loads(lines[0])
    events = [json.loads(line) for line in lines[1:]]

    assert header == {
        "version": 2,
        "width": 100,
        "height": 28,
        "env": {"TERM": "xterm-256color"},
    }
    assert events[0][1] == "o"
    assert all(event[1] == "o" for event in events)
    recording_text = "".join(event[2] for event in events)
    assert (
        "$ uv run python examples/agent_workflow_comparison_demo.py" in recording_text
    )
    assert "--target examples/BigService.java" in recording_text
    assert "--symbol updateCustomerName" in recording_text
    assert "Reduction: 900 estimated tokens (90.0%)." in recording_text
