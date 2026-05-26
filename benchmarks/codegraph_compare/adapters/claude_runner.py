"""Benchmark runner that drives Claude CLI or Codex CLI for each trial.

No separate API key required — uses the current Claude Code session's
authentication (keychain / OAuth).

Writes:
  - results_dir/raw/<run_id>_prompt.txt          — the full prompt sent to the agent
  - results_dir/raw/<run_id>_result.jsonl        — raw JSONL response from the agent CLI
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
    "Bash(codegraph *)",
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
    "Bash(uv run --project * python -m tree_sitter_analyzer *)",
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
        "Bash(codegraph *)",
        "mcp__codegraph__*",
        "mcp__ruflo__*",
        "mcp__*",
        "ToolSearch",
        "Agent",
    ],
    "tsa-warm": ["Bash(codegraph *)", "mcp__codegraph__*", "ToolSearch", "Agent"],
    "tsa-cold": ["Bash(codegraph *)", "mcp__codegraph__*", "ToolSearch", "Agent"],
    "codegraph-warm": ["ToolSearch", "Agent"],
    "codegraph-cold": ["ToolSearch", "Agent"],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEFAULT_MODELS = {
    "claude": "claude-sonnet-4-6",
    "codex": "gpt-5.2",
}


def _make_run_id(question_id: str, arm_id: str, repeat: int, agent_backend: str) -> str:
    return f"{question_id}__{arm_id}__{agent_backend}__{repeat:02d}"


def _extract_citations(text: str, repo_path: Path) -> list[str]:
    """Extract answer citations that correspond to real files in repo_path."""
    citations: list[str] = []
    seen: set[str] = set()

    for match in re.finditer(
        r"[\w./\-]+\."
        r"(?:py|ts|tsx|go|rs|java|swift|kt|js|jsx|cpp|c|h|cs|rb|php)",
        text,
    ):
        candidate = match.group(0).lstrip("./")
        if candidate in seen:
            continue
        path = Path(candidate)
        if path.is_absolute():
            exists = path.is_file()
        else:
            exists = (repo_path / candidate).is_file()
        if exists:
            citations.append(candidate)
            seen.add(candidate)

    return citations


def _codex_sandbox_for_arm(arm_id: str) -> str:
    """Return the least-permissive Codex sandbox that still lets indexes query."""
    if arm_id == "native-only":
        return "read-only"
    return "workspace-write"


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


def _looks_like_shell_read(command: str) -> bool:
    return bool(re.search(r"\b(cat|head|tail|nl)\b|\bsed\s+-n\b", command))


def _looks_like_shell_search(command: str) -> bool:
    return bool(re.search(r"\b(rg|grep|find|fd|ls)\b", command))


def _looks_like_index_query(command: str) -> bool:
    return "tree_sitter_analyzer" in command or "codegraph" in command.lower()


def _parse_codex_tool_calls_from_stream(lines: list[str]) -> tuple[int, int, int, int]:
    """Count Codex CLI command_execution events by benchmark category."""
    tool_calls = 0
    file_reads = 0
    search_calls = 0
    index_queries = 0

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "item.completed":
            continue

        item = event.get("item", {})
        if item.get("type") != "command_execution":
            continue

        tool_calls += 1
        command = str(item.get("command") or "")
        if _looks_like_index_query(command):
            index_queries += 1
        elif _looks_like_shell_read(command):
            file_reads += 1
        elif _looks_like_shell_search(command):
            search_calls += 1
        else:
            search_calls += 1

    return tool_calls, file_reads, search_calls, index_queries


def _parse_codex_stream(lines: list[str]) -> tuple[str, dict[str, Any], str | None]:
    answer = ""
    usage: dict[str, Any] = {}
    error: str | None = None

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")
        if event_type == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                answer = item.get("text", "")
            elif item.get("type") == "error":
                error = item.get("message") or json.dumps(item)
        elif event_type == "turn.completed":
            usage = event.get("usage", {})
        elif event_type in {"turn.failed", "error"}:
            error = event.get("message") or event.get("error") or json.dumps(event)

    if not answer and not error:
        error = "No Codex agent_message event found in stream output"
    return answer, usage, error


def _usage_int(usage: dict[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    return int(value or 0)


def _extract_usage_metrics(
    usage: dict[str, Any], agent_backend: str
) -> tuple[int, int, int, int, int]:
    """Return input, cached input, output, reasoning output, total tokens.

    Claude and Codex expose cache details differently. Claude reports cache read
    and creation tokens outside input_tokens; Codex reports cached/reasoning
    counters as detail fields that are already included in input/output totals.
    """
    input_tokens = _usage_int(usage, "input_tokens")
    output_tokens = _usage_int(usage, "output_tokens")
    cached_input_tokens = (
        _usage_int(usage, "cached_input_tokens")
        + _usage_int(usage, "cache_read_input_tokens")
        + _usage_int(usage, "cache_creation_input_tokens")
    )
    reasoning_output_tokens = _usage_int(usage, "reasoning_output_tokens")

    if agent_backend == "claude":
        total_tokens = input_tokens + cached_input_tokens + output_tokens
    else:
        total_tokens = input_tokens + output_tokens

    return (
        input_tokens,
        cached_input_tokens,
        output_tokens,
        reasoning_output_tokens,
        total_tokens,
    )


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
    model: str | None = None,
    agent_backend: str = "claude",
    dry_run: bool = False,
) -> dict:
    """Run one benchmark trial via the configured agent CLI.

    Writes prompt + raw result to results_dir/raw/, appends to runs.jsonl.
    """
    if agent_backend not in {"claude", "codex"}:
        raise ValueError("agent_backend must be one of: claude, codex")
    model = model or _DEFAULT_MODELS[agent_backend]
    run_id = _make_run_id(question_id, arm_id, repeat, agent_backend)
    started_at = datetime.now(timezone.utc).isoformat()
    started_perf = time.perf_counter()

    allowed_tools_str = ",".join(
        _ARM_ALLOWED_TOOLS.get(arm_id, _ARM_ALLOWED_TOOLS["native-only"])
    )
    disallowed_tools_str = ",".join(_ARM_DISALLOWED_TOOLS.get(arm_id, []))

    # Build the prompt the agent will receive
    user_parts = []
    if run_config.extra_context:
        user_parts.append(run_config.extra_context)
    user_parts.append(f"Question: {question_prompt}")
    user_message = "\n\n".join(user_parts)
    if agent_backend == "codex":
        sandbox = _codex_sandbox_for_arm(arm_id)
        tool_policy = (
            f"Benchmark arm: {arm_id}.\n"
            f"Codex sandbox: {sandbox}.\n"
            f"Allowed tool policy: {allowed_tools_str}.\n"
            f"Disallowed tool policy: {disallowed_tools_str or 'none'}.\n"
            "Respect this policy strictly when using tools. Do not edit source "
            "files or project configuration. For indexed arms, the only allowed "
            "writes are tool-maintained cache/database side effects such as "
            ".codegraph SQLite WAL files or .ast-cache metadata. "
            "Answer the architecture question with concrete file citations."
        )
        user_message = f"{tool_policy}\n\n{user_message}"

    full_prompt = f"{run_config.system_prompt}\n\n{user_message}"

    # Persist prompt
    raw_dir = results_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = raw_dir / f"{run_id}_prompt.txt"
    prompt_path.write_text(full_prompt, encoding="utf-8")

    # Build agent CLI command. Claude has stronger tool allowlisting; Codex
    # gets the same restrictions as explicit prompt text because codex exec
    # currently exposes sandbox controls rather than per-tool allowlists.
    if agent_backend == "claude":
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
    else:
        sandbox = _codex_sandbox_for_arm(arm_id)
        cmd = [
            "codex",
            "--ask-for-approval",
            "never",
            "exec",
            "--json",
            "--ephemeral",
            "--sandbox",
            sandbox,
            "--model",
            model,
            "-C",
            str(repo_path),
            "-",
        ]

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
                error = (
                    f"{agent_backend} CLI exited {proc.returncode}: {proc.stderr[:500]}"
                )
            elif agent_backend == "claude":
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
            error = f"{agent_backend} CLI not found in PATH"
            answer = "ERROR"

        if agent_backend == "codex" and not dry_run:
            answer, codex_usage, codex_error = _parse_codex_stream(stream_lines)
            if codex_error:
                error = codex_error
                answer = answer or "ERROR"
            raw_result = {"usage": codex_usage}

    ended_at = datetime.now(timezone.utc).isoformat()
    elapsed_seconds = round(time.perf_counter() - started_perf, 4)

    # Extract metrics from result event
    usage = raw_result.get("usage", {})
    (
        input_tokens,
        cached_input_tokens,
        output_tokens,
        reasoning_output_tokens,
        total_tokens,
    ) = _extract_usage_metrics(usage, agent_backend)
    estimated_cost = float(raw_result.get("total_cost_usd", 0.0))
    if estimated_cost == 0 and input_tokens + output_tokens > 0:
        estimated_cost = (input_tokens / 1_000_000 * 3.0) + (
            output_tokens / 1_000_000 * 15.0
        )

    # Count tool calls from agent stream events. Claude exposes tool_use blocks;
    # Codex exposes completed shell command events.
    tool_parser = (
        _parse_codex_tool_calls_from_stream
        if agent_backend == "codex"
        else _parse_tool_calls_from_stream
    )
    tool_calls, file_reads, search_calls, index_queries = tool_parser(stream_lines)

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
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost, 6),
        "tool_calls": tool_calls,
        "file_reads": file_reads,
        "search_calls": search_calls,
        "index_queries": index_queries,
        "answer": answer,
        "citations": _extract_citations(answer, repo_path),
        "transcript_path": str(raw_dir / f"{run_id}_result.jsonl"),
        "error": error,
        "agent_backend": agent_backend,
        "model": model,
    }

    runs_jsonl = results_dir / "runs.jsonl"
    with runs_jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record
