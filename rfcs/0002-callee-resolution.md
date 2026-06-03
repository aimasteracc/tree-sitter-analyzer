# RFC-0002: Callee resolution — bare names to resolved symbols

- **Status**: draft
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-03
- **Last updated**: 2026-06-03
- **Tracking issue**: TBD
- **Affected source paths**:
  - `tree_sitter_analyzer/_ast_cache_unresolved.py` (the second-pass resolver)
  - `tree_sitter_analyzer/_ast_cache_synapse.py` (synapse resolution RMW)
  - `tree_sitter_analyzer/_ast_extraction.py` (call-edge extraction / receiver capture)
  - `tree_sitter_analyzer/graph/edge_store.py` (edges schema: callee_resolved_file / callee_resolution / callee_symbol_id)
  - `tree_sitter_analyzer/hyphae/evaluator.py` (consumer — edge pseudo-classes)
  - `tests/unit/`

## Summary

Resolve the `callee` endpoint of `calls` edges from a **bare name**
(`execute`, `absolute_path`) to a **specific resolved symbol** (which file,
which class/scope, which definition) and classify it
(`project` / `local` / `stdlib` / `external` / `builtin`). Today **87.7% of
call edges have an unresolved bare callee** and **62.6% are classified
`unknown`** — which makes any call-graph-derived analysis (test coverage,
impact, "who tests whom") untrustworthy, and even makes a bare-name `grep`
verification unreliable.

## Motivation

Measured on TSA's own index (1787 files, 112,633 call edges):

| metric | value |
|---|---|
| call edges total | 112,633 |
| callee resolved to a file | 13,886 (**12.3%**) |
| callee still a bare name | 98,747 (**87.7%**) |
| `callee_resolution = unknown` | 70,482 (**62.6%**) |
| `stdlib` | 28,265 · `project` 11,264 · `local` 2,622 |

**The pain is concrete.** When we tried to answer "which production methods are
untested?" via Hyphae (`.function:in(src):not(:callees(.function:in(tests/)))`),
the query *ran* fine — but the result was polluted by the bare-name problem:

- **`execute`** appears as the callee of 227 test files — but those are
  *different* `execute` methods on different classes (dynamic dispatch). A bare
  name can't tell them apart.
- **`absolute_path`** (a real function at `_codegraph_query_symbols.py:156`) has
  **0 call edges** and is genuinely untested — yet a bare-name `grep`
  "verification" wrongly flagged it as a false positive, because the matches
  were actually `_absolute_path`, `_validate_absolute_path`, and the test
  function name `test_relative_vs_absolute_path`. **Bare names fooled even the
  human cross-check.**

So bare-name callees don't just make the call graph imprecise — they make every
downstream answer (coverage, impact, dedup, "who calls/tests this exact symbol")
unreliable, and they hide that unreliability behind plausible-looking results.
Resolving the callee is the root fix; it directly advances the project's
north-star "agent-native **resolved** code graph".

## Detailed design

### Data structures (mostly already present)

The `edges` table already carries the target columns — this RFC is about
**filling them correctly**, not adding schema:

- `callee_resolved_file` — the file the callee is defined in
- `callee_symbol_id` — the resolved symbol's id (the precise definition)
- `callee_resolution` — `project` / `local` / `stdlib` / `external` / `builtin` / `unknown`

### Algorithms — scope-aware resolution

> **Cascade order matters — bindings before builtins (Codex review).** A
> project/local binding can *shadow* a builtin or stdlib-looking name
> (`def len(): ...; len()`, or a project import named `Path`). If we classified
> by bare name *first*, we'd mislabel the call `builtin`/`stdlib` with no
> `callee_symbol_id` and **regress the resolved graph**. This RFC therefore
> follows the EXISTING cascade in
> `tree_sitter_analyzer/synapse_resolver/__init__.py` (local → self/cls →
> import → stdlib/builtin), which already orders bindings before builtins
> specifically to preserve shadowing. This RFC extends that cascade's *reach*
> and *fill rate*, it does not reorder it.

For each `calls` edge `(caller, callee_name)`, in priority order:

1. **Local scope**: a name bound in the caller's own function/module (local
   def, parameter, assignment) → `local`, resolve to that definition.
2. **self/cls**: `self.X` / `cls.X` on the caller's enclosing class → resolve
   to that class's member.
3. **Import-based**: follow the caller file's imports (`ast_imports` + B3 import
   resolution) → `project` / `external`.
4. **Receiver-typed method calls** (`obj.method()`): infer the type of `obj`
   (annotation, constructor assignment) → resolve `method` to that class's
   definition. This disambiguates the 227 same-named `execute` edges.
5. **Builtin/stdlib classification — LAST, only if nothing above bound the
   name** (so a shadowing local/import wins): match against a per-language
   builtin + stdlib table → `builtin` / `stdlib`. This is where the `len`/`str`/
   `Path` noise gets classified, *after* confirming no binding shadows it.
