"""Anthropic agent loop for a single benchmark question against one arm.

Runs Claude with a restricted tool set, counts every tool call, and records
full token usage.  Writes:
  - results_dir/raw/<run_id>_prompt.txt   — the full system + user prompt
  - results_dir/raw/<run_id>_transcript.jsonl — every message in the loop
  - results_dir/runs.jsonl               — one JSONL line per trial
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import RunConfig

# ---------------------------------------------------------------------------
# Tool definitions available to each arm
# ---------------------------------------------------------------------------
# All file operations are sandboxed to repo_path — the runner enforces this.

_TOOL_READ_FILE: dict[str, Any] = {
    "name": "read_file",
    "description": (
        "Read a file from the repository. Path is relative to the repository root."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to repo root",
            },
            "start_line": {
                "type": "integer",
                "description": "First line to return (1-based, optional)",
            },
            "end_line": {
                "type": "integer",
                "description": "Last line to return (1-based, optional)",
            },
        },
        "required": ["path"],
    },
}

_TOOL_SEARCH_FILES: dict[str, Any] = {
    "name": "search_in_files",
    "description": (
        "Grep for a pattern across files in the repository. "
        "Returns matching lines with file paths and line numbers."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "directory": {
                "type": "string",
                "description": "Directory to search in (relative to repo root, default '.')",
                "default": ".",
            },
            "file_glob": {
                "type": "string",
                "description": "File name glob filter (e.g. '*.py', default '*')",
                "default": "*",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matching lines to return (default 50)",
                "default": 50,
            },
        },
        "required": ["pattern"],
    },
}

_TOOL_LIST_FILES: dict[str, Any] = {
    "name": "list_files",
    "description": "List files in a directory of the repository.",
    "input_schema": {
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Directory to list (relative to repo root, default '.')",
                "default": ".",
            },
            "pattern": {
                "type": "string",
                "description": "Glob pattern for file names (default '**/*')",
                "default": "**/*",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of entries to return (default 100)",
                "default": 100,
            },
        },
        "required": [],
    },
}

_TOOL_RUN_TSA: dict[str, Any] = {
    "name": "run_tsa",
    "description": (
        "Run tree-sitter-analyzer CLI in the repository. "
        "Example: run_tsa('smart-context', '--query URLRouter --format json'). "
        "Subcommands: smart-context, project-graph, call-graph, change-impact."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "subcommand": {
                "type": "string",
                "description": "TSA subcommand (e.g. 'smart-context', 'call-graph')",
            },
            "args": {
                "type": "string",
                "description": "Additional arguments as a string (e.g. '--query X --format json')",
                "default": "",
            },
        },
        "required": ["subcommand"],
    },
}

_TOOL_QUERY_CODEGRAPH: dict[str, Any] = {
    "name": "query_codegraph",
    "description": (
        "Query the CodeGraph symbol index for the repository. "
        "Operations: context, search, callers, callees, explore, node, files, impact."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": (
                    "One of: context, search, callers, callees, explore, node, files, impact"
                ),
            },
            "query": {
                "type": "string",
                "description": "Symbol name, file path, or free-form query",
                "default": "",
            },
            "extra": {
                "type": "string",
                "description": "Extra CLI flags as a string",
                "default": "",
            },
        },
        "required": ["operation"],
    },
}

# Map arm_id → list of tool defs to expose
_ARM_TOOLS: dict[str, list[dict[str, Any]]] = {
    "native-only": [_TOOL_READ_FILE, _TOOL_SEARCH_FILES, _TOOL_LIST_FILES],
    "tsa-warm": [_TOOL_READ_FILE, _TOOL_SEARCH_FILES, _TOOL_LIST_FILES, _TOOL_RUN_TSA],
    "tsa-cold": [_TOOL_READ_FILE, _TOOL_SEARCH_FILES, _TOOL_LIST_FILES, _TOOL_RUN_TSA],
    "codegraph-warm": [
        _TOOL_READ_FILE,
        _TOOL_SEARCH_FILES,
        _TOOL_LIST_FILES,
        _TOOL_QUERY_CODEGRAPH,
    ],
    "codegraph-cold": [
        _TOOL_READ_FILE,
        _TOOL_SEARCH_FILES,
        _TOOL_LIST_FILES,
        _TOOL_QUERY_CODEGRAPH,
    ],
}

# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

_MAX_OUTPUT_BYTES = 32_000  # cap individual tool output to avoid token explosion


def _safe_path(repo_path: Path, relative: str) -> Path | None:
    """Return resolved absolute path only if it stays inside repo_path."""
    try:
        resolved = (repo_path / relative.lstrip("/")).resolve()
        resolved.relative_to(repo_path.resolve())  # raises ValueError if outside
        return resolved
    except (ValueError, OSError):
        return None


def _execute_tool(name: str, inputs: dict[str, Any], repo_path: Path) -> str:
    """Dispatch a tool call and return its string output (capped)."""
    try:
        if name == "read_file":
            return _tool_read_file(inputs, repo_path)
        if name == "search_in_files":
            return _tool_search(inputs, repo_path)
        if name == "list_files":
            return _tool_list(inputs, repo_path)
        if name == "run_tsa":
            return _tool_run_tsa(inputs, repo_path)
        if name == "query_codegraph":
            return _tool_query_codegraph(inputs, repo_path)
    except Exception as exc:  # noqa: BLE001
        return f"ERROR executing {name}: {exc}"
    return f"Unknown tool: {name}"


def _tool_read_file(inputs: dict[str, Any], repo_path: Path) -> str:
    path = _safe_path(repo_path, inputs.get("path", ""))
    if path is None:
        return "ERROR: path is outside the repository root"
    if not path.exists():
        return f"ERROR: file not found: {inputs['path']}"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"ERROR: {e}"
    start = max(0, inputs.get("start_line", 1) - 1)
    end = inputs.get("end_line", len(lines))
    selected = lines[start:end]
    text = "\n".join(f"{start + i + 1}: {line}" for i, line in enumerate(selected))
    return text[:_MAX_OUTPUT_BYTES]


def _tool_search(inputs: dict[str, Any], repo_path: Path) -> str:
    pattern = inputs.get("pattern", "")
    directory = inputs.get("directory", ".")
    file_glob = inputs.get("file_glob", "*")
    max_results = int(inputs.get("max_results", 50))
    search_dir = _safe_path(repo_path, directory)
    if search_dir is None:
        return "ERROR: directory is outside the repository root"
    cmd = [
        "grep",
        "-rn",
        "--include",
        file_glob,
        "-m",
        str(max_results),
        pattern,
        str(search_dir),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    output = result.stdout or result.stderr or "(no matches)"
    return output[:_MAX_OUTPUT_BYTES]


def _tool_list(inputs: dict[str, Any], repo_path: Path) -> str:
    directory = inputs.get("directory", ".")
    pattern = inputs.get("pattern", "**/*")
    max_results = int(inputs.get("max_results", 100))
    base = _safe_path(repo_path, directory)
    if base is None:
        return "ERROR: directory is outside the repository root"
    if not base.is_dir():
        return f"ERROR: not a directory: {directory}"
    paths = []
    for p in base.glob(pattern):
        if p.is_file():
            try:
                paths.append(str(p.relative_to(repo_path)))
            except ValueError:
                pass
        if len(paths) >= max_results:
            break
    return "\n".join(sorted(paths)[:max_results]) or "(no files found)"


def _tool_run_tsa(inputs: dict[str, Any], repo_path: Path) -> str:
    subcommand = inputs.get("subcommand", "")
    args = inputs.get("args", "")
    cmd_str = f"python -m tree_sitter_analyzer {subcommand} {args}".strip()
    result = subprocess.run(  # nosec B602
        cmd_str,
        shell=True,  # noqa: S602 — intentional: TSA args are from LLM, not user shell
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(repo_path),
        timeout=60,
    )
    output = result.stdout or result.stderr or "(no output)"
    return output[:_MAX_OUTPUT_BYTES]


def _tool_query_codegraph(inputs: dict[str, Any], repo_path: Path) -> str:
    operation = inputs.get("operation", "")
    query = inputs.get("query", "")
    extra = inputs.get("extra", "")
    cmd_str = f"codegraph {operation} {query} {extra}".strip()
    result = subprocess.run(  # nosec B602
        cmd_str,
        shell=True,  # noqa: S602 — intentional: codegraph args are from LLM, not user shell
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(repo_path),
        timeout=60,
    )
    output = result.stdout or result.stderr or "(no output)"
    return output[:_MAX_OUTPUT_BYTES]


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


def _make_run_id(question_id: str, arm_id: str, repeat: int) -> str:
    return f"{question_id}__{arm_id}__{repeat:02d}"


def _extract_text(content: list[Any]) -> str:
    """Pull plain text from a list of content blocks."""
    return " ".join(block.text for block in content if hasattr(block, "text")).strip()


def _extract_citations(answer: str) -> list[str]:
    """Extract file-path-like strings from the answer text."""
    import re

    return list(
        dict.fromkeys(  # deduplicate preserving order
            m.group(0)
            for m in re.finditer(
                r"[\w./\-]+\.(?:py|ts|tsx|go|rs|java|swift|kt|js|jsx|cpp|c|h|cs|rb|php)",
                answer,
            )
        )
    )


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

_MAX_TURNS = 40  # hard ceiling on agent loop iterations


def _run_agent_loop(
    system_prompt: str,
    user_message: str,
    tools: list[dict[str, Any]],
    repo_path: Path,
    arm_id: str,
    model: str,
    timeout_seconds: int,
    transcript: list[dict[str, Any]],
) -> tuple[str, int, int, int, int, int, int, str | None]:
    """Run the agent tool-use loop.

    Returns
    -------
    answer, input_tokens, output_tokens, tool_calls,
    file_reads, search_calls, index_queries, error
    """
    try:
        import anthropic  # lazy import — only needed for real runs
    except ImportError as exc:
        raise RuntimeError(
            "anthropic package not installed. Run: uv pip install anthropic"
        ) from exc

    client = anthropic.Anthropic()
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    input_tokens = 0
    output_tokens = 0
    tool_calls = 0
    file_reads = 0
    search_calls = 0
    index_queries = 0
    answer = ""
    error = None
    deadline = time.perf_counter() + timeout_seconds

    for _turn in range(_MAX_TURNS):
        if time.perf_counter() > deadline:
            answer = "TIMEOUT"
            error = f"Timed out after {timeout_seconds}s"
            break

        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001
            error = f"API error: {exc}"
            answer = "ERROR"
            break

        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens

        # Record assistant message in transcript
        transcript.append(
            {
                "role": "assistant",
                "stop_reason": response.stop_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
                "content": [
                    {
                        "type": getattr(b, "type", "unknown"),
                        "text": getattr(b, "text", None),
                        "name": getattr(b, "name", None),
                        "id": getattr(b, "id", None),
                        "input": getattr(b, "input", None),
                    }
                    for b in response.content
                ],
            }
        )

        if response.stop_reason == "end_turn":
            answer = _extract_text(response.content)
            break

        if response.stop_reason != "tool_use":
            answer = _extract_text(response.content)
            error = f"Unexpected stop_reason: {response.stop_reason}"
            break

        # Execute tools
        tool_results = []
        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if not hasattr(block, "type") or block.type != "tool_use":
                continue

            tool_calls += 1
            tname = block.name
            tinputs = block.input or {}

            # categorise
            if tname == "read_file":
                file_reads += 1
            elif tname == "search_in_files":
                search_calls += 1
            elif tname in ("run_tsa", "query_codegraph"):
                index_queries += 1

            result_text = _execute_tool(tname, tinputs, repo_path)

            # Record tool result in transcript
            transcript.append(
                {
                    "role": "tool",
                    "tool_name": tname,
                    "tool_use_id": block.id,
                    "inputs": tinputs,
                    "result_snippet": result_text[:500],
                }
            )

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    else:
        answer = answer or "MAX_TURNS_REACHED"
        error = error or f"Reached {_MAX_TURNS}-turn limit without end_turn"

    return (
        answer,
        input_tokens,
        output_tokens,
        tool_calls,
        file_reads,
        search_calls,
        index_queries,
        error,
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
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Run one benchmark trial.

    Writes:
      results_dir/raw/<run_id>_prompt.txt
      results_dir/raw/<run_id>_transcript.jsonl
      results_dir/runs.jsonl  (appended)

    Returns a dict matching RunRecord schema.
    """
    run_id = _make_run_id(question_id, arm_id, repeat)
    started_at = datetime.now(timezone.utc).isoformat()
    started_perf = time.perf_counter()

    # Build prompt
    user_message_parts = []
    if run_config.extra_context:
        user_message_parts.append(run_config.extra_context)
    user_message_parts.append(f"Question: {question_prompt}")
    user_message = "\n\n".join(user_message_parts)

    # Persist prompt for reproducibility
    raw_dir = results_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = raw_dir / f"{run_id}_prompt.txt"
    prompt_path.write_text(
        f"SYSTEM:\n{run_config.system_prompt}\n\nUSER:\n{user_message}",
        encoding="utf-8",
    )

    # Get tools for this arm
    tools = _ARM_TOOLS.get(arm_id, _ARM_TOOLS["native-only"])

    # Run agent loop
    transcript: list[dict[str, Any]] = []
    (
        answer,
        input_tokens,
        output_tokens,
        tool_calls,
        file_reads,
        search_calls,
        index_queries,
        error,
    ) = _run_agent_loop(
        system_prompt=run_config.system_prompt,
        user_message=user_message,
        tools=tools,
        repo_path=repo_path,
        arm_id=arm_id,
        model=model,
        timeout_seconds=timeout_seconds,
        transcript=transcript,
    )

    ended_at = datetime.now(timezone.utc).isoformat()
    elapsed_seconds = round(time.perf_counter() - started_perf, 4)
    total_tokens = input_tokens + output_tokens
    estimated_cost = (input_tokens / 1_000_000 * 3.0) + (
        output_tokens / 1_000_000 * 15.0
    )

    # Persist transcript
    transcript_path = raw_dir / f"{run_id}_transcript.jsonl"
    with transcript_path.open("w", encoding="utf-8") as fh:
        for entry in transcript:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    record: dict = {
        "run_id": run_id,
        "repo": str(repo_path.name),
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
        "transcript_path": str(transcript_path),
        "error": error,
    }

    # Append to JSONL
    runs_jsonl = results_dir / "runs.jsonl"
    with runs_jsonl.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    return record
