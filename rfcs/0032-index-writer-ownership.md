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

### Published-wheel counterexample: ordinary-table guards are insufficient

A subsequent eight-route probe imports the actual v1.29.5 wheel identified above in
separate Python processes. Each old process opens its cache first; develop initializes
and certifies the same database before installing provisional denial triggers. This
is an already-open published runtime, not a second instance of develop. The ordinary
variant eagerly creates `ast_build_state`; the shadow variant additionally guards FTS
shadow tables. Both use a function-dependent `RAISE(ROLLBACK)` trigger, but the old
connection has no admission function. No schema-18 migration is claimed.

| Old runtime operation | Ordinary guards: committed dump unchanged after explicit old commit | Including shadow guards: operation / commit outcome |
|---|---|---|
| `index_file` | yes; pending transaction remains before commit | missing function / commit succeeds |
| `invalidate` | **no: FTS shadow rows changed** | `database disk image is malformed` on both |
| incremental sync | **no: FTS shadow rows changed** | `database disk image is malformed` on both |
| forced project rebuild | yes; no pending transaction | missing function / commit succeeds |

The published invalidation route changes FTS before reaching a guarded ordinary-table
statement. That statement fails during preparation with a missing function, so its
`RAISE(ROLLBACK)` body never executes. The preceding FTS changes remain committable.
Changing current entry wrappers cannot fix rollback behavior inside an already-open
old process. Ordinary-table fencing therefore fails the old-writer acceptance gate.

Adding triggers to shadow tables is also not a qualified solution: although committed
dumps were unchanged after the old connections closed in all four observations, two
operations and their subsequent commits raised `database disk image is malformed`.
That error is not a typed admission rejection, and unchanged final dumps do not prove
connection usability or safe FTS recovery. The experiment does not establish permanent
on-disk corruption either. Preserve the error and transaction-lifetime observations;
do not turn this negative experiment into an implementation recommendation.

The enforcement mechanism remains **unqualified**. Resolve old-client FTS writes,
preparation-time failures, and connection recovery before accepting a trigger-based
migration, or qualify a different publication/isolation design against these same
old-wheel scenarios. Local raw records are `/tmp/tsa-published-writer-fence-proof.json`
and `/tmp/tsa-published-writer-shadow-fence-proof.json`; scripts are temporary probes,
not shipped test or benchmark assets.

### Separate-file isolation probe and remaining design obligations

A four-route follow-up keeps each real v1.29.5 process attached to the historical
`index.db` while current develop builds `owned-index.db` through the existing
`ASTCache(..., db_path=...)` option. Sources are changed before the new build; no
source edits occur during the subsequent old-writer operation. No denial triggers
or runtime-method replacements are installed.

All four old operations (`index_file`, `invalidate`, incremental sync, forced rebuild)
succeed, commit, and change the legacy database dump. All four new database dumps
remain exactly unchanged. This establishes file separation for those SQLite routes
on this machine, not old-writer rejection or a complete migration protocol. Raw
observations are in `/tmp/tsa-published-writer-namespace-proof.json`.

This direction must resolve the following before it can replace the in-place design:

- Define one authoritative active generation for every reader and writer. Current
  pinned snapshot code still opens `index.db` and its WAL/journal names; a custom
  write path alone cannot move certification, CLI/MCP routing, or snapshot identity.
- Specify creation, publication, recovery and retirement without renaming a live
  SQLite database underneath its WAL users. Prove native Windows/Linux/macOS behavior,
  pinned hierarchy identity, hard-link/alias rejection, custom paths, and bounded
  recovery after interruption at every publication boundary.
- Scope all mutable mirrors and derived storage to the same generation. The existing
  custom-database constructor disables the project mirror, so this experiment does
  not qualify production mirror migration or isolation.
- Preserve revision admission and complete-operation ownership among new-version
  writers. Separate legacy files do not reject a stale candidate targeting the new
  database, nor fence a delayed callback in the same active generation.
- Explicitly decide legacy-file handling. Allowing an old process to modify a retired
  file differs from rejecting its writes in place. Do not silently replace the
  current acceptance criterion with that weaker statement; a revised contract must
  prove retired writes cannot become active, influence readers, or affect shared
  state before this alternative is accepted.

There is no selected separate-file schema/path protocol yet. The positive observation
justifies developing that alternative; it does not accept it, remove existing gates,
or authorize implementation or release.

### Legacy FTS name sealed by a view: narrow in-place probe

A further four-route old-wheel experiment renames the FTS virtual table to
`ast_symbols_fts_owned` and creates a read-only `ast_symbols_fts` view, then installs
the same eager ordinary-table guards. The old connection remains open throughout.
All four real v1.29.5 operations are rejected and the complete logical dump remains
unchanged after an explicit old-connection commit. `invalidate` and incremental sync
fail with `cannot modify ast_symbols_fts because it is a view`; `index_file` and forced
rebuild fail with the missing admission function. No malformed-image error occurs in
these four observations. Raw record: `/tmp/tsa-published-writer-fts-view-proof.json`.

This closes the observed FTS-before-guard hole only for the four tested routes. It
is not a selected migration. Three operations still leave a deferred transaction
before explicit commit; prove bounded new-writer progress and safe connection reuse.
The proposed view cannot transparently preserve FTS `MATCH`/control-command behavior;
new writers, search readers, schema validators and snapshot projection must agree on
the active FTS owner. Qualify fresh old-runtime connections, all lazy DDL, rollback,
trusted-schema settings, native platforms and mirrors before making a compatibility
or isolation claim. Keep the earlier failing probes: do not erase negative evidence
when a more constrained experiment passes.

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
2. The pure SQL guard feasibility gate must resolve trusted-schema, virtual-table/DDL,
   and old-client write behavior before choosing the final enforcement mechanism.
