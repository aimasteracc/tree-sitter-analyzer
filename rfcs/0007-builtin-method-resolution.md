# RFC-0007: Qualified-builtin method classification — setattr/getattr to builtin

- **Status**: implemented
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-06
- **Last updated**: 2026-06-06
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/synapse_resolver/_constants.py` (BUILTIN_QUALIFIED_PY table)
  - `tree_sitter_analyzer/synapse_resolver/__init__.py` (cascade: new final tier)
  - `tree_sitter_analyzer/synapse_resolver/_context.py` (wire the table + _ensure_loaded copy-back)
  - `tests/unit/test_builtin_method_resolution.py`

## Summary

Add a final resolution tier that classifies a **qualified Python builtin name**
(a builtin called with a receiver — `monkeypatch.setattr(...)`, `obj.getattr(...)`)
as `builtin` instead of leaving it `unknown` — but **only when the project defines
no compatible-language method of that name**, preserving shadowing and preventing
mis-classification.

## Motivation

After RFC-0004 (83.9% → 93.3%) and RFC-0005 (93.3% → 95.9%), the top remaining
`unknown` callee was `setattr` (688 edges) — the Python builtin `setattr` called
as a method with a qualifier: `monkeypatch.setattr(obj, 'attr', val)`.

The existing `_try_builtin` tier handles bare builtin calls with no qualifier:

```python
def _try_builtin(base, qualifier, ctx):
    if qualifier:
        return None          # ← skips ALL qualified calls
    if base in ctx.builtins.get("python", frozenset()):
        return ResolvedCallee(None, "builtin", "")
```

The `qualifier` guard is correct for most builtins — `obj.len()` or `obj.open()`
are almost certainly project methods, not the Python builtins `len`/`open`. But
`setattr`, `getattr`, `hasattr`, and `delattr` are overwhelmingly the Python
builtins even when qualified. `monkeypatch.setattr(...)` is pytest's thin wrapper
around the builtin; the resolved call IS the builtin.

Measured on TSA's own index (113,856 call edges):

| metric | before RFC-0007 | after RFC-0007 |
|---|---|---|
| call edges total | 113,856 | 113,856 |
| classified | 109,158 (**95.9%**) | 109,859 (**96.5%**) |
| unknown | 4,698 (**4.1%**) | 3,997 (**3.5%**) |
| `setattr` as builtin | 0 | 701 |

Classification improved **95.9% → 96.5%**; unknown dropped **4.1% → 3.5%**.

## Detailed design

### Data structures

`_constants.py` gains a conservative `frozenset` of Python builtin names whose
qualified form is still almost exclusively the Python builtin:

```python
BUILTIN_QUALIFIED_PY: frozenset[str] = frozenset({
    "setattr",  # monkeypatch.setattr(obj, 'attr', val) — dominant case
    "getattr",  # obj.getattr(name, default)
    "hasattr",  # obj.hasattr(name)
    "delattr",  # obj.delattr(name)
})
```

**Conservative by design.** Only names whose qualified use is overwhelmingly
the Python builtin are included. Names that projects commonly define as methods
(`get`, `set`, `call`, `apply`, etc.) are deliberately EXCLUDED — the risk of
mis-classification outweighs the completeness gain. The project-ownership gate
(below) also protects any name a project DOES define.

`ResolverContext` carries it as `builtin_methods: dict[str, frozenset[str]]`
(same shape as `stdlib_methods` / `external_methods`), defaulting to
`{"python": BUILTIN_QUALIFIED_PY}`.

### Algorithm — a new FINAL cascade tier

```python
def _try_builtin_method(base, qualifier, caller_file, ctx) -> ResolvedCallee | None:
    """RFC-0007: classify a QUALIFIED Python builtin name as builtin.

    _try_builtin classifies bare (unqualified) builtins. This tier recovers
    qualified calls (monkeypatch.setattr, obj.getattr) for names in
    BUILTIN_QUALIFIED_PY — after every project-binding, stdlib, and external
    rule has already had a chance to claim the name.
    """
    if not qualifier:
        return None  # bare builtins already handled by _try_builtin
    if base not in ctx.builtin_methods.get("python", frozenset()):
        return None
    # Language-aware project-ownership gate (same Codex P2 pattern as RFC-0004/0005):
    if ctx.callee_resolver is not None:
        caller_lang = ctx.file_languages.get(caller_file, "")
        matches = ctx.callee_resolver.resolve_items(
            base, "", include_local=False, include_import=False
        )
        for item, _confidence in matches:
            item_lang = ctx.file_languages.get(_item_file(item), "")
            if (not caller_lang or not item_lang
                    or languages_compatible(caller_lang, item_lang)):
                return None  # project owns the name — leave unknown
    return ResolvedCallee(None, "builtin", "")
