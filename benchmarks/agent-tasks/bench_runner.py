"""Agent-task bench runner.

Runs (repo × scenario × tool) combinations and emits one JSONL row per case.
Each row matches the schema declared in ``benchmarks/agent-tasks/README.md``::

    {
      "repo": "vscode",
      "task": "cold-start",
      "tool": "tsa",
      "tool_calls": 1,
      "tokens_in": 850,
      "tokens_out": 1100,
      "wall_clock_s": 0.42,
      "verdict": "INFO",
      "agent_decidable": true
    }

Wall-clock uses :func:`time.perf_counter` for monotonic precision. Tokens are
estimated via ``len(text) // 4`` (CodeGraph's own bench docs use the same
heuristic — see scenarios.py for rationale).

Created: 2026-05-22 r37fE
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

# Make sibling modules importable when invoked via ``uv run python`` without
# installation. The benchmarks dir is intentionally outside ``tree_sitter_analyzer``
# so it never ships with the wheel.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from scenarios import (  # noqa: E402  — sys.path mutation above
    SCENARIOS,
    estimate_tokens,
    list_scenarios,
)

# ---------------------------------------------------------------------------
# Schema — the README documents these as the contract; keep in sync.
# ---------------------------------------------------------------------------

REQUIRED_FIELDS: tuple[str, ...] = (
    "repo",
    "task",
    "tool",
    "tool_calls",
    "tokens_in",
    "tokens_out",
    "wall_clock_s",
    "verdict",
    "agent_decidable",
)


# ---------------------------------------------------------------------------
# Core measurement
# ---------------------------------------------------------------------------


def _extract_verdict(result: dict[str, Any]) -> str:
    """Pull the verdict from a tool result, mirroring base_tool's vocabulary.

    Tools mirror verdict between top-level and ``agent_summary`` — we accept
    either. Falls back to ``"INFO"`` if nothing is set so the row is always
    schema-complete.
    """
    verdict = result.get("verdict")
    if isinstance(verdict, str) and verdict:
        return verdict
    agent_summary = result.get("agent_summary")
    if isinstance(agent_summary, dict):
        v = agent_summary.get("verdict")
        if isinstance(v, str) and v:
            return v
    return "INFO"


def _build_input_blob(task: str, repo: str, kwargs: dict[str, Any]) -> str:
    """Synthesize the prompt the agent would have to send.

    For tokens_in we count what the *agent* paid to invoke the tool — task
    description + arguments. This is the apples-to-apples number against
    CodeGraph (their bench counts the same thing).
    """
    parts = [task, f"repo={repo}"]
    for k, v in sorted(kwargs.items()):
        if v is None:
            continue
        parts.append(f"{k}={v}")
    return " ".join(parts)


def _build_output_blob(result: dict[str, Any]) -> str:
    """Render the tool/baseline result for tokens_out estimation.

    JSON is cheap and predictable; using ``json.dumps`` keeps token counts
    stable across runs even if dict iteration order changes.
    """
    try:
        return json.dumps(result, default=repr, ensure_ascii=False)
    except (TypeError, ValueError):
        # Fall back to repr — should not happen with our tools but the
        # bench must not abort on a weird result.
        return repr(result)


def run_case(
    repo: str,
    task: str,
    tool: str,
    **scenario_kwargs: Any,
) -> dict[str, Any]:
    """Run one (repo, task, tool) case and return a JSONL-ready row.

    On exception the row is still schema-complete: ``verdict="ERROR"``,
    ``agent_decidable=False``, ``error`` field appended (not in the schema
    but useful for triage). Callers can filter by verdict.
    """
    if task not in SCENARIOS:
        raise ValueError(f"Unknown task '{task}'. Known: {', '.join(list_scenarios())}")
    if tool not in ("baseline", "tsa"):
        raise ValueError(f"tool must be 'baseline' or 'tsa', got '{tool}'")

    scenario = SCENARIOS[task]
    fn = scenario[tool]

    input_blob = _build_input_blob(task, repo, scenario_kwargs)
    tokens_in = estimate_tokens(input_blob)

    started = time.perf_counter()
    try:
        outcome = fn(repo, **scenario_kwargs)
        wall_clock_s = time.perf_counter() - started
    except Exception as exc:  # noqa: BLE001 — bench must never crash a matrix
        wall_clock_s = time.perf_counter() - started
        return _error_row(
            repo=repo,
            task=task,
            tool=tool,
            wall_clock_s=wall_clock_s,
            tokens_in=tokens_in,
            error=f"{type(exc).__name__}: {exc}",
            traceback_str=traceback.format_exc(limit=3),
        )

    result = outcome.get("result", {})
    output_blob = _build_output_blob(result)
    tokens_out = estimate_tokens(output_blob)

    row = {
        "repo": repo,
        "task": task,
        "tool": tool,
        "tool_calls": int(outcome.get("tool_calls", 0)),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "wall_clock_s": round(wall_clock_s, 4),
        "verdict": _extract_verdict(result) if isinstance(result, dict) else "INFO",
        "agent_decidable": bool(outcome.get("agent_decidable", False)),
    }
    _assert_schema(row)
    return row


def _error_row(
    *,
    repo: str,
    task: str,
    tool: str,
    wall_clock_s: float,
    tokens_in: int,
    error: str,
    traceback_str: str,
) -> dict[str, Any]:
    """Build a schema-complete row for a failed case.

    Why we don't re-raise: a bench harness that aborts on the first repo
    failure is useless for multi-repo matrices. We emit a row tagged with
    verdict=ERROR and continue. The traceback is preserved so triage is
    one ``jq '.error_traceback'`` away.
    """
    row = {
        "repo": repo,
        "task": task,
        "tool": tool,
        "tool_calls": 0,
        "tokens_in": tokens_in,
        "tokens_out": 0,
        "wall_clock_s": round(wall_clock_s, 4),
        "verdict": "ERROR",
        "agent_decidable": False,
        "error": error,
        "error_traceback": traceback_str,
    }
    _assert_schema(row)
    return row


def _assert_schema(row: dict[str, Any]) -> None:
    """Verify a row carries every REQUIRED_FIELDS entry.

    Fails loudly — the bench is supposed to *measure* the contract, so a
    drifting schema is itself a failure worth surfacing.
    """
    missing = [f for f in REQUIRED_FIELDS if f not in row]
    if missing:
        raise RuntimeError(f"row missing required fields: {missing} (row={row})")


# ---------------------------------------------------------------------------
# Multi-case orchestration
# ---------------------------------------------------------------------------


def run_matrix(
    repos: list[str],
    tasks: list[str],
    tools: list[str],
    scenario_kwargs: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Run the full (repos × tasks × tools) matrix and return all rows.

    ``scenario_kwargs`` lets the caller pin per-task arguments — for example
    ``{"find-callers": {"symbol": "execute"}}`` overrides the default symbol.
    """
    scenario_kwargs = scenario_kwargs or {}
    rows: list[dict[str, Any]] = []
    total = len(repos) * len(tasks) * len(tools)
    idx = 0
    for repo in repos:
        for task in tasks:
            kw = scenario_kwargs.get(task, {})
            for tool in tools:
                idx += 1
                print(
                    f"[{idx}/{total}] {Path(repo).name} :: {task} :: {tool}",
                    file=sys.stderr,
                    flush=True,
                )
                row = run_case(repo, task, tool, **kw)
                rows.append(row)
    return rows


