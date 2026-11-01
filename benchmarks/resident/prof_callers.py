"""Stage profile of in-process ``nav callers`` (RFC-0042 §Motivation).

Usage::

    python benchmarks/resident/prof_callers.py --repo PATH --mode first|warm
        [--sample sample.json] [--targets 40] [--rounds 2] [--bodies] [--out out.json]

Each pipeline stage is wrapped with a timer. A stage's time **excludes** the
time of the wrapped stages it calls, so the buckets add up to the total; the
rest is reported as ``unwrapped_ms_per_query``. ``first`` times one query of a
fresh process; ``warm`` runs one untimed round over every target (qualified
and bare form), then ``--rounds`` timed rounds.

Answers are classified per query: ``review`` when the RFC-0040 review gates
ran (``_reference_scan`` was called), else ``edge_only``. Set ``PROF=1`` to
also write a cProfile report next to ``--out`` (it inflates the times, use it
only to explain buckets).

The repo must already be indexed (``tree-sitter-analyzer --project-root PATH
--full-index``). ``tree_sitter_analyzer`` is imported from the environment, so
point ``PYTHONPATH`` at the code under test.
"""

from __future__ import annotations

import argparse
import asyncio
import cProfile
import functools
import inspect
import io
import json
import os
import pstats
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import load_targets, summary_ms, write_json  # noqa: E402

EXCL: dict[str, float] = defaultdict(float)
CALLS: dict[str, int] = defaultdict(int)
_stack: list[list[float]] = []
MISSING: list[str] = []


def wrap(owner: Any, name: str, label: str) -> None:
    """Time ``owner.name`` exclusively (minus wrapped callees); skip if absent."""
    if not hasattr(owner, name):
        MISSING.append(label)
        return
    orig = getattr(owner, name)

    @functools.wraps(orig)
    def inner(*a: Any, **k: Any) -> Any:
        _stack.append([0.0])
        t0 = time.perf_counter()
        try:
            return orig(*a, **k)
        finally:
            dt = time.perf_counter() - t0
            child = _stack.pop()[0]
            EXCL[label] += dt - child
            CALLS[label] += 1
            if _stack:
                _stack[-1][0] += dt

    if isinstance(inspect.getattr_static(owner, name), staticmethod):
        inner = staticmethod(inner)  # type: ignore[assignment]
    setattr(owner, name, inner)


def wrap_cm(owner: Any, name: str, label: str) -> None:
    """Time a context manager's ``__enter__`` and ``__exit__`` separately."""
    if not hasattr(owner, name):
        MISSING.append(label)
        return
    orig = getattr(owner, name)

    @contextmanager
    def inner(*a: Any, **k: Any) -> Any:
        t0 = time.perf_counter()
        cm = orig(*a, **k)
        value = cm.__enter__()
        EXCL[label + ".enter"] += time.perf_counter() - t0
        CALLS[label + ".enter"] += 1
        if _stack:
            _stack[-1][0] += time.perf_counter() - t0
        try:
            yield value
        except BaseException:
            if not cm.__exit__(*sys.exc_info()):
                raise
        else:
            t1 = time.perf_counter()
            cm.__exit__(None, None, None)
            EXCL[label + ".exit"] += time.perf_counter() - t1
            if _stack:
                _stack[-1][0] += time.perf_counter() - t1

    setattr(owner, name, inner)


def install_wrappers() -> None:
    import tree_sitter_analyzer.cache.query_cost as qc
    import tree_sitter_analyzer.call_graph as cg
    import tree_sitter_analyzer.index_snapshot as isnap
    import tree_sitter_analyzer.mcp.tools.callers_absence as cabs
    import tree_sitter_analyzer.mcp.tools.callers_tool as ct
    import tree_sitter_analyzer.mcp.utils.format_helper as mfh

    wrap_cm(isnap, "certified_index_read", "A.certified_index_read")
    tool = ct.CodeGraphCallersTool
    wrap(tool, "_graph_for", "B.graph_object")
    wrap(cg.CachedCallGraph, "build", "B.graph_build_or_adopt")
    wrap(tool, "_sole_definition_file", "C.resolve.sole_definition_file")
    wrap(tool, "_single_method_name", "C.resolve.single_method_name")
    wrap(ct, "target_set", "C.resolve.target_set")
    wrap(tool, "_parse_fallback_refusal", "D.guard.parse_fallback_refusal")
    wrap(tool, "_cache_call_graph_built", "D.guard.call_graph_built")
    wrap(tool, "_sql_native_callers", "E.edges.sql_native_callers")
    for name in (
        "label_graph_relations",
        "name_bound_targets",
        "graph_bound_targets",
        "_sibling_methods",
    ):
        wrap(ct, name, "E.edges." + name.lstrip("_"))
    for name in (
        "unattributed_sites",
        "relation_files",
        "read_unresolved_inbound",
        "rank_sites",
        "_declaring_file_unresolved",
        "_declaring_file_excluded",
        "narrow_to_target",
        "drop_external_producers",
        "name_only_sites",
        "call_edge_lines",
    ):
        wrap(ct, name, "F.check." + name.lstrip("_"))
    wrap(ct, "relation_source_evidence", "F.check.relation_source_evidence(freshness)")
    wrap(ct, "assess_completeness", "G.review.assess_completeness")
    wrap(ct, "prove_edges", "G.review.prove")
    wrap(ct, "prove", "G.review.prove")
    for gate in [
        n for n in dir(cabs) if n.startswith("_") and callable(getattr(cabs, n))
    ]:
        if (
            gate == "_is_accessor"
            or gate.endswith("gate")
            or any(
                part in gate
                for part in ("reference", "unindexed", "decorator", "defined")
            )
        ):
            try:
                wrap(cabs, gate, "G.review." + gate)
            except (AttributeError, TypeError):
                pass
    wrap(tool, "_inline_caller_bodies", "H.bodies")
    wrap(ct, "is_index_rebuilding", "J.infra.is_index_rebuilding")
    wrap(
        ct,
        "_certification_ruled_out",
        "J.infra.certification_ruled_out(live_index_probe)",
    )
    wrap(tool, "_try_get_cache", "J.infra.try_get_cache")
    wrap(ct, "_is_stale_resolution", "J.infra.is_stale_resolution")
    wrap(ct.certification_timeouts, "should_skip", "J.infra.cert_timeouts")
    wrap(ct.certification_timeouts, "record", "J.infra.cert_timeouts")
    wrap(ct, "_symbol_indexed", "J.infra.symbol_indexed")
    wrap(ct, "not_in_index_hint", "J.infra.not_in_index_hint")
    wrap(ct, "build_response", "I.serialize.build_response")
    wrap(mfh, "apply_output_format_to_response", "I.serialize.apply_output_format")
    wrap(qc, "query_cost", "I.serialize.query_cost")
    wrap(ct, "apply_source_evidence", "I.serialize.apply_source_evidence")


