# RFC-0029: "Does this test constrain this code?" — a question an agent can ask

- **Status**: draft
- **Author(s)**: @lead-agent
- **Created**: 2026-08-20
- **Last updated**: 2026-08-20
- **Evidence level**: every number and code location cited here is an **E0**
  measurement taken on 2026-08-19/20 on a single un-isolated Windows host, with
  the command recorded inline. No claim here is qualified above E0, and public
  wording stays bound by the RFC-0021 evidence ladder — the same clause RFC-0028
  carries.
- **Tracking issue**: TBD
- **Relationship to other RFCs**:
  - **Parent: [RFC-0017](0017-test-effectiveness-mutation-and-value-invariants.md)**
    (accepted 2026-06-14). RFC-0017 owns mutation *scoring* as a CI campaign,
    per-tool value invariants, outside-the-loop authorship, and boundary
    testing, and states explicitly: *"This RFC adds no MCP/CLI surface."*
    This RFC adds the surface RFC-0017 declined to add, and does not change any
    of its mechanisms.
  - **Boundary with [RFC-0028](0028-measuring-claimed-properties.md), drawn by
    mechanism rather than by gate-versus-test**: RFC-0028 owns **static,
    always-on, CI-enforced invariants**; this RFC owns the **on-demand,
    per-pair, non-gating query**. That split matters because both documents
    initially claimed the same two defects: RFC-0028 §3.1 item 3 claims the ESM
    dispatch and §3.2 requirement 3 claims the synthetic-fixture defect, and
    this RFC's corpus claimed both as *its* motivation. Under the mechanism
    split **both defects belong to RFC-0028** — each is closable by an
    always-on invariant, which is strictly better than a query someone has to
    remember to ask. This RFC keeps them only as **engine-validation fixtures**
    (does the mutation engine reproduce a known-real escape?), never as
    justification for the feature's existence.
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/mutation_probe/` (new — AST mutation + isolated run)
  - `tree_sitter_analyzer/mcp/tools/edit_facade.py` (new action — **not**
    `health_facade.py`; see §Surface)
  - `tree_sitter_analyzer/cli/argument_groups/` (CLI twin)
  - `tests/unit/mutation_probe/` (new — including the escaped-defect corpus)
  - `docs/CODEMAPS/cli.md`, `docs/CODEMAPS/mcp-tools.md`

## Summary

A test can pass while constraining nothing. Today there is no way to ask whether
a specific test actually holds a specific piece of code in place; the only
available answer is a Linux-only batch mutation campaign that reports a score
for a whole module.

This RFC adds one question, callable mid-work, on any platform:

> Given a test node id and a code location, apply exactly one mutation from a
> small closed set at that location, run only that test, and report whether it
> goes red **for an assertion-derived reason**.

If it does not go red, **that test asserts nothing about that code**, whatever
its name says. If it goes red because the mutation crashed the module rather than
because an assertion caught it, the answer is `unknown`, never `constrains`. The answer is a fact, not a judgement, and the RFC deliberately
stops there.

**Honest scope, corrected from the first draft.** Of the seven "green CI, broken
behaviour" defects found on 2026-08-19, this operation as specified answers
**two** — not four. The first draft claimed four; two of those are not posable by
this operation at all (one is a `bash` gate with no pytest node id; one is a wrong
*expected value* in a set literal, which no branch inversion can detect) and are
handed to RFC-0028. The count is corrected everywhere below rather than softened:
an inflated motivating count is the same defect class this RFC exists to catch.

## Motivation

### Two of seven escaped defects in one session are this exact question

On 2026-08-19 a single working session produced seven defects of the form
"green CI, broken behaviour" (the count is shared with
[RFC-0028](0028-measuring-claimed-properties.md), whose earlier draft said six;
the seventh is the `assert p50_ns > 0` case below). Four of them look like one
unaskable question. **Two of the four actually are, and the table says which:**

| defect | the question | answer | posable here? |
|---|---|---|---|
| `assert p50_ns > 0` was claimed to lock a latency fix | does this test constrain the fix? | no | **yes**, once the hoist mutation below exists |
| `.mjs` resolver tests called the **private helper**, while ESM never reached it | does this test constrain the public path? | no | **yes** — inverting `startswith("import ")` at `import_graph.py:372` leaves the private-helper test untouched |
| the codemap-sync gate's test built a **synthetic** old-shape registry fixture | does this test constrain the real registry? | no | **no** — `tests/integration/test_codemap_sync_hook.sh` and `scripts/codemap-sync-check.sh` are both **bash**: no pytest node id, no Python AST. RFC-0028's deferred section rules shell out of reach by name. → RFC-0028 §3.2 |
| a test **pinned an orphaned tool as expected** | does this test constrain reachability? | it pinned the inverse | **no** — `tests/unit/cli/test_install_skills.py:571` is `legacy_call_names = sorted(set(LEGACY_TOOL_MAP) \| {"get_project_summary"})`, a set literal in the test body. The defect is a wrong *expected value*; inverting a branch structurally cannot detect it. → RFC-0028 §3.1 |

So the honest motivating count is **two of seven**, and both of those two are also
claimable by an RFC-0028 invariant (see the boundary note in the header). What
this RFC contributes over those invariants is not coverage of these two defects —
it is the ability to ask the question **about a pair nobody wrote an invariant
for**, mid-work, before the escape happens.

Both were found by a human or a reviewer **reverting the change by hand and
watching the test still pass.** That is a mechanical operation performed
manually, repeatedly, in a single day.

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
FailureKind = Literal["NONE", "ASSERTION", "NON_ASSERTION", "NOT_RUN"]


@dataclass(frozen=True)
class ConstrainsResult:
    """Whether a test detects a single applied mutation.

    ``constrains`` is emitted only when the baseline run did not fail AND
    the mutated run failed with an **assertion-derived** failure. Anything
    else is ``does_not_constrain`` or ``unknown`` — never optimistically
    ``constrains``. pytest labels a crash inside a test body ``failed``,
    identically to a real detection, so the outcome label is not usable as
    the discriminator; see below.
    """

    verdict: Literal["constrains", "does_not_constrain", "unknown"]
    reason: str | None          # closed subcodes; None only when constrains
    mutation: str               # human-readable: what was changed, where
    baseline_failure: FailureKind
    mutated_failure: FailureKind
    baseline_ms: float          # measured, so the cost claim stays executable
    mutated_ms: float
    overhead_ms: float          # wall minus the two reported call durations
```