def write_jsonl(rows: list[dict[str, Any]], out_path: Path) -> None:
    """Write rows as JSONL — one row per line, UTF-8, atomic via rename.

    Atomic because partial files break later ``json.loads`` consumers and
    we'd rather lose a run than ship half a results file.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(out_path)


def write_json_aggregate(rows: list[dict[str, Any]], out_path: Path) -> None:
    """Write a single JSON object aggregating all rows for README rendering.

    Keeps the JSONL as the canonical row store; this aggregate is just the
    "results-2026-05-22.json" the README links to.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z") or "n/a",
        "row_count": len(rows),
        "rows": rows,
    }
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Agent-task benchmark harness (CodeGraph parity).",
    )
    parser.add_argument(
        "--repo",
        action="append",
        required=False,
        default=[],
        help="Repository path to benchmark (repeatable). Defaults to project root.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        required=False,
        default=[],
        help=f"Scenario id (repeatable). Default: all. Known: {', '.join(list_scenarios())}",
    )
    parser.add_argument(
        "--tool",
        action="append",
        required=False,
        default=[],
        help="Tool variant: 'baseline' or 'tsa' (repeatable). Default: both.",
    )
    parser.add_argument(
        "--symbol",
        default="execute",
        help="Function name for find-callers scenario (default: 'execute').",
    )
    parser.add_argument(
        "--file",
        default="",
        help="File path for refactor-suggest scenario (default: largest .py in repo).",
    )
    parser.add_argument(
        "--out",
        default=str(_THIS_DIR / "results.jsonl"),
        help="Output JSONL path.",
    )
    parser.add_argument(
        "--aggregate",
        default="",
        help="Optional aggregate JSON path. Empty = skip aggregate.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the bench from the command line. Returns a process exit code."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    repos = args.repo or [str(Path(__file__).resolve().parents[2])]
    tasks = args.scenario or list_scenarios()
    tools = args.tool or ["baseline", "tsa"]

    scenario_kwargs = {
        "find-callers": {"symbol": args.symbol},
        "refactor-suggest": {"file": args.file},
    }

    rows = run_matrix(repos, tasks, tools, scenario_kwargs=scenario_kwargs)
    write_jsonl(rows, Path(args.out))
    if args.aggregate:
        write_json_aggregate(rows, Path(args.aggregate))

    print(f"Wrote {len(rows)} rows to {args.out}", file=sys.stderr)
    if args.aggregate:
        print(f"Aggregate JSON written to {args.aggregate}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised by tests via main()
    raise SystemExit(main())