6. **Leave `unknown`** only when none of the above resolves — and record *why*
   (so the number is auditable, not silent).

### Error handling

Resolution is best-effort and monotonic: an edge never regresses from resolved
to unknown. Ambiguous resolution (multiple candidates) records the candidate
set rather than guessing one.

### MCP surface (facade + action)

No new surface. Hyphae edge pseudo-classes (`:calls`/`:callees`) become precise
automatically once callees resolve, because the evaluator already matches on
`(name, file)` (RFC for the file-identity fix landed in #271). A future
optional `[resolution=project]` attribute could filter by class.

## Three-Surface impact (CLI ↔ MCP parity)

No surface change; this is an indexing-layer improvement consumed equally by CLI
and MCP. The CLI `--callers "Class.method"` path (which already needs the
receiver field, per CLAUDE.md rule 6) benefits directly.

## Drawbacks

- Resolution is non-trivial for dynamic languages (Python/JS): receiver type
  inference is heuristic and will not reach 100%.
- More work at index time (per-edge resolution). Mitigated: it is a second pass
  over already-extracted edges (we have `_ast_cache_unresolved.py` for exactly
  this), and builtin/stdlib classification is a cheap table lookup.

## Alternatives

- **Runtime tracing** (e.g. `sys.settrace` / coverage.py) — precise, but
  requires executing the code; out of scope for a static index. *Complementary,
  not a replacement.*
- **LSP integration** (defer name resolution to a language server) — accurate
  but heavy, per-language servers, not embeddable. *Deferred.*
- **Leave it bare, document the caveat** — status quo; rejected, it makes the
  whole call graph untrustworthy for the analyses agents actually want.

## Prior art

- **codegraph's `UnresolvedRef` two-phase resolution** (see
  `reference_codegraph-architecture`): extract refs first, resolve in a second
  pass against the symbol table — we adopt this shape (and already have the
  second-pass scaffold in `_ast_cache_unresolved.py`).
- **rust-analyzer name resolution** / **Sourcegraph SCIP** — scope-aware symbol
  resolution with stable symbol ids; we adopt the "resolve to a stable symbol
  id" idea (`callee_symbol_id`).
- **mycelium Synapse** (the sibling project) — resolved bidirectional edges by
  symbol, not name.

## Test plan (RED-first)

- Unit: builtin/stdlib classifier (Python `len`/`str` → builtin; `os.path` →
  stdlib).
- Unit: **shadowing** — `def len(): ...; len()` resolves to the local def
  (`local` + symbol_id), NOT `builtin`; a project import named `Path` resolves
  to `project`, not `stdlib` (the cascade-order regression).
- Unit: receiver-typed resolution — two classes with same-named method, an
  `execute` call resolves to the right one by receiver type.
- Unit: `absolute_path` vs `_absolute_path` vs `_validate_absolute_path` resolve
  to distinct symbols (the disambiguation regression).
- Integration: re-index TSA self; assert callee resolution rate rises and
  `unknown` drops; assert the `execute` edges no longer collapse to one name.
- Dogfood: re-run the Hyphae coverage query; assert the false-positive rate
  (bare-name collisions) drops materially vs the 12.3% baseline.

## Acceptance criteria

- [ ] Builtin/stdlib classifier per language, applied LAST in the cascade;
      `unknown` rate drops measurably
- [ ] Shadowing preserved: a local/import binding that shadows a builtin/stdlib
      name resolves to the binding (local/project + symbol_id), not builtin/stdlib
- [ ] Receiver-typed method resolution disambiguates same-named methods
- [ ] `absolute_path`/`_absolute_path`/`_validate_absolute_path` resolve to
      distinct `callee_symbol_id`s (unit regression)
- [ ] Re-indexed TSA self: callee resolution rate ≥ a target (set after a spike;
      proposed ≥ 50% resolved-or-classified, from 12.3%)
- [ ] Hyphae coverage query (`:callees`) false-positive rate measurably lower
- [ ] No edge regresses resolved→unknown (monotonicity test)
- [ ] CLI `--callers "Class.method"` still green; docs/CODEMAPS updated

## What this RFC does NOT do (deferred)

- Full type inference / a Python type checker — heuristic receiver typing only.
- Runtime coverage (that's pytest-cov's job; this is the static-graph fix).
- Cross-repository resolution (external deps resolve to `external`, not into
  their source).

## Open questions

1. Target resolution rate for the acceptance gate — set after a spike on a few
   files (proposed ≥ 50%).
2. Receiver typing depth: just `self` + direct constructor assignment for v1, or
   also annotations / return types?
3. Should `builtin`/`stdlib` callees be dropped from the graph entirely (noise)
   or kept-but-classified? Proposed: kept-but-classified (so `:callees` can
   still answer "does X call any stdlib").