Steps, in order:

1. **Baseline.** Run the named test on the unmodified tree in isolation. If it
   does not pass, return `unknown` / `BASELINE_NOT_GREEN` — a red or erroring
   test cannot be shown to constrain anything.
2. **Mutate.** Locate the target and apply exactly one mutation from the closed
   set below. The mutated bytes are held **in memory** and served to the child
   process by a `sys.meta_path` finder; nothing is written to the working tree or
   to a temp file on `sys.path` (see §"Mutation delivery" for why the temp-copy
   approach cannot work). If no applicable mutation exists at the location,
   return `unknown` / `NO_INVERTIBLE_BRANCH`.
3. **Re-run.** Run only that test against the mutated module.
4. **Report.** `constrains` iff the baseline did not fail **and** the mutated run
   failed **with an assertion-derived failure** (see below). Never on pytest's
   outcome label alone.

#### The failed-vs-errored discriminator does not exist in pytest

The first draft specified "`constrains` iff baseline passed and mutated failed"
and separately promised a `MUTATED_RUN_ERRORED` subcode for "the test errored
rather than failed". **pytest has no such distinction for the case that matters.**
Measured 2026-08-20 (`uv run pytest <probe file> -q --override-ini="addopts=--strict-markers" -p no:cacheprovider`),
a probe module raising `ModuleNotFoundError` in a test body, `AttributeError` in a
test body, and `assert 1 == 2`:

```
FAILED test_probe.py::test_module_not_found
FAILED test_probe.py::test_attribute_error
FAILED test_probe.py::test_real_assert
3 failed in 0.45s
```

All three are `failed`. pytest reserves `error` for **collection and fixture**
problems, not for exceptions raised inside a test body. So the original algorithm
returns `constrains: true` for a mutation that merely made the module crash —
**the exact false reassurance the fail-closed section exists to prevent, reachable
through this RFC's own algorithm.**

