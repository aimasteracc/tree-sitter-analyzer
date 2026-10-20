# RFC-0039 feasibility study — decision memo

- **For**: the RFC-0039 owner (accept / revise / reject).
- **Date**: 2026-10-20.
- **Base**: `origin/develop` @ `6015a214`, which contains #1714 (scoped backfill) and #1715 (mtime-only no-op).
- **Environment**: Windows 11 Enterprise 10.0.26200, NTFS, Python 3.13, SQLite 3.47.
  - The workstation was shared with other agents' runs, so timings are ±30%.
  - All comparisons are made within one run on the same connection, so the relative numbers are reliable.
- **Scope**: feasibility only.
  - No change under `tree_sitter_analyzer/` or `tests/` is committed.
  - Dataset B ran a one-line scratch patch, described below. It lived in a disposable worktree and was not committed.
- **Raw records**: [`observations.jsonl`](observations.jsonl) holds one JSON object per experiment.
  - Line 1 is the environment.
  - Each dataset then has a `baseline` record and eight `edit` records (`"dataset": "A"` or `"B"`).
  - Following the `rfcs/evidence/` convention (data only), the probe script is not committed. Its method is described in §2.

## 1. Headline

| Question | Answer |
|---|---|
| Does an incremental per-file Merkle root equal a full recompute? | **Yes, 16/16.** Eight 1-file edit kinds × two datasets gave equal roots. 0 of 15,091 leaves differed in every case. |
| Hashing cost per 1-file refresh, today | `index_fingerprint` takes **9.1–14.6 s** (B) / 10.4–21.6 s (A) over 511,915 rows. |
| Hashing cost per 1-file refresh, incremental (option A of the RFC) | **0.89–2.15 s** (B). **0.04–0.99 s** if the FTS5 projection is bound by `ast_symbol_projection_state` instead of being hashed (§3.3). |
| Is today's index content stable across a 1-file refresh? | **No.** Every refresh rewrites `ast_index.certified_at` for all 2,565 files (A: 2,573–2,609 leaves change per refresh). With that fixed (B), 8–45 leaves change. |
| SHA-256 of the sealed generation file (option B of the RFC) | **0.41–0.86 s** for 363 MB. |

## 2. Method

1. **Index.** I built one index of this repository at `6015a214`: 2,565 files and 511,915 rows in fingerprinted tables. Only this one index existed on disk.
2. **Baseline.** I computed the full Merkle leaves from the published generation, read-only. I also computed today's `index_fingerprint` and checked it against the stamped manifest: `current_fingerprint_matches_manifest: true`.
3. **Edits.** I applied eight 1-file edits in sequence. Each one ran a real `IncrementalSync.sync()` of the default route:

   | Edit | File |
   |---|---|
   | `body_only` | `cache/write.py` |
   | `signature` | `file_change_time.py` |
   | `add_method` | `LanguagePlugin` |
   | `base_class` | `DefaultExtractor` |
   | `import_alias` | `cache/query.py`: the alias and its use |
   | `return_annotation` | `build_resolver_context` |
   | `add_file` | new module |
   | `delete_file` | the same module |

4. **Dirty tracking.** When the sync armed its writer connection, the probe installed TEMP `AFTER INSERT/UPDATE/DELETE` triggers on every ordinary fingerprinted table.
   - Each trigger records `(table, file_path)`, or `(table, '*')` for tables without `file_path`.
   - `UPDATE`s that leave every column unchanged are skipped (`WHEN NOT (OLD.c IS NEW.c AND …)`).
   - The FTS5 virtual table cannot carry triggers. Triggers on its shadow tables crashed the process (`0xC00000FD`, a stack overflow inside FTS writes). FTS was therefore handled without triggers:
     - the virtual table's groups are recomputed for every file dirtied in any table;
     - the shadow tables are re-hashed whole.
5. **Measurement at stamp time.** The probe wrapped `stamp_full_index_manifest` and measured on the same connection and the same uncommitted state the stamp certifies:
   - `current_fingerprint_s`: today's full `index_fingerprint`. `current_fingerprint_equals_stamped: true` confirms it is the value then stamped.
   - `merkle_full_s`: all leaves recomputed and folded into a root.
   - `incremental_s`: previous leaves plus the recomputed dirty leaves, folded into a root.
     - A table with more than 25% of its groups dirty is re-scanned in one ordered pass.
     - The root fold is included.
   - `roots_equal` / `mismatched_groups`: the incremental root against the full Merkle root.
   - `generation_file_sha256_s`: SHA-256 of the newly published generation file.
