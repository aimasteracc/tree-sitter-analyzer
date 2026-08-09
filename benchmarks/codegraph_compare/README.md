# CodeGraph Comparison Benchmark


## NO1-003B production-canary operator runbook

> **Current decision: NO-GO for a real canary.** The repository can qualify the
> NO1-002C/002D trust chain, but it intentionally contains no production model
> dispatcher. `CanaryProtocol` rejects every non-fixture execution with
> `QUALIFICATION_SCAFFOLD_NOT_PRODUCTION_READY`. Do not bypass that stop, replace
> `execution_mode`, or call an agent adapter directly. A real run requires a
> separately reviewed operator-controlled dispatcher and external approvals.

### 1. Run the zero-cost offline rehearsal

This is the only executable canary operation currently authorized. It imports no
agent adapter, makes no network/provider request, uses an ephemeral
rehearsal-only key and spec, and emits E0 evidence only. The work root must not
exist, which makes accidental replay fail closed.

```bash
cd /path/to/tree-sitter-analyzer
WORK_PARENT="$(mktemp -d)"
WORK_ROOT="$WORK_PARENT/no1-003b-offline"
uv run python -m benchmarks.codegraph_compare.production_rehearsal \
  --work-root "$WORK_ROOT" | tee "$WORK_PARENT/receipt.json"
jq -e '
  .status == "PASS" and
  .execution_mode == "offline-rehearsal" and
  .artifact_count == 2 and
  .attestation_verified == true and
  .synthetic_judge_signature_verified == true and
  .independent_judge_available == false and
  .trust_qualification_status == "NOT_EVALUATED" and
  .trust_violations == ["INDEPENDENT_JUDGE_UNAVAILABLE"] and
  .trust_gate_would_allow_bound_fixture == false and
  .production_dispatch_allowed == false and
  .model_callbacks_invoked == 0 and
  .provider_requests == 0 and
  .input_tokens == 0 and .output_tokens == 0 and .cost_usd == 0 and
  .evidence_level == "E0" and .winner == null and
  .dominance_allowed == false and .publishable == false
' "$WORK_PARENT/receipt.json"
```

`synthetic_judge_signature_verified=true` proves only that the same-process
rehearsal record is canonically signed. It is deliberately not represented as an
independent judgment. `trust_qualification_status=NOT_EVALUATED` with
`INDEPENDENT_JUDGE_UNAVAILABLE` proves the production gate remains closed. The
ephemeral key, `offline-rehearsal-only` cell, `offline-fixture-no-model` model
identity, and `production_dispatch_allowed=false` prevent reuse as canary
evidence. Preserve the receipt for review, then securely remove the temporary
rehearsal key and artifacts according to local operator policy.

### 2. Verify the fail-closed boundary

```bash
uv run pytest -q \
  tests/unit/test_production_anchor.py \
  tests/unit/test_production_collector.py \
  tests/unit/test_production_trust.py \
  tests/unit/test_benchmark_harness.py
uv run python -m tree_sitter_analyzer --change-impact --format json
```

Stop immediately if either command fails, if the rehearsal reports any non-zero
usage/cost, or if any claim flag is enabled. Never “fix” rehearsal failure by
weakening attestation, budget, judge, immutability, transcript, matrix, or claim
checks.

### 3. Production readiness checklist (all items mandatory)

The Anchor Custodian, Budget Gateway, Evidence Collector, independent Judge,
and execution operator must record approval out of band. Before any future real
call, all of the following must be true:

1. The exact Gin commit, clean workspace fingerprint, prompt hash, MCP launch
   identities, exact model ID, nonce, expiry, one-cell request limit, token limit,
   and USD ceiling are frozen in `ProductionRunSpecV1`.
2. The anchor and trust store are operator-controlled regular files outside the
   checkout and evidence bundle, with no symlink component. No TOFU,
   bundle-provided key, environment inheritance, or self-signed replacement is
   allowed.
3. `SpendAttestation` binds the exact spec hash, nonce, expiry, and budget mode.
   Provider reservation is preferred. `client-process-kill` is only the recorded
   Codex CLI limitation; it still requires timeout/kill and post-run usage
   verification and never permits ceiling overrun.
4. The collector root is fresh and external. Every write is exclusive and the
   finalized ledger/artifacts are immutable. Checkout/runtime audits and cleanup
   must pass for each arm.
5. The Judge independently signs the exact evidence digest and spec hash. Any
   missing, stale, mismatched, non-`ACCEPT`, or unverifiable record is terminal
   `NOT_EVALUATED`/`INVALID`, never a retry opportunity or a TSA win.
