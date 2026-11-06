# RFC-0043: Warm `nav callers` after the resident graph — measured cost and next steps

- **Status**: draft (Phase A #1927; Phase B and the §4 byte budget shipped with the parse memo on
  by default — see "Phase B and the byte budget: what shipped")
- **Author(s)**: @aimasteracc
- **Created**: 2026-11-06
- **Last updated**: 2026-11-06
- **Tracking issue**: #1855
- **Builds on**: RFC-0042 (resident call graph and check substrate; P1, P1b, P2a, P2b and P3-lite
  shipped in #1868, #1869, #1870, #1871, #1875, #1876), RFC-0040 (proof-carrying completeness),
  RFC-0030 (paths and generations are not freshness evidence)
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/mcp/tools/callers_decorators.py` (prototype: opt-in per-text decorator table memo)
  - `tests/unit/mcp/tools/test_callers_decorators_parse_memo.py`
  - `benchmarks/resident/corpus_replay.py`, `benchmarks/resident/copy_gate_index.py` (identity and latency harness)
  - follow-ups (planned, not in this PR): `callers_supertypes.py`, `callers_declaration_header.py`,
    `callers_absence.py` (`_is_accessor`), `call_graph_memo.py` (byte budget)

## Summary

Issue #1855 asks for the caller and callee adjacency to be loaded into memory at MCP server start,
because warm `nav callers` took 43–225 ms against a competitor's 2–5 ms. RFC-0042 already designed
that, and its first phases have shipped: the graph is loaded in a background thread after
`initialize`, the certified lease is renewed while the server is active, and the per-request probes
and the SQL edge-layer checks are memoized per certified snapshot.

This RFC re-measures `develop` (`cd512a45`) on all 7 gate repos and every stored callers-gate answer
(2,457 rows), and asks where the remaining warm time goes. The answer is clear:

- **The graph is not the cost.** Graph reads and edge resolution take 0.5–4.0 ms per query, which is
  0.5–2.3 % of warm time on every repo. Making them free would move no median by more than 4 ms.
- **Edge-only answers are already at the target.** Answers decided by the edge layer have a warm
  median of 6.3–16.9 ms (first touch of each target, in-process).
- **The RFC-0040 review gates are 70–93 % of warm time.** They decide 79 % of the corpus rows (1,932
  of 2,457). Inside them, two kinds of work dominate:
  1. **Re-parsing the declaring files on every request** (registering-decorator gate, supertype
     gate, declaration-header check): 25 ms (hono) to 122 ms (pydantic) per query, and 759 ms on zod,
     where one gate re-parses and walks a large TypeScript file for every query.
  2. **The stat-based source freshness floor** (reading or stat-ing every same-language file, the
     new-file walk, the freshness stats of the answer's files): 34–59 ms per query on this Windows
     host (about 100 µs per `stat`).

The recommendation is therefore not a second resident graph. It is:

1. **Phase A (prototype in this PR, opt-in):** memoize *parse-derived facts* of a source text by
   `(language, digest of the text)`. The text is still read through the stamp-validated file cache
   on every request, so a changed file has a new digest and is parsed again: freshness is
   unchanged, and the answer is a pure function of the same inputs. The prototype covers the
   tree-sitter decorator table (`TSA_RESIDENT_PARSE_MEMO=1`). On zod (ABBA, first touch of every
   row) it cuts the mean warm query from **818–850 ms to 144–152 ms**, the p90 from **3.1–3.4 s to
   330–343 ms** and the review-gated median from **122–156 ms to 87–93 ms**, with **0 differing
   rows** against the stored gate answers in every slot (see Measurements).
2. **Phase B:** extend the same memo to the supertype facts, the Python definition table, the
   declaration-header check and the accessor check (projected warm mean: rich 87 → ~57 ms,
   pydantic 296 → ~174 ms, gson 145 → ~71 ms, hono 94 → ~68 ms, zod → ~125 ms).
3. **Memory bounds:** put the resident call-graph memo under a byte budget with LRU eviction across
   roots, and skip the background preload when the estimated state exceeds it (§4).
4. **Trust gate:** every phase must replay all 2,457 stored callers-gate answers with the feature on
   and get 0 differing rows (`benchmarks/resident/corpus_replay.py`), on top of the callers gate.

Single-digit milliseconds for review-gated answers still needs RFC-0042 Phase 5 (a watcher-synced
freshness token) to remove the stat floor. This RFC does not claim parity with the competitor for
those answers in the default mode; it says where the remaining time is and removes the part that
can be removed without weakening any proof.

## Motivation

### What the issue assumed, and what is true on `develop`

| Issue #1855 premise | `develop` `cd512a45` |
|---|---|
| The graph loads lazily on the first query (3–8 s) | Loaded in the background after `initialize` (RFC-0042 P1, #1868); the lease is renewed while active (P1b, #1869) |
| Warm time is SQLite adjacency reads | Adjacency is in memory (`call_graph_memo`); graph read + edge resolution = 0.5–2.3 % of warm time |
| Needs invalidation on generation publish | Resident objects are keyed by the certified snapshot identity and graph input digest; a publish gives a new key (RFC-0042 §5) |
| Needs a SQLite fallback while loading | A request that finds nothing resident takes today's path (RFC-0042 §4.3) |

The remaining gap to the competitor is in the completeness proof, which the competitor does not
have. The design must cut that cost without touching the proof.

## Measurements

### Setup

- Code: `develop` `cd512a45` (package tree `ccb67d89`, the head of the latest callers-gate run).
- Indexes: the callers gate's own indexes for that tree (index keys `ec8722ff` rich, `fd1ac9d9`
  pydantic, `7d4d66d4` fastapi, `4e91fbf2` gson, `72354b7a` axios, `7df9c20a` hono, `cc2ff98b` zod).
  The gate cache was **never written**: each index was copied to a scratch root with
  `benchmarks/resident/copy_gate_index.py`, which rebinds the copy's generation selector and
  snapshot manifest to the new root (without the rebind, certification refuses the copy with
  `NO_EXACT_FULL_INDEX_MANIFEST` and every query recaptures the snapshot; that state costs about
  200 ms per query and is not representative).
- Answers: the stored head answers of that gate run (`results/ccb67d89…/<key>/20261106-134502/`),
  2,457 rows (each corpus target in bare and qualified form, full form, `include_bodies=false`,
  `limit=5000`).
- Harness: `benchmarks/resident/corpus_replay.py` — one in-process `CodeGraphCallersTool`, one
  untimed warm-up query, then every stored row once (**first touch** of each row on a warm tool)
  and once more (repeat). Every answer is projected with the gate's own `slim` and compared with
  the stored row. Stage buckets are the exclusive timers of `benchmarks/resident/prof_callers.py`;
  a finer split of the review gates used the same technique.
- Environment: Windows 11, CPython 3.12.9, `TSA_EVIDENCE_STORE=off`, `PYTHONHASHSEED=0` (as the
  gate servers). The host was shared with other work (CPU load about 66 %, 14 logical CPUs); `stat`
  measured 99.5 µs and `realpath` 234 µs (`statcost.py`), against 83 µs in RFC-0042. Absolute times
  are therefore somewhat high; the shares are the point.
- In-process numbers exclude the MCP layer (facade, TOON encoding, stdio), which RFC-0042 measured
  at about 7–22 ms and #1876 reduced.

### Answer identity of the measurement path

All 2,457 rows: **0 differing rows** in both rounds (4,914 answers) against the stored gate answers,
and 0 on rich with `TSA_RESIDENT=off`. The copied index and the in-process path therefore answer
exactly like the gate's MCP servers, so the latency numbers below describe the answers the gate
verifies.

### Warm latency by answer kind (round 1: first touch of every row)

| Repo | Rows (review-gated) | Edge-only median | Review-gated median / p90 | All median | Review gates, share of mean | Graph read + edge resolution |
|---|---:|---:|---:|---:|---:|---:|
| rich | 492 (325) | 8.0 ms | 86.0 / 190 ms | 60.7 ms | 64.5 of 77.4 ms (83 %) | 0.86 ms (1.1 %) |
| pydantic | 648 (527) | 16.9 ms | 132.4 / 484 ms | 107.7 ms | 145.3 of 207.0 ms (70 %) | 2.68 ms (1.3 %) |
| fastapi | 558 (483) | 9.5 ms | 118.6 / 238 ms | 112.9 ms | 111.7 of 144.5 ms (77 %) | 1.23 ms (0.9 %) |
| gson | 215 (168) | 6.3 ms | 51.8 / 180 ms | 42.3 ms | 87.5 of 97.3 ms (90 %) | 0.50 ms (0.5 %) |
| axios | 214 (140) | 8.0 ms | 40.6 / 132 ms | 33.4 ms | 38.3 of 52.3 ms (73 %) | 1.18 ms (2.3 %) |
| hono | 152 (128) | 8.9 ms | 99.2 / 192 ms | 87.2 ms | 77.6 of 102.0 ms (76 %) | 0.70 ms (0.7 %) |
| zod | 178 (161) | 15.0 ms | 124.1 / 3,133 ms | 110.7 ms | 681.6 of 735.5 ms (93 %) | 3.99 ms (0.5 %) |

- "Review gates" is the exclusive time of `assess_completeness`, `_reference_scan`,
  `_reference_lines` and `_is_accessor` (RFC-0040 checks 6–12). "Graph read + edge resolution" is
  the `B.*` and `E.*` buckets: the graph object from `call_graph_memo`, `callers_of`, labelling and
  the target rewrite.
- The SQL edge-layer checks (RFC-0040 checks 1–5, memoized per snapshot by RFC-0042 P2b) are
  1.6–6.3 ms per query, except pydantic (29.3 ms, of which `drop_external_producers` 24 ms; its
  per-request part reads the declaring file's source, RFC-0042 P2b note).
- Round 2 (the same rows again) is within noise of round 1 (for example rich 61.1 ms, pydantic
  97.9 ms, zod 97.6 ms median): the SQL memo is already warm after the first touch of a name, and
  the review-gate cost is paid again on every request.
- The stored gate timings for the same rows (7 repos answered concurrently, several servers per
  repo) have medians of 283–1,042 ms; they measure a saturated host, not warm latency.

### Inside the review gates (exclusive ms per query, all rows)

| Sub-stage | rich | pydantic | gson | hono | zod |
|---|---:|---:|---:|---:|---:|
| Registering-decorator gate (`decorator_finding`: parse + walk of the declaring file) | 12.0 | 34.6 | 9.0 | 15.6 | **708.7** |
| Supertype gate (`supertype_outcome`: parse of the class chain's files) | 14.4 | 75.9 | 61.4 | 1.1 | 1.9 |
| Declaration-header check (`without_header_names`) | 3.7 | 12.0 | 2.7 | 8.7 | 48.7 |
| **Parse-derived facts, subtotal** | **30.1** | **122.4** | **73.1** | **25.4** | **759.3** |
| Same-language files: vocabulary/stat check and reads (`_files_containing`, file cache) | 19.4 | 38.8 | 45.0 | 30.4 | 32.3 |
| New-file walk (`project_files`) | 11.7 | 6.7 | 10.2 | 11.9 | 7.6 |
| Freshness stats of the answer's files (`relation_source_evidence`) | 2.7 | 12.0 | 4.1 | 8.8 | 10.0 |
| **Stat/read floor, subtotal** | **33.8** | **57.5** | **59.3** | **51.1** | **49.9** |
| Comment/prose stripping and reference lines (`_strip_comments_and_prose`, `_reference_lines`, alias check) | 10.2 | 28.8 | 2.1 | 4.2 | 14.4 |
| Mean per query (this run) | 87.1 | 296.2 | 144.5 | 93.7 | 883.8 |
| `stat`/`lstat` calls per query | 532 | 938 | 597 | 904 | 1,093 |

(Separate run from the table above, with more timers, so the means differ; fastapi and axios were
not split.)

### Memory (per repo, `graph_size.py` and process RSS)

| Repo | Files | Symbols | Nodes | Certain / name-only edges | Graph state retained / build peak | Compact CSR estimate | Process RSS after all rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| rich | 213 | 3,509 | 1,810 | 2,954 / 3,312 | 6.6 / 17.1 MB | 0.3 MB | 128 MB |
| pydantic | 605 | 22,735 | 10,597 | 8,993 / 52,947 | 35.5 / 98.2 MB | 2.6 MB | 424 MB |
| fastapi | 1,191 | 10,922 | 5,763 | 4,840 / 34,618 | 15.6 / 40.0 MB | 1.6 MB | 201 MB |
| gson | 264 | 8,265 | 3,480 | 4,834 / 97,643 | 14.6 / 37.1 MB | 3.5 MB | 143 MB |
| axios | 275 | 2,849 | 1,106 | 2,647 / 26,307 | 11.4 / 27.9 MB | 1.0 MB | 153 MB |
| hono | 453 | 4,175 | 1,549 | 9,968 / 40,425 | 24.6 / 57.0 MB | 1.7 MB | 155 MB |
| zod | 521 | 6,586 | 2,407 | 13,214 / 67,958 | 35.0 / 82.0 MB | 2.8 MB | 300 MB |

- The graph state is what `call_graph_memo` already holds; 138–814 bytes per (node + edge).
- The compact estimate is the RFC-0042 §8 Phase 6 layout: two CSR arrays of 17 bytes per edge plus
  about 60 bytes per node. It would save 6–33 MB per repo, not time: the graph is already in memory.
- RSS (53 MB at start) also includes the certified snapshot's private in-memory copy of the index
  (bounded by the snapshot registry: 512 MB, 16 snapshots), the evidence file cache (≤ 256 MB), the
  reference vocabulary (≤ 64 MB) and the per-snapshot memo (≤ 4 snapshots × 8,192 entries, plus
  whole-snapshot tables). The graph memo is the only resident structure bounded by count
  (`_MAX_ROOTS = 4`) and not by bytes.

### Prototype result: per-text decorator table memo (ABBA)

One fresh process per slot, slots in A B B A order, each slot asking every stored row once (first
touch on a warm tool). A = default (memo off), B = `TSA_RESIDENT_PARSE_MEMO=1`.

| zod, 178 rows (161 review-gated) | A | B | B | A |
|---|---:|---:|---:|---:|
| Mean per query | 849.8 ms | 151.6 ms | 144.1 ms | 818.0 ms |
| Median / p90 | 122.0 / 3,409 ms | 79.8 / 343 ms | 74.3 / 330 ms | 101.2 / 3,122 ms |
| Review-gated median | 156.0 ms | 92.9 ms | 86.9 ms | 122.1 ms |
| `assess_completeness` exclusive, ms per query | 680.5 | 16.8 | 16.0 | 664.7 |
| Differing rows against the stored gate answers | 0 | 0 | 0 | 0 |

The other tree-sitter repos gain less, because their declaring files are smaller; the slot means
are noisy on this shared host, so the exclusive gate bucket is the clearer signal:

| Repo (rows) | Mean per query, A B B A | Review-gated median, A B B A | `assess_completeness` exclusive, A B B A | Differing rows |
|---|---|---|---|---:|
| hono (152) | 104.7 / 72.9 / 96.2 / 87.2 ms | 100.2 / 73.2 / 90.6 / 88.1 ms | 36.5 / 13.8 / 19.4 / 29.2 ms | 0 in every slot |
| axios (214) | 52.7 / 60.2 / 37.1 / 65.1 ms | 45.5 / 60.7 / 35.6 / 55.3 ms | 19.0 / 14.3 / 8.2 / 26.3 ms | 0 in every slot |
| gson (215) | 138.5 / 116.0 / 114.5 / 127.0 ms | 68.7 / 53.1 / 62.1 / 58.0 ms | 103.4 / 88.0 / 79.0 / 95.7 ms | 0 in every slot |

(`assess_completeness` is the exclusive time of the review gates not wrapped separately in
`prof_callers.py`; the registering-decorator gate is part of it. In gson most of it is the
supertype gate, which Phase B targets.) With the memo on, rich, fastapi and pydantic (Python; the
memo does not apply to the Python decorator path) answered all their rows identically as well:
0 differing rows of 492, 558 and 648. With the flag on, every one of the 2,457 stored rows was
therefore answered at least once (the tree-sitter repos twice) with 0 differences. (Their
latencies in that run, for example fastapi median 227 ms, were taken while the host was busier and
are not compared: the memo does not touch the Python path.)

The remaining zod cost is the parse-derived facts not yet memoized (the declaration-header check
re-parses the same file) and the stat floor.

## Detailed design

### Invariants (inherited from RFC-0042, restated for the new memos)

- **R0.** No memo constructs `complete`. `complete` still comes only from `callers_checks.prove()`
  over a ledger in which every check recorded `Checked(scope)` (RFC-0040).
- **R1.** No memo is freshness evidence. A parse memo is keyed by the *content* it was computed
  from, and the content is read live on every request through `evidence_file_cache.FILE_CACHE`,
  which re-stats the file and re-reads it when the stamp changes. If the file changed, the digest
  changed, and the memo is not consulted for the new text.
- **R2.** For the same index, source state and request, the response is identical with and without
  the memo. The memoized function is a pure function of `(text, language)`; its result is reused
  only for byte-identical text.

### 1. Phase A: per-text parse memo (prototype in this PR)

`callers_decorators._tree_sitter_decorators(text, line, language)` used to parse `text` with
tree-sitter and walk the whole tree for every call, keeping the decorators whose declaration header
spans `line`. The prototype splits it into:

```python
def _ts_decorator_table(text: str, language: str) -> tuple[tuple[str, int, int], ...] | None:
    """Every decorator attached to a declaration, in source order: (text, header start, header end)."""

def _tree_sitter_decorators(text, line, language):
    table = _ts_decorator_table(text, language)
    if table is None:
        return None          # unreadable: no grammar, or the parse raised
    return [Decorator(raw, None) for raw, start, end in table if start <= line <= end]
```

- The table is built by the same walk in the same order, and the line filter is the same
  comparison `_ts_header_holds` made, so the output for every line is the same list.
- With `TSA_RESIDENT_PARSE_MEMO=1` the table is kept in an LRU of 256 entries keyed by
  `(language, blake2b-128(text))`. Without the flag, nothing is kept (the default; the refactor alone
  changes no answer and no cost).
- An entry is a tuple of `(str, int, int)`, not a syntax tree: a few hundred bytes per file.
- The memo is process-local, thread-safe (one lock), and cleared by `clear_parse_memo()`.

**Why a digest and not a stat stamp.** A stamp says "probably unchanged"; the digest of the text
that was actually read says "this exact input". Reading the text is already done on every request
(the gate needs it), so the digest costs one hash of a file that is in memory (about 0.5 ms for a
300 KB file) and adds no trust assumption.

### 2. Phase B: the other parse-derived facts

Same pattern, one PR each, each with its own identity gate:

| Gate | Pure function to memoize by `(language, digest)` | Measured cost it removes |
|---|---|---|
| Supertype dispatch (`callers_supertypes`) | per-file facts: class headings, heritage values, member positions, bindings (`_facts`) — not the chain walk, which reads other files | pydantic 76 ms, gson 61 ms, rich 14 ms |
| Declaration header (`callers_declaration_header`) | the definition table of a file (Python: `_python_definitions`; others: the tree-sitter equivalent) | zod 49 ms, pydantic 12 ms, hono 9 ms |
| Python decorators (`_parsed_python`) | today one parse per text per *request* (`query_scope`); keep the derived definition and binding tables per digest instead of the AST | part of rich 12 ms, pydantic 35 ms |
| Accessor (`_is_accessor`) | the line split (`text.splitlines`), already per request | < 8 ms |

The comment/prose stripping depends on the target name (`string_code` keeps strings that mention
it), so only its name-independent part (token spans) could be memoized; it is 2–29 ms and is
deferred.

**Projected warm mean** after Phase B (the parse subtotal of the review table removed, everything
else unchanged): rich 87 → ~57 ms, pydantic 296 → ~174 ms, gson 145 → ~71 ms, hono 94 → ~68 ms,
zod 884 → ~125 ms. These are projections from exclusive buckets, not measurements; each Phase B PR
must measure its own ABBA.

### 3. The floor that remains: stat-based freshness

After Phase B, a review-gated answer still stats every same-language file (or proves through the
reference vocabulary that a file cannot contain the name, which also needs its stamp), walks the
project for new files, and stats the files the answer names: 34–59 ms per query here. These read
**source**, which is exactly what RFC-0040 checks 6–12 must prove is current. No index-derived
resident structure can replace them (RFC-0042 conclusion 3). The only design that removes the floor
without weakening the proof is RFC-0042 Phase 5: an opt-in watcher-synced token with a cookie sync
barrier, qualified by fault injection. This RFC keeps that phase as the route to single-digit
review-gated answers and does not duplicate its design.

### 4. Memory bounds and eviction

| Resident structure | Bound today | Proposal |
|---|---|---|
| Certified snapshot copies (`index_snapshot.REGISTRY`) | 512 MB charged, 16 snapshots, 35 s TTL | unchanged |
| Evidence file cache | 256 MB, 8 MB per file | unchanged |
| Reference vocabulary | 64 MB | unchanged |
| Per-snapshot memo (`snapshot_memo`) | 4 snapshots × 8,192 entries; whole-snapshot tables uncounted | count tables against a byte estimate (rows × measured row size) |
| Call-graph memo (`call_graph_memo`) | **4 roots, no byte bound** | byte budget `TSA_RESIDENT_GRAPH_MB` (default 256): LRU eviction across roots by last request; never evict the root of an in-flight request; the loader skips the preload (and a request builds without storing) when the estimate exceeds the budget |
| Parse memo (this RFC) | 256 entries of decorator tables | Phase B tables share one budget per process |

The graph-state estimate before a build is `(nodes + edges) × 820 bytes`, the worst measured ratio
(rich, 814); the persisted edge counts are known from the index before the build. Under the default
budget, all 7 repos fit at once (sum of retained state 143 MB). A repo whose estimate exceeds the
budget keeps today's first-use behaviour, which is always correct, only slower. Eviction is safe
because a miss rebuilds or adopts through the graph input digest (#1657, #1675), never from stale
data.

### 5. Invalidation (unchanged, restated)

- Generation publish, refresh, generation swap, watcher refresh: a new certified snapshot gets a new
  identity, so every snapshot-keyed resident object is never looked up again; the graph memo is
  keyed by the input digest (RFC-0042 §5).
- Source edit without refresh: the review gates read the new text; the parse memo sees a new digest
  and recomputes; the freshness checks report the edit as today.
- Memory pressure or the kill switch (`TSA_RESIDENT=off`, or no `TSA_RESIDENT_PARSE_MEMO`): every
  memo is bypassed and the request takes today's path.

### 6. Trust argument and the identity gate

The answer-identity check covers **every stored callers-gate answer**:

1. `copy_gate_index.py` copies each gate index of the code under test (read-only on the gate).
2. `corpus_replay.py --stored <gate answer file>` replays all rows of the repo with the feature on
   and compares the gate's `slim` projection of each answer with the stored row. Exit status 1 on
   any difference.
3. **Gate:** 0 differing rows on all 2,457 rows with the feature on, in two rounds (first touch and
   repeat), and 0 with it off (noise baseline). A row that becomes `complete` where the stored row
   is not is a release blocker.
4. The callers gate itself (`benchmarks/callers_gate`) runs on the PR as for any change to the
   callers path; with the memo flag off it must be identical by construction, and the replay above
   covers the flag-on path, which the gate servers do not set.

The identity holds by construction for Phase A and B (a pure function memoized on its full input);
the replay is the empirical check that the construction was implemented as claimed.

## Phase B and the byte budget: what shipped (2026-11-06)

### What changed

- **One memo for all parse-derived facts:** `tree_sitter_analyzer/resident/parse_facts.py`.
  - The key is `(kind, language, extra, blake2b-128 of the content)`.
  - Values are immutable tables. No syntax tree is kept.
  - Bounds: at most 4,096 entries and 64 MB (estimated), least recently used first out.
  - **On by default.** It is off with `TSA_RESIDENT_PARSE_MEMO=0` (`off` / `false` / `no` also
    work), or with the RFC-0042 kill switch `TSA_RESIDENT=off`.
  - The Phase A decorator table moved into it.
- **Facts memoized in this phase:**
  - the Python definition table: each definition's name, header lines and decorators, in
    `ast.walk` order. It serves both the registering-decorator gate and the declaration-header
    check;
  - the tree-sitter declaration table of the declaration-header check;
  - the Python class facts of the subtype class index (`callers_py_class_index`). These are
    keyed with the file's path, because every fact names it, and computed from the exact bytes
    read on that call. They now survive a renewed snapshot or a refresh, which rebuilds the
    class index.
- **Java subtype candidates: a substring pre-test.** In profiling, the Java supertype gate spent
  most of its time (gson: 8.0 s of 9.4 s over 72 calls) in `callers_java_subtypes._candidates`.
  That function runs a lazy `extends|implements … name` regex over every Java type file, for every
  name. The clause regex needs `name` as a whole word, so a text that does not contain the
  substring cannot match. `name in text` now runs first. The pre-test is exact and is not behind
  the switch.
- **Byte budget for `call_graph_memo`:** `TSA_RESIDENT_GRAPH_MB`, default 256. Each stored state is
  estimated as container entries counted two levels deep × 200 bytes. The measured range is
  54–155 bytes per entry on the 7 repos, so the estimate errs high: for example rich 17.0 MB
  estimated against 6.6 MB retained, and pydantic 106 against 35.5 MB, both measured with an
  earlier 400-byte constant. Least recently used roots are evicted until the count (4 roots) and
  the bytes are within bounds.
- **Not done:**
  - The accessor check stays as it is (< 8 ms per query).
  - The TypeScript and Python supertype readers already keep stamp-keyed parses (`_PARSED`,
    `callers_ts_source`), so they are unchanged.
  - The per-snapshot tables are not yet counted against a byte budget.

**Deviation from §4.** The root that was just stored is never evicted, even when its own estimate
exceeds the budget. Without this rule, a repository larger than the budget would rebuild its graph
on every query, which is a severe regression; with it, memory stays at about one graph, as before
the budget existed. The budget therefore bounds several roots resident at once. "Skip the
preload" is not needed. A request that holds a state keeps its reference, so an eviction never
affects an answer in progress.

### Identity (all 2,457 stored callers-gate answers)

Each repo was copied with `copy_gate_index.py`, then run in four slots, A B B A, with one fresh
process per slot:
- A: `TSA_RESIDENT_PARSE_MEMO=0`, one round;
- B: the new default (memo on), two rounds (first touch, then repeat).

**0 differing rows in every slot on all 7 repos.** That is 2 × 2,457 answers with the memo off and
4 × 2,457 with it on, all equal to the stored gate answers.

### Warm latency, round 1 (first touch of every row), mean / p90 per slot

Both sides include the Java pre-test. The host was shared (other agents running), so slot-to-slot
noise is ±20–30 % (rich and fastapi show it in both directions).

| Repo (rows) | A (memo off) | B (memo on) | B | A |
|---|---|---|---|---|
| rich (492) | 68.7 / 148 ms | 70.2 / 147 ms | 57.4 / 126 ms | 73.9 / 164 ms |
| pydantic (648) | 233.7 / 485 ms | 170.1 / 394 ms | 153.8 / 347 ms | 254.3 / 555 ms |
| fastapi (558) | 222.3 / 379 ms | 134.8 / 193 ms | 180.3 / 281 ms | 172.1 / 290 ms |
| gson (215) | 69.3 / 105 ms | 62.9 / 85 ms | 57.3 / 76 ms | 70.5 / 99 ms |
| axios (214) | 62.1 / 132 ms | 29.6 / 58 ms | 38.1 / 71 ms | 44.0 / 85 ms |
| hono (152) | 75.9 / 130 ms | 52.2 / 74 ms | 53.3 / 74 ms | 73.7 / 135 ms |
| zod (178) | 856.0 / 3,585 ms | 101.0 / 160 ms | 93.1 / 148 ms | 721.5 / 3,108 ms |

- **Against `develop` before this RFC** (the RFC-0043 measurement, same harness):
  - gson's mean was 127–139 ms. It is now 57–70 ms, with or without the memo, from the Java
    pre-test.
  - zod's mean was 818–850 ms; with Phase A it was 144–152 ms, and with Phase B it is 93–101 ms.
- **Review-gated medians, A → B:**
  - zod 107–129 → 66–67 ms
  - hono 75–81 → 55 ms
  - axios 37–51 → 30–38 ms
  - pydantic 151–155 → 88–90 ms
  - gson 47–52 → 40–41 ms
  - rich 83–86 → 64–79 ms
- **What remains** is mostly the stat-based freshness floor (§3) and the Python supertype walk
  over AST trees (`_owner_class`, `_scope_bindings`), which this phase did not change.

## Three-Surface impact (CLI ↔ MCP parity)

- No CLI flag, MCP action, parameter or payload change.
- `TSA_RESIDENT_PARSE_MEMO` and `TSA_RESIDENT_GRAPH_MB` are environment switches like
  `TSA_RESIDENT`. The parse memo helps any long-running process; a one-shot CLI run asks one
  question and gains nothing, but gives the same answer.

## Drawbacks

- More caches mean more places for a stale-answer bug. Mitigated by keying on content digests (not
  stamps or paths), keeping the live read, and the corpus-wide identity gate.
- The default mode still does not reach single-digit milliseconds for review-gated answers on
  Windows; Phase B leaves the stat floor (34–59 ms here).
- The prototype is opt-in, so users get nothing until a follow-up turns it on by default after the
  identity gate and the callers gate pass on the default.

## Alternatives

- **A. A second resident adjacency structure (the issue as written).** Rejected: the adjacency is
  resident already and costs 0.5–4 ms; the measured ceiling of the gain is under 4 ms per query.
- **B. Compact CSR graph (RFC-0042 Phase 6) now.** Deferred: it saves 6–33 MB per repo and no time;
  it stays conditional on a memory failure on a real repo, now enforced by the byte budget (§4).
- **C. Memoize the gates' verdicts per (snapshot, target).** Rejected: the verdicts depend on source
  state, so a hit would still need the full freshness proof, and first touches (the benchmark case)
  gain nothing.
- **D. Key parse memos by stat stamp instead of content digest.** Rejected: a stamp can stay equal
  across an edit on some filesystems (coarse mtime, same size); the digest of the text actually read
  cannot.
- **E. Skip the review gates when the graph is "warm".** Rejected: violates RFC-0040; every
  `complete` needs every check.
- **F. Parse every source file at server start.** Rejected as the default: it costs CPU and memory
  for files no query asks about; the per-digest memo pays only for files a gated query reads, and
  the loader could prefill it later if the measurements justify it.

## Prior art

- RFC-0042 P2b reused the external-producer parse for byte-identical text (keyed by the text's
  digest); this RFC generalizes that pattern to the other parse-derived gate inputs.
- rust-analyzer / Salsa: memoized pure queries keyed by input revision; here the revision of a file
  is the digest of the bytes read.
- The competitor in #1855 loads its graph at start and carries no completeness proof; we adopt its
  loading (RFC-0042 P1) and not its trust model.

## Test plan (RED-first)

- Unit (`tests/unit/mcp/tools/test_callers_decorators_parse_memo.py`, written first and RED):
  every line of a TypeScript and a Java fixture gives the same decorators with the memo off, on and
  on again; the default keeps no state; one parse per text when on; an edited text is parsed again;
  the same text in two languages is two entries; unreadable stays unreadable; the memo is bounded;
  a grammar fault is unreadable.
- Existing `tests/unit/mcp/tools/test_callers_decorators.py` passes unchanged.
- Identity: `corpus_replay.py` on all 7 gate repos with the flag on (0 differing rows), ABBA on the
  4 tree-sitter repos.
- Phase B PRs add the same three kinds of tests per memoized function, plus the byte-budget tests
  for §4 (eviction order, in-flight root kept, skip-preload above budget).

## Acceptance criteria

- [x] Measurements on all 7 gate repos and all 2,457 stored answers (this RFC)
- [x] Phase A prototype behind `TSA_RESIDENT_PARSE_MEMO=1`, default off; unit tests green; 0
      differing rows with the flag on over every stored answer
- [x] Phase A on by default: 0 differing rows over all 2,457 stored answers with the memo off
      and on (Phase B PR); the callers gate on the default is left to its owner
- [x] Phase B (one PR): Python definition table, tree-sitter declaration table, Python class facts
      of the subtype index, Java subtype substring pre-test; ABBA on all 7 repos, 0 differing rows.
      Not done: the accessor check (< 8 ms) and the AST walks of the Python supertype reader
- [x] §4 byte budget for `call_graph_memo` (`TSA_RESIDENT_GRAPH_MB`, default 256; the root just
      stored is always kept)
- [ ] §4 byte accounting for the per-snapshot tables
- [ ] RFC-0042 Phase 5 (watcher-synced freshness) qualified, for single-digit review-gated answers

## What this RFC does NOT do (deferred)

- It does not change any answer, reason, payload field or the RFC-0040 registry.
- It does not change the default behaviour (the prototype is opt-in).
- It does not redesign the watcher-synced freshness token; that is RFC-0042 Phase 5.
- It does not measure the MCP layer again (RFC-0042 P0/#1876 did).

## Open questions

1. Should Phase A turn on by default together with Phase B (one switch for all parse memos), or
   per gate as each lands?
2. Is 256 MB the right default for `TSA_RESIDENT_GRAPH_MB`, or should it scale with available RAM?
3. Should the loader prefill the parse memo for the files gated queries read most (declaring files
   of public classes), or stay purely on demand?
4. gson spends 29 ms per query in `FILE_CACHE.read_stamped`: is the Java declaring-file set larger
   than the cache's working set, or is a stamp re-read happening that the cache could avoid?
