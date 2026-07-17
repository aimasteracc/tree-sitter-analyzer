# RFC-0021: Real-World Competitive Benchmark

- **Status**: draft
- **Author(s)**: project maintainers
- **Created**: 2026-07-17
- **Last updated**: 2026-07-17
- **Tracking issue**: TBD
- **Affected source paths**:
  - `benchmarks/codegraph_compare/`
  - `tests/unit/test_benchmark_harness.py`
  - `rfcs/ROADMAP-beyond-codegraph.md`

## Summary

Build a pre-registered, reproducible benchmark that compares TSA with CodeGraph
and a native-file-tools control on at least five pinned real repositories. The
benchmark measures answer quality, reliability, provider-reported cost, tokens,
turns, warm latency, logical-cold end-to-end latency, and incremental refresh.
It must fail closed when an arm is unavailable or a result set is incomplete.

The benchmark succeeds when it produces trustworthy evidence, regardless of
which tool wins. It may support only a bounded claim such as "best among the
tested tools and versions on benchmark vN"; it cannot establish an unqualified
"No.1" claim.

## Motivation

TSA has a measured cross-language correctness advantage, but its current cost
and agent-efficiency claims are not current enough to guide product decisions.
The existing `benchmarks/codegraph_compare/` harness is a useful base, with
seven pinned repositories and 21 questions, but it has validity blockers:

1. The cold matrix builds once per repository and arm, outside the trial timer;
   later questions and repeats use a warm index.
2. Index build failures can log and continue, and warm readiness can be inferred
   from a directory or non-empty database without checking provenance.
3. Results from different sessions share logical run IDs, while evaluation joins
   do not include session identity; old and new results can be mixed.
4. The analyzer does not prove exact matrix completeness before passing a run.
5. Execution order is fixed by repository and arm, which exposes the comparison
   to provider load, prompt cache, OS cache, and learning-order effects.
6. `IndexStats.file_count` has different meanings across adapters, so it cannot
   be used as a comparable coverage denominator.
7. There is no incremental protocol, fixed patch set, or stale-edge oracle.

Until those blockers are fixed, new cold, cost, or dominance claims are invalid.

## Detailed design

### Scope and comparison set

The confirmatory set uses the existing seven third-party repositories in
`repos.yaml`: VS Code, Excalidraw, Django, Tokio, OkHttp, Gin, and Alamofire.
They cover six primary language families and small, medium, and large projects.

The repository set is frozen before results are observed. A repository may not
be removed because an arm performs poorly or fails to prepare. Preparation
failure remains visible as `NOT_EVALUATED` or a product failure according to the
failure policy. TSA itself, toy projects, benchmark fixtures, and repositories
dominated by generated or vendored code are excluded from the confirmatory set.

For file-coverage comparisons, the denominator is the exact intersection of
source extensions supported by both indexed arms. Generated, vendored,
minified, ignored, and submodule paths are excluded by a versioned rule set.
`approx_files` remains descriptive only.

### Experiment manifest

Every phase consumes an immutable manifest created before model-backed work:

```yaml
benchmark_version: 1
experiment_id: "sha256:..."
benchmark_git_sha: "..."
config_hash: "sha256:..."
question_hash: "sha256:..."
oracle_hash: "sha256:..."
seed: 210021
agent_backend: codex
model: "exact-model-id"
timeout_seconds: 300
repeats: 5
repos: [vscode, excalidraw, django, tokio, okhttp, gin, alamofire]
arms: [native-only, codegraph-warm, tsa-warm]
primary_endpoints: [quality, reliability, total_tokens, num_turns]
```

The manifest also records exact repository SHAs, clean-tree fingerprints,
question IDs, expected cells, randomized schedule, tool/package/binary versions,
agent CLI version, Python/Node/uv versions, OS, CPU, and RAM. Any change to the
manifest creates a new experiment ID and cannot be appended to an old result set.

An append-only experiment registry records every manifest hash, first execution
time, status, and outcome. Once any model or tool result exists, an experiment
cannot be deleted or hidden; abandoned, failed, invalid, and unfavorable runs
appear in the final report appendix. Confirmatory endpoints, thresholds, and
reduced subsets are frozen before any result on that corpus is visible. Otherwise,
pilot and confirmatory runs must use non-overlapping holdouts. A post-result
question or oracle change creates an exploratory experiment on a new holdout and
does not replace the disclosed original.

