"""Split the RFC-0040 review-gate time into sub-stages (exclusive ms per gated query).

Usage: prof_review.py COPY_ROOT STORED_JSON OUT_JSON [--limit N]
Asks each corpus row once (first touch on a warm tool) and wraps the gate internals.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
WT = Path(r"C:\git-private\tsa-worktrees\rfc-1855")
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "benchmarks" / "resident"))
import prof_callers as pc  # noqa: E402

from benchmarks.callers_gate.layout import QUERY_ARGS  # noqa: E402


def install_review_wrappers():
    import tree_sitter_analyzer.ast_cache as ac
    import tree_sitter_analyzer.mcp.tools.callers_absence as ab
    import tree_sitter_analyzer.mcp.tools.evidence_file_cache as efc
    import tree_sitter_analyzer.mcp.tools.reference_vocab as rv

    for name, label in (
        ("resolve_target", "R1.resolve_target"),
        ("excluded_definition", "R1.excluded_definition"),
        ("_declarations", "R2.declarations(sql)"),
        ("project_files", "R3.new_files_walk(project_files)"),
        ("_files_containing", "R4.files_containing(stat+read)"),
        ("_strip_comments_and_prose", "R5.strip_comments(regex)"),
        ("alias_reference_check", "R6.alias_reference_check"),
        ("without_header_names", "R6.header_names"),
        ("mask_import_bindings", "R6.mask_imports"),
        ("call_edge_lines", "R7.call_edge_lines(sql)"),
        ("_indexed_files", "R7.indexed_files(sql)"),
        ("stale_reference_files", "R8.stale_reference_files(stat)"),
        ("decorator_finding", "R9.decorator_finding"),
        ("supertype_outcome", "R9.supertype_outcome"),
        ("target_registrations", "R9.target_registrations"),
    ):
        pc.wrap(ab, name, "G.review." + label)
    pc.wrap(
        efc.FILE_CACHE.__class__, "read_stamped", "G.review.R4a.file_cache.read_stamped"
    )
    pc.wrap(rv.ReferenceVocabulary, "lacking", "G.review.R4b.vocab.lacking")
    pc.wrap(rv.ReferenceVocabulary, "lacks", "G.review.R4b.vocab.lacks")
    pc.wrap(ac.ASTCache, "get_conn", "Z.ast_cache.get_conn")


async def main(a):
    from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

    rows = json.loads(Path(a.stored).read_text(encoding="utf-8"))["rows"][: a.limit]
    tool = CodeGraphCallersTool(a.root)
    args = {k: v for k, v in QUERY_ARGS.items() if k != "action"}

    async def ask(row):
        return await tool.execute(
            {**args, "function_name": row["name"], "file_path": row["file"]}
        )

    await ask({"name": "__warm_up__", "file": rows[0]["file"]})
    pc.EXCL.clear()
    pc.CALLS.clear()
    pc._stat_count["n"] = 0
    gated = 0
    t0 = time.perf_counter()
    for row in rows:
        before = pc.CALLS.get("G.review._reference_scan", 0)
        await ask(row)
        gated += pc.CALLS.get("G.review._reference_scan", 0) > before
    total = time.perf_counter() - t0
    n = len(rows)
    return {
        "rows": n,
        "gated": gated,
        "mean_ms": round(total * 1000 / n, 2),
        "stat_calls_per_query": round(pc._stat_count["n"] / n, 1),
        "stages_ms_per_query": {
            k: round(v * 1000 / n, 2)
            for k, v in sorted(pc.EXCL.items(), key=lambda kv: -kv[1])
            if v * 1000 / n >= 0.05
        },
        "calls_per_query": {
            k: round(v / n, 1)
            for k, v in pc.CALLS.items()
            if k.startswith(("G.", "Z."))
        },
        "unwrapped_ms_per_query": round((total - sum(pc.EXCL.values())) * 1000 / n, 2),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root")
    p.add_argument("stored")
    p.add_argument("out")
    p.add_argument("--limit", type=int, default=100000)
    a = p.parse_args()
    pc.install_wrappers()
    install_review_wrappers()
    pc.count_stats()
    rec = asyncio.run(main(a))
    Path(a.out).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(json.dumps(rec, indent=1))
