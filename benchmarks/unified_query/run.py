"""Run the unified-query benchmark for one repository and arm (RFC-0041).

Usage::

    uv run python benchmarks/unified_query/run.py --repo rich \
        --root C:/git-private/tsa-dogfood/uq/repos/rich \
        --arm today --out C:/git-private/tsa-dogfood/uq/results

Run with ``ANSWER_CACHE_BUDGET_MB=0`` so no arm is served a memoised answer.
After one untimed warm-up pass (a long-lived MCP server has built its graph),
each question is timed exactly once. Recorded request and
response texts go to ``<out>/<repo>-<arm>-texts.jsonl`` for token counting
(``tokens.py``); per-question rows go to ``<out>/<repo>-<arm>.jsonl``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import GrepClient, Trace, TsaClient  # noqa: E402
from oracle import Oracle  # noqa: E402
from questions import QUESTIONS, oracle_answer  # noqa: E402


def _plans(arm: str) -> dict[str, Any]:
    if arm == "today":
        from plans_today import PLANS
    elif arm == "grep":
        from plans_grep import PLANS
    elif arm == "uql":
        from plans_uql import PLANS
    else:
        raise SystemExit(f"unknown arm {arm}")
    return PLANS


def _discovery(arm: str) -> dict[str, Any]:
    if arm == "today":
        from plans_today import DISCOVERY
    elif arm == "uql":
        from plans_uql import DISCOVERY
    else:
        return {}
    return DISCOVERY


def _score(
    answer: dict[str, set[str]],
    claims: dict[str, str | None],
    truth: dict[str, set[str]],
) -> dict[str, Any]:
    sets: dict[str, Any] = {}
    for name, expected in truth.items():
        got = answer.get(name, set())
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        claim = claims.get(name)
        sets[name] = {
            "expected": len(expected),
            "got": len(got),
            "missing": missing,
            "extra": extra,
            "exact": not missing and not extra,
            "claim": claim,
            "wrong_complete": claim == "complete" and bool(missing),
        }
    return {
        "exact": all(s["exact"] for s in sets.values()),
        "wrong_complete": any(s["wrong_complete"] for s in sets.values()),
        "sets": sets,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--arm", required=True, choices=["today", "grep", "uql"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--tag", default="", help="suffix for output files (paired runs)")
    ap.add_argument(
        "--cold",
        action="store_true",
        help="no warm-up: the first call of this process is the question (cold)",
    )
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    oracle = Oracle(args.root)
    plans = _plans(args.arm)
    discovery = _discovery(args.arm)
    client: Any = TsaClient(args.root) if args.arm != "grep" else GrepClient(args.root)
    rows: list[dict[str, Any]] = []
    texts: list[dict[str, Any]] = []
    # Warm server: one untimed callers call on an unrelated symbol builds the
    # in-memory graph, as a long-lived MCP server has. ``--cold`` skips it.
    # The facade answer cache is disabled by the caller
    # (ANSWER_CACHE_BUDGET_MB=0) so no arm is served a memoised payload.
    warmup = 0.0
    if not args.cold and args.arm != "grep":
        client.trace = Trace()
        client.call("nav", {"action": "callers", "function_name": "main"})
        warmup = client.trace.seconds
    for q in QUESTIONS[args.repo]:
        if args.only and q.qid not in args.only.split(","):
            continue
        truth = oracle_answer(oracle, q)
        client.trace = Trace()
        answer, claims = plans[q.kind](client, q.params)
        trace = client.trace
        repeat = None
        if not args.cold:
            client.trace = Trace()
            plans[q.kind](client, q.params)
            repeat = round(client.trace.seconds, 3)
        disc_bytes = 0
        if q.kind in discovery:
            facade, dargs = discovery[q.kind]
            saved = client.trace
            client.trace = Trace()
            client.call(facade, dargs)
            disc = client.trace.calls[0]
            disc_bytes = len(disc.response.encode("utf-8"))
            texts.append(
                {"qid": q.qid, "discovery": True, "text": disc.request + disc.response}
            )
            client.trace = saved
        row = {
            "repo": args.repo,
            "arm": args.arm,
            "qid": q.qid,
            "question": q.text,
            "calls": len(trace.calls),
            "response_bytes": trace.response_bytes,
            "request_bytes": trace.request_bytes,
            "discovery_bytes": disc_bytes,
            "seconds": round(trace.seconds, 3),
            "repeat_seconds": repeat,
            "cold": args.cold,
            "warmup_seconds": round(warmup, 3),
            "score": _score(answer, claims, truth),
        }
        rows.append(row)
        texts.append(
            {
                "qid": q.qid,
                "discovery": False,
                "text": "".join(c.request + c.response for c in trace.calls),
            }
        )
        print(
            f"{q.qid} {args.arm}: calls={row['calls']} bytes={row['response_bytes']} "
            f"t={row['seconds']}s exact={row['score']['exact']} "
            f"wrong_complete={row['score']['wrong_complete']}",
            flush=True,
        )
    stem = f"{args.repo}-{args.arm}" + (f"-cold-{args.only}" if args.cold else "")
    if args.tag:
        stem += f"-{args.tag}"
    (out / f"{stem}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    (out / f"{stem}-texts.jsonl").write_text(
        "\n".join(json.dumps(t) for t in texts) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