Artifacts live under an experiment-specific directory. Raw records, transcripts,
manifests, index statistics, evaluations, reports, and checksums are immutable and
must not be overwritten by retries.

### Data structures

Logical cell identity is `(experiment_id, run_id)`. Immutable attempt identity is
`(experiment_id, session_id, run_id, attempt_no)`. `EvalRecord` uses the full
attempt identity; joining on `run_id` alone is forbidden. A report declares one
primary session plus its manifest-linked retry sessions. Any other session under
the experiment is invalid and cannot replace a failed result.

`RunRecord` adds:

- experiment/config/question/oracle hashes;
- schedule position and random seed;
- `status`: `SUCCESS`, `PRODUCT_FAILURE`, `INFRA_FAILURE`, `INVALID`, or
  `NOT_EVALUATED`;
- `retry_of` and retry number;
- exact repo, environment, model, agent, and tool provenance;
- `index_build_seconds`, `index_refresh_seconds`, and `answer_seconds`;
- `cold_end_to_end_seconds` and `incremental_to_answer_seconds`;
- provider-reported token/cost fields and whether each value is reported or
  estimated;
- policy-audit result and violations.

`IndexStats.file_count` is replaced by explicit, comparable fields:

```python
@dataclass(frozen=True)
class IndexStats:
    eligible_source_files: int
    indexed_source_files: int
    parse_error_files: int
    build_seconds: float
    index_size_bytes: int
    repo_fingerprint: str
    tool_fingerprint: str
    readiness_oracles_passed: tuple[str, ...]
```

The manifest freezes the exact eligible path set and hash. Each adapter records
exact indexed, explicitly excluded, and parse-error path sets and hashes. Setup
requires those three sets to be disjoint and their union to equal the eligible
set. The default parse-error allowance is exactly zero; any exception needs an
exact, pre-registered path allowlist. A known-answer query cannot substitute for
this completeness proof.

Incremental fixtures pin a deterministic patch per repository. Each patch covers
add, modify, delete, symbol rename, call-edge change, and import-edge change. Its
oracle contains exact new, changed, and absent symbols/edges, including an exact
stale-row and stale-edge count of zero.

### Setup-validation gate

Setup validation performs no model call and therefore consumes no agent/API
budget. It must prove, for every repository and indexed arm:

1. repository SHA and clean-tree fingerprint match the manifest;
2. exact tool version and executable fingerprint are recorded;
3. index deletion, build, and health checks return success;
4. eligible/indexed/excluded/error source sets satisfy the exact partition and
   pre-registered parse-error policy;
5. known-answer symbol and call queries return the pinned oracle;
6. a warm index fingerprint matches repo SHA, tool version, and configuration.

Any setup failure blocks all model-backed phases. An unavailable competitor is
reported as `NOT_EVALUATED`, makes the publishable comparison fail, consumes no
agent call, has zero tokens/cost, and is excluded from medians and dominance. It
is never treated as a TSA win. CodeGraph's reproducible
installation baseline is `@colbymchenry/codegraph` at a pinned version, with the
exact install and version commands captured in the manifest.

### Execution protocols

#### Smoke

One repository, one question, one repeat, all required arms. It verifies only
installation, isolation, transcript capture, and artifact integrity.

#### Pilot

One repository, all questions, all arms, at least four repeats. Pilot results are
exploratory and cannot support a product claim. They validate budgets, oracles,
evaluation blindness, and the failure policy before confirmatory spend.

#### Warm confirmatory

Build and validate each index once. Every trial starts a fresh agent session but
retains the validated index. A seeded blocked-random or Latin-square schedule
interleaves arms and prevents repeats of one arm from running as a contiguous
block. Each repository/question/arm cell has five pre-registered repeats. With
the current 21-question bank and three arms, benchmark v1 expects exactly 315
warm logical cells.

#### Logical-cold confirmatory

Each trial uses an isolated arm checkout. Timing starts before index removal and
ends after the answer. Index removal, rebuild, readiness checks, and answering are
all included in cold end-to-end time. Clone and dependency installation remain
outside the timer. Unless OS page caches are explicitly and symmetrically cleared,
the result is named **logical/process cold**, never physical-disk cold.

To control spend, cold uses one pre-registered representative question per
repository, with the seven-question set collectively covering all five existing
categories. Two indexed arms and five repeats produce exactly 70 cold logical
cells. Warm and cold results are never pooled.

