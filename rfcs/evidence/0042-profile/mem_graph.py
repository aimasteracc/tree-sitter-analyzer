"""Memory of today's in-process call graph state: python -I mem_graph.py <repo>"""
import gc
import sqlite3
import sys
import time
import tracemalloc

sys.dont_write_bytecode = True
sys.path.insert(0, r"C:\git-private\tsa-worktrees\rfc-1855")
repo = sys.argv[1]

from tree_sitter_analyzer.call_graph import CachedCallGraph  # noqa: E402
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool  # noqa: E402

tool = CodeGraphCallersTool(repo)
cache = tool._try_get_cache()
gc.collect()
tracemalloc.start()
base = tracemalloc.get_traced_memory()[0]
t0 = time.perf_counter()
g = CachedCallGraph(repo, cache=cache, fallback=False, persist=False)
g.build()
dt = time.perf_counter() - t0
gc.collect()
cur, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()

callers_edges = sum(len(v) for v in g._callers.values())
possible = sum(len(v) for v in g._possible_callers.values())
print("built", g._built, "build_s_under_tracemalloc", round(dt, 2))
print("functions(nodes)", len(g._functions), "certain_edges", callers_edges,
      "call_edges_list", len(g._call_edges), "possible_edges", possible)
print("retained_MB", round((cur - base) / 1e6, 1), "peak_MB", round((peak - base) / 1e6, 1))
edges = callers_edges + possible
nodes = len(g._functions)
print("retained_bytes_per_(node+edge)", round((cur - base) / max(1, nodes + edges)))
db = getattr(cache, "db_path", None)
print("db_path", db)
if db:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    for t in ("call_edges", "functions", "symbols"):
        try:
            print("rows", t, con.execute(f"select count(*) from {t}").fetchone()[0])
        except sqlite3.Error as e:
            print("rows", t, "n/a", e)
