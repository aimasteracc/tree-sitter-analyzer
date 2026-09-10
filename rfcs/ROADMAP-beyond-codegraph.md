# Strategic Roadmap — beyond CodeGraph (2026-06-06)

> **Historical strategy.** The active No.1 program is now
> [`ROADMAP-no1-agent-trust.md`](ROADMAP-no1-agent-trust.md). This document remains
> the record of the correctness-moat work and its original priorities. All comparative
> tables, rates, costs, and leadership language below are quarantined historical notes:
> they are not claim-registry evidence and must not support public wording. Re-admit a
> conclusion only through the active RFC-0021 E4 policy with named versions, repositories,
> date, model/backend, artifacts, and independent reproduction. Hand-counted support
> totals below are snapshots of their cited commits; current dimensions come only from
> [`docs/language-support-inventory.json`](../docs/language-support-inventory.json).

PM strategy note. Where TSA stands vs CodeGraph (CG) after the v1.21.0 work, and
the prioritized path to becoming the default agent code-intelligence layer.

## Where we stand (measured on this repo)

| axis | TSA | CG | verdict |
|---|---|---|---|
| symbol kinds (kind=method) | 20,348 | 20,275 | TSA ahead |
| callee classification | 96.3% (.ast-cache, measured) | many same-name mis-wires | TSA ahead (correct AND complete) |
| cross-language safety | ~0.01% mis-wires across 13 active languages (py/java/go/js/ts/c/cpp/rust/csharp/kotlin/ruby/php/swift), each with extraction + a dedicated resolver | wires 299 Python `sorted()` callers to a Swift func | TSA structurally ahead — gated by language family, ~0.01% residual (generic Java names) vs CodeGraph's wholesale cross-language collapse; see REPORT-v1.21.0 |
| FTS production-first | yes | test-mock shadows | TSA ahead |
| edges_by_kind status | yes | none | TSA exclusive |
| token / context call | ~6.6k (was 12.7k) | ~4.4k | gap 2.9x to 1.5x; near parity |
| nav context self-sufficiency | A/B/C shipped (RFC-0009, #330/#331/#333) | n/a | full entry bodies + entry-first ranking + generic-verb candidate filter; measured turn-drop pending (gated on benchmark) |
| reactive push | implemented (RFC-0001, #336 surfaced) | none | TSA exclusive |

TSA's thesis is now defensible: correct + complete + nearly as cheap, with
capabilities CG lacks. The remaining work is to make each lead decisive and
measured, not anecdotal.

## Prioritized initiatives (impact x confidence / cost)

### P0 — Prove the token-cost win with a real benchmark
The README still cites a pre-RFC-0006 dollar table. Re-run
benchmarks/codegraph_compare/run.py phase full-warm --repos gin,django on
current develop to get the real per-task cost after the 53% payload cut.
If TSA is now within ~1.1x of CG (or cheaper), the "CG is cheaper" caveat can be
retired with evidence. This converts a hedge into a headline. (Needs API budget;
user has authorized spend.)

### P1 — Multi-language correctness moat (RFC-0008 + RFC-0010): 14 CALL-DISPATCH LANGUAGES IN THIS HISTORICAL SNAPSHOT
The 83.9% → 96.5% classification win was Python-only; the cross-language-safety
win generalises only as far as TSA has per-language resolution. **All 14 call-dispatch languages in this post-Scala snapshot are ACTIVE (extraction + resolver + moat):
py/java/go/js/ts/c/cpp/rust (wave 1 + #358), csharp/kotlin/ruby/php (#360), swift (#364 — the language CodeGraph mis-wires INTO), and scala (#1143).** RFC-0010 (#345) introduced a language **registry + auto-discovery**
so a language is a self-contained `languages/<lang>.py` module — added with ZERO
edits to shared files, in parallel. First wave landed: **Go (#350), JavaScript
(#346), TypeScript (#347), C++ (#348), Rust (#349)** — on top of Python + Java
(#326). Every one: conservative stdlib/external tiers, **adversarially verified to
never cross-language bind** (the moat), Java classification byte-identical (no
regression), Codex-hardened over 3 precision rounds each. Scala (#1143, 2026-07-11)
completes the moat: receiver-guard prevents `items.map` from binding to a same-file
`map` symbol, and cross-language filtering blocks Python/Go symbols from resolving
as Scala project matches. **All 14 listed languages in this historical snapshot have dedicated call resolution;
the axis CodeGraph structurally cannot match (it name-collides across
languages — see REPORT-v1.21.0).**

### P2 — File-level resolution of stdlib/builtin methods (RFC-0004 phase 2)
Today stdlib/external/builtin methods are classified but not file-resolved.
Receiver-type inference (annotation + constructor-assignment driven) would point
p.write_text() at pathlib, raising the file-resolution rate and enabling
"jump to the stdlib def" for agents. Precision-sensitive; gate hard.

### P3 — Reactive push as a demoed differentiator
RFC-0001 is **implemented** (subscription registry + watch→push bridge + resource
read; #336 surfaced it in the MCP differentiators) but still under-demoed. Add a
CLI watch --subscribe mode + a recorded demo (edit a file, agent receives
resource_updated, re-reads the changed set). No competitor has this; make it legible.

### P4 — Resolution confidence signal
Expose per-edge callee_resolution + a confidence so agents can trust/distrust a
binding. Turns the resolved graph from a black box into an auditable one — directly
on-thesis ("agents know before they touch").

## Operating discipline (keep)
- RFC-first for substantial changes; RED-first TDD; one PR = one feature.
- Triage every Codex review (locked) — 14 findings this cycle, all real-fixed or
  clean. Codex caught 3 latent dead-code/wiring bugs that local tests missed.
- docs-only changes now skip the heavy matrix (CI smart-routing, #323).

## Next action
Landed on develop: RFC-0009 A/B/C (#330/#331/#333), the correctness report
(REPORT-v1.21.0, #343), RFC-0010 registry foundation (#345), the **first-wave
language resolvers** Go/JS/TS/C++/Rust (#346-#350), **wave 2**
(csharp/kotlin/ruby/php, #360, plus swift, #364), and **Scala** (#1143,
2026-07-11) — the correctness moat snapshot spans **14 call-dispatch languages**
(Python + the 13 listed `synapse_resolver/languages/` modules). This is not a
current pipeline-support count; use the generated inventory linked above. P1 was
recorded complete for that historical scope.
Next: implement the pre-registered **N≥5 cost benchmark** in
[RFC-0021](0021-real-world-competitive-benchmark.md), beginning with its
no-model setup-validation and measurement-integrity gates; **keep the moat
numbers current** (README + REPORT-v1.21.0 + GAUNTLET.md)
as the codebase grows — see the 2026-07-10 re-measurement note in
REPORT-v1.21.0.md (classification rate and cross-language edge count refreshed
against `develop`@`6fe62fba`; the CodeGraph-vs-TSA ratio itself awaits a
documented CodeGraph install path before it can be re-verified).
