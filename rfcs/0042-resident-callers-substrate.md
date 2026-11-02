# RFC-0042: Resident call graph and check substrate for `nav callers` / `callees`

- **Status**: draft (design only; no implementation in this PR)
- **Author(s)**: @aimasteracc
- **Created**: 2026-11-02
- **Last updated**: 2026-11-02
- **Tracking issue**: #1855
- **Builds on**: RFC-0030 (paths and generations are not freshness evidence), RFC-0032 (index writer
  ownership), RFC-0039 (incremental index certification), RFC-0040 (proof-carrying completeness)
- **Affected source paths** (planned; pin them — reviewers watch for drift here):
  - new `tree_sitter_analyzer/resident/` (`handle.py`, `substrate.py`, `loader.py`)
  - `tree_sitter_analyzer/mcp/server.py` (start the background loader after the loop starts)
  - `tree_sitter_analyzer/call_graph_warm.py`, `call_graph_memo.py` (load at start, not only after publish)
  - `tree_sitter_analyzer/mcp/tools/callers_tool.py` (`execute_batch`, `_execute_bound`: read through the handle)
  - `tree_sitter_analyzer/mcp/tools/callers_target_set.py`, `callers_reason_steps.py`,
    `callers_external_producers.py`, `callers_call_lines.py` (edge-layer checks read the substrate)
  - `tree_sitter_analyzer/mcp/tools/index_rebuild_signal.py`, `cache/query_cost.py`,
    `cache/generation_routing.py` (per-request probes become one handle check)
  - `tests/unit/resident/`, `tests/integration/test_resident_identity.py`
  - Not touched: the compact callers output of #1853 (`nav` answer shaping) — this RFC only changes
    how the same answer is computed.

## Summary

