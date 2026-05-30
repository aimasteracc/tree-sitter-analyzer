# G1 Implementation Tasks — FTS5 BM25 Ranking

Tasks follow RED → GREEN → VERIFY order. Each step is independently committable.

---

## Step 1 — RED: Write failing tests for `fts_search_ranked`

File: `tests/unit/mcp/test_fts5_bm25_ranking.py`

Tests to write (all should fail before implementation):

1. `test_fts_search_ranked_returns_relevance_score` — in-memory SQLite with FTS5, insert 3 symbols, assert each result dict has `relevance_score` key.
2. `test_fts_search_ranked_sorted_best_first` — insert symbols with clearly different BM25 signal (one exact name match vs partial); assert first result has higher `relevance_score` than last.
3. `test_fts_search_ranked_score_range` — all `relevance_score` values are in `[0.0, 1.0]`.
4. `test_fts_search_ranked_short_query_returns_empty` — query of 1 char returns `[]`.
5. `test_fts_search_ranked_no_fts5_returns_empty` — pass a plain `sqlite3.Connection` without FTS5 table; assert `OperationalError` is caught and returns `[]`.
6. `test_fts_search_ranked_language_filter` — insert Python + Go symbols; with `language="python"` only Python rows appear.
7. `test_fts_search_ranked_limit_respected` — insert 10 symbols, call with `limit=3`, assert `len(results) <= 3`.
8. `test_normalize_bm25_worst_is_best_match` — unit test for `_normalize_bm25(raw=-1.5, worst=-0.5)` → `1.0` (raw is more negative than worst so it's the best match).
9. `test_normalize_bm25_identical_scores` — all identical scores → all get `1.0`.
10. `test_ast_cache_fts_search_ranked_delegates` — mock `_ast_cache_query.fts_search_ranked`; assert `ASTCache.fts_search_ranked` delegates when FTS5 available.
11. `test_ast_cache_fts_search_ranked_falls_back_short_query` — `len(query) < 2` → calls `_search_symbols_linear` instead.

Run command to confirm RED: `uv run pytest tests/unit/mcp/test_fts5_bm25_ranking.py -x 2>&1 | head -20`

---

## Step 2 — GREEN: Implement `_normalize_bm25` + `fts_search_ranked` in `_ast_cache_query.py`

Changes to `tree_sitter_analyzer/_ast_cache_query.py`:

- Add `_normalize_bm25(raw: float, worst: float) -> float` pure function (no I/O, easy to unit-test).
- Add `fts_search_ranked(conn, query, language, limit)` that:
  1. Returns `[]` if `len(query) < 2`.
  2. Builds MATCH expression identical to existing `fts_search` but selects `bm25(ast_symbols_fts) AS bm25_raw`.
  3. Wraps the execute in `try/except sqlite3.OperationalError` → log DEBUG, return `[]`.
  4. Collects rows, computes `worst = max(row["bm25_raw"] for row in rows)` (the least-negative value).
  5. Calls `_normalize_bm25(row["bm25_raw"], worst)` per row.
  6. Returns list sorted descending by `relevance_score` (SQLite `ORDER BY bm25_raw` is ascending = best first, so the Python list is already in order; just attach the score).

SQL to use:
```sql
SELECT r.name, r.kind, r.file_path, r.language, r.line, r.end_line,
       bm25(ast_symbols_fts) AS bm25_raw
FROM ast_symbols_fts f
JOIN ast_symbol_rows r ON f.rowid = r.id
WHERE ast_symbols_fts MATCH ? {lang_clause}
ORDER BY bm25_raw
LIMIT ?
```

Run: `uv run pytest tests/unit/mcp/test_fts5_bm25_ranking.py -x`  — expect GREEN for steps 1–8.

---

## Step 3 — GREEN: Add `ASTCache.fts_search_ranked` wrapper

Changes to `tree_sitter_analyzer/ast_cache.py`:

- Add `fts_search_ranked(self, query, language=None, limit=100)` immediately after `fts_search`.
- Guard: if `not self._fts5_available or len(query) < 2` → return `self._search_symbols_linear(query, language)`.
- Otherwise delegate to `_query.fts_search_ranked(self._get_conn(), query, language, limit)`.

Run: `uv run pytest tests/unit/mcp/test_fts5_bm25_ranking.py -x` — all 11 tests GREEN.

---

## Step 4 — GREEN: Wire `execute_symbol_search` to FTS5 ranked path

Changes to `tree_sitter_analyzer/mcp/tools/query_symbol_search.py`:

- In `execute_symbol_search`, before calling `_scatter_symbol_search`, attempt the FTS5 fast path:
  1. If `len(symbol) >= 2` and `project_root` is set, try `ASTCache(str(root)).fts_search_ranked(symbol, language=language, limit=500)`.
  2. If results are non-empty, convert them to the existing match dict shape (add `relevance_score` field), call `_assemble_symbol_search_response` with an extra `ranked=True` kwarg.
  3. If FTS5 returns `[]` or raises, fall through to the existing `_scatter_symbol_search`.

- Add `_fts_symbol_to_match(row: dict, root: Path) -> dict` pure converter function.
- Update `_assemble_symbol_search_response` signature to accept optional `ranked: bool = False` and `ranking_method: str = ""` kwargs. When `ranked=True`, add those fields to the response envelope.

New tests to add to the test file (Step 4 RED before implementation):

12. `test_execute_symbol_search_uses_fts_when_available` — patch `ASTCache.fts_search_ranked` to return ranked fixture data; assert response has `ranked=True` and `ranking_method="fts5_bm25"`.
13. `test_execute_symbol_search_falls_back_when_fts_empty` — patch `ASTCache.fts_search_ranked` to return `[]`; assert scatter search is called.
14. `test_execute_symbol_search_skips_fts_for_short_query` — `symbol="a"` → FTS path skipped entirely.
15. `test_fts_symbol_to_match_shape` — unit test for the converter: input a `fts_search_ranked` row dict, assert output has `name, type, file, start_line, end_line, relevance_score`.

---

## Step 5 — VERIFY: Run full test suite

```bash
uv run pytest tests/unit/mcp/test_fts5_bm25_ranking.py -v
uv run pytest tests/unit/test_fts_fast_path.py -v
uv run pytest tests/unit/test_ast_cache.py -v
uv run pytest tests/ -x --timeout=60 -q
```

All existing tests must still pass. No regressions in `test_fts_fast_path`, `test_codegraph_query_backend`, `test_symbol_search_tool`.

---

## Step 6 — VERIFY: Change-impact check

```bash
uv run python -m tree_sitter_analyzer --change-impact --format json
```

Follow the `verification_command` in the output.

---

## Step 7 — VERIFY: Performance smoke test

Manual or scripted: index a real project (e.g. the TSA repo itself), then time:

```python
import time
from tree_sitter_analyzer.ast_cache import ASTCache
cache = ASTCache(".")
t0 = time.perf_counter()
results = cache.fts_search_ranked("execute", limit=50)
print(f"{(time.perf_counter()-t0)*1000:.1f}ms, {len(results)} results")
assert (time.perf_counter()-t0) < 0.2, "ranked search exceeded 200ms"
```

Expected: < 5 ms. If > 200 ms, investigate missing FTS5 index or uncommitted writes.
