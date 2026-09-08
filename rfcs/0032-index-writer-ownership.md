# RFC-0032: Index writer ownership and obsolete-candidate fencing

- **Status**: draft
- **Author(s)**: @aimasteracc, Codex
- **Created**: 2026-09-08
- **Last updated**: 2026-09-08
- **Tracking issue**: TBD after acceptance
- **Affected source paths**:
  - `tree_sitter_analyzer/ast_cache.py`, `_ast_cache_*_mixin.py`
  - `tree_sitter_analyzer/cache/{schema,schema_extensions,write,indexer_snapshot,index_project_runner}.py`
  - `tree_sitter_analyzer/{indexing_snapshot,incremental_sync,file_watcher}.py`
  - `tests/unit/test_incremental_sync.py`, existing cache/storage contract modules

## Summary

Bind every mutable candidate to a persistent cache revision, serialize each managed
writer from candidate capture through final publication, and restrict delayed cleanup
to rows owned by that operation. Reject obsolete candidates before changing rows,
graph state, or certification. This requires an ast_cache migration and therefore
acceptance before implementation; this draft is not a shipped safety guarantee.

## Motivation

On develop `b7023f60`, two real Python processes reproduce: an older watcher pauses
after capture, a newer watcher completes indexing, then the older watcher resumes
and deletes the newer row. Both processes exit normally. The same failure occurs
without concurrent execution when an old candidate is replayed after a newer sync.
The replay also changes `ast_call_graph_state` from built to unbuilt.

The RED test `test_obsolete_candidate_preserves_newer_complete_index` in the isolated
`fix/stale-index-writer-ownership` worktree compares the complete SQLite logical dump
before and after replay, in same-process and other-process variants. Both fail;
the other 127 incremental-sync tests pass. Protecting only a content hash or adding
only a process lock does not establish the required ownership.

## Detailed design

### Persistent identity and schema migration

Baseline `CURRENT_SCHEMA_VERSION` is 17. Reserve migration 18; if another migration
lands first, renumber this migration and its exact contracts before implementation.

- Add singleton `ast_writer_state`: `id=1`, random `cache_uuid`, nonnegative integer
  `revision`, nullable `active_operation`, and `phase` (`idle`, `writing`, `incomplete`).
- Add nullable `write_operation` to `ast_index`. Existing rows start unowned.
- Include the final revision/operation in full-index publication metadata. They are
  write-authority metadata, not replacements for source/index fingerprints.
- Increment revision atomically with every canonical data/certification mutation.
  Revision never depends on wall clocks, mtimes, hashes, or reusable row IDs.
- Generate a new cache UUID on a true cache replacement; retain it during ordinary
  incremental updates. A revision from another cache incarnation is never valid.
- Materialize the complete managed schema, including lazily created state tables,
  before installing guards. An inventory of currently existing tables is insufficient.
  The migration contract must enumerate the exact supported table/DDL set, including
  `ast_build_state` and `ast_resolve_state`, and fail on an unwatched managed addition.

Migration runs under writer exclusion and a SQLite write transaction. Install all
required schema/guards and record version 18 atomically. Existing content remains
available as uncertified cache data until a successful owned full reindex; migration
must not label old rows complete. Failure rolls back the migration. Downgrade needs
a separately rebuilt cache; do not silently strip ownership metadata.

Stop old TSA processes before migration. In addition, qualification must exercise an
already-open v17 writer against the upgraded database and prove its supported write
operations fail without partial mutations. A schema-version check only at connection
creation is insufficient. No mixed-version live-write compatibility is promised.

### Operation lease and candidate binding

Use one reentrant process-local owner plus an OS-backed cross-process lease keyed by
canonical database identity. Hold the lease across capture, validation, scope pruning,
all batches, backfill, manifest publication, and cleanup. SQLite read-only consumers
remain independent. Nested same-owner calls reuse the lease; a new operation cannot
replace ownership while an earlier callback or worker can still mutate the database.

The implementation must use pinned paths/handles, reject symlink/reparse replacement,
and prove that atomic database replacement cannot create two concurrent lease owners.
Do not repurpose a PID file as a lock. OS owner death releases exclusion. A 30-second
acquisition bound returns a retryable existing error envelope; this is a wait bound,
not a feedback SLA. Watcher stop retains active ownership until the writer actually
exits. Cancellation cannot release the lease underneath surviving writers.