Issue #1855 asks for the caller and callee adjacency to be loaded into memory when the MCP server
starts, so that `nav action=callers` answers in single-digit milliseconds, as a competitor does
(2–5 ms). Profiling `develop` shows that **the adjacency is not the cost**. After the first query, a long-running server already keeps the graph in memory (`call_graph_memo`, #1657/#1708).
Reading the in-memory graph costs about 0.65 ms of a 57 ms warm answer (1.1%). The rest is spent on:

- per-request filesystem probes that re-derive the same facts every call (35%);
- the RFC-0040 review gates that scan source text (43%);
- the edge-layer completeness checks that query SQLite (16%);
- source freshness (4%).

On the first query of a fresh process, about 70% of the time goes to capturing and certifying the
index snapshot, and about 10–26% to loading the graph.

This RFC therefore proposes more than "load the graph early". It proposes a **resident answer
substrate**, one immutable object per certified snapshot, with three parts:

1. The existing call graph state (the same `CachedCallGraph` state that `call_graph_memo` holds
   today), loaded in a background thread right after server start, not first at use.
2. Edge-layer check inputs, served from memory instead of per-request SQL. They are first
   memoized results of the **same functions** over the **same immutable snapshot**, so the answers
   are byte-identical by construction (Phase 2). They are later precomputed eagerly, and that step
   is proven identical per key (Phase 3).
3. A `ResidentHandle` that replaces about ten per-request probes (index location, generation
   selector reads, live-index probe, certification ruling, cost tier) with one validated selector
   check plus one rebuild-flag query on a held connection.

Source freshness stays as strict as today. Every `complete` still requires the RFC-0040 proof over
checks that ran against the request's own snapshot and the current source state. A stale resident
object can never serve a request, because every resident object is keyed by the certified snapshot
identity, never by a path or generation number. A miss falls back to today's code path, which
gives the same answer more slowly.

Projected warm latency on `rich`, in the default stat-based freshness mode:

- answers that stop at the edge layer: median 31.7 ms → about 2–4 ms;
- answers that run the review gates: median 74 ms → about 15–25 ms. The floor is one stat per
  source file of the target's language, about 83 µs per stat on this Windows host.

Single-digit milliseconds for review-gated answers needs a watcher-synced freshness token
(Phase 5, opt-in, qualified separately). It is not promised for the default mode.

## Motivation

### Measured symptom (competitor benchmark, 2026-11-02; 7 repos)

| | TSA today | Competitor |
|---|---|---|
| Warm `nav callers` | 43–225 ms | 2–5 ms |
| First query of a fresh process | 3–8 s | 2–5 ms (graph loaded at server start) |
| Largest graph | pydantic, about 19k nodes / 46k edges | same repo |

TSA must stay the tool that never gives a wrong `complete`. The latency gap matters because agents
call `nav callers` in tight loops, for example when tracing blast radius or reviewing a PR. A 3–8 s
first call, or a 0.3 s call after 35 s of idle (see below), makes agents fall back to grep.

### Where the time goes today (profiled on `develop` `70c8e80c`)

**Setup.**
- Repo: `rich`, a fresh `git clone` of the dogfood copy at `9d8f9a3`, put in a scratch directory.
  It has 213 Python files, 3,509 symbols, 1,810 graph nodes, 2,954 certain edges and 3,312
  name-only edges. It was indexed once with the worktree code (24 s).
- Interpreter: the r15 dogfood venv (CPython 3.12.9), importing the worktree's `tree_sitter_analyzer`.
- Calls: in-process `CodeGraphCallersTool.execute` with `include_bodies=false`, which is the
  benchmark setting.
- Targets: the first 40 targets of the r10 `rich` sample, asked in both qualified and bare form.
  One untimed warm-up round, then 2 timed rounds, giving n = 160.
- Method: each pipeline stage was wrapped with a timer. A stage's time **excludes** the time of
  the wrapped stages it calls, so the buckets add up to the total; 0.48 ms per query was left
  unwrapped.
- cProfile was used only to explain the buckets, because it inflates the times.
- The scripts and raw results are in
  [`evidence/0042-profile/`](evidence/0042-profile/): `prof_callers.py`, `mem_graph.py`,
  `idle_probe.py`, `statcost.py`, and `rich-warm-n160.json` / `rich-first-{1,2,3}.json`. Their
  hard-coded paths are local. Phase 0 turns them into a portable harness under
  `benchmarks/resident/`.

**Warm, n = 160.** Mean 56.9 ms, median 46.2 ms, p90 about 120 ms, max 177 ms. Payload about 8 KB
JSON. 378 `stat`/`lstat` calls per query.

| Bucket | ms / query (mean) | Share | What it is |
|---|---:|---:|---|
| **Review gates (RFC-0040 checks 6–12, source text)** | **24.56** | **43.2%** | `_reference_scan` 15.5, `assess_completeness`/`_assess_absence` 7.5 (`project_files` walk for new files, declarations), `_reference_lines` 1.3, `_is_accessor` 0.3. They run only when the edge layer is clean (68 of 160 queries), so **about 58 ms per gated query**. |
| **Per-request infra probes** | **19.81** | **34.8%** | `is_index_rebuilding` ×2 6.0, `certification_timeouts` 3.8, `_certification_ruled_out` (`probe_live_index`) 3.5, `query_cost` tier label 4.2, `certified_index_read` enter 2.2. The common cause is `generation_routing.resolve_index_location`, called 6 times per query. Each call reads the generation selector `index-generations/active.json` through a shared-delete open (`_win_fileops._create`) and runs `_require_plain_path` checks, plus `realpath` calls (`_getfinalpathname`, about 306 µs here). RFC-0041's `query_scope` memo covers only part of this route. There are also 4 `sqlite3.connect` per query (rebuild flag, live-index probe, cost tier). |
| **Edge-layer checks (RFC-0040 checks 1–5, SQLite)** | **9.00** | **15.8%** | `drop_external_producers` 3.8, `_declaring_file_unresolved` 2.0 and `_declaring_file_excluded` 1.9 (both decode every classified call site in the declaring file: about 300 JSON rows per query through `_edge_from_row`), `unattributed_sites` 0.7, `narrow_to_target` 0.3, `read_unresolved_inbound` 0.1, the rest < 0.1. |
| Source freshness (`relation_source_evidence`) | 2.38 | 4.2% | Stats of the files the answer names, on a thread pool. |
| **Graph read and resolution (in memory)** | **0.65** | **1.1%** | Graph object and adoption from `call_graph_memo` 0.5, `callers_of`/`possible_callers_of`/labelling 0.1, target rewrite (#1759/#1798) < 0.05. |
| Serialization (`build_response`, output format) | 0.01 | ~0% | JSON. The MCP-level TOON encode and the stdio transport are outside this harness and are measured in Phase 0. |
| Unwrapped | 0.48 | 0.8% | |

By outcome class:

| Class | n | Median | Max |
|---|---:|---:|---:|
| Edge-layer only (answer is `incomplete`/`unknown` before the review gates) | 92 | 31.7 ms | 120 ms |
| Review-gated (edge layer clean; the gates decide `complete` or which reason) | 68 | 74.0 ms | 177 ms |

The 160 answers were 20 `complete`, 112 `incomplete` and 28 `unknown`.

**First query of a fresh process.** Three runs: total 0.79 / 1.02 / 1.10 s, plus 1.1–1.8 s of imports.

| Stage | ms |
|---|---:|
| `certified_index_read` enter: capture and certify the source manifest, then pin a private read-only in-memory copy of the index | 551 / 776 / 695 (70–76%) |
| Graph build or adopt (replay of the persisted edge resolution, #1675) | 94 / 100 / 286 |
| `query_cost` (first open of the index) | 59 / 49 / 46 |
| Everything else | < 40 |
| `stat`/`lstat` calls | 1,211 per first query |

The benchmark's 3–8 s on the larger repos is the same shape at larger scale. r15 measured hono:
4,156 lstat and 1,812 hashes in the first query.

**After idle.** The same query takes 50 ms warm, then **334 ms** after 40 s of idle, then 50 ms
again. The certified snapshot registry has a 35 s TTL (`index_snapshot._TTL_SECONDS`), so after
idle the next query captures again. The competitor has no such cliff.

**Conclusions the design must respect.**

1. Loading adjacency at start fixes the first-query graph cost, about 10–26% of the first query and
   about 1% of a warm one. On its own it cannot reach single-digit ms.
2. **The completeness checks, not the edge reads, dominate.** The review gates and the edge-layer
   checks are 59% of warm time. The per-request probes that guard them are another 35%.
3. The review gates depend on **source**, not on the index. No index-derived resident data can
   stand in for them without a source-freshness proof. A stat-based proof is O(files of the
   language) per gated query. Only a watcher-synced token can remove that floor.
4. Snapshot capture (70% of a first query) is the other cold cost. It recurs after every 35 s idle.

## Detailed design

### Invariant (overrides every other goal)

> **R0.** Resident data is used only for a request whose certified snapshot identity equals the
> identity the resident data was built from. In every other case the request takes today's code
> path. No resident path may construct `complete`. `complete` comes only from
> `callers_checks.prove()` over a ledger whose every check recorded `Checked(scope)` (RFC-0040).

> **R1.** Resident data is **index-derived** and is never freshness evidence (RFC-0030). Source
> freshness for an answer is established exactly as today, by the RFC-0040 checks 6 and 9 and the
> review gates, unless Phase 5's watcher-synced token is qualified and enabled.

> **R2.** For the same snapshot, source state and request, the response is byte-identical with
> and without resident data, excluding the timing and `query_cost` fields (see Verification).

### 1. Snapshot identity (the cache key)

The key is the existing certified snapshot key from #1774:
`(canonical_root, snapshot_id, index_fingerprint, source_generation)`
(`call_graph_snapshot_inputs.snapshot_key`), joined with the graph input digest (#1657).

- **The snapshot ID is random and never reused.** The private in-memory copy it names is
  immutable for its lifetime.
- **Refresh or edit never hits an old key.** A refresh, or an edit followed by a refresh, makes
  the next certified read capture a new copy with a new ID, so an old key is never looked up again.
- **The key deliberately excludes the generation number, the database path and `indexed_at`.**
  RFC-0030 says these are not freshness evidence. A content-identical republish is still a hit,
  through the graph digest, as in #1657.

### 2. `ResidentHandle`: one check instead of ten probes

Today every request does the following, and each step re-resolves the index location (realpath):

- `is_index_rebuilding` twice;
- `_certification_ruled_out` (`probe_live_index`);
- `certification_timeouts.should_skip`/`record`;
- `certified_index_read`;
- `query_cost`.

A `ResidentHandle` per project root caches these facts:

```python
@dataclass(frozen=True)
class ResidentHandle:
    root: str                        # canonical project root (realpath once)
    selector_stamp: FileStamp        # (file id, st_size, st_mtime_ns) of index-generations/active.json
    index_location: IndexLocation    # resolve_index_location() result for this selector_stamp
    live_index_exact: bool           # probe_live_index result for this selector_stamp
    cost_tier: str                   # query_cost tier for this selector_stamp
    substrate: "Substrate | None"    # None while loading or after invalidation
```

**Validation per request.** One `lstat` of the selector, about 0.08 ms here. If the stamp equals
the handle's stamp, the cached location, live-index ruling and cost tier are reused. Otherwise the
handle is rebuilt on today's code path, and the request is answered without the substrate.

- **Why this is correct.** The cached facts are pure functions of the selector's content and the
  generation directory it names. Publish replaces the selector atomically: `generation_store._replace`
  uses POSIX-semantics rename, also on Windows. The rename gives a new file ID, so the stamp check
  cannot miss a publish.
- **The rebuild signal is not cached.** `is_index_rebuilding` reads a `build_in_progress` row in
  the active database, which can change without a publish. The handle keeps one read-only
  connection to the active database, used only on the event-loop thread, and runs that one query
  per request (about 0.1 ms) instead of `connect` plus path resolution twice. The rebuild reply is
  unchanged.
- **Certification timeouts.** `certification_timeouts` keeps its own state and is consulted
  through the handle without the path re-resolution.
- **Cheapest first step.** Run the whole callers request inside one RFC-0041 `query_scope`. That
  removes the repeated `realpath` calls before any handle exists, and P2a starts with it.

### 3. `Substrate`: resident data per snapshot

The substrate is one immutable object per snapshot key, with three parts.

**3.1 Graph core (Phase 1).**
- This is exactly the `CachedCallGraph` state `call_graph_memo` already holds: `_callers`,
  `_callees`, `_possible_callers`, `_call_edges`, bindings, the function indexes and the hierarchy.
- It is unchanged code, reused as-is. The only change is **when** it is built: at server start and
  after every publish, not first at use (§4).
- Because the same object answers, `callers_of`/`possible_callers_of`/`label_graph_relations` are
  trivially byte-identical.

**3.2 Edge-layer check inputs (Phase 2: memoized; Phase 3: precomputed).**
These are the RFC-0040 checks 1–5. Today they are SQL reads over the snapshot's private
in-memory copy:

| Check (RFC-0040 #) | Today's reader | Resident form |
|---|---|---|
| `unresolved_inbound` (1) | `read_unresolved_inbound(cache, count_name, file, bound)` | `unresolved_by_name[count_name]`: rows in SQL order |
| `declaring_file` (2) | `_declaring_file_unresolved` / `_declaring_file_excluded` → `_classified_call_sites_in_file` (decodes every site in the file) | `classified_sites_by_file[file]`: decoded once per snapshot |
| `declaring_file` (2) narrowing | `narrow_to_target`, `drop_external_producers(cache, root, …)` | `external_producer_verdicts[(file, line, text)]`: memo |
| `name_only` (3) | `call_edge_lines(cache, count_name)` | `call_lines_by_name[count_name]` |
| `unattributed` (4) | `unattributed_sites(cache, target)` | `module_sites_by_name[count_name]` |
| `evidence_base` (5) | `cache.has_call_edges()` | `has_call_edges: bool` |
| (target set) | `sole_definition_file`, `name_bound_targets` | `definitions_by_name[name]` |

**Phase 2** wraps each reader in a per-snapshot memo: `memo[(snapshot_key, reader, args)] → result`.
The results are the outputs of today's functions over an immutable input. They are equal by
construction, so no reimplementation is needed and no semantics can drift. A memo miss calls
today's function. This alone removes repeated cost, for example batch queries, the bare and
qualified forms of one method, and agent re-asks. It does not speed up the first touch of a
new target.

**Phase 3** fills the same maps eagerly in the background, in one pass per table. The pass runs
the **same SQL text** with the same parameters' shape, groups rows in Python in **the order SQL
returns them**, and stores them as tuples, not dicts. Rows are decoded to dicts lazily on lookup,
with the same `_edge_from_row`. Readers then look up the map, and a missing key falls back to the
SQL reader. Order identity is the main risk (see Risks). Two rules handle it:
- every resident map is checked against the per-key SQL result, for every key, in the
  differential test;
- any reader whose SQL has no `ORDER BY` first gets an explicit `ORDER BY` equal to today's
  observed plan order, in a separate PR, proven identical on all stored answers before Phase 3
  uses it.

**3.3 Not in the substrate: the review gates (RFC-0040 checks 6–12).**
- These read **source**: `_reference_scan`, `project_files`, `_is_accessor`, decorators and
  `stale_reference_files`. They already have stamp-validated caches: `evidence_file_cache`,
  `reference_vocab` and `project_walk_cache`.
- This RFC does not move them into the substrate. It only removes redundant work inside one
  request (Phase 2b): each file is stat'ed at most once per request through a request-scoped stamp
  memo. Today one gated query makes about 9,840 `reference_vocab.lacks` calls and 378 stats on
  average, so the stats repeat.
- The source state is still read live, so freshness semantics are unchanged.
- Phase 5 adds the watcher-synced alternative.

### 4. Load strategy

The default is **background after start**.

**4.1 When the loader starts.**
- `server.main()` already calls `call_graph_warm.enable()`. After the MCP `initialize` handshake
  has been answered (the loader must never delay the handshake: clients time out), the loader
  thread starts **if and only if** a published index exists for the root. It never builds an index.

**4.2 What the loader does, at low priority.**
1. Take a certified snapshot lease. This is today's capture, which carries the 70% first-query cost.
2. Adopt or build the graph (`CachedCallGraph(persist=True)`). This uses the #1675 persisted
   replay when the digest matches.
3. Build the substrate (Phase 3).
4. Publish the `ResidentHandle` by a single reference assignment.

**4.3 Requests that arrive while loading.**
- Requests take today's path. The fallback is SQLite and the existing in-memory graph build.
- If the loader is already building the graph for the same digest, the request waits for it
  through the existing `call_graph_memo.claim` (#1708). This is today's behaviour, and it avoids
  two parallel builds competing for the GIL.
- The substrate is never waited for. A request that finds `substrate is None` reads SQL.

**4.4 Keeping the lease alive.**
- To remove the 35 s idle cliff, the loader re-leases (recaptures) the snapshot when the pinned
  snapshot is within 5 s of TTL and the server has had a request in the last N minutes (default 10).
- This is the same capture a request would do. Doing it in the background gives the same trust
  as today: an answer is certified against a capture at most one TTL old, plus its own re-checked
  files.
- After N idle minutes, the loader stops renewing, so an idle server stops spending CPU.

**4.5 Modes.** Set with `TSA_RESIDENT=off|first-use|background` (default `background`):
- `first-use` is today's lazy behaviour, plus the handle and memo.
- `off` disables everything in this RFC and is the kill switch.
- There is no eager-blocking mode. Blocking start for seconds to save one later query is never
  better for an MCP client.

**4.6 One-shot CLI processes** keep `first-use`. A CLI run asks one question, so preloading only
adds work.

### 5. Invalidation and consistency

| Event | What happens | Why no stale `complete` is possible |
|---|---|---|
| Seal/publish of a new generation (full or incremental refresh, any writer, RFC-0032 owner) | The selector stamp changes. The next request's handle check fails and the handle is rebuilt on today's path. The old substrate is dropped at once: old snapshot keys are never asked again, and we keep peak memory at one substrate plus the transient build, as `call_graph_memo.discard` does today. The loader builds the new substrate in the background. For a bounded refresh (#1714) the graph core uses the existing incremental update (#1723). The substrate maps are rebuilt in full in v1. | Resident data is looked up by snapshot key. The new request's lease has a new snapshot ID, so it **cannot** see old data, even if the selector check were wrong. The selector check is only a fast path for the infra facts. |
| Full rebuild in progress | The `build_in_progress` row is read on every request (§2). It is never cached, and the `cache_rebuilding` reply is unchanged. | The same query gives the same reply. |
| Source edit, no refresh yet | Nothing resident changes. The source-freshness checks (RFC-0040 #6, #9) and the review gates read the current source as today, so the answer is `stale`/`unknown` with the same reasons. | R1: resident data is never freshness evidence. |
| Watcher-driven refresh (`FileWatcherDaemon`, polling by default) | Same as publish. The watcher thread publishes, and `call_graph_warm` already schedules a background build for watcher refreshes (#1708). This RFC extends that task to build the substrate too. | Same as publish. |
| Lease expiry (35 s TTL) | The loader renews it (§4.4). If it does not, the request recaptures as today. | A renewed lease is a fresh capture, with the same certification as a request-time capture. |
| Process memory pressure | The substrate is dropped (`substrate=None`), and requests read SQL. | Falling back is always correct. |
| Writer crash mid-publish (RFC-0032 fencing) | No selector change means the old handle and substrate stay valid. A selector change means the handle is rebuilt. | The selector is renamed atomically, never half-written. |

**Belt and braces.**
- Every substrate lookup asserts `substrate.key == request.snapshot_key`. A mismatch is logged and
  counted, and the request falls back. It is never an answer.
- The debug mode `TSA_RESIDENT_VERIFY=1` computes each answer on both paths and returns the SQL
  path's answer. On a byte difference it logs the diff and disables the substrate for the process.
  Dogfood runs with this on.

### 6. Completeness checks against resident data (byte-identical)

- RFC-0040's ledger and `prove()` are untouched. The edge-layer check functions keep their
  signatures. Only their **data source** changes: the substrate map on a hit, SQL on a miss.
- Every check still records `Checked(target.scope)` or `NotChecked(code)` exactly as today. A
  resident read that fails (a missing key that should exist, or a decode error) falls back to SQL.
  It never records `NotChecked` on its own, because that would change answers.
- `completeness_checks` (`{"required": 12, "checked": 12}`) is therefore identical.

The identity argument has three steps:
1. Phase 1 serves the same graph object.
2. Phase 2 memoizes the same functions over immutable input.
3. Phase 3 changes the evaluation strategy and must be proven by the differential test for every
   key, plus the full stored-answer identity check (§8).

The review gates (§3.3) are not reimplemented.

### 7. Concurrency

The MCP server's threads:

- **Event-loop thread.** It runs tool `execute` coroutines. `CodeGraphCallersTool` runs
  synchronously inside its coroutine, so only one callers request runs at a time per server.
- **Watcher thread** (`FileWatcherDaemon`). It syncs and publishes under `cache._index_lock`.
- **`call_graph_warm` thread.** It is the background graph build after publish, and becomes the
  loader in this RFC.
- **Short-lived pools.** The absence reader pool (`callers_absence`) and the freshness pool
  (`relation_freshness`).

The rules:

1. **Immutable publish.** A `Substrate` and a `ResidentHandle` are fully built and frozen before
   publication. Publication is a single reference store under a module lock (`_RESIDENT[root] =
   handle`). A request reads the reference **once** at start and uses that object to the end, so
   it sees one consistent snapshot even if a publish happens mid-request.
2. **No shared SQLite connections.** The loader takes its own certified lease. Certified snapshot
   connections are private in-memory copies and are never passed across threads.
3. **No waiting on the substrate.** Requests never block on it. The only wait is the existing
   same-digest graph-build wait (#1708).
4. **GIL contention.** A background build competes for the GIL with the loop thread. The loader
   yields between chunks of `_CHUNK_ROWS` (8,192) rows, and runs with the cyclic GC paused for its
   own allocations, as #1657 does. The latency gate (§8) measures requests that run during a build.
5. **Generations.** At most one substrate per root, and at most `_MAX_ROOTS = 4` roots, the
   `call_graph_memo` bound. A new build for root R discards R's old substrate first.
6. **Shutdown.** Shutdown follows `call_graph_warm.shutdown()`: schedule no new build, wait up to
   `SHUTDOWN_SECONDS`, and run daemon threads.

### 8. Memory cost

**Measured on `rich`.** The retained `CachedCallGraph` state is 6.9 MB, with a 14.8 MB build peak
(tracemalloc). That is about 850 bytes per (node + edge), with 1,810 nodes and 6,266 certain plus
name-only edges. This is the state `call_graph_memo` already keeps in long-running servers today,
so Phase 1 adds no steady-state memory. It only moves the time it is paid.

**Estimate for the 7 repos.**
- Graph size is scaled from `rich` by symbol count (graph nodes + edges ≈ 2.3–2.9 × symbols:
  `rich` measured 2.3, pydantic 65k / 22.7k ≈ 2.9).
- The substrate (§3.2) is estimated at ≤ 0.5 × graph: raw tuples for call sites by name and file.

| Repo | Files | Symbols | Graph nodes+edges | Graph state, today's format | + substrate (Phase 3) | Ceiling (gate) |
|---|---:|---:|---:|---:|---:|---:|
| rich | 213 | 3,509 | 8.1k (measured) | 6.9 MB (measured) | ≤ 3.5 MB | 16 MB |
| axios | 275 | 2,849 | 6.6–8.3k | 5.6–7.0 MB | ≤ 3.5 MB | 16 MB |
| gson | 264 | 8,265 | 19–24k | 16–20 MB | ≤ 10 MB | 40 MB |
| fastapi | 1,191 | 10,922 | 25–32k | 21–27 MB | ≤ 14 MB | 56 MB |
| pydantic | 605 | 22,735 | 65k (19k / 46k) | about 55 MB | ≤ 28 MB | 110 MB |
| hono | 453 | 4,175 | 51.9k (1.5k / 50.4k, measured P0) | 11.5–24.7 MB (measured P0) | ≤ 12 MB | 50 MB |
| zod | 521 | 6,586 | 83.6k (2.4k / 81.2k, measured P0) | 15.5–35.0 MB (measured P0) | ≤ 18 MB | 70 MB |

- The ceiling is 2 × the graph state.
- File and symbol counts are taken from the r13 index replies. hono and zod were measured in
  Phase 0 with `benchmarks/resident/graph_size.py` on `develop` `c9277106` (nodes / edges, where
  edges = certain + name-only). The range is a fresh edge resolution against a replay of the
  persisted resolution (#1675); the build peak is 55–57 MB for hono and 79–82 MB for zod. Both
  TypeScript graphs are dominated by name-only edges (78–81 % of edges), so their bytes per
  (node + edge) are lower than `rich`'s (about 220–475 against 815). The other rows are
  estimates.

**Optional Phase 6: a compact graph.** Integer node IDs with CSR adjacency
(`array('i')` caller → callee and callee → caller, with line) cost 16–17 bytes per edge plus about
60 bytes per node with interned names. That is about 2 MB for pydantic, against about 55 MB. It
is a reimplementation of the `CallGraph` queries, so it is deferred. It only goes ahead if the
memory gate fails on a real user repo, and it must pass the same identity gates.

### 9. Projected latency and targets

These are projected from the measured buckets, not measured. The gates below decide.

| Answer class | Today (rich, median) | After Phases 1–3 (stat mode) | After Phase 5 (watch-synced, opt-in) |
|---|---:|---:|---:|
| First query after server start | 0.8–1.1 s (3–8 s on larger repos) | ≈ warm, if the loader finished; otherwise today's | same |
| After 35 s idle | 334 ms | ≈ warm (lease renewed) | same |
| Edge-layer-only answer | 31.7 ms | 2–4 ms (1 selector stat + 1 rebuild-flag query + freshness stats of the answer's files) | 1–3 ms |
| Review-gated answer | 74 ms | 15–25 ms (floor: 1 stat per same-language source file, rich 213 × 83 µs ≈ 18 ms) | 3–8 ms |

On Linux and macOS, `stat` costs about 1–3 µs, not 83 µs, so the stat-mode floor there is roughly
1 ms. Most of the Windows floor is per-syscall overhead, likely including antivirus filter
drivers on the measurement host.

### 10. Phase 5 (opt-in): watcher-synced source freshness

This is for single-digit review-gated answers on Windows.

**When it applies.** Only when the watcher runs the `watchdog` backend (OS-native events). The
default polling backend, with a 5 s interval, can never qualify.

**The token.** The watcher keeps a monotonic `source_epoch` and a dirty set of the paths it has
seen change since the last publish.

**The sync barrier.** A request may skip per-file stats only after a **sync barrier**. This is
the Watchman "cookie" technique:
1. Create a uniquely named cookie file under the watched root (in `.ast-cache/watch-cookies/`).
2. Wait until the watcher observes the cookie's create event.

Event queues are FIFO per watch, so every change made before the cookie has then been delivered.

**Falling back.** The request falls back to stat mode, with the same answer, when:
- the barrier times out (default 50 ms);
- the watcher reported an overflow or error since the last full sweep;
- the dirty set touches any file the answer depends on;
- the watcher started after the snapshot capture.

**Self-audit.** A background full-stat sweep compares the watcher's view with the stat truth
every M minutes. On any discrepancy it disables Phase 5 for the process and logs it.

**Gate.** Phase 5 ships only after a fault-injection qualification: edits and creates racing
queries, editors' atomic-rename saves, a forced buffer overflow, a network or virtual filesystem,
and a sleep/resume cycle. The gate requires 0 wrong `complete` across all of them.

## Three-Surface impact (CLI ↔ MCP parity)

- No CLI flag or MCP action/param changes, and no payload field changes.
- The answers are the same. The CLI keeps `first-use` because it is a one-shot process; that is
  intentional, since a one-shot process cannot benefit from preloading.
- `TSA_RESIDENT` and `TSA_RESIDENT_VERIFY` are environment switches, the same pattern as
  `TSA_GRAPH_WARM`.
- `index action=status` gains an additive `resident` block: `{state: loading|ready|off, built_ms,
  bytes_estimate, snapshot_age_s}`. It is an operability field and never part of a `nav` answer.

## Drawbacks

- **Extra work at startup.** A server that never asks `nav callers` still pays one background
  capture and one graph load. With `background`, this is CPU at idle, not latency.
  `TSA_RESIDENT=first-use` opts out.
- **Background lease renewal** (§4.4) spends periodic capture CPU while a session is active.
- **More state** means more invalidation code, which is the classic source of stale-answer bugs.
  Mitigated by R0, keying on the snapshot key, falling back to the slow path, and the verify mode.
- **The default mode does not reach single-digit ms for review-gated answers on Windows.** It
  reaches roughly 15–25 ms. The RFC says so instead of claiming parity.

## Alternatives

- **A. Load only the adjacency at start (the issue as written).**
  - Pros: smallest change.
  - Cons: the profile shows adjacency is about 1% of warm time and about 10–26% of the first
    query. Warm stays 30–75 ms.
  - Rejected as insufficient. It is kept as Phase 1.
- **B. Whole-answer memo keyed by (snapshot, request).**
  - Pros: about 0.1 ms on repeat questions.
  - Cons: the answer depends on source state, so a memo hit would need the same freshness proof
    anyway. It does not help distinct targets, which is the benchmark case.
  - Deferred. It could be added on top of Phase 5's epoch token.
- **C. Skip or relax the completeness checks when the graph is "warm".**
  - Rejected. It violates the trust-first rule. Every `complete` must carry the full RFC-0040 proof.
- **D. A TTL on source freshness**, for example "trust stats for 1 s".
  - Rejected. An edit inside the window gives a wrong `complete`, and agents edit and then query
    within milliseconds.
- **E. The NTFS USN journal or directory mtimes as the change signal.**
  - The USN journal needs volume handles, often with admin rights, and is Windows-only.
  - Directory mtime does not change on in-place writes.
  - `os.scandir` stamps from directory entries can lag for files with open handles on NTFS.
  - Rejected as the default. Open question 3 covers scandir as a stat-mode optimization.
- **F. Eager blocking load before answering `initialize`.**
  - Rejected. MCP clients time out, and background loading gives the same steady state.
- **G. A separate graph daemon process shared by CLI and MCP.**
  - Rejected for now. It needs IPC and process lifecycle, and duplicates RFC-0032 ownership.

## Prior art

- **The competitor benchmarked in #1855.** It loads its graph at server start and answers in
  2–5 ms. As far as the benchmark shows, it carries no completeness or freshness proof. We adopt
  its loading, not its trust model.
- **Watchman clock and cookie sync.** We adopt it for Phase 5's barrier.
- **rust-analyzer / Salsa.** Memoized pure queries over immutable inputs, keyed by revision. We
  adopt the idea for Phase 2, with the certified snapshot key as the revision.
- **SQLite's own page cache.** It is not enough here: the measured SQL cost is row decode and JSON
  parse (`_edge_from_row`, about 300 rows per query), not I/O.
- **TSA's own work.** #1657 (input-digest graph memo), #1675 (persisted resolution), #1708
  (post-publish warm), #1723 (incremental graph), #1774 (snapshot-keyed digest) and #1840/#1847
  (per-request direct-inbound memo). This RFC generalizes #1847's per-request memo to a
  per-snapshot one.

## Test plan (RED-first)

**Unit, `tests/unit/resident/`.**
- Handle and selector invalidation:
  - a changed selector stamp (new file ID, same size and mtime) invalidates the handle;
  - a `build_in_progress` row set without a publish still gives the rebuilding reply, because it
    is never cached;
  - `TSA_RESIDENT=off` never builds a handle.
- R0, parametrised over every substrate reader:
  - a substrate built on snapshot A is never consulted for a request leased on B, even with a
    forged equal selector stamp. The request falls back, and the answer equals the SQL answer.
- Memo purity:
  - each memoized reader's result is equal to a fresh call for the same snapshot;
  - a memo never survives a snapshot change.
- Phase 3 differential: for every key in the fixture projects, the resident map's rows equal the
  per-key SQL rows, **in order**.

**Integration, `tests/integration/test_resident_identity.py`, on real indexed fixtures in both modes.**
- Bare and qualified queries are identical with and without resident data, including
  `completeness_checks`.
- An edit without a refresh gives the same `stale`/`unknown` answer on both paths.
- A refresh or publish during a request: the answer is from the old snapshot or the new one,
  never a mix.
- A watcher-driven publish: after `call_graph_warm` finishes, the substrate key equals the new
  snapshot key.
- Every RFC-0040 RED scenario (forgetful gate, unreadable siblings, no root, rebuild reply) gives
  the same non-`complete` answer with resident data on.

**RED evidence.** The handle-invalidation and R0 tests are written first against a stub substrate.
They must fail on a naive "global dict keyed by root" implementation.

## Verification plan (gates; each phase PR cites them)

**V1. Answer identity over every stored dogfood answer.**
- Rerun the r15 identity battery with `TSA_RESIDENT=off` and with `background` after the loader is
  ready, on fresh `git clone --local` copies. The battery is `tools/identity.py`: 64 files and
  2,959 rows over rich, pydantic, fastapi, axios, gson, hono and zod, covering batteries, sweeps,
  scope, GT and UQL.
- Fields excluded: the timing and process fields already in `identity.py`'s `SKIP` list, plus the
  `query_cost` cost fields.
- **Gate:** 0 differing rows that are not differing on `off` vs `off` (noise baseline). Answers
  that move from `complete` to non-`complete` count as differences. **Any row that becomes
  `complete` while the `off` row is not complete is a release blocker.**
- Also run once with `TSA_RESIDENT_VERIFY=1`, with 0 shadow diffs logged.

**V2. Latency ABBA.**
- Interleave A (`off`) and B (`background`) as A B B A pairs, using the r15 `lat1840.py` layout,
  on hono and pydantic plus one Java repo (gson). Use fresh indexes per slot and stop below 2 GB
  free disk.
- Measures:
  - first query after start, with the loader finished and while it is still loading;
  - warm median, p90 and max, with qualified and bare queries split by edge-only or review-gated;
  - the query after 40 s idle;
  - queries that run during a background rebuild.
- **Gates for Phases 1–3:**
  - the warm edge-only median ≤ 5 ms on every repo;
  - the warm review-gated median ≤ 35% of A's;
  - the first query after load ≤ 2 × the warm median;
  - the after-idle query ≤ 2 × the warm median;
  - no slot's B median worse than A's by more than noise (5%).
- Suspended runs are dropped, using the wall/monotonic check of `lat14`.

**V3. Memory ceiling.**
- RSS and tracemalloc of the resident objects after load, at peak during a rebuild, and after
  10 publish cycles (leak check), on all 7 repos.
- **Gate:**
  - steady state ≤ the §8 ceiling;
  - rebuild peak ≤ steady state + one graph build peak;
  - growth after 10 cycles ≤ 5%.

**V4. Trust regression.**
- Run the full RFC-0040 proof tests and the wrong-`complete` audit (`audit_complete.py`) on all
  r15 answers with resident data on.
- **Gate:** 0 wrong `complete`.

## Phasing (small PRs, each independently revertible)

| Phase | PR | Content | Gate |
|---|---|---|---|
| P0 | `bench(resident)` | Commit the profiling harness (`benchmarks/resident/`). Measure hono and zod sizes and the MCP-level TOON and transport share. No product change. | Numbers reproduce ±10% |
| P1 | `perf(mcp): load call graph at server start` | The loader thread after `initialize`: certified lease, then the graph via the existing `CachedCallGraph(persist=True)`, then `call_graph_memo`. `TSA_RESIDENT` switch. | V1, V2 first-query, V3 |
| P1b | `perf(mcp): renew the certified lease while active` | §4.4 | V2 after-idle, V4 |
| P2a | `perf(callers): resident handle` | §2: the handle replaces per-request probes | V1, V2 (−15 to −20 ms expected) |
| P2b | `perf(callers): per-snapshot memo of edge-layer readers` | §3.2 memo; request-scoped stamp memo for the review gates | V1, V2, V4 |
| P3-pre | `refactor(cache): explicit ORDER BY on the readers the substrate mirrors` | Behaviour-preserving; identity-proven | V1 |
| P3 | `perf(callers): precomputed edge-layer substrate` | §3.2 eager maps, built by the loader and after publish, `TSA_RESIDENT_VERIFY` | V1 (with VERIFY), V2, V3, V4, differential test |
| P4 | `perf(nav): callees through the same substrate` | `nav callees` and `caller_tree` read the handle and graph core | V1 (callees rows), V2 |
| P5 | `feat(watch): watcher-synced freshness token` (opt-in) | §10, separate qualification | Fault-injection gate, V1, V4 |
| P6 | (only if V3 fails on a real repo) compact CSR graph | §8 optional | All gates |

- Each PR updates this RFC's acceptance checkboxes and the `CHANGELOG`.
- Each PR lands on its own branch to `develop`.
- No phase changes the payload schema.
- P1–P3 do not touch the `nav` output-shaping code of #1853.

## Risks

1. **Stale resident data producing a wrong `complete`.** This is the overriding risk.
   - Mitigations: key on the certified snapshot ID, never a path or generation (R0); the selector
     check is only a fast path for infra facts; fall back on any doubt; keep resident data out of
     the freshness evidence (R1); verify mode in dogfood; V1 and V4 gates.
2. **Order drift between SQL and resident maps (Phase 3).** The byte identity of lists such as
   `unresolved_sites` and `name_only` depends on row order.
   - Mitigations: P3-pre explicit `ORDER BY`, the per-key differential test, V1.
3. **GIL contention from background builds** raising request latency, the #1708 finding.
   - Mitigations: chunked yields; the V2 "during rebuild" measure; `first-use` mode.
4. **Memory on large monorepos** beyond the 7 benchmark repos.
   - Mitigations: the `_MAX_ROOTS` bound, dropping under pressure, the `first-use` mode and P6
     compaction.
5. **Lease renewal CPU** on laptops.
   - Mitigation: renew only while there was a request in the last N minutes.
6. **Phase 5 watcher gaps**: overflow, network filesystems, sleep/resume, editor save patterns.
   - Mitigations: cookie barrier, self-audit, opt-in only, fault-injection gate.
7. **The benchmark target is only partly met by default.** Review-gated answers on Windows stay
   at roughly 15–25 ms in stat mode.
   - Mitigation: report the class split honestly in release notes; Phase 5 for users who opt in.

## Acceptance criteria

- [x] P0 harness committed; hono and zod sizes measured; the §8 table completed
- [ ] P1: first query after start ≈ warm (V2); V1 0 diffs; V3 within the ceiling
  - P1 PR: V1 0 differing rows (rich 402, hono 101, zod 98; noise baseline 0). V3: server RSS
    after the first query is unchanged (rich 99.4 → 98.5 MB, hono 170.7 → 162.8 MB). V2 first
    query, MCP ABBA medians off → on: rich 1,278 → 199 ms, hono 2,681 → 346 ms. That is
    4.8 × and 2.7 × the warm median, not yet ≤ 2 ×. What remains is the first `query_cost` index
    open (40–70 ms, P2a's handle) and the `nav` facade construction on the event loop (about
    0.14 s on rich; no phase covers it yet).
- [x] P1b: after-idle query ≤ 2 × warm
  - P1b PR: MCP ABBA medians after 40 s idle, off → on: rich 342 → 56 ms (warm after idle 48 ms),
    hono 884 → 147 ms (162 ms). A renewal keeps the same snapshot ID when nothing changed. V1 on
    vs off is 0 differing rows on rich, hono and zod (601 rows).
- [x] P2a/P2b: V1 0 diffs; V2 shows the expected drop; V4 0 wrong `complete`
  - P2a PR (#1870): one `ResidentHandle` per root, kept only for a sealed published generation
    (plain file, no write bit). A request validates it with two `lstat` calls (selector and
    database stamps) and reads the index location, the live-index probe, the cost tier and the
    certified-lease reuse check through it; a warm request resolves the index location 0 times
    and opens no probe connection. The rebuild flag is still read on every request. Two
    deviations from §2, both measured: the read-only connection for the rebuild flag lives for
    one request, not across requests (a held connection pins a retired generation on Windows,
    #1631), at about 1.3 ms per request here; and the "cheapest first step", one RFC-0041
    `query_scope` per request, was not adopted: on rich (ABBA, n = 160 per slot) it made the
    review-gated median 97.5–104.6 ms against 86.2–87.7 ms without it. V2 in-process warm ABBA
    medians, off → on: rich edge-only 52.1 → 26.6 ms, review-gated 114.6 → 91.1 ms; hono
    edge-only 236 → 214 ms, review-gated 304 → 272 ms. V1: see the PR (0 differing questions).
  - P2b PR (#1871, stacked on #1870): `resident/snapshot_memo.py` memoizes the §3.2 readers by
    the certified snapshot key (`graph_input_identity`): `has_call_edges`, the declaring-file
    classified sites (unresolved and excluded), `unresolved_caller_sites` /
    `count_unresolved_callers`, `symbol_definitions`, `symbol_declaring_files`,
    `query_callers` (the unattributed check), `call_edge_lines`, and the index facts of the
    external-producer check (languages, import rows, Python paths, indexed paths). A hit returns
    a deep copy; `None`, exceptions and reads that end past the owner's deadline are not stored
    (some readers turn a deadline interrupt into `[]`). A new snapshot of a root drops the old
    memo; at most 4 snapshots and 8,192 entries each (measured 1.7 KB per entry on rich).
    **Correction to the §3.2 table:** the `external_producer_verdicts` row cannot be keyed by
    the snapshot, because the verdict reads the declaring file's source (`_literal_container`,
    `_rebound`, `_named_elsewhere`). Only its index inputs are snapshot-memoized; its parse of
    the declaring file is reused only for byte-identical text (keyed by the text's digest),
    and the text is read on every request. The request-scoped stamp memo for the review gates
    was not added (see P2a: the scope machinery is slower for one name). V2 in-process warm
    ABBA medians, off → on, P2a + P2b: rich edge-only 52.3 → 11.2 ms, review-gated
    113.3 → 77.8 ms; hono edge-only 177 → 8.1 ms, review-gated 222 → 64.8 ms. These timed
    rounds repeat questions; a first touch of a new target gains less (rich edge-only
    33 → 7.4 ms, review-gated 100 → 77 ms; hono 179 → 136 ms and 235 → 107 ms). MCP ABBA,
    `develop` (P1b on) → P2a + P2b: warm median rich 87 → 21 ms, hono 262 → 74 ms; after 40 s
    idle rich 97 → 28 ms, hono 354 → 123 ms. The RFC targets (edge-only 2–4 ms, review-gated
    15–25 ms) are **not met**: what remains on an edge-only answer is the MCP layer
    (about 7–22 ms), the certified-lease enter, the rebuild-flag connection and the freshness
    stats of the answer's files; review-gated answers are dominated by the source gates (§3.3).
    V1 through a real MCP server (`benchmarks/resident/identity.py`, r15 rows of rich, hono,
    zod, pydantic and fastapi: 951 rows, 901 distinct questions): 0 differing questions on vs
    off for P2a alone and for P2a + P2b (noise off vs off 0), and 0 again when every question is
    asked a second time in the same server (memo-warm answers); 0 new `complete`. V4 follows
    from V1 (every answer equals `off`); `audit_complete.py` was not rerun.
- [ ] P3: differential test green for every key; V1 0 diffs with VERIFY; V2 warm edge-only median ≤ 5 ms
- [ ] P4: callees identity and latency gates
- [ ] CLI↔MCP parity test green (answers identical; CLI `first-use`)
- [ ] `docs/agent-envelope-contract.md` unchanged; `index status` `resident` block documented
- [ ] CODEMAPS updated

## What this RFC does NOT do (deferred)

- It does not change any answer, reason code, payload field or the RFC-0040 registry.
- It does not move the review gates (source text) into resident data. Phase 5 changes only how
  their freshness is proven.
- It adds no new index schema. It needs no reindex, and the extractor version is unchanged.
- It does not change the compact callers output (#1853) or the answer-shaping code.
- It does not share a graph daemon across processes (Alternative G).

## Open questions

1. Should `background` be the default for every MCP start, or only when a published index exists
   *and* the previous session asked a graph question (a recorded hint)?
2. What is the lease-renewal policy (N minutes idle, before TTL)? Is renewal even worth its CPU, or
   should the TTL be longer when the resident handle exists? A longer TTL changes certification
   age, so it would need its own review.
3. Can `os.scandir` directory-entry stamps replace per-file `stat` in stat mode on Windows? The
   rich walk measured 9.1 ms for 45 directories, against about 18 ms for 213 stats. It is only
   safe if NTFS directory-entry metadata is current for closed files. That needs a qualification
   test, and it must stay off for files with open write handles, which cannot be detected cheaply.
4. Should Phase 4 also cover `caller_tree` and `trace_impact`, which read the same graph, in the
   same PR, or one PR per action?
5. Is a whole-answer memo (Alternative B) worth adding on top of Phase 5's epoch token for
   repeated agent questions?
