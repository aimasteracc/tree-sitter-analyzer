# RFC-0027: The Secretary Layer — instant answers, comprehension, and a calibrated learning loop

- **Status**: draft
- **Author(s)**: @lead-agent
- **Created**: 2026-08-19
- **Last updated**: 2026-08-19
- **Tracking issue**: TBD
- **Relationship to other RFCs**:
  - complements [RFC-0025](0025-instant-causal-proprioception.md) (the *sensing*
    layers L1–L5). This RFC specifies the layers *above* sensing: L6–L10. It does
    not restate or modify RFC-0025's design; where it depends on a RFC-0025
    layer, the dependency is named explicitly.
  - §L10 **supersedes [RFC-0016](0016-semantic-symbol-search.md) conditionally**.
    RFC-0016 was rejected on measured evidence (2026-06-13 embedding pilot,
    2/5 on the conceptual-gap gate). L10 may only proceed after a re-pilot
    passes; see §L10 for the blocking precondition.
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/cache/answer_cache.py` (new — L6)
  - `tree_sitter_analyzer/mcp/tools/get_project_summary_tool.py` (L7 — currently unreachable)
  - `tree_sitter_analyzer/mcp/tools/codegraph_refactor_tool.py`, `rename_symbol.py` (L8 — currently unreachable)
  - `tree_sitter_analyzer/mcp/tools/modification_guard_tool.py` (L8 — wrong-signal fix)
  - `tree_sitter_analyzer/calibration/` (new — L9)
  - `tree_sitter_analyzer/semantic_search.py` (L10)
  - `tests/unit/...`, `tests/benchmarks/claims/...`

## Summary

RFC-0025 makes the analyzer *sense*: it knows, instantly and continuously, what
changed and what that touches. Sensing alone does not make a secretary. This RFC
specifies the five layers that turn a sensing organ into an assistant an agent
*wants* to consult:

- **L6 — Instant answer path**: the same question asked twice must not cost the
  same twice. Generation-keyed memoization plus declared query cost.
- **L7 — Comprehension surfaces**: the project explains itself — to a new agent,
  a new hire, and a first-time contributor — from graph facts, with no LLM.
- **L8 — Judgment surfaces**: what is rotten, what to fix first, and the
  *smallest* edit that accomplishes a change.
- **L9 — Calibration ledger**: TSA records what it predicted and later observes
  what actually happened, producing a published, falsifiable accuracy number.
  This is the mechanism behind "it gets smarter the more you use it", and it is
  the only one in this RFC that a competitor cannot copy without publishing
  their own error rate.
- **L10 — Semantic index**: embedding-backed similarity search, permanently
  and structurally subordinate to resolved evidence.

## Motivation

### The measured problem

Dogfood measurement on this repository (2026-08-19, Windows 11, ~1.8k files,
in-process, 3 repeats — magnitudes are load-bearing, digits are not):

| path | cold | warm | note |
|---|---|---|---|
| `edit action=safe` | 2.40 s | 2.41 s / 2.59 s | **no warm-path benefit at all** |
| `callers` (in-process) | 24.8 s | 16–17 ms | 1500x cliff |
| `--callers` (CLI subprocess) | 28–35 s | 28–35 s | pays the cliff *every invocation* |

`edit action=safe` is the single call an agent makes before **every** edit. At
2.4 s it is not a reflex; a spinal reflex is ~15 ms. Worse, it does not improve
on repetition — there is no memoization on the hottest path in the product.

The `callers` 24.8 s to 16 ms cliff is the direct signature of a missing standing
index; RFC-0025 L1 owns that. This RFC owns the *second* problem the same
measurement exposes: even once warm, **repeat questions are re-answered from
scratch**.

### The capability problem

A 2026-08-19 capability audit against the proprioception vision scored
**4 HAVE / 11 PARTIAL / 3 MISSING**. Three of the highest-value capabilities are
**built, tested, and reachable from nothing**:

| capability | implementation | reachable? |
|---|---|---|
| minimal edit set (rename) | `codegraph_refactor_tool.py:29` + `rename_symbol.py:291`, 15 passing tests | no facade, no CLI flag |
| project card (purpose + module descriptions) | `get_project_summary_tool.py:46` | no facade, no CLI flag |
| refactor priority `(1-health)*log(churn)*dead_ratio` | markdown only | 0 code hits, 0 tests |

`build_project_index_tool.py:244` emits `next_step="get_project_summary"` — a
name that routes nowhere — and `tests/unit/cli/test_install_skills.py:571` pins
that orphan state as *expected*. A test is currently protecting a wiring bug.
This is the same failure shape as the 2026-06-08 TOON incident (CLAUDE.md §11):
conformance tests verify the spec, and cannot notice the spec is wrong.

**The distance to the vision is shorter than the audit implies, and a
meaningful fraction of it is wiring, not construction.**

### The honesty problem

"使えば使うほど賢くなる" ("it gets smarter the more you use it") is, today,
false. Exactly one read-back path exists (`change_impact_support.py:114`,
monotone escalation from a **manually written** journal), and
`.ast-cache/decision_journal.db` does not exist on this repository — the path
has never been exercised. Nothing anywhere records whether an answer was
*right*.

Under CLAUDE.md §11 an unmeasured non-functional claim is a **belief**. "Gets
smarter" is exactly such a claim, and it will rot silently unless it is an
executable invariant. L9 exists to make it falsifiable.

## Detailed design

### L6 — Instant answer path

#### L6.1 Generation-keyed answer cache

Every certified answer already carries a provenance record with an index
generation stamp (RFC-0022 / RFC-0023). That stamp is, by construction, the
complete determinant of the answer: if the generation is unchanged, the answer
is unchanged. Therefore the answer is memoizable with a sound key.

```python
@dataclass(frozen=True)
class AnswerKey:
    """Sound cache key for a certified answer.

    ``generation`` is the index-generation stamp the answer was derived
    from. Two calls with equal keys are guaranteed to have equal answers
    because the generation is the sole input that can change the result;
    this is the same invariant ``SOURCE_GENERATION_MISMATCH`` already
    enforces per call.
    """

    tool: str
    action: str
    normalized_args: str    # canonical JSON, keys sorted, project-relative paths
    generation: str         # source-tree state, e.g. "idxsrc-v3:..."
    producer_version: str   # action_version + schema version + resolver-rule digest
    extra_inputs: str       # digest of declared non-source inputs (config, constraints)


