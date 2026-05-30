# G1 — FTS5 BM25 Semantic Search Ranking

## Background

TSA stores every indexed symbol in two parallel structures:

| Table | Purpose |
|---|---|
| `ast_symbol_rows` | Relational store (name, kind, file_path, language, line, end_line). Used for exact-match lookups. |
| `ast_symbols_fts` | FTS5 virtual table, content=''. Populated in sync with `ast_symbol_rows` via shared `rowid`. |

The FTS5 table is already written on every index run (`_ast_cache_write.write_fts5_symbols`). The existing `_ast_cache_query.fts_search` query already emits `ORDER BY rank` — but `rank` is the raw FTS5 negative BM25 value and it is **never surfaced to the caller**. Every consumer (`CodeGraphQueryBackend._fts_definitions`, `_fts_fast_path.try_fts5_fast_path`, `ASTCache.search_symbols`) discards the score and returns an unranked flat list.

`execute_symbol_search` in `query_symbol_search.py` does not use FTS5 at all; it walks files with `asyncio.gather` in 50-file batches through the full `AnalysisEngine` pipeline — expensive for large repos.

## Problem

1. **Unranked results** — callers of `fts_search` receive symbols in arbitrary file-path order. The most relevant definition (e.g. `search` → `def search` in the core module) can appear behind hundreds of lower-signal hits.
2. **Score invisibility** — agents have no signal to distinguish a high-confidence BM25 hit from a marginal one.
3. **`execute_symbol_search` bypasses FTS5 entirely** — it pays the full engine cost even when the cache is warm and FTS5 can answer in sub-millisecond.

## Solution

Expose the FTS5 BM25 score through the full call chain so that:

1. `fts_search_ranked` returns `relevance_score` per result (a float in `[0.0, 1.0]` normalized from the raw BM25 value).
2. `CodeGraphQueryBackend.resolve_definitions` uses the ranked path when FTS5 is available.
3. `execute_symbol_search` checks FTS5 availability and falls back gracefully.
4. `codegraph_query` search/semantic steps emit `relevance_score` when the ranked path was used.

### SQL contract

FTS5 BM25 scores are **negative** (more negative = better match). The canonical ranked query is:

```sql
-- Prefix-aware BM25 ranked symbol search
SELECT
    r.name,
    r.kind,
    r.file_path   AS file,
    r.language,
    r.line,
    r.end_line,
    bm25(ast_symbols_fts) AS bm25_raw
FROM ast_symbols_fts f
JOIN ast_symbol_rows r ON f.rowid = r.id
WHERE ast_symbols_fts MATCH ?          -- FTS5 MATCH expression
  [AND r.language = ?]                 -- optional language filter
ORDER BY bm25_raw                      -- ascending = most relevant first
LIMIT ?;
```

The MATCH expression is built as:

```
"<token1>" OR "<token2>" ...
```

Each token is double-quoted (FTS5 phrase query) to prevent tokenizer splitting. For a two-character-minimum query `"foo"` this becomes `"foo"`.

BM25 normalization to `[0.0, 1.0]`:

```python
def _normalize_bm25(raw: float, worst: float) -> float:
    # raw and worst are both negative; worst is the least-negative value seen.
    # 0.0 = worst match, 1.0 = best match.
    if worst >= 0.0 or raw >= 0.0:
        return 0.0
    return min(1.0, raw / worst)
```

`worst` is the maximum (least-negative) `bm25_raw` in the result set. If all scores are identical, every result gets `relevance_score = 1.0`.

### Fallback contract

| Condition | Behavior |
|---|---|
| FTS5 unavailable (`cache._fts5_available` is falsy) | Use existing scatter search / linear search, `relevance_score` absent from response |
| Query shorter than 2 characters | Use existing scatter search, `relevance_score` absent |
| FTS5 returns 0 rows | Fall back to scatter search for `execute_symbol_search`, return empty for `fts_search_ranked` |
| SQLite `OperationalError` during FTS query | Log at DEBUG, return `[]`, caller falls back |

### API contract — new function `fts_search_ranked`

Location: `tree_sitter_analyzer/_ast_cache_query.py`

```python
def fts_search_ranked(
    conn: sqlite3.Connection,
    query: str,
    language: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """BM25-ranked FTS5 symbol search.

    Returns dicts with keys:
        name, kind, file, language, line, end_line, relevance_score

    relevance_score is a float in [0.0, 1.0].
    1.0 = best match; 0.0 = weakest match in this result set.
    Results are sorted descending by relevance_score (best first).

    Returns [] when query < 2 chars or FTS5 errors.
    """
```

### API contract — `ASTCache.fts_search_ranked`

Thin wrapper in `ast_cache.py` (mirrors existing `fts_search` wrapper):

```python
def fts_search_ranked(
    self,
    query: str,
    language: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if not self._fts5_available or len(query) < 2:
        return self._search_symbols_linear(query, language)
    from . import _ast_cache_query as _query
    return _query.fts_search_ranked(self._get_conn(), query, language, limit)
```

### API contract — MCP response shape

When the ranked path is taken, each symbol dict in `definitions` gains:

```json
{
  "name": "search",
  "kind": "function",
  "file": "core/search.py",
  "start_line": 42,
  "end_line": 67,
  "relevance_score": 0.93
}
```

When the unranked (fallback) path is taken, `relevance_score` is absent.

The `execute_symbol_search` response gains a top-level field:

```json
{
  "ranked": true,
  "ranking_method": "fts5_bm25"
}
```

or absent when fallback path was used.

### Performance target

- Ranked FTS5 query for 1 000-file project: < 5 ms (single SQLite read, no subprocess).
- Scatter search (fallback) path: unchanged.
- No new indexes required — FTS5 uses its own internal B-tree.

## Non-goals

- No schema migration required. `ast_symbols_fts` already exists and is populated.
- No change to TOON/JSON format selection (TOON default for MCP is locked — see CLAUDE.md).
- No vector/embedding search (that is `semantic()` step territory).
- No persistence of BM25 scores between queries.
