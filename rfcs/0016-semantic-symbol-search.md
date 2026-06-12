# RFC-0016: Semantic symbol search via sqlite-vec in `.ast-cache`

- **Status**: draft
- **Author(s)**: lead (autonomous), on behalf of dogfood evidence in #517
- **Created**: 2026-06-13
- **Last updated**: 2026-06-13
- **Tracking issue**: #517
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/mcp/tools/` (search facade: new `semantic` action)
  - `tree_sitter_analyzer/core/ast_cache*` (new `symbol_embeddings` virtual table, schema version bump)
  - `tree_sitter_analyzer/cli_main.py` (new `--search-semantic` flag, CLI twin)
  - `tests/unit/mcp/`, `tests/integration/` (RED-first suites below)

## Summary

Add an opt-in semantic (vector) symbol search to the existing `.ast-cache`
SQLite file using the `sqlite-vec` extension: embed each symbol's
signature + docstring at index time, expose `search action=semantic`
(MCP) / `--search-semantic` (CLI), and optionally rerank `nav
action=context` candidates. No new daemon, no storage-engine change — the
"100% local, zero infra" story stays intact.

## Motivation

BM25-only search dead-ends on **conceptual** queries — measured, not
hypothetical (#517, #441 residual):

- `nav action=context "how does the MCP server route a tool call to the
  right facade action"` → candidates are honest post-#487, but
  `entry_points` is **empty**: `legacy_to_facade` / `handle_call_tool`
  exist, yet no lexical token reaches them.
- `search action=symbol` requires knowing a name fragment; "where is
  request dispatching handled" finds nothing.

Every "how does X work" question that shares no tokens with symbol names
forces the agent back into grep loops — the exact behavior TSA exists to
replace. This is the single biggest recall gap left in the dogfood resolution
program (#441 → #487 closed the stop-word half; this RFC addresses the
semantic half).

## Detailed design

### Storage (ast_cache schema)

New virtual table in the **same** `.ast-cache` SQLite database:

```sql
-- requires the sqlite-vec loadable extension
CREATE VIRTUAL TABLE IF NOT EXISTS symbol_embeddings USING vec0(
    symbol_id INTEGER PRIMARY KEY,   -- FK → existing symbols rowid
    embedding FLOAT[384]             -- model-dependent dim, pinned in meta
);
CREATE TABLE IF NOT EXISTS embedding_meta (
    model_id TEXT NOT NULL,          -- e.g. "minilm-l6-v2-onnx"
    dim INTEGER NOT NULL,
    built_at TEXT NOT NULL,
    symbols_embedded INTEGER NOT NULL
);
```