6. The exact two indexed cells, order, one attempt each, receipt/tool arguments,
   oracle (`gin.go`, `Engine.ServeHTTP`, `method`), transcript policy, and
   cumulative USD ceiling remain unchanged. A failure stops the phase; selective
   retry is forbidden.
7. Output remains E0/internal: `winner=null`, `dominance_allowed=false`, and
   `publishable=false`. No No.1, dominance, production-readiness, E1+, or public
   benchmark claim is permitted.
8. A separately reviewed production dispatcher proves it consumes the qualified
   spec exactly once and atomically records reservation, usage, termination, and
   immutable evidence. **That dispatcher is not present today.**

### 4. Abort and escalation

Abort before spend on any missing approval, pre-existing artifact root, dirty or
mutated checkout, wrong binary/model/hash, expired spec, budget-mode mismatch,
open verification-to-use gap, judge/attestation failure, or unavailable arm.
After a call starts, kill at the frozen timeout/limit, retain all partial evidence,
terminalize the cell, and do not rerun it. Escalate the immutable receipt and
violation list to the maintainers; never delete, overwrite, relabel, or exclude
an unfavorable outcome.

## NO1-008A seven-repository setup qualification (implementation only)

`setup_qualification.py` is a model-free RFC-0021 **E0 evidence contract**
for the seven pinned repositories and two indexed arms. It validates canonical
POSIX paths using `openat`/`O_NOFOLLOW`, schema-v2 receipts, exact finite
resource observations, exact indexed/excluded/parse-error partitions, and full
oracle-spec/query/normalized-result bindings. Index and execution provenance
plus OS audit evidence require the pinned independent executor signature;
plan/evidence approval requires a different pinned human-approver signature.
Neither private key is available to a producer. It deliberately has no collector
adapter: `produce_strict_cell` fails `NOT_EVALUATED` until a harness-owned sandbox
executor exists. Plans must match the commits in `repos.yaml`, and both arms use
identical eligibility. The orchestrator invokes the exact ordered 14-cell plan
once per cell, then re-reads and strictly revalidates every immutable receipt and
digest immediately before sealing. It records all failures and can emit only
`E0/NOT_EVALUATED`.
There is no reachable `QUALIFIED`, publish, winner, dominance, or unlock state.

This is **not an operator command to run qualification yet**. NO1-003C, an
independently reviewed oracle set, a real OS-level network/process sandbox, and
an executor capable of independently capturing raw bytes remain gates. Do not
run the real matrix, mark NO1-008A complete, start 008B, or describe these setup
artifacts as E2/No.1/winner evidence. A failed attempt is followed by a new
experiment directory, never overwrite or selective retry. Acquisition/cache
preparation remains separate from the offline qualification phase.

## Quantitative README claim release gate

The checked-in `claim_registry.json` is the sole source for public benchmark,
performance, and competitive numbers in the main README. Registry records do
not accept author-written claim text. Only a verified E4 record with exact TSA
and competitor names/versions, metric, unit, numerator, denominator,
benchmark version, measurement date, corpus name/revision, repository commit,
and a matching artifact SHA-256 can generate wording. E4 additionally requires a
public benchmark manifest and an independent-third-party reproduction manifest
whose exact digest is admitted by the code-owned authority trust root; copying
registry values into an artifact cannot grant E4. The generated wording includes
the repository commit directly; artifact path/status remain validation metadata.

Blocked, unverified, and E0–E3 records always produce
`emittable_wording=[]`, regardless of phrases such as “superior”, “2x”,
“dominates”, or “lower latency”; there is no victory-word denylist. All three public README markers and whole-document quantitative-marketing scans are enforced
in `tests/unit/test_claim_registry.py`. Fenced command examples and Python/package versions are outside this claim
contract. Language-support counts and registry-derived MCP/CLI surface counts
are controlled by their independent generator/governance contracts and are
also explicitly excluded. Current registry status is E0/blocked,
so the generated main-README claim section is intentionally empty.

Validate the registry and contracts with:

```bash
uv run python -m benchmarks.codegraph_compare.claim_registry \
  benchmarks/codegraph_compare/claim_registry.json
uv run pytest tests/unit/test_claim_registry.py -q
```

The registry command exits non-zero while any record is blocked; that is the
expected release posture until a real E4 artifact exists.

## NO1-001A Gin Smoke qualification

The model-free qualification adapter proves that the fixed native,
tree-sitter-analyzer, and CodeGraph cells can be isolated and replayed. It
does not run an index, backend, or model and can only emit E0 evidence:

