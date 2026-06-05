# RFC-0004: Stdlib/builtin method resolution — collapse the `unknown` tail

- **Status**: implemented
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-05
- **Last updated**: 2026-06-05
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/synapse_resolver/_constants.py` (stdlib-method table)
  - `tree_sitter_analyzer/synapse_resolver/__init__.py` (cascade: new final tier)
  - `tree_sitter_analyzer/synapse_resolver/_context.py` (wire the table)
  - `tests/unit/test_synapse_resolution.py`, `tests/unit/`

## Summary

Add a final resolution tier that classifies a **bare method name** that survives
every project-binding rule (`write_text`, `strip`, `items`, `add_argument`,
`group`, …) as `stdlib` instead of leaving it `unknown` — but **only when the
project defines no method of that name at all**, so shadowing is preserved and
no edge is mis-classified.

## Motivation

Measured on TSA's own index (113,735 call edges):

| metric | value |
|---|---|
| call edges total | 113,735 |
| `callee_resolution != unknown` (classified) | 95,409 (**83.9%**) |
| `callee_resolution == unknown` | 18,326 (**16.1%**) |

The `unknown` tail is not random — it is dominated by **stdlib/builtin method
calls** the cascade cannot name-match, because the builtin/stdlib classifier
keys on *function* names (`len`, `open`) and top-level *module* names (`os`,
`re`), never on *method* names. The top 25 `unknown` callees are almost all
`str` / `pathlib.Path` / `dict` / `list` / `re.Match` / `argparse` methods:

```
write_text 1589 · raises 943 · join 788 · strip 743 · setattr 688
startswith 607 · mkdir 603 · lower 560 · add_argument 506 · split 500
items 470 · extend 398 · exists 356 · write 314 · group 262 · replace 257 …
```

A curated stdlib/builtin **method** table covers **11,153 of the 18,326 unknown
edges (60.9%)**, lifting classification **83.9% → 93.7%** with zero mis-wiring
risk (the new tier runs last, after every project binding rule). This directly
advances the north-star "agent-native **resolved** code graph": an agent that
sees `p.write_text()` classified `stdlib` knows *not* to look for `write_text`
in this repo — today it sees `unknown` and cannot tell.

## Detailed design

### Data structures

`_constants.py` gains a curated frozenset of well-known stdlib/builtin **method**
names, grouped by owning type for auditability:

```python
# Methods on str, pathlib.Path, dict/list/set, re.Match, argparse, datetime, …
STDLIB_METHODS_PY: frozenset[str]  # write_text, strip, items, add_argument, group, …
```

`ResolverContext` carries it as `stdlib_methods: dict[str, frozenset[str]]`
(same shape as `builtins` / `stdlib_modules`), defaulting to
`{"python": STDLIB_METHODS_PY}`.

### Algorithm — a new FINAL cascade tier

```python
def _try_stdlib_method(base, qualifier, ctx) -> ResolvedCallee | None:
    """Classify a bare method name as stdlib — only if no project method
    of that name exists (so an ambiguous project method is NOT mislabeled)."""
    if base not in ctx.stdlib_methods.get("python", frozenset()):
        return None
    # Gate on the project: if ANY project symbol carries this name, leave it
    # ``unknown`` rather than claim stdlib (the project owns the name).
    if ctx.callee_resolver is not None:
        matches = ctx.callee_resolver.resolve_items(
            base, "", include_local=False, include_import=False
        )
        if matches:
            return None
    return ResolvedCallee(None, "stdlib", "")
```

It is appended to the cascade **after** `_try_builtin` (itself the last project
tier), so the order is:

```
self/cls → local → import → stdlib-module → single-global → class-method →
unique-method → builtin → stdlib-METHOD (new) → unknown
```

Because every project-binding rule runs first, a project that defines `split`,
`get`, or `items` resolves to the project; only names with **no** project
definition reach the stdlib-method tier.

### Error handling

Best-effort and monotonic (consistent with RFC-0002): the tier only ever moves
an edge `unknown → stdlib`, never the reverse, and never produces a
`callee_resolved_file` (stdlib has no project file), so no file-resolution
consumer is affected.

### MCP surface (facade + action)

None. This is an indexing-layer classification improvement consumed equally by
every callee-resolution reader (Hyphae `:calls`/`:callees`, call trees, xref).

## Three-Surface impact (CLI ↔ MCP parity)

No surface change. The classification is computed at index time and read
identically by CLI and MCP. No new flag, no default to keep in lock-step.

## Drawbacks

- The method table is curated, not exhaustive — it will not classify every
  stdlib method (e.g. third-party-library methods stay `unknown`). It is a
  high-recall floor, not a complete type system.
- A project that defines a method named identically to a stdlib method, but
  only via dynamic/metaclass machinery the symbol index misses, could in
  principle be mislabeled `stdlib`. Mitigated: the project-symbol gate catches
  every statically-indexed definition, which is the overwhelming majority.

## Alternatives

- **Full receiver-type inference** (infer `p: Path` then resolve `write_text` to
  `pathlib`): more precise, much larger blast radius, per-type modelling.
  *Deferred to a phase 2* — the name table captures 61% of the tail for a
  fraction of the cost.
- **Leave them `unknown` + document**: status quo; rejected — it understates
  the graph's completeness and makes "is this a project call?" unanswerable.
- **Classify by receiver var heuristics** (`tmp_path` → Path): brittle, naming-
  dependent. Rejected.

## Prior art

- **RFC-0002** (this repo) established the binding-before-builtin cascade and the
  shadowing rule; RFC-0004 extends the *tail* of that same cascade.
- **rust-analyzer / SCIP** classify calls to stdlib as resolved-to-stdlib, not
  unresolved — we adopt that "stdlib is a resolution, not a failure" stance.

## Test plan (RED-first)

- Unit: `write_text` with no project def → `stdlib`. (RED today: `unknown`.)
- Unit: a project class defining `split` → `split()` resolves `project`, NOT
  `stdlib` (shadowing preserved).
- Unit: an ambiguous project method name (two classes define `get`) → stays
  `unknown`, never claimed `stdlib`.
- Unit: a genuinely unknown name (`frobnicate`) → stays `unknown`.
- Dogfood: re-index this repo, assert `unknown` share drops below 8% and the
  classified share rises above 92%.

## Acceptance criteria

- [x] `STDLIB_METHODS_PY` table in `_constants.py`, grouped + commented by type
- [x] `_try_stdlib_method` final tier in the cascade (after `_try_builtin`)
- [x] `ResolverContext.stdlib_methods` wired with the default table
- [x] Shadowing preserved: project method of the same name wins (unit test)
- [x] Ambiguous project method name stays `unknown` (unit test)
- [x] Dogfood: classified share **93.2%** on this repo (was 83.9%; unknown 16.1% → 6.8%)
- [x] CLI↔MCP parity unaffected (no surface change) — contract tests green
- [x] Docs/CODEMAPS updated; RFC status → implemented

## What this RFC does NOT do (deferred)

- Receiver-type inference to resolve stdlib methods to the owning *module file*
  (phase 2). This RFC classifies, it does not file-resolve.
- Third-party-library method tables (requests, numpy, …) — out of scope.
- Non-Python stdlib-method tables (Java/Go/JS) — Python first; others follow the
  same shape once proven.

## Open questions

1. Should the table live in `_constants.py` (chosen) or be generated from
   `inspect` over the stdlib at build time? Curated is auditable and offline.
2. Phase-2 receiver-type inference: annotation-driven first, or constructor-
   assignment driven first?
