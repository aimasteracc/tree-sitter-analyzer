# RFC-0028: Measuring the properties we already claim

- **Status**: draft
- **Author(s)**: @lead-agent
- **Created**: 2026-08-19
- **Last updated**: 2026-08-20
- **Tracking issue**: TBD
- **Relationship to other RFCs**: complements [RFC-0025](0025-instant-causal-proprioception.md)
  (sensing, L1–L5), [RFC-0027](0027-agent-secretary-and-calibration.md)
  (secretary layer, L6–L10), and [RFC-0029](0029-does-this-test-constrain-this-code.md)
  (the on-demand "does this test constrain this code" query). It converts four
  load-bearing claims into executable invariants and closes one measurement gap
  in the north star. It is the reflexive application of CLAUDE.md §11 to the
  project's own foundational beliefs. **It adds no product capability** — the one
  surface change it does make (§1's `completeness` field) exists solely to expose
  a property the AST cache already records and the response layer currently drops.
- **Division of labour with RFC-0029** (drawn by *mechanism*, not by
  gate-versus-test): **this RFC owns static, always-on, CI-enforced invariants**;
  **RFC-0029 owns the on-demand, per-pair, non-gating query.** Under that split
  the ESM-dispatch defect (#3) and the synthetic-fixture defect (#1) belong here;
  RFC-0029 keeps them only as engine-validation fixtures, never as justification.
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/mcp/tools/callers_tool.py` (§1 — `completeness` field)
  - `tests/unit/mcp/tools/test_tool_response_contract.py` (§1 — response-surface contract)
  - `tests/benchmarks/claims/test_unknown_vs_absent_invariant.py` (new — §1)
  - `tests/benchmarks/claims/test_unknown_rate_ratchet.py` (§1 reconciliation, §3.2 instance)
  - `tests/contracts/test_reachability_invariants.py` (new — §3.1)
  - `tests/contracts/test_gate_effectiveness.py` (new — §3.2)
  - `.pre-commit-config.yaml` (§3.2 — the six first-party local hooks)
  - `.github/workflows/dogfood-pr-check.yml` (§1/§3.2 — the job that must collect)
  - `docs/CODEMAPS/*.md` (§3.2 counts)
  - *Prospective, does not exist today:* `tree_sitter_analyzer/calibration/`
    (§2 — created only if RFC-0027 is accepted; see §2)

## Summary

On 2026-08-19 a single working session found seven defects that shared one shape:
**the absence of a signal was read as a positive signal.**

| # | defect | why it looked fine |
|---|---|---|
| 1 | the codemap-sync gate's two detectors matched nothing | hook exited 0 → read as "no violation" |
| 2 | a built, tested MCP tool was reachable from no facade | a test **pinned the orphan state as expected** |
| 3 | a suffix fix was unreachable for ESM; the resolver was never called | tests called the private helper directly → read as "it works" |
| 4 | `ImportGraph` dropped every cross-directory edge on Windows | Linux CI structurally cannot see a separator mismatch |
| 5 | a doc example named a file that did not exist and whose name a hook bans | the weak-assertion ratchet parses `.py` via `ast` and cannot see markdown |
| 6 | an agent silently falls back to `grep` when a tool is too slow | the agent does not report non-use; VCSR cannot distinguish it |
| 7 | `assert p50_ns > 0` was claimed to lock a latency fix it cannot distinguish from the bug | the test is green against the bug and against the fix — owned by [RFC-0029](0029-does-this-test-constrain-this-code.md) |

**Count convention, reconciled with RFC-0029: seven.** An earlier draft of this
RFC said *six*, omitting #7 on the grounds that it is RFC-0029's subject rather
than this RFC's. It is counted here anyway so the two documents cannot drift on
the same session's evidence. The *invariant* for #7 still lives in RFC-0029; only
the count is shared.

Five of the seven were invisible to a green CI (#1–#5). #6 is invisible to the
north star itself. #7 was invisible to the test written specifically to catch it.
None of them is a bug in a feature; each is a **missing invariant**.

This RFC specifies four of those invariants and one new measurement, and hands #7
to RFC-0029. It adds one response field (§1's `completeness`) and no new
user-facing capability beyond it.

## Motivation

### The project's central claim is not merely unmeasured — on the flagship route it is not implemented

TSA's moat, as stated in `ROADMAP-no1-agent-trust.md` and enforced by hand in
review after review, is conservative resolution: *a visible `unknown` is safer
than a confident unsupported edge.*

The primary user articulated why that matters better than any spec text in this
repository:

> Every other tool I have silently conflates "there is none" with "I could not
> determine it." `grep` returns fewer lines; it does not tell me whether the
> callers are absent or merely invisible to it. I cannot see the difference. The
> mistake I make most often is trusting a confidently incomplete answer.

That property is the reason to prefer TSA over `grep` for a safety question. The
first draft of this RFC said it was "a belief: nothing in CI measures it." Both
halves of that sentence are wrong, and correcting them is the reason this section
is the largest in the RFC.

**Wrong half one: on the flagship route, the property is not implemented.**
Measured 2026-08-19 (E0, this host):

- `tree_sitter_analyzer/mcp/tools/_verdict.py:23` — `_LEGAL_VERDICTS` is a
  **closed** `frozenset` of exactly eight values (`SAFE`, `CAUTION`, `REVIEW`,
  `UNSAFE`, `INFO`, `WARN`, `ERROR`, `NOT_FOUND`). There is no `UNKNOWN`, and
  `_canonicalize_verdict` silently coerces anything outside the set to `INFO`.
- `tree_sitter_analyzer/mcp/tools/callers_tool.py:187` — the verdict is binary:
  `"INFO" if callers or total_callers else "NOT_FOUND"`. There is no third
  outcome to express "I could not determine it."
- Run against a purpose-built corpus of dict-dispatch and `getattr` call sites
  with a **real built index**, the callers route answers
  `verdict=NOT_FOUND, caller_count=0, callers=[]` — while the index itself
  records `callee_resolution='unknown'` on exactly those edges.

So **the honest `unknown` exists in the store and is dropped on the callers
route.** The moat's substrate is real; its answer surface erases it. That is a
worse finding than "unmeasured", and it is the finding this RFC is built on.

The same route emits `next_step` "Symbol not in the index", which is **false**
whenever the symbol *is* indexed and only its callers are unresolved — the
response actively misdirects the agent toward re-indexing instead of toward the
unresolved edges.

**Wrong half two: something in CI does measure `unknown` — with the opposite
sign.** `tests/benchmarks/claims/test_unknown_rate_ratchet.py` exists and
pressures the unknown rate **down** ("must not exceed 6.0%", "the threshold must
NEVER increase"). §1's ratchet pressures a count of `unknown`s **up**. That
apparent contradiction is reconciled in §1 below; the honest statement is not
"nothing measures it" but "one thing measures a different denominator, in the
opposite direction, in a test no CI job collects" (§3.2).

The concrete risk is not hypothetical. A future change that reduces `unknown`
counts in the name of "improved precision" would leave every existing test green,
because every existing test asserts conformance to a shape, not the preservation
of epistemic honesty.

### VCSR cannot see adoption failure

The north star is Verified Change Success Rate. It measures whether a change
succeeded. It does **not** measure whether TSA was consulted.

An agent that finds `edit action=safe` too slow does not report "I skipped TSA."
It uses `grep`, proceeds, and the run may well succeed. Measured on this
repository: `edit action=safe` warm p50 is **3322.89 ms** (p95 3393.28 ms, 5
samples), from the committed artifact
`docs/baselines/rfc0025-l5-latency-windows-e0.json` at commit `9137b39b`
(RFC-0025 L5, PR #1315; Windows, E0, single un-isolated host). Every other route
in that artifact drops to milliseconds (`nav` 2.7 ms, `search` 17.2 ms). 3.3 s is
squarely inside the range where an agent routes around a tool.

> An earlier draft of this section cited **~3.7 s p50**. That number came from a
> pre-re-pin revision that was superseded *inside PR #1315 itself*; the artifact
> as merged says 3322.89 ms. Citing a superseded intermediate as if it were the
> committed baseline is a CLAUDE.md §11 rule-3 violation ("a locked claim carries
> its evidence: measurement command + last-measured date") committed by the RFC
> whose whole purpose is to enforce §11. Recorded rather than quietly fixed.
>
> **And the precondition is scheduled for deletion.** PR #1320 takes this same
> route to **~47 ms**. §2 therefore must not be written as if 3.3 s were a
> standing property of the tool: §2's motivating precondition has a known expiry,
> and §2 survives it only as the *mechanism* for recording an explicit decline,
> not as a claim that this route is slow. If #1320 lands before §2 is
> implemented, re-derive the bypass-candidate argument from the then-current
> artifact or drop it.

So the world where TSA is fast and useful and the world where it is bypassed are
**indistinguishable in the north star**. Adoption failure is silent. This is
defect #6, and it is the same shape as the other six: a missing signal read as
a positive one.

### Three classes of defect the suite is structurally blind to

Six of the seven defects cluster into three blind classes, none of which
RFC-0025 or RFC-0027 addresses (#7 is RFC-0029's class — does a test constrain
the code it names — and is not addressed here):

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

**This section requires a surface change. It is not test-only.** The measured
finding above means there is no field on the callers response capable of carrying
the distinction, so an invariant asserting it would be RED-forever against the
current shape. The first draft claimed §1 fit inside a "no new surface" scope;
that was wrong and is corrected here.

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

#### §1.1 The surface: a new `completeness` field, not a ninth verdict

Add to the callers response (and to any route that answers a
"who-touches-this" question from resolved edges):

```
completeness: "complete" | "incomplete" | "unknown"
```

- `complete` — every edge into this symbol resolved; a `caller_count` of 0 is a
  real zero.
- `incomplete` — callers were found *and* at least one edge into this symbol is
  unresolved; the list is a lower bound.
- `unknown` — no callers were resolved *and* at least one edge into this symbol
  is unresolved. This is the case that today returns `NOT_FOUND` + `count=0`.

**Why a field and not a ninth verdict.** `_LEGAL_VERDICTS` is a closed
cross-surface contract: MCP tools, the CLI, and third-party clients (Claude Code,
Cursor, Cline) branch on the string, and the vocabulary is pinned twice — in
`_verdict.py` and in `_N_VERDICT_VOCABULARY` in
`tests/unit/mcp/tools/test_tool_response_contract.py`. Widening a closed
vocabulary forces every consumer's branch table to change and is the **more**
invasive edit; adding an orthogonal field leaves every existing branch correct
and lets a consumer that ignores it behave exactly as today. Verdict stays
`NOT_FOUND`/`INFO`; `completeness` carries the epistemic status.

`next_step` must be corrected in the same change: "Symbol not in the index" may
only be emitted when the symbol is genuinely absent from the index. When
`completeness != "complete"` it must name the unresolved edges instead.

#### §1.2 Ratchet, and how it reconciles with the existing unknown-rate cap

**Ratchet:** the count of corpus cases where TSA answers `completeness="unknown"`
rather than a bare confident zero may **increase or hold, never decrease**. A
change that converts an `unknown` into a confident empty fails this gate even if
every other test is green. Same mechanism as the existing weak-assertion ratchet.

That is the **opposite sign** from `tests/benchmarks/claims/test_unknown_rate_ratchet.py`,
which lives in the very directory §1 targets and caps unknowns at 6.0% with "the
threshold must NEVER increase". The two are not in conflict, because the
denominators are different things:

| | existing unknown-rate cap | §1's ratchet |
|---|---|---|
| denominator | every `kind='calls'` row in `edges`, repo-wide | the hand-checked **undecidable** corpus cases only |
| unit | a percentage | a count |
| measures | **resolution quality** — how much the resolver *can* resolve | **honesty where resolution is impossible** |
| direction | down (fewer unknowns is better) | up (fewer silent zeros is better) |

A genuine resolver improvement moves **both** favourably: repo-wide unknown rate
falls (cap satisfied) and corpus cases move from `unknown` to a *resolved edge*,
which §1 accepts because §1 forbids only the transition
`unknown → confident-empty`, never `unknown → resolved`. **Which wins if they
ever do collide: §1.** A change that lowers the repo-wide unknown rate by
converting undecidable cases into confident zeros is precisely the failure §1
exists to block, and the cap may be re-pinned upward with a reviewed decision
where §1 may not be relaxed at all.

**Scope guard against §3.1 (see §3.1).** §1 applies **only** to symbols whose
containing file has at least one unresolved edge. A symbol in a fully-resolved
file must answer `complete`, so "answer `unknown` whenever the file contains a
dynamic construct" is not a legal way to satisfy this ratchet.

### §2 — Consultation records: making non-use visible

**Claim under test:** TSA is used.

**§2 is conditional on RFC-0027 being accepted, and is empty until RFC-0027 L6.2
exists.** Stated plainly, because the first draft of this RFC asserted "no change
to the RFC-0025 or RFC-0027 designs" in the same document that proposed *adding a
record kind* to RFC-0027's L9 ledger — adding a record kind **is** a design
change. Measured 2026-08-19:

- RFC-0027 is `draft`, not accepted. Extending its ledger is a change to an
  unapproved design.
- `tree_sitter_analyzer/calibration/` **does not exist**. The first draft listed
  it under Affected source paths as if it did; it is now marked prospective.
- There is no `QueryCost`, no declared budget, and **no caller-side rejection
  path anywhere in the package**. Nothing can populate `declined_reason`.

Therefore `declined_reason` would be `None` on **100%** of records until
RFC-0027 L6.2 ships. §2's own Drawbacks entry said "measures a proxy, not the
thing"; the accurate statement is stronger: **the proxy is not weak, it is
currently empty.** §2 must not be implemented before RFC-0027 is accepted and
L6.2 lands, and its acceptance criteria are gated on that below.

Conditional on that, extend RFC-0027's L9 ledger with a third record kind
alongside `Prediction` and `Outcome`:

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

**Also out of scope until its precondition is re-measured:** the "this route is a
bypass candidate because its p95 sits in the seconds" argument. PR #1320 takes
`edit action=safe` to ~47 ms. The mechanism (an explicit decline record instead
of silence) is what §2 contributes; the specific slow route that motivated it is
scheduled for deletion.

### §3 — Invariants for the three blind classes

#### §3.1 Reachability

Point the existing zero-caller machinery at three questions it is not currently
asked:

1. **Registered-surface reachability.** Every MCP tool class and every CLI
   command module must be reachable from the tool registry or the argument
   parser. A tool that is built and tested but registered nowhere fails.
   *This catches defect #2 — and note that a test currently pins that orphan
   state as expected; that assertion must be corrected, not preserved.*

   **The orphan count is six, not one.** Measured against the live registry on
   2026-08-19: `CodeGraphPRReviewTool`, `CodeGraphRefactorTool`,
   `GetProjectSummaryTool`, `MiddlewareDetectorTool`, `UniversalAnalyzeTool`,
   `UnreachableCodeTool`. The first draft's "the known orphan", singular,
   understated this by ~6×.

   **Disposition rule (mandatory — the invariant is not implementable without
   it).** Without a stated rule, an implementer facing six red rows will add an
   allowlist of six entries plus three for the abstract bases below, tick the
   box, and thereby **manufacture a new pinned-orphan-state test — the exact
   anti-pattern this item exists to kill.** So: every orphan must be resolved
   into exactly one of three dispositions, recorded in the invariant's data, and
   an allowlist entry is not one of them:

   - **delete** — no consumer, no plan: remove the tool and its tests;
   - **wire** — register it in the facade/registry it belongs to;
   - **deprecate with an expiry** — keep it, mark it deprecated with a named
     removal version, and let the invariant **fail once that version ships**.

   **Abstract-base exclusion.** `FacadeTool`, `MCPTool` and `_CallTreeBase` are
   abstract/base classes and are legitimately not registered. The exclusion is
   structural, not an allowlist: a class is exempt iff it is `abc`-abstract or
   has no concrete `execute`. Naming them individually would be the allowlist
   pattern again.
2. **`next_step` routability.** Restated, because the first draft's wording is
   **false as written**. Real emitted strings include "Pass roots within the
   project boundary." and "Check server logs for details." — English prose, not
   routes; an invariant requiring every `next_step` to name a resolving route
   fails on correct behaviour. The invariant is:

   > Any `next_step` containing a token matching a known tool / facade / action
   > name must resolve to a **registered** route.

   That still catches the live defect: `build_project_index_tool.py` emits
   `next_step="get_project_summary"`, a token that matches a tool name and
   resolves nowhere.
3. **Dispatch reachability.** For each language-family branch in a resolver
   dispatch, at least one test must reach it **through the public entry point**,
   not by calling the private helper. *This catches defect #3, where the ESM
   branch was unreachable in production while its helper's unit tests passed:
   `ImportGraph._resolve_import` (`import_graph.py:350`) dispatches, and the
   `startswith("import ")` branch at `:372` is what the private-helper tests
   never exercised.*

**Rule 5's caveat, corrected.** The first draft repeated CLAUDE.md rule 5's
figure of "~50 modules" imported by `conftest.py`'s autouse singleton reset. That
figure is stale in two ways, measured 2026-08-19:

- `tests/conftest.py:334` (`_reset_all_singletons`) states in its own docstring
  that it uses `importlib.import_module()` with **string paths specifically so
  that static call-graph tools do not record a conftest→module edge** — the fix
  for **issue #220**. The phantom edges rule 5 warns about were deliberately
  removed.
- It touches **10 distinct modules** across 11 `import_module` call sites (the
  formatter registry is re-imported inside its own reset lambda), not ~50:
  `core.analysis_engine`, `core.language_detector`, `core.query`,
  `formatters.formatter_registry`, `core.engine_manager`,
  `mcp.utils.file_output_factory`, `mcp.utils.search_cache`,
  `mcp.utils.gitignore_detector`, `language_loader`, `query_loader`.

So §3.1's one-way property is **safe, but the stated reason for it was wrong**.
These invariants still use only the zero-caller signal, because one-way false
positives are the conservative choice on principle. But the contamination that
made a positive-caller assertion unusable has been fixed, so a positive-caller
assertion **may now be available again** — worth measuring before assuming it is
not, and out of scope here.

**§3.1's zero-signal is exempt from §1's ratchet, and §1 is scoped away from
it.** The cheapest way to maximise §1's ratchet is "answer `unknown` whenever the
file contains any dynamic construct" — and dynamic construction is exactly how
the orphan-detection subjects are built (`health_facade.py` is assembled by a
function-local import; `plugins/manager.py:72` uses `importlib.import_module`).
Under that implementation a genuine orphan would answer `unknown` instead of `0`,
§3.1 would silently stop detecting anything, and **both gates would be green** —
a new instance of this RFC's own defect shape. Therefore, normatively:

- §1 applies only to symbols whose file has **at least one unresolved edge**
  (§1.2); and
- §3.1's zero-caller signal is **exempt** from §1's ratchet — a zero there must
  remain a zero, and a `completeness` field is not a licence to soften it.

#### §3.2 Gate effectiveness

Every **first-party, detector-bearing** gate must carry a **self-check**
proving its detector still matches live production, asserting **exact** set
equality — not a `count > 0` lower bound.

**Scope, stated precisely, because "every blocking gate" is unimplementable.**
`.pre-commit-config.yaml` declares **27 hooks, of which 21 are third-party**:
`ruff` + `ruff-format`, 14 `pre-commit-hooks`, `detect-secrets`, `bandit`,
`mypy`, `pyupgrade`, `actionlint`. You cannot add a `--self-check` mode to
`ruff`, and requirement 2 below ("count of surface items outside the watch
filter == 0") has **no referent at all** for `check-yaml` — it has no watched
surface to be outside of. §3.2 therefore scopes to the **6 local hooks**:

| local hook | has a live surface to drift from? |
|---|---|
| `tsa-codemap-sync` | **yes** — the MCP/CLI registry; already rebuilt this way in #1314 |
| `weak-assertion-ratchet` | **yes** — the set of assertions it can parse (its blind spot to markdown is defect #5) |
| `block-banned-test-names` | **yes** — the banned-pattern list vs the live test-file set |
| `workflow-consistency-tests` | **yes** — the set of workflows it checks vs `.github/workflows/*` |
| `block-local-artifacts` | partial — a static path/glob denylist; requirement 1 applies, requirement 2 does not |
| `tsa-ps-ascii` | partial — a static character-class check over `.ps1`; requirement 1 applies, requirement 2 does not |

Third-party hooks are out of scope: they are versioned upstream, and a pinned
`rev` bump is the review surface for their behaviour. Requirements 1 and 2 apply
to the four "yes" rows; requirements 3 and 4 apply to all six.

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
4. the test **invoked by a named CI job** whose failure fails the job, or —
   where no CI job blocks — wired into pre-commit, **naming which**. The codemap
   gate's own test was referenced by no workflow at all before #1314.

   **The blocking layer is pre-commit, not CI.** Measured 2026-08-19 via the
   GitHub API: `branches/develop/protection` returns **404 — not protected**, and
   the repository's only ruleset (`main-branch-protect`) restricts just
   `deletion` and `non_fast_forward`, with **no `required_status_checks`**. So
   today *no CI job can block a merge*, and "wired into CI" is not by itself a
   sufficient discharge of this requirement. Two acceptable resolutions, and
   §3.2 requires one of them to be named per gate:

   a. add `required_status_checks` to a `develop` ruleset covering the job — this
      is itself in scope for §3.2, since a gate that cannot fail a merge is the
      §3.2 defect shape one level up; or
   b. wire the gate into pre-commit, the only actually-blocking layer, and state
      that CI collection is corroboration rather than enforcement.

#### §3.2 instances already live in the tree

Two of them sit in the directory §1 targets, which is why they are recorded here
rather than left as footnotes:

1. **A ratchet that no CI job collects.**
   `tests/benchmarks/claims/test_unknown_rate_ratchet.py` declares
   `pytestmark = [benchmark, claims_benchmark, full_language]`. Measured against
   the two marker expressions that exist: `reusable-test.yml` runs
   `-m "not slow and not e2e and not network and not benchmark and not full_language"`
   → **0 collected**; `dogfood-pr-check.yml:127` (job `claim-invariants`) runs
   `-m "claims_benchmark and not full_language"` → **0 collected**. The gate runs
   **nowhere**.

   This matters beyond the one file: it means **§1's acceptance criterion
   "ratchet wired into CI" is tickable against a test CI never collects** — which
   is defect #1 from this RFC's own table (a gate that exits 0 because it matched
   nothing), reproduced by the RFC that exists to prevent it. Stated here rather
   than discovered later. §1 and §3.2 therefore require every gate to name its
   **marker set** *and* its **workflow job**, not only its file path, and to
   prove collection with a non-zero collected count.

2. **A tautological assertion in the same directory.**
   `test_unknown_rate_threshold_value` asserts
   `UNKNOWN_RATE_THRESHOLD_PCT == 6.0` — a module constant compared against its
   own literal. It cannot fail for any reason other than someone editing both
   lines, measures nothing about the repository, and is a T-3 instance
   (a test whose only effect is to exist). The sibling
   `test_unknown_rate_threshold_is_documented_in_this_file` reads its own source
   and asserts substrings are present — same class. Both must be replaced by a
   live measurement or deleted.

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

**PR attribution, reconciled with RFC-0029: the fix is `pre-#1312`.** The work
was authored on **#1312**'s branch and reached `develop` folded into **#1308**'s
merge, so both numbers are defensible; this RFC and RFC-0029 both say
`pre-#1312`, naming where the change was written. An earlier draft of this RFC
said `pre-#1308`.

**Minimum invariant:** any code comparing a path against an AST-cache key must be
covered by a test asserting the comparison holds under **both** separator
conventions, independent of the host. This is cheap and it is the specific bug
class already shown to be live.

## Three-Surface impact (CLI ↔ MCP parity)

| capability | CLI | MCP |
|---|---|---|
| `completeness` on caller answers (§1) | present on the JSON payload | present on the TOON payload |
| consultation + decline rates (§2, conditional) | `--self-health` (extends RFC-0025 L5) | `health action=self` |

**§1 is a surface change and this RFC no longer claims otherwise.** It adds one
**response field**, `completeness`, on both surfaces with identical values — a
parity test pins that. It adds **no new flag and no new action**, and it does
**not** widen `_LEGAL_VERDICTS` (see §1.1 for why a ninth verdict is the more
invasive option). §3 is tests and gates only. §2 extends an existing report and
is conditional on RFC-0027. The locked TOON-on-MCP / JSON-on-CLI asymmetry is
untouched; per CLAUDE.md §1 the TOON payload must carry the same scalar field
rather than dropping it.

## Drawbacks

1. **Near-pure cost, no feature.** Nothing here makes the product do anything
   new; the one field §1 adds only exposes a status the store already holds. It
   makes existing claims falsifiable. The argument for paying it is that five of
   the seven motivating defects survived a green CI, and one of them shipped a
   Windows-wide correctness bug.
2. **The §1 corpus is hand-curated and will rot.** Ground truth requires human
   judgement about whether a dynamically-dispatched edge exists. Mitigated by
   keeping the corpus small and the invariant one-directional.
3. **§1 will fail on merge, and more widely than §3.1.** Adding `completeness`
   changes the response shape of the callers route, so the response-surface
   contract test (`test_tool_response_contract.py`) and every fixture that pins
   the callers payload go red, on both surfaces. This is the **larger** of the
   two merge-time failures in this RFC and was missing from the first draft
   entirely, which is why it is listed above §3.1's.
4. **§3.1 will fail on merge.** Six existing orphans, and at least one test that
   pins an orphan as expected. That is the point, and the fix is to apply the
   §3.1 disposition rule — not to add an allowlist.
5. **§2 is empty until RFC-0027 L6.2 exists.** Not "a weak proxy": with no
   `QueryCost` and no rejection path, `declined_reason` is `None` on 100% of
   records. Non-invocation is additionally unobservable from inside. Both stated
   in the design rather than papered over.
6. **§3.2 imposes work on every future first-party gate.** Acceptable: a gate
   that cannot prove it still fires is worse than no gate, because it
   manufactures confidence. Third-party hooks are explicitly out of scope
   (§3.2).
7. **§3.2 may require a repository-settings change, not only code.** With no
   `required_status_checks` on `develop`, "the test is invoked by a CI job that
   can fail" is not satisfiable in code alone.

## Alternatives

- **A: Trust review to catch these.** Rejected on evidence. Five review rounds by
  an automated reviewer on one PR produced a stream of individually-valid
  findings about an unbounded enumeration, and never named the architecture as
  the defect. Review finds instances; invariants close classes.
- **B: Raise coverage instead.** Rejected. All seven defects lived in *covered*
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
   against the pre-#1312 resolver.
8. §2 (only once RFC-0027 L6.2 exists): a declined consultation is recorded with
   its exact reason code; an unavailable one is `null`, never `0`.
9. §1.1: the callers route on the undecidable corpus must emit
   `completeness="unknown"`, and its `next_step` must **not** say "Symbol not in
   the index" while the symbol is indexed. RED today.
10. §1.2: a synthetic change that answers `unknown` for a symbol in a
    fully-resolved file must **fail** — the scope guard, not just the ratchet.
11. §3.1: an allowlist-shaped resolution of an orphan must fail the invariant;
    only delete / wire / deprecate-with-expiry may make it green.
12. §3.2: each named gate must report a **non-zero collected count** under the
    marker expression of the CI job (or pre-commit hook) that claims it. RED
    today for `test_unknown_rate_ratchet.py`, which collects 0 everywhere.

## Acceptance criteria

- [ ] §1.1 `completeness` field emitted by the callers route on both surfaces;
      response-surface contract test updated; parity test green
- [ ] §1.1 `_LEGAL_VERDICTS` **unchanged** — no ninth verdict added
- [ ] §1.1 `next_step` no longer claims "Symbol not in the index" for an indexed
      symbol with unresolved callers
- [ ] §1 corpus + one-directional invariant green
- [ ] §1 ratchet wired into a **named** CI job **and** its marker set recorded,
      with a proven non-zero collected count (not merely a committed file)
- [ ] §1.2 reconciliation with `test_unknown_rate_ratchet.py` recorded in both
      test files, including which gate wins on collision
- [ ] §1.2 scope guard green: a symbol in a fully-resolved file answers
      `complete`, never `unknown`
- [ ] §1 documented as the executable form of the conservative-resolution claim,
      cross-referenced from `ROADMAP-no1-agent-trust.md`
- [ ] §2 **blocked until RFC-0027 is accepted and L6.2 (`QueryCost`) lands** —
      not tickable before then
- [ ] §2 `Consultation` record persisted in the L9 ledger; decline rates in
      `--self-health`; CLI↔MCP parity test green
- [ ] §2 scope limitation stated in the emitted payload, not only in this RFC,
      including that `declined_reason` is `None` until a rejection path exists
- [ ] §3.1 registered-surface reachability green; all **six** orphans given a
      delete / wire / deprecate-with-expiry disposition; the test that pins an
      orphan **corrected**, not preserved; **no allowlist**
- [ ] §3.1 abstract-base exemption is structural (`abc`-abstract / no concrete
      `execute`), not a list of three names
- [ ] §3.1 `next_step` routability green under the token-matching formulation
- [ ] §3.1 dispatch reachability asserted through public entry points
- [ ] §3.1 zero-caller signal exempt from §1's ratchet, asserted by a test that
      fails if a genuine orphan starts answering `unknown`
- [ ] §3.2 each of the **six first-party local hooks** has an exact-equality
      self-check; the four with a live surface additionally have a
      coverage-invariant of exactly 0
- [ ] §3.2 every gate names its **marker set + workflow job** (or its pre-commit
      hook) and proves a non-zero collected count
- [ ] §3.2 the enforcement layer is named per gate: either
      `required_status_checks` added to a `develop` ruleset, or pre-commit
      declared as the blocking layer
- [ ] §3.2 `test_unknown_rate_threshold_value` and
      `test_unknown_rate_threshold_is_documented_in_this_file` replaced by a live
      measurement or deleted
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
- **No change to the RFC-0025 design.** This RFC adds invariants over it. It
  *does* propose a change to RFC-0027 (a third L9 record kind), which is why §2
  is explicitly conditional on RFC-0027's acceptance rather than claiming to
  leave it untouched.
- **No interactive per-test mutation query.** That is
  [RFC-0029](0029-does-this-test-constrain-this-code.md). Split by mechanism:
  static, always-on, CI-enforced invariants here; on-demand, per-pair,
  non-gating query there.
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