```bash
RECEIPT=$(python -m benchmarks.codegraph_compare.gin_smoke create /tmp/gin-smoke \
  --benchmark-git-sha "$(git rev-parse HEAD)" \
  --repository-path /fixture/gin \
  --repository-commit 0123456789abcdef0123456789abcdef01234567 \
  --repository-fingerprint 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --question "Where is the Gin router assembled?" \
  --model fixture-model --timeout-seconds 60)
DIGEST=$(printf '%s' "$RECEIPT" | jq -r .bundle_digest)
python -m benchmarks.codegraph_compare.gin_smoke validate /tmp/gin-smoke \
  --expected-git-sha "$(git rev-parse HEAD)" --expected-bundle-digest "$DIGEST"
python -m benchmarks.codegraph_compare.gin_smoke replay \
  /tmp/gin-smoke /tmp/gin-smoke-replay \
  --expected-git-sha "$(git rev-parse HEAD)" --expected-bundle-digest "$DIGEST"
```

Validation requires a trusted Git SHA supplied outside the bundle. Any
checksum change, missing or mixed cell, namespace collision, tool leakage,
oracle material, selective retry, or claim above E0 invalidates the bundle.

Measures answer quality, token cost, and latency across three code-intelligence approaches on real open-source repositories:

| Arm | Tool(s) | Index |
|-----|---------|-------|
| `native-only` | grep + file reads | none |
| `codegraph-warm` | CodeGraph MCP | pre-built |
| `codegraph-cold` | CodeGraph MCP | built at query time |
| `tsa-warm` | tree-sitter-analyzer | pre-built |
| `tsa-cold` | tree-sitter-analyzer | built at query time |

---

## Directory Structure

```
benchmarks/codegraph_compare/
├── README.md           — this file
├── schemas.py          — Pydantic v2 dataclasses (RunRecord, EvalRecord, …)
├── repos.yaml          — 7 pinned repositories
├── arms.yaml           — 5 treatment arms
├── adapters/           — one adapter module per tool
├── prompts/            — question bank (QuestionSpec YAML files per repo)
├── repo_prep.py        — clone + pin + index build script
└── results/            — run records, eval records, transcripts
```

---

## Quick Start

```bash
# 1. Prepare repos (clone at pinned SHA, optionally pre-build indexes)
uv run python benchmarks/codegraph_compare/run.py prepare --all

# 2. Run a Codex-backed smoke without spending model quota
uv run python benchmarks/codegraph_compare/run.py phase smoke \
    --agent-backend codex \
    --dry-run

# 3. Run a real Codex-backed smoke
uv run python benchmarks/codegraph_compare/run.py run-matrix \
    --repos gin \
    --arms native-only,tsa-warm,codegraph-warm \
    --question-limit 1 \
    --repeats 1 \
    --agent-backend codex \
    --model <exact-model-id> \
    --timeout-seconds 1200 \
    --manifest <frozen-manifest.json> \
    --index-evidence <validated-index-evidence.json>

# 4. Evaluate answers (LLM judge, writes EvalRecord JSONL)
uv run python benchmarks/codegraph_compare/evaluate.py \
    --runs results/runs.jsonl --out results/evals.jsonl

# 5. Print summary table
uv run python benchmarks/codegraph_compare/analyze.py \
    --runs results/runs.jsonl --evals results/evals.jsonl \
    --fail-on-gate
```

Use `--agent-backend claude` to reproduce the original Claude Code arm, or
`--agent-backend codex` to spend Codex quota through `codex exec --json`.
Run IDs include the backend name so Claude and Codex results never overwrite
each other.

Manifest-backed execution first consumes the strict setup evidence without a
model call, then follows `expected_cells` in manifest order. Each terminal
attempt is written under `results/experiments/<manifest-hash>/runs.jsonl` as a
V1 record and receives a mechanical transcript-policy audit. The older
unmanifested `phase smoke` path remains available only for historical harness
compatibility and cannot establish RFC-0021 evidence.

Codex records include `cached_input_tokens` and `reasoning_output_tokens` when
the CLI reports them. These are stored separately because Codex reports them as
detail counters already covered by the top-level input/output totals, while
Claude reports cache counters outside `input_tokens`.

---

## Fairness Rules

These rules are enforced by the harness. Violating any of them invalidates a run.

