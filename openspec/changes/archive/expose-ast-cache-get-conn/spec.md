# Spec: Expose ASTCache.get_conn() Public API

## Problem

`ASTCache._get_conn()` is called directly by 17 production modules across 31
call sites, bypassing encapsulation.  This is an API contract violation — callers
are coupled to the private attribute name.

Affected modules (sample):
- `xref.py`, `call_path.py`, `incremental_sync.py`, `class_hierarchy.py`
- `code_similarity.py`, `codegraph_query_backend.py`, `cross_file_resolver.py`
- `semantic_search.py`, `symbol_resolver.py`, `synapse_resolver/_context.py`
- 7 MCP tool files

## Decision

Add `ASTCache.get_conn()` as a public alias for `_get_conn()`, then migrate all
31 call sites.  `_get_conn()` is kept as an internal delegation to avoid touching
any non-Python callers (none found, but kept for safety).

This is the minimal-change approach: no behavioral change, no query refactoring,
no new abstractions.  The goal is purely to eliminate private-attribute coupling.

## Non-Goals

- Replacing raw SQL with higher-level `ASTCache` methods (separate, larger refactor)
- Changing connection lifecycle or WAL settings
- Touching any test infrastructure

## Acceptance Criteria

1. `ASTCache.get_conn()` is defined and returns the same connection as `_get_conn()`
2. All 31 production call sites use `get_conn()` instead of `_get_conn()`
3. `_get_conn()` remains (delegates to `get_conn()`) for backward compat
4. All existing tests pass
5. `change-impact` shows `risk=low` or lower after the change
