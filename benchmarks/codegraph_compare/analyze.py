"""analyze.py — Benchmark results aggregator.

Reads results/runs.jsonl and results/evals.jsonl, then produces:
  - results/summary.md   (markdown report)
  - results/summary.csv  (flat per-run table)

CLI usage:
    python benchmarks/codegraph_compare/analyze.py \\
        --runs   results/runs.jsonl \\
        --evals  results/evals.jsonl \\
        --output results/summary.md

evals.jsonl is optional; if absent quality columns are omitted with a
warning written to stderr.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

_INPUT_COST_PER_M = 3.0  # USD / M input tokens  (Sonnet 4.6)
_OUTPUT_COST_PER_M = 15.0  # USD / M output tokens (Sonnet 4.6)


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * _INPUT_COST_PER_M) + (
        output_tokens / 1_000_000 * _OUTPUT_COST_PER_M
    )


# ---------------------------------------------------------------------------
# JSONL loading & enrichment
# ---------------------------------------------------------------------------


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                print(
                    f"WARNING: skipping malformed JSON line {lineno} of {path}: {exc}",
                    file=sys.stderr,
                )
    return records


def _enrich(run: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *run* with derived fields: _cost, _total_tokens, _repo_name."""
    run = dict(run)
    # Support both schema field names (input_tokens) and runner field names (tokens_in)
    t_in = int(run.get("input_tokens") or run.get("tokens_in") or 0)
    t_out = int(run.get("output_tokens") or run.get("tokens_out") or 0)
    t_total = int(run.get("total_tokens") or 0)
    existing = run.get("estimated_cost_usd")
    run["_cost"] = (
        float(existing)
        if existing and float(existing) > 0
        else estimate_cost(t_in, t_out)
    )
    run["_total_tokens"] = t_total if t_total > 0 else t_in + t_out
    # Support both 'repo' (schema) and 'repo_path' (runner)
    repo_raw = run.get("repo") or run.get("repo_path") or "unknown"
    run["_repo_name"] = Path(str(repo_raw)).name
    # Normalise arm/backend fields and keep backend in the aggregate label so
    # Claude and Codex runs do not get averaged together.
    run["_agent_backend"] = run.get("agent_backend") or "claude"
    arm = run.get("arm") or run.get("arm_id") or "unknown"
    run["_arm_base"] = arm
    run["_arm"] = f"{run['_agent_backend']}/{arm}"
    return run


def _is_dry(run: dict[str, Any]) -> bool:
    return run.get("answer") == "DRY_RUN"


def _is_failed(run: dict[str, Any]) -> bool:
    return bool(run.get("error"))


def _is_timeout(run: dict[str, Any]) -> bool:
    return "timeout" in str(run.get("error") or "").lower()


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


