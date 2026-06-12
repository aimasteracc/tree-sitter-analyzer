# RFC-0016: Semantic symbol search (brute-force-first, sqlite-vec deferred)

- **Status**: rejected (data-driven, 2026-06-13 — embedding pilot at deployment
  scale scored 2/5 on the conceptual-gap gate; full chain: stemming #606,
  demotion #609, BM25-docstring #621 all measured first; pilot report
  `.recon/rfc0016-pilot-step2-embeddings.md`, decision thread #517)
- **Author(s)**: lead (autonomous), on behalf of dogfood evidence in #517
- **Created**: 2026-06-13
- **Last updated**: 2026-06-13
- **Tracking issue**: #517
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/mcp/tools/` (search facade: new `semantic` action)
  - `tree_sitter_analyzer/ast_cache.py`, `tree_sitter_analyzer/_ast_cache_schema.py`,
    `tree_sitter_analyzer/_ast_cache_write.py` (docstring/signature serialization,
    new `symbol_embeddings` table, schema version bump)
  - `tree_sitter_analyzer/cli_main.py` (new `--search-semantic` flag, CLI twin)
  - `tests/unit/mcp/`, `tests/integration/` (RED-first suites below)

> **Revision 2 note.** Round-1 adversarial review (two independent reviewers,
> all findings probe-backed) falsified three load-bearing claims of revision 1:
> the motivating query was NOT broken on HEAD, the specified embedding input
> does not exist in the cache schema, and the brute-force cost estimate was
> ~119× too high — which was the only thing making sqlite-vec look necessary
> for v1. This revision re-measures the motivation, re-scopes phase-1 to
> brute-force-over-BLOB, demotes sqlite-vec to a measured-need phase-2, and
> adds a retrieval-quality pilot as an acceptance PRECONDITION. Raw findings:
> PR #603 review thread.

## Summary

Add an opt-in semantic (vector) symbol search: embed each symbol's
signature + docstring at index time into a plain BLOB column in the existing
`.ast-cache` SQLite file, query via brute-force cosine (measured ~1 ms at
this repo's 44k symbols), expose `search action=semantic` (MCP) /
`--search-semantic` (CLI). No new daemon, no loadable extension in phase-1.
sqlite-vec/ANN indexing is explicitly deferred until a measured need exists.
A near-free lexical improvement (FTS5 porter stemming) ships first as its own
change and re-baselines the motivation.

## Motivation (re-measured 2026-06-13 on HEAD `1cc119b7`)

Revision 1 claimed `entry_points` came back **empty** for conceptual queries.
Re-measured on HEAD, that is **false** for the flagship query — and the real
failure is worse than emptiness:

- `nav action=context "how does the MCP server route a tool call to the
  right facade action"` → rank #1 = `legacy_to_facade` (facade_map.py:140).
  **Already works on BM25.** (#487 fixed more than #517 credited; the issue
  evidence was captured against a stale index.)
- `nav action=context "where is request dispatching handled"` → 6
  entry_points, **all confidently-irrelevant test helpers** that token-match
  "handled" (`test_symlink_handled`, `_collect_handled_errors`, …) under
  `verdict=INFO`.
- `search action=symbol "dispatch*"` → 9 production hits — the gap for this
  family is **stemming** ("dispatching" ≠ "dispatch" under FTS5's default
  tokenizer), not semantics.

So the measured problem is two-layered:

1. **Stemming gap** — closable for ~zero cost with FTS5's built-in porter
   tokenizer (one-line `tokenize=` change + reindex). This ships FIRST,
   independent of this RFC (tracking: see Acceptance precondition 0), and
   the semantic layer is then justified only by what stemming cannot close.
2. **Conceptual gap with confidently-wrong results** — "dispatching" never
   bridges to `handle_call_tool` lexically, and BM25 fills the void with
   plausible garbage instead of admitting low confidence. The honesty
   problem (INFO verdict over garbage) is in scope for this RFC: the
   semantic action must carry a score floor below which it says so.

Reproduction artifacts (Rule 11 — claims carry their commands):

```bash
# Query 1/2 baseline, run from repo root at 1cc119b7:
uv run python -c "from tree_sitter_analyzer.mcp.tools.context_tool import ...  # pinned in tests/integration/semantic/test_motivation_baseline.py"
```

The baseline lives as an executable test, not prose, so motivation drift is
caught mechanically (the round-1 failure mode).

## Detailed design

### Phase 0 (separate change, precondition): FTS5 porter stemming

One-line tokenizer change + reindex; re-run the motivating queries; record
which gaps remain. Not part of this RFC's implementation, but its outcome
re-baselines the pilot below.

### Prerequisite: docstring/signature must reach the cache

**Round-1 P1**: the specified embedding input
`"{kind} {qualified_name}({params}) -> {return_type}\n{docstring}"` is not
constructible from today's cache — `ast_index.symbols_json` carries neither
`docstring` nor `return_type` (0 of 1,885 rows), and `ast_symbol_rows` has
only name/kind/file/language/lines. The in-memory model HAS these fields
(`models/base.py:43`); the cache writer drops them.

This RFC therefore includes extending the `symbols_json` serialization with
`docstring` + `return_type` + `params` (schema version bump; existing repos
need a full reindex — stated cost, see Drawbacks). Quality reality check
(measured): only **33%** of production symbols have a substantive (≥10-word)
docstring; the flagship target `handle_call_tool` has **none**. The pilot
(below) exists precisely to test whether thin inputs still retrieve.

### Phase 1 storage: plain BLOB column, no extension

```sql
CREATE TABLE IF NOT EXISTS symbol_embeddings (
    file_path TEXT NOT NULL,          -- enables file-scoped delete (see below)
    symbol_key TEXT NOT NULL,         -- stable content key, NOT the rowid
    embedding BLOB NOT NULL,          -- float32[384] (int8 = exactly 1/4, phase-2 option)
    model_id TEXT NOT NULL,
    PRIMARY KEY (file_path, symbol_key)
);
CREATE INDEX IF NOT EXISTS idx_symbol_embeddings_file
    ON symbol_embeddings(file_path);
CREATE TABLE IF NOT EXISTS embedding_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- single row, unambiguous staleness
    model_id TEXT NOT NULL,
    dim INTEGER NOT NULL,
    built_at TEXT NOT NULL,
    symbols_embedded INTEGER NOT NULL
);
```

- **No rowid FK.** Round-1 (both reviewers independently): re-index DELETEs +
  re-inserts `ast_symbol_rows` with fresh AUTOINCREMENT ids
  (`_ast_cache_write.py:26-27`; ~4.3k ids already burned on this repo), so a
  rowid-keyed embedding table dangles after every file edit. Embeddings key
  on `(file_path, symbol_key)` and the dirty-file path does
  `DELETE FROM symbol_embeddings WHERE file_path = ?` **in the same
  transaction** as the symbol-row delete — the exact pattern
  `ast_symbol_activation` already uses (`_ast_cache_schema.py:96-113`,
  `_ast_cache_write.py:162-186`).
- Query path: load all embeddings (memory-mapped read), numpy brute-force
  cosine. **Measured**: 0.42 ms/query at 20k symbols, **1.03 ms at 44,169
  (this repo)**; ~25 ms extrapolated at 1M. No ANN needed at any plausible
  single-repo scale.
- Note vec0 (sqlite-vec ≤0.1.x) is ALSO a linear scan (no ANN; measured
  2.38 ms at 20k×384) — phase-2 buys persistence/SQL ergonomics, **not** an
  algorithmic speedup. Stated here so nobody weighs a phantom benefit.

### Embedding model (Open question 1 — panel decision required)

Candidates unchanged (A: ONNX MiniLM via `[semantic]` extra; B: endpoint
override), but round-1 measurements correct the table:

| | A: ONNX MiniLM (all-MiniLM-L6-v2) | B: endpoint (`TSA_EMBEDDING_ENDPOINT`) |
|---|---|---|
| Cold start | **606 ms measured** for `import onnxruntime` alone (1.26.0, M-series) — NOT ~100 ms | user-managed |
| Platform | onnxruntime 1.26 requires py≥3.11 (project supports 3.10 → pins 1.22); macOS wheels are 14.0+ arm64-only (no current Intel-mac wheel) | n/a |
| Tokenizer | MiniLM needs WordPiece — onnxruntime does NOT tokenize; requires the `tokenizers` wheel (another platform surface) or a vendored minimal WordPiece impl. **Must be specified before acceptance.** | server side |
| Model file | pip extras cannot ship the 23 MB model; either a separate model wheel (publishing commitment) or first-run download (**breaks "offline guaranteed" — pick one honestly**) | n/a |

A pinned support table (OS × arch × py → versions) is an acceptance
deliverable; unsupported combos (Windows-ARM, musllinux, Intel mac) get the
graceful-degrade verdict, never a crash.

### Index build

- `index action=build_semantic` / `--build-semantic-index`: batched,
  resumable via per-file progress (the `(file_path, symbol_key)` PK makes
  "which files are embedded under model X" a cheap query — `embedding_meta`
  alone cannot express this; round-1 P2).
- Incremental: dirty-file detection already exists
  (`incremental_sync.py:5-10`, mtime + SHA-256); the delta deletes + re-embeds
  only that file's rows (same-transaction rule above).
- **Concurrency (round-1 P2)**: embedding inference runs OUTSIDE DB
  transactions; writes land in batches of ≤200 rows per transaction with
  busy-retry (the watcher's 10 s `timeout` + the codebase's
  silently-pass-on-OperationalError convention means long write transactions
  can silently DROP watcher re-indexes — batch small, never hold the writer
  across inference). WAL checkpoint after build completion; `-wal` growth
  bounded by batch size, not build length.
- Never implicit; absence modes below.

### Query path

#### MCP surface (facade + action)

```python
{
  "action": "semantic",
  "query": "where is request dispatching handled",
  "limit": 10,
  "output_format": "toon",   # MCP default, locked
}
```

Response: standard ToolResponse envelope. In TOON mode the control surface
is the locked `TOON_CONTROL_SURFACE` allowlist — `results`,
`results_listed`, `total_candidates`, `truncated`, `next_step` live inside
`toon_content`, NOT at the top level (round-1 caught revision 1's example
contradicting RFC-0012; this revision states the rule instead of an
allowlist-violating example). JSON mode carries them top-level as usual.

- **Low-confidence honesty**: if the best cosine score < pinned floor, the
  response says "no confident semantic match" (`verdict=INFO` + explicit
  `low_confidence: true` in payload) instead of returning garbage — this is
  the half of the measured problem BM25 cannot express.
- **Hybrid lexical leg (round-1 P2 — revision 1's tiebreak was
  unimplementable)**: the candidate pool is the UNION of (a) cosine top
  `limit*4` and (b) FTS5 exact/prefix name hits for query tokens — so an
  exact-name symbol whose embedding is thin can never miss the pool. Ranking:
  exact-name-match group first (ordered by cosine desc, then qualified name
  asc as total order), then the rest by cosine desc. "Exact-name" :=
  case-insensitive token == symbol bare name. This is a total order — the
  exact-pin ordering tests are writable.

#### Error handling (absence modes — round-1 added the first row)

| Condition | Behavior |
|---|---|
| `sqlite3` built without extension support (`enable_load_extension` absent — notably python.org/system macOS builds) | phase-1 unaffected (no extension); phase-2 vec0 upgrade refuses with explicit message, stays on BLOB path |
| `[semantic]` extra not installed | `verdict=ERROR`, names the extra, install hint (#559 convention) |
| index absent / `embedding_meta.model_id` stale | `verdict=INFO` + build command |
| model/tokenizer load failure | `verdict=ERROR`; explicit `fallback:"bm25"` opt-in param, never silent fallback |

#### Concurrency / async

Reads: plain SQLite reads (WAL, thread-local connections as today). Note
phase-2 vec0 would need per-connection extension loading
(`ast_cache.py:107-114` creates lazy thread-local connections) — recorded
here so phase-2 doesn't trip on `no such module: vec0`.

## Three-Surface impact (CLI ↔ MCP parity)

| Surface | Addition |
|---|---|
| MCP | `search action=semantic`; `index action=build_semantic` |
| CLI | `--search-semantic <query>` (+ `--limit`); `--build-semantic-index` |
| Output | MCP defaults TOON (🔒 locked, unchanged); CLI defaults JSON (unchanged) |

(`nav action=context` rerank is deferred to phase-2 — revision 1 bundled it;
the pilot decides whether it earns its complexity.)

Parity test: the registry-driven parity suite gains the two new pairs; the
#519 facade-actions drift doc regenerates with the new action.

## Drawbacks

- **Full reindex on upgrade**: extending `symbols_json` bumps the schema —
  every existing repo re-indexes once. Stated, not hidden.
- **Index size (measured reference)**: this repo = 33.6k embeddable symbols
  (methods+functions+classes; imports/variables excluded) → **52-68 MB
  float32** on top of the existing 215 MB index.db (+24-32%). int8 is
  exactly ¼. Stays opt-in.
- **Thin inputs**: 33% substantive docstrings in production code (measured);
  the pilot gates acceptance on whether retrieval works anyway.
- **New optional dependency surface** (phase-1: onnxruntime + tokenizer
  path; phase-2 adds sqlite-vec): platform matrix above; sqlite-vec is
  pre-1.0, single-maintainer, with a ~16-month release gap (0.1.6 2024-11 →
  0.1.7a13 2026-03) — the BLOB path doubles as the permanent exit ramp.
- **Build latency**: unmeasured until the pilot (Rule 11: the pilot, not
  this RFC, produces the pinned number).

## Alternatives

- **A: FTS5 porter stemming only**: one line, closes the "dispatching"
  family. **Adopted as phase 0** — but cannot bridge true vocabulary gaps
  ("routing" → `handle_call_tool`), and cannot express low-confidence
  honesty. Insufficient alone IF the pilot shows semantic adds recall on
  stemmed baselines; the pilot decides.
- **B: external vector DB**: breaks the zero-daemon single-file moat.
  Rejected (unchanged).
- **C: sqlite-vec in v1**: rejected by measurement — vec0 is also a linear
  scan, brute-force BLOB is ~1 ms at real scale, and the extension drags the
  entire loadable-extension platform matrix into v1 for zero algorithmic
  gain. Deferred to phase-2 behind a measured trigger (e.g. >100 ms p95
  query at some future scale).
- **D: do nothing**: the confidently-wrong-results failure stays. Rejected,
  contingent on pilot.

## Prior art

Unchanged from revision 1 (codegraph, Sourcegraph hybrid lesson, sqlite-vec)
— with the correction that sqlite-vec's vec0 is brute-force in shipped
versions; its prior-art value is SQL ergonomics, not ANN.

## Pilot (acceptance precondition — runs BEFORE implementation lands)

1. Phase 0 stemming change + reindex; re-run both motivating queries; record.
2. Extend serialization on a branch; embed ~1k symbols (MiniLM via any local
   runner); run both motivating queries + 10 conceptual queries sampled from
   real agent transcripts; report top-5 hit rate against hand-labeled
   targets, on thin (signature-only) vs docstring-bearing symbols separately.
3. Measure: embed throughput (symbols/s), index bytes/symbol actual, query
   p95. These become the Rule-11 pinned invariants.
4. **Go/no-go**: if the pilot's top-5 hit rate on stemmed baseline fails to
   beat BM25 meaningfully, this RFC is rejected with the data attached —
   that outcome is explicitly acceptable and cheap (the pilot is ~1 day).

## Test plan (RED-first, post-pilot)

- Unit: schema migration (fresh + upgrade); file-scoped embedding delete in
  same transaction as symbol delete (exact-count pin after edit); absence
  modes (4 rows above); embedding input formatter (exact pins); hybrid
  union + total-order ranking (exact pins, including the thin-embedding
  exact-name case); low-confidence floor.
- Integration: build → query round-trip; incremental re-embed (only dirty
  file re-embedded — exact count); CLI↔MCP parity pair; TOON control-surface
  compliance via `handle_call_tool` boundary (not `execute` — the RFC-0012
  lesson).
- Motivation baseline test: the reproduction commands pinned as an
  executable test so motivation can never drift from reality again.
- Cost invariants: pilot numbers pinned in `test_output_cost_invariants.py`
  style with measurement date.

## Acceptance criteria

- [ ] Phase 0 stemming shipped separately; motivation re-baselined on it
- [ ] Pilot run, numbers attached, go decision recorded (panel)
- [ ] Docstring/return_type/params reach `symbols_json` (schema bump + reindex path)
- [ ] `search action=semantic` + `--search-semantic` behind `[semantic]` extra
- [ ] File-scoped embedding lifecycle (same-transaction delete) with exact-count tests
- [ ] All four absence modes verdict-tested
- [ ] Hybrid union ranking with total order, exact-pin tests
- [ ] Low-confidence floor behavior tested
- [ ] CLI↔MCP parity green; #519 facade-actions doc regenerated
- [ ] Cost invariants measured and pinned (bytes/symbol, symbols/s, query p95)
- [ ] Docs/CODEMAPS updated

## What this RFC does NOT do (deferred)

- sqlite-vec/ANN indexing (phase-2, behind a measured trigger; if adopted,
  the vec0 column MUST pin `distance_metric=cosine` — the default is L2,
  which would silently disagree with the phase-1 cosine semantics (Codex P2
  on #603 rev 1)).
- `nav action=context` semantic rerank (phase-2, pilot-gated).
- Body-content embeddings; cross-repo federation; replacing BM25 anywhere;
  auto-building on first connect. (Unchanged.)

## Outcome (2026-06-13, closing note)

The pilot ran exactly as specified and returned **NO-GO at deployment scale**:
semantic top-5 hit 2/5 of the conceptual-gap gate set at 37,876 symbols
(vs 4/5 on the 1k pilot corpus — the gap between the two IS the lesson:
**retrieval pilots need deployment-size distractor sets**, a 1k corpus
overstates recall by construction). Other recorded findings:

- The hybrid spec in this RFC is actively harmful as written (1/10): the
  exact-name leg promoted bare symbols named `format`/`search`/`a`. Any
  future revival must gate the lexical leg on identifier quality.
- Vectors added exactly +2 conceptual wins over post-#609 BM25 (union 7/10
  vs 5/10) — one short of the gate, against the full onnx/tokenizer/model-
  distribution platform surface the round-1 panel costed.
- The flagship miss (`handle_call_tool`: generic name + no docstring) is
  unreachable by ANY retrieval layer — that is a naming/documentation
  problem, not a search problem.
- Measured (Rule 11): 1,821 symbols/s embed throughput, 1,536 B/symbol,
  ~18 ms query p50 @ 38k — the engineering was viable; the recall wasn't.

What this rejection does NOT undo: phase 0 stemming (#606), the cascade
demotion fix (#609), constants indexing (#610/#612/#613/#615/#618), and
docstring serialization (#621) all shipped on their own merits during the
measurement chain.

## Open questions

1. Embedding model packaging: separate model wheel vs first-run download —
   which honesty trade-off does the panel prefer? (pip extras cannot bundle
   the model; "offline guaranteed" dies with download-on-first-run.)
2. Tokenizer: `tokenizers` wheel dependency vs vendored minimal WordPiece?
3. Pilot query set: which 10 transcript-sourced conceptual queries? (lead
   proposes sampling from the dogfood issue corpus #437-#449.)
4. int8 from day one (¼ size) or float32 first?
