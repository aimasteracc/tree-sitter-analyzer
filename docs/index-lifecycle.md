# Index Lifecycle Guide

> **The #1 user trap:** per-query CLI calls (e.g. `--callees`) build only a
> small on-demand partial cache. Cross-project queries — Hyphae selectors,
> symbol search across the whole project, callers/callees trees — need the
> **full** index. Build it once; sync after edits.

---

## Two Separate Indexes

TSA maintains two distinct caches:

| Cache | Location | Built by | Purpose |
|---|---|---|---|
| AST symbol index | `.ast-cache/index-generations/generations/<id>/index.db` (SQLite) | `action=full`, `action=auto`, `action=sync` | Symbol definitions, call edges, type info — used by callers/callees, search, Hyphae selectors |
| Project structure index | `.tree-sitter-cache/project-index.json` | `action=build` | Directory/language map, entry points, README excerpt — used by `project` facade |

Both directories are listed in `.gitignore` and are never committed.

---

## The Four Index Operations

### `action=build` — cold-build the project structure index

Scans the file tree, detects languages, finds entry points, extracts a README
excerpt, and writes `.tree-sitter-cache/project-index.json`.

**Use when:** starting fresh on a new project, or after large directory
restructures. This is the lighter of the two indexes (seconds, not minutes).

MCP:
```json
{ "action": "build" }
```

CLI equivalent:
```bash
uv run python -m tree_sitter_analyzer --build-project-index
```

---

### `action=full` — complete AST reindex

With `mode=full`, reparses source files into a private database and publishes it
only after certification succeeds. The `active.json` selector binds default readers
to one immutable generation. Failed or superseded builds leave the prior generation
unchanged. `sync` and watcher updates use the same publication boundary.

