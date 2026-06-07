# Strategic Roadmap — beyond CodeGraph (2026-06-06)

PM strategy note. Where TSA stands vs CodeGraph (CG) after the v1.21.0 work, and
the prioritized path to becoming the default agent code-intelligence layer.

## Where we stand (measured on this repo)

| axis | TSA | CG | verdict |
|---|---|---|---|
| symbol kinds (kind=method) | 20,348 | 20,275 | TSA ahead |
| callee classification | 96.5% (after #324) | many same-name mis-wires | TSA ahead (correct AND complete) |
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

### P1 — RFC-0008 multi-language method classification (Java shipped; Go/JS/TS remaining)
The 83.9% to 96.5% classification win was Python-only. Extend the cascade tiers to
Java/Go/JS/TS so polyglot repos get the same resolved-graph completeness. One PR
per language. **Java shipped** (#326 — stdlib/external tiers + method-call name
extraction, on develop); Go/JS/TS still pending. Largest single lever for
non-Python users.

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
RFC-0008 Java (#326) and RFC-0009 A/B/C (#330/#331/#333) have landed on develop. Next:
P0 (benchmark) to retire the "CG is cheaper" caveat with evidence, and continue
P1 (RFC-0008 Go/JS/TS) for the remaining polyglot reach.
