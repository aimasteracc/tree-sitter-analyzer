# RFC-0010: Resolver language registry — scale the correctness moat to N languages

- **Status**: draft
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-07
- **Last updated**: 2026-06-07
- **Tracking issue**: TBD
- **Builds on**: RFC-0008 (multi-language method classification — Java shipped #326)
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/synapse_resolver/__init__.py` (`resolve_callee` dispatch)
  - `tree_sitter_analyzer/synapse_resolver/_context.py` (`ResolverContext`, `build_resolver_context`)
  - `tree_sitter_analyzer/synapse_resolver/_registry.py` (NEW — the registry)
  - `tree_sitter_analyzer/synapse_resolver/_java.py` (migrate to self-register)
  - `tree_sitter_analyzer/synapse_resolver/languages/__init__.py` (NEW — auto-discovery)
  - `tree_sitter_analyzer/synapse_resolver/languages/<lang>.py`, `_<lang>_constants.py` (per-language, NEW)
  - `tests/unit/test_<lang>_method_resolution.py` (per-language, NEW)

## Summary

Make the callee-resolution cascade **extensible by language without editing shared
files**, so multiple independent teams can add a language each — in parallel —
without colliding. Today adding a language (à la Java, RFC-0008) requires editing
THREE shared files: a `ResolverContext.java_context` field, a
`_maybe_build_java_context` builder + its call in `build_resolver_context`, and an
`if language == "java"` branch in `resolve_callee`. With N concurrent
language teams those edits guarantee merge conflicts (and, with git worktrees,
index-corruption races — observed twice). This RFC introduces a **language
registry** + a `languages/` auto-discovery subpackage: a new language is one
self-contained module under `languages/` that calls `register_language(...)`, plus
its constants and tests. ZERO edits to any existing file.

This directly widens TSA's **only measured competitive lead** — call-graph edge
correctness (96.3% of `calls` edges classified, ~0.01% cross-language mis-wires,
measured from `.ast-cache/index.db`; the full repro lands as the correctness
report in **PR #343**, `benchmarks/codegraph_compare/REPORT-v1.21.0.md`). Today
that lead is Python +
Java. Every additional language with classified tiers is correctness CodeGraph
structurally cannot match (it name-collides across languages; TSA gates by
language family). The registry is the lever that turns "one language per careful
RFC" into "five teams in parallel."

## Motivation

- **The moat is multi-language correctness.** The correctness report (PR #343) shows CodeGraph wires
  299 Python `sorted()` callers to a Swift `func sorted`; TSA refuses. That win
  generalises only as far as TSA has per-language resolution. Python + Java today;
  the registry unlocks Go/JS/TS/C++/Rust/… next.
- **Parallelism needs isolation.** The investor mandate is "a team per supported
  program, ~5 at a time." Five teams editing `_context.py` + `__init__.py`
  concurrently is unworkable. The registry makes each language an island.
- **Safety-critical core.** The resolver IS the correctness machinery. A
  refactor here must be **behaviour-preserving** (the 401 resolver/synapse tests
  stay green) and is RFC-gated for exactly that reason.

## Detailed design

### Data structures — `_registry.py` (new)

```python
class LanguageResolver(NamedTuple):
    language: str
    build_context: Callable[..., Any | None]   # common kwargs -> per-lang context | None
    resolve_callee: Callable[[str, str, str, Any], tuple[str | None, str, str]]
                    # (bare_name, full_name, caller_file, lang_context) -> (sym_id, resolution, resolved_file)

_REGISTRY: dict[str, LanguageResolver] = {}
def register_language(language, build_context, resolve_callee) -> None: ...
def get_language_resolver(language: str | None) -> LanguageResolver | None: ...
def registered_languages() -> list[str]: ...
```

### Context building — registry-driven, circular-dep-free

`build_resolver_context` precomputes the COMMON derived inputs once
(`imports_by_file`, `file_languages`, `file_symbols`, `global_name_table`,
`file_class_methods`, `conn`, `line_idx`) and then iterates
`registered_languages()`, calling each `build_context(**common)`. Each builder
does its OWN gating (e.g. Java returns `None` when no file is Java — zero cost for
Python-only projects, preserved) and its OWN per-language filtering. Results are
stored in a generic `ResolverContext.lang_contexts: dict[str, Any]`. Passing
`file_class_methods` in (rather than the builder importing it from `_context`)
breaks the `_java` ↔ `_context` import cycle.

`ResolverContext.java_context` stays as a back-compat property returning
`lang_contexts.get("java")`, so existing callers/tests do not change.

### Dispatch — registry lookup

```python
def resolve_callee(callee_name, caller_file, ctx, callee_full=None, caller_name=""):
    language = ctx.file_languages.get(caller_file)
    resolver = get_language_resolver(language)
    lang_ctx = ctx.lang_contexts.get(language) if resolver else None
    if resolver is not None and lang_ctx is not None:
        sym_id, resolution, resolved_file = resolver.resolve_callee(
            callee_name, callee_full if callee_full is not None else callee_name,
            caller_file, lang_ctx)
        return ResolvedCallee(sym_id, resolution, resolved_file)
    return _resolve_callee_python(callee_name, caller_file, ctx, callee_full, caller_name)
```

Python remains the default fallback cascade verbatim (no behaviour change).

### Registration wiring — auto-discovery, ZERO shared edits

To make parallel language PRs **truly** conflict-free (a single shared
`_languages.py` append point would still collide when 5 PRs each add a line —
Codex #344), language modules live in a dedicated subpackage
`synapse_resolver/languages/` with one module per language
(`languages/go.py`, `languages/java.py`, …). `languages/__init__.py` auto-imports
every submodule once at package load:

```python
# synapse_resolver/languages/__init__.py  (fixed; never edited to add a language)
import importlib, pkgutil
for _m in pkgutil.iter_modules(__path__):
    if not _m.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_m.name}")