def _med(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.median(clean) if clean else None


def _f(v: float | None, d: int = 4) -> str:
    return f"{v:.{d}f}" if v is not None else "—"


def _f2(v: float | None) -> str:
    return _f(v, 2)


def _pct(native: float | None, arm: float | None) -> str:
    if native is None or arm is None or native == 0:
        return "—"
    return f"{(native - arm) / native * 100:.1f}%"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _agg(runs: list[dict[str, Any]]) -> dict[str, Any]:
    live = [r for r in runs if not _is_dry(r)]
    return {
        "count": len(runs),
        "failed": sum(1 for r in runs if _is_failed(r)),
        "median_cost": _med([r["_cost"] for r in live]),
        "median_tokens": _med([r["_total_tokens"] for r in live]),
        "median_time": _med(
            [
                float(r["elapsed_seconds"])
                for r in live
                if r.get("elapsed_seconds") is not None
            ]
        ),
        "median_tool_calls": _med([int(r.get("tool_calls") or 0) for r in live]),
        "median_quality": _med(
            [r["_quality"] for r in live if r.get("_quality") is not None]
        ),
    }


# ---------------------------------------------------------------------------
# Markdown table helper
# ---------------------------------------------------------------------------


def _table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    def _row(cells: list[str]) -> str:
        return (
            "| "
            + " | ".join(
                c.ljust(widths[i] if i < len(widths) else 0)
                for i, c in enumerate(cells)
            )
            + " |"
        )

    sep = ["-" * w for w in widths]
    return "\n".join([_row(headers), _row(sep)] + [_row(r) for r in rows])


# ---------------------------------------------------------------------------
# Section generators
# ---------------------------------------------------------------------------


def _s_overview(runs: list[dict[str, Any]], has_evals: bool) -> str:
    repos = sorted({r["_repo_name"] for r in runs})
    arms = sorted({r["_arm"] for r in runs})
    models = sorted({r.get("model", "") for r in runs if r.get("model")})
    dates = sorted(r["started_at"] for r in runs if r.get("started_at"))
    dr = (
        f"{dates[0][:10]} — {dates[-1][:10]}"
        if len(dates) >= 2
        else (dates[0][:10] if dates else "—")
    )
    note = (
        ""
        if has_evals
        else "\n> **Note:** evals.jsonl not found — quality scores unavailable.\n"
    )
    total_evals = sum(1 for r in runs if r.get("_quality") is not None)
    lines = [
        "## 1. Overview\n",
        note,
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total runs | {len(runs)} |",
        f"| Total evals | {total_evals} |",
        f"| Dry-run stubs | {sum(1 for r in runs if _is_dry(r))} |",
        f"| Repos covered | {len(repos)} ({', '.join(repos)}) |",
        f"| Arms covered | {len(arms)} ({', '.join(arms)}) |",
        f"| Date range | {dr} |",
        f"| Model(s) | {', '.join(models) if models else '—'} |",
        f"| Failed runs | {sum(1 for r in runs if _is_failed(r))} |",
        f"| Timeout runs | {sum(1 for r in runs if _is_timeout(r))} |",
    ]
    return "\n".join(lines)


def _s_per_arm(by_arm: dict[str, list[dict[str, Any]]], has_evals: bool) -> str:
    headers = [
        "Arm",
        "Runs",
        "Median Cost ($)",
        "Median Tokens",
        "Median Time (s)",
        "Median Tool Calls",
        "Median Quality",
        "Failed",
    ]
    rows_data = []
    for arm, arm_runs in by_arm.items():
        a = _agg(arm_runs)
        q = _f2(a["median_quality"]) if has_evals else "n/a"
        rows_data.append(
            (
                a["median_tokens"] if a["median_tokens"] is not None else float("inf"),
                [
                    arm,
                    str(a["count"]),
                    _f(a["median_cost"], 6),
                    _f2(a["median_tokens"]),
                    _f2(a["median_time"]),
                    _f2(a["median_tool_calls"]),
                    q,
                    str(a["failed"]),
                ],
            )
        )
    rows_data.sort(key=lambda x: x[0])
    return "## 2. Per-arm aggregate\n\n" + _table(headers, [r for _, r in rows_data])


def _s_per_repo_arm(runs: list[dict[str, Any]], has_evals: bool) -> str:
    by_ra: dict[tuple[str, str], list] = defaultdict(list)
    for r in runs:
        by_ra[(r["_repo_name"], r["_arm"])].append(r)
    headers = [
        "Repo",
        "Arm",
        "Median Cost ($)",
        "Median Tokens",
        "Median Time (s)",
        "Median Quality",
    ]
    rows = []
    for (repo, arm), arm_runs in sorted(by_ra.items()):
        a = _agg(arm_runs)
        q = _f2(a["median_quality"]) if has_evals else "n/a"
        rows.append(
            [
                repo,
                arm,
                _f(a["median_cost"], 6),
                _f2(a["median_tokens"]),
                _f2(a["median_time"]),
                q,
            ]
        )
    return "## 3. Per-repo × arm\n\n" + _table(headers, rows)


def _s_savings(runs: list[dict[str, Any]]) -> str:
    by_ra: dict[tuple[str, str], list] = defaultdict(list)
    for r in runs:
        by_ra[(r["_repo_name"], r["_arm"])].append(r)

    def _medians(repo: str, arm: str) -> tuple[float | None, float | None]:
        live = [r for r in by_ra.get((repo, arm), []) if not _is_dry(r)]
        return _med([r["_total_tokens"] for r in live]), _med(
            [r["_cost"] for r in live]
        )

    repos = sorted({r["_repo_name"] for r in runs})
    non_native = sorted({r["_arm"] for r in runs if r["_arm_base"] != "native-only"})
    if not non_native:
        return "## 4. Savings vs native-only\n\n_No non-native arms found._"

    headers = (
        ["Repo"]
        + [f"{a} token savings" for a in non_native]
        + [f"{a} cost savings" for a in non_native]
    )
    rows = []
    for repo in repos:
        row = [repo]
        for arm in non_native:
            backend = arm.split("/", 1)[0]
            n_tok, _ = _medians(repo, f"{backend}/native-only")
            if n_tok is None:
                row.append("—")
                continue
            row.append(_pct(n_tok, _medians(repo, arm)[0]))
        for arm in non_native:
            backend = arm.split("/", 1)[0]
            _, n_cost = _medians(repo, f"{backend}/native-only")
            if n_cost is None:
                row.append("—")
                continue
            row.append(_pct(n_cost, _medians(repo, arm)[1]))
        rows.append(row)
    if not rows:
        return "## 4. Savings vs native-only\n\n_No repos with both native-only and non-native data._"
    return "## 4. Savings vs native-only\n\n" + _table(headers, rows)


def _s_quality_efficiency(runs: list[dict[str, Any]], has_evals: bool) -> str:
    if not has_evals:
        return (
            "## 5. Quality vs efficiency scatter summary\n\n_Quality data unavailable._"
        )

    native_live = [
        r for r in runs if r["_arm_base"] == "native-only" and not _is_dry(r)
    ]
    n_tok_med = _med([r["_total_tokens"] for r in native_live])

    lines = ["## 5. Quality vs efficiency scatter summary\n"]
    for arm in sorted({r["_arm"] for r in runs}):
        arm_live = [
            r
            for r in runs
            if r["_arm"] == arm and not _is_dry(r) and r.get("_quality") is not None
        ]
        if len(arm_live) < 2:
            lines.append(f"- **{arm}**: insufficient data for correlation.")
            continue
        toks = [r["_total_tokens"] for r in arm_live]
        quals = [r["_quality"] for r in arm_live]
        n = len(arm_live)
        mt, mq = sum(toks) / n, sum(quals) / n
        cov = sum((t - mt) * (q - mq) for t, q in zip(toks, quals, strict=True)) / n
        st = (sum((t - mt) ** 2 for t in toks) / n) ** 0.5
        sq = (sum((q - mq) ** 2 for q in quals) / n) ** 0.5
        if st == 0 or sq == 0:
            direction = "no change in"
        else:
            rv = cov / (st * sq)
            direction = (
                "higher" if rv > 0.1 else ("lower" if rv < -0.1 else "no change in")
            )
        arm_tok_med = _med(toks)
        if n_tok_med and arm_tok_med and arm != "native-only":
            vs = (
                "lower"
                if arm_tok_med < n_tok_med
                else ("higher" if arm_tok_med > n_tok_med else "similar")
            )
            lines.append(
                f"- **{arm}**: {vs} token use correlates with {direction} quality vs native-only."
            )
        else:
            lines.append(f"- **{arm}**: token use correlates with {direction} quality.")
    return "\n".join(lines)


def _s_cold_warm(runs: list[dict[str, Any]]) -> str:
    headers = [
        "Repo",
        "Arm",
        "Index Build Time (s)",
        "Index Size (MB)",
        "Warm Query Median Tokens",
        "Cold Query Median Tokens",
    ]
    rows = []
    for repo in sorted({r["_repo_name"] for r in runs}):
        for cold_arm, warm_arm in [
            ("codegraph-cold", "codegraph-warm"),
            ("tsa-cold", "tsa-warm"),
        ]:
            cold = [
                r
                for r in runs
                if r["_repo_name"] == repo
                and r["_arm_base"] == cold_arm
                and not _is_dry(r)
            ]
            warm = [
                r
                for r in runs
                if r["_repo_name"] == repo
                and r["_arm_base"] == warm_arm
                and not _is_dry(r)
            ]
            if not cold:
                continue
            build = _med(
                [
                    float(r["index_build_seconds"])
                    for r in cold
                    if r.get("index_build_seconds") is not None
                ]
            )
            size_b = _med(
                [
                    float(r["index_size_bytes"])
                    for r in cold
                    if r.get("index_size_bytes") is not None
                ]
            )
            size_mb = size_b / (1024 * 1024) if size_b is not None else None
            rows.append(
                [
                    repo,
                    f"{cold_arm} / {warm_arm}",
                    _f2(build),
                    _f2(size_mb),
                    _f2(_med([r["_total_tokens"] for r in warm]) if warm else None),
                    _f2(_med([r["_total_tokens"] for r in cold])),
                ]
            )
    if not rows:
        return "## 6. Cold vs warm index comparison\n\n_No cold-arm data found._"
    return "## 6. Cold vs warm index comparison\n\n" + _table(headers, rows)


def _s_failed(runs: list[dict[str, Any]]) -> str:
    problems = [r for r in runs if _is_failed(r) or _is_dry(r)]
    if not problems:
        return "## 7. Failed / timed-out runs\n\n_No failed or dry-run records._"
    headers = ["run_id", "repo", "arm", "question_id", "error / note"]
    rows = []
    for r in problems:
        msg = r.get("error") or ("DRY_RUN stub" if _is_dry(r) else "—")
        qid = r.get("question_id") or r.get("question_id", "—")
        rows.append(
            [r.get("run_id", "—"), r["_repo_name"], r["_arm"], str(qid), str(msg)[:120]]
        )
    return "## 7. Failed / timed-out runs\n\n" + _table(headers, rows)


def _s_notes(n_repeats: int) -> str:
    return "\n".join(
        [
            "## 8. Notes\n",
            f"- Median reported across {n_repeats} repeat(s) per question per arm",
            "- Cost uses the agent CLI reported cost when available; otherwise it is estimated at $3/M input and $15/M output",
            "- Quality scores from LLM evaluator (claude-haiku) on 1-5 scale",
            "- Index build time excluded from warm query timing",
        ]
    )


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

_RUN_FIELDS = [
    "run_id",
    "question_id",
    "agent_backend",
    "arm_id",
    "repo_name",
    "repo_path",
    "repeat",
    "model",
    "timeout_seconds",
    "started_at",
    "ended_at",
    "elapsed_seconds",
    "answer",
    "tokens_in",
    "cached_input_tokens",
    "tokens_out",
    "reasoning_output_tokens",
    "total_tokens",
    "tool_calls",
    "estimated_cost_usd",
    "error",
    "index_build_seconds",
    "index_size_bytes",
    "prompt_file",
]
_EVAL_FIELDS = ["quality_score", "evaluator_model", "eval_notes"]


def _write_csv(
    runs: list[dict[str, Any]], evals_by_id: dict[str, dict[str, Any]], path: Path
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=_RUN_FIELDS + _EVAL_FIELDS, extrasaction="ignore"
        )
        writer.writeheader()
        for run in runs:
            ev = evals_by_id.get(run.get("run_id", ""), {})
            # quality_score: prefer EvalRecord.overall, fall back to quality_score key
            quality = (
                ev.get("overall")
                if ev.get("overall") is not None
                else ev.get("quality_score")
            )
            writer.writerow(
                {
                    "run_id": run.get("run_id"),
                    "question_id": run.get("question_id"),
                    "agent_backend": run["_agent_backend"],
                    "arm_id": run["_arm"],
                    "repo_name": run["_repo_name"],
                    "repo_path": run.get("repo_path") or run.get("repo"),
                    "repeat": run.get("repeat"),
                    "model": run.get("model"),
                    "timeout_seconds": run.get("timeout_seconds"),
                    "started_at": run.get("started_at"),
                    "ended_at": run.get("ended_at"),
                    "elapsed_seconds": run.get("elapsed_seconds"),
                    "answer": run.get("answer"),
                    "tokens_in": run.get("tokens_in") or run.get("input_tokens"),
                    "cached_input_tokens": run.get("cached_input_tokens"),
                    "tokens_out": run.get("tokens_out") or run.get("output_tokens"),
                    "reasoning_output_tokens": run.get("reasoning_output_tokens"),
                    "total_tokens": run["_total_tokens"],
                    "tool_calls": run.get("tool_calls"),
                    "estimated_cost_usd": run["_cost"],
                    "error": run.get("error"),
                    "index_build_seconds": run.get("index_build_seconds"),
                    "index_size_bytes": run.get("index_size_bytes"),
                    "prompt_file": run.get("prompt_file"),
                    "quality_score": quality,
                    "evaluator_model": ev.get("evaluator_model"),
                    "eval_notes": ev.get("eval_notes") or ev.get("missing_key_points"),
                }
            )


# ---------------------------------------------------------------------------
# Main report builder
# ---------------------------------------------------------------------------


def build_report(runs_path: Path, evals_path: Path | None, output_path: Path) -> None:
    if not runs_path.exists():
        print(f"ERROR: runs file not found: {runs_path}", file=sys.stderr)
        sys.exit(1)

    runs = [_enrich(r) for r in _load_jsonl(runs_path)]

    has_evals = False
    evals_by_id: dict[str, dict[str, Any]] = {}
    if evals_path is not None and evals_path.exists():
        for e in _load_jsonl(evals_path):
            if "run_id" in e:
                evals_by_id[e["run_id"]] = e
        has_evals = True
    elif evals_path is not None:
        print(
            f"WARNING: evals file not found: {evals_path} — quality columns omitted.",
            file=sys.stderr,
        )

    for run in runs:
        ev = evals_by_id.get(run.get("run_id", ""), {})
        # EvalRecord.overall is the primary quality field (schemas.py); fall back to quality_score
        q = (
            ev.get("overall")
            if ev.get("overall") is not None
            else ev.get("quality_score")
        )
        run["_quality"] = float(q) if q is not None else None

    by_arm: dict[str, list] = defaultdict(list)
    for run in runs:
        by_arm[run["_arm"]].append(run)

    repeats_counts: dict[tuple[str, str], set] = defaultdict(set)
    for run in runs:
        repeats_counts[(run.get("question_id", ""), run["_arm"])].add(
            run.get("repeat", 0)
        )
    max_repeats = max((len(v) for v in repeats_counts.values()), default=1)

    sections = [
        "# Benchmark Summary Report\n",
        _s_overview(runs, has_evals),
        "",
        _s_per_arm(by_arm, has_evals),
        "",
        _s_per_repo_arm(runs, has_evals),
        "",
        _s_savings(runs),
        "",
        _s_quality_efficiency(runs, has_evals),
        "",
        _s_cold_warm(runs),
        "",
        _s_failed(runs),
        "",
        _s_notes(max_repeats),
        "",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(sections), encoding="utf-8")
    print(f"Report written to {output_path}", file=sys.stderr)

    csv_path = output_path.with_suffix(".csv")
    _write_csv(runs, evals_by_id, csv_path)
    print(f"CSV written to {csv_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze benchmark runs/evals JSONL and produce a markdown summary.",
    )
    parser.add_argument(
        "--runs",
        type=Path,
        default=Path("results/runs.jsonl"),
        help="Path to runs.jsonl (default: results/runs.jsonl)",
    )
    parser.add_argument(
        "--evals",
        type=Path,
        default=Path("results/evals.jsonl"),
        help="Path to evals.jsonl (default: results/evals.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/summary.md"),
        help="Output markdown path (default: results/summary.md)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    build_report(args.runs, args.evals, args.output)


if __name__ == "__main__":
    main()
