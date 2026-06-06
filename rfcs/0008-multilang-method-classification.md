# RFC-0008: Multi-language method classification — beyond Python

- **Status**: draft
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-06
- **Last updated**: 2026-06-06
- **Tracking issue**: TBD
- **Affected source paths**:
  - `tree_sitter_analyzer/synapse_resolver/_constants.py` (per-language method tables)
  - `tree_sitter_analyzer/synapse_resolver/_java_constants.py` (precedent: Java tables)
  - `tree_sitter_analyzer/synapse_resolver/__init__.py` (cascade: language dispatch)
  - `tests/unit/`

## Summary

Extend the method-classification cascade tiers from RFC-0004 (`_try_stdlib_method`),
RFC-0005 (`_try_external_method`), and RFC-0007 (`_try_builtin_method`) — currently
**Python-only** — to **Java, Go, and JavaScript/TypeScript**, so a polyglot
repository's call graph is classified to the same ~96% completeness TSA reaches on
a pure-Python repo.

## Motivation

RFC-0004/0005/0007 took Python callee classification from **83.9% to 96.5%** by
recognising bare stdlib / external-library / builtin **method** names the binding
cascade can't resolve, gated on the project owning no compatible-language symbol of
that name (shadowing preserved, zero mis-wires).

Those three tiers are **Python-only**: the tables (`STDLIB_METHODS_PY`,
`EXTERNAL_METHODS_PY`, `BUILTIN_QUALIFIED_PY`) and the cascade tiers each gate on
`caller_lang == "python"` (RFC-0007 Codex P2). On a Java / Go / JS repo those tiers
never fire, so the `unknown` tail stays large — the same class of edge
(`list.add`, `strings.Split`, `arr.map`, `obj.toString`) we now resolve in Python
is left unclassified elsewhere. TSA advertises broad language coverage; resolved-
graph completeness should follow.

## Detailed design

### Data structures — per-language method tables

Mirror the Python tables, one set per language, grouped + commented by owning
type/library. Curated, high-recall, conservative (exclude names projects commonly
define):

- **Java** (`STDLIB_METHODS_JAVA`): `java.util` collections (`add`, `get`, `put`,
  `containsKey`, `stream`, `forEach`), `String` (`substring`, `trim`, `split`),
  `Optional` (`orElse`, `isPresent`), `Stream` (`map`, `filter`, `collect`).
  External: JUnit (`assertEquals`, `assertThat`), Mockito (`mock`, `when`, `verify`).
- **Go** (`STDLIB_METHODS_GO`): package-qualified calls (`strings.Split`,
  `fmt.Sprintf`) are already import-resolved; the gap is receiver methods on
  stdlib types (`err.Error`, `ctx.Done`, `wg.Wait`, `b.WriteString`). External:
  `testing` (`t.Run`, `t.Fatal`), testify (`assert.Equal`, `require.NoError`).
- **JS/TS** (`STDLIB_METHODS_JS`): `Array` (`map`, `filter`, `reduce`, `forEach`,
  `find`, `push`), `String` (`split`, `slice`, `replace`, `trim`), `Object`
  (`keys`, `values`, `entries`), `Promise` (`then`, `catch`). External: Jest/Vitest
  (`expect`, `toBe`, `toEqual`).

### Algorithm — language-dispatched tiers

The three tiers already thread `caller_file` and compute `caller_lang`. Generalise:
each tier looks up the table for `caller_lang` instead of hard-coding `"python"`.

```python
def _try_stdlib_method(base, qualifier, caller_file, ctx):
    caller_lang = ctx.file_languages.get(caller_file, "")
    table = ctx.stdlib_methods.get(caller_lang)   # was: .get("python")
    if not table or base not in table:
        return None
    # same language-aware project-ownership gate as today
    ...
```

`ResolverContext` already carries `stdlib_methods` / `external_methods` /
`builtin_methods` as `dict[str, frozenset[str]]` keyed by language — so wiring is
"add more keys", not new plumbing. The default builder registers Java / Go / JS
tables alongside Python.

The **language-aware project-ownership gate** stays: a project method of the same
name in a compatible-language file wins; ambiguous names stay `unknown`.

### Error handling

Best-effort and monotonic: a tier only moves an edge `unknown -> stdlib/external/
builtin`, never the reverse, never crosses languages. A language with no table
behaves exactly as today (no-op).

### MCP surface

None. Indexing-layer classification, consumed identically by every reader.

## Three-Surface impact (CLI / MCP parity)

No surface change. Computed at index time, read identically by CLI and MCP.

## Drawbacks

- Curating four languages' tables is more surface to maintain. Mitigated: tables
  are high-recall floors, not exhaustive; the ownership gate prevents over-claiming.
- Go's package-qualified calls are mostly import-resolved already; the receiver-
  method gap is smaller there — measure before investing.

## Alternatives

- **Per-language full type inference**: precise, far larger, per-language type
  systems. Deferred — the name table captured 12pp in Python cheaply.
- **Leave non-Python at status quo**: rejected — completeness should not be
  Python-only.

## Prior art

- RFC-0004/0005/0007 (this repo) — the cascade-tier + ownership-gate pattern this
  RFC generalises across languages.
- `_java_constants.py` already exists (Java builtins/stdlib for the binding
  cascade) — extend it with method tables rather than starting fresh.

## Test plan (RED-first)

- Unit per language: a Java caller `list.add(x)` with no project `add` -> `stdlib`;
  a project method `add` -> `project` (shadowing); a JS `arr.map(f)` -> `stdlib`;
  cross-language gate (a Python `split` table must not classify a Java `split`).
- Dogfood: index a polyglot/Java/Go repo; assert classified share rises vs the
  Python-only baseline; zero mis-wires.

## Acceptance criteria

- [ ] `STDLIB_METHODS_JAVA` / `_GO` / `_JS` (+ external/builtin where apt), grouped + commented
- [ ] cascade tiers dispatch on `caller_lang` (not hard-coded Python)
- [ ] language-aware ownership gate preserved per language (shadowing + ambiguity)
- [ ] per-language RED-first unit tests + cross-language gate test
- [ ] dogfood on a Java or Go repo shows a measurable classified-share rise
- [ ] CLI/MCP parity unaffected; full suite green
- [ ] Docs/CODEMAPS + RFC status -> implemented

## What this RFC does NOT do (deferred)

- Full per-language type inference / prototype resolution.
- Languages beyond Java/Go/JS/TS (C#/Ruby/Rust follow the same shape later).
- File-level resolution of stdlib methods to their owning module (separate RFC).

## Open questions

1. Land all three languages in one PR, or one per PR (Java first, where
   `_java_constants.py` already exists)? Recommendation: one PR per language for
   focused Codex review.
2. Go: is the receiver-method gap large enough to justify a table, or is import
   resolution already covering most of it? Measure on a real Go repo first.
