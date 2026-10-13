# RFC-0032 feasibility study — decision memo

- **For**: RFC-0032 owner (accept / revise / reject decision)
- **Date**: 2026-10-13
- **Base**: `origin/develop` @ `8ae31232` (contains #1421 `349ae3a8`; shipped since v2.0.0)
- **Environment (measured)**: Windows 11 Enterprise 10.0.26200, NTFS, Python 3.12.9,
  SQLite 3.47.1 (`sqlite3.sqlite_version`), `LongPathsEnabled=1`
- **Scope**: feasibility only. No change under `tree_sitter_analyzer/` or `tests/`, and
  RFC-0032 itself is not edited. All probes ran against disposable fixture projects in
  a scratch directory outside the repository. No real `.ast-cache` was touched.
- **Raw records**: [`observations.jsonl`](observations.jsonl) holds one JSON object
  per experiment, with local paths redacted to `<scratch>`. Following the existing
  `rfcs/evidence/` convention (data records only, no scripts), the probe scripts are
  not committed. The core scenario is reproduced inline below.

## 0. Headline: the RFC's premise is out of date

RFC-0032 was last updated on 2026-09-09 (#1412). That same day **#1421 ("isolate default AST
index publication and readers")** merged. It became part of the **released v2.0.0 (2026-09-17)**,
v2.1.0 and v2.2.0 (latest GitHub release, 2026-09-18). #1421 adds a copy-on-write generation
store (`cache/generation_store.py`). Each write builds a private copy, and publication is a
compare-and-set of the parent selector under a cross-process lease. That design is the RFC's
"isolated storage protocol", but it lives at `.ast-cache/index-generations/`, not at
`L + ".tsa-v18"`. It covers **the default locator only**. The RFC text predates it, which
invalidates several of its claims:

| RFC statement | Measured state on develop / v2.x |
|---|---|
| "latest release v1.29.5; no candidate surface released" | Latest is **v2.2.0**. `IncrementalSync.sync(candidate_snapshot=...)` is in v2.2.0, so the candidate parameter **is released**. |
| Major version still pending | v2.0.0 already shipped the default-path `db_path` relocation and the read-only `get_conn()` for published generations. The v2.0.0 CHANGELOG does not mention it. |
| Fix needs in-place schema 18 + triggers | The default route is already fenced without triggers (E1, E1b). `CURRENT_SCHEMA_VERSION` is still 17. |

The obsolete-writer bug is **therefore real but narrower** than the RFC states. It
reproduces only on routes that still write in place: custom `db_path`, and the default
locator before the first publication.

## 1. Per-gate verdicts

| Gate (RFC lines) | Verdict | One-line evidence |
|---|---|---|
| RED baseline: obsolete replay deletes newer rows | **REPRODUCED** (custom + legacy-default routes); **FENCED** (published default route) | E1/E1b: custom/legacy keep `files a.py,b.py → a.py`, graph state `built=1 → 0`, dump changed 17 lines, process exit 0. Managed route: `Superseded: INDEX_GENERATION_SUPERSEDED`, dump identical. |
| Write-guard feasibility incl. trusted-schema and FTS (337-422) | **INFEASIBLE as specified** (in-place SQL triggers); **FEASIBLE-WITH-REVISION** (generation CAS, already shipped) | E2: UDF trigger → `unsafe use of tsa_admitted()` under `trusted_schema=OFF`; FTS5 → `cannot create triggers on virtual tables`; temp-table identity → `cannot reference objects in database temp`; state-only trigger lets an obsolete writer through. The generation CAS needs no trigger, and FTS works on published generations (E5). |
| Crash / ABA (`phase=writing`) | **FEASIBLE** (generation route); RFC phase machinery unnecessary there | E3: killing the lease holder lets the next publish succeed in 0.31 s. Killing mid-build leaves the active selector unchanged and leaves an orphan generation dir (no GC). ABA with identical bytes is still fenced (E1 identical). |
| Custom-path compatibility (419) | **FEASIBLE-WITH-REVISION** | No CLI/MCP route opens a custom path (grep: only internal private writables). The concern is therefore Python-API-only. `GenerationStore` at `L + ".tsa-v18"` works and fences replay on Windows without creating `L` (E4.6). Relocating it changes released `db_path` / `get_conn()` behaviour. |
| Selector error / parity details (419) | **FEASIBLE-WITH-REVISION** | E5: busy writer → CLI exit 1 / MCP `error: "Sync failed: OperationalError: database is locked"`, with no `error_code`, after a 5.5 s wait. Typed fields are additive and the exit code is unchanged. |
| Native publication (Windows) | **FEASIBLE-WITH-REVISION — shipped defect found** | E4.2: concurrent reader + publisher → **1001/2000 publishes failed `PermissionError [WinError 5]`** and 4557 reader `PermissionError`s. E4c: POSIX-semantics rename + `FILE_SHARE_DELETE` readers → **0/2000** failures, 0 read errors, 0 torn reads. |
| Native paths (Windows) | **FEASIBLE** | Case alias and 8.3 short-name alias resolve to the same locator and read the published generation. A junction storage dir is rejected (`INDEX_GENERATION_PATH_UNSAFE`). A 433-char generation path publishes. |
| Public read connection escape (105-128) | **FEASIBLE-WITH-REVISION — shipped defect found** | E5: on a published generation, `get_conn()` rejects a direct DELETE, but `ATTACH ... mode=rw` deleted 1 row. New readers then see an **empty index**. E5b: a read-only file attribute after seal blocks it and keeps `get_conn()` a `sqlite3.Connection`. |
| Major version (124) | **NOT REQUIRED** for the recommended slices 1-6; **REQUIRED (v3)** only for the optional slice 7 | See §5. |

## 2. Evidence (commands and raw results)

All runs used `.venv\Scripts\python.exe` from this worktree after `uv sync --all-extras`, with
`TMP/TEMP` pointed to the scratch directory. Each record below is a line in `observations.jsonl`.

### E1 / E1b — RED baseline (sequential and two-process replay)

Scenario (RFC Motivation): index `a.py` → capture `C_old` → add `b.py` → complete a newer sync
→ replay `C_old`. Core reproduction (custom route):

```python
cache = ASTCache(root, custom_db)          # custom route; ASTCache(root) = legacy/managed
sync(cache)                                # IncrementalSync(cache).sync(..., source_scope=SCOPE)
old = build_index_candidate_snapshot(root, max_files=..., exclude_patterns=..., walk_fn=..., language_fn=...)
(root / "b.py").write_text("def beta():\n    return 1\n")
sync(ASTCache(root, custom_db))            # newer complete index: a.py, b.py
sync(ASTCache(root, custom_db), old)       # obsolete replay
```

| Route | Replay outcome | Files after | `ast_call_graph_state` | Dump preserved |
|---|---|---|---|---|
| custom `db_path` | returned `errors=1` | `a.py` (b.py **deleted**) | `built 1 → 0`, extra row | no (17 lines) |
| default, no selector (direct Python) | returned `errors=1` | `a.py` (b.py **deleted**) | `built 1 → 0` | no (17 lines) |
| default, published generation | `Superseded: INDEX_GENERATION_SUPERSEDED` | `a.py, b.py` | unchanged | **yes** |
| custom, identical bytes (ABA) | returned `errors=0` | `a.py` | rewritten | no (3 lines) |
| published, identical bytes (ABA) | `Superseded` | `a.py` | unchanged | **yes** |

E1b repeats this with two real processes. The child captures, waits on a barrier, then writes.
Custom route: child exit 0 with `errors=1`, b.py deleted. Published route: child raises
`Superseded` and the dump is preserved. The replay deletes data first and reports
`errors=1` afterwards: the manifest certification fails *after* the delete.

Reachability of the vulnerable legacy route: `ensure_indexed()` on a fresh project (used
by `auto_index`, `metrics`, `refactor`, `visualization`, `incremental_sync` MCP tools)
writes **legacy `.ast-cache/index.db` in place** and publishes no selector (E5,
`ensure_indexed_fresh.published_selector=false`). `FileWatcherDaemon` on a custom path is
also in-place (`_default_generation` is set only when `_uses_project_mirror`).

### E2 — in-place SQLite guard primitives (SQLite 3.47.1, default `trusted_schema=1`)

| Probe | Result |
|---|---|
| Python UDF in trigger, `trusted_schema=ON` | ok |
| same, `trusted_schema=OFF` | `unsafe use of tsa_admitted()` |
| old client without the function | `no such function: tsa_admitted` (fails closed for ordinary tables only) |
| trigger on FTS5 table | `cannot create triggers on virtual tables` |
| old client writes FTS5 | ok (unguarded) |
| main trigger reading `temp` identity table | `trigger gt cannot reference objects in database temp` |
| state-only trigger (`ws.op IS NULL`) while new owner active | obsolete writer **passes** |
| cooperative CAS (`BEGIN IMMEDIATE; UPDATE ws ... WHERE revision=?`) with FTS insert, `trusted_schema=OFF` | newer commits; obsolete → `INDEX_CANDIDATE_SUPERSEDED`, dump preserved, no open transaction |
| `mode=ro` + `ATTACH mode=rw` | update succeeds (value 3 seen independently) |

These match the RFC's macOS/3.50.4 observations on a second platform and SQLite version.
A trigger cannot carry per-connection owner identity without a UDF. A UDF is unsafe under
`trusted_schema=OFF`, and FTS5 cannot be triggered at all. In-place enforcement against
non-cooperating writers is therefore not achievable with SQLite primitives. Only
cooperative CAS works, and it fences TSA writers of the same version only.

### E3 — killed writers (Windows `TerminateProcess`)

| Case | Result |
|---|---|
| Another process holds the publication lease | contender: `OperationalError: database is locked` after 5.53 s (raw, untyped) |
| Lease holder killed | active selector unchanged; next publish 0.31 s, contains a.py + b.py |
| Writer killed after `begin()` (mid-build) | active selector unchanged; next publish 0.30 s; **3 generation dirs** on disk (orphan retained, no GC) |

### E4 — native Windows storage protocol

- `os.replace(tmp, active.json)` while any reader holds `active.json` open: `PermissionError [WinError 5]`
  for both `open()` and `os.open()` handles.
- Real `read_selector` loop vs real `_write_atomic` loop (2000 publishes): **1001 publish failures,
  4557 reader `PermissionError`s** vs 3630 successful reads. Readers get `PermissionError` and
  not `InvalidGenerationSelector`, so `ASTCache(root)` construction can fail during any
  watcher publication.
- Mitigations (E4b/E4c, 2000 publishes each, disposable files):

| Variant | Publish errors | Read errors | Torn reads |
|---|---:|---:|---:|
| baseline `os.replace`, plain readers | 1375 | 26212 | 0 |
| `FILE_SHARE_DELETE` readers, `os.replace` | 1354 | 0 | 0 |
| bounded retry (20× linear backoff) on both sides | 2 | 0 | 0 |
| `FileRenameInfoEx` `REPLACE_IF_EXISTS\|POSIX_SEMANTICS` + plain readers | 1562 | 1985 | 0 |
| **`FileRenameInfoEx` POSIX + `FILE_SHARE_DELETE` readers** | **0** | **0** | **0** |

  A held share-delete reader keeps reading the old bytes after replacement, while new opens see the
  new bytes. This is POSIX rename semantics. Both sides must change, and retry alone is not a proof.
- Long paths: 350-char root → 433-char published `index.db`. Plain SQLite at 462 chars is OK
  (`LongPathsEnabled=1`; machines with it disabled were not tested).
- Aliases: upper-case and 8.3 short-name spellings of the root give the same `logical_index_path`
  and read the published generation. A junction at `.ast-cache/index-generations` is rejected:
  `ValueError: INDEX_GENERATION_PATH_UNSAFE`.
- Custom locator: `GenerationStore(root, L + ".tsa-v18", logical_path=L)` publishes, rejects an
  obsolete candidate (`Superseded`), and creates no file at `L`. The layout is `active.json`,
  `generations/<32hex>/index.db{,-wal,-shm}`, `publication.lock.db`.
- Directory durability: `_flush_directory` is a no-op on Windows and `os.replace` does not
  request `MOVEFILE_WRITE_THROUGH`. NTFS gives atomic replacement here, **not proven
  power-loss durability**. Wording must say so.

POSIX/macOS (reasoning, not measured here): `rename(2)` replaces atomically while readers hold
the old inode, so the E4 race does not exist. Directory `fsync` is implemented. On macOS,
`fsync` does not force media flush (`F_FULLFSYNC`), so a durability claim needs that or must be
limited. `/var` → `/private/var` aliases converge because `logical_index_path` applies
`realpath` internally. This is consistent with CLAUDE.md "Deliberate design decisions" §2:
**do not** move canonicalisation into `BaseMCPTool`. Native Linux/macOS CI must confirm both points.

### E5 — released public surface

- Published generation: `db_path` = `.ast-cache\index-generations\generations\<id>\index.db`.
  `fts_search("alpha")` returns the symbol. Direct `DELETE` → `attempt to write a readonly
  database`. **`ATTACH ... mode=rw` + `DELETE FROM w.ast_index` deleted 1 row. Afterwards both
  the generation and a fresh `ASTCache(root)` report zero files.**
- E5b: `chmod(db, S_IREAD)` after seal → `get_conn()` is still `sqlite3.Connection`, reads and FTS OK,
  ATTACH-rw DELETE → `attempt to write a readonly database`, and the next publication still
  copies from the read-only parent. On POSIX, 0444 blocks `O_RDWR` for the non-root owner. Root,
  or code that chmods back, is outside the boundary the RFC already declares (RFC lines 111-112).
- Busy writer through real routes: `python -m tree_sitter_analyzer --incremental-sync --project-root R`
  → exit **1**, stdout `{"success": false, "verdict": "ERROR", "error": "Sync failed: OperationalError: database is locked"}`.
  MCP `CodeGraphIncrementalSyncTool.execute({"mode":"sync"})` gives the same payload with
  `error_code/retryable/next_action = null`.

## 3. Recommended mechanism

**Adopt the shipped #1421 copy-on-write generation store as the single write fence, and
withdraw the in-place trigger/`ast_writer_state` design for managed storage.**

- The authority is the selector identity `(canonical_root, logical_path, storage_epoch,
  generation_id)`. Admission is a CAS against the current selector under the publication
  lease. It is not a content hash or a timestamp, so it is ABA-safe (E1 identical). It
  needs no SQL guard, so `trusted_schema` and FTS5 do not matter.
- A crash never leaves a published `phase=writing`. Unpublished generations are unreferenced
  garbage, so recovery is simply "next writer". The RFC's phase/recovery machinery is needed
  only for in-place routes.
- Extend the fence to the routes that still write in place:
  1. **Default locator before first publication**: make every mutating default route
     (`ensure_indexed`, `index_project`, `index_file`, `invalidate`, direct `IncrementalSync`)
     bootstrap a generation, as the watcher already does. Do not write legacy `index.db`.
  2. **Custom `db_path`** (Python-only): non-breaking now. Add a persistent singleton revision
     row and do cooperative CAS in the writer's `BEGIN IMMEDIATE` transaction (E2e), binding
     retained candidates to it. This fences same-version TSA writers. Old-version writers stay
     out of scope ("no mixed-version live-write compatibility", RFC line 263). Relocating
     custom storage to `L + ".tsa-v18"` is optional, at v3.
- Fix the two shipped defects: the Windows selector race (POSIX rename + share-delete readers,
  fail closed with a typed busy error where `FileRenameInfoEx` is unsupported), and the ATTACH
  escape (read-only attribute on sealed generations).

## 4. Proposed RFC text revisions (wording only; not applied)

1. Replace **"Released-interface boundary"** paragraphs 1-3 with:
   > On 2026-10-13 the latest release is v2.2.0. Since v2.0.0, `IncrementalSync.sync`
   > publicly accepts `candidate_snapshot`, and default-locator caches route through the
   > generation store from #1421. On a published default cache, `db_path` reports the active
   > generation file and `get_conn()` returns a read-only connection. Rejecting unbound
   > candidates on the default route is already released behaviour. On custom paths it
   > would be new and requires a deprecation period.
2. Replace **"Persistent identity and schema migration"** and **"Write fence and cleanup"** for
   managed storage with:
   > The write fence for default-locator storage is the generation selector CAS defined by
   > `GenerationStore.publish`. No SQL triggers or application-defined guard functions are
   > installed. Measured on SQLite 3.47.1 and 3.50.4, they are unsafe under
   > `trusted_schema=OFF`, cannot cover FTS5, and cannot carry connection identity. Schema 18
   > adds only `ast_writer_state(id=1, cache_uuid, revision)` for in-place custom databases.
   > Every TSA mutation there advances `revision` by compare-and-set inside its own
   > `BEGIN IMMEDIATE` transaction.
3. In **"Proposed isolated storage protocol"** item 1, change the namespace to the shipped
   `.ast-cache/index-generations/` for the default locator. Keep `L + ".tsa-v18"` only for a
   future custom-locator option.
4. In **"Crash recovery"**, add:
   > Generation routes have no persisted writing phase: an unpublished generation is
   > unreferenced and the next admitted writer proceeds. Bounded retirement of unreferenced
   > generations is required; until it exists, orphan generations are retained on disk.
5. In **"Typed admission failures"**, add the mapping:
   - `INDEX_GENERATION_SUPERSEDED` and `INDEX_GENERATION_SOURCE_CHANGED` → `INDEX_CANDIDATE_SUPERSEDED`
   - lease timeout and Windows sharing violation → `INDEX_WRITER_BUSY`
   - `INDEX_GENERATION_SELECTOR_INVALID`/`_MISSING`/`_PATH_UNSAFE` → `INDEX_RECOVERY_REQUIRED`

   The existing `error` text and exit 1 are preserved.
6. Add a **native publication** clause:
   > On Windows, selector replacement uses `FileRenameInfoEx` with POSIX semantics and readers
   > open the selector with `FILE_SHARE_DELETE`. If unsupported, publication fails closed with
   > `INDEX_WRITER_BUSY`. Windows replacement is atomic but not claimed power-loss durable.
7. Replace the **read-session contract** with:
   > Sealed generation files are marked read-only at the OS level before publication.
   > `get_conn()` keeps returning `sqlite3.Connection`. Code with the same OS authority that
   > alters file permissions is outside the boundary.

   The full read-session type remains a deferred v3 option.

## 5. Major-version verdict

**No major release is needed for the recommended fix (slices 1-6).** Every change in those
slices is either already released (v2.0.0 default isolation and default-route unbound
rejection), additive (`error_code`/`retryable`/`retry_after_ms`/`next_action` fields,
`last_admission_error`, a new schema table), or a bug fix that keeps the type contract
(read-only attribute, Windows rename). CLI exit codes stay `_exit_code_for` → 1 on failure.

A **v3 major** is required only if the owner wants any of:
- (a) physical relocation of custom `db_path` storage, which changes the meaning of `db_path`
  and stops updating the file at `L` for direct SQLite clients;
- (b) a non-`sqlite3.Connection` read session from `get_conn()`;
- (c) hard rejection of unbound candidates on custom paths.

Recommend deferring (a)-(c). Separately, v2.0.0 CHANGELOG should gain a retroactive
note about the default-path relocation. That is a docs follow-up, not part of this RFC.

## 6. Implementation slice plan (each independently mergeable, RED-first)

| # | Slice | RED test first | Breaking? |
|---|---|---|---|
| 1 | Default mutating routes before first publication bootstrap a generation (`ensure_indexed`, `index_project`, `index_file`, `invalidate`, direct `IncrementalSync`) | `ensure_indexed` on fresh project publishes selector; E1 legacy replay raises `Superseded` and dump preserved | no |
| 2 | Windows selector publication: POSIX-semantics rename + share-delete readers; typed busy fallback | E4.2 contention loop: 0 publish / 0 read errors (Windows CI); unsupported-FS path → `INDEX_WRITER_BUSY` | no |
| 3 | Seal marks generation read-only | E5 ATTACH-rw DELETE on published generation must fail; reads, FTS, next publish unchanged | no |
| 4 | Typed admission errors (`IndexWriteAdmissionError`) on CLI/MCP/watcher with RFC table + §4 mapping | E5 busy payload carries `error_code=INDEX_WRITER_BUSY`, `retryable=true`; CLI exit stays 1; parity test | additive |
| 5 | Custom-path cooperative revision CAS (schema 18 `ast_writer_state`), candidate bound to revision | E1/E1b custom replay: `INDEX_CANDIDATE_SUPERSEDED`, dump preserved, no open transaction | additive schema |
| 6 | Bounded retirement of unreferenced generations (no reader pin, not active, identity verified) | E3 mid-build kill: orphan count returns to 1 after retirement; active/pinned never removed | no |
| 7 | *(optional, v3)* custom locator → `L + ".tsa-v18"` generations; read-session type | E4.6 as contract tests; migration notes | **yes** |

Slices 1 and 2 close the remaining replay route and the shipped Windows defect, so they come first.
Each slice carries its own native Windows/Linux/macOS CI proof, per RFC Test plan.

## 7. Owner decisions remaining

1. Accept the revision in §3/§4: the generation CAS is the fence, and in-place triggers are withdrawn.
2. Pick the custom-path policy: cooperative CAS now (recommended), relocation at v3, or both.
3. Decide whether slices 2 and 3 land as standalone bug fixes now, outside RFC acceptance. They are
   shipped defects in v2.x.
4. Retention policy for orphan generations (slice 6): count/age bound vs. reader-pin-only.
5. Durability claim level: atomic-only on Windows/macOS, or invest in `MOVEFILE_WRITE_THROUGH` /
   `F_FULLFSYNC`.

## Assumptions and limits

- Measured on one Windows/NTFS host. POSIX/macOS statements are reasoning to be confirmed in CI.
- The E4 contention loops are adversarial tight loops that bound worst-case behaviour. They are
  not real-world frequencies.
- PyPI was unreachable from this network (TLS blocked). Release state comes from `gh release list`
  (v2.2.0 latest, 2026-09-18) and git tags.
- Schema-18 forward compatibility with an already-running v2.2 process is assumed (extra table
  only) and was not exercised. Slice 5 must test it.