Benchmark v1 freezes these cold questions: `gin-route-matching`,
`django-migration-detection`, `tokio-task-selection`, `vscode-lsp-diagnostics`,
`excalidraw-serialization`, `okhttp-interceptor-chain`, and
`alamofire-build-send-request`.

#### Incremental confirmatory

Each repository gains one pre-registered question named
`<repo>-incremental-change-impact` before any result is visible. Each repeat
starts from the pinned base SHA and a validated
base-index snapshot. The runner applies the fixed patch, times refresh, validates
exact symbol/edge oracles, asks that question, then discards the checkout and snapshot.
If a tool has no explicit refresh command, time includes its first query-triggered
refresh. Two indexed arms, seven repositories, and five repeats produce exactly
70 incremental logical cells. A full rebuild is measured separately as the baseline.

### Isolation and fairness

- Same backend, model ID, context limit, timeout, hardware class, and network
  policy within a paired comparison; observed turns are reported, not assumed capped.
- Same question text and public file-read/search capabilities; only the indexed
  capability differs by arm.
- Each arm gets a separate checkout and index namespace.
- Question/oracle content is hashed before execution; expected key points never
  enter the agent prompt.
- Codex transcript policy is mechanically audited because prompt instructions are
  not a hard tool allowlist. A forbidden tool call makes the trial `INVALID`.
- Every primary oracle is signed before execution by two reviewers using exact
  pinned file, symbol, line, and semantic facts. At least one signer is independent
  of the TSA implementation and question author. Oracles may not be generated
  from any tested tool's output. If an author sees any arm result before changing
  an oracle, that question leaves the confirmatory set.
- Answer evaluation is arm-blind and randomized. A deterministic verifier computes
  `citation_location_validity` from exact repository path, line, and symbol checks.
  Semantic `claim_support` is a separate arm-blind reviewer/judge score; it is not
  presented as deterministic. At least 20% receives independent blind audit;
  judge disagreement is reported and adjudicated, never averaged away.

### Metrics

Metrics remain separate; no weighted score may hide a correctness regression.

| Dimension | Primary measurements |
|---|---|
| Quality | correctness, completeness, supported citations, hallucination risk |
| Reliability | success, timeout, crash, empty-index, low-quality, invalid rates |
| Agent efficiency | provider tokens by class, billed cost, turns, tool calls, raw reads/searches, index calls |
| Latency | warm answer, index build, logical-cold end-to-end, incremental refresh, incremental-to-answer |
| Index | eligible/indexed/error files, completeness, known-answer recall, size |
| Incremental correctness | exact add/modify/delete oracle, stale rows/edges |

Provider-reported cost is authoritative when available. Estimated cost is labeled
as such and cannot be mixed with reported cost. Backends are analyzed separately.
Timeouts and product failures remain in the denominator and retain capped latency
and observed cost.

### Statistical analysis

The unit of comparison is a paired repository/question/repeat block. The report:

1. computes cell medians, then macro-averages by repository and category;
2. reports paired differences and ratios with repository-question cluster
   bootstrap 95% confidence intervals;
3. reports N, win/tie/loss, failure rate, and every repository/category result;
4. distinguishes pre-registered primary endpoints from exploratory metrics;
5. never selects the best repeat or silently removes failures.

Quality must first be non-inferior: for TSA-minus-competitor quality, the 95% CI
lower bound must be above `-0.10` on the 1-5 scale, deterministic
`citation_location_validity` must be at least 99%, and success must be at least
99%. Semantic `claim_support` remains part of blind quality review. Only then may
cost or latency decide. For the TSA/competitor cost or latency ratio, a practical
efficiency win requires the 95% CI upper bound to be at most `0.80`, in at least
four of five question categories and five of seven repositories. Any repository
quality drop greater than 0.25 rejects the win claim.

These thresholds are frozen in the manifest before confirmatory execution. A
benchmark is valid even when TSA fails them.

### Failure and retry policy

- Judge outage re-evaluates the same immutable answer once and never reruns the
  agent. Execution infrastructure failure retries every required arm in the paired
  block once; retain original attempts with `retry_of` links.
- Tool timeout, crash, empty index, or incorrect result in a healthy environment
  is a product failure: worst quality, timeout-capped latency, and observed cost.
- Dirty repo, wrong fingerprint, forbidden tool, missing/duplicate cell, missing
  evaluation, or malformed artifact invalidates the session.
