#!/usr/bin/env python3
"""auto_review — drive the project's own analyzer against itself and emit a
machine-readable sprint plan.

This is the *safe* counterpart to a fully-autonomous coding loop. It does:

  1. `--project-health` to score every source file and rank refactor targets.
  2. `--code-patterns` on each backlog file to surface concrete smells.
  3. `--change-impact` on the current git diff to predict test surface.
  4. `--detect-routes summary` to capture the framework footprint.

It does NOT:
  * commit
  * push
  * skip pre-commit hooks
  * pass --dangerously-skip-permissions to any agent
  * mutate any source file

Output is a single JSON document on stdout (or to ``--out path``) that lists
prioritised work items plus, for each one, the exact verification commands the
project's own change-impact tool says you must run after editing. A human or a
properly-sandboxed Claude Code session can then consume the plan and act on it.

Exit codes
----------
0  Plan written, no work required (health was clean).
1  Plan written, work items found (used by CI to surface the issue).
2  A tool invocation failed (unexpected — investigate).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

TOOL_BIN = [sys.executable, "-m", "tree_sitter_analyzer"]


def _run_tool(args: list[str], *, timeout: int = 240) -> dict[str, Any]:
    """Run the analyzer with --output-format json and parse the result."""
    cmd = [*TOOL_BIN, *args, "--output-format", "json"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"timeout after {timeout}s", "cmd": cmd}
    if proc.returncode != 0:
        return {
            "success": False,
            "error": f"exit {proc.returncode}",
            "stderr": proc.stderr.strip()[:400],
            "cmd": cmd,
        }
    try:
        parsed: dict[str, Any] = json.loads(proc.stdout)
        return parsed
    except json.JSONDecodeError as exc:
        return {
            "success": False,
            "error": f"json decode: {exc}",
            "stdout_head": proc.stdout[:200],
            "cmd": cmd,
        }


@dataclass
class WorkItem:
    """One unit of work the autonomous loop can hand to a specialist agent."""

    file_path: str
    priority: str
    grade: str
    score: float
    signal: str
    weakest_dimension: str
    safety_command: list[str]
    refactor_command: list[str]
    post_edit_commands: list[list[str]]
    patterns: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "priority": self.priority,
            "grade": self.grade,
            "score": self.score,
            "signal": self.signal,
            "weakest_dimension": self.weakest_dimension,
            "safety_command": self.safety_command,
            "refactor_command": self.refactor_command,
            "post_edit_commands": self.post_edit_commands,
            "patterns": self.patterns,
        }


def _shellify(cmd: str) -> list[str]:
    """Turn the project's recommended CLI string into a list[str] for subprocess."""
    return cmd.split()


def collect_backlog(max_items: int) -> list[WorkItem]:
    health = _run_tool(["--project-health", "--min-grade", "D", "--max-files", str(max_items)])
    if not health.get("success"):
        raise RuntimeError(f"project-health failed: {health}")
    items: list[WorkItem] = []
    for entry in health.get("agent_backlog", [])[:max_items]:
        items.append(
            WorkItem(
                file_path=entry["file"],
                priority=entry.get("priority", "high"),
                grade=entry.get("grade", "?"),
                score=float(entry.get("score", 0.0)),
                signal=entry.get("signal", ""),
                weakest_dimension=entry.get("weakest_dimension", ""),
                safety_command=_shellify(entry.get("safety_cli_command", "")),
                refactor_command=_shellify(entry.get("recommended_cli_command", "")),
                post_edit_commands=[
                    _shellify(c) for c in entry.get("post_edit_commands", [])
                ],
            )
        )
    return items


def enrich_with_patterns(items: list[WorkItem]) -> None:
    """Run --code-patterns on each work item to attach concrete smells."""
    for item in items:
        result = _run_tool(["--code-patterns", item.file_path], timeout=60)
        if result.get("success"):
            # Skip docstring-located print noise so the plan stays signal-heavy.
            raw = result.get("patterns", [])
            item.patterns = [
                p for p in raw if not _looks_like_docstring_example(item.file_path, p)
            ]


def _looks_like_docstring_example(file_path: str, pattern: dict[str, Any]) -> bool:
    """Skip print-in-production hits whose line is inside a triple-quoted block.

    This is a small dogfood-of-dogfood: the --code-patterns tool itself flags
    Python `print()` calls in docstring examples (see route_detector.py:122).
    Until that tool gets a "skip docstring" pass, the auto-review filter mutes
    the noise so the plan only highlights real production issues.
    """
    if pattern.get("type") != "print_in_production":
        return False
    line = pattern.get("line")
    if not line:
        return False
    try:
        source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lines = source.splitlines()
    triple = '"""'
    open_count = sum(1 for ln in lines[: line - 1] if triple in ln)
    return open_count % 2 == 1  # inside an open docstring block


def diff_impact() -> dict[str, Any]:
    return _run_tool(["--change-impact"])


def route_summary() -> dict[str, Any]:
    return _run_tool(["--detect-routes", "--detect-routes-mode", "summary"])


def build_plan(items: list[WorkItem]) -> dict[str, Any]:
    return {
        "schema": "tree-sitter-analyzer/auto-review/v1",
        "generated_at_utc": _utc_now(),
        "project_root": str(ROOT),
        "summary": {
            "work_item_count": len(items),
            "highest_priority": items[0].priority if items else None,
            "weakest_dimension": items[0].weakest_dimension if items else None,
        },
        "work_items": [it.to_dict() for it in items],
        "diff_impact": diff_impact(),
        "routes": route_summary(),
        "next_action_hint": (
            "Hand the top work_item to a coder agent. Agent must: "
            "(1) run safety_command, (2) call refactor_command, "
            "(3) edit, (4) run every post_edit_commands entry, "
            "(5) only commit if grade improves AND pytest is green. "
            "NEVER use --no-verify or --dangerously-skip-permissions."
        ),
    }


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-items", type=int, default=10, help="how many backlog files to include"
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="write plan JSON to this file (default: stdout)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress human-readable summary on stderr",
    )
    args = parser.parse_args(argv)

    try:
        items = collect_backlog(args.max_items)
    except RuntimeError as exc:
        print(f"auto_review: {exc}", file=sys.stderr)
        return 2

    enrich_with_patterns(items)
    plan = build_plan(items)
    text = json.dumps(plan, indent=2, ensure_ascii=False)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)

    if not args.quiet:
        print(
            f"auto_review: {len(items)} work item(s); "
            f"top = {items[0].file_path if items else 'clean'} "
            f"(grade {items[0].grade if items else 'A'})",
            file=sys.stderr,
        )

    return 0 if not items else 1


if __name__ == "__main__":
    raise SystemExit(main())