def lookup(key: AnswerKey) -> CachedAnswer | None:
    """Return a cached answer, or ``None``.

    A cached answer is returned ONLY when its ``generation`` equals the
    live generation at call time. A generation bump evicts the whole
    cache; there is no partial invalidation, because partial
    invalidation cannot be proved sound against unresolved edges.
    """
```

The key deliberately has **three** independent components, not one. The
`generation` alone is not sufficient: the same source tree can produce a
different answer after a TSA upgrade, an `action_version` bump, a resolver-rule
change, or an edit to `architectural-constraints.yml`. A key that omits those
would replay a stale verdict under an old schema after an upgrade — the cache
would be silently serving the previous release's opinion.

Rules (all fail-closed):

1. **Read-only actions only.** An action is cacheable only if it is registered
   in an explicit `CACHEABLE_ACTIONS` allowlist, and an action may only enter
   that allowlist if it performs no filesystem write, no index mutation, no
   lease acquisition, and no ledger append. Index-lifecycle, doc-sync,
   snapshot-acquire, and `record_outcome` routes are structurally excluded. A
   contract test asserts the allowlist is a subset of the actions a
   side-effect audit marks pure — the allowlist may never be edited by hand
   alone. (Without this, a cache hit would return the previous answer *without
   performing the requested side effect*.)
2. **Only certified answers are cached.** An answer whose freshness is
   `stale`, `missing`, or `unknown` is never stored.
3. **Whole-cache eviction on any key-component bump.** No partial invalidation.
   Partial invalidation would require proving which answers a file change can
   affect — which is exactly the unresolved-edge problem, so it cannot be
   proved sound.
4. **Bounded**: `ANSWER_CACHE_BUDGET_MB` (default 128 MiB), LRU eviction,
   mirroring the RFC-0022 P0.1 registry's boundedness style.
5. **A cache hit is visible.** The response carries
   `provenance.served_from = "cache" | "computed"` and all key components. An
   agent must always be able to tell. A cache that lies about freshness is
   worse than no cache.

**Completion criterion (measurable, exact pins — no `>=` bounds):** on the
dogfood corpus, a repeat `edit action=safe` on an unchanged generation is served
from cache, and `tests/benchmarks/claims/test_answer_cache_invariants.py` pins
the *relationship* `p95(repeat) < p95(first)` plus an exact pin on the recorded
`served_from` value. Absolute millisecond ceilings are NOT asserted (they are
machine-dependent); the relationship and the provenance value are.

**Clarification (added when L6.1 landed — two premises above needed correcting):**

1. *"Every certified answer already carries a provenance record with an index
   generation stamp"* **does not hold on Windows.** The RFC-0022 oracle
   (`index_source_snapshot.capture_current_source_snapshot`, which mints
   `idxsrc-v3:`) short-circuits to `SOURCE_SCOPE_UNSUPPORTED` unless
   `os.name == "posix"` and `/dev/fd` exists; `source_oracle._supports_nofollow`
   likewise gates on `os.name != "nt"`. So on the platform the RFC-0025 L5
   baseline was measured on, the stamp is structurally uncomputable, and keying
   the cache off it would mean the cache never engages there. The implementation
   therefore keys off `cache.fingerprint.compute_source_tree_digest` — a per-file
   digest of `(relative path, mtime_ns, size)` over all 30 supported extensions,
   plus a content hash for the 16 most-recently-modified files, with the
   canonical project root folded in (`AnswerKey` has no `project_root` field, so
   two projects in one process could otherwise collide). Cost ~30 ms at 2,382
   files, scaling linearly; limits on `answer_cache_policy.current_generation`.

   **It is deliberately NOT `compute_graph_fingerprint`.** That
   `(file_count, max_mtime_ns)` pair is sound for invalidating a graph rebuilt
   from content but not as an answer key. The first implementation used it and
   was wrong in four ways, all found by adversarial review with executed
   evidence: a plain `os.rename` changes neither component, so a cached
   `edit action=safe` reported `verdict=CAUTION, downstream_count=1` for a path
   that no longer existed — where the live code raises `File not found`, i.e. a
   normal mid-refactor `git mv` turned a hard error into a false SAFE-ish
   verdict; `GRAPH_SOURCE_EXTS` covers only 19 of 30 extensions, so for
   `.cs .kt .lua .php .rb .scala .swift .swiftinterface .sh .bash .zsh` the
   stamp was the *constant* `0:0` and nothing could ever invalidate; an
   mtime-preserving replacement (`tar -x`, `cp -p`, `rsync --times`) was
   invisible; and a single file with a future mtime pinned the maximum ahead of
   the wall clock, blinding the entire tree until real time caught up. The
   defence that the cache was "no weaker than the graph caches whose answers it
   memoises" was **false as stated** — the target-file existence check is not
   inside any graph cache; it ran live on every call before this change.

   Timestamps also lack the resolution their units imply: measured on Windows, a
   same-size rewrite (`x = 1` -> `x = 2`) left `st_mtime_ns` byte-identical in
   **15 of 20** trials. Hence the content hash, and hence its selection by
   *rank* rather than by a clock window — a window makes the digest depend on
   `now`, so an unchanged tree digests differently as files age out of it and the
   cache takes a spurious miss (observed once as a 4.8 s recompute inside a warm
   reservoir that should have been all hits).
2. **Rule 2 needs a second dimension.** "Freshness `stale`/`missing`/`unknown`"
   is not the only way an answer can be uncertified: `edit action=safe` with
   `access_mode=read_existing` returns RFC-0022 P0.4 `access_state="unknown"` /
   `READ_EXISTING_AUTHORITY_UNCERTIFIED` wherever the oracle above cannot run,
   with no `freshness` field at all. `is_certified` refuses non-certified
   `access_state` as well, or a one-off "I could not certify this" would be
   replayed as a persistent verdict.
3. Admission to `CACHEABLE_ACTIONS` also requires that the route's cost dominate
   the generation stamp. `structure action=outline` is audited pure but runs at
   ~3 ms warm, so caching it would make it slower; it is excluded.
4. **Only *global* components may take part in whole-cache eviction.** The key's
   `producer_version` is route-scoped (it carries the route's `action_version`),
   and putting it in the eviction prelude made `edit action=safe` and
   `health action=file` evict each other on every switch — so the two
   allowlisted routes could never be resident together and the hit rate was
   **0% in the workflow this project's own skills prescribe per edit**
   (`.claude/skills/tsa-edit-safety/SKILL.md:16`,
   `tsa-edit-then-verify/SKILL.md:6`), with every call additionally paying the
   generation stamp for nothing: a net regression. `producer_version` is now
   encoded `"<global>:pvr1:<route>"` and only the global half is in the prelude.
5. **The completion criterion above is insufficient on its own, because the
   harness that measures it cannot see this class of bug.**
   `scripts/measure_self_health_baseline.py` drives `for route: for repeat:`, so
   all repeats of a route are grouped and any per-route cache state is constant
   inside a measurement block. Finding 4 therefore produced a 0% real-workflow
   hit rate while the harness reported a 62x speedup. The harness now also
   drives the prescribed pair **alternating** and records `served_from` per call
   (`interleaved_workflow` in the artifact), with a `CACHE_NOT_SERVING` verdict
   when a repeat at an unchanged generation is not a hit. Judge L6.1 on those
   rows. `p95(repeat) < p95(first)` is likewise not a fence — it passed at 1.01x
   while nothing was being served — so the benchmark ratchets the *ratio*.

#### L6.2 Declared query cost

Before running an expensive route, a tool declares what it will cost, so a
budget-bound agent can choose:

```python
@dataclass(frozen=True)
class QueryCost:
    tier: Literal["cached", "warm", "cold", "index_build"]
    estimated_ms: int | None      # None when genuinely unknown — never guessed
    requires_index_build: bool
    cheaper_alternative: str | None  # e.g. "nav action=context (1-hop, warm)"