- Competitor installation failure makes the comparison `NOT_EVALUATED` and stops
  public dominance claims.
- Exhausted retries stop the phase. Unlimited or selective retries are forbidden.

Before analysis, expected logical cells and canonical terminal cells must be
exactly equal. A canonical terminal cell is selected only by the pre-registered
retry rule and may have zero or one linked retry lineage; all attempts remain in
the reliability denominator. The analyzer
must reject mixed experiment IDs, config hashes, question hashes, model IDs, or
tool versions. A report cannot pass without all required arms and evaluations.

### Schema compatibility

New records use `benchmark_version: 1`. Historical v0 JSONL remains readable for
historical reports through an explicit legacy parser or conversion command, but
it is read-only and cannot pass the publishable-result gate because it lacks the
required manifest, attempt identity, and provenance. Pydantic models continue to
reject unknown fields within each declared schema version.

### Evidence and claim ladder

| Level | Evidence | Permitted claim |
|---|---|---|
| E0 | RFC or self-tests only | design claim only |
| E1 | reproducible install and smoke | setup works |
| E2 | complete pre-registered internal matrix | result on this machine/session |
| E3 | clean second machine plus independent blind review | reproduced result |
| E4 | public artifacts, current named competitors, third-party reproduction | bounded "best among tested tools" |

An unqualified "No.1" claim is never emitted. Before E4, findings are framed as
internal benchmark evidence. Every public claim names benchmark version, tools
and versions, date, repositories, model/backend, and evidence level.

### Budget discipline

Setup, unit tests, dry runs, and deterministic oracle validation are local and
must complete before model-backed execution. Smoke and pilot establish an exact
upper-bound estimate for remaining calls, tokens, and subscription usage. The
confirmatory phase starts only when that estimate fits the user-approved Codex
subscription allocation. No paid API or third-party spend is implied by a Codex
Max subscription; such spend requires separate explicit authorization.

### Output and reproducibility

One command validates artifacts and generates Markdown, CSV, and a checksum
manifest from raw records. The report includes all failures, invalid trials,
retries, provenance, exact commands, and the claim level. Regeneration must be
byte-stable except for explicitly separated generation timestamps.

### Implementation sequence

Implementation hardens the existing harness; it does not create a parallel
benchmark system.

1. **Slice A: integrity foundation** — versioned schema compatibility, experiment
   registry/manifest, attempt identity, CodeGraph preflight, fail-closed statuses,
   exact matrix/provenance gate, and smoke/warm-only support. No model-backed
   comparison may start before this slice lands.
2. **Slice B: warm confirmatory** — isolated checkouts, deterministic interleaved
   schedule, signed oracles, blind evaluation, and paired analysis.
3. **Slice C: logical cold** — per-trial delete/rebuild/readiness and end-to-end timing.
4. **Slice D: incremental** — fixed patches/questions, snapshot reset, refresh
   timing, and exact stale-data oracles.
5. **Slice E: statistical report and evidence** — confidence intervals, failure
   disclosure, claim-level output, complete evidence run, and E3 reproduction.

Each phase is independently reviewable and must leave the existing historical
artifacts readable. Compatibility defaults may read old records, but old records
cannot pass the publishable-result gate because they lack required provenance.

## Three-Surface impact (CLI ↔ MCP parity)

This RFC changes only the benchmark developer surface. It adds no TSA public CLI,
MCP action, or Python API, so CLI/MCP parity is not applicable. If implementation
later exposes benchmark behavior through a public TSA surface, that change needs
its own parity design and contract tests.

## Drawbacks

- Seven repositories, paired repeats, blind evaluation, and a second-machine
  reproduction take materially longer than a demo benchmark.
- Strict failure handling may produce `NOT_EVALUATED` rather than a headline.
- Logical-cold results do not isolate physical disk performance.
- Maintainer-authored questions can retain product bias even after blind review.
- Current competitors do not represent the whole code-intelligence market, so
  conclusions remain bounded.

## Alternatives

- **Keep the existing four-repeat harness** — cheaper, but cold timing, result
  isolation, and completeness defects make product conclusions unsafe.
- **Benchmark TSA only** — useful for regression tracking, but cannot support a
  competitive decision.
- **Publish the correctness moat without cost work** — honest but leaves the key
  adoption objection unresolved.
