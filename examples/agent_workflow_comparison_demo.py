#!/usr/bin/env python3
"""Repeatable demo comparing unguided reading with SMART workflow context."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Comparison:
    """Context comparison for a single target symbol."""

    target_path: str
    symbol_name: str
    source_lines: int
    focused_lines: int
    baseline_tokens: int
    guided_tokens: int
    reduction_tokens: int
    reduction_percent: float
    workflow_next_step: str
    queue_boundary: str
    focused_range: str
    guided_context: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "target_path": self.target_path,
            "symbol_name": self.symbol_name,
            "source_lines": self.source_lines,
            "focused_lines": self.focused_lines,
            "baseline_tokens": self.baseline_tokens,
            "guided_tokens": self.guided_tokens,
            "reduction_tokens": self.reduction_tokens,
            "reduction_percent": round(self.reduction_percent, 1),
            "workflow_next_step": self.workflow_next_step,
            "queue_boundary": self.queue_boundary,
            "focused_range": self.focused_range,
            "guided_context": self.guided_context,
        }


def estimate_tokens(text: str) -> int:
    """Estimate LLM tokens with the common four-characters-per-token heuristic."""
    return max(1, (len(text) + 3) // 4)


def run_tree_sitter_analyzer(args: list[str], project_root: Path) -> Any:
    """Run the local CLI and parse JSON output."""
    command = [sys.executable, "-m", "tree_sitter_analyzer", *args]
    completed = subprocess.run(
        command,
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def build_guided_context(
    workflow_pack: dict[str, Any],
    method_result: dict[str, Any],
) -> dict[str, Any]:
    """Build the compact context an agent needs after SMART-guided retrieval."""
    return {
        "workflow_next_step": workflow_pack["agent_summary"]["next_step"],
        "queue_boundary": workflow_pack["queue_boundary_commands"][-1],
        "target_symbol": {
            "name": method_result["name"],
            "parent": method_result.get("parent"),
            "start_line": method_result["start_line"],
            "end_line": method_result["end_line"],
            "line_span": method_result["line_span"],
        },
        "focused_code": method_result["content"],
    }


def build_comparison(
    *,
    project_root: Path,
    target_path: str,
    symbol_name: str,
) -> Comparison:
    """Build the comparison by calling the same CLI a human would demo."""
    target_file = project_root / target_path
    source_text = target_file.read_text(encoding="utf-8")
    workflow_pack = run_tree_sitter_analyzer(
        ["agent-workflow", target_path, "--format", "json"],
        project_root,
    )
    method_results = run_tree_sitter_analyzer(
        [
            target_path,
            "--query-key",
            "methods",
            "--filter",
            f"name={symbol_name}",
            "--output-format",
            "json",
        ],
        project_root,
    )
    method_result = _select_method(method_results, symbol_name)
    guided_context = build_guided_context(workflow_pack, method_result)
    guided_text = json.dumps(guided_context, indent=2)

    baseline_tokens = estimate_tokens(source_text)
    guided_tokens = estimate_tokens(guided_text)
    reduction_tokens = baseline_tokens - guided_tokens
    reduction_percent = (
        (reduction_tokens / baseline_tokens) * 100 if baseline_tokens else 0.0
    )
    return Comparison(
        target_path=target_path,
        symbol_name=symbol_name,
        source_lines=len(source_text.splitlines()),
        focused_lines=method_result["line_span"],
        baseline_tokens=baseline_tokens,
        guided_tokens=guided_tokens,
        reduction_tokens=reduction_tokens,
        reduction_percent=reduction_percent,
        workflow_next_step=workflow_pack["agent_summary"]["next_step"],
        queue_boundary=workflow_pack["queue_boundary_commands"][-1],
        focused_range=f"{method_result['start_line']}-{method_result['end_line']}",
        guided_context=guided_context,
    )


def _select_method(
    method_results: list[dict[str, Any]], symbol_name: str
) -> dict[str, Any]:
    """Return the exact method match from query results."""
    for method in method_results:
        if method.get("name") == symbol_name:
            return method
    raise ValueError(f"Method not found: {symbol_name}")


def format_markdown(comparison: Comparison) -> str:
    """Render a concise demo report suitable for terminal output or README snippets."""
    data = comparison.to_dict()
    return "\n".join(
        [
            "# Agent Workflow Comparison Demo",
            "",
            f"Target: `{data['target_path']}`",
            f"Symbol: `{data['symbol_name']}` (`{data['focused_range']}`)",
            "",
            "| Scenario | Lines Read | Estimated Tokens |",
            "| --- | ---: | ---: |",
            f"| Without Tree-sitter Analyzer | {data['source_lines']} | {data['baseline_tokens']} |",
            f"| With SMART workflow context | {data['focused_lines']} | {data['guided_tokens']} |",
            "",
            (
                f"Reduction: {data['reduction_tokens']} estimated tokens "
                f"({data['reduction_percent']}%)."
            ),
            "",
            "Next step from workflow pack:",
            f"`{data['workflow_next_step']}`",
            "",
            "Queue boundary:",
            f"`{data['queue_boundary']}`",
        ]
    )


def format_asciicast(comparison: Comparison) -> str:
    """Render an asciinema v2 recording payload for repeatable demo evidence."""
    command = " ".join(
        [
            "uv",
            "run",
            "python",
            "examples/agent_workflow_comparison_demo.py",
            "--target",
            shlex.quote(comparison.target_path),
            "--symbol",
            shlex.quote(comparison.symbol_name),
        ]
    )
    frames = [f"$ {command}\r\n"]
    frames.extend(f"{line}\r\n" for line in format_markdown(comparison).splitlines())
    lines = [
        json.dumps(
            {
                "version": 2,
                "width": 100,
                "height": 28,
                "env": {"TERM": "xterm-256color"},
            },
            separators=(",", ":"),
        )
    ]
    elapsed = 0.25
    for frame in frames:
        lines.append(json.dumps([round(elapsed, 2), "o", frame], separators=(",", ":")))
        elapsed += 0.35
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the demo."""
    parser = argparse.ArgumentParser(
        description="Compare full-file reading with SMART workflow guided context.",
    )
    parser.add_argument(
        "--target",
        default="examples/BigService.java",
        help="Project-relative file to analyze.",
    )
    parser.add_argument(
        "--symbol",
        default="updateCustomerName",
        help="Method name to retrieve for the focused-context scenario.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "cast"],
        default="markdown",
        help="Demo output format.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the demo."""
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parent.parent
    comparison = build_comparison(
        project_root=project_root,
        target_path=args.target,
        symbol_name=args.symbol,
    )
    if args.format == "json":
        print(json.dumps(comparison.to_dict(), indent=2))
    elif args.format == "cast":
        print(format_asciicast(comparison), end="")
    else:
        print(format_markdown(comparison))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