```

`estimated_ms` is derived from the L9 ledger's *observed* p50 for that
`(tool, action, tier)` on **this** project, and is `None` until at least one
observation exists. It is never a hardcoded guess.

#### L6.3 Stable cross-turn identities

Every returned symbol, edge, and finding carries a stable id derived from the
RFC-0023 identity scheme. An agent in turn N+1 references the id instead of
re-describing the symbol. This is a token-cost reduction, and it is a
*correctness* improvement: re-description is where an agent silently
substitutes a different symbol.

**The short form is a display abbreviation, never the identity.** A naive
6-hex-digit id is 24 bits; the birthday bound puts a 50% collision probability
at roughly **4,800 symbols**, so on any repository at the RFC-0025 target scale
(100k symbols) collisions are effectively certain, and an agent resolving
`sym:7f3a2c` in a later turn would silently get the wrong symbol. The rule
instead follows git's abbreviated-hash discipline:

- the **canonical id is the full RFC-0023 identity** and is always present in
  the response;
- the abbreviation is lengthened until it is unique **within the emitting
  project index**, never merely within the response payload;
- a minimum width is enforced, and resolution of an abbreviation that has since
  become ambiguous fails closed with `SYMBOL_ID_AMBIGUOUS` listing the
  candidates — it never silently picks one;
- a contract test asserts abbreviation-uniqueness on the largest fixture corpus.

### L7 — Comprehension surfaces

All three derive from facts TSA already computes. **No LLM client is added to
this package** — output is deterministic and reproducible.

| surface | derived from | answers |
|---|---|---|
| `project action=card` | `get_project_summary_tool.py` (wire the existing tool) | "what is this project?" |
| `project action=tour` | centrality (`knowledge_graph/builder.py::_annotate_centrality`) + entry points (`codegraph_overview_tool.py:203`) | "in what order do I read this?" |
| `project action=start_here` | health + centrality + test coverage | "what can I safely change first?" |

`project action=tour` emits a deterministic ordered reading path: graph entry
points, then hub modules descending by centrality, then leaf utilities — each
with its file, its one-line role, and its immediate dependencies. Determinism is
a contract: the same generation yields a byte-identical tour.

`project action=start_here` is the contributor/new-hire surface. A change is
*easy* when it is **low-centrality** (few dependents), **well-tested** (an
exercising test exists per RFC-0025 L2's causal envelope), and
**low-complexity**. All three signals exist today; the project-health backlog
currently ranks by rot, which is the opposite ordering — a newcomer sent to the
rottenest file is being sent to the hardest one.

```python
def start_here_score(f: FileFacts) -> float:
    """Rank files by *ease of a safe first change*, not by rot.

    Deliberately the inverse ranking of the health backlog: a newcomer
    needs a file whose blast radius is small and whose behavior is
    pinned by tests. Files with no exercising test are excluded
    entirely rather than ranked low — an unverifiable first change is
    not a good first change.
    """