- **Use a single weighted leaderboard score** — concise, but rejected because it
  can hide correctness or reliability regressions behind cheaper output.

## Prior art

- Existing `benchmarks/codegraph_compare/` phases, schemas, and fairness rules.
- `GAUNTLET.md` for same-session correctness comparisons and explicit handling of
  a temporarily unavailable competitor lane.
- Paired benchmark design, blocked randomization, macro-averaging, and clustered
  bootstrap confidence intervals used in reproducible systems evaluation.

## Test plan (RED-first)

Extend `tests/unit/test_benchmark_harness.py`; T-1 forbids creating fragmented
benchmark test files for this existing subsystem. RED tests must prove exact behavior:

1. cold preparation occurs for every trial and build time is included in cold
   end-to-end time;
2. warm trials reuse only a fingerprint-matching ready index;
3. non-zero build, delete, health, or oracle failures fail closed;
4. source-file denominators have identical meaning across adapters;
5. a fixed seed produces an exact, interleaved schedule;
6. incremental repeats reset from the same base and exact index snapshot;
7. run/eval joins require full experiment, session, run, and attempt identity;
8. missing, duplicate, malformed, mixed-provenance, or unevaluated cells fail the
   matrix-completeness gate;
9. timeout and product-error records make the phase fail and remain in analysis;
10. judge input is arm-blind and transcript policy violations invalidate a trial;
11. report generation from a fixed artifact fixture is deterministic;
12. setup validation uses no agent backend and blocks later phases on failure;
13. the experiment registry rejects deletion, overwrite, and hidden historical
    outcomes, and reports abandoned, failed, invalid, and unfavorable runs;
14. post-result confirmatory mutation fails, and pilot/confirmatory holdouts are
    proven disjoint when they share a benchmark version;
15. missing oracle signatures, non-independent signers, or tested-tool-derived
    oracle provenance fail closed;
16. deterministic citation-location validity uses the exact declared denominator
    and cannot be overwritten by a judge score;
17. reports reject unlinked sessions, accept only the declared primary/retry
    lineage, and retain every attempt in the reliability denominator.

After focused tests, run TSA change-impact and its exact verification command.
Benchmark-only performance runs follow the repository benchmark exception in
`AGENTS.md`.

## Acceptance criteria

### Implementation completion

- [ ] Setup validation passes for every pinned repository and required indexed arm.
- [ ] Manifest records exact matrix, versions, fingerprints, hashes, seed, schedule, and thresholds.
- [ ] Append-only registry and holdout gates prevent selective experiment disclosure.
- [ ] Every primary oracle has two valid signatures, an independent signer, and non-tool provenance.
- [ ] Exact matrix-completeness and provenance gates reject partial or mixed runs.
- [ ] Reports accept only declared session lineage and retain all attempts in reliability metrics.
- [ ] Logical-cold rebuilds per trial and includes build time in end-to-end latency.
- [ ] Warm readiness is fingerprinted; index failures fail closed.
- [ ] Incremental protocol resets per repeat and has exact stale-data oracles.
- [ ] Confirmatory warm cells have at least five repeats; cold/incremental use the pre-registered reduced matrix.
- [ ] Analyzer reports paired 95% CIs, macro results, N, all failures, invalids, and retries.
- [ ] Citation-location validity is deterministic; semantic claim support remains blind-reviewed.
- [ ] Raw artifacts and a checksum manifest reproduce the report with one command.
- [ ] No public CLI/MCP surface changed; parity remains N/A.
- [ ] `rfcs/README.md` and the roadmap are updated with the benchmark status.

### Evidence milestones

- [ ] E2: the complete pre-registered primary matrix and all failures are reported.
- [ ] E3: a clean second-machine run reproduces the primary conclusion.
- [ ] E4: public artifacts and independent reproduction support only the bounded claim.
- [ ] Public wording obeys the claim ladder and names every tested version.

## What this RFC does NOT do (deferred)

- It does not itself run the paid/model-backed confirmatory matrix.
- It does not claim TSA wins or is No.1.
- It does not compare every commercial or closed-source code-intelligence tool.
- It does not define physical-disk-cold methodology across operating systems.
- It does not change TSA index, graph, CLI, MCP, or storage architecture.

## Open questions

1. Which independent machine and reviewer will provide the E3 reproduction?
2. Should E4 add a second current indexed competitor before any public headline?
3. Which independent reviewers will sign each primary oracle before execution?