Respecified: discriminate on whether the failure is **assertion-derived**, using
the exception type and representation available from the run
(`excinfo.type` / `longrepr`), not on pytest's outcome label:

| observed on the mutated run | classification | verdict |
|---|---|---|
| no failure | `NONE` | `does_not_constrain` |
| `AssertionError` (including pytest's rewritten asserts), or an explicit `pytest.fail` / `raises` mismatch | `ASSERTION` | `constrains` |
| any other exception — `ImportError`, `AttributeError`, `TypeError`, `SyntaxError`, … | `NON_ASSERTION` | `unknown` / `MUTATED_RUN_CRASHED` |
| node not collected, deselected by a marker filter, or the run never reached the test | `NOT_RUN` | `unknown` / `NOT_ISOLABLE` |

The subcode is renamed `MUTATED_RUN_CRASHED` from `MUTATED_RUN_ERRORED`, because
"errored" named a pytest outcome that does not occur here and would have sent an
implementer looking for a label they can never observe.

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
| **hoist a statement out of its nearest enclosing `with` / `try` block** | any statement inside a `with`/`try` body |

The fourth is not decorative. It is the exact shape of five defects in one
day (`newline=""`, `follow_symlinks`, extension-table membership), and a
missing keyword argument is invisible to a condition-flipping mutator.

**The fifth exists because without it the flagship example is not covered by the
flagship design.** The `assert p50_ns > 0` defect was produced by *relocating a
statement across a `with`-block boundary* — the key derivation moved outside
`recorder.measure`. None of the first four mutations reproduces that, and
statement deletion (which also does not reproduce it) is excluded. By this RFC's
own standard — "the corpus **is** the acceptance criterion… if it does not
reproduce the escaped defects, the feature is a lie" — v1 without this mutation
is a lie about its own motivating example. So:

> **Hoist**: move exactly one statement from inside a `with`/`try` body to
> immediately before that block, preserving relative order otherwise.

Note this is **not** statement deletion, which stays excluded: the statement still
executes, and its effect on the program's data flow is unchanged. Only its
*guarded / measured context* is removed. That is precisely the "the guard was
outside the guarded region" bug shape — a timing window, a lock, a transaction, a
`suppress`, a temp-dir lifetime — and it is invisible to every operator-level
mutator.

**Deliberately excluded** from v1: arithmetic operators, loop bounds, exception
types, statement deletion, and statement *reordering* other than the hoist above.
A small closed set with a published false-negative profile is more useful than a
large one with an unknown profile — and RFC-0017's campaign remains the
comprehensive instrument.

### Fail-closed, because the failure mode is a false reassurance

`constrains: true` is the answer an agent will act on by *not* looking further.
So every uncertainty resolves away from it:

- baseline not green → `unknown`, never `constrains`
- no invertible branch at the location → `unknown`
- the test cannot be run in isolation (fixture depends on session state), or the
  node id is not collected / is deselected by a marker filter →
  `unknown` / `NOT_ISOLABLE`
- mutation applied and the test failed, but **not** with an assertion-derived
  failure → `unknown` / `MUTATED_RUN_CRASHED`, because a crash is not detection
  (and pytest labels it `failed`, identically to a real detection — see above)
- a timeout → `unknown` / `TIMEOUT`

A verdict of `does_not_constrain` is a positive finding and is only emitted when
the mutated run genuinely **passed**.

### Mutation delivery: a `sys.meta_path` finder, not a temp file on `sys.path`

Open question 1 of the first draft proposed "a temp copy of the file plus a path
override". **That is unimplementable for every candidate target, and it is
jointly unsatisfiable with acceptance criterion 7** ("working tree provably
unmodified"), so it is resolved here in the design rather than left as a wrong
proposal in an open question.

Measured: every candidate target uses **relative** imports —
`tree_sitter_analyzer/import_graph.py:24` is `from .constants import (...)`. A
file copied to a temp directory and reached via `sys.path` raises
`ImportError: attempted relative import with no known parent package`. The only
escapes from that are (a) writing the mutated bytes **into the package
directory**, which violates "working tree provably unmodified", or (b) copying
the whole tree, already rejected as too slow to ask casually.

**Design:** install a `sys.meta_path` finder in the child process that intercepts
exactly one fully-qualified module name (e.g.
`tree_sitter_analyzer.import_graph`) and returns a loader serving the **mutated
bytes from memory**, with the package's real `__package__` / `__spec__.parent`
preserved so relative imports resolve normally. Every other module loads from the
untouched working tree. Nothing is written anywhere, so criterion 7 holds by
construction rather than by cleanup. The finder is injected via a `-p` plugin or
a `conftest`-free `sys.meta_path.insert(0, ...)` in the subprocess bootstrap,
before the target module is first imported.

### Isolating the run

The first draft proposed "a subprocess with `-p no:randomly` and the target node
id, so xdist and ordering plugins cannot perturb the result." Measured
2026-08-20, that recipe is wrong in both halves:

- `-p no:randomly` is a **no-op in this repository**: `pytest_randomly` is not
  installed (`importlib.util.find_spec("pytest_randomly") is None`). Disabling a
  plugin that is not there protects nothing.
- It does nothing about **xdist**, which is not merely a declared dependency
  awaiting `-n`: `pytest.ini` `addopts` sets `--numprocesses=4 --dist=worksteal`
  **by default**, so every plain invocation already runs distributed. The same
  `addopts` also sets `--reruns=1` (a flaky-rerun would mask a detection) and a
  default marker filter, `-m "not e2e and not slow and not network and not
  full_language and not benchmark"`, which can silently **deselect the target
  node** — producing "no tests ran", which must map to `unknown` / `NOT_ISOLABLE`
  and never to `constrains`.

**Design:** invoke pytest in a subprocess with the repo's defaults overridden
rather than trusted, following the pattern the repo's own CI already uses
(`dogfood-pr-check.yml` uses `--override-ini="addopts=…"`):

```
uv run pytest <node id> \
  --override-ini="addopts=--strict-markers --timeout=<budget>" \
  -p no:cacheprovider
```

That drops xdist, the rerun, and the marker filter in one move, and
`-p no:cacheprovider` keeps the run from writing `.pytest_cache`. The collected
count must be asserted to be exactly 1 before either outcome is believed.

### Surface

| capability | CLI | MCP |
|---|---|---|
| does this test constrain this code | `--mutation-probe TEST CODE` | `edit action=mutation_probe` |

**The facade is `edit`, not `health`.** Two reasons, both measured:

1. **`health` asserts read-only, and this action is not.**
   `tree_sitter_analyzer/mcp/tools/health_facade.py:33` states "every action in
   this facade is read-only, so `readOnlyHint=True` is valid", and
   `tests/unit/mcp/tools/test_health_facade.py:184` pins all four annotation
   flags (`readOnlyHint=True, destructiveHint=False, idempotentHint=True,
   openWorldHint=False`). An action that materialises mutated module bytes, spawns
   pytest and **executes arbitrary test code** falsifies all four — and the test
   would stay **green**, because the annotation is a facade-level constant rather
   than a per-action one. An MCP client would be told `readOnlyHint=True` for an
   action that runs a test suite. That is a worse outcome than any ergonomic cost.
2. **`edit` already spans mutating-intent actions** and already owns
   `constraints` / `impact` / `guard`; its docstring (`edit_facade.py:22-31`)
   records that a single honest `readOnlyHint=True` is impossible there, which is
   the correct home for this action.

The first draft justified `health` with "RFC-0017 placed test effectiveness in
that domain". **That justification was fabricated and is deleted:**
`grep -i health rfcs/0017-*.md` returns **nothing** — RFC-0017 mentions no facade
at all.

**The action is named `mutation_probe`, not `constrains`.** `edit` already exposes
`constraints`, and `facade_tool.py:297` resolves an unknown action with
`difflib.get_close_matches(..., cutoff=0.6)`. Measured ratios against the live
`edit` action list:

| candidate | closest existing action | ratio | self-heals? |
|---|---|---|---|
| `constrains` | `constraints` | **0.952** | yes — a one-character typo silently routes to the wrong action, in both directions |
| `test_constrains` | `constraints` | **0.769** | **yes** — still above the 0.6 cutoff |
| `mutation_probe` | `guard` | 0.316 | no |

`test_constrains` was a candidate but measurement rejects it: 0.769 > 0.6, so it
collides too. `mutation_probe` is the only tested candidate that cannot self-heal
into a neighbouring action. The verdict *values* (`constrains` /
`does_not_constrain`) keep their names — they are response data, not a routed
identifier.

No new facade, so the RFC-0022 menu gate is untouched. CLI defaults to JSON, MCP
to TOON — the locked asymmetry, unchanged.

## Three-Surface impact (CLI ↔ MCP parity)

1:1 as above, with a parity test. Adding a CLI flag and an MCP action requires a
CODEMAP update, and the codemap-sync gate (rebuilt in #1314) now genuinely
blocks and asserts exact set equality — so this cannot land undocumented.

## Drawbacks

1. **It runs tests, so it is slow relative to a query — measured, and the
   "casual asking" claim does not survive it.** Measured 2026-08-20 on this host:

   ```
   uv run pytest tests/governance/test_postmortem_guards.py::test_postmortem_v1_13_doc_exists -q -p no:cacheprovider
   → 18.71 s wall  (pytest's own report: 8.51 s; the test's `call` duration: 0.03 s)
   ```

   Effectively none of that is the test. It is `uv` resolution, a **641-line
   `tests/conftest.py`** with an autouse singleton reset, and collection. A
   comparable run on 2026-08-19 measured **15.3 s** wall (`call` 0.24 s), so the
   magnitude is ~15–19 s, E0. **Two runs per question ⇒ ~30–38 s.**

   For scale: RFC-0028 §2 calls **3.3 s** "squarely inside the range where an
   agent routes around a tool". This operation is ~10× that. So the first draft's
   "acceptable, it is asked about one pair at a time" and its open-question
   rationale "a whole-tree copy is too slow to ask casually and casual asking is
   the point" are **inconsistent with each other**: at 30 s, casual asking does
   not survive. Stated plainly rather than asserted away.

   What the RFC therefore claims: this is a **deliberate, blocking, one-pair
   question** — the ergonomics of `git bisect`, not of a hover tooltip — and it is
   worth 30 s when the alternative is a manual revert-and-rerun that costs
   minutes. What would make casual asking real, and is **explicitly not in v1**:
   a warm in-process runner (import the target once, re-execute the single test
   function against re-imported mutated bytes) or a persistent session that
   amortises `uv` + conftest + collection across calls. Either is a separate RFC;
   neither is assumed here.

   **Budget (§11 rule 1 — an executable invariant, not prose):** a single call
   must complete within **60 s** wall on the slowest supported axis, and the
   two-run overhead attributable to harness startup must be **reported in the
   response** (`baseline_ms`, `mutated_ms`, `overhead_ms`) so the number can never
   again live only in a design document.
2. **A small mutation set has false negatives** — `constrains: true` means "this
   test detects *this* inverted branch", not "this test is good". The verdict
   wording must not overclaim, and the published false-negative profile is part
   of the deliverable.
3. **It executes arbitrary test code in a child process.** That is why it belongs
   on the `edit` facade rather than the read-only `health` facade (see §Surface).
   It writes **nothing** — mutated bytes are served from memory by a
   `sys.meta_path` finder — so the working tree and the temp directory are both
   untouched; the temp-hygiene rules apply vacuously rather than being relied on.
4. **It could become a coverage-chasing instrument** — "make `constrains` return
   true" is a number to game, and T-3 prohibits exactly that. Mitigation: the
   result is a fact for a human or agent to act on, and it is deliberately **not**
   wired into any gate or score in this RFC.
5. **It confirms a hypothesis; it does not find one.** The caller must already
   supply *both* a test node id **and** a code location — so the operation is
   only reachable once you know where to look, and knowing where to look is
   frequently the missing insight. For the one covered defect this is concrete:
   the correct code location for the `.mjs` escape is the **dispatch** at
   `ImportGraph._resolve_import` (`import_graph.py:350`, ESM branch at `:372`),
   **not** the private helper `_resolve_js_import` (`:261`) that the test names.
   An agent that trusted the test's own subject would probe the helper, get
   `constrains` (the helper's unit tests do constrain the helper), and conclude
   wrongly. RFC-0028's static reachability invariant needs no such input, which
   is another reason the two defects it claims belong there rather than here.
6. **Two of the seven session defects are outside this operation entirely** — a
   `bash` gate and a wrong expected value in a set literal. Recorded in the
   motivation table rather than counted as coverage.

## Alternatives

- **A: extend `run_mutation_baseline.py` to accept arbitrary pairs.** Rejected as
  the primary path: it stays Linux-only, so the agent and maintainer who need it
  most cannot use it interactively. Worth doing *later* as the comprehensive
  arm — see RFC-0017 mechanism 1, which already owns that.
- **B: rely on coverage.** Rejected. Both motivating defects lived in *covered*
  code; the private-helper tests executed the helper every run. Coverage measures
  execution, not constraint.
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

The corpus **is** the acceptance criterion. If it does not reproduce the escaped
defects it claims, the feature is a lie. The corpus is **two** real escapes, not
four — the two dropped items and why are in the motivation table.

1. **`assert p50_ns > 0` vs the key-inside-`measure` fix** (PR #1320) →
   must return `does_not_constrain`. The one case where a reviewer already
   established the ground truth by hand. **This item is the acceptance test for
   the hoist mutation**: it is unreachable by the other four operators.
2. **The private-helper `.mjs` test vs the public `ImportGraph._resolve_import`
   dispatch** (pre-#1312) → `does_not_constrain` when the probed location is the
   dispatch at `import_graph.py:372`. **And** `constrains` when the probed
   location is the private helper `_resolve_js_import` — the pair together is the
   test that the operation is location-sensitive, and it is the executable form of
   Drawbacks 5.
3. **Positive controls**: at least three known-good exact-assertion tests →
   `constrains`. Without these the feature could pass items 1–2 by always
   answering `does_not_constrain`.
4. **Crash is not detection** (the respecified discriminator): a mutation that
   makes the module raise `ModuleNotFoundError` / `AttributeError` inside the test
   body must return `unknown` / `MUTATED_RUN_CRASHED`, **even though pytest labels
   all three `failed`** (measured 2026-08-20). RED against the first draft's
   outcome-label algorithm, which returns `constrains` here.
5. **Every fail-closed subcode** forced independently: `BASELINE_NOT_GREEN`,
   `NO_INVERTIBLE_BRANCH`, `NOT_ISOLABLE`, `MUTATED_RUN_CRASHED`, `TIMEOUT`.
6. **A deselected node is not a pass**: invoking with a node id the repo's default
   marker filter would deselect must return `unknown` / `NOT_ISOLABLE`, and the
   collected count must be asserted to be exactly 1.
7. **The working tree is never written**: assert byte-identical file digests
   across a call, including on a failure path. The `sys.meta_path` design makes
   this structural — the assertion pins it anyway.
8. **Relative imports survive mutation**: probe a module that uses
   `from .constants import ...` (e.g. `import_graph.py:24`) and assert no
   `ImportError: attempted relative import with no known parent package`. RED
   against the first draft's temp-copy-on-`sys.path` proposal.
9. **All-OS**: the mutation engine runs on Windows, macOS and Linux. This is the
   whole point of not using mutmut; a Linux-only implementation fails the RFC.
10. **False-negative profile**: for each excluded mutation kind, a test
    documenting that a defect of that kind is *not* detected, so the profile is
    executable rather than prose. Includes the two dropped corpus items as
    documented **out-of-scope** cases, not as failures.
11. **Latency budget**: a call on the positive-control pair completes within the
    60 s budget, and the response carries `baseline_ms` / `mutated_ms` /
    `overhead_ms`.

## Acceptance criteria

- [ ] `edit action=mutation_probe` + `--mutation-probe`, 1:1, parity test green
- [ ] the action lives on `edit`, **not** `health`; `health`'s
      `readOnlyHint=True` assertion remains true
- [ ] the action name does not self-heal into any sibling action under
      `difflib.get_close_matches(cutoff=0.6)` — asserted by a test over the live
      action list, not by inspection
- [ ] mutation engine runs on Windows, macOS and Linux with no `mutmut` dependency
- [ ] the **hoist** mutation is implemented and item 1 of the test plan passes
      because of it
- [ ] the **two-defect** corpus returns `does_not_constrain` for both
- [ ] at least three positive controls return `constrains`
- [ ] a non-assertion failure returns `unknown` / `MUTATED_RUN_CRASHED`, never
      `constrains`
- [ ] a deselected / uncollected node returns `unknown`, and collected count is
      asserted to be exactly 1
- [ ] the run is isolated by `--override-ini="addopts=…"` (dropping the repo's
      default xdist, rerun and marker filter), not by `-p no:randomly`
- [ ] mutated bytes are delivered via `sys.meta_path`; a relative-import module is
      in the corpus and does not raise `ImportError`
- [ ] every fail-closed subcode forced by its own test
- [ ] `unknown` is emitted, never a defaulted `constrains`
- [ ] working tree provably unmodified across every call path
- [ ] a call completes within the **60 s** budget and the response reports
      `baseline_ms` / `mutated_ms` / `overhead_ms`
- [ ] false-negative profile published and executable, including the two
      out-of-scope corpus items
- [ ] CODEMAPs updated; codemap-sync gate green
- [ ] NOT wired into any gate or score (deliberate, see Drawbacks 4)

## What this RFC does NOT do (deferred)

- **No mutation campaign.** RFC-0017 mechanism 1 owns that, and this RFC does not
  touch it.
- **No judgement.** It answers whether a branch is detected. Whether the test
  *should* be improved, and how, is the caller's call.
- **No gate.** Deliberately, until the false-negative profile exists.
- **No arithmetic / loop-bound / exception-type / statement-deletion mutations**
  in v1. Statement *hoisting* out of a `with`/`try` block **is** in v1 (see the
  mutation table); deletion and general reordering are not.
- **No shell-gate analysis and no expected-value checking.** The two dropped
  corpus items are out of reach by construction, not by scheduling: `bash` has no
  pytest node id and no Python AST, and a wrong constant in a test's expected
  value is undetectable by any structural mutation of the code under test. Both
  are RFC-0028's (§3.2 and §3.1 respectively).
- **No warm runner and no persistent session.** Named in Drawbacks 1 as what
  would make "casual asking" real; deliberately not attempted in v1.
- **Not a general audit of my own assertions.** A separate defect this week — a
  loose `>= 1` replaced by a pinned `== 2` where the measured value was `1` —
  is covered by RFC-0028 §3.2's doc-example execution, not by this.

### Two further wants — moved out of this RFC

Finding clustering across a session, and belief provenance. Both were drafted
here with their evidence; neither is about this RFC's question, and
[`rfcs/README.md`](README.md) makes a merged RFC immutable except for status and
clarifications — which would freeze two fully-evidenced feature proposals inside a
document that is not about them. They now live, evidence intact, in
[`ROADMAP-no1-agent-trust.md`](ROADMAP-no1-agent-trust.md) §11.

## Open questions

Two of the first draft's four open questions are **resolved in the design above**
rather than left open, because both of their proposals were measured to be wrong
and a wrong proposal sitting in an open question is an invitation to implement it:

1. ~~Temp copy of the file plus a path override?~~ **Resolved: no.** Every
   candidate target uses relative imports, so a temp copy on `sys.path` raises
   `ImportError`. See §"Mutation delivery" — a `sys.meta_path` finder serving
   mutated bytes for one module name.
2. ~~A subprocess with `-p no:randomly`?~~ **Resolved: no.** `pytest_randomly` is
   not installed (so the flag is a no-op) and xdist is on by default via
   `pytest.ini` `addopts`. See §"Isolating the run" —
   `--override-ini="addopts=…" -p no:cacheprovider`.

Genuinely open:

3. Should `does_not_constrain` include a *suggested* assertion? **Proposal: no.
   That is judgement, and it would invite the coverage-chasing failure mode in
   Drawbacks 4.**
4. Multi-branch locations — invert one branch or report per branch?
   **Proposal: report per branch, capped, since "the test catches branch A but
   not branch B" is more actionable than an aggregate.**
5. Is the ~30 s two-run cost tolerable in practice, or does the warm in-process
   runner named in Drawbacks 1 have to land before this is used at all? **Proposal:
   ship the subprocess version, measure how often it is actually invoked over one
   month, and let that decide — the same "measure, do not assume" discipline
   RFC-0028 applies to the moat.**
