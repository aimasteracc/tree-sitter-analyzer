"""Answer identity with the RFC-0042 switch on and off, through a real MCP server (V1).

Usage::

    python benchmarks/resident/identity.py --repo PATH --rows FILE [--rows FILE ...]
        [--passes off,on,off] [--settle 10] [--repeat 1] [--env KEY=VALUE ...] [--out out.json]

``--rows`` are stored dogfood answer files. The ``nav callers`` question of
every row is replayed; the stored payloads are not compared (they come from
another version). Three row shapes are understood:

* battery rows with ``args`` (the exact ``nav`` arguments);
* sweep rows with ``def`` (``qual``, ``name``, ``file``): asked qualified and bare;
* rows with ``target`` and ``query`` (TypeScript sweeps and ground-truth answers).

Questions are de-duplicated by their arguments. Each pass starts one fresh
server (``python -m tree_sitter_analyzer.mcp.server``, this interpreter and
``PYTHONPATH``): ``off`` sets ``TSA_RESIDENT=off``; ``on`` leaves the default
(``background``) and waits ``--settle`` seconds after ``initialize`` so the
loader finishes. Answers are compared field by field after dropping timing,
process and ``query_cost`` fields (the r15 ``tools/identity.py`` rule).

The report counts, per pair of passes, the questions whose answers differ, and
the questions answered ``complete`` with the switch on but not off (a release
blocker under RFC-0042 V1). ``off`` against ``off`` is the noise baseline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import MIN_FREE_GB, SuspendClock, free_gb, write_json  # noqa: E402
from mcp_latency import StdioClient, server_env  # noqa: E402

#: Fields that differ between any two runs (r15 ``tools/identity.py``) plus cost.
SKIP = re.compile(
    r"(^|_)(seconds|wall|elapsed\w*|cpu\w*|load|server_pid|pid|t|ms|duration\w*|"
    r"first_seconds|median_seconds|p90_seconds|max_seconds|time|timing|timings|"
    r"started\w*|finished\w*|phase_seconds|generated_at|seconds_\w+|\w+_seconds|"
    r"\w+_ms)$|^query_cost$"
)


def strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if not SKIP.search(k)}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def _nav(name: str, file: str) -> dict[str, Any]:
    return {
        "action": "callers",
        "function_name": name,
        "file_path": file,
        "include_bodies": False,
        "limit": 5000,
    }


def questions_of(row: Any) -> list[dict[str, Any]]:
    """The ``nav callers`` arguments a stored row asked (empty when not a callers row)."""
    if not isinstance(row, dict):
        return []
    args = row.get("args")
    if isinstance(args, dict) and args.get("action") == "callers":
        return [dict(args)]
    definition = row.get("def")
    if isinstance(definition, dict) and definition.get("file"):
        names = [definition.get("qual"), definition.get("name")]
        return [_nav(n, definition["file"]) for n in dict.fromkeys(names) if n]
    target = row.get("target")
    if isinstance(target, dict) and target.get("file") and row.get("query"):
        return [_nav(str(row["query"]), str(target["file"]))]
    return []


def load_questions(paths: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Distinct questions of the rows, and how many callers rows were read."""
    seen: dict[str, dict[str, Any]] = {}
    rows_read = 0
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = data
        if isinstance(data, dict):
            rows = data.get("results") or data.get("rows") or []
        for row in rows if isinstance(rows, list) else []:
            asked = questions_of(row)
            rows_read += bool(asked)
            for question in asked:
                seen.setdefault(json.dumps(question, sort_keys=True), question)
    return list(seen.values()), rows_read


def run_pass(
    repo: str, mode: str, questions: list[dict[str, Any]], args: argparse.Namespace
) -> dict[str, Any]:
    env_pairs = list(args.env)
    if mode == "off":
        env_pairs.append("TSA_RESIDENT=off")
    clock = SuspendClock()
    # Run the server outside the repo: ``python -m`` puts the working directory on
    # ``sys.path``, and a repo such as pydantic would shadow the server's own import.
    client = StdioClient(
        repo, server_env(env_pairs), args.stderr, cwd=str(Path(repo).parent)
    )
    answers: dict[str, Any] = {}
    try:
        client.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "tsa-resident-identity", "version": "1"},
            },
        )
        client.notify("notifications/initialized", {})
        client.request("tools/list", {})
        if mode != "off" and args.settle:
            time.sleep(args.settle)
        # ``--repeat`` asks the whole list again in the same server; the last
        # round is kept, so with the switch on it is answered from warm state.
        for _round in range(max(1, args.repeat)):
            for question in questions:
                _seconds, _size, payload = client.call("nav", question)
                answers[json.dumps(question, sort_keys=True)] = strip(payload)
    finally:
        client.close()
    return {"mode": mode, "answers": answers, "suspended": clock.suspended()}


def compare(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(set(a["answers"]) | set(b["answers"]))
    differ = [k for k in keys if a["answers"].get(k) != b["answers"].get(k)]
    new_complete = [
        k
        for k in keys
        if (b["answers"].get(k) or {}).get("completeness") == "complete"
        and (a["answers"].get(k) or {}).get("completeness") != "complete"
    ]
    return {
        "pair": f"{a['mode']}->{b['mode']}",
        "questions": len(keys),
        "differ": len(differ),
        "new_complete_in_second": len(new_complete),
        "examples": differ[:5],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--rows", action="append", required=True)
    parser.add_argument("--passes", default="off,on,off")
    parser.add_argument("--settle", type=float, default=10.0)
    parser.add_argument("--repeat", type=int, default=1, help="rounds per pass")
    parser.add_argument("--env", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--stderr", default=None)
    parser.add_argument("--out")
    args = parser.parse_args()
    repo = str(Path(args.repo).resolve())
    if args.stderr is None:
        args.stderr = str(Path(repo).parent / "identity-server.stderr.log")
    questions, rows_read = load_questions(args.rows)
    passes: list[dict[str, Any]] = []
    for mode in args.passes.split(","):
        if free_gb(repo) < MIN_FREE_GB:
            raise SystemExit(f"stopping: less than {MIN_FREE_GB} GiB free")
        passes.append(run_pass(repo, mode.strip(), questions, args))
    completeness: dict[str, dict[str, int]] = {}
    for number, done in enumerate(passes):
        counts: dict[str, int] = {}
        for answer in done["answers"].values():
            key = str((answer or {}).get("completeness"))
            counts[key] = counts.get(key, 0) + 1
        completeness[f"{number}:{done['mode']}"] = counts
    record = {
        "repo": Path(repo).name,
        "rows": [Path(p).name for p in args.rows],
        "rows_read": rows_read,
        "questions": len(questions),
        "passes": [p["mode"] for p in passes],
        "repeat": args.repeat,
        "suspended": any(p["suspended"] for p in passes),
        "completeness": completeness,
        "comparisons": [
            compare(passes[i], passes[j])
            for i in range(len(passes))
            for j in range(i + 1, len(passes))
        ],
    }
    write_json(args.out, record)


if __name__ == "__main__":
    main()