```

Each `languages/<lang>.py` calls `register_language(...)` at import. The resolver
package imports `languages` once. **Adding a language = adding ONE new file in
`languages/` + its constants + its tests. No existing file is edited** — no merge
conflict, no worktree race, for any number of parallel teams. A discovery test
asserts every `languages/*.py` module registered a resolver (catches a typo or a
module that forgot to register).

Constants live next to the module (`languages/_<lang>_constants.py` or inline) so
they are also new-file-only.

## The per-language team contract (what each of the ~5 teams ships)

One PR per language, **fully isolated — zero edits to any existing file**:

1. `languages/<lang>.py` — `build_<lang>_context(**common) -> ctx | None` (gated on
   the language being present) and `resolve_<lang>_callee(bare, full, file, ctx) ->
   (sym_id, resolution, resolved_file)`, ending in `register_language(...)`.
2. `languages/_<lang>_constants.py` (or inline) — `STDLIB_METHODS_<LANG>`,
   `EXTERNAL_METHODS_<LANG>`, etc. **Conservative tiers only** (see below).
3. `tests/unit/test_<lang>_method_resolution.py` — RED-first, tests the resolver
   directly + an integration test through `resolve_callee`.

(The foundation PR provides `languages/__init__.py` auto-discovery + migrates Java
to `languages/java.py`; from then on, every language PR is new-files-only.)

### Conservative-tier rule (the RFC-0008 lesson — MANDATORY)

RFC-0008's Java work proved that **method-name classification without receiver
inference has a low precision ceiling**: an over-broad stdlib/external name set
mis-classifies inherited/DDD/value-object methods. Java's `STDLIB_METHODS_JAVA`
was cut 90 → 12 (only `String`/`Optional`-final exclusive names) and
`EXTERNAL_METHODS` 44 → 18 (assert* static families) before it was correct.
**Every language team starts conservative**: include a name in a classified tier
ONLY if it is (near-)exclusively that stdlib/external API and unlikely to be a
user method. Precision over recall — an `unknown` edge is correct; a
mis-classified edge is the exact CodeGraph failure this project exists to avoid.

### First wave (5 teams)

Ordered by agent-codebase prevalence and corpus availability:
`go`, `javascript`, `typescript`, `cpp`, `rust`. (Kotlin/Scala/PHP/Ruby/C# in a
later wave.) Each gates hard; a language with no safe stdlib/external set ships
with an **empty** classified tier (still correct — everything stays `project`/
`unknown`, never cross-wired) rather than a guessed one.

## Three-Surface impact (CLI ↔ MCP parity)

No new CLI/MCP surface. `resolve_callee` is internal; the registry changes how
edges are classified at index time. CLI (`--callers`/`--callees`) and MCP
(`nav action=callers/...`) both read the same classified edges, so they move
together automatically. The parity check is: same classified edges via both
surfaces for a fixture in the new language.

## Drawbacks

- A core-resolver refactor carries regression risk. Mitigated by the
  behaviour-preserving requirement + the 401-test gate + Java-output parity (the
  registry path must produce byte-identical Java classification to today).
- Eager import of all `_<lang>` modules at package load. Cost is function
  definitions + dict inserts (microseconds); context BUILD stays gated/lazy.

## Alternatives

- **Keep editing the if-chain per language, merge sequentially.** Rejected: the
  investor mandate is parallel teams; sequential merges serialise the moat-widening
  and re-introduce the worktree-race surface.
- **Manual `_languages.py` import list.** Rejected (Codex #344): a single shared
  append point still collides when N PRs each add a line. Auto-discovery of a
  `languages/` subpackage is the only design with literally zero shared edits;
  the fragility concern is closed by a discovery test that asserts every
  `languages/*.py` registered a resolver.
- **Sequential merges of an if-chain.** Rejected: serialises the moat-widening and
  re-introduces the worktree-race surface the investor mandate is trying to avoid.

## Test plan (RED-first)

- **Foundation (this RFC's core PR):**
  - All 401 existing resolver/synapse/callee tests stay green (behaviour-preserving).
  - Java classification output is **identical** before/after (golden parity test:
    same `(sym_id, resolution, resolved_file)` for a Java fixture corpus).
  - New `test_resolver_registry.py`: `register_language` a fake language, assert
    `resolve_callee` routes to it when a file is that language, falls back to
    Python otherwise, and `build_resolver_context` builds its context.
- **Per-language PR:** RED-first resolver unit tests (stdlib/external/project/
  unknown cases) + one `resolve_callee` integration test + a "no cross-language
  mis-wire" assertion (a same-name symbol in another language is NOT bound).

## Acceptance criteria

- [ ] `_registry.py` + `register_language`/`get_language_resolver` exist; Java
      migrated to self-register; `_context.py` + `__init__.py` are registry-driven
- [ ] 401 resolver tests green; Java classification byte-identical (parity test)
- [ ] `languages/` subpackage with auto-discovery; adding a language requires
      **zero edits to any existing file** (only new files: `languages/<lang>.py`,
      its constants, and tests) — verified by a discovery test
- [ ] Auto-discovery test: every `languages/*.py` module registered a resolver
- [ ] First-wave languages land one focused PR each, conservative tiers,
      adversarial-reviewed, with a "no cross-language mis-wire" test
- [ ] The correctness report (REPORT-v1.21.0, PR #343, or a successor) re-measures the classification rate +
      cross-language count across the newly-supported languages
- [ ] Docs/CODEMAPS updated; RFC status → implemented

## What this RFC does NOT do (deferred)

- Receiver-type inference (the path to higher per-language precision) — separate
  RFC; each language ships name-tier classification first.
- File-level resolution of stdlib/external methods (RFC-0004 phase 2).

## Open questions

1. Golden-parity: snapshot Java `(sym_id, resolution, resolved_file)` for the
   `tests/golden/corpus_java.java` corpus and assert equality across the refactor?
   (Proposed: yes — it is the strongest behaviour-preservation guarantee.)
2. Should an empty-tier language (no safe stdlib set yet) still register, to get
   the cross-language gating (never bind `sorted` across languages) even without
   classification? (Proposed: yes — gating is the correctness win; classification
   is the completeness win.)
