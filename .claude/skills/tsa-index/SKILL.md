---
name: tsa-index
version: 1.0.0
description: |
  Manage the persistent AST cache / index. Refresh, force-rebuild, inspect
  cache state, diff one file's AST between commits, advise on parser readiness
  for a language. Mostly ops/infra, not daily agent work.

  Use when:
  - "Re-index the project" / "force rebuild AST cache"
  - "Why is callees returning unknown" (likely stale index)
  - "AST diff this file vs last commit" (structural diff, not text diff)
  - "What language plugins are ready / which are stubs"
  - Setting up the project for the first time (autoindex)

  Replaces: manual `rm -rf .ast-cache && reindex` + reading plugin docs.
allowed-tools:
  - mcp__tree-sitter-analyzer__ast_cache
  - mcp__tree-sitter-analyzer__ast_diff
  - mcp__tree-sitter-analyzer__codegraph_autoindex
  - mcp__tree-sitter-analyzer__codegraph_full_index
  - mcp__tree-sitter-analyzer__codegraph_incremental_sync
  - mcp__tree-sitter-analyzer__codegraph_status
  - mcp__tree-sitter-analyzer__advise_parser_readiness
  - mcp__tree-sitter-analyzer__build_project_index
  - Bash
  - Read
---

# tsa-index — Cache / index ops

> Not a daily skill. Most agents never need it. Pull when index is stale or
> a language plugin behaves oddly.

## Tool routing

| Goal                                           | Tool                    |
|------------------------------------------------|-------------------------|
| Status / stats of the AST cache                | `ast_cache` (mode=status) |
| Force rebuild                                  | `ast_cache` (mode=force)  |
| Incremental refresh                            | `ast_cache` (mode=index)  |
| Watch a directory and auto-refresh             | `ast_cache` (mode=watch_start) |
| AST-level diff of one file across commits      | `ast_diff`              |
| First-time index for a freshly-cloned repo     | `codegraph_autoindex`   |
| Full bulk reindex (large monorepo)             | `codegraph_full_index`  |
| "Is the python plugin / swift plugin ready"    | `advise_parser_readiness` |

## Procedure

### When to force rebuild

The auto-cache is usually correct. Force rebuild only when:
- `--callees` / `--callers` returns `callee_resolution: unknown` consistently
  AND the symbols clearly exist (means imports not indexed)
- Schema migration happened (e.g., new column added — pre-existing rows have defaults)
- Files were renamed/moved en masse (mtime-based invalidation may miss this)

```bash
uv run tree-sitter-analyzer --ast-cache --ast-cache-mode force
# OR safer (preserves what works):
uv run tree-sitter-analyzer --ast-cache --ast-cache-mode index
```

### AST diff

For structural change detection (not text):

```yaml
ast_diff(file_path: "...", base_ref: "HEAD~5", head_ref: "HEAD")
# returns: {nodes_added: n, nodes_removed: n, nodes_modified: n,
#           classification_hints: [...]}
```

Useful for distinguishing pure formatting from real change.

### Parser readiness

```yaml
advise_parser_readiness(language: "swift")
# returns: {status: "stable|beta|stub", supported_queries: [...], limitations: [...]}
```

Avoid asking "why doesn't swift work" — query this first.

## CLI equivalents

```bash
uv run tree-sitter-analyzer --ast-cache --ast-cache-mode status
uv run tree-sitter-analyzer --ast-cache --ast-cache-mode force
uv run tree-sitter-analyzer --ast-diff <file> --base HEAD~5 --head HEAD
uv run tree-sitter-analyzer parser-readiness swift
uv run tree-sitter-analyzer --autoindex            # codegraph_autoindex
uv run tree-sitter-analyzer --full-index           # codegraph_full_index
```

## Anti-patterns

- DON'T force-rebuild on every agent turn — the cache is correct 99% of the time
- DON'T run `--full-index` on a small project — `--ast-cache --ast-cache-mode index` is faster
- DON'T mix `--watch` and `--watch-health` in the same process — see tsa-health-watch
