# RFC-0039: Incremental index certification

- **Status**: accepted — accepted by the owner on 2026-10-20 with the recommended defaults (see "Owner decisions"); implementation tracked in #1718
- **Author(s)**: @aimasteracc
- **Created**: 2026-10-20
- **Last updated**: 2026-10-21 (step 3 amended, owner-approved)
- **Tracking issue**: #1718 (follow-up of #1696 / PR #1714; related #1710)
- **Feasibility evidence**: [`evidence/0039-feasibility/`](evidence/0039-feasibility/README.md)
- **Affected source paths** (if accepted):
  - `tree_sitter_analyzer/index_snapshot_schema.py` (`index_fingerprint`, `stamp_full_index_manifest`, manifest v3)
  - `tree_sitter_analyzer/index_snapshot.py` (reader verification)
  - `tree_sitter_analyzer/index_fingerprint_memo.py`, `tree_sitter_analyzer/index_fingerprint_store.py` (#1561 / #1700)
  - `tree_sitter_analyzer/incremental_sync.py` (`certified_at` stamping; arming)
  - `tree_sitter_analyzer/cache/indexer.py`, `tree_sitter_analyzer/cache/index_project_runner.py` (arming on the `index_project` route)
  - `tree_sitter_analyzer/_ast_cache_database_mixin.py` (initialization baseline for the armed-connection invariant)
  - `tree_sitter_analyzer/cache/certification_tracking.py` (dirty tracking, stale flag, incremental fold)
  - new `tree_sitter_analyzer/cache/certification_tree.py`
  - `tests/unit/test_index_fingerprint*.py`, new `tests/unit/test_certification_tree_1718.py`

## Owner decisions

- **2026-10-20, accepted with the recommended defaults.**
  - Option A: a per-file two-level Merkle root (`(table, file_path)` leaves, root over sorted leaves).
  - FTS5 (the virtual table and its shadow tables) is bound through the existing per-file projection digest (`ast_symbol_projection_state` plus `symbol_projection_is_exact`), not hashed into the root (step 2, recommended variant). This resolves Open question 1.
  - The remaining open questions (2–4) take the defaults proposed in this RFC:
    - scheduled verify every 20 stamps or 24 h;
    - on-demand verify deferred until needed;
    - reader-memo seeding only after a full or verified stamp.
  - Implementation starts with step 0, as its own bug-fix PR, followed by RED-first slices per the test plan. Every slice carries the always-verify gate (in every stamp in the test suite the incremental root equals a full recompute, and a mismatch fails closed) and the repository check over 8 edit kinds.
- **2026-10-21, the armed-connection invariant uses `PRAGMA data_version` and persistent stale-flag triggers instead of the RFC-0032 writer revision** (step 3, amended).
  - The writer revision only advances when the RFC-0032 fence is armed, which is on custom `db_path` in-place routes.
  - On the default generation route a refresh writes a private copy whose revision does not move, so a revision delta proves nothing there.
  - The always-verify gate also found two cases a revision check would not have caught: a refresh whose stamp failed but whose rows were published, and a single-file write between refreshes.

## Summary

Every certified refresh hashes every row of every query-visible table: 512k rows on this repository, taking 9–24 s. It does so to stamp `index_fingerprint` in the snapshot manifest, even when one file changed.

This RFC replaces that flat digest with a **two-level Merkle root**:
- one leaf per `(table, file_path)` group;
- a root over the sorted leaves.

The writer recomputes only the leaves its own connection dirtied, then folds the root. On this repository the hashing cost of a 1-file refresh drops from 9.1–14.6 s to 0.9–2.2 s, or 0.04–1.0 s if the FTS5 projection is bound through its existing per-file projection digest. Across 16 measured refreshes, the incremental root equaled a full recompute every time.

"Certified" keeps its meaning: the manifest commits to the exact query-visible rows. What changes:
- the commitment's format;
- the writer's obligation, from "read everything" to "prove nothing was written outside the tracked connection, else read everything";
- a **verifier** that recomputes the full root on every refresh in tests, on a schedule in production, and on any reader mismatch.

## Motivation

### The cost

#1696 / PR #1714 scoped the call-graph backfill. A 1-file refresh still took 34–64 s on this repository, and most of the remainder is certification and publication:

| Phase (1-file refresh, PR #1714 gate) | Seconds |
|---|---|
| `stamp_full_index_manifest` | 15–24 |
| — of which `index_fingerprint` | 13–19 |
| `GenerationStore.capture` | 2.4–6.7 |
| `GenerationStore.publish` | 2.2–5.1 |
| scoped backfill stages | 5–12 |

The #1718 target is a 1-file refresh in at most 10 s. It cannot be reached while certification reads every row.

### What is hashed today, and where

**Writer: `stamp_full_index_manifest`** (`index_snapshot_schema.py:225`). This runs at the end of `IncrementalSync.sync`, `index_project` and the `full_index` tool, inside `BEGIN IMMEDIATE` on the writer connection. It computes:
1. `source_fingerprint`, from the recorded source inventory;
2. `index_fingerprint`. This is SHA-256 over:
   - the project root;
   - for every table in `sqlite_master` except `_CONTROL_TABLES` (manifest, metadata, build / call-graph / resolve state, `sqlite_sequence`, `ast_writer_state`): its name, schema SQL, query-visible columns (`table_xinfo`), and every row, `_typed`-encoded and `ORDER BY` every column `COLLATE BINARY`.

   It also includes FTS5 virtual tables and their shadow tables. It is bounded by row, byte and cell budgets and a deadline. On this repository: 15 tables, 511,915 rows, 9.1–24 s depending on load;
3. a fresh capture of the current sources (portable inventory on Windows), compared with the recorded rows.

The manifest row is `(canonical_root, source_fingerprint, index_fingerprint, file_count, source_scope_descriptor, manifest_version=2)`.

**Reader: `index_snapshot` capture** (`index_snapshot.py:328/533`). Every certified read verifies:
- `manifest.index_fingerprint == index_fingerprint(private copy)`;
- that the source fingerprint and rows match a fresh source capture.

The reader's recompute is memoized by a **content key**, the SHA-256 of the pinned database bytes:
- in process since #1561;
- across processes since #1700 (PR #1701), in `~/.tsa/cache/index-fingerprint/`, re-checked element by element.

A cold reader of a new generation still pays the full recompute. That cost is part of #1710.

**Other consumers.**
- `constraint_index_snapshot.py:203` recomputes in full too.
- `generation_noop.py` relies on the manifest commitment to skip publishing unchanged runs (#1631).
- `edge_evidence.py` compares `index_fingerprint` strings as opaque identifiers.

### A precondition we found: content churn on every refresh

`IncrementalSync` stamps `ast_index.certified_at = now()` on every new, updated **and unchanged** file (`incremental_sync.py:183`). So each refresh changes one row per file in a hashed table: 2,565 leaves on this repository, evidence dataset A.

No reader uses the value; all readers only test `IS [NOT] NULL`. Any incremental scheme must first stop this churn (Detailed design, step 0).

## Detailed design

### Step 0 (prerequisite, no format change): stop `certified_at` churn

Unchanged files keep their `certified_at`. New, updated and still-NULL files are stamped as now, and error files are reset to NULL as now.

This is an independent bug-fix PR. It also helps the no-op detector and any per-file change detection.

### Step 1: the certification tree

- **Group.** A table with a `file_path` column is grouped by `file_path`, with NULL as a distinct key. Any other table is one group, `*`.
- **Leaf.**

  ```
  SHA-256("tsa-index-leaf-v1\0" ‖ frame("row", _typed(row)) for each row
          in ORDER BY file_path, <every query-visible column> COLLATE BINARY)
  ```

  The row encoding and order are unchanged from `index_fingerprint`.
- **Root.**

  ```
  "merkle:" ‖ SHA-256("tsa-index-merkle-v1\0" ‖ frame("root", canonical_root)
      ‖ for each table in name order:
          frame("table", name) ‖ frame("schema", sql) ‖ frame("columns", _typed(cols))
          ‖ for each group key in binary order: frame("group", key) ‖ frame("leaf", leaf))
  ```

- **Budgets.** The existing row, byte and cell budgets and the deadline apply to a full build. An incremental fold is bounded by the dirty set.
- **Leaf store.** Leaves are stored in a new **control table** `ast_certification_leaves(tbl, grp, leaf, PRIMARY KEY(tbl, grp))`. It is derived data outside the root, like `ast_writer_state` (RFC-0032 slice 5).
  - A writer trusts the stored leaves only if they fold to the parent generation's manifest root. That check costs 0.02–0.06 s for about 15k leaves.
  - If the fold does not match, the writer rebuilds the leaves in full.

### Step 2: FTS5 binding (recommended variant)

Triggers cannot track the FTS5 virtual table and its shadow tables (`_data`, `_idx`, `_docsize`, `_config`):
- triggers on a virtual table are rejected (RFC-0032 evidence E2);
- triggers on the shadow tables crashed the process (`0xC00000FD`, evidence §2);
- the virtual table cannot be filtered by `file_path` without a full scan.

Re-hashing FTS on every refresh is 0.75–1.35 s, most of the remaining cost.

**Recommended:** exclude the FTS virtual and shadow tables from the root, and bind them through what already certifies them:
- `ast_symbol_projection_state`, one row per file with `content_hash`, `symbol_count` and `projection_digest`. It is an ordinary table, so it is in the root and incrementally tracked;
- the `symbol_projection_is_exact` check, which the snapshot capture already runs (memoized since #1561). It is extended to run at stamp time for the dirty files only.

This is a narrowing of what the root itself hashes. Readers that consume FTS are protected by the projection check exactly as today. The alternative is to keep FTS in the root and pay about 1 s per refresh; that is Open question 1.

### Step 3: dirty tracking on the writer connection

When a refresh arms its writer connection (the same point as `backfill_scope.begin`, #1696), it installs TEMP triggers:
- `AFTER INSERT / UPDATE / DELETE` on every ordinary table in the root;
- each one records `(table, file_path)` or `(table, '*')` in a TEMP table;
- `UPDATE`s that change no column are ignored (`WHEN NOT (OLD.c IS NEW.c AND …)`).

TEMP objects live only on that connection and never enter the index file.

**The armed-connection invariant** (amended 2026-10-21, see "Owner decisions"). The incremental root is valid only if two things hold: the rows at arming are exactly the rows the parent certified, and every later write to a rooted table went through the armed connection. The writer proves this with three checks:
- **No writes before arming on this connection.** Schema initialization records `total_changes`. Arming requires the same count and that no migration ran (`WRITES_BEFORE_ARMING`, `MIGRATED`).
- **No writes since the last stamp, from anyone.**
  - Every stamp ensures persistent `AFTER INSERT / UPDATE / DELETE` triggers on every rooted table, and sets `ast_cache_metadata.certification_stale` to `0`.
  - The first later write, from any connection, code path, process or TSA version, sets it to `1`.
  - Arming requires `0` and every trigger present (`WRITTEN_SINCE_STAMP`, `NO_STALE_TRACKING`).
  - The flag lives in `ast_cache_metadata`, which every index has, so a trigger body can never make a write fail.
- **No other committer during the refresh.** `PRAGMA data_version` on the armed connection is unchanged between arming and stamping (`OTHER_CONNECTION_COMMITTED`).

The RFC-0032 writer revision is not used. It only advances on fenced (custom-path) connections, so on the default generation route it cannot show that nothing else wrote.

Any of the following makes the writer fold a **full** recompute instead, and record why (`certification: {mode: "full", reason}`, mirroring `backfill_scope`):
- any check above fails;
- a table whose schema SQL or columns changed;
- a missing or untrusted leaf store;
- a route that is not armed. The `index_project` workers, custom `db_path` in-place writers and `invalidate` are not armed until each is shown to be.

### Step 4: stamping

`stamp_full_index_manifest` keeps its transaction and source checks. It replaces `index_fingerprint(conn)` with:
1. load the parent leaves and check that they fold to the parent root;
2. recompute the dirty leaves;
3. fold the root, store the leaves, and write manifest `manifest_version = 3` with `index_fingerprint = "merkle:…"`.

The column name is kept, and the value is self-describing by prefix.

### Step 5: verification (the verifier)

The incremental root claims equality with a full recompute. Four mechanisms check that claim:

1. **Tests: verify always.** With `TSA_CERTIFICATION_VERIFY=full`, set in `tests/conftest.py` for the whole suite, every stamp also computes the full root and **fails closed** on a mismatch. It raises `CERTIFICATION_TREE_MISMATCH`, and the manifest is not written. This is the #1718 gate: "the incremental root equals a full recompute on every refresh in the test suite."
2. **Readers verify in full, as today.** A reader recomputes the root of the generation it reads, memoized by content key (#1561 / #1700). A mismatch means "not certified", exactly as a v2 mismatch does today. So a wrong incremental root can never yield a certified read; it costs availability, not correctness.
3. **Seeding the reader memo** (optional, addresses part of #1710).
   - After publishing a sealed generation, the writer computes the SHA-256 of the sealed file. That is the same digest a reader computes as its memo key; it took 0.41–0.86 s for 363 MB.
   - The writer stores `(content key → root)` in the #1700 store, so a cold reader skips the 9–24 s recompute.
   - This is safe only under the same assumptions as #1700. The key is the full byte digest, the store is in the user cache directory, and the entry is re-checked element by element. To keep point 2 meaningful, seeding happens only when the stamp was a **full** recompute or a verified incremental one (point 4).
4. **Production: a scheduled full verify.** Every Nth stamp (proposed: 20), or when the leaf store is older than T (proposed: 24 h), the writer computes the full root alongside the incremental one.
   - On a mismatch it stamps the full root, discards the leaf store, logs `CERTIFICATION_TREE_MISMATCH` with the dirty-table summary, and reports `certification.mode = "full"` with that reason.
   - CLI `--ast-cache-verify` and MCP `index action=cache mode=verify` (1:1) force a full verify on demand. These are new surfaces; see the three-surface section.

### What can go wrong, and what catches it

| Failure | Effect without a verifier | Caught by |
|---|---|---|
| A write on another connection, or raw SQL | a stale leaf, so the root is wrong | `data_version` or the stale flag (step 3) falls back to full; readers (step 5.2) |
| A new write path that is not armed | a stale leaf | the same, plus the always-verify suite (5.1) |
| A trigger missed on a newly added table | that table's leaves are stale | the schema/inventory change forces a full recompute of that table; 5.1 |
| A corrupted or tampered leaf store | a wrong fold | the fold-to-parent-root check (step 1); readers |
| FTS drift from `ast_symbol_rows` | none in the root (excluded) | the projection-exact check at stamp and at read, as today |
| SQLite or Python version changes the encoding | leaves are not comparable | the leaf-store format and version key; full rebuild |
| A crash between leaf store and manifest | leaves and root disagree | the fold check makes the next writer rebuild |

## Three-Surface impact (CLI ↔ MCP parity)

- The refresh result gains a `certification` field with `mode` and `reason`, emitted in the sync result and in the `index_project` stats.
- In the MCP index reply, a compact `"certification": "incremental"` or `"full:<REASON>"` is added under the #1582 size contract, in the same way #1714 added `backfill`.
- The optional on-demand verify is `--ast-cache-verify` on the CLI and `index action=cache mode=verify` on MCP, kept 1:1. If it is deferred, no surface changes beyond the result field.

## Interaction with other RFCs and memos

- **RFC-0030 (Pulse source evidence).**
  - Unchanged. Source certification (source fingerprint, recorded rows, fresh capture) is untouched.
  - RFC-0030's rule that paths, generation ids and mtimes are never evidence on their own still holds. The root is content-derived, and the reader still recomputes it.
- **RFC-0032 (generation ownership, slice 3 seal, slice 5 revision).**
  - The leaf store lives inside the generation and is copied with it, so it is copy-on-write, sealed read-only at publish (slice 3), and never mutated after publication.
  - The slice 5 revision is not used for the invariant (amended 2026-10-21): it does not advance on the default generation route. `PRAGMA data_version` and the stale flag are used instead.
  - Publication CAS is unchanged.
  - Custom `db_path` in-place routes are not sealed, are not armed in the first phase, and always certify in full.
- **#1561 / #1634 / #1700 (PR #1701) memos.**
  - Keys stay content-addressed by database bytes. The value becomes a `merkle:` root for v3 manifests.
  - The stored-key environment already includes the code fingerprint, so existing entries miss after an upgrade and are recomputed.
  - Step 5.3 adds a writer-side seed.
- **#1710 (certified reads cost about 10 s; partly addressed by #1713, merged 2026-10-20, which stops paying a discarded capture on every call).**
  - This RFC removes the writer's full hash, and the optional seeding removes the cold reader's index hash.
  - The source re-hash that #1710 also measures is out of scope.

## Migration and back-compat

- **Manifest.** `manifest_version` 3 means a `merkle:` root. Readers accept 2 (flat fingerprint, full recompute as today) and 3.
- **Older readers.** They require `manifest_version == 2`, so they treat a v3 manifest as "not certified". That fails closed, with no wrong certified answer.
- **Schema.** The control table `ast_certification_leaves` is additive. The reader-required snapshot version is unchanged.
- **First stamp after upgrade.** No leaf store exists, so it does a full tree build: 6.0–17.3 s here, comparable to today's single stamp. Every later stamp is incremental.
- **Downgrade.** An older writer ignores the leaf table and stamps a v2 manifest. The newer writer then finds that the leaves do not fold to a v3 parent root and rebuilds them.
- **Rollout.**
  1. Step 0.
  2. Steps 1–4, shipped with 5.1 and 5.2 only.
  3. 5.3 and 5.4.

  Each step is RED-first and independently mergeable.

## Drawbacks

- The writer's guarantee becomes conditional: "full, unless the tracked set provably covers every write". It relies on `data_version`, the stale-flag triggers and TEMP triggers, which is more machinery than "hash everything".
- Excluding FTS from the root (step 2) narrows the commitment. FTS is then certified through the projection check rather than byte-for-byte.
- A leaf store of about 15k rows per generation, around 1 MB, is added to each generation.
- `index_fingerprint` values change format, so any external consumer that stored them sees new strings once. In this repository only opaque equality is used.

## Alternatives

### A. Per-file Merkle tree (this RFC)

| | |
|---|---|
| Cost per 1-file refresh | 0.9–2.2 s with FTS, 0.04–1.0 s without (evidence B) |
| Verifier | full root at read time, scheduled, and on every stamp in tests |
| Risk | untracked writes, caught by `data_version`, the stale flag and readers |

### B. Physical digest of the sealed generation file

The writer records the SHA-256 of the sealed generation bytes, 0.41–0.86 s, in a sidecar or the selector. Readers check bytes instead of rows.

- **Pros:** cheapest, and it also fixes the reader cost.
- **Cons:**
  - it cannot live in the database it hashes, so the manifest's commitment moves out of the index;
  - it binds bytes, not rows: two identical logical builds certify differently, and the no-op detector (#1631) loses its row-level meaning;
  - it only exists for sealed generations, so custom and legacy in-place routes still need a full logical hash;
  - it changes what "certified" means from a statement about content to a statement about a file.

**Not recommended as the certification;** used only as the reader-memo key in step 5.3.

### C. Lazy full verify on a schedule (stamp provisionally)

The writer stamps without hashing. A background verifier computes the full fingerprint later, and readers treat the manifest as uncertified until it is verified.

- **Cons:** it moves the 9–24 s to the first certified read, which is #1710's problem, or leaves results uncertified for a window.
- **Rejected.**

### D. Per-file digests rolled into a flat list instead of a tree

This is option A without a stored structure: the writer recomputes per-file digests for dirty files and concatenates the sorted list.

It is equivalent to A at this scale; the fold over about 15k leaves is 0.02–0.06 s. A is A plus the leaf store, so this is not a separate option. A deeper tree (row-group chunks inside large files) is unnecessary: the largest file group here is a few thousand rows.

## Recommended default

**Option A** with the following:
- step 0;
- FTS bound through the projection digest (step 2, recommended variant);
- the armed-connection invariant (`data_version` plus the stale flag);
- always-verify in tests and reader full recompute as the verifier.

Scheduled verify (step 5.4) defaults to every 20 stamps. Reader-memo seeding (5.3) comes in the second phase.

## Test plan (RED-first)

- **Unit.**
  - The leaf and root encoding is stable and independent of insertion order.
  - The incremental fold equals a full fold for: a modified file, an added file, a deleted file, NULL `file_path`, an ungrouped table, a schema change, and an empty table.
- **Integration.** Under `TSA_CERTIFICATION_VERIFY=full`, the whole suite passes, which proves equality on every refresh the suite performs.
- **Negative.**
  - A write on a second connection, during the refresh or since the last stamp, makes the stamp fall back to full (RED first).
  - A tampered leaf makes the fold check rebuild.
  - A tampered row makes the reader verify fail and report "not certified".
- **Dogfood.** On this repository, 1-file edits of each kind: body only, signature, add or remove a method, base class, import alias, return annotation, add file, delete file. For each, the incremental root equals the full root, and hashing time is at most 2 s.

## Acceptance criteria

- [ ] Step 0: `certified_at` stamped only for new, updated or NULL files (separate PR)
- [ ] Manifest v3 with a `merkle:` root; readers accept v2 and v3; v2-only readers fail closed
- [ ] Armed-connection invariant (`data_version` plus the stale flag), falling back to full with `certification.reason`
- [ ] Always-verify in the test suite; a mismatch fails closed
- [ ] Dogfood: equality on every edit kind; 1-file stamp hashing ≤ 2 s on this repository
- [ ] CLI↔MCP parity for `certification` and the optional verify action
- [ ] Docs: `docs/index-lifecycle.md`, envelope contract

## What this RFC does NOT do (deferred)

- The source-side re-hash in reader captures (#1710, part 1).
- Capture and publish costs (2–7 s each).
- Arming the `index_project` worker route and custom `db_path` in-place writers. They certify in full until each is shown to keep the invariant.

## Open questions

1. Should FTS stay in the root (about 1 s per refresh, a byte-exact commitment) or be bound through the projection digest (step 2)?
2. What are the scheduled-verify cadence (N stamps / T hours) and the default for laptops versus CI?
3. Should the on-demand verify surface (`mode=verify`) ship in phase 1, or wait until a mismatch has been seen in the field?
4. Should reader-memo seeding (5.3) require the stamp itself to have been a full recompute, which is safer but leaves the cold reader slow after most refreshes? Or is a verified-incremental stamp (with 5.4) enough?
