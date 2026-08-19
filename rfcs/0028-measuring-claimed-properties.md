# RFC-0028: Measuring the properties we already claim

- **Status**: draft
- **Author(s)**: @lead-agent
- **Created**: 2026-08-19
- **Last updated**: 2026-08-19
- **Tracking issue**: TBD
- **Relationship to other RFCs**: complements [RFC-0025](0025-instant-causal-proprioception.md)
  (sensing, L1–L5) and [RFC-0027](0027-agent-secretary-and-calibration.md)
  (secretary layer, L6–L10). This RFC adds **no product capability**. It converts
  four load-bearing claims into executable invariants and closes one measurement
  gap in the north star. It is the reflexive application of CLAUDE.md §11 to the
  project's own foundational beliefs.
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tests/benchmarks/claims/test_unknown_vs_absent_invariant.py` (new — §1)
  - `tree_sitter_analyzer/calibration/` (§2 — consultation records; RFC-0027 L9 substrate)
  - `tests/contracts/test_reachability_invariants.py` (new — §3.1)
  - `tests/contracts/test_gate_effectiveness.py` (new — §3.2)
  - `docs/CODEMAPS/*.md` (§3.2 counts)

## Summary

On 2026-08-19 a single working session found six defects that shared one shape:
**the absence of a signal was read as a positive signal.**

| # | defect | why it looked fine |
|---|---|---|
| 1 | the codemap-sync gate's two detectors matched nothing | hook exited 0 → read as "no violation" |
| 2 | a built, tested MCP tool was reachable from no facade | a test **pinned the orphan state as expected** |
| 3 | a suffix fix was unreachable for ESM; the resolver was never called | tests called the private helper directly → read as "it works" |
| 4 | `ImportGraph` dropped every cross-directory edge on Windows | Linux CI structurally cannot see a separator mismatch |
| 5 | a doc example named a file that did not exist and whose name a hook bans | the weak-assertion ratchet parses `.py` via `ast` and cannot see markdown |
| 6 | an agent silently falls back to `grep` when a tool is too slow | the agent does not report non-use; VCSR cannot distinguish it |

Five of the six were invisible to a green CI. The sixth is invisible to the north
star itself. None of them is a bug in a feature; each is a **missing invariant**.

This RFC specifies four of those invariants and one new measurement. It
deliberately ships no new user-facing capability.

## Motivation

### The project's central claim is currently prose

TSA's moat, as stated in `ROADMAP-no1-agent-trust.md` and enforced by hand in
review after review, is conservative resolution: *a visible `unknown` is safer
than a confident unsupported edge.*

The primary user articulated why that matters better than any spec text in this
repository:

> Every other tool I have silently conflates "there is none" with "I could not
> determine it." `grep` returns fewer lines; it does not tell me whether the
> callers are absent or merely invisible to it. I cannot see the difference. The
> mistake I make most often is trusting a confidently incomplete answer.

That property is the reason to prefer TSA over `grep` for a safety question. And
under §11, **it is a belief**: nothing in CI measures it. RFC-0025's fail-closed
work and RFC-0027's §L9.4 soundness fence protect the *implementation*; neither
measures the *property*.

The concrete risk is not hypothetical. A future change that reduces `unknown`
counts in the name of "improved precision" would leave every existing test green,
because every existing test asserts conformance to a shape, not the preservation
of epistemic honesty.

### VCSR cannot see adoption failure

The north star is Verified Change Success Rate. It measures whether a change
succeeded. It does **not** measure whether TSA was consulted.

An agent that finds `edit action=safe` too slow does not report "I skipped TSA."
It uses `grep`, proceeds, and the run may well succeed. Measured on this
repository (RFC-0025 L5 baseline, 2026-08-19, E0): `edit action=safe` is
~3.7 s p50 even warm, while every other route drops to milliseconds. That is
squarely inside the range where an agent routes around a tool.

So the world where TSA is fast and useful and the world where it is bypassed are
**indistinguishable in the north star**. Adoption failure is silent. This is
defect #6, and it is the same shape as the other five: a missing signal read as
a positive one.

### Three classes of defect the suite is structurally blind to

The six defects cluster into three blind classes, none of which RFC-0025 or
RFC-0027 addresses:

1. **Reachability** — is this code actually called? (#2, #3)
2. **Gate effectiveness** — does this gate actually gate? (#1, #5)
3. **Platform specificity** — does this hold where CI cannot look? (#4)

The good news, and the reason this RFC is small: **two of the three are already
within reach of existing primitives pointed at a new question.** CLAUDE.md rule 5
already states that a static call graph is sound for zero-coverage detection —
"methods with 0 callers are definitely untested" — because its false positives
only go one way. An MCP tool registered in no facade *is* a zero-caller symbol.
The capability exists; nothing asks it about the right subjects.

## Detailed design

### §1 — The `unknown`-vs-absent differential invariant

**Claim under test:** TSA distinguishes "no callers exist" from "callers could not
be determined." A text search cannot.

**Design:** a fixture corpus in which call edges are genuinely undecidable by
text search — dynamic dispatch, string-keyed invocation, reflection, computed
attribute access, decorator-mediated registration — each with a hand-checked
ground truth recording whether the edge exists.

For each corpus symbol, run both:

- TSA's resolved caller query, and
- a text search standing in for the naive tool.

Assert the **one-directional** property:

```
For every symbol where ground truth says an edge EXISTS but text search
returns no hit, TSA MUST NOT report a confident empty result.
It must report the edge, or report `unknown`. Never a bare zero.
```

```python
def test_undecidable_edge_is_never_reported_as_confidently_absent() -> None:
    """The moat, as an executable invariant.

    A confident empty answer where an edge genuinely exists is the single
    failure mode that makes an agent conclude "safe to change" and be
    wrong. This test does not require TSA to *resolve* the edge — being
    unable to resolve it is acceptable and expected. It requires TSA to
    say so.
    """
```

Deliberately **not** asserted: that TSA resolves more edges than text search.
That is a precision claim and it belongs to the benchmark, not here. This
invariant is about honesty only, which is why it can be one-directional and
therefore stable.

**Ratchet:** the count of corpus cases where TSA answers `unknown` rather than a
bare zero may **increase or hold, never decrease**. A change that converts an
`unknown` into a confident empty fails this gate even if every other test is
green. Same mechanism as the existing weak-assertion ratchet.

### §2 — Consultation records: making non-use visible

**Claim under test:** TSA is used.

Extend RFC-0027's L9 ledger with a third record kind alongside `Prediction` and
`Outcome`:

```python
@dataclass(frozen=True)
class Consultation:
    """One question an agent asked, and whether the answer was usable.

    ``declined_reason`` is how a bypass becomes visible: a route that
    returns a cost estimate the caller rejects, or that exceeds a
    declared budget, records WHY it was not used. A tool that is
    routinely too slow then shows up as a population of declines rather
    than as silence.
    """

    consultation_id: str
    tool: str
    action: str
    generation: str
    served_from: Literal["cache", "computed"]
    elapsed_ns: int
    declined_reason: str | None   # BUDGET_EXCEEDED / COST_REJECTED / None
```

Surfaced by `--self-health` (RFC-0025 L5) as consultation counts and decline
rates per route, alongside the existing latency percentiles.

**What this can and cannot do — stated plainly.** TSA cannot observe an agent
that never calls it; nothing inside a process can record a call that did not
happen. What it *can* do is make the **precondition** measurable: a route whose
p95 sits in the seconds while its sibling routes sit in milliseconds is a
bypass candidate, and RFC-0027's L6.2 `QueryCost` gives a caller a place to
decline explicitly rather than silently. This turns an unobservable into a
weak but real signal. Claiming more would be the same overreach this RFC exists
to correct.

**Explicitly out of scope:** any telemetry that leaves the machine. Local
records only; the L9.5 storage discipline (identities and outcomes, never source
text, secret-canary tested) applies unchanged.

### §3 — Invariants for the three blind classes

#### §3.1 Reachability

Point the existing zero-caller machinery at three questions it is not currently
asked:

1. **Registered-surface reachability.** Every MCP tool class and every CLI
   command module must be reachable from the tool registry or the argument
   parser. A tool that is built and tested but registered nowhere fails.
   *This catches defect #2 — and note that a test currently pins that orphan
   state as expected; that assertion must be corrected, not preserved.*
2. **`next_step` routability.** Every `next_step` string a tool emits must name a
   route that resolves. `build_project_index_tool.py` emits
   `next_step="get_project_summary"`, which routes nowhere.
3. **Dispatch reachability.** For each language-family branch in a resolver
   dispatch, at least one test must reach it **through the public entry point**,
   not by calling the private helper. *This catches defect #3, where the ESM
   branch was unreachable in production while its helper's unit tests passed.*

Rule 5's caveat applies and is honoured: `conftest.py`'s autouse singleton reset
inflates caller counts, so these invariants use only the **zero-caller** signal,
whose false positives go one way. They never assert a positive caller count.

#### §3.2 Gate effectiveness

Every blocking gate must carry a **self-check** proving its detector still
matches live production, asserting **exact** set equality — not a `count > 0`
lower bound.

This is now precedent rather than proposal: #1314 rebuilt
`scripts/codemap-sync-check.sh` this way after the old gate's `count > 0` guard
was shown to pass against a tree where both detectors were fully dead. Note the
irony worth preserving in the record: **the anti-staleness guard was violating
the exact-assertion rule it existed to enforce.**

Required of every gate:

1. a `--self-check` mode asserting exact equality against the live surface;
2. a **coverage invariant** — the count of surface items falling outside the
   gate's watch filter must be exactly `0`;
3. its test fixture derived from **real** production files, never a synthetic
   imitation of their shape;
4. the test **invoked by a CI job** whose failure fails the job. The codemap
   gate's own test was referenced by no workflow at all before #1314.

**Doc-example verification** belongs here too (defect #5). The weak-assertion
ratchet parses staged `.py` via `ast` and cannot reach fenced code blocks in
markdown. Extract executable examples from agent-facing docs and run them.
The author of this RFC replaced a loose `>= 1` with a pinned `== 2` in
`docs/TESTING.md` where the correct value was `1`, because nothing runs those
examples — an exactly-wrong exact assertion, which is worse than the bound it
replaced.

#### §3.3 Platform specificity

For any invariant whose correctness depends on filesystem or OS semantics —
path separators, case sensitivity, symlinks, line endings, locale codecs — the
test must either run on every axis or **fail closed on the axes where it cannot
run**, never skip silently.

Defect #4 is the worked example: `ImportGraph` dropped every import edge crossing
a directory on Windows (POSIX cache keys versus `os.path.normpath` backslashes),
language-independently, making the import graph effectively empty for any real
project — and Linux CI could not observe it because POSIX paths have no
separator mismatch. It surfaced only when a test was finally written against the
public API instead of a private helper.

**Minimum invariant:** any code comparing a path against an AST-cache key must be
covered by a test asserting the comparison holds under **both** separator
conventions, independent of the host. This is cheap and it is the specific bug
class already shown to be live.

## Three-Surface impact (CLI ↔ MCP parity)

| capability | CLI | MCP |
|---|---|---|
| consultation + decline rates | `--self-health` (extends RFC-0025 L5) | `health action=self` |

No new flag and no new action. §1 and §3 are tests and gates with no user-facing
surface. §2 extends an existing report. The locked TOON-on-MCP / JSON-on-CLI
asymmetry is untouched.

## Drawbacks

1. **Pure cost, no feature.** Nothing here makes the product do anything new. It
   makes existing claims falsifiable. The argument for paying it is that five of
   the six motivating defects survived a green CI, and one of them shipped a
   Windows-wide correctness bug.
2. **The §1 corpus is hand-curated and will rot.** Ground truth requires human
   judgement about whether a dynamically-dispatched edge exists. Mitigated by
   keeping the corpus small and the invariant one-directional.
3. **§3.1 will fail on merge.** At least one existing test pins an orphan as
   expected. That is the point, and the fix is to correct the assertion.
4. **§2 measures a proxy, not the thing.** Non-invocation is unobservable from
   inside. Stated in the design rather than papered over.
5. **§3.2 imposes work on every future gate.** Acceptable: a gate that cannot
   prove it still fires is worse than no gate, because it manufactures
   confidence.

## Alternatives

- **A: Trust review to catch these.** Rejected on evidence. Five review rounds by
  an automated reviewer on one PR produced a stream of individually-valid
  findings about an unbounded enumeration, and never named the architecture as
  the defect. Review finds instances; invariants close classes.
- **B: Raise coverage instead.** Rejected. All six defects lived in *covered*
  code. Defect #3's helper had passing unit tests while being unreachable in
  production. Coverage measures execution, not reachability from a real entry
  point — and T-3 prohibits coverage as a goal.
- **C: Assert TSA resolves more edges than text search** (§1). Rejected: that is
  a precision claim, it belongs to the RFC-0021 benchmark, and it is fragile.
  The honesty property is the one worth a permanent gate.
- **D: Emit telemetry to measure adoption** (§2). Rejected outright — a
  local-first tool does not phone home. The decline-record proxy is weaker and
  is the correct trade.

## Prior art

- **Metamorphic testing.** §1 is a metamorphic relation: it does not require a
  known correct output, only that a property hold between two systems on the same
  input. That is what makes an honesty invariant expressible at all, since the
  ground truth for "is this dynamic edge real" is expensive while "must not claim
  confident absence" is cheap.
- **Mutation testing.** §3.2's self-check is a targeted, cheap mutation test: it
  asks whether the detector would still fire, rather than assuming it. The repo
  already has `mutation-baseline.yml`; this applies the same idea to gates.
- **Google Tricorder.** Analyzer abandonment above ~10% false-positive rate is
  the documented failure mode; §2's decline records are the local analogue of
  measuring "did anyone act on this finding."
- **`git`'s abbreviated object names.** Adopted in RFC-0027 §L6.3 for the same
  reason it appears here: an identifier that can silently resolve to the wrong
  thing is worse than one that fails loudly.

## Test plan (RED-first)

1. §1 corpus: at least one case per undecidable mechanism (dynamic dispatch,
   string-keyed call, reflection, computed attribute, decorator registration),
   each with hand-checked ground truth. RED against a deliberately-weakened
   resolver that returns a bare zero.
2. §1 ratchet: a synthetic regression converting one `unknown` into a confident
   empty must fail the gate.
3. §3.1: RED today — the registered-surface invariant must fail on the known
   orphan before the orphan is wired.
4. §3.1: `next_step` routability must fail today on the known unroutable string.
5. §3.2: for each existing blocking gate, a self-check asserting exact set
   equality, plus its coverage-invariant-equals-zero.
6. §3.2: doc-example extraction must fail on a deliberately wrong pinned count.
7. §3.3: a path-comparison test asserting both separator conventions, failing
   against the pre-#1308 resolver.
8. §2: a declined consultation is recorded with its exact reason code; an
   unavailable one is `null`, never `0`.

## Acceptance criteria

- [ ] §1 corpus + one-directional invariant green; ratchet wired into CI
- [ ] §1 documented as the executable form of the conservative-resolution claim,
      cross-referenced from `ROADMAP-no1-agent-trust.md`
- [ ] §2 `Consultation` record persisted in the L9 ledger; decline rates in
      `--self-health`; CLI↔MCP parity test green
- [ ] §2 scope limitation stated in the emitted payload, not only in this RFC
- [ ] §3.1 registered-surface reachability green; the test that pins the orphan
      **corrected**, not preserved
- [ ] §3.1 `next_step` routability green
- [ ] §3.1 dispatch reachability asserted through public entry points
- [ ] §3.2 every blocking gate has an exact-equality self-check plus a
      coverage-invariant of exactly 0
- [ ] §3.2 every gate's test is invoked by a CI job that can fail
- [ ] §3.2 doc-example extraction runs agent-facing doc examples in CI
- [ ] §3.3 path-comparison invariant covers both separator conventions
- [ ] Docs/CODEMAPS updated

## What this RFC does NOT do (deferred)

- **No new product capability.** By design.
- **No shell-script analysis.** Defect #1 was a dead regex in a `bash` gate. TSA
  does not analyse shell, and §3.2 addresses it by requiring every gate to prove
  itself, not by teaching TSA `bash`. **A dead detector inside an unanalysed
  language remains out of reach** and the mitigation is procedural.
- **No runtime platform emulation.** §3.3 requires path invariants to hold under
  both conventions; it does **not** claim TSA can predict OS-specific runtime
  behaviour generally. That class stays out of reach.
- **No adoption telemetry.** §2 is a local proxy and says so.
- **No change to the RFC-0025 or RFC-0027 designs.** This RFC adds invariants
  over them.
- **No public claim.** Every number cited here is an E0 dogfood measurement from
  2026-08-19; public wording stays bound by the RFC-0021 evidence ladder.

## Open questions

1. How large should the §1 corpus be? Small enough to keep ground truth honest,
   large enough to cover the mechanisms. **Proposal: five mechanisms, three cases
   each, and grow only when a real escape is found.**
2. Should the §1 ratchet be per-mechanism or aggregate? Aggregate lets a
   regression in one mechanism hide behind an improvement in another.
   **Proposal: per-mechanism.**
3. Does §3.1 belong in `tests/contracts/` or in a new `tests/invariants/`?
   **Proposal: `tests/contracts/`, since these are contracts about the surface;
   avoid a new top-level directory.**
4. Should §2's decline records feed the RFC-0026 VCSR denominator? **Proposal:
   no. VCSR stays the single north star; decline rate is a supporting signal,
   per the roadmap's "no weighted score may hide a regression" rule.**
