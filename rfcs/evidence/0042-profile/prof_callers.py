"""Phase profile of nav callers (worktree code).

python -I prof_callers.py <repo> <sample.json> <mode: first|warm> <out.json> [n_targets] [bodies 0|1]

Wraps the callers pipeline stages and reports exclusive time per stage
(a stage's time excludes the time of wrapped stages it calls), plus cProfile.
"""

import asyncio
import cProfile
import functools
import io
import json
import os
import pstats
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, r"C:\git-private\tsa-worktrees\rfc-1855")

repo, sample, mode, out = sys.argv[1:5]
n_targets = int(sys.argv[5]) if len(sys.argv) > 5 else 10
bodies = bool(int(sys.argv[6])) if len(sys.argv) > 6 else False

t_imp0 = time.perf_counter()
import tree_sitter_analyzer.cache.query_cost as qc  # noqa: E402
import tree_sitter_analyzer.call_graph as cg  # noqa: E402
import tree_sitter_analyzer.index_snapshot as isnap  # noqa: E402
import tree_sitter_analyzer.mcp.tools.callers_absence as cabs  # noqa: E402
import tree_sitter_analyzer.mcp.tools.callers_tool as ct  # noqa: E402
import tree_sitter_analyzer.mcp.utils.format_helper as mfh  # noqa: E402

t_imp1 = time.perf_counter()

EXCL = defaultdict(float)
CALLS = defaultdict(int)
_stack: list[list[float]] = []


def wrap(owner, name, label=None):
    orig = getattr(owner, name)
    label = label or name

    @functools.wraps(orig)
    def inner(*a, **k):
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

    import inspect

    if isinstance(inspect.getattr_static(owner, name), staticmethod):
        inner = staticmethod(inner)
    setattr(owner, name, inner)


def wrap_cm(owner, name, label):
    """Context manager factory: time __enter__ and __exit__ (setup/teardown)."""
    orig = getattr(owner, name)
    from contextlib import contextmanager

    @contextmanager
    def inner(*a, **k):
        t0 = time.perf_counter()
        cm = orig(*a, **k)
        v = cm.__enter__()
        EXCL[label + ".enter"] += time.perf_counter() - t0
        CALLS[label + ".enter"] += 1
        if _stack:
            _stack[-1][0] += time.perf_counter() - t0
        try:
            yield v
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


# --- stage wrappers -------------------------------------------------------
wrap_cm(isnap, "certified_index_read", "A.certified_index_read")
T = ct.CodeGraphCallersTool
wrap(T, "_graph_for", "B.graph_object")
wrap(cg.CachedCallGraph, "build", "B.graph_build_or_adopt")
wrap(T, "_sole_definition_file", "C.resolve.sole_definition_file")
wrap(T, "_single_method_name", "C.resolve.single_method_name")
wrap(ct, "target_set", "C.resolve.target_set")
wrap(T, "_parse_fallback_refusal", "D.guard.parse_fallback_refusal")
wrap(T, "_cache_call_graph_built", "D.guard.call_graph_built")
wrap(T, "_sql_native_callers", "E.edges.sql_native_callers")
wrap(ct, "label_graph_relations", "E.edges.label_graph_relations")
wrap(ct, "name_bound_targets", "E.edges.name_bound_targets")
wrap(ct, "graph_bound_targets", "E.edges.graph_bound_targets")
wrap(ct, "_sibling_methods", "E.edges.sibling_methods")
wrap(ct, "unattributed_sites", "F.check.unattributed_sites")
wrap(ct, "relation_files", "F.check.relation_files")
wrap(ct, "relation_source_evidence", "F.check.relation_source_evidence(freshness)")
wrap(ct, "read_unresolved_inbound", "F.check.read_unresolved_inbound")
wrap(ct, "rank_sites", "F.check.rank_sites")
wrap(ct, "_declaring_file_unresolved", "F.check.declaring_file_unresolved")
wrap(ct, "_declaring_file_excluded", "F.check.declaring_file_excluded")
wrap(ct, "narrow_to_target", "F.check.narrow_to_target")
wrap(ct, "drop_external_producers", "F.check.drop_external_producers")
wrap(ct, "name_only_sites", "F.check.name_only_sites")
wrap(ct, "call_edge_lines", "F.check.call_edge_lines")
wrap(ct, "assess_completeness", "G.review.assess_completeness")
wrap(ct, "prove_edges", "G.review.prove")
wrap(ct, "prove", "G.review.prove")
for gate in [n for n in dir(cabs) if n.startswith("_") and callable(getattr(cabs, n))]:
    if (
        gate in ("_is_accessor",)
        or gate.endswith("gate")
        or "reference" in gate
        or "unindexed" in gate
        or "decorator" in gate
        or "defined" in gate
    ):
        try:
            wrap(cabs, gate, "G.review." + gate)
        except Exception:
            pass