_stat_count = {"n": 0}


def count_stats() -> None:
    real_lstat, real_stat = os.lstat, os.stat

    def counted_lstat(*a: Any, **k: Any) -> Any:
        _stat_count["n"] += 1
        return real_lstat(*a, **k)

    def counted_stat(*a: Any, **k: Any) -> Any:
        _stat_count["n"] += 1
        return real_stat(*a, **k)

    os.lstat = counted_lstat  # type: ignore[assignment]
    os.stat = counted_stat  # type: ignore[assignment]


class _NoProfile:
    def enable(self) -> None: ...

    def disable(self) -> None: ...


async def run(args: argparse.Namespace, import_s: float) -> dict[str, Any]:
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    targets = load_targets(args.sample, args.repo, args.targets)
    tool = CodeGraphCallersTool(args.repo)
    rec: dict[str, Any] = {
        "repo": Path(args.repo).name,
        "mode": args.mode,
        "import_s": round(import_s, 3),
        "bodies": args.bodies,
        "targets": len(targets),
    }
    prof: Any = cProfile.Profile() if os.environ.get("PROF") == "1" else _NoProfile()

    async def ask(name: str, file: str) -> dict[str, Any]:
        return await tool.execute(
            {"function_name": name, "file_path": file, "include_bodies": args.bodies}
        )

    if args.mode == "first":
        qual, _bare, file = targets[0]
        prof.enable()
        t0 = time.perf_counter()
        answer = await ask(qual, file)
        rec["total_s"] = round(time.perf_counter() - t0, 4)
        prof.disable()
        rec["n_queries"] = 1
        rec["completeness"] = answer.get("completeness")
    else:
        for qual, bare, file in targets:  # warm-up round, not timed
            for name in (qual, bare):
                await ask(name, file)
        EXCL.clear()
        CALLS.clear()
        _stat_count["n"] = 0
        latencies: list[float] = []
        by_kind: dict[str, list[float]] = {}
        completeness: dict[str, int] = {}
        size = 0
        prof.enable()
        for _ in range(args.rounds):
            for qual, bare, file in targets:
                for name in (qual, bare):
                    scans = CALLS.get("G.review._reference_scan", 0)
                    t0 = time.perf_counter()
                    answer = await ask(name, file)
                    latencies.append(time.perf_counter() - t0)
                    kind = (
                        "review"
                        if CALLS.get("G.review._reference_scan", 0) > scans
                        else "edge_only"
                    )
                    by_kind.setdefault(kind, []).append(latencies[-1])
                    key = str(answer.get("completeness"))
                    completeness[key] = completeness.get(key, 0) + 1
                    size = len(json.dumps(answer, default=str))
        prof.disable()
        rec["n_queries"] = len(latencies)
        rec["total_s"] = round(sum(latencies), 4)
        rec.update(summary_ms(latencies))
        rec["last_payload_bytes"] = size
        rec["by_kind"] = {k: summary_ms(v) for k, v in by_kind.items()}
        rec["completeness"] = completeness
    rec["stat_calls_per_query"] = round(_stat_count["n"] / rec["n_queries"], 1)
    accounted = sum(EXCL.values())
    rec["stages_ms_per_query"] = {
        k: round(v * 1000 / rec["n_queries"], 2)
        for k, v in sorted(EXCL.items(), key=lambda kv: -kv[1])
    }
    rec["calls_per_query"] = {
        k: round(v / rec["n_queries"], 2) for k, v in CALLS.items()
    }
    rec["unwrapped_ms_per_query"] = round(
        (rec["total_s"] - accounted) * 1000 / rec["n_queries"], 2
    )
    rec["unwrapped_stage_names"] = MISSING
    if isinstance(prof, cProfile.Profile) and args.out:
        text = io.StringIO()
        pstats.Stats(prof, stream=text).sort_stats("cumulative").print_stats(60)
        text.write("\n===== tottime\n")
        pstats.Stats(prof, stream=text).sort_stats("tottime").print_stats(30)
        Path(args.out).with_suffix(".prof.txt").write_text(
            text.getvalue(), encoding="utf-8"
        )
    return rec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--mode", choices=("first", "warm"), required=True)
    parser.add_argument("--sample", help="targets JSON; default: picked from the index")
    parser.add_argument("--targets", type=int, default=40)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--bodies", action="store_true", help="include_bodies=true")
    parser.add_argument("--out")
    args = parser.parse_args()
    t0 = time.perf_counter()
    install_wrappers()
    import_s = time.perf_counter() - t0
    count_stats()
    write_json(args.out, asyncio.run(run(args, import_s)))


if __name__ == "__main__":
    main()
