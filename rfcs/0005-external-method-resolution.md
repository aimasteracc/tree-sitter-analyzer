# RFC-0005: External library method classification — collapse the remaining `unknown` tail

- **Status**: implemented
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-05
- **Last updated**: 2026-06-05
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/synapse_resolver/_constants.py` (external-method table)
  - `tree_sitter_analyzer/synapse_resolver/__init__.py` (cascade: new final tier)
  - `tree_sitter_analyzer/synapse_resolver/_context.py` (wire the table + _ensure_loaded copy-back)
  - `tests/unit/test_external_method_resolution.py`

## Summary

Extend RFC-0004's cascade pattern by adding one more final tier
(`_try_external_method`) that classifies bare method names dominated by
test-framework libraries (pytest, hypothesis, unittest.mock) as `external`
instead of leaving them `unknown` — gated on the same language-aware project-
ownership guard introduced by RFC-0004.

## Motivation

After RFC-0004 (unknown 16.1% → 6.6%), the remaining ~7,766 unknown call edges
are dominated by third-party / test-framework method names the cascade cannot
name-match:

```
raises 943 · setattr 688 · given 286 · draw 285 · settings 265 · debug 204
MagicMock 187 · assert_called_once 173 · integers 157 · skip 150
assert_called_once_with 142 · sampled_from 137 · skipif 101 · parametrize 89
readouterr 88 …
```

These are overwhelmingly **external library calls** — pytest, hypothesis,
and unittest.mock — that the project does not define. Classifying them
`external` (instead of `unknown`) is honest and valuable: an agent that sees
`raises` classified `external` knows *not* to look for `raises` in this repo.
An agent that sees `unknown` cannot make that determination.

Measured on TSA's own index (113,731 call edges) after RFC-0004:

| metric | before RFC-0005 | after RFC-0005 |
|---|---|---|
| call edges total | 113,731 | 113,731 |
| classified | 106,052 (**93.3%**) | 109,046 (**95.9%**) |
| unknown | 7,679 (**6.7%**) | 4,685 (**4.1%**) |
| external (new) | 0 | 3,211 |

Classification improved from 93.3% → 95.9%; unknown dropped from 6.7% → 4.1%.

### Note on `setattr` (688 occurrences)

`setattr` is `monkeypatch.setattr(...)` — the Python builtin `setattr` called
as a METHOD (qualifier present). `_try_builtin` requires no qualifier, so it
skips these. Since `setattr` IS a Python builtin (already in `BUILTINS_PY`),
classifying it `external` here would be misleading. It is therefore a known
residual for a future `_try_builtin_method` tier or receiver-type inference.
It is deliberately NOT included in `EXTERNAL_METHODS_PY`.

## Detailed design

### Data structures

`_constants.py` gains a curated `frozenset` of well-known **external** (third-
party) library method names, grouped by owning library for auditability:

```python
# pytest — fixture methods and helpers
_PYTEST_METHODS = frozenset({"raises", "skip", "skipif", "parametrize",
    "fixture", "mark", "approx", "warns", "deprecated_call",
    "readouterr", "monkeypatch"})

# hypothesis — core strategies and decorators
_HYPOTHESIS_METHODS = frozenset({"given", "integers", "sampled_from",
    "characters", "text", "floats", "lists", "dictionaries", "tuples",
    "booleans", "composite", "assume", "note", "target", "event",
    "reproduce_failure"})

# unittest.mock — mock assertion and configuration methods
_MOCK_METHODS = frozenset({"assert_called_once_with", "assert_called_once",
    "assert_called_with", "assert_called", "assert_not_called",
    "assert_any_call", "assert_has_calls", "call_args_list", "mock_calls",
    "reset_mock", "configure_mock", "MagicMock", "patch", "call"})

EXTERNAL_METHODS_PY: frozenset[str] = _PYTEST_METHODS | _HYPOTHESIS_METHODS | _MOCK_METHODS
```

**Precision guards — deliberately excluded** names that projects commonly define:
`settings`, `debug`, `draw`, `execute`, `language` — these generic names risk
mis-classifying project code as external. The project-ownership gate (below) also
protects any name in the table that a project DOES define.

`ResolverContext` carries it as `external_methods: dict[str, frozenset[str]]`
(same shape as `stdlib_methods`), defaulting to `{"python": EXTERNAL_METHODS_PY}`.

### Algorithm — a new cascade tier after `_try_stdlib_method`

```python
def _try_external_method(base, qualifier, caller_file, ctx) -> ResolvedCallee | None:
    """Classify a bare external library method name as 'external' — only if no
    compatible-language project method of that name exists."""
    if base not in ctx.external_methods.get("python", frozenset()):
        return None
    # Language-aware project-ownership gate (Codex P2 pattern from RFC-0004):
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
    return ResolvedCallee(None, "external", "")