1. **Pinned commits** — all repos use a fixed SHA from `repos.yaml`; no `HEAD`-tracking.
2. **Same model for all arms** — the selected model ID is applied uniformly within an agent backend.
3. **Identical question text** — each arm receives the exact same `prompt` string from `QuestionSpec`.
4. **Minimum 4 repeats** — the pilot and full phases require `--repeats 4` or higher; the summary drops any arm with fewer.
5. **Report median, not best** — `overall`, `elapsed_seconds`, and `total_tokens` are summarized as median across repeats.
6. **Cold and warm reported separately** — arms with `index_mode: cold` are never averaged with `index_mode: warm`; they form separate columns in the summary table.
7. **Index build time excluded from warm query time** — `elapsed_seconds` in a warm run begins after the index is confirmed ready.
8. **Flag low-quality answers** — any run with `EvalRecord.overall < 2.5` is marked `LOW_QUALITY` in the report even if it was token-efficient.
9. **Auto-penalize phantom citations** — citations to files that do not exist in the pinned repo reduce `citation_quality` automatically before human/LLM review.
10. **No silent drops** — timeouts and exceptions are recorded as `RunRecord` entries with `error` set; they appear in the report as `FAILED` rather than being omitted.

Claude runs use hard CLI tool allowlists. Codex runs ignore the user's global
configuration and inject exactly one required MCP server for each indexed arm,
with an explicit MCP tool allowlist; native-only injects no MCP server. Codex
native-only runs use a read-only sandbox. Codex indexed arms use a
workspace-write sandbox because CodeGraph and TSA query paths may update SQLite
WAL/cache metadata during otherwise read-only queries. CodeGraph's Codex MCP
server is pinned to `@colbymchenry/codegraph@1.5.0`.

---

## Warm vs Cold Index

| | Warm | Cold |
|-|------|------|
| Index state at query time | Already built and on disk | Built from scratch during the timed run |
| What is measured | Query latency and quality only | Full end-to-end cost including index construction |
| Indexed build time in report | Separate `IndexStats` record | Included in `elapsed_seconds` |
| Realistic scenario | Persistent dev environment | Fresh CI checkout or first-run |

---

## Phase Execution Order

Run phases in order. Each phase gates the next.

```
smoke    →  1 repo, 1 question, 1 repeat, all arms
             Goal: verify adapters run without errors

pilot    →  1 repo, all questions, 4 repeats, all arms
             Goal: catch quality regressions before full compute spend

full-warm →  all 7 repos, all questions, 4 repeats, warm arms only
             Goal: primary quality + token comparison

cold     →  all 7 repos, all questions, 4 repeats, cold arms only
             Goal: measure index-build overhead
```

Stop and investigate if any arm has a `FAILED` rate above 5 % in smoke or pilot.
The `phase` subcommand applies these defaults directly:

```bash
uv run python benchmarks/codegraph_compare/run.py phase smoke --agent-backend codex
uv run python benchmarks/codegraph_compare/run.py phase pilot --agent-backend codex
uv run python benchmarks/codegraph_compare/run.py phase full-warm --agent-backend codex
uv run python benchmarks/codegraph_compare/run.py phase cold --agent-backend codex
```

### Manifest-bound Gin Smoke

Before freezing a real three-arm Gin Smoke, prove that the exact Codex model is
available without exposing the repository, benchmark question, or oracle:

```bash
uv run python -m benchmarks.codegraph_compare.smoke_preflight \
  --model gpt-5.4 \
  --output .benchmark-runs/no1-001c/model-preflight.json
```

Then pass that immutable evidence to the plan freezer:

```bash
uv run python -m benchmarks.codegraph_compare.smoke_plan \
  --checkout-root .benchmark-runs/no1-001c/checkouts \
  --destination .benchmark-runs/no1-001c/frozen \
  --model-preflight .benchmark-runs/no1-001c/model-preflight.json \
  --model gpt-5.4 \
  --session-id NO1-001C-PRIMARY
```

The freezer rejects failed, stale, future-dated, differently authenticated,
different-model, or different-CLI preflight evidence before it creates the
destination or reads benchmark questions. The evidence is copied into the
immutable plan and included in bundle checksums and byte-identical replay.

---

## Reading the Summary Table

```
repo         question_id          arm              med_overall  med_tokens  med_elapsed_s  fail_rate
----------   ------------------   --------------   -----------  ----------  -------------  ---------
django       call-chain-orm-001   native-only            3.2      14 200          18.4       0 %
django       call-chain-orm-001   codegraph-warm         4.1       6 100           4.2       0 %
django       call-chain-orm-001   tsa-warm               3.9       7 800           5.1       0 %
```

Column meanings:

- `med_overall` — median `EvalRecord.overall` (1–5 scale, 5 = best)
- `med_tokens` — median `RunRecord.total_tokens`
- `med_elapsed_s` — median wall-clock seconds (index build excluded for warm arms)
- `fail_rate` — percentage of repeats with `error` set or `overall < 2.5`

A result is considered **dominant** if it scores higher on `med_overall` AND lower on `med_tokens` than the next-best arm. Neither dimension alone is sufficient.