wrap(T, "_inline_caller_bodies", "H.bodies")
wrap(ct, "is_index_rebuilding", "J.infra.is_index_rebuilding")
wrap(
    ct, "_certification_ruled_out", "J.infra.certification_ruled_out(live_index_probe)"
)
wrap(T, "_try_get_cache", "J.infra.try_get_cache")
wrap(ct, "_is_stale_resolution", "J.infra.is_stale_resolution")
wrap(ct.certification_timeouts, "should_skip", "J.infra.cert_timeouts")
wrap(ct.certification_timeouts, "record", "J.infra.cert_timeouts")
wrap(ct, "_symbol_indexed", "J.infra.symbol_indexed")
wrap(ct, "not_in_index_hint", "J.infra.not_in_index_hint")
wrap(ct, "build_response", "I.serialize.build_response")
wrap(mfh, "apply_output_format_to_response", "I.serialize.apply_output_format")
wrap(qc, "query_cost", "I.serialize.query_cost")
wrap(ct, "apply_source_evidence", "I.serialize.apply_source_evidence")


def load_targets(p, n):
    d = json.loads(Path(p).read_text(encoding="utf-8"))
    rows = d["targets"] if isinstance(d, dict) else d
    res = []
    for t in rows:
        q = t.get("qual") or (
            f"{t['class']}.{t['name']}" if t.get("class") else t["name"]
        )
        res.append((q, q.rsplit(".", 1)[-1], t["file"]))
    return res[:n]


targets = load_targets(sample, n_targets)
nlstat = {"n": 0}
_l = os.lstat
_s = os.stat


def counted_lstat(*a, **k):
    nlstat["n"] += 1
    return _l(*a, **k)


def counted_stat(*a, **k):
    nlstat["n"] += 1
    return _s(*a, **k)


os.lstat = counted_lstat
os.stat = counted_stat


async def run():
    tool = ct.CodeGraphCallersTool(repo)
    rec = {
        "repo": Path(repo).name,
        "mode": mode,
        "import_s": round(t_imp1 - t_imp0, 3),
        "bodies": bodies,
    }
    prof = (
        cProfile.Profile()
        if os.environ.get("PROF") == "1"
        else type("N", (), {"enable": lambda s: None, "disable": lambda s: None})()
    )
    if mode == "first":
        q, b, f = targets[0]
        prof.enable()
        t0 = time.perf_counter()
        r = await tool.execute(
            {"function_name": q, "file_path": f, "include_bodies": bodies}
        )
        rec["total_s"] = round(time.perf_counter() - t0, 4)
        prof.disable()
        rec["n_queries"] = 1
        rec["completeness"] = r.get("completeness")
    else:
        for q, b, f in targets:  # warm-up round, not timed
            for name in (q, b):
                await tool.execute(
                    {"function_name": name, "file_path": f, "include_bodies": bodies}
                )
        EXCL.clear()
        CALLS.clear()
        nlstat["n"] = 0
        lat = []
        bykind = {}
        comp = {}
        prof.enable()
        for _ in range(2):
            for q, b, f in targets:
                for name in (q, b):
                    nref0 = CALLS.get("G.review._reference_scan", 0)
                    t0 = time.perf_counter()
                    r = await tool.execute(
                        {
                            "function_name": name,
                            "file_path": f,
                            "include_bodies": bodies,
                        }
                    )
                    lat.append(time.perf_counter() - t0)
                    kind = (
                        "review"
                        if CALLS.get("G.review._reference_scan", 0) > nref0
                        else "edge_only"
                    )
                    bykind.setdefault(kind, []).append(lat[-1])
                    comp[r.get("completeness")] = comp.get(r.get("completeness"), 0) + 1
                    sz = len(json.dumps(r, default=str))
        prof.disable()
        rec["n_queries"] = len(lat)
        rec["total_s"] = round(sum(lat), 4)
        rec["median_ms"] = round(statistics.median(lat) * 1000, 1)
        rec["p90_ms"] = round(sorted(lat)[int(len(lat) * 0.9) - 1] * 1000, 1)
        rec["max_ms"] = round(max(lat) * 1000, 1)
        rec["last_payload_bytes"] = sz
        rec["by_kind"] = {
            k: {
                "n": len(v),
                "median_ms": round(statistics.median(v) * 1000, 1),
                "max_ms": round(max(v) * 1000, 1),
            }
            for k, v in bykind.items()
        }
        rec["completeness"] = comp
    rec["stat_calls_per_query"] = round(nlstat["n"] / rec["n_queries"], 1)
    acc = sum(EXCL.values())
    rec["stages_ms_per_query"] = {
        k: round(v * 1000 / rec["n_queries"], 2)
        for k, v in sorted(EXCL.items(), key=lambda kv: -kv[1])
    }
    rec["calls_per_query"] = {
        k: round(v / rec["n_queries"], 2) for k, v in CALLS.items()
    }
    rec["unwrapped_ms_per_query"] = round(
        (rec["total_s"] - acc) * 1000 / rec["n_queries"], 2
    )
    sio = io.StringIO()
    if isinstance(prof, cProfile.Profile):
        pstats.Stats(prof, stream=sio).sort_stats("cumulative").print_stats(60)
    sio2 = io.StringIO()
    if isinstance(prof, cProfile.Profile):
        pstats.Stats(prof, stream=sio2).sort_stats("tottime").print_stats(30)
    Path(out).with_suffix(".prof.txt").write_text(
        sio.getvalue() + "\n===== tottime\n" + sio2.getvalue(), encoding="utf-8"
    )
    Path(out).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(json.dumps(rec, indent=1))


asyncio.run(run())
