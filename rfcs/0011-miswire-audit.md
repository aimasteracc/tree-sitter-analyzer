# RFC-0011: Mis-Wire Audit — the run-on-your-repo correctness demo

- **Status**: accepted — console entrypoint + module + tests shipped (this PR); CLI subcommand + pre-seed + README surgery tracked below
- **Author(s)**: TSA strategy team (4-lens panel + chair, 2026-06-08)
- **Created**: 2026-06-08
- **Affected surfaces**: new console entrypoint `miswire-audit`; `tree_sitter_analyzer/miswire_audit.py`; `tests/benchmarks/test_miswire_audit.py`

## Summary

Ship `miswire-audit <repo-or-path>` — a single command that runs TSA's
cross-language correctness check on the **reader's own repository** and prints a
stark, personalized verdict: how many call edges a **name-only resolver** (the
design CodeGraph and most code indexes use) *would* mis-wire across a language
boundary, versus how many TSA actually does. No CodeGraph install required.

    uvx --from tree-sitter-analyzer miswire-audit .
    # → "a name-only resolver would mis-wire 4,199 call edges in YOUR repo;
    #    TSA mis-wires 6 — 700× cleaner. Here are 5: Python sorted() → Swift func …"

## Motivation

TSA has **won** the correctness axis and **proven** it: on both tools' live
indexes of TSA's own repo, CodeGraph makes 745 cross-language call-graph
mis-wires vs TSA's 6 — ~390× cleaner (REPORT-v1.21.0 addendum 2). But that proof
is *illegible*: it lives as a static table about TSA analysing TSA's own source,
which a reader must **trust**. The strategy team (growth, DX, competitive, moat
lenses) unanimously concluded the highest-leverage next move is to convert
"trust my table" into "watch it find wrong edges in code **you** wrote" — the
canonical OSS dev-tool breakout pattern (ruff, biome, oxc, sqlfluff all broke out
on a run-it-on-your-code benchmark, never on blog claims). A self-serve,
falsifiable, screenshot-worthy audit is simultaneously the demo, the Show HN
submission, the comparison page, and the SEO/social asset — and it is the one
format where "more correct" mechanically becomes "more known," because skeptics
reproduce it on their own code and amplify it.

## Detailed design

`audit(project_root)` indexes the repo with TSA, then for every `calls` edge:

- **TSA mis-wire**: the edge's `callee_resolved_file` is in a language
  *incompatible* with the caller (the real, measured cross-language bind). TSA's
  family-gated resolver keeps this ~0.
- **Name-only mis-wire (modeled, no CodeGraph install)**: the callee name has a
  same-name definition in the index but **none** in a compatible language — so a
  resolver that binds by name alone has only a cross-language def to choose, and
  wires across the boundary. This is the worst case for the name-only design.

Output: total edges, the name-only count + rate, TSA's count + rate, the
multiplier, and the top-N **distinct** offending names (`Python sorted() → Swift
func at file:line`). A `--card` flag emits a copy-paste markdown/social card.

### Honesty (a locked project value)

The modeled name-only figure is an **upper bound for the name-only design**, NOT
CodeGraph's exact count (CodeGraph does *some* language handling — 745 < the
4,199 pure-name-only bound on TSA's repo). The output therefore says "**a
name-only resolver** would mis-wire up to N" and points to REPORT-v1.21.0 for the
**live, CodeGraph-specific** 745-vs-6. We never label the modeled number as
CodeGraph's measured count — one debunk-able claim destroys the trust the proof
exists to build.

## Three-Surface (CLI ↔ MCP) parity

This is a **distribution/demo artifact**, not a code-intelligence query, so it
ships first as a console entrypoint (`miswire-audit`). Parity follow-ups (below):
a `tree-sitter-analyzer miswire-audit` CLI subcommand and, if demanded, a thin
MCP `viz action=miswire_audit` so an agent can self-audit a repo. The core
resolution logic it reports on already has full CLI↔MCP parity (the resolver).

## Test plan (RED-first)

- [x] A planted polyglot fixture (Python `sorted()` caller + Swift `func sorted`)
      → the name-only model flags `sorted → swift`; TSA mis-wires 0.
- [x] A clean single-language repo → 0 and 0.
- [x] Rendering is honest: says "NAME-ONLY resolver", points to REPORT-v1.21.0,
      never claims "CodeGraph would mis-wire N".

## Acceptance criteria

- [x] `miswire-audit <path>` console entrypoint; module under the package;
      ruff+mypy clean; 3 RED-first tests green.
- [ ] `tree-sitter-analyzer miswire-audit` CLI subcommand (parity follow-up).
- [ ] Pre-seed `--card` results for 5 well-known repos under
      `benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md` so the README shows
      results before anyone clones. *(path correction 2026-06-12: the 5-repo table
      lives in `benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md`, not `results/`)*
- [ ] README surgery: make the `miswire-audit` one-liner the first runnable block
      above the fold; lead with the scorecard.

  *Clarification (2026-06-12):* This criterion now conflicts with the #501
  README structure decision (`docs(readme): one-sentence lede, merged quick-start,
  comparison after features`), which established that the lede + quick-start go
  first and the comparison section follows features. Reordering the README to lead
  with the miswire scorecard would revert that structure. **This criterion needs an
  owner re-decision before implementation.** Do NOT reorder the README in the
  meantime; the #501 structure is the current baseline.

## Open questions

1. Should the name-only model exclude language builtins (Python `print`) to be
   even more conservative? Current "up to N / worst case" framing is honest; a
   `--exclude-builtins` mode could show the floor too.
2. MCP facade for agent self-audit — only if demanded.