```

The cascade order after this RFC:

```
self/cls → local → import → stdlib-module → single-global → class-method →
unique-method → builtin → stdlib-METHOD (RFC-0004) → external-METHOD (RFC-0005) → unknown
```

### Error handling

Best-effort and monotonic: the tier only ever moves an edge `unknown → external`,
never the reverse. Returns `ResolvedCallee(None, "external", "")` — no
`callee_resolved_file` (external libraries have no project file).

### MCP surface (facade + action)

None. This is an indexing-layer classification improvement consumed identically
by every callee-resolution reader (call trees, xref, Hyphae `:calls`/`:callees`).

## Three-Surface impact (CLI ↔ MCP parity)

No surface change. Classification is computed at index time and read identically
by CLI and MCP. No new flag; no default to keep in lock-step.

## Drawbacks

- The method table is curated, not exhaustive. Third-party library methods not in
  the table remain `unknown`. It is a high-recall floor, not a complete type system.
- A project that defines a method named identically to an external table entry, but
  only via dynamic/metaclass machinery the symbol index misses, could be
  mislabeled `external`. Mitigated: the project-ownership gate catches every
  statically-indexed definition.
- Ambiguous names (`settings`, `debug`) are explicitly excluded to avoid
  mis-classifying project code.

## Alternatives

- **Full receiver-type inference**: more precise, much larger blast radius. Deferred
  to a phase 2 (would classify `m.assert_called_once_with` as `external` even when
  `m = MagicMock()` is type-inferred — currently handled by `_try_stdlib` since
  `MagicMock` comes from stdlib `unittest.mock`).
- **Leave them `unknown`**: status quo; rejected — understates the graph's
  completeness and makes "is this a project call?" unanswerable.

## Prior art

- **RFC-0004** established `_try_stdlib_method` and the language-aware project-
  ownership gate. RFC-0005 is a direct extension of the same pattern, one tier
  later, for external (third-party) library methods.
- **rust-analyzer / SCIP**: classify external crate calls as resolved-to-external,
  not unresolved.

## Test plan (RED-first)

Five tests in `tests/unit/test_external_method_resolution.py`:

1. `mock_arg.assert_called_once_with(...)` with no project def → `external`
   (RED before RFC-0005: `unknown`).
2. `pytest.raises(...)` bare name → `external` (RED: `unknown`).
3. Guard: a project class defining `assert_called_once` → resolves `project`,
   not `external` (shadowing preserved).
4. Guard: two project classes define `assert_called_once` → stays `unknown`,
   never claimed `external`.
5. Guard: JS file defining `readouterr` does NOT suppress Python external
   classification (language-aware gate).
6. Guard: public lazy `ResolverContext(project_root=, cache=)` populates
   `external_methods` (the `_ensure_loaded` copy-back — Codex P2 pattern).

## Acceptance criteria

- [x] `EXTERNAL_METHODS_PY` table in `_constants.py`, grouped + commented by library
- [x] `_try_external_method` tier in the cascade (after `_try_stdlib_method`)
- [x] `ResolverContext.external_methods` property + `_ensure_loaded` copy-back
- [x] `_build_resolver_context_uncached` passes `external_methods={"python": EXTERNAL_METHODS_PY}`
- [x] Shadowing preserved: project method of the same name wins (unit test)
- [x] Ambiguous project method name stays `unknown` (unit test)
- [x] Language-aware gate: cross-language JS symbol does not suppress (unit test)
- [x] `_ensure_loaded` copy-back test (Codex P2 pattern)
- [x] Dogfood: classified share **95.9%** (was 93.3%); unknown **4.1%** (was 6.7%)
- [x] `ruff` + `mypy` clean
- [x] CLI↔MCP parity unaffected (no surface change)

## What this RFC does NOT do (deferred)

- `setattr` (688 occurrences as `monkeypatch.setattr`) — left for a future
  `_try_builtin_method` tier or receiver-type inference. `setattr` is a Python
  builtin; classifying it `external` would be incorrect.
- Full receiver-type inference to resolve to the owning library file (phase 2).
- Non-Python external-method tables (Java/Go/JS) — Python first; others follow
  the same shape once proven.
- Exhaustive coverage of all third-party libraries (`requests`, `numpy`,
  `sqlalchemy`, …) — out of scope; test-framework methods are the dominant gap.

## Open questions

1. Should `draw` (285 occurrences) be added to the table? It appears in
   hypothesis (`@st.composite` functions use `draw`), but projects also commonly
   define `draw` methods (matplotlib, pygame, custom renderers). Left out for now;
   projects can override the table by passing `external_methods={}`.
2. Phase-2 receiver-type inference: how should `external` interact with a resolved
   `m: MagicMock` annotation — should it produce `external` with a library
   reference, or stay `external` with no file?
