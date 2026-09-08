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

## Released-interface boundary

The roadmap's user decision remains binding: already released CLI/MCP/Python
interfaces are removed only in an explicitly authorized major release with migration
notes. This RFC does not override that decision or authorize a release.

The candidate compatibility premise has now been checked against published artifacts.
On 2026-09-08, the latest GitHub Release and PyPI wheel were v1.29.5. The wheel
`tree_sitter_analyzer-1.29.5-py3-none-any.whl` has SHA-256
`c97e2d6941e3cfc8714b18a00d97edfb637794705d59305d6e1509fa89153f89`.
Scanning every packaged Python source found neither `IndexCandidateSnapshot` nor
`candidate_snapshot`. Its `ASTCache.index_project` accepts `max_files`, `force` and
keyword-only `workers`, `resolve_only`, `include_activation`, `language_filter`;
`IncrementalSync.sync` accepts `max_files`, `callback`, with no candidate parameter.
The same name scan across 113 locally fetched `v*` tags, including v1.29.5, found no
candidate surface. Latest-wheel inspection is stronger evidence than merely testing
whether the develop introduction commit is an ancestor of a release tag.

Therefore the proposed binding changes an unreleased develop candidate interface;
it has not been shown to remove a released retained-candidate API. Earlier wording
that treated unbound candidates as a published legacy compatibility promise was
unsupported. Existing released calls that omit a candidate must keep working through
the new coordinator. Never manufacture write authority by binding an externally
supplied obsolete candidate to the current revision. If another published artifact
exposes that surface, resolve its migration against the major-release rule before
shipping. Recheck the latest artifact when implementation starts.