Capture `(cache_uuid, revision)` before collecting source candidates while holding
the lease. Store it as private candidate metadata. Before the first write, compare
the binding to current state under the same lease. Mismatch returns
`INDEX_CANDIDATE_SUPERSEDED`, with no changes to the logical database dump.

Externally retained candidates also need this binding. Unbound legacy candidates
cannot authorize mutation: return `INDEX_CANDIDATE_UNBOUND` without writes and require
fresh capture through the coordinator. Update every internal producer and real CLI/MCP
route together. Frozen candidates remain tied to both their frozen source identity and
their cache revision; materialization does not waive revision admission.

### Write fence and cleanup

Each admitted operation receives a unique token. Ordinary writes stamp that token on
their rows. Scope deletion is authorized by an admitted current candidate; rollback,
late-result cleanup, and delayed callbacks may remove only their own operation's rows.
Check ownership before deleting FTS/graph projections, not after deleting the primary
row. Lost ownership must never clear another operation's graph marker or manifest.

Use SQL guards on canonical ordinary tables to reject writes from connections without
an admitted owner, and advance revision in the same transaction. The guard function
must be pure and perform no filesystem/network/process access. A local SQLite 3.50.4
prototype rejects both a pre-migration connection lacking the guard function and a
released owner; the sole admitted row remains unchanged. This proves one primitive,
not migration or application-wide coverage.

Before choosing the final guard implementation, audit the exact canonical table and
mutation set, including direct `index_file`, `invalidate`, incremental/full/force index,
resolve-only, graph rebuild, clear/prune, maintenance, and migration. Derived FTS virtual
tables and DDL do not inherit ordinary-table trigger protection: their managed paths
must be included in the admission/transaction audit and old-client negative tests.
Missing or modified guards make mutable admission fail closed. Do not claim protection
against an adversarial process that deliberately removes the schema or replaces files.

Pure Python SQLite functions cannot assume `SQLITE_INNOCUOUS` registration. Explicitly
qualify the selected trigger/function approach with the deployed `trusted_schema`
policy. Do not silently enable trusted schema to make a failing implementation pass.
This feasibility gate may require a revised mechanism before acceptance is finalized.
The same SQLite 3.50.4 prototype confirms `unsafe use of tsa_writer_admitted()` with
`trusted_schema=OFF`, and `cannot create triggers on virtual tables` for FTS5.
These are reproduced limitations, not hypothetical exceptions to the admission gate.

### Real-route feasibility evidence

Additional local experiments use the real `ASTCache` and `IncrementalSync` methods
from develop `0d50d276`, Python 3.14.3 and SQLite 3.50.4 on macOS. Each cell starts
with a complete one-file index and an already-open runtime connection. A separate
connection installs denial triggers, then the existing runtime executes the listed
operation. Compare whole SQLite logical dumps both immediately and after committing
any transaction the rejected operation left open. No source-code methods are mocked.

| Rejected operation | Only `ast_index` guarded: dump changed | Existing ordinary tables guarded: dump changed | Ordinary tables plus eager `ast_build_state`: dump changed |
|---|---|---|---|
| `index_file` | yes | no | no |
| `invalidate` | no | no | no |
| incremental sync | no | no | no |
| forced project rebuild | yes | yes | no |

The first failure clears `ast_call_graph_state` before the primary-table rejection.
The second failure creates and writes `ast_build_state` after the guard inventory was
taken. Eager creation removes that observed DDL gap. Merely catching the final SQLite
exception does not undo already committed metadata changes.

With all ordinary tables guarded and the state table eagerly created, a separate
four-route probe registers an admission function returning false and uses
`RAISE(ROLLBACK, 'WRITER_REQUIRED')`. All four operations preserve the logical dump
and leave `in_transaction=false`. Use transaction-aborting rejection, not a mechanism
that only aborts the last statement. Entry wrappers must also roll back connection
state for preparation errors such as a missing guard function; that older-connection
case left a deferred transaction open in the `index_file` probe.

These 16 route observations are feasibility evidence, not full qualification. They
do not cover direct virtual-table/DDL writes, every lazy table, filesystem mirrors,
all old wheels, concurrent owner transitions, or native Windows/Linux. Reproduce the
negative cells and preserve the positive cells in the implementation test matrix.