6. **Leaf and root definitions.**
   - **Leaf**: SHA-256 over the typed rows of one `(table, file_path)` group, ordered by `file_path` and then by every query-visible column. It uses the same `_typed` / `_frame` encoding as `index_fingerprint`.
   - **Root**: SHA-256 over the sorted tables. For each table it frames the name, schema SQL, columns, and the sorted `(group, leaf)` pairs.
7. **Datasets.**
   - **A** runs develop as-is.
   - **B** adds a single scratch change to `IncrementalSync`: unchanged files keep their `certified_at`, while new, updated and still-NULL files are stamped as before. Readers only test `certified_at IS [NOT] NULL` (`index_snapshot.py:874`, `index_status_response.py`, `_ast_cache_index_mixin.py:426`), so the epoch value carries no reader semantics.

## 3. Results

### 3.1 Equality: incremental root equals a full recompute

All 16 edit records have `roots_equal: true` and `mismatched_groups: 0` (15,091 groups). They also have `current_fingerprint_equals_stamped: true`, so the measured state is exactly the certified state.

The dirty-tracking assumption held on the default sync route. Every row write that changed content went through the armed writer connection. No write was missed, including:
- the #1696 scoped-backfill resets and restores;
- the Synapse and second-pass updates;
- deletion.

### 3.2 Cost per refresh (B, seconds)

| edit | dirty groups | leaves changed | incremental | of which FTS | full Merkle | today's `index_fingerprint` |
|---|---|---|---|---|---|---|
| body_only | 155 | 26 | 1.59 | 1.15 | 6.71 | 9.95 |
| signature | 15 | 9 | 0.89 | 0.75 | 5.99 | 10.98 |
| add_method | 509 | 45 | 1.79 | 0.81 | 7.05 | 10.27 |
| base_class | 509 | 44 | 1.59 | 0.80 | 6.24 | 9.14 |
| import_alias | 147 | 19 | 1.47 | 1.00 | 7.30 | 11.57 |
| return_annotation | 311 | 31 | 2.15 | 1.35 | 6.97 | 12.70 |
| add_file | 16 | 8 | 1.10 | 1.06 | 8.33 | 14.60 |
| delete_file | 16 | 8 | 1.06 | 1.02 | 7.37 | 10.96 |

Notes:
- "Of which FTS" is the full-table re-scan of `ast_symbols_fts` plus its shadow tables (`full_table_rehash_s`). The probe also measures shadow tables alone as `shadow_rehash_s`.
- The dirty-group counts include the FTS groups derived from dirty files.
- `edges` accounts for 5–252 dirty groups but only a few changed leaves. Most of those writes are the #1696 reset-then-restore, which writes and then restores the same values.
- The root fold over about 15k leaves takes 0.02–0.06 s.

### 3.3 FTS5 is the floor of the incremental cost

`ast_symbols_fts` is a virtual table. It cannot be filtered by `file_path` without a full scan, and its shadow tables (`_data`, `_idx`, `_docsize`, `_config`) cannot be tracked. Hashing them costs 0.75–1.35 s per refresh, which is most of the incremental cost.

The FTS rows are a projection of `ast_symbol_rows`. `ast_symbol_projection_state` already holds a per-file `projection_digest`, and the snapshot capture already runs `symbol_projection_is_exact`. If the root binds FTS through those instead of hashing the FTS tables themselves, the incremental cost is **0.04–0.99 s**.

### 3.4 `certified_at` churn (A)

Dataset A shows the problem. Every refresh changes 2,565 `ast_index` leaves, one per file, because `IncrementalSync` stamps `certified_at = now()` on every unchanged file. As a result:
- an incremental scheme must re-hash `ast_index` in full on every refresh (0.14–0.33 s);
- any per-file change detector sees all files as changed.

It is a prerequisite fix regardless of the option chosen.

### 3.5 Option B: the physical digest

SHA-256 of the sealed generation file (363 MB) took 0.41–0.86 s in every record. It is cheaper than any logical hash. But it binds bytes, not rows, and it cannot be stored inside the database it hashes (RFC §Alternatives).

## 4. What this does not show

- **Untracked write paths.** The probe covered only the default `IncrementalSync` route. Not exercised:
  - the `index_project` route, with workers;
  - custom `db_path` / in-place routes;
  - `invalidate`;
  - raw SQL on other connections.

  The RFC requires a full recompute wherever the armed-connection invariant cannot be shown (writer-revision binding, §Detailed design).
- **Reader-side cost (#1710).** That cost is not measured here. The RFC's reader-memo seeding (option A, step 5) is a design proposal only.
- **Production refresh time.** `refresh_s` includes the probe's own full Merkle and extra `index_fingerprint` work (about 8–20 s per refresh), so it is not a production refresh time.