Every other write to the default cache (`auto`, `ast_cache` index/invalidate,
persisted constraint checks, Python `index_file`/`index_project`/`IncrementalSync`)
also publishes a generation, including the first write on a never-published project
(RFC-0032 slice 1, #1554). No write creates or updates the legacy
`.ast-cache/index.db`. If a legacy file already exists, the first write copies it
into the first generation; read-only calls never create or copy one.
A write still publishes when the only failures are stable per-file failures
(`failure_kind: stable`: missing grammar or a parse failure on the captured bytes).
Those files stay unindexed and uncertified, so completeness stays partial or
unknown. Any transient failure keeps the previous generation active.

Legacy `.ast-cache/index.db` remains separate, so old writers cannot modify the
published generation. TSA read connections and in-progress builds pin their
generation (`index-generations/pins/`, RFC-0032 slice 6). Each publication then retires,
within 1 s, every unpinned inactive generation except the 2 newest sealed ones under
24 h old, including builds of killed writers. Unverified directories (wrong name, link
or reparse point) are never touched. Use the status response
`cache_path` or `cache.generation_routing.resolve_index_path()` for direct reads.

**Use when:** after a `git pull`, rebase, or large refactor — any time many
files changed and you want guaranteed consistency.

MCP:
```json
{ "action": "full", "mode": "full" }
```

> ⚠️ Without `"mode": "full"` the tool **defaults to `incremental`** — unchanged-but-stale rows survive. For a guaranteed from-scratch rebuild always pass the mode explicitly.

```json
{ "action": "full" }   // mode defaults to "incremental"
```

A full-index operation walks the project once and freezes one immutable
candidate snapshot for both its AST-cache and incremental-sync phases. This
keeps ordering, exclusions, and the `max_files` boundary identical across the
operation. Existing selected files that change or disappear after the snapshot
are skipped with a `changed_during_run` reason and produce a `WARN` verdict;
files created afterward wait for the next operation. Snapshot and phase
reconciliation counters are returned in `candidate_snapshot`.

An incremental refresh re-resolves only the call edges whose resolution inputs
changed (#1696). The scope is:
- the changed files' own edges;
- edges bound into the changed files;
- edges named after a definition, signature, base class, return annotation,
  module singleton or import binding that changed;
- the call edges of files that depend on those names, through imports,
  aliases, star imports, module aliases, subclasses and typed exports.

A body-only edit therefore re-resolves only the changed file and the edges
bound into it. The decision is reported as `backfill_scope`, both in the sync
result and in the `stats` returned by `index_project`:
- `mode` is `scoped` or `full`;
- `reason` says why;
- the remaining fields count the scope's files, names and edges.

The refresh falls back to the full backfill when it cannot bound the scope:
- the previous backfill did not converge (`COLLECTOR_NOT_ARMED`);
- a write was not recorded (`CHANGED_FILE_NOT_RECORDED`);
- the changed set is unknown (`CHANGED_FILES_UNKNOWN`);
- computing the scope failed (`SCOPE_COMPUTATION_FAILED`);
- the scope exceeds half of all call edges (`SCOPE_TOO_LARGE`).

Either way the result is the same index as a fresh full build.

CLI equivalent:
```bash
# Guaranteed full rebuild (recommended after pull/rebase):
uv run python -m tree_sitter_analyzer --full-index --full-index-mode full
# Bare --full-index defaults to --full-index-mode incremental:
uv run python -m tree_sitter_analyzer --full-index
```

---

### `action=sync` — fast incremental sync

Compares each file's SHA-256 content hash against the stored value. Only files
whose hash differs are re-parsed. Typically completes in seconds on large repos.

**Use when:** after editing a few files — the everyday post-edit operation.

MCP:
```json
{ "action": "sync" }
```

CLI equivalent:
```bash
uv run python -m tree_sitter_analyzer --incremental-sync
```

To preview what would be re-indexed without writing:
```bash
uv run python -m tree_sitter_analyzer --incremental-sync --incremental-sync-mode changes
```

---

### `action=auto` — transparent background warming

Checks whether the index is warm and triggers indexing if not. Other
codegraph tools call this internally on first use; `action=auto` gives
explicit control. Modes: `status` (read-only check), `warm` (index if not
warm — idempotent), `reset` (force re-index on next access).

**Use when:** you want to pre-warm the cache before a batch of queries, or
check/reset the auto-index guard without running a full reindex.

MCP:
```json
{ "action": "auto", "mode": "warm" }
```

CLI equivalent:
```bash
uv run python -m tree_sitter_analyzer --autoindex --autoindex-mode warm
```

---

## `action=status` — health check

Returns: indexed yes/no, total files, total symbols, FTS5 availability, lag
vs newest source file, and error indicators. Run this before any navigation
query to decide whether to warm the cache first.

MCP:
```json
{ "action": "status" }
```

CLI equivalent:
```bash
uv run python -m tree_sitter_analyzer --codegraph-status   # indexed? schema version, FTS5, cache lag
# Raw AST-cache stats (lower level, no health verdict):
uv run python -m tree_sitter_analyzer --ast-cache --ast-cache-mode stats
```

---

## The Trap: Partial Cache vs Full Index

Per-query CLI calls like `--callees MyClass.method` build **only** a partial,
on-demand cache covering the files needed to answer that single query. This
cache may hold only tens of files out of thousands.

**Queries that require the full index:**

- Hyphae selectors (`search action=subscribe` / `search action=query`)
- Project-wide symbol search (`search action=symbol`)
- Caller/callee trees spanning more than the immediate file

**What you see with a partial or missing index:**

Since PR #497, the Hyphae selector tool returns an explicit
`index_state` field and a `WARN` verdict when the index is absent or empty:

```
Index missing, empty, or unreadable. Run the `index` tool with
action=auto to build the cache (if this persists, check
.ast-cache permissions).
```

When the index is present but small (e.g. only 1 file indexed from a
previous on-demand call), the tool reports the actual `indexed_files` count so
you can judge whether zero results mean "no matches" or "index incomplete".

**Decision guide:**

```
Editing a few files?        → action=sync   (fast, content-hash diff)
Just pulled / rebased?      → action=full   (full reindex for consistency)
First time on project?      → action=full   (then action=build for structure)
Hyphae/search returning 0?  → action=status → if missing, action=auto mode=warm
```

---

## Lag and Consistency

The file-watcher debounces ~500 ms after writes. Do not re-query the index
immediately after editing a file in the same CLI invocation — the index
reflects the state at parse time.

`action=status` includes a `lag_seconds` field showing the gap between the
newest source mtime and the cache timestamp. A lag above a few minutes on an
active codebase is a sign to run `action=sync`.

---

## Quick Reference

| Goal | MCP | CLI |
|---|---|---|
| Check index health | `index action=status` | `--ast-cache --ast-cache-mode stats` |
| Cold-build project structure | `index action=build` | `--build-project-index` |
| Full reindex (post-pull) | `index action=full` | `--full-index` |
| Incremental sync (post-edit) | `index action=sync` | `--incremental-sync` |
| Pre-warm / auto-index | `index action=auto mode=warm` | `--autoindex --autoindex-mode warm` |