This evidence resolves that specific compatibility premise, not RFC acceptance.
Schema migration, new admission responses, old already-open writer isolation, and
the enforcement mechanism still require review. Draft status remains unchanged.
Published sources: [v1.29.5 release](https://github.com/aimasteracc/tree-sitter-analyzer/releases/tag/v1.29.5)
and [PyPI version metadata](https://pypi.org/pypi/tree-sitter-analyzer/1.29.5/json).

### Published custom-path and raw-connection behavior

A real v1.29.5 wheel probe confirms that a custom constructor path equals both
`cache.db_path` and SQLite's `PRAGMA database_list` main path; the requested file
exists. `get_conn()` returns a writable `sqlite3.Connection`: caller-created table
writes commit and are visible from an independent connection. The published docstring
explicitly invites external modules to use this accessor for raw SQL. The probe uses
a custom file outside the project and creates no project `.ast-cache` directory.
Raw record: `/tmp/tsa-published-custom-db-contract.json`.

Consequently physical relocation and mandatory write admission affect released
behavior even though candidate binding does not. Proposed **major-version direction**:
keep the constructor argument as a logical locator, expose its original value as
`requested_db_path`, report the actual active file through `db_path`, and restrict
public `get_conn()` to reads. Existing ASTCache mutation methods remain the supported
write entry points and must acquire operation ownership. Internal SQL helpers use
owned connections; do not secretly preserve a second unrestricted public write path.
This is a direction for review, not an accepted API change; the exact read-connection
lifetime and compatibility/migration examples still need specification.

If accepted, these changes must be part of the next explicitly authorized major-version
migration with notes for direct SQLite clients. This round authorizes no release.
If the published physical-path/raw-write behavior must remain unchanged, redesign
the storage/admission approach; do not claim complete enforcement while leaving an
undocumented escape through the published accessor. The owner decision is pending.

## Detailed design

### Persistent identity and schema migration

Baseline `CURRENT_SCHEMA_VERSION` is 17. Reserve migration 18; if another migration
lands first, renumber this migration and its exact contracts before implementation.

- Add singleton `ast_writer_state`: `id=1`, random `cache_uuid`, nonnegative integer
  `revision`, nullable `active_operation`, and `phase` (`idle`, `writing`, `incomplete`).
- Add nullable `write_operation` to every independently mutable canonical row, not
  just `ast_index`. Existing rows start unowned. This includes symbol rows/comments,
  imports, activation, edges (including incoming-edge rewrites), projection state,
  resolution caches, manifests, and global graph/build state.
- The exact migration inventory assigns every table one ownership mode: row-owned
  canonical data; ownership-control state; immutable schema history; or rebuild-only
  derived storage. No table may remain unclassified. FTS shadow/virtual storage is
  derived from owned canonical symbol rows and is never its own recovery authority.
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
The first post-migration full reindex must regenerate all mutable canonical and
derived state without retaining unowned rows through a cache-hit shortcut.

Stop old TSA processes before migration. In addition, qualification must exercise an
already-open v17 writer against the upgraded database and prove its supported write
operations fail without partial mutations. A schema-version check only at connection
creation is insufficient. No mixed-version live-write compatibility is promised.

### Operation lease and candidate binding

Use one reentrant process-local owner plus an OS-backed cross-process lease keyed by
canonical database identity. A one-shot writer holds the lease across capture,
validation, scope pruning, all batches, backfill, manifest publication, and cleanup.
SQLite read-only consumers remain independent. Nested same-owner calls reuse the
lease; a new operation cannot replace ownership while an earlier callback or worker
can still mutate the database under that operation's admission.

The implementation must use pinned paths/handles, reject symlink/reparse replacement,
and prove that atomic database replacement cannot create two concurrent lease owners.
Do not repurpose a PID file as a lock. OS owner death releases exclusion. A 30-second
acquisition bound returns the typed failure defined below; this is a wait bound,
not a feedback SLA. Watcher stop retains active ownership until the writer actually
exits. Cancellation cannot release the lease underneath surviving writers.

Capture `(cache_uuid, revision)` before collecting source candidates while holding
the lease. Store it as private candidate metadata. Before the first write, compare
the binding to current state under the same lease. Mismatch returns
`INDEX_CANDIDATE_SUPERSEDED`, with no changes to the logical database dump.

Externally retained candidates also need this binding. Unbound develop candidates
cannot authorize mutation: return `INDEX_CANDIDATE_UNBOUND` without writes and require
fresh capture through the coordinator. Update every internal producer and real CLI/MCP
route together. Frozen candidates remain tied to both their frozen source identity and
their cache revision; materialization does not waive revision admission.
Retained capture is a separate, capture-only lease: acquire exclusion, read the base
revision, capture the candidate, recheck the revision, then release exclusion before
returning. The candidate retains metadata and its existing bounded frozen-resource
lifetime, not a live writer lock. Consumption reacquires exclusion and performs
revision admission before claiming a new operation. A retained candidate can neither
block writers indefinitely nor silently bind itself to a later revision. Capture-only
requests encountering abandoned state return `INDEX_RECOVERY_REQUIRED` without repair.

### Write fence and cleanup

Each admitted operation receives a unique token. Ordinary writes stamp that token on
their rows. Scope deletion is authorized by an admitted current candidate; rollback,
late-result cleanup, and delayed callbacks may remove only their own operation's rows.
Check ownership before deleting FTS/graph projections, not after deleting the primary
row. Lost ownership must never clear another operation's graph marker or manifest.
Every canonical insert/update assigns the current operation to the changed row,
including changes to an edge whose caller belongs to a different file. A cleanup
request carries its original operation token explicitly; it must not infer authority
from a connection subsequently reused by a newer operation. Admission and the
row-owner predicate both apply before any primary or derived cleanup mutation.

Recovery may delete abandoned-operation rows and regenerate affected projections
under the new recovery owner; it does not claim to reconstruct earlier row values.
Global metadata and independently rewritten cross-file rows are owned too. If their
dependencies cannot be repaired exactly, perform an owned full rebuild and withhold
complete publication until it succeeds. FTS and other rebuild-only projections are
recreated from surviving/new canonical rows while exclusion remains held.

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

### Mechanism evidence and decision

Forty real-route observations constrain this proposal. Experiments use macOS,
Python 3.14.3/SQLite 3.50.4; published-runtime cases import the SHA-pinned v1.29.5
wheel in separate processes opened before the experiment's migration/guard step.
No observation proves native Windows/Linux behavior or complete route coverage.

| Probe family | Observations | Result and consequence |
|---|---:|---|
| Current runtime, primary/ordinary/eager ordinary guards plus explicit rollback | 16 | Primary guards miss committed graph changes; ordinary inventory misses lazy DDL; eager guards plus registered denial preserve four tested routes, but preparation failures can leave transactions. |
| Published wheel, ordinary versus FTS-shadow guards | 8 | Old invalidate/incremental commit FTS changes before missing-function failure; shadow triggers instead produce malformed-image errors during operation and commit. Neither qualifies old-writer isolation. |
| Published wheel, separate database files | 4 | Every old route succeeds and changes legacy data; every new database dump stays unchanged. |
| Published wheel, read-only legacy FTS view | 4 | Every old route is rejected and post-commit dumps stay unchanged; three transactions remain open. |
| Held old transaction, same versus separate new database | 8 | Same file blocks three new writes; separate file admits exactly one changed row in all four cases and late old commits preserve the entire new dump. |

The failed new writes cannot count as survived newer results. Final dump equality
after closing a connection does not prove writer progress or absence of connection
errors. The held-transaction comparison motivates the separate-file protocol below;
it does not make the in-place trigger proposal safe.

[Full earlier experimental methods and observations](https://github.com/aimasteracc/tree-sitter-analyzer/blob/09979aa88eeaeb2bc565d5ee16ccc9a2328ed040/rfcs/0032-index-writer-ownership.md)
remain versioned, including raw temporary artifact paths, negative cases, exact route
names and limitations. Raw records are diagnostic attachments, not shipped benchmarks.

### Proposed isolated storage protocol — pending acceptance

This is the preferred replacement for **legacy in-place migration** above; revision
admission and owned cleanup within the active new database remain required. Acceptance
must select this protocol explicitly and reconcile the schema section before coding.

1. Treat the existing constructor's requested database path as a logical locator `L`.
   Default `L` is `<root>/.ast-cache/index.db`; custom `L` retains its explicit parent.
   The proposed namespace is `L + ".tsa-v18"`, with an `active.json` selector and
   `generations/<32-lowercase-hex-id>/index.db`. No fallback, union, dual-write or
   symlink from active storage to legacy `L` is allowed. Existing calls without a
   candidate remain accepted; relocating physical storage is a separate compatibility
   decision. Specify/document the returned `db_path` and maintenance-report paths
   before accepting this protocol; do not silently change their published meaning.
2. One resolver owns location choice for ASTCache, watcher, all CLI/MCP readers,
   pinned snapshot acquisition, FTS, derived mirrors and maintenance. It returns the
   logical locator, storage epoch, active generation ID and pinned physical identity.
   A private immutable reader copy is not another active generation. Root aliases must
   resolve to the same locator without resolving descendant source symlinks.
3. `active.json` is bounded to 4 KiB and contains only protocol version, storage epoch,
   generation ID, cache UUID and canonical locator/root bindings. Reject unknown or
   missing fields, duplicate keys, invalid IDs, symlinks/reparse points, traversal,
   mismatched bindings and database hard links. Revalidate the pinned hierarchy before
   and after use. Never accept an arbitrary path supplied through selector content.
4. Bootstrap under a cross-process locator lease. Create a fresh generation exclusively,
   build schema 18 and a complete source-certified index there, then close every build
   connection and worker before publication. Do not read mutable legacy rows as trusted
   migration input. Publish a fully written, flushed selector with atomic replacement;
   qualify directory durability on each native platform. Never rename a live SQLite
   database or reuse its WAL/SHM names underneath old connections.
5. Before selector publication, failure leaves no active new generation; after it,
   readers see exactly the published generation. Missing/invalid selectors fail closed
   without opening legacy `L`. Define the migration-required error and recovery command
   across CLI/MCP before acceptance. Read-only calls must not bootstrap, repair or delete.
   Recovery under the locator lease distinguishes unpublished staging from the active
   generation using persisted identities, never directory age, PID or timestamps.
6. Ordinary writes mutate the selected active database under the operation lease and
   revision contract. Bind candidates to storage epoch plus cache UUID/revision. A
   replacement build records its parent selector and may publish only if that parent
   still matches. Recheck active identity before publishing results or cleanup; retired
   tasks cannot write into, restore, or certify the new active generation.
7. Generation replacement requires all managed users of the retiring generation to
   release write authority; retained reader copies may finish only under their existing
   source/identity validation contract. All mutable mirrors belong to the generation.
   No reader may consult a legacy mirror after selecting new storage. The current custom
   database option disables project mirrors, so the isolation probe did not verify this.
8. Keep legacy files untouched and outside active reads. Old processes may mutate or lock
   those files; neither may influence active data, selectors, mirrors or new-writer
   progress. Do not auto-delete legacy or retired generations while leases/readers could
   reference them. Explicit bounded retirement must verify inactivity and pinned identity.
   This revises the earlier old-write-rejection requirement to isolation of active state;
   it requires explicit RFC acceptance, not an inference from the positive experiment.

Before acceptance, resolve custom-path compatibility, selector error/parity details,
native publication durability, the complete location-consumer inventory, and active
write-guard feasibility (including trusted-schema and FTS). This protocol is not yet
implemented, and the forty observations do not waive those gates.

### Crash recovery and publication

A killed process cannot update its phase: it leaves `phase=writing` and its operation
token persisted. Readers treat both `writing` and `incomplete` as non-complete, without
waiting for a PID/TTL heuristic. Successful OS-lease acquisition proves the previous
owner no longer holds exclusion; under that lease and a SQLite transaction, the next
mutating coordinator recognizes the old `writing` token as abandoned and changes its
phase to `incomplete`, advancing revision. A capture-only caller does not perform this
mutation. Never infer abandonment solely from elapsed time or an unresponsive process.

The recovery owner then recaptures sources and repairs the index with the owned-row
rules above before publishing a new exact manifest. A late result carrying the
abandoned token is rejected. Until recovery is complete, the durable state remains
non-complete even if the OS lock is currently free.

Lease acquisition and publication failure leave explicit incomplete/unknown evidence;
they never fabricate success. Retry performs a fresh capture instead of replaying the
rejected candidate. Error accounting must remain truthful through CLI and MCP.

### Typed admission failures and retry contract

Introduce `IndexWriteAdmissionError` for admission failures before mutation. Python
index/full/incremental entrypoints raise it instead of manufacturing a successful
`SyncResult`; its fields are `code`, `retryable`, `retry_after_ms`, and `next_action`.
Existing ordinary indexing errors retain their current result semantics.

| Code | retryable | retry_after_ms | next_action |
|---|---|---|---|
| `INDEX_WRITER_BUSY` | true | 5000 | `recapture` |
| `INDEX_CANDIDATE_SUPERSEDED` | true | 5000 | `recapture` |
| `INDEX_CANDIDATE_UNBOUND` | false | 0 | `obtain_bound_candidate` |
| `INDEX_RECOVERY_REQUIRED` | false | 0 | `recover_index` |
| `INDEX_WRITER_FENCED` | false | 0 | `discard_result` |

MCP adapters use `build_error` with `success=false`, `verdict="ERROR"`, a sanitized
human-readable `error`, and these exact machine fields (`code` maps to `error_code`).
For example, contention produces this core payload; existing contextual fields may
be added without changing these values:

```json
{"success":false,"verdict":"ERROR","error":"Index writer is busy.","error_code":"INDEX_WRITER_BUSY","retryable":true,"retry_after_ms":5000,"next_action":"recapture"}
```

Equivalent CLI paths print the same JSON payload and exit 1 via the existing
`_exit_code_for` convention. One-shot CLI/MCP calls do not secretly retry. No raw path,
SQL exception, or operation token belongs in the human-readable error.

`FileWatcherDaemon.trigger_sync()` returns that same failure payload for typed
admission errors, rather than reducing them to `{"error": ...}`. Background watchers
retry only the two retryable codes, using fresh capture after delays of 5, 10, 20, 40,
then 60 seconds (60-second cap). Existing notification coalescing and stop ownership
remain mandatory. An unbound candidate or fenced late callback does not cause an
automatic replay loop. Normal mutating coordination performs admitted recovery;
capture-only callers must explicitly request recovery through a mutating route.

Watch status exposes `last_admission_error` (null or the failure payload) and increments
its existing error counter once per failed attempt. Clear this diagnostic after a
successful complete sync. Status-query success means the query succeeded, not that
indexing succeeded. These additional response fields are proposed API changes in this
RFC; they are not claimed to exist today.

## Three-Surface impact (CLI ↔ MCP parity)

No new facade, MCP action, or CLI flag. Existing index/sync/watch paths share the same
coordinator and failure reasons. Python callers supplying retained candidates must
obtain bound candidates; this admission change is part of the RFC decision. Public
read-only snapshot tokens remain governed by RFC-0022 and are not writer leases.
The error/retry fields and watch diagnostic above must be introduced on equivalent
CLI/MCP routes together and covered by the existing parity contracts and real CLI tests.

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
- [ ] Released calls without candidates remain valid; latest-artifact surface audit and
  migration notes respect the major-release boundary without silently rebinding old input.
- [ ] Cross-process exclusion covers every managed write route and full operation lifetime.
- [ ] Late cleanup cannot remove another operation's data or certification, including ABA.
- [ ] Every independently mutable canonical table has recoverable ownership; cross-file
  rewrites and global metadata are covered, not only `ast_index`.
- [ ] Killed `writing` owners are recognized only after exclusion is acquired; readers
  reject both non-complete phases and retained capture never holds an unbounded lease.
- [ ] Typed admission fields, CLI exit 1, watcher backoff, and no-retry cases match
  exactly across Python, CLI, and MCP.
- [ ] Crash, timeout, cancellation, replacement, and full rebuild scenarios pass natively.
- [ ] CLI↔MCP parity and existing read-only source-evidence contracts remain green.
- [ ] Measured write cost and feedback latency published without an unsupported SLA claim.
- [ ] Relevant codemaps, migration notes, and recovery guidance updated with implementation.

## Deferred / open questions

This RFC does not establish industry leadership or instantaneous feedback. Benchmark
admission and pending RFC-0031 verification execution remain separate work.

1. Accept revision-bound candidates and schema 18, including explicit rejection of
   unbound candidates from the unreleased develop interface? The published v1.29.5
   no-candidate call signatures must remain supported; no release is authorized here.
2. Select the isolated storage protocol explicitly, including custom-path/reporting
   compatibility and active-state isolation instead of in-place old-write rejection?
3. Resolve selector errors, native publication, consumer inventory, and active-write
   guard feasibility before implementation; no experiment waives these requirements.