```

The cascade order after this RFC:

```
self/cls → local → import → stdlib-module → single-global → class-method →
unique-method → builtin → stdlib-METHOD (RFC-0004) → external-METHOD (RFC-0005) →
builtin-METHOD (RFC-0007) → unknown
```

Because every project-binding, stdlib, and external rule runs first, only
names with **no** compatible-language project definition reach this tier.

### Error handling

Best-effort and monotonic (consistent with RFC-0002 / RFC-0004 / RFC-0005): the
tier only ever moves an edge `unknown → builtin`, never the reverse, and never
produces a `callee_resolved_file` (builtins have no project file), so no
file-resolution consumer is affected.

### MCP surface (facade + action)

None. This is an indexing-layer classification improvement consumed identically
by every callee-resolution reader (call trees, xref, Hyphae `:calls`/`:callees`).

## Three-Surface impact (CLI ↔ MCP parity)

No surface change. Classification is computed at index time and read identically
by CLI and MCP. No new flag; no default to keep in lock-step.

## Drawbacks

- The table is conservative (four names) — other qualified builtins that are
  genuinely the Python builtin (`obj.iter(...)`, `obj.hash()`) remain `unknown`.
  Adding more names risks false positives; the four attr-inspection builtins are
  the dominant case by edge count.
- A project that defines a method named `setattr` only via dynamic/metaclass
  machinery the symbol index misses could in principle be mislabeled `builtin`.
  Mitigated: the project-ownership gate catches every statically-indexed
  definition, which is the overwhelming majority.

## Alternatives

- **Expand to more builtins**: `iter`, `hash`, `repr`, `str`, etc. can appear
  with a receiver, but those names are also commonly user-defined methods. The
  conservative table is the right tradeoff for precision.
- **Full receiver-type inference**: infer `monkeypatch: MonkeyPatch` → resolve
  `setattr` to stdlib `unittest.mock`. More precise, much larger blast radius.
  Deferred to a later phase — this RFC's four-name table captures all 701 edges
  in one tier for a fraction of the cost.
- **Classify setattr as external**: `monkeypatch.setattr` is technically a pytest
  wrapper. But `setattr` is in `BUILTINS_PY`; classifying it `external` would be
  misleading. `builtin` is the correct classification. RFC-0005 explicitly deferred
  this to a future `_try_builtin_method` tier — this is that tier.
- **Leave them unknown**: status quo; rejected — understates the graph's
  completeness and makes "is this a project call?" unanswerable.

## Prior art

- **RFC-0004** established `_try_stdlib_method` and the language-aware project-
  ownership gate. RFC-0007 follows the exact same pattern for the builtin tier.
- **RFC-0005** explicitly deferred `setattr` (688 occurrences) to a future
  `_try_builtin_method` tier (see RFC-0005 §Note on setattr). This is that tier.
- **rust-analyzer / SCIP**: classify calls to stdlib/builtin as resolved-to-builtin,
  not unresolved.

## Test plan (RED-first)

Five tests in `tests/unit/test_builtin_method_resolution.py`:

1. `monkeypatch.setattr(obj, 'attr', 42)` with no project def → `builtin`
   (RED before RFC-0007: `unknown`).
2. `obj.getattr(name, None)` with no project def → `builtin`.
3. Guard: a project class defining `setattr` → resolves `project`, not `builtin`
   (shadowing preserved).
4. Guard: two project classes define `setattr` → stays `unknown`, never `builtin`.
5. Guard: JS file defining `setattr` does NOT suppress Python builtin classification
   (language-aware gate).
6. Guard: public lazy `ResolverContext(project_root=, cache=)` populates
   `builtin_methods` (the `_ensure_loaded` copy-back — Codex P2 pattern).

## Acceptance criteria

- [x] `BUILTIN_QUALIFIED_PY` table in `_constants.py`, commented by rationale
- [x] `_try_builtin_method` final tier in the cascade (after `_try_external_method`)
- [x] `ResolverContext.builtin_methods` property + `_ensure_loaded` copy-back
- [x] `_build_resolver_context_uncached` passes `builtin_methods={"python": BUILTIN_QUALIFIED_PY}`
- [x] Qualified builtin: `monkeypatch.setattr` → `builtin` (unit test — was unknown)
- [x] Shadowing preserved: project method of the same name wins (unit test)
- [x] Ambiguous project method name stays `unknown` (unit test)
- [x] Language-aware gate: cross-language JS symbol does not suppress (unit test)
- [x] `_ensure_loaded` copy-back test (Codex P2 pattern)
- [x] Dogfood: classified share **96.5%** (was 95.9%); unknown **3.5%** (was 4.1%)
- [x] `ruff` + `mypy` clean on `synapse_resolver/`
- [x] CLI↔MCP parity unaffected (no surface change)

## What this RFC does NOT do (deferred)

- Expanding `BUILTIN_QUALIFIED_PY` beyond the four attr-inspection builtins
  (`iter`, `hash`, `repr`, `str`, …) — conservative table wins on precision.
- Full receiver-type inference to resolve to the Python `builtins` module (phase 2).
- Non-Python qualified-builtin tables (Java, Go, JS) — Python first; others
  follow the same shape once proven.

## Open questions

1. Should `vars`, `dir`, or `type` be added? They can appear qualified but risk
   false positives on projects that define `vars()`, `dir()`, or `type()` methods.
   Left out; can be added in a follow-up RFC if edge counts justify it.
2. Phase-2 receiver-type inference: when `monkeypatch: MonkeyPatch` is annotated,
   should the resolution produce `external` (the pytest library) rather than
   `builtin`? This RFC intentionally leaves that distinction to the type-inference
   phase — `builtin` is correct for the underlying operation regardless of the
   library wrapper.
