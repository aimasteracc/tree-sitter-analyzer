# RFC-0029: "Does this test constrain this code?" — a question an agent can ask

- **Status**: draft
- **Author(s)**: @lead-agent
- **Created**: 2026-08-20
- **Last updated**: 2026-08-20
- **Tracking issue**: TBD
- **Relationship to other RFCs**:
  - **Parent: [RFC-0017](0017-test-effectiveness-mutation-and-value-invariants.md)**
    (accepted 2026-06-14). RFC-0017 owns mutation *scoring* as a CI campaign,
    per-tool value invariants, outside-the-loop authorship, and boundary
    testing, and states explicitly: *"This RFC adds no MCP/CLI surface."*
    This RFC adds the surface RFC-0017 declined to add, and does not change any
    of its mechanisms.
  - Complements [RFC-0028](0028-measuring-claimed-properties.md) §3.2 (gate
    effectiveness). RFC-0028 asks whether a *gate* still fires; this RFC asks
    whether a *test* constrains anything.
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/constrains/` (new — AST branch inversion + isolated run)
  - `tree_sitter_analyzer/mcp/tools/health_facade.py` (new action)
  - `tree_sitter_analyzer/cli/argument_groups/` (CLI twin)
  - `tests/unit/constrains/` (new — including the escaped-defect corpus)
  - `docs/CODEMAPS/cli.md`, `docs/CODEMAPS/mcp-tools.md`

## Summary

A test can pass while constraining nothing. Today there is no way to ask whether
a specific test actually holds a specific piece of code in place; the only
available answer is a Linux-only batch mutation campaign that reports a score
for a whole module.

This RFC adds one question, callable mid-work, on any platform:

> Given a test node id and a code location, invert one branch at that location,
> run only that test, and report whether it goes red.

If it does not go red, **that test asserts nothing about that code**, whatever
its name says. The answer is a fact, not a judgement, and the RFC deliberately
stops there.

## Motivation

### Four of seven escaped defects in one session were this exact question

On 2026-08-19 a single working session produced seven defects of the form
"green CI, broken behaviour". **Four of them are one unaskable question:**

| defect | the question | answer |
|---|---|---|
| the codemap-sync gate's test built a **synthetic** old-shape registry fixture | does this test constrain the real registry? | no |
| a test **pinned an orphaned tool as expected** | does this test constrain reachability? | it pinned the inverse |
| `.mjs` resolver tests called the **private helper**, while ESM never reached it | does this test constrain the public path? | no |
| `assert p50_ns > 0` was claimed to lock a fix | does this test constrain the fix? | no |

Every one was found by a human or a reviewer **reverting the change by hand and
watching the test still pass.** That is a mechanical operation performed
manually four times in one day.

The fourth is the sharpest, because the author had *just* fixed a real bug —
their harness was reporting a cache hit as `0.0 ms` because the key was built
outside the measured window — and added a test they believed locked it in. A
reviewer moved the code back outside the window and ran it:

```
REVERTED: key derivation moved OUTSIDE recorder.measure
2 passed in 7.64s
```

`assert p50_ns > 0` is satisfied by the sub-microsecond dict lookup that remains
inside the window. The guard could not distinguish the bug from the fix. Nobody
was careless; the question simply could not be asked.

### RFC-0017 already wrote the rule. It was unenforceable.

RFC-0017 §4, accepted in June, states:

> Contract tests run through the **real boundary** — `handle_call_tool` / the
> CLI entrypoint / the facade — not the inner `execute()` (**the
> test-execute-not-boundary false-negative is already documented**).

The rule was correct, written down, and labelled as a known false-negative
class. In August, PR #1312 shipped a `.mjs`/`.mts` resolver fix whose tests
called `_resolve_js_import` directly. The suffix list was correct; the ESM
dispatch never reached it. `health action=imports` still dropped the edge, and
the tests were green.

**A principle that cannot be checked is a principle that gets violated.** This
RFC converts RFC-0017 §4 from prose into a query.

### What exists today, and why it does not answer this

`scripts/run_mutation_baseline.py` runs mutmut over one source file and its
targeted tests, feeding `tests/effectiveness/BASELINE.md` — the RFC-0017
mechanism-1 campaign. It cannot answer the question above because:

1. the module-to-tests mapping is a **hardcoded dict**, so an arbitrary
   `(test, code)` pair cannot be posed;
2. mutmut requires `os.fork`, so it is **Linux-only** — unavailable on the
   platform the primary agent and the maintainer both work on;
3. it is a **campaign, not a question**: it answers "how many mutants survive in
   this module", not "does this test hold this line".

The capability substrate exists and nothing points it at the question. That is
the same shape as this project's zero-caller detection, which is sound for
reachability and has never been asked about registered surfaces
(RFC-0028 §3.1).

## Detailed design

### The operation

```python
@dataclass(frozen=True)
class ConstrainsResult:
    """Whether a test detects a single inverted branch.

    ``constrains`` is ``True`` only when the test passed on the unmodified
    tree AND failed on the mutated tree. Anything else is ``False`` or
    ``UNKNOWN`` — never optimistically ``True``.
    """

    verdict: Literal["constrains", "does_not_constrain", "unknown"]
    reason: str | None          # closed subcodes; None only when constrains
    mutation: str               # human-readable: what was inverted, where
    baseline_outcome: str       # pass | fail | error  (unmodified tree)
    mutated_outcome: str        # pass | fail | error  (mutated tree)
