# RFC-0017: Test effectiveness — mutation scoring, value invariants, and outside-the-loop authorship

- **Status**: accepted (owner approved 2026-06-14; phase 1 = mutation baseline first)
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-14
- **Last updated**: 2026-06-14
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tests/unit/mcp/test_output_cost_invariants.py` (new + extended)
  - `tests/effectiveness/` (new — mutation harness config + reports)
  - `pyproject.toml` (dev-deps: `mutmut` or `cosmic-ray`)
  - `.github/workflows/` (new gate: value-invariants required; mutation score reported)
  - `CLAUDE.md` (codify "test value not just conformance" + "test author ≠ code author")

## Summary

Our test suite is ~2× the size of the source it covers, yet in a single
session it failed to catch **nine real P1/P2 defects** — every one was found by
an outside-the-loop signal (a human dogfooding, or the Codex reviewer), not by
the suite. This RFC diagnoses why (the suite tests **conformance** — "does the
code match its spec?" — and is structurally blind to **value** — "is the spec
good / does the tool deliver what it advertises?") and proposes four mechanical
countermeasures: (1) **mutation scoring** to quantify whether tests *can* catch
bugs; (2) **per-tool value invariants** (output size / latency / advertised
capability) as CI gates; (3) **outside-the-loop test authorship** (RED-first
against an independent spec, author ≠ implementer); (4) **boundary + all-consumer
testing** for shared components. None of these is "write more tests" — they
change *what* tests assert and *how* discovery happens.

## Motivation

### The evidence (this session, 2026-06-14)

A seven-PR fix cascade produced nine real defects. The suite (≈18k tests, all
green throughout) caught **zero**:

| Defect | Found by | Why the suite missed it |
|---|---|---|
| `ast_diff` returns 155 KB for a small diff (#552) | human dogfood | tests asserted hunks are *correct*, never that output is *small* |
| `lineage` advertises inheritance, returns only an impact profile (#568/#688) | dogfood | tests asserted the impact profile is correct, not that the tool delivers its *advertised* capability |
| 7 facade actions ship no `agent_summary` (#577/#695) | QC dogfood | contract test didn't *cover* those 7 actions |
| `classify(include_ast_nodes=True)` broke after a shared `to_dict` default change (#694→#696) | Codex | byte-budget test covered only the *default* path; the opt-in path had no test |
| `ast_path` summary reads non-existent keys → "0 nodes" always (#697) | Codex | #577 test asserted `agent_summary` *exists*, never its *content* |
| `impact` blast_radius advises editing an unknown symbol (#697) | Codex | no test for the not-found edge |
| children leak into `codegraph_pr_review` (3rd consumer of the same serializer) (#698) | Codex | no test enumerated the serializer's consumers |
| `find_references` budget eaten by vendored/dot dirs → `refs=0` (#568-2/#699) | dogfood | no test exercised the file-walk's exclude behavior |
| the #699 fix itself broke when the project root sits under a dotted ancestor (#700) | Codex | the #699 RED test used a clean `tmp_path`, never the edge case |

### First principles

A test answers only the question you encode. We encoded one question —
*"does the code match its spec?"* (`assert field == X`, `set(keys) <= SURFACE`)
— ~18k times. A conformance test **cannot discover that the spec itself is
wrong or wasteful**: a 155 KB response, a tool that doesn't do what it
advertises, a 1.96× TOON bloat (the #11 incident already in CLAUDE.md) are all
"correct per spec." So **2× conformance volume = 0× discovery**. Worse, volume
breeds false confidence that suppresses the only thing that *does* find these
defects: real use and independent review.

The incentive gradient explains the shape: conformance tests are cheap to write
(assert what the code does), always green, and an agent writing code+tests in
one shot produces them by default; value tests are expensive (require knowing
what "good" means, independent of the implementation) and often red. Rewarding
"green CI + coverage %" mass-produced green conformance and avoided value tests.

The one counter-example proves the thesis: the **single** value test we had —
the #543 classify byte-budget — was the **only** suite test that caught a real
regression this session (the #552 child_count leak).

## Detailed design

Four mechanisms. Each is mechanical (a gate or a measured number), not a
guideline.

### 1. Mutation scoring — quantify whether tests *can* catch bugs

Add `mutmut` (preferred; simple, Python-native) or `cosmic-ray` as a dev
dependency. Mutation testing deliberately perturbs the code (flip `==`→`!=`,
`<`→`<=`, drop a statement, change a constant) and reports the fraction of
mutants the suite kills. A module with 95% line coverage but a low mutation
score is the precise definition of "形同虚设" (tests that execute code without
asserting anything that matters).

- **Scope (phase 1)**: the highest-leverage core modules only — `ast_diff.py`,
  `semantic_change_classifier.py`, `mcp/tools/facade_tool.py`,
  `mcp/tools/query_symbol_search.py`, the TOON encoder. (Whole-repo mutation is
  too slow for CI; target the modules where defects escaped.)
- **Runner (Codex P2)**: `mutmut` relies on `os.fork`, which does not exist on
  Windows; the mutation job runs on **`ubuntu-latest` only** — it is NOT part of
  the cross-platform reusable test matrix (which includes `windows-latest`). The
  per-PR test matrix is unchanged; the mutation job is a separate, Linux-pinned
  workflow. (If we ever switch to `cosmic-ray`, the same Linux-only pin holds.)
- **Output (Codex P2)**: the per-run mutation report is a **CI artifact**
  (uploaded + retained), NOT committed — committing generated results every
  nightly/on-label run would dirty the repo or require bot commits. Only a
  single human-curated **baseline summary** (the surviving-mutant count per
  module, the number that answers "why don't our tests catch bugs") is recorded
  in a tracked file (`tests/effectiveness/BASELINE.md`) and refreshed
  deliberately, not on every run. The CI job *reports* the score
  (non-blocking at first — we need the baseline before we ratchet).
- **Ratchet (phase 2)**: once baselines exist, the score becomes a
  **monotonic ratchet** (like the loose-assertion ratchet): a PR may not lower a
  module's mutation score. The ratchet compares the run's artifact against the
  tracked `BASELINE.md`. Surviving mutants are triaged: kill (add the missing
  assertion) or annotate (equivalent mutant).

### 2. Per-tool value invariants — assert "is it good?", not only "does it match?"

Extend `tests/unit/mcp/test_output_cost_invariants.py` so **every facade tool**
carries at least one *value* invariant, asserting a documented relationship or
an exact pin (never a hand-waved ceiling — see CLAUDE.md §11 and the exact-
assertion rule):

- **Output cost**: a per-tool serialized-size budget on a fixed fixture
  (exact pin, or `toon ≤ json`, or `default < include_bodies`). This single
  class would have caught #552, #698, and the original TOON 1.96× incident.
- **Advertised-capability**: for each tool, one test that asserts the tool
  delivers what its description claims (lineage → has a `hierarchy` block for a
  class; ast_path outline → reports the true node count, not 0). Catches
  #568, #697.
- **Envelope content, not just presence**: contract tests must assert the
  *value* of `agent_summary`/`verdict` (the verdict is canonical AND correct for
  the case), not merely that the key exists. Catches #577, #697.

This becomes a **required** CI gate: a new facade tool/action cannot merge
without its value invariant (enforced by a registry-driven test, like
`test_readme_counts_match_registry` already does for counts).

### 3. Outside-the-loop authorship — RED-first against an independent spec

The tautology to break: when one agent writes code and its tests together, the
tests encode the code's *current* behavior as "correct." Policy:

- For any **behavior-bearing** change, the failing test is authored from the
  **issue/spec/RFC**, by a different agent (or pod) than the one implementing —
  watched to fail on current code (RED), then implemented to green. This is the
  dev≠review separation we already run for *review*, extended to *test
  authorship*.
- Discovery is explicitly **not** the suite's job. Keep dogfood (real use +
  *measure* bytes/latency) and independent review (Codex) as the discovery
  instruments; the suite is the regression net that locks in what they find.

### 4. Boundary + all-consumer testing for shared components

The #552→#694→#696→#698 chain was one shared serializer (`ASTNodeInfo.to_dict`)
rippling through four consumers, each fix surfacing the next because **no test
enumerated the consumers**. Rules:

- A change to a **shared** function (serializer, walker, envelope helper) must
  add/maintain a test for **every** consumer of it (enumerate via
  `grep`/codegraph; the change-impact tool already lists them).
- Contract tests run through the **real boundary** — `handle_call_tool` / the
  CLI entrypoint / the facade — not the inner `execute()` (the
  test-execute-not-boundary false-negative is already documented).
- **Cross-surface** differential test: CLI and MCP produce equivalent results
  for the same query (parity is a locked rule; make it a test, not a hope).

#### Defect → invariant (the ratchet that converts the suite)

Every escaped defect must land a fix **plus** the value invariant / consumer
test / edge case that would have caught it — not just a regression test for the
one input. Over time this migrates the suite from conformance toward value.

## Three-Surface impact (CLI ↔ MCP parity)

This RFC adds no MCP/CLI surface. It adds CI gates and dev-deps. The
cross-surface *differential test* (mechanism 4) strengthens the existing
CLI↔MCP parity rule by making it executable. TOON-default-on-MCP /
JSON-default-on-CLI asymmetry is respected (the value-invariant fixtures assert
per-surface, citing the locked decision).

## Drawbacks

- **CI time**: mutation testing is slow. Mitigated by scoping to core modules
  and running the full mutation job nightly / on-label, not on every PR (PRs get
  the fast value-invariant gate; mutation score is a ratchet checked less often).
- **Up-front cost**: writing one value invariant per tool is real work
  (~bounded: one per facade action). Phased.
- **Author-separation friction**: RED-first-by-a-different-pod adds an
  orchestration step. We already pay this for review; the marginal cost is one
  more pod per behavior change.
- **Equivalent mutants**: mutation testing has false positives (mutants that
  don't change behavior). Triage cost; annotate-and-move-on.

## Alternatives

- **A: Just raise the line-coverage gate.** Rejected — coverage measures
  execution, not assertion strength; this is exactly the metric that produced
  the false confidence. Mutation score measures the right thing.
- **B: More dogfooding, no suite change.** Rejected — dogfooding is essential
  for *discovery* but is not mechanical/repeatable; it can't be a merge gate.
  This RFC keeps dogfooding AND makes the suite catch regressions of what it
  finds.
- **C: Property-based testing (Hypothesis) everywhere.** Adopt *selectively*
  (already used in a few places), but it still encodes properties the author
  chose — it doesn't, by itself, answer "can my tests catch a bug?" Mutation
  scoring does. Complementary, not a substitute.

## Prior art

- **Mutation testing**: `mutmut`, `cosmic-ray` (Python); PIT (Java); Stryker
  (JS). Mutation score is the established instrument for test-suite quality.
- **Ratchet pattern**: our own loose-assertion ratchet and README-count
  registry test — proven mechanical gates we extend here.
- **CLAUDE.md §11** ("a non-functional claim is a BELIEF until it is an
  executable invariant") — this RFC operationalizes that rule suite-wide.
- **mycelium** RFC discipline (spec-first catches architecture dead-ends before
  code) — same philosophy, applied to test design.

## Test plan (RED-first)

This RFC's deliverables are themselves tests/gates; the "RED" is the current
baseline:

1. **Mutation baseline (RED)**: run `mutmut` on the five core modules; commit
   the report. Expectation: a meaningful fraction of mutants **survive** —
   that surviving count is the quantified "形同虚设". (This number is the
   headline deliverable that answers the investor's question with data.)
2. **Value-invariant coverage (RED)**: a meta-test enumerates facade tools and
   asserts each has a registered value invariant; today most don't → RED.
   Lands GREEN as invariants are added.
3. **Retro-invariants (RED→GREEN)**: add the value invariant for each of the
   nine escaped defects above; confirm each would have gone RED on the
   pre-fix code (mutation-style verification).

## Acceptance criteria

- [ ] `mutmut` (or `cosmic-ray`) added as a dev-dependency; `tests/effectiveness/` harness committed.
- [ ] Mutation job runs on `ubuntu-latest` only (mutmut needs `os.fork`; not in the windows test matrix), as a separate workflow.
- [ ] Per-run mutation report is a CI artifact (uploaded, not committed); a curated `tests/effectiveness/BASELINE.md` records the surviving-mutant count per core module (the number that answers "why 2× tests don't catch bugs").
- [ ] CI job reports mutation score (non-blocking phase 1).
- [ ] `test_output_cost_invariants.py` extended: every facade tool has ≥1 value invariant (size/latency/advertised-capability), exact-pinned or documented-relationship.
- [ ] Meta-test enforces "every facade action has a value invariant" (required gate).
- [ ] Cross-surface CLI↔MCP differential test added for ≥1 representative tool (template for the rest).
- [ ] CLAUDE.md codifies: (a) value-not-just-conformance, (b) test author ≠ code author for behavior changes, (c) shared-component change → all-consumer tests, (d) escaped defect → value invariant.
- [ ] Phase-2 (separate PR): mutation score becomes a monotonic ratchet gate.
- [ ] All linked PRs merged.
