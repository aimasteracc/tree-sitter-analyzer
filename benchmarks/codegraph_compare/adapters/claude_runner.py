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
import os
import re
import subprocess
import tempfile
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
    "mcp__tree-sitter-analyzer__nav",
    "mcp__tree-sitter-analyzer__search",
    "mcp__tree-sitter-analyzer__structure",
    "mcp__tree-sitter-analyzer__health",
    "mcp__tree-sitter-analyzer__index",
    "mcp__tree-sitter-analyzer__project",
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
    # Symmetric with the codegraph arm: allow base file tools + TSA MCP, block
    # only the OTHER tool's MCP + ToolSearch/Agent. (Previously this arm was CLI
    # and force-blocked Read/grep, which was both asymmetric vs codegraph and
    # measured the CLI — not the MCP — surface.)
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
            elif (
                "codegraph" in name_lower
                or "tree_sitter" in name_lower
                or "tree-sitter" in name_lower  # TSA MCP: mcp__tree-sitter-analyzer__*
            ):
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

    def _is_reconnect_error(message: Any) -> bool:
        return str(message or "").startswith("Reconnecting...")

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")
        item = event.get("item", {})
        if isinstance(item, dict) and item.get("type") == "agent_message":
            answer = item.get("text", "")
        elif event_type == "item.completed":
            if item.get("type") == "agent_message":
                answer = item.get("text", "")
            elif item.get("type") == "error":
                error = item.get("message") or json.dumps(item)
        elif event_type == "turn.completed":
            usage = event.get("usage", {})
        elif event_type == "agent_message":
            answer = str(
                (item.get("text") if isinstance(item, dict) else event.get("text", ""))
                or ""
            )
        elif event_type in {"turn.failed", "error"}:
            if error is None or not _is_reconnect_error(error):
                error = event.get("message") or event.get("error") or json.dumps(event)
        elif (
            event_type == "item.started"
            and isinstance(item, dict)
            and item.get("type") == "agent_message"
        ):
            answer = item.get("text", "")

    if answer and error and _is_reconnect_error(error):
        error = None

    if not answer and not error:
        error = "No Codex agent_message event found in stream output"
    return answer, usage, error


def _parse_claude_result_from_stream(
    stream_lines: list[str],
) -> tuple[str, str | None, dict[str, Any]]:
    """Extract answer, error, and raw_result from a claude stream-json output."""
    answer = ""
    error: str | None = None
    raw_result: dict[str, Any] = {}
    for line in reversed(stream_lines):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "result":
            continue
        raw_result = event
        if event.get("is_error"):
            error = event.get("result", "unknown error")
            answer = "ERROR"
        else:
            answer = event.get("result", "")
        break
    if not answer and not error:
        error = "No result event found in stream output"
    return answer, error, raw_result


_ANALYZER_ROOT = Path(__file__).resolve().parents[3]
_MCP_CONFIG_DIR = Path(tempfile.gettempdir()) / "tsa_bench_mcp_configs"


def _write_arm_mcp_config(arm_id: str) -> Path:
    """Write a per-arm MCP config so each arm sees ONLY its own MCP server.

    Used with ``--strict-mcp-config`` so the developer's global MCP servers
    (Context7, Gmail, codegraph, ruflo, vercel, ...) do NOT leak into the
    benchmark agent — their tool definitions otherwise bloat the context by
    millions of tokens and pollute every arm. native-only gets an empty set.
    """
    if arm_id.startswith("tsa"):
        servers = {
            "tree-sitter-analyzer": {
                "command": str(_ANALYZER_ROOT / ".venv" / "bin" / "python"),
                "args": ["-m", "tree_sitter_analyzer.mcp.server"],
            }
        }
    elif arm_id.startswith("codegraph"):
        servers = {"codegraph": {"command": "codegraph", "args": ["serve", "--mcp"]}}
    else:
        servers = {}  # native-only: no MCP at all
    _MCP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = _MCP_CONFIG_DIR / f"{arm_id}.json"
    path.write_text(json.dumps({"mcpServers": servers}))
    return path


def _build_agent_cmd(
    arm_id: str,
    model: str,
    repo_path: Path,
    run_config: RunConfig,
    allowed_tools_str: str,
    disallowed_tools_str: str,
    agent_backend: str,
) -> list[str]:
    """Build the CLI command list for the given agent backend."""
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
        # Isolate MCP: each arm sees only its own server (no global MCP leak).
        mcp_cfg = _write_arm_mcp_config(arm_id)
        cmd += ["--strict-mcp-config", "--mcp-config", str(mcp_cfg)]
        return cmd
    # codex backend: the MCP arms (tsa*, codegraph*) need their server wired in
    # with the SAME per-arm isolation the claude branch gets via
    # --strict-mcp-config. `codex exec` has no equivalent strict flag here, so
    # it would either miss the server entirely or silently inherit the
    # developer's global ~/.codex MCP config — both invalidate the
    # TSA-vs-CodeGraph comparison. Fail loudly rather than emit wrong numbers
    # (Codex P2 on #290). Use --agent-backend claude for MCP arms until codex
    # MCP wiring (codex -c mcp_servers.*) is implemented and verified.
    if arm_id.startswith(("tsa", "codegraph")):
        raise NotImplementedError(
            f"Per-arm MCP isolation is not wired for the codex backend, but arm "
            f"{arm_id!r} requires its own MCP server. Running `codex exec` here "
            f"would miss the server or inherit the global ~/.codex MCP config, "
            f"invalidating the comparison. Use --agent-backend claude for MCP "
            f"arms, or wire `codex -c mcp_servers.*` before enabling this path."
        )
    sandbox = _codex_sandbox_for_arm(arm_id)
    return [
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
    cmd = _build_agent_cmd(
        arm_id,
        model,
        repo_path,
        run_config,
        allowed_tools_str,
        disallowed_tools_str,
        agent_backend,
    )

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
                # Extend the MCP startup window. A python MCP server spawns in
                # ~300-400ms (python + mcp lib import), which is at the edge of
                # claude's default connect window → load-dependent "pending"
                # (TSA arm then falls back to Read). 30s removes the race so the
                # MCP arm is measured fairly. Verified: 3/3 stable connects.
                env={
                    **os.environ,
                    "MCP_TIMEOUT": "30000",
                    "MCP_TOOL_TIMEOUT": "30000",
                },
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
                answer, error, raw_result = _parse_claude_result_from_stream(
                    stream_lines
                )

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
