---
name: tsa-index
version: 2.0.0
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
  - mcp__tree-sitter-analyzer__index
  - mcp__tree-sitter-analyzer__edit
  - mcp__tree-sitter-analyzer__project
  - Bash
  - Read
---

# tsa-index — Cache / index ops

> Not a daily skill. Most agents never need it. Pull when index is stale or
> a language plugin behaves oddly.

## Tool routing

| Goal                                           | Tool                              |
|------------------------------------------------|-----------------------------------|
| Status / stats of the AST cache                | `index action=cache` (mode=status) |
| Force rebuild                                  | `index action=cache` (mode=force)  |
| Incremental refresh                            | `index action=cache` (mode=index)  |
| Watch a directory and auto-refresh             | `index action=cache` (mode=watch_start) |
| AST-level diff of one file across commits      | `edit action=ast_diff`            |
| First-time index for a freshly-cloned repo     | `index action=auto`               |
| Full bulk reindex (large monorepo)             | `index action=full`               |
| "Is the python plugin / swift plugin ready"    | `project action=parser`           |

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
edit action=ast_diff file_path="..." base_ref="HEAD~5" head_ref="HEAD"
# returns: {nodes_added: n, nodes_removed: n, nodes_modified: n,
#           classification_hints: [...]}
```

Useful for distinguishing pure formatting from real change.

### Parser readiness

```yaml
project action=parser language="swift"
# returns: {status: "stable|beta|stub", supported_queries: [...], limitations: [...]}
```

Avoid asking "why doesn't swift work" — query this first.

## CLI equivalents

```bash
uv run tree-sitter-analyzer --ast-cache --ast-cache-mode status
uv run tree-sitter-analyzer --ast-cache --ast-cache-mode force
uv run tree-sitter-analyzer --ast-diff --ast-diff-file <file> --ast-diff-old-ref HEAD~5 --ast-diff-new-ref HEAD
uv run tree-sitter-analyzer --parser-readiness swift
uv run tree-sitter-analyzer --autoindex            # index action=auto
uv run tree-sitter-analyzer --full-index           # index action=full
```

## Anti-patterns

- DON'T force-rebuild on every agent turn — the cache is correct 99% of the time
- DON'T run `--full-index` on a small project — `--ast-cache --ast-cache-mode index` is faster
- DON'T mix `--watch` and `--watch-health` in the same process — see tsa-health-watch
