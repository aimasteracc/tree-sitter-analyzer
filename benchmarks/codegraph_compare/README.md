# CodeGraph Comparison Benchmark


## NO1-003B production-canary operator runbook

> **Current decision: NO-GO for a real canary.** NO1-003D provides only an
> offline-qualified, direct single-transport dispatch boundary; it contains no
> provider implementation or operator command. A caller-supplied `runner` is a
> fail-closed compatibility marker and is never executed. `CanaryProtocol` still
> rejects every non-fixture execution with
> `QUALIFICATION_SCAFFOLD_NOT_PRODUCTION_READY`. Do not bypass that stop or call
> an adapter directly. A real NO1-003C run still requires separate human budget
> authorization, external authorities, external paths, and independent role keys.

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
  .evidence_durable == false and
  (.evidence_durability == "local-dirfd-diagnostic-only" or
   .evidence_durability == "unsupported") and
  .attestation_verified == true and
  .synthetic_judge_signature_verified == true and
  .independent_judge_available == false and
  .denial_probe_qualification_status == "NOT_EVALUATED" and
  .denial_probe_violations == ["ROLE_KEYS_NOT_INDEPENDENT","ROLE_KEY_MATERIAL_NOT_INDEPENDENT","INDEPENDENT_JUDGE_UNAVAILABLE"] and
  .bound_fixture_gate_eligible == true and
  .production_dispatch_allowed == false and
  .model_callbacks_invoked == 0 and
  .provider_requests == 0 and
  .input_tokens == 0 and .output_tokens == 0 and .cost_usd == 0 and
  .evidence_level == "E0" and .winner == null and
  .dominance_allowed == false and .publishable == false
' "$WORK_PARENT/receipt.json"
```

`evidence_durable=false` is mandatory for this E0 rehearsal. POSIX reports
`local-dirfd-diagnostic-only` after mode sealing; Windows reports `unsupported`
because it has no equivalent `openat`/`dir_fd` durability boundary. Neither mode
is production evidence. `synthetic_judge_signature_verified=true` proves only
that the same-process rehearsal record is canonically signed. It is deliberately not represented as an
independent judgment. `denial_probe_qualification_status=NOT_EVALUATED` with role-key path and material independence violations proves the production gate remains closed. The
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
  tests/unit/test_production_dispatch.py \
  tests/unit/test_production_rehearsal.py \
  tests/unit/test_benchmark_harness.py
uv run python scripts/no1_003d_mutations.py
uv run python -m tree_sitter_analyzer --change-impact --format json
```

Stop immediately if either command fails, if the rehearsal reports any non-zero
usage/cost, or if any claim flag is enabled. Never “fix” rehearsal failure by
weakening attestation, budget, judge, immutability, transcript, matrix, or claim
checks.

### 3. Production readiness checklist (all items mandatory)

The Anchor Custodian, Budget Gateway, Evidence Collector, independent Judge,
and execution operator must record approval out of band. The strict wire request
contains `schema_version`, `manifest`, `spec`, `cell_order`, `timeout_seconds`,
`qualification_evidence_digest`, `journal_root`, and `evidence_root`. The spec
continues to bind the configured roots and ledger identity material as frozen
input, but no local journal, pathname, inode, or ledger establishes a claim or
terminal authorization. Operator config pins independent spend and judge keys
and independent Ed25519 public keys/key IDs for the external nonce-claim,
provider-budget, and immutable-evidence authorities. The dispatcher contains no
authority private key or receipt issuer. Production PASS requires all three
external facts: a fresh one-shot claim receipt bound to the dispatch challenge,
signed provider reservation and usage receipts, and a signed terminal evidence
receipt. Before any future real call, all of the following must be true:

1. The exact Gin commit, clean workspace fingerprint, prompt hash, MCP launch
   identities, exact model ID, nonce, expiry, one-cell request limit, token limit,
   USD ceiling, and canonical absolute journal/evidence/global-ledger roots are
   frozen in the strict `ProductionRunSpecV1` v1 wire schema.
2. The anchor and trust store are operator-controlled regular files outside the
   checkout and evidence bundle, with no symlink component. No TOFU,
   bundle-provided key, environment inheritance, or self-signed replacement is
   allowed.
3. `SpendAttestation` and `JudgeRecord` bind the exact spec hash (including all
   three roots and the ledger identity material), nonce, expiry, and provider
   budget mode. `client-process-kill` self-reporting is rejected. The dispatcher
   rejects unrestricted provider callables and accepts only an externally supervised
   transport authority receipt proving exact-one, the frozen timeout, and whole-process
   termination after a verified one-shot claim. Exact-v1 provider reservation and usage
   receipts require canonical bounded
   identities, exact numeric types, and Ed25519 signatures verified with the
   qualification-time pinned provider public key.
4. The collector root is fresh and external. The configured local journal and
   collected evidence are E0 diagnostics only. `EvidenceCollector.finalize()`
   always reports
   `durable=false`: POSIX dirfd collection reports
   `local-dirfd-diagnostic-only`, while Windows/no-dirfd reports
   `durability="unsupported"` and does not simulate read-only or WORM storage.
   Dispatch consumes only the local ledger SHA-256 as an input to the external
   evidence authority; local files cannot establish terminal durability or PASS.
5. The Judge independently signs the exact evidence digest and spec hash. Any
   missing, stale, mismatched, non-`ACCEPT`, or unverifiable record is terminal
   `NOT_EVALUATED`/`INVALID`, never a retry opportunity or a TSA win.
6. The exact two indexed cells, order, one attempt each, receipt/tool arguments,
   oracle (`gin.go`, `Engine.ServeHTTP`, `method`), transcript policy, and
   cumulative USD ceiling remain unchanged. A manifest-level experiment authority
   reserves from the shared $3 ceiling and binds cell 1 to cell 0's immutable terminal;
   cell 1 cannot run first or obtain a second independent $3 reservation.
7. Output remains E0/internal: `winner=null`, `dominance_allowed=false`, and
   `publishable=false`. No No.1, dominance, production-readiness, E1+, or public
   benchmark claim is permitted.
8. The library dispatcher accepts a one-shot claim only from the external
   nonce-claim authority, verifies provider reservation/usage receipts from the
   external provider-budget authority, and accepts terminal durability only from
   the external immutable-evidence authority. All are independently pinned
   Ed25519 verification roles. Missing transport/authority inputs or unavailable
   authority public-key pins fail before transport as `NOT_EVALUATED` with zero
   callbacks. A refused or invalid claim also invokes zero callbacks; an invalid
   terminal evidence receipt after the call remains E0 and cannot become PASS.
   A production provider adapter and operator command are not present today;
   `TrustedOfflineTestAdapter` is explicitly test-only and is rejected by
   production dispatch.

### 4. Abort and escalation

Abort before spend on any missing approval, pre-existing artifact root, dirty or
mutated checkout, wrong binary/model/hash, expired spec, budget-mode mismatch,
open verification-to-use gap, judge/attestation failure, or unavailable arm.
After a call starts, kill at the frozen timeout/limit, retain all partial evidence,
terminalize the cell, and do not rerun it. Escalate the immutable receipt and
violation list to the maintainers; never delete, overwrite, relabel, or exclude
an unfavorable outcome.

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
