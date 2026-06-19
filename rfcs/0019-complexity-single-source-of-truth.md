# RFC-0019: Cyclomatic complexity — one source of truth

- **Status**: draft
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-19
- **Last updated**: 2026-06-19
- **Tracking issue**: #1094
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/languages/` (the per-language extractor complexity functions — the chosen source of truth)
  - `tree_sitter_analyzer/health_scorer.py` (`DECISION_NODE_TYPES`, `score_complexity`)
  - `tree_sitter_analyzer/_ast_extraction.py` (`_count_complexity_in_node`, `analyze_file_complexity`)
  - `tree_sitter_analyzer/complexity_heatmap.py`
  - `tests/unit/test_complexity_heatmap.py`, `tests/unit/languages/test_cyclomatic_complexity.py`, golden masters carrying a `Cx` column

## Summary

Cyclomatic complexity is currently computed by **three independent
implementations** that disagree on the same function. Consolidate them so every
consumer (the extractor, `project_health`, the complexity heatmap/hotspot)
derives complexity from **one** per-language function. No new behavior — this is
a correctness/consistency fix that removes a duplication root cause.

## Motivation

#1080–#1098 fixed cyclomatic complexity **eight times** — once per language — but
only in the *extractor* path (`languages/*`). Two other implementations were
never touched and still disagree:

1. **`health_scorer.DECISION_NODE_TYPES`** — its own per-language node set used by
   `score_complexity`. The `java` entry lists `switch_statement` /
   `conditional_expression` (names tree-sitter-java never emits — it emits
   `switch_expression` / `ternary_expression`) and omits `do_statement`; the
   `javascript`/`typescript` entries list `conditional_expression` (emitted as
   `ternary_expression`). So `project_health` silently undercounts Java/JS/TS
   `switch` / `ternary` / `do-while`.
2. **`_ast_extraction._count_complexity_in_node`** — its own per-language set that
   counts `switch_case` / `case_clause` / `switch_block_statement_group` **per
   arm**, so `analyze_file_complexity(...)` reports Cx ≈ 5 for a 4-case switch
   where the extractor (and the golden `--table full`) now report 2.

Concrete: `examples/BigService.java::performBackup` is `Cx 2` in the golden
formatter output but the heatmap/health path scores it differently, so the
user-facing heatmap / hotspot ranking / health grade are inconsistent with the
`--table` output and with each other. Worse, the same class of bug has to be
fixed three times forever. The audit history (this is the eighth+ complexity PR)
is itself the motivation: **duplicated decision tables are a bug factory.**

## Detailed design

Pick the **extractor per-language functions as the single source of truth**
(they are the most-tested, RED-first-pinned, and already correct after
#1080–#1098), and route the other two consumers through them.

### A shared dispatcher

Add `tree_sitter_analyzer/languages/complexity.py`:

```python
def cyclomatic_complexity(function_node, language: str) -> int:
    """Return 1 + decision points for a function/method node, using the
    language's own (extractor) complexity walker. The single source of truth
    for every consumer (extractor, health_scorer, heatmap)."""
```

**Signature heterogeneity (found while prototyping — the wrinkle this RFC must
pin down).** The per-language walkers do NOT share a signature today:
`_java_ast_helpers.calculate_complexity(node)`, `_complexity_decisions.
count_decision_complexity(node)` and most others take a bare node; but
`csharp_helpers.calculate_complexity(node, traverse_fn)` needs a traversal
helper, `typescript_plugin._text_helpers.calculate_complexity(node,
get_node_text, cache)` needs two more, and the Python path
(`python_plugin/_node_helpers.calculate_complexity(body: str)`) takes a **source
string**, not a node. So the dispatcher cannot be a 1-line `FUNCS[language]
(node)`.

The dispatcher therefore owns a small **per-language adapter table** mapping
`language -> Callable[[node], int]`, where each adapter closes over whatever the
underlying walker needs (a no-op `traverse_fn`/cache for C#/TS; for Python,
either migrate its body-string counter to a node walk or have the adapter
re-extract the body text). Normalising these signatures — ideally giving every
plugin a uniform `complexity(function_node) -> int` — is the bulk of the work
and is the part reviewers should scrutinise. It also means the migration is best
done **language-by-language** behind the dispatcher (start with the already-
node-shaped ones; Python and C#/TS adapters last), each step keeping the
extractor byte-identical.

It dispatches `language -> the existing per-language function` already used by the
extractors (`_java_ast_helpers.calculate_complexity`, `ruby_plugin.
_ruby_calculate_complexity`, `_complexity_decisions.count_decision_complexity`
for JS/TS, `scala_plugin.calculate_scala_complexity`, the Go/Rust/Swift/PHP/
Kotlin/C/C++/C# walkers, …). The extractor element builders keep calling their
own walker (or this dispatcher — equivalent), so the extractor path is
behavior-preserving.

### Consumers

- **`health_scorer.score_complexity`** — delete `DECISION_NODE_TYPES`; parse the
  file (it already has `source`+`language`), walk to each function node, and sum
  `cyclomatic_complexity(node, language)`. The normalization (`CC_IDEAL`, the
  0–100 score) is unchanged.
- **`_ast_extraction._count_complexity_in_node`** — delete its per-language set;
  call the dispatcher. `analyze_file_complexity` already has the parsed nodes.

### Algorithms

No algorithm change — the per-language walkers are the spec. This RFC only
removes the two duplicate tables and points their callers at the canonical
walker.

## Three-Surface impact (CLI ↔ MCP parity)

- CLI `--table` / `--advanced` already use the extractor value — **unchanged**.
- MCP `health` (project_health) and `viz`/heatmap tools change to the canonical
  value — these are the surfaces being *corrected*. After this RFC all three
  surfaces report the same Cx for the same function.

## Drawbacks

- Health grades and heatmap numbers **change** for Java/JS/TS switch/ternary/
  do-while-heavy and (heatmap) switch-heavy code — they go *down* (the old
  values were inflated/undercounted). Golden/score tests must be re-pinned with
  the corrected values. This is a one-time, conscious re-pin (exact-assertion
  rule), and it makes the numbers *correct*, but it is user-visible movement.

## Alternatives

- **Alternative A — have consumers read `element.complexity_score`.** Instead of
  a dispatcher, `health_scorer`/`heatmap` could run the plugin extractor and use
  the element's `complexity_score`. Pros: even less duplication. Cons: heavier
  (full element extraction) where a function-node walk suffices; couples health
  scoring to the full extractor pipeline. **Deferred**, not rejected — the
  dispatcher leaves this open as a later simplification.
- **Alternative B — keep three tables, just sync them.** Rejected: that is the
  status quo that produced eight duplicate fixes; it will drift again.

## Prior art

- #1080–#1098: the eight per-language extractor fixes this RFC consolidates.
- The codebase already centralizes the `&&`/`||` rule in
  `languages/_complexity_logical.py` and the JS/TS walk in
  `languages/_complexity_decisions.py` — this RFC extends that consolidation to
  the cross-consumer dimension.

## Test plan (RED-first)

1. **Cross-path invariant** (new, the keystone): for a fixture with one
   `switch`(3 arms) + one ternary + one `do-while`, assert
   `extractor_cx == health_path_cx == heatmap_path_cx` for Java, JS, TS — RED
   today (they differ), GREEN after.
2. Re-pin `tests/unit/test_complexity_heatmap.py` values that drop (switch-heavy
   fixtures) to the canonical numbers.
3. Re-pin any `project_health` score tests whose grade shifts; record the
   measured before→after.

## Acceptance criteria

- [ ] `cyclomatic_complexity(node, language)` dispatcher added; extractor path
      byte-identical (no golden change from the extractor side).
- [ ] `health_scorer` no longer defines `DECISION_NODE_TYPES`; uses the dispatcher.
- [ ] `_ast_extraction` no longer defines its own decision set; uses the dispatcher.
- [ ] Cross-path invariant test passes for Java/JS/TS (and a parametrized sweep
      over all 13 languages where the construct exists).
- [ ] All grade/heatmap re-pins are exact values with a recorded before→after.

## What this RFC does NOT do (deferred)

- Does not change the per-language complexity *definition* (that is the
  extractor spec, already settled by #1080–#1098).
- Does not adopt Alternative A (consume `element.complexity_score`) — left as a
  follow-up.
- Does not add a new MCP tool or CLI flag.

## Open questions

- Python's counter takes a source *string*; migrate it to a node walk
  (preferred — uniform signature) or adapt by re-slicing the body? 
- Should `health_scorer` parse independently or reuse a cached parse? (Perf —
  health already parses for other metrics; reuse if cheap.)