```

### L8 — Judgment surfaces

1. **Register the minimal-edit-set engine, preview-only.**
   `codegraph_refactor_tool` + `rename_symbol` already compute a true minimal
   rename edit set with 15 passing tests. Expose as `edit action=plan_rename`
   (MCP) / `--plan-rename` (CLI).

   The underlying tool supports **both preview and apply** modes. `plan_rename`
   names a planning operation and users will reasonably assume it cannot write.
   Therefore the binding MUST pin `mode="preview"` internally and **reject**
   any apply-like argument with a stable error rather than forwarding it — the
   mode is not a caller-supplied parameter at this surface at all. A contract
   test asserts that no filesystem write occurs on any `plan_rename` input,
   including adversarial ones that attempt to smuggle an apply flag through.
   Applying a rename stays on the existing write-intent surface.
2. **Implement the refactor queue in code.** `(1 - health) * log(1 + churn) *
   dead_ratio` currently exists only in a markdown skill. Move it into
   `tree_sitter_analyzer/` with exact-value tests. A formula that lives only in
   a prompt is a formula with no regression protection.
3. **Fix the two wrong-signal verdicts.**
   `modification_guard_tool.py:485` ranks symbol-level edit risk on **ripgrep
   occurrence counts** while the AST caller count is fetched at `:484` and left
   unused; `test_gap_analyzer.py:652` (`who_should_test`) uses basename matching
   while the graph-correct `test_map` (`nav_facade.py:466`) exists. Both are
   heuristic answers presented with an authoritative label. Switch both to the
   resolved-graph signal, and where the graph says `unknown`, return `unknown`
   rather than falling back to the heuristic silently.
4. **Design smells beyond the current set**: cohesion (LCOM), cross-file
   fan-in hubs, and shotgun-surgery (one logical change touching N modules,
   mined from L9's observed co-change). Cyclic dependencies are already
   *detected* but not *enforceable* — `constraints/parser.py:108` supports only
   `forbid`; add an `acyclic` constraint kind so a detected cycle can fail a
   gate rather than merely be reported.

### L9 — The calibration ledger (core contribution)

This is the layer that makes "gets smarter" a measurable fact.

#### L9.1 Predictions are recorded

Every prediction TSA emits gets a stable `prediction_id` and a durable row:

```python
@dataclass(frozen=True)
class Prediction:
    prediction_id: str            # stable, content-derived
    kind: Literal["blast_radius", "exercising_tests", "risk_verdict"]
    subject: str                  # symbol or file identity
    generation: str
    predicted: frozenset[str]     # predicted files / tests
    verdict: str | None           # for risk_verdict
    created_at_ns: int