### Crash recovery and publication

An abandoned operation leaves `phase=incomplete`; readers cannot infer fresh/complete
from leftover rows. A subsequent owner recaptures current sources and repairs the
index. It may clean abandoned owned rows while excluding any later owner, then publish
a new exact manifest. A late result from the abandoned operation is rejected.

Lease acquisition and publication failure leave explicit incomplete/unknown evidence;
they never fabricate success. Retry performs a fresh capture instead of replaying the
rejected candidate. Error accounting must remain truthful through CLI and MCP.

## Three-Surface impact (CLI ↔ MCP parity)

No new facade, MCP action, or CLI flag. Existing index/sync/watch paths share the same
coordinator and failure reasons. Python callers supplying retained candidates must
obtain bound candidates; this admission change is part of the RFC decision. Public
read-only snapshot tokens remain governed by RFC-0022 and are not writer leases.

## Drawbacks and alternatives

- Exclusion can delay writers; guard/revision work adds write amplification. Measure
  1k/10k source projects and cancellation under contention before shipping.
- Full rebinding/migration touches several write surfaces and invalidates existing
  certification until reindex. It cannot be safely implemented as one local DELETE fix.
- Hash-only conditional deletion confuses identical-content generations. Timestamp
  ordering is not ownership. A process lock alone admits sequential obsolete replay.
- Rejecting every changed candidate without generation admission leaves unresolved
  deletion/unsafe-source policies and does not fence late callbacks.
- Staging a complete new database per operation is a viable alternative but needs
  reader/connection lifecycle and atomic publication qualification; it is not assumed
  cheaper or safer without that evidence.

## Prior art

[SQLite transactions](https://www.sqlite.org/lang_transaction.html) provide transaction
exclusion but do not cover a multi-commit indexing operation or a candidate retained
outside that transaction. [SQLite trigger semantics](https://www.sqlite.org/lang_createtrigger.html)
support aborting an unauthorized statement. [Application-defined function security](https://www.sqlite.org/appfunc.html)
constrains trigger-based guards; qualification must include that constraint.

## Test plan (RED-first)

Start with the existing two failing obsolete-replay tests. Extend them to identical
bytes/mtime (ABA), preexisting partial rows, newly added/deleted paths outside the old
selection, permanent source rejection followed by recovery, full/force indexing, and
late batch cleanup. Preserve whole-database state on rejected admission.

Use real processes with barriers before capture, after capture, before batch commit,
and before publication. Kill an owned test worker and prove bounded recovery; prove
stop does not release ownership while a callback can still write. Exercise custom DB
paths, aliases, root/cache replacement, and native Linux/macOS/Windows behavior.

Migration tests cover v17, missing/partial guard installation, restart, rollback,
unknown future schema, old already-open connections, and old runtime write routes.
Enumerate every managed mutation site and require an exact admission audit, rather
than checking a small sample of wrappers. Run TSA impact-selected tests, fresh patch
coverage, and the runtime-contract quick gate before any implementation PR is pushed.

## Acceptance criteria

- [ ] RFC accepted, guard feasibility/native compatibility gate resolved.
- [ ] Migration and exact schema/guard contracts pass; old writers cannot partially mutate.
- [ ] Lazy table/DDL inventory is exact; rejected operations preserve committed state
  and leave no transaction that can publish delayed mutations.
- [ ] All candidate producers bind cache revision; unbound/obsolete candidates write nothing.
- [ ] Cross-process exclusion covers every managed write route and full operation lifetime.
- [ ] Late cleanup cannot remove another operation's data or certification, including ABA.
- [ ] Crash, timeout, cancellation, replacement, and full rebuild scenarios pass natively.
- [ ] CLI↔MCP parity and existing read-only source-evidence contracts remain green.
- [ ] Measured write cost and feedback latency published without an unsupported SLA claim.
- [ ] Relevant codemaps, migration notes, and recovery guidance updated with implementation.

## Deferred / open questions

This RFC does not establish industry leadership or instantaneous feedback. Benchmark
admission and pending RFC-0031 verification execution remain separate work.

1. Accept revision-bound candidates and schema 18, including explicit rejection of
   legacy unbound retained candidates?
2. The pure SQL guard feasibility gate must resolve trusted-schema, virtual-table/DDL,
   and old-client write behavior before choosing the final enforcement mechanism.