- Schema version bumps (existing ast_cache migration convention). Absence of
  the extension or the table MUST degrade gracefully: `semantic` action
  returns `verdict=INFO` + `next_step` pointing at the build command — never
  a crash, never a silent empty result (honesty convention, #537).
- Embedding input per symbol: `"{kind} {qualified_name}({params}) -> {return_type}\n{docstring}"`
  — signature line + docstring, capped at N tokens (pinned in implementation).

### Embedding model (Open question 1 — panel decision required)

Two candidate paths, both local-only:

| | A: bundled ONNX MiniLM (all-MiniLM-L6-v2, ~23 MB int8) | B: optional `ollama` / user-provided endpoint |
|---|---|---|
| Install | `pip install tree-sitter-analyzer[semantic]` pulls onnxruntime + model | zero new deps; user opts in via config |
| Cold start | ~100 ms session warmup | depends on user daemon |
| Licensing | Apache-2 model, redistributable | n/a |
| Offline | guaranteed | user-managed |

Default proposal: **A** as the `[semantic]` extra (keeps zero-config), with
B as a config override (`TSA_EMBEDDING_ENDPOINT`). Neither ships in the
default install — the base wheel stays lean.

### Index build

- `index action=build_semantic` (MCP) / `--build-semantic-index` (CLI):
  embeds all symbols, batched, resumable; writes `embedding_meta`.
- Incremental: the existing file-watcher/dirty-file path re-embeds only
  symbols whose source file changed (delta keyed off the existing symbols
  table).
- Build is **never** implicit: first call to `semantic` without an index
  returns the INFO verdict above. No surprise multi-minute writes.

### Query path

#### MCP surface (facade + action)

```python
# search facade — new action
{
  "action": "semantic",
  "query": "where is request dispatching handled",   # required
  "limit": 10,                                        # default 10, capped
  "output_format": "toon",                            # MCP default, locked
}
# → response (TOON_CONTROL_SURFACE-compliant):
{
  "verdict": "INFO",
  "results": [
    {"symbol": "handle_call_tool", "file": "...", "line": 123,
     "score": 0.78, "signature": "..."},
  ],
  "results_listed": 10, "total_candidates": 40, "truncated": true,
  "next_step": "nav action=context --query '<top symbol>'"
}
```

- KNN via `vec0` `MATCH` with `k = limit * 4` over-fetch, then a cheap
  lexical-overlap tiebreak so exact-name hits never rank below fuzzy ones
  (hybrid guard).
- `nav action=context` gains an optional `rerank: "semantic"` parameter
  (default off) that reorders its candidate pool by embedding similarity —
  directly targets the empty-`entry_points` failure.

#### Error handling

| Condition | Behavior |
|---|---|
| sqlite-vec extension not loadable | `verdict=ERROR`, message names the missing extra, `next_step` install hint (mirrors #559 Swift grammar honesty) |
| index absent / stale model_id | `verdict=INFO` + build command |
| query embeds to zero-vector / model error | `verdict=ERROR`, no fallback to silent BM25 (explicit `fallback:"bm25"` param if the agent wants it) |

#### Concurrency / async

Read path is a plain SQLite read (WAL, same as existing). Build path takes
the existing writer lock; embedding runs in a thread pool, DB writes batched
on the loop thread (same pattern as the current index build).

## Three-Surface impact (CLI ↔ MCP parity)

| Surface | Addition |
|---|---|
| MCP | `search action=semantic`; `index action=build_semantic`; `nav action=context` `rerank` param |
| CLI | `--search-semantic <query>` (+ `--limit`); `--build-semantic-index` |
| Output | MCP defaults TOON (🔒 locked, unchanged); CLI defaults JSON (unchanged) |

Parity test: the registry-driven parity suite gains the two new pairs.

## Drawbacks

- **Index size**: 384-dim float32 ≈ 1.5 KB/symbol → ~30 MB for a 20k-symbol
  repo (int8 quantization halves-to-quarters this). `.ast-cache` grows
  noticeably; must stay opt-in.
- **Build latency**: minutes-scale first build on large repos (CPU ONNX
  ~1-2k symbols/s expected; needs measurement per Rule 11 — a cost claim
  without an executable invariant is a belief).
- **New optional dependency surface**: onnxruntime wheels per-platform;
  sqlite-vec loadable-extension quirks (notably macOS SIP and Windows DLL
  paths) need CI coverage on all three OS axes.
- **Quality ceiling**: signature+docstring embeddings miss body semantics;
  undocumented symbols embed thin. Mitigation: include leading body comment
  line (deferred, see non-goals).

## Alternatives

- **A: FTS5 synonym/expansion layer** (no vectors): cheap, but cannot bridge
  "dispatching" → `handle_call_tool` without hand-curated synonyms; rejected
  as unmaintainable.
- **B: external vector DB (LanceDB/qdrant)**: better tooling, but breaks the
  zero-daemon/single-file story — the moat (#helixdb assessment: local
  zero-dependency IS the differentiator). Rejected.
- **C: embed at query time only (no index), brute-force cosine over
  signatures**: O(n) per query, ~50 ms at 20k symbols — actually viable as a
  fallback mode and as phase-1 ship vehicle; kept as an explicit option in
  the implementation plan (build the API first, swap brute-force → vec0
  index transparently).
- **D: do nothing**: the #441 residual stays; agents grep-loop on every
  conceptual query. Rejected by dogfood evidence.

## Prior art

- **codegraph**: `codegraph_context` does lexical + graph expansion, no
  vectors — same gap.
- **Sourcegraph Cody / embeddings era**: shipped then partially retreated
  from repo embeddings due to staleness cost — our incremental dirty-file
  re-embed addresses the staleness half; their lesson (hybrid lexical+vector
  beats pure vector) is adopted via the lexical tiebreak.
- **sqlite-vec** (asg017): the load-bearing dependency; vec0 virtual tables,
  used in production by several local-first tools.

## Test plan (RED-first)

- Unit: schema migration (version bump, fresh + upgrade); graceful-degrade
  verdicts (extension missing / index absent / stale model); embedding input
  formatter (exact pins); hybrid tiebreak ordering (exact-name beats fuzzy).
- Integration: build → query round-trip on a fixture repo; incremental
  re-embed after file edit (only dirty file re-embedded — exact count pin);
  CLI↔MCP parity pair tests.
- Dogfood acceptance (the motivating queries, pinned as e2e):
  - "how does the MCP server route a tool call to the right facade action"
    → `handle_call_tool` (or `legacy_to_facade`) in top-5.
  - "where is request dispatching handled" → non-empty, top-5 contains a
    routing symbol.
- Cost invariants (Rule 11): index bytes/symbol ≤ pinned ceiling; build
  throughput symbols/s ≥ pinned floor — measured, dated, in
  `test_output_cost_invariants.py` style.

## Acceptance criteria

- [ ] `search action=semantic` + `--search-semantic` ship behind the
      `[semantic]` extra, default-off
- [ ] Graceful-degrade verdicts for all three absence modes
- [ ] Incremental re-embed on file change (exact-count pinned test)
- [ ] Both motivating dogfood queries pass top-5 (e2e)
- [ ] CLI↔MCP parity test green
- [ ] Cost invariants measured and pinned (size, build throughput)
- [ ] Docs/CODEMAPS updated (+ facade-actions.md regenerates with the new
      action, #519 ratchet)

## What this RFC does NOT do (deferred)

- Body-content / comment embeddings (signature+docstring only).
- Cross-repo or multi-index federation.
- Replacing BM25 anywhere — `semantic` is additive; existing `symbol` /
  `content` actions and their defaults are untouched.
- Auto-building the index on first MCP connect.

## Open questions

1. Embedding model default: bundled ONNX MiniLM (`[semantic]` extra) vs
   ollama-endpoint-only? (proposal: ONNX default, endpoint override)
2. Ship phase-1 with brute-force cosine (Alternative C) to decouple API
   stabilization from sqlite-vec platform risk, swapping the index in
   phase-2?
3. Should `nav action=context` rerank become default-on once the index
   exists, or stay opt-in forever (token-cost neutrality argument)?
4. int8 quantization from day one, or float32 first + quantize later?