```

#### L9.2 Outcomes are observed

When the agent runs the verification command TSA itself emitted, TSA ingests the
result and records what *actually* happened:

```python
@dataclass(frozen=True)
class Outcome:
    prediction_id: str
    actually_changed: frozenset[str]    # from the real diff
    tests_executed: frozenset[str]      # every test the runner actually ran
    tests_failed: frozenset[str]        # subset of tests_executed that failed
    verification_passed: bool           # did the emitted verification command pass
    escaped_allowed_paths: frozenset[str]  # writes outside the declared allowlist
    observed_at_ns: int
```

Ingestion is explicit (`index action=record_outcome`), never scraped. An outcome
with no matching prediction is rejected, not guessed at.

**Why `tests_executed` and not only failures.** The actual set for
`kind="exercising_tests"` is the set of tests that genuinely exercise the
symbol — which is what *ran and was relevant*, not what happened to break. A
successful verification has an empty failure set even when the prediction was
exactly right, so scoring against failures alone would make recall undefined on
every green run and would score correct predictions as false positives. The
comparison set is `tests_executed`; `tests_failed` is retained because a
predicted test that *failed* is the strongest possible confirmation and is
reported separately.

**Why the two extra fields.** `kind="risk_verdict"` predicts a safety judgment,
and a judgment needs an observed judgment to score against. The observed
outcome for a risk verdict is derived, by a table pinned in this RFC, from
`verification_passed` and `escaped_allowed_paths`:

| observed | condition |
|---|---|
| `benign` | verification passed and nothing escaped the allowed paths |
| `harmful` | verification failed, or a write escaped the allowed paths |
| `indeterminate` | verification was not run, or the outcome is incomplete |

`indeterminate` outcomes are excluded from the risk-verdict denominator and
counted separately, so an unrun verification can never be laundered into either
a good or a bad score.

#### L9.3 Calibration is computed and published

```
precision = |predicted AND actual| / |predicted|
recall    = |predicted AND actual| / |actual|
```

per `kind`, per project. Surfaced by `--self-health` (RFC-0025 L5) and pinned in
CI on the dogfood corpus. **Recall is the honesty metric**: a missed dependent is
a wrong edit; a spurious one is only wasted tokens. Recall regressions are a
release blocker; precision regressions are not.

**Empty-set semantics are pinned here, not left to the implementation.** Both
formulas have a zero-denominator case, and a metric that a release gate depends
on may not be allowed to emit `NaN` or to differ between implementations:

| case | precision | recall | counted in the aggregate? |
|---|---|---|---|
| `predicted` empty, `actual` empty | `1.0` | `1.0` | **no** — recorded as `trivial` |
| `predicted` empty, `actual` non-empty | `None` | `0.0` | yes (a total miss) |
| `predicted` non-empty, `actual` empty | `0.0` | `None` | yes (a total false alarm) |
| both non-empty | as above | as above | yes |

`None` means *undefined for this observation* and is excluded from that metric's
aggregate while still being counted in the observation total, so the aggregate
can never be inflated by dropping inconvenient rows. `trivial` observations
(nothing predicted, nothing happened) are reported with their own count so that
a ledger dominated by no-op changes is visibly distinguishable from one with
real signal — otherwise a project with no activity would show a perfect score.

#### L9.4 What learning may and may not do — the soundness fence

**LOCKED by this RFC. Any future proposal to relax it supersedes this RFC.**

Learned signal may:

- **re-rank** results that resolved evidence already admits;
- **widen** a candidate set with entries explicitly labelled
  `evidence: "observed_cochange"` and `confidence: <float>`;
- populate L6.2's `estimated_ms`.

Learned signal may **NOT**:

- narrow, soften, or override a fail-closed verdict;
- promote an unresolved edge to resolved;
- appear inside the RFC-0025 L2 certified `causal_envelope`, which admits
  resolved evidence only.

Rationale: the conservative-resolution moat is the product. A learning loop that
can talk the analyzer out of `unknown` destroys the exact property that makes it
trustworthy. Learning makes the *ordering* smarter; it never makes the *claims*
looser.

#### L9.5 Storage — the first non-regenerable artifact

The ledger is the first TSA artifact that is **not** a regenerable cache.
Consequences that MUST be handled:

- `--clean-state` currently deletes `.ast-cache/` wholesale, including
  `decision_journal.db`. The ledger MUST survive it; `--clean-state` gets an
  explicit `--include-ledger` opt-in for deletion.
- Schema versioned with a migration plan (RFC-0020 SQLite substrate).
- The ledger records **identities and outcomes, never source text** — the same
  `TASK_TEXT_OMITTED` discipline RFC-0022 applies, with the same secret-canary
  tests.
- Gitignored by default. Sharing a ledger across a team is a **separate future
  RFC**; it raises provenance and trust questions this RFC does not answer.

### L10 — Semantic index (supersedes RFC-0016; gated on a re-pilot)

**RFC-0016 proposed embedding-backed semantic symbol search and was REJECTED on
measured evidence** (2026-06-13): an embedding pilot at deployment scale scored
2/5 on the conceptual-gap gate, after stemming (#606), demotion (#609) and
BM25-docstring (#621) were each measured first. Pilot report:
`.recon/rfc0016-pilot-step2-embeddings.md`; decision thread #517.

This RFC does not get to quietly reintroduce that design. Two things differ, and
only one of them is an argument:

- **Not an argument**: nothing in this RFC makes embeddings retrieve better.
  The measurement that killed RFC-0016 is about retrieval quality and it still
  stands.
- **The actual difference**: RFC-0016 positioned semantic search as a *retrieval
  surface* competing with BM25 on top-5 hit rate. L10 positions it as a
  **subordinate discovery aid** whose output can never be an answer by itself —
  it proposes candidates that resolved evidence must then confirm. A recall-ish
  aid that surfaces one extra true candidate has value even when its ranking
  loses to BM25, because the confirmation step removes the false ones.

That is a *hypothesis*, not a result. Under CLAUDE.md §11 it stays a belief
until measured, so:

> **L10 acceptance precondition (blocking).** Before any L10 implementation
> merges, re-run the RFC-0016 pilot harness, unchanged, plus one added
> measurement for the new positioning: *does adding subordinate similarity
> candidates to a resolved-evidence workflow increase the number of true
> candidates found, at an acceptable confirmation cost, versus BM25 alone?*
> If it does not, **L10 is rejected with the new data attached** and the rest of
> RFC-0027 ships without it. That outcome is explicitly acceptable and cheap —
> exactly the disposition RFC-0016 itself took.

RFC-0016's status changes to `superseded by RFC-0027` only if the re-pilot
passes; if it fails, RFC-0016 stays `rejected` and this section is struck.

The module named `semantic_search.py` is today a `collections.Counter`
term-count cosine over **identifier tokens only** — it never reads a body, and
two synonymous functions sharing no token score exactly 0. It is not semantic
search.

Proposal: a local embedding index (no network, optional dependency, model
digest pinned and recorded in provenance) over symbol signature + docstring +
body, exposed as `search action=similar`.

**Structural subordination (locked, same fence as L9.4):** every semantic hit
carries `evidence: "similarity"` and a `confidence` score. A similarity hit is
never admitted to the certified causal envelope, and can never be the sole basis
for a safety verdict. It is a *discovery* aid — it helps an agent find a
candidate, which resolved evidence must then confirm.

When the optional dependency is absent, `search action=similar` returns a
stable `SEMANTIC_INDEX_UNAVAILABLE`, never a silent lexical fallback labelled as
semantic.

## Three-Surface impact (CLI ↔ MCP parity)

| capability | CLI | MCP |
|---|---|---|
| project card | `--project-card` | `project action=card` |
| tour | `--tour` | `project action=tour` |
| start here | `--start-here` | `project action=start_here` |
| minimal rename set | `--plan-rename` | `edit action=plan_rename` |
| refactor queue | `--refactor-queue` | `health action=refactor_queue` |
| record outcome | `--record-outcome` | `index action=record_outcome` |
| calibration report | `--self-health` (extends RFC-0025 L5) | `health action=self` |
| semantic similar | `--similar` | `search action=similar` |

All 1:1. The only intentional asymmetry is the locked TOON-on-MCP /
JSON-on-CLI default (CLAUDE.md §1) — unchanged by this RFC. No new *facade* is
added: every action lands on an existing facade, so the RFC-0022
menu-experiment gate is not triggered.

## Drawbacks

1. **The ledger is durable state.** It can be stale, corrupt, or wrong. Mitigated
   by the L9.4 fence — it can only re-rank and widen, so a corrupt ledger
   degrades ordering, never correctness.
2. **The answer cache can serve a wrong answer if the generation stamp is ever
   wrong.** This moves generation-stamp correctness from "important" to
   "load-bearing". Mitigated by whole-cache eviction and by `served_from` being
   visible in every response.
3. **L10 adds an optional heavy dependency** (embedding model). Mitigated by
   optional-extra packaging and a fail-closed unavailable code.
4. **More public surface**, against the roadmap's own "stop adding surfaces"
   rule. Partially mitigated: three of the eight actions expose code that
   *already exists and is already tested* — this is net wiring, not net surface
   growth in implementation terms.
5. **Calibration numbers may be embarrassing.** They will show TSA's real recall
   on real repositories. This is intentional and is the point.

## Alternatives

- **A: LLM-generated onboarding prose.** Rejected — non-deterministic, adds a
  network dependency and a model cost to a local-first tool, and cannot be
  pinned in CI. L7 derives everything from graph facts instead.
- **B: Learn edges directly** (infer unresolved edges from co-change). Rejected —
  violates the conservative-resolution moat. Co-change is admitted only as a
  labelled, subordinate widening signal (L9.4).
- **C: Time-based cache expiry instead of generation-keyed.** Rejected — time is
  not a soundness argument. The generation stamp is.
- **D: Ship semantic search first** (it demos well). Rejected — a similarity
  layer over a 2.4 s reflex and an uncalibrated index makes the tool *feel*
  smarter without *being* smarter, which is the exact failure mode CLAUDE.md §11
  documents.

## Prior art

- **rust-analyzer / Salsa**: demand-driven incremental recomputation with
  explicit revision stamps. L6.1's generation key is the same idea, restricted
  to whole-cache eviction because TSA's dependency graph across *unresolved*
  edges is not sound enough for fine-grained invalidation. We diverge
  deliberately, and conservatively.
- **Sourcegraph / SCIP**: precise-vs-search-based indexing with an explicit
  precision label per result. L10's `evidence: "similarity"` label adopts this;
  we go further by *structurally forbidding* the imprecise class from the
  certified envelope rather than merely labelling it.
- **Google Tricorder ("no false positives" doctrine)**: developers abandon an
  analyzer above roughly a 10% false-positive rate. L9's published
  precision/recall is the instrument that makes this measurable per project
  rather than assumed.
- **Weather-forecast calibration (Brier score)**: a forecaster is judged by
  scoring observed outcomes against stated probabilities, not by confidence.
  L9 applies the identical discipline to change-impact prediction. This is the
  part of the design with no equivalent in current code-intelligence tooling.

## Test plan (RED-first)

Unit:

1. `AnswerKey` equality/inequality across generation bumps (exact assertions).
2. Cache returns `None` on generation mismatch — RED before L6.1 exists.
3. Non-certified answers are never stored.
4. `served_from` is exactly `"cache"` on the second identical call.
5. `start_here_score` excludes files with zero exercising tests (exact count).
6. `tour` output is byte-identical across two runs at the same generation.
7. Ledger rejects an `Outcome` with an unknown `prediction_id` (exact error code).
8. Precision/recall computed on a fixture with hand-checked exact values.
9. **Soundness fence (the critical test):** a learned co-change signal with
   confidence 1.0 does NOT change a fail-closed verdict and does NOT appear in
   `causal_envelope`. This test must exist before any learning code is written.
10. `search action=similar` returns exactly `SEMANTIC_INDEX_UNAVAILABLE` when
    the optional dependency is absent.
11. A `producer_version` bump at an unchanged `generation` misses the cache
    (the upgrade-replay case).
12. A mutating action is absent from `CACHEABLE_ACTIONS`, and the allowlist is
    a subset of the audited side-effect-free set.
13. `plan_rename` performs zero filesystem writes on adversarial input that
    attempts to smuggle an apply flag.
14. An ambiguous id abbreviation returns exactly `SYMBOL_ID_AMBIGUOUS` with the
    candidate list, and never resolves to one of them.
15. `exercising_tests` recall on an all-green verification is scored against
    `tests_executed` and is exactly `1.0` when the prediction was exact
    (the case that would be undefined if scored against failures).
16. Each row of the risk-verdict observation table and each row of the
    empty-set table, with exact values.

Value invariants (CLAUDE.md §11 — measure the value, not only the shape):

11. `p95(repeat certified query) < p95(first)` — a *relationship*, not a ceiling.
12. Ledger recall on the dogfood corpus does not decrease between releases
    (ratchet, same style as the weak-assertion ratchet).

Parity: every row of the Three-Surface table has a CLI↔MCP parity test.

Dogfood: a scripted 10-edit refactor records predictions, ingests real outcomes,
and emits a calibration report with non-placeholder numbers.

## Acceptance criteria

- [x] L6.1 answer cache; `served_from` visible; whole-cache eviction on any
      key-component bump; bounded and LRU
- [x] L6.1 key includes `producer_version` and `extra_inputs`; a TSA/action
      version bump at an unchanged source generation misses the cache
- [x] L6.1 `CACHEABLE_ACTIONS` allowlist exists and a contract test asserts it
      is a subset of the side-effect-free actions
- [x] L6.1 benchmark ratchets the repeat-vs-first *ratio* (no absolute ceiling);
      a bare `p95(repeat) < p95(first)` is not a fence — it passed at 1.01x
- [x] L6.1 the generation stamp sees a rename, a delete, an mtime-preserving
      replacement, a future mtime, a same-size edit inside one filesystem tick,
      and all 30 supported extensions; it fails closed when it can see nothing
- [x] L6.1 whole-cache eviction keys on *global* components only, so the
      allowlisted routes do not evict each other
- [x] L6.1 the harness drives the prescribed route pair **interleaved** and
      records `served_from` per call, so a 0% real-workflow hit rate cannot hide
      behind a grouped-repeat speedup
- [ ] L6.2 `QueryCost` returned by the three most expensive routes;
      `estimated_ms` is `None` until observed
- [ ] L6.3 canonical full id always present; abbreviation unique within the
      project index; `SYMBOL_ID_AMBIGUOUS` fail-closed on an ambiguous
      abbreviation; uniqueness contract test on the largest fixture corpus
- [x] L7 `project action=card` wired; the orphan-pinning assertion in
      `tests/unit/cli/test_install_skills.py:571` is corrected, not preserved
- [ ] L7 `tour` deterministic (byte-identical at equal generation)
- [ ] L7 `start_here` excludes untested files
- [x] L8 `edit action=plan_rename` registered on both surfaces, pinned to
      preview; apply-like arguments rejected; contract test proves zero
      filesystem writes on adversarial input
- [x] L8 refactor-queue formula in code with exact-value tests
      (`tree_sitter_analyzer/refactor_queue.py`)
- [ ] L8 `modification_guard` and `who_should_test` use the resolved-graph
      signal; `unknown` where the graph is silent
- [ ] L8 `acyclic` constraint kind
- [ ] L9 prediction + outcome schema, versioned, with migration
- [ ] L9 outcome records `tests_executed` (not only `tests_failed`);
      `exercising_tests` recall is scored against the executed set
- [ ] L9 risk-verdict observed outcome derived by the pinned table;
      `indeterminate` excluded from the denominator and counted separately
- [ ] L9 empty-set semantics implemented exactly as the pinned table; `trivial`
      observations reported with their own count and excluded from aggregates
- [ ] L9 ledger survives `--clean-state`; deletion requires `--include-ledger`
- [ ] L9 precision/recall in `--self-health` with exact pins on the fixture
- [ ] L9.4 soundness-fence test green **before** any learning code merges
- [ ] L9 recall ratchet wired into CI
- [ ] **L10 re-pilot passes (BLOCKING).** RFC-0016's harness re-run unchanged,
      plus the subordinate-discovery measurement. If it fails, L10 is struck,
      RFC-0016 stays `rejected`, and the rest of RFC-0027 ships without it
- [ ] L10 embedding index optional; `SEMANTIC_INDEX_UNAVAILABLE` fail-closed;
      model digest in provenance
- [ ] L10 similarity hits structurally excluded from `causal_envelope`
      (contract test)
- [ ] CLI↔MCP parity test green for all eight actions
- [ ] Docs/CODEMAPS updated

## What this RFC does NOT do (deferred)

- **No new MCP facade** — every action lands on an existing facade, so the
  RFC-0022 menu-experiment gate is untouched.
- **No cross-machine or cross-team ledger sharing.** Local only. Sharing raises
  provenance and trust questions that need their own RFC.
- **No LLM client in the package.** L7 output is derived and deterministic.
- **No change to the RFC-0025 sensing layers.** L1–L5 remain RFC-0025's design.
  L6 depends on L1 for the generation stamp but does not specify it.
- **No public performance claim.** Every number here is a dogfood measurement at
  E0. Public wording remains bound by the RFC-0021 evidence ladder and the claim
  registry.
- **No modification to the locked TOON-default decision.**

## Open questions

1. Should the answer cache be process-local or persisted to `.ast-cache/`?
   Process-local is trivially sound; persisted survives the CLI's
   per-invocation cost, which is where the 28–35 s measurement hurts most.
   **Proposal: persisted, keyed by generation, since the generation stamp
   already makes cross-process reuse sound.**
2. Should `record_outcome` be pushed by the agent, or should TSA observe the
   test run directly? Pushing is simpler and needs no runner integration;
   observing gets far higher ingestion rates. **Proposal: push first, observe
   later behind a separate RFC.**
3. Which embedding model, and is a pinned local ONNX model acceptable against
   the local-first constraint? **Proposal: yes, pinned digest, optional extra.**
4. Does the calibration ledger belong in the VCSR denominator (RFC-0026), or is
   it strictly a supporting signal? **Proposal: supporting signal — VCSR stays
   the single north star, per the roadmap's "no weighted score may hide a
   regression" rule.**