```

Steps, in order:

1. **Baseline.** Run the named test on the unmodified tree in isolation. If it
   does not pass, return `unknown` / `BASELINE_NOT_GREEN` — a red or erroring
   test cannot be shown to constrain anything.
2. **Mutate.** Locate the target and invert exactly one branch (see below).
   Write the mutated source to a **temporary copy**; never to the working tree.
   If no invertible branch exists at the location, return `unknown` /
   `NO_INVERTIBLE_BRANCH`.
3. **Re-run.** Run only that test against the mutated copy.
4. **Report.** `constrains` iff baseline passed and mutated failed.

### Mutation via TSA's own AST, on every platform

No `mutmut`, no `os.fork`. TSA already parses with tree-sitter and, for Python,
has `ast` available, and it already knows where decision points are —
`complexity_heatmap._COMPLEXITY_NODES` enumerates the decision node types per
language, and RFC-0019 made scalar complexity canonical.

The initial mutation set is deliberately small and closed:

| mutation | applies to |
|---|---|
| invert a boolean condition (`if C` → `if not C`) | any `if`/`while` guard |
| flip a comparison operator to its negation | `==`/`!=`, `<`/`>=`, `>`/`<=` |
| replace a returned boolean literal with its negation | `return True`/`False` |
| drop a keyword argument that carries a flag | e.g. `newline=""` |

That last one is not decorative. It is the exact shape of five defects in one
day (`newline=""`, `follow_symlinks`, extension-table membership), and a
missing keyword argument is invisible to a condition-flipping mutator.

**Deliberately excluded** from v1: arithmetic operators, loop bounds, exception
types, statement deletion. A small closed set with a published false-negative
profile is more useful than a large one with an unknown profile — and RFC-0017's
campaign remains the comprehensive instrument.

### Fail-closed, because the failure mode is a false reassurance

`constrains: true` is the answer an agent will act on by *not* looking further.
So every uncertainty resolves away from it:

- baseline not green → `unknown`, never `constrains`
- no invertible branch at the location → `unknown`
- the test cannot be run in isolation (fixture depends on session state) →
  `unknown` / `NOT_ISOLABLE`
- mutation applied but the test *errored* rather than failed → `unknown` /
  `MUTATED_RUN_ERRORED`, because an import error is not detection
- a timeout → `unknown` / `TIMEOUT`

A verdict of `does_not_constrain` is a positive finding and is only emitted when
the mutated run genuinely **passed**.

### Surface

| capability | CLI | MCP |
|---|---|---|
| does this test constrain this code | `--constrains TEST CODE` | `health action=constrains` |

`health` is the correct facade: this is a test-effectiveness question and
RFC-0017 placed test effectiveness in that domain. No new facade, so the
RFC-0022 menu gate is untouched. CLI defaults to JSON, MCP to TOON — the locked
asymmetry, unchanged.

## Three-Surface impact (CLI ↔ MCP parity)

1:1 as above, with a parity test. Adding a CLI flag and an MCP action requires a
CODEMAP update, and the codemap-sync gate (rebuilt in #1314) now genuinely
blocks and asserts exact set equality — so this cannot land undocumented.

## Drawbacks

1. **It runs tests, so it is slow relative to a query.** Two isolated test runs
   per call. Acceptable: it is asked about one pair at a time, deliberately, not
   swept over a suite.
2. **A small mutation set has false negatives** — `constrains: true` means "this
   test detects *this* inverted branch", not "this test is good". The verdict
   wording must not overclaim, and the published false-negative profile is part
   of the deliverable.
3. **It writes a temporary mutated copy.** Never the working tree, and the
   temp-hygiene rules already in force apply.
4. **It could become a coverage-chasing instrument** — "make `constrains` return
   true" is a number to game, and T-3 prohibits exactly that. Mitigation: the
   result is a fact for a human or agent to act on, and it is deliberately **not**
   wired into any gate or score in this RFC.

## Alternatives

- **A: extend `run_mutation_baseline.py` to accept arbitrary pairs.** Rejected as
  the primary path: it stays Linux-only, so the agent and maintainer who need it
  most cannot use it interactively. Worth doing *later* as the comprehensive
  arm — see RFC-0017 mechanism 1, which already owns that.
- **B: rely on coverage.** Rejected. All four motivating defects lived in
  *covered* code; the private-helper tests executed the helper every run.
  Coverage measures execution, not constraint.
- **C: make it a CI gate now.** Rejected. A gate on a v1 mutation set with an
  unmeasured false-negative profile would manufacture confidence — the defect
  class this project has spent the week removing. Gate it after the profile is
  published.
- **D: an LLM judges whether the test is meaningful.** Rejected. Non-deterministic,
  unpinnable in CI, and this package has no LLM client by design.

## Prior art

- **Mutation testing (DeMillo/Lipton/Sayward, 1978).** The idea is old; the
  contribution here is *interactive granularity* — one pair, one branch, any
  platform — rather than a score.
- **`git bisect`.** The closest ergonomic analogue: a mechanical question a
  developer asks mid-work and gets a fact back. Nobody would accept "run the
  bisect campaign nightly and read the report" as a substitute.
- **Property-based shrinking (Hypothesis).** Shrinking answers "what is the
  smallest input that breaks this"; this answers "what is the smallest change
  this test fails to notice". Complementary, opposite direction.
- **Google Tricorder.** Its lesson — an analyzer is abandoned above a false-positive
  rate developers will not tolerate — is why `unknown` is a first-class verdict
  here rather than a defaulted `false`.

## Test plan (RED-first)

The corpus **is** the acceptance criterion. If it does not reproduce the four
escaped defects, the feature is a lie.

1. **`assert p50_ns > 0` vs the key-inside-`measure` fix** (PR #1320) →
   must return `does_not_constrain`. The one case where a reviewer already
   established the ground truth by hand.
2. **The synthetic old-shape registry fixture vs the real registry**
   (pre-#1314 `test_codemap_sync_hook.sh`) → `does_not_constrain`.
3. **The orphan-pinning assertion vs reachability**
   (`tests/unit/cli/test_install_skills.py:571`) → `does_not_constrain`.
4. **The private-helper `.mjs` test vs the public `ImportGraph.build` path**
   (pre-#1312) → `does_not_constrain`.
5. **Positive controls**: at least three known-good exact-assertion tests →
   `constrains`. Without these the feature could pass items 1–4 by always
   answering `does_not_constrain`.
6. **Every fail-closed subcode** forced independently: `BASELINE_NOT_GREEN`,
   `NO_INVERTIBLE_BRANCH`, `NOT_ISOLABLE`, `MUTATED_RUN_ERRORED`, `TIMEOUT`.
7. **The working tree is never written**: assert byte-identical file digests
   across a call, including on a failure path.
8. **All-OS**: the mutation engine runs on Windows, macOS and Linux. This is the
   whole point of not using mutmut; a Linux-only implementation fails the RFC.
9. **False-negative profile**: for each excluded mutation kind, a test
   documenting that a defect of that kind is *not* detected, so the profile is
   executable rather than prose.

## Acceptance criteria

- [ ] `health action=constrains` + `--constrains`, 1:1, parity test green
- [ ] mutation engine runs on Windows, macOS and Linux with no `mutmut` dependency
- [ ] the four-defect corpus returns `does_not_constrain` for all four
- [ ] at least three positive controls return `constrains`
- [ ] every fail-closed subcode forced by its own test
- [ ] `unknown` is emitted, never a defaulted `constrains`
- [ ] working tree provably unmodified across every call path
- [ ] false-negative profile published and executable
- [ ] CODEMAPs updated; codemap-sync gate green
- [ ] NOT wired into any gate or score (deliberate, see Drawbacks 4)

## What this RFC does NOT do (deferred)

- **No mutation campaign.** RFC-0017 mechanism 1 owns that, and this RFC does not
  touch it.
- **No judgement.** It answers whether a branch is detected. Whether the test
  *should* be improved, and how, is the caller's call.
- **No gate.** Deliberately, until the false-negative profile exists.
- **No arithmetic / loop-bound / exception-type / statement-deletion mutations**
  in v1.
- **Not a general audit of my own assertions.** A separate defect this week — a
  loose `>= 1` replaced by a pinned `== 2` where the measured value was `1` —
  is covered by RFC-0028 §3.2's doc-example execution, not by this.

### Two further wants, recorded with their evidence and deliberately deferred

Held until this RFC ships, so their priority can be measured against what it
actually removes rather than guessed:

- **Finding clustering across a session.** Five line-ending defects were found in
  one day — `ImportGraph` normpath-vs-POSIX keys, a corpus digest on an
  unpinned `*.jsonl`, detect-secrets rewriting 67 paths to backslashes,
  repeated CRLF commit churn, and a CI retry path that could never fire — each
  reported separately, hours apart, by a different reviewer. The class was named
  on the fifth. Clustering would have compressed five point fixes into one
  invariant. Substrate: `decision_journal.py` exists, is reachable from a CLI
  flag, and has never been used (`.ast-cache/decision_journal.db` does not exist
  in this repository).
- **Belief provenance.** Three false beliefs were held with confidence and
  propagated in one day: that 23 `mypy` errors were technical debt (they are a
  Windows host artifact — `mypy --platform linux` is clean, and three agents
  were instructed to preserve a debt that did not exist); that an 1880-line
  module was pre-existing (it was introduced by the PR under review); and that a
  benchmark block was spec-level (false for two of seven gates). RFC-0027 L9
  records *predictions*; nothing records *beliefs* or where they came from.

## Open questions

1. Should the mutation be applied to a temp copy of the whole tree, or to a
   single file with an import shim? **Proposal: temp copy of the file plus a
   path override, because a whole-tree copy is too slow to ask casually and
   casual asking is the point.**
2. How is the test run isolated? **Proposal: a subprocess with
   `-p no:randomly` and the target node id, so xdist and ordering plugins cannot
   perturb the result.**
3. Should `does_not_constrain` include a *suggested* assertion? **Proposal: no.
   That is judgement, and it would invite the coverage-chasing failure mode in
   Drawbacks 4.**
4. Multi-branch locations — invert one branch or report per branch?
   **Proposal: report per branch, capped, since "the test catches branch A but
   not branch B" is more actionable than an aggregate.**
