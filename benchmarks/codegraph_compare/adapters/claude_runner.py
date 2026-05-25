"""Benchmark runner that drives the `claude --print` CLI for each trial.

No separate API key required — uses the current Claude Code session's
authentication (keychain / OAuth).

Writes:
  - results_dir/raw/<run_id>_prompt.txt          — the full prompt sent to claude
  - results_dir/raw/<run_id>_result.json         — raw JSON response from claude CLI
  - results_dir/runs.jsonl                       — one JSONL line per trial (appended)
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import RunConfig

# ---------------------------------------------------------------------------
# Tool allowlist per arm
# ---------------------------------------------------------------------------
# These are passed to `claude --allowed-tools` so Claude can only use the
# tools appropriate for each arm, keeping the comparison fair.

_BASE_TOOLS = ["Read", "Bash(grep *)", "Bash(find *)", "Bash(ls *)", "Glob", "Grep"]
_CODEGRAPH_TOOLS = [
    "mcp__codegraph__codegraph_context",
    "mcp__codegraph__codegraph_search",
    "mcp__codegraph__codegraph_callers",
    "mcp__codegraph__codegraph_callees",
    "mcp__codegraph__codegraph_explore",
    "mcp__codegraph__codegraph_node",
    "mcp__codegraph__codegraph_files",
    "mcp__codegraph__codegraph_impact",
]
_TSA_TOOLS = [
    "Bash(python -m tree_sitter_analyzer *)",
    "Bash(uv run python -m tree_sitter_analyzer *)",
]

# Tools explicitly blocked per arm (prevents Claude from discovering and using them via ToolSearch)
_ARM_ALLOWED_TOOLS: dict[str, list[str]] = {
    "native-only": _BASE_TOOLS,
    "tsa-warm": _BASE_TOOLS + _TSA_TOOLS,
    "tsa-cold": _BASE_TOOLS + _TSA_TOOLS,
    "codegraph-warm": _BASE_TOOLS + _CODEGRAPH_TOOLS,
    "codegraph-cold": _BASE_TOOLS + _CODEGRAPH_TOOLS,
}

# For native-only: explicitly disallow codegraph MCP and ToolSearch so Claude
# can't discover and call them even when --allowed-tools is set
_ARM_DISALLOWED_TOOLS: dict[str, list[str]] = {
    "native-only": [
        "mcp__codegraph__*",
        "mcp__ruflo__*",
        "mcp__*",
        "ToolSearch",
        "Agent",
    ],
    "tsa-warm": ["mcp__codegraph__*", "ToolSearch", "Agent"],
    "tsa-cold": ["mcp__codegraph__*", "ToolSearch", "Agent"],
    "codegraph-warm": ["ToolSearch", "Agent"],
    "codegraph-cold": ["ToolSearch", "Agent"],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_run_id(question_id: str, arm_id: str, repeat: int) -> str:
    return f"{question_id}__{arm_id}__{repeat:02d}"


def _extract_citations(text: str) -> list[str]:
    """Extract file-path-like strings from the answer text."""
    return list(
        dict.fromkeys(
            m.group(0)
            for m in re.finditer(
                r"[\w./\-]+\."
                r"(?:py|ts|tsx|go|rs|java|swift|kt|js|jsx|cpp|c|h|cs|rb|php)",
                text,
            )
        )
    )


def _parse_tool_calls_from_stream(lines: list[str]) -> tuple[int, int, int, int]:
    """Count tool calls by category from stream-json event lines."""
    tool_calls = 0
    file_reads = 0
    search_calls = 0
    index_queries = 0
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []):
            if block.get("type") != "tool_use":
                continue
            tool_calls += 1
            name: str = block.get("name", "")
            name_lower = name.lower()
            if name_lower in ("read", "readfile"):
                file_reads += 1
            elif "codegraph" in name_lower or "tree_sitter" in name_lower:
                index_queries += 1
            elif name_lower == "bash":
                inp = block.get("input", {})
                cmd_str = inp.get("command", "") if isinstance(inp, dict) else str(inp)
                if (
                    "tree_sitter_analyzer" in cmd_str
                    or "python -m tree_sitter" in cmd_str
                ):
                    index_queries += 1
                elif "grep" in cmd_str or "find" in cmd_str or "rg " in cmd_str:
                    search_calls += 1
                else:
                    search_calls += 1
            else:
                search_calls += 1
    return tool_calls, file_reads, search_calls, index_queries


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_one(
    question_id: str,
    question_prompt: str,
    arm_id: str,
    repo_path: Path,
    repeat: int,
    run_config: RunConfig,
    results_dir: Path,
    timeout_seconds: int = 1200,
    model: str = "claude-sonnet-4-6",
    dry_run: bool = False,
) -> dict:
    """Run one benchmark trial via `claude --print --output-format json`.

    Writes prompt + raw result to results_dir/raw/, appends to runs.jsonl.
    """
    run_id = _make_run_id(question_id, arm_id, repeat)
    started_at = datetime.now(timezone.utc).isoformat()
    started_perf = time.perf_counter()

    # Build the prompt Claude will receive
    user_parts = []
    if run_config.extra_context:
        user_parts.append(run_config.extra_context)
    user_parts.append(f"Question: {question_prompt}")
    user_message = "\n\n".join(user_parts)

    full_prompt = f"{run_config.system_prompt}\n\n{user_message}"

    # Persist prompt
    raw_dir = results_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = raw_dir / f"{run_id}_prompt.txt"
    prompt_path.write_text(full_prompt, encoding="utf-8")

    # Build claude CLI command — stream-json captures per-tool-call events
    allowed_tools_str = ",".join(
        _ARM_ALLOWED_TOOLS.get(arm_id, _ARM_ALLOWED_TOOLS["native-only"])
    )
    disallowed_tools_str = ",".join(_ARM_DISALLOWED_TOOLS.get(arm_id, []))
    cmd = [
        "claude",
        "--print",
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--model",
        model,
        "--add-dir",
        str(repo_path),
        "--append-system-prompt",
        run_config.system_prompt,
        "--allowed-tools",
        allowed_tools_str,
    ]
    if disallowed_tools_str:
        cmd += ["--disallowed-tools", disallowed_tools_str]

    # Run — prompt via stdin
    error: str | None = None
    answer = ""
    raw_result: dict[str, Any] = {}
    stream_lines: list[str] = []

    if dry_run:
        result_path = raw_dir / f"{run_id}_result.jsonl"
        answer = "DRY_RUN"
        result_path.write_text("", encoding="utf-8")
    else:
        try:
            proc = subprocess.run(
                cmd,
                input=user_message,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                cwd=str(repo_path),
            )
            stream_lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]

            # Save raw stream
            result_path = raw_dir / f"{run_id}_result.jsonl"
            result_path.write_text(proc.stdout, encoding="utf-8")

            if proc.returncode != 0 and not proc.stdout.strip():
                error = f"claude CLI exited {proc.returncode}: {proc.stderr[:500]}"
            else:
                # Extract result event (last line is usually the result)
                for line in reversed(stream_lines):
                    try:
                        event = json.loads(line)
                        if event.get("type") == "result":
                            raw_result = event
                            if event.get("is_error"):
                                error = event.get("result", "unknown error")
                                answer = "ERROR"
                            else:
                                answer = event.get("result", "")
                            break
                    except json.JSONDecodeError:
                        continue
                if not answer and not error:
                    error = "No result event found in stream output"

        except subprocess.TimeoutExpired:
            error = f"Timed out after {timeout_seconds}s"
            answer = "TIMEOUT"
        except FileNotFoundError:
            error = "claude CLI not found in PATH"
            answer = "ERROR"

    ended_at = datetime.now(timezone.utc).isoformat()
    elapsed_seconds = round(time.perf_counter() - started_perf, 4)

    # Extract metrics from result event
    usage = raw_result.get("usage", {})
    input_tokens = usage.get("input_tokens", 0) + usage.get(
        "cache_read_input_tokens", 0
    )
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = input_tokens + output_tokens
    estimated_cost = float(raw_result.get("total_cost_usd", 0.0))
    if estimated_cost == 0 and total_tokens > 0:
        estimated_cost = (input_tokens / 1_000_000 * 3.0) + (
            output_tokens / 1_000_000 * 15.0
        )

    # Count tool calls from assistant events in the stream
    tool_calls, file_reads, search_calls, index_queries = _parse_tool_calls_from_stream(
        stream_lines
    )

    record: dict = {
        "run_id": run_id,
        "repo": repo_path.name,
        "question_id": question_id,
        "arm": arm_id,
        "repeat": repeat,
        "started_at": started_at,
        "ended_at": ended_at,
        "elapsed_seconds": elapsed_seconds,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost, 6),
        "tool_calls": tool_calls,
        "file_reads": file_reads,
        "search_calls": search_calls,
        "index_queries": index_queries,
        "answer": answer,
        "citations": _extract_citations(answer),
        "transcript_path": str(raw_dir / f"{run_id}_result.jsonl"),
        "error": error,
    }

    runs_jsonl = results_dir / "runs.jsonl"
    with runs_jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record
