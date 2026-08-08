# RFC-0022: Static task outcomes by primitive orchestration

- **Status**: draft; corrective design, no implementation
- **Author(s)**: project maintainers
- **Created**: 2026-08-08
- **Last updated**: 2026-08-08
- **Tracking issue**: TBD
- **Affected paths in later implementation only**: `tree_sitter_analyzer/task/`,
  existing `index`/`edit` primitive adapters, their existing tests, and (only after
  the menu gate) MCP/CLI registries and codemaps.

## Summary

This RFC proposes three static outcomes over existing TSA facade actions:
`understand`, `plan_change`, and `assess_change`. The task layer validates,
routes, and normalizes primitive results; it never parses a patch or source,
resolves a symbol, builds a graph, evaluates a constraint, or runs a command.

The first implementation is deliberately not a ninth MCP facade. Phase A is an
internal Python API plus a non-registered experiment harness. Registration is
forbidden until the pre-registration tool-menu experiment in this RFC passes.
If it passes, MCP remains TOON-by-default and CLI JSON-by-default.

## Non-negotiable boundary

```text
internal Python / experiment request
  -> validate boundary and routing budget
  -> call existing facade action adapters, sequentially
  -> freeze one TaskOutcome value
  -> serialize that value (JSON or TOON)
```

`tree_sitter_analyzer/task/` MUST NOT import analyzer internals or own a parser,
diff reader, filesystem/index scanner, identifier extractor, keyword router,
constraint engine, command runner, graph, or cache. It may perform schema
validation, stable sorting, caps, ID hashing, and table-driven aggregation only.
Task/diff text is untrusted data and never selects a callable or shell command.

## Phase 0: authoritative primitive capabilities (release prerequisite)

Phase A MUST NOT begin until these existing primitive adapters expose and test
all capabilities below. This is a prerequisite, not task-layer implementation.

### P0.1 Authoritative index snapshot oracle

`index.status` must return an opaque `snapshot_id`, an authoritative
`source_fingerprint`, `index_fingerprint`, and `completeness` (`complete`,
`partial`, or `unknown`). Every graph-backed primitive used here must echo the
same `snapshot_id` it actually read. Only the primitive/index owner computes
these values. A task never scans or hashes the repository.

If any field is absent, disagrees across calls, or completeness is not
`complete`, freshness is `unknown` (or `stale` when the primitive says so) and
a graph-dependent outcome is at most `partial`. `lag_seconds`, mtimes, elapsed
time, and a task-computed hash are never evidence of freshness.

### P0.2 Frozen workspace/staged diff snapshot

V1 accepts only `workspace` and `staged`. They map respectively to
`edit.impact(mode="diff", ...)` and `edit.impact(mode="staged", ...)`.

Before Phase A, the edit-adapter runtime must own a process-local, non-persistent
snapshot registry. `edit.impact` atomically materializes the normalized patch and
all available old/new bytes into an immutable registry entry, then returns its
opaque `diff_snapshot_id` and changed-file records (`path`, `status`, old/new
availability, binary flag). `edit.ast_diff` and `edit.classify` accept only that
ID plus `file_path`; they never reread a file to reconstruct the captured input.
The task only fans out the returned records in normalized path order.

The frozen registry configuration is part of the primitive contract: at most 16
live snapshots, 64 MiB total materialized bytes, and a 35-second hard lifetime.
An entry is pinned against eviction while its route lease is open; capacity or
size exhaustion fails `edit.impact` with `DIFF_SNAPSHOT_CAPACITY` rather than
writing to disk. The orchestration host closes the primitive-issued lease in a
`finally` block after outcome freeze/failure; close and hard expiry erase the
entry. Access after either returns `DIFF_SNAPSHOT_EXPIRED`. Before every fan-out
call, the primitive owner compares its source-generation token with the one
captured atomically by `impact`; a changed workspace/staged source returns
`DIFF_SNAPSHOT_SOURCE_CHANGED`, emits no derived result, and makes the task stop
remaining diff fan-out. These stable errors are result data, not exceptions
whose text is serialized. No snapshot directory, temp file, DB, WAL, or implicit
persistent cache is permitted.

Rename, add, delete, multi-file, binary, capacity, expiry, lease cleanup, and
mid-route workspace mutation are primitive contract tests. Today these adapters
do not share such an artifact, so no diff outcome may ship until P0.2 lands.
`inline`, `stdin`, arbitrary patch content, branch, and PR are not V1 inputs.

### P0.3 Read-only constraint evaluation

Before Phase A, `edit.constraints` must support `persist=false`, perform no
DB/file write, and have a corrected MCP side-effect annotation. Every diff route
reserves a call and, after successful `edit.impact`, invokes it with
`persist=false` before per-file fan-out; the primitive owns config discovery
and returns `state=not_applicable`, `reason=NO_CONFIG` when none exists.
That result satisfies the constraint row and contributes no verdict. Only request
rejection, impact failure, or an expired routing deadline can prevent the reserved
call, producing the truth-table `unknown` contribution. The task never preflights
files or capability. P0.3 is a release prerequisite, so there is no runtime
`READ_ONLY_CAPABILITY_UNAVAILABLE` branch and no fallback evaluator.

### P0.4 Read-only/open-existing mode for every routed adapter

Every routed adapter (`index.status`, `nav.context`, `edit.safe`, `edit.impact`,
`edit.ast_diff`, `edit.classify`, and `edit.constraints`) must expose a tested
`access_mode="read_existing"` used by Phase A. It may open a compatible existing
index/cache read-only, but must not create a directory, DB, journal/WAL, schema,
index, migration, lock file, snapshot file, or temp file. Each successful result
echoes the primitive-owned source snapshot it actually read (index, diff, or
config), or explicit `not_applicable`; the task creates none. A missing cache/index
returns `missing`/`unknown`; an old or incompatible schema returns
`unknown:INCOMPATIBLE_SCHEMA`. Neither case triggers initialization or migration.

Primitive acceptance fixtures cover (1) a clean repository with no cache, (2) a
repository with an old schema, and (3) a read-only filesystem. For each adapter
and composed route, tests pin the stable result and compare before/after project
and cache trees plus hashes of every pre-existing DB and sidecar; all are exactly
unchanged. The in-memory P0.2 registry is the only allowed ephemeral state.

### P0.5 Authoritative wire owner and versions

Every routed result fragment must echo its adapter-owned stable `action_version`.
A fragment derived by a primitive rule must also echo its primitive facade,
action, `producer_rule_id`, and `producer_rule_version`. A general generated
action registry may detect and diagnose disagreement, but it is never a fallback
source for evidence fields. Task code may not insert, default, or pin them.
Missing or disagreement makes that contribution `unknown` and issues no evidence
ID. The task adapter canonicalizes and hashes the exact received wire fragment;
the primitive does not supply that digest. Contract tests prove action/rule
version changes alter the exact wire bytes and therefore evidence identity.

## Internal Python contract

```python
@dataclass(frozen=True)
class Budget:
    profile: Literal["compact", "standard"] = "standard"
    max_primitive_calls: int | None = None
    max_evidence_items: int | None = None
    routing_deadline_ms: int | None = None

@dataclass(frozen=True)
class DiffInput:
    source: Literal["workspace", "staged"]

async def understand(request: UnderstandRequest) -> TaskOutcome: ...
async def plan_change(request: PlanChangeRequest) -> TaskOutcome: ...
async def assess_change(request: AssessChangeRequest) -> TaskOutcome: ...
```

A plan request has exactly one non-empty `task` or one `diff`. Task V1 does not
accept `scope_paths`: `nav.context` currently has no such parameter, and local
post-filtering would falsely imply a scoped search. Diff requests may carry
`scope_paths`, passed unchanged only to `edit.impact`. Boundary validation
precedes every primitive call.

Pinned profiles are:

| profile | primitive calls | evidence items | routing deadline |
|---|---:|---:|---:|
| compact | 4 | 15 | 5,000 ms |
| standard | 12 | 50 | 30,000 ms |

Explicit values may only lower a profile value. A diff request requires
`max_primitive_calls >= 3` for `index.status`, `edit.impact`, and the reserved
`edit.constraints` call. A lower explicit value is `BUDGET_INVALID`, rejected
before any primitive call. File fan-out may still be omitted by the remaining
budget and then contributes partial. `routing_deadline_ms` is a routing deadline,
**not a wall-time SLA or resource cap**. V1 calls primitives
sequentially and checks the deadline before starting each call. A non-cancellable
running primitive may finish after it; `consumed.routing_wall_ms` may therefore
exceed the limit, with `deadline_overrun_ms` reported exactly. No new call starts
after the deadline. Safe cancellation needs a separate primitive contract.

## Complete V1 route decision table

There is no task-layer keyword, regex, identifier, intent, or LLM router. Free
text is passed unchanged to the already-existing `nav.context` primitive, which
is the sole owner of natural-language symbol inference. Parameters not shown are
not sent; primitive output format is JSON internally.

### Common routing rules

1. Validate request and paths. On failure, make zero calls.
2. Before each row, stop if call/deadline budget is exhausted. For a diff route,
   validate the three-call minimum at the boundary and reserve the constraints
   slot **before** starting impact. A successful impact is followed immediately
   by constraints, before file fan-out; fan-out cannot consume the reserved slot.
3. Call rows in displayed order. Fan-out lists are de-duplicated and sorted by
   `(path, symbol)` before their pinned cap is applied.
4. Never substitute a failed/unsupported action. Record `unknown`/`not_run`.
5. After graph calls, compare only primitive-issued snapshot tokens.
6. Stop immediately on snapshot disagreement, expiry, or
   `DIFF_SNAPSHOT_SOURCE_CHANGED`; retain earlier evidence as partial and make no
   further snapshot-dependent calls.

| operation/input | condition | facade action and exact semantic parameters | stop/degrade rule |
|---|---|---|---|
| all | always | `index.status(access_mode="read_existing", output_format="json")` | missing oracle => freshness unknown; continue, at most partial if graph evidence is used |
| `understand(task)` | valid task | `nav.context(task=task, max_nodes=12/30, max_code_blocks=3/5, include_graph=false, access_mode="read_existing", output_format="json")` | failure => unknown; success ends route |
| `plan_change(task)` | valid task | same `nav.context` call | failure => unknown and stop |
| `plan_change(task)` | each distinct existing path explicitly returned in `code_blocks`, max 2/5 | `edit.safe(file_path=path, edit_type="refactor", access_mode="read_existing", output_format="json")` | missing path is not inferred; per-call failure is partial |
| diff operation | valid diff | `edit.impact(mode="diff"|"staged", scope_paths=scope_paths, include_tests=true, resource_profile="local_low_impact", access_mode="read_existing", output_format="json")` | missing/failing `diff_snapshot_id` => unknown and stop |
| diff operation | successful impact; reserved before fan-out | `edit.constraints(persist=false, access_mode="read_existing", output_format="json")` | `not_applicable:NO_CONFIG` satisfies the row; invocation failure degrades per the truth table |
| diff operation | each non-binary changed record with old/new material available | `edit.ast_diff(diff_snapshot_id=id, file_path=path, access_mode="read_existing", output_format="json")` | unsupported add/delete/rename is explicit `not_run`, never locally reconstructed |
| diff operation | same eligible records | `edit.classify(diff_snapshot_id=id, file_path=path, access_mode="read_existing", output_format="json")` | per-file failure => partial |

The compact/standard values in a cell are selected only by `Budget.profile`.
The task-plan `edit.safe` fan-out uses only paths emitted by `nav.context`; it
does not guess a modification kind or symbol. Diff `plan_change` and
`assess_change` share the identical primitive route and differ only in their
artifact projection: an ordered plan versus a static assessment.

Required static questions are: context for task-understanding; context plus all
selected file-safety checks for task-planning; and impact, every eligible
structural/classification result, plus one unconditional constraints invocation
for diff operations. `not_applicable:NO_CONFIG` is a completed constraints row.
Budget omission makes the result partial, not a shorter definition of required.

### `tsa_explore` disposition

`mcp/tsa_explore.py` remains non-production today. Phase 0 marks it retired and
migrates any benchmark fixtures, then deletes it before a task route is added.
It is never registered. Its keyword inference, `_extract_symbol`, and `_ROUTING`
MUST NOT be copied or imported. This RFC's fixed table plus `nav.context` is the
only task routing path, preventing a second orchestration/inference engine.

## Fixed `task-outcome/v1` semantics

The fixed model keeps these required top-level keys:

```jsonc
{
  "schema": "task-outcome/v1",
  "success": true,
  "operation": "understand|plan_change|assess_change",
  "status": "complete|partial|unknown",
  "verdict": "SAFE|CAUTION|REVIEW|UNSAFE|INFO|WARN|NOT_FOUND",
  "subject": {"task": null, "diff": {"source": "workspace|staged", "snapshot_id": "opaque", "changed_paths": []}},
  "claims": [], "artifacts": {"relevant_symbols": [], "relevant_paths": [], "plan_steps": [], "verification": [], "edge_collections": []},
  "evidence": [], "provenance": [], "freshness": [], "unknowns": [], "errors": [],
  "budget": {}, "truncation": {}, "next_step": null, "agent_summary": {}
}
```

Arrays stay present when empty. `artifacts.edge_collections` is required and is
an empty array when RFC-0023 edge evidence is unused. This field is incorporated
while `task-outcome/v1` is still an unimplemented draft: earlier draft fixtures
must be regenerated, and no deployed V1 compatibility promise is affected. After
V1 implementation, removing or retyping it requires a negotiated V2. Strict
clients reject unknown enum values.
Request failures use `success=false` and existing TSA envelope conventions with
stable codes `INVALID_REQUEST`, `OUTSIDE_PROJECT`, `BUDGET_INVALID`,
`UNSUPPORTED_DIFF_SOURCE`, and `INTERNAL_ERROR`. Absolute host paths, bodies,
secrets, environment values, stderr, and traces are not serialized.

### Evidence and provenance identity

Every supported/contradicted claim cites evidence; unknown claims cite an
unknown. Evidence IDs are:

```text
evidence:sha256(canonical_json({
  primitive_facade, action, action_version,
  normalized_result_sha256, source_snapshot_id, locator
}))
```

The normalized result hash covers the canonical bytes of the exact primitive wire
fragment supporting the claim. That wire already contains its primitive facade,
action, action version, and, when rule-derived, producer rule ID/version. The task
adapter only validates, canonicalizes, and hashes those exact bytes; it never
inserts owner fields and the primitive never supplies the digest. A registry may
diagnose mismatch but cannot repair missing edge-evidence ownership. Missing or
disagreement makes the contribution `unknown` and mints no evidence ID. Locator
alone never identifies or deduplicates evidence. Provenance records the same
owner/version fields, request hash, result hash, snapshot, success, verdict,
truncation, and input evidence IDs. RFC-0023's specialized edge formulas and
strict artifacts refine this generic identity without changing the owner flow.

### Freshness and snapshot truth

Freshness states are `fresh|stale|missing|not_applicable|unknown`. `fresh` is
allowed only when the authoritative oracle is complete and every graph result
echoes its token. Without that oracle, repository/index fingerprints are null,
reason is `AUTHORITATIVE_SNAPSHOT_UNAVAILABLE`, and graph-dependent status is at
most partial. Diff evidence cites the primitive-owned `diff_snapshot_id`.
Outcomes never claim a mixed snapshot is complete.

### Static verification truth table

The old name `verify_change` is removed because no command is executed.
`assess_change` fixes `completeness_scope=static` and `runtime_status=not_run`.
Each required invocation produces exactly one contribution from this table;
`finding` is the normalized primitive result, never task inference.

| invocation | finding | freshness | truncation | status contribution | verdict contribution |
|---|---|---|---|---|---|
| not required (runtime, binary structural/classification) | none | not_applicable | false | ignored | none |
| not called (budget/deadline) | unknown | unknown | unknown | unknown | none |
| failed/unsupported/expired/source changed | unknown | unknown | false | unknown | none |
| succeeded | unknown/malformed | any | any | unknown | none |
| succeeded | none | fresh | false | complete | primitive non-risk verdict (`SAFE`, `INFO`, or conclusive `NOT_FOUND`) |
| succeeded | risk | fresh | false | complete | primitive risk verdict (`WARN`, `CAUTION`, `REVIEW`, or `UNSAFE`) |
| succeeded structural | invalid | fresh | false | complete | primitive `REVIEW` or `UNSAFE` |
| succeeded constraints | violation | fresh | false | complete | `UNSAFE` |
| succeeded constraints | `NO_CONFIG` | not_applicable | false | complete | none |
| succeeded | none/risk/invalid/violation | stale/missing/unknown | false | partial | same primitive verdict, marked non-fresh |
| succeeded | none/risk/invalid/violation | any | true/unknown | partial | same primitive verdict, marked truncated |

The table is ordered: the first matching row wins, so truncation overrides a
fresh success and malformed finding overrides freshness. `any` is a wildcard;
any tuple matching no row is invalid primitive output and canonicalizes to
`(succeeded, malformed, unknown, unknown)` before a second, final lookup. Thus
every input tuple has exactly one contribution. Impact not invoked or
failed with no decision evidence therefore yields `unknown`; successful fresh,
untruncated impact with a risk finding is `complete` and contributes its risk
verdict; the same success with no finding is `complete` and contributes its
non-risk verdict. Structural invalidity and constraint violation explicitly
permit `complete + REVIEW/UNSAFE`: completeness describes observation, not safety.
Classification risk likewise does not make invocation failure.

Aggregate status is deterministic: remove ignored rows; `complete` requires all
remaining contributions to be complete; `partial` requires at least one useful
complete/partial contribution and at least one non-complete contribution;
otherwise status is `unknown`. Runtime never enters this aggregation. A
primitive-provided verification command is inert suggested text, never evidence.
Verdicts aggregate as `UNSAFE > REVIEW > CAUTION > WARN > SAFE > INFO >
NOT_FOUND`; no contribution is not a verdict, and incompleteness never upgrades
risk. If there are no verdict contributions, the required top-level verdict is
`INFO`. Conclusive `NOT_FOUND` requires known scope and fresh, untruncated success.

### Budget and truncation

Failed attempts consume calls. Primitive truncation and orchestration omission
are separate dimensions. Unknown totals are `null` with
`total_count_state=unknown`; “N of N” is forbidden unless the primitive provides
an exact total. Omitted decision-relevant evidence forces partial plus
`BUDGET_EXHAUSTED` or `TRUNCATED`. Routing order, paths, symbols, locators,
claims, and evidence are stable-sorted before the frozen model is created.

## Determinism and serializer parity

One execution creates one immutable/frozen `TaskOutcome`, including timestamps,
durations, result hashes, and snapshot IDs. The parity oracle serializes **that
same object** through JSON and TOON, decodes both, and requires exact model
equality. It never compares two live executions, whose clocks or snapshots may
differ. Transport metadata is outside the semantic model.

MCP's default remains TOON and CLI's default remains JSON. Payload stays on
stdout and diagnostics on stderr. If/when public surfaces land, both handlers
must call the same Python API and the same serializers; explicit JSON/TOON are
available on both. No default is flipped to manufacture parity.

## Public surface and ninth-facade gate

### Phase A — internal experiment only

- After Phase 0 passes, implement frozen models, validators, the fixed router,
  and serializers behind `tree_sitter_analyzer.task` internal/experimental imports.
- Exercise them through a benchmark harness, not `_tool_registry.py`, MCP server,
  facade schemas, main CLI flags, or codemaps.
- Existing public surface remains exactly eight facades plus infrastructure.

### Pre-registration gate

A checked-in experiment manifest must freeze task corpus, agent/model/config,
randomization, sample size, success rubric, and tool definitions before running.
The paired live-agent A/B compares the existing menu with the candidate ninth
facade. Registration requires all of:

1. exact corpus completion and raw artifacts are published;
2. task-facade discovery rate and end-to-end task success show the manifest's
   predeclared measurable improvement, with no material primitive-discovery loss;
4. exact serialized tool-definition bytes and tokenizer counts are pinned for
   both menus, and the candidate stays within the predeclared menu budget;
5. median turns and input/output token cost are reported, not inferred from this RFC;
6. a rerunnable executable gate validates the signed result artifact.

An RFC/self-test is E0 design evidence and cannot satisfy this gate. Failure or
an inconclusive result means no registration. A new menu experiment must be
approved rather than silently moving the actions onto another facade.

### Phase B — conditional public registration

Only after the gate passes may one `task` facade be registered with actions
`understand`, `plan_change`, and `assess_change`. Its CLI equivalents land in
the same change, along with registry/facade counts, MCP/CLI parity tests, and
both codemaps. If the gate does not pass, the outcome API remains experimental
Python-only. This RFC does not pre-authorize a ninth facade.

## Executable value and cost invariants

Later implementation tests must use one frozen fixture and pin exact byte/token
counts for each serializer/profile. They also assert these differential facts:

- compact model bytes and tokens are strictly less than standard;
- TOON bytes and the repository-pinned tokenizer count do not exceed JSON for
  the same frozen model;
- decoding JSON and TOON yields exactly the same frozen model;
- adding the candidate facade changes menu bytes/tokens by the exact reviewed
  delta in the experiment artifact.

Any claim about size, token cost, latency, discovery, or success is removed from
documentation unless its executable measurement is checked in. Timing tests use
an injected clock for exact routing decisions; a blocking fake proves deadline
overrun reporting and proves that no later call starts.

## Security and compatibility

All paths pass the existing `ProjectBoundaryManager`; absolute, `..`, symlink,
submodule, and out-of-root paths fail before calls. No implicit index build,
network, shell, edit, git mutation, or persistence is permitted. Excerpts use
existing bounded/redacted primitive results. This RFC does not change
`BaseMCPTool` root canonicalization, index storage, or primitive behavior except
the separately tested Phase 0 capabilities.

Existing eight facades, legacy shim, CLI flags, schemas, and defaults remain
unchanged in Phase A. `task-outcome/v1` fields are not removed or retyped within
V1. A future version requires explicit negotiation and overlap.

## RED-first acceptance plan

1. Phase 0 tests prove authoritative snapshot/version propagation; bounded
   in-memory snapshot ownership, expiry, cleanup, and mutation errors; and
   workspace/staged mapping including add/delete/rename/binary.
2. For every routed adapter and composed route, Phase 0 tests prove exact zero
   writes by before/after tree and DB/sidecar hashes on clean, old-schema, and
   read-only-filesystem fixtures; they also pin `NO_CONFIG` from the unconditional
   `constraints(persist=false)` call.
3. Route tests pin every row, parameter, fan-out order/cap, stop condition, and
   prove no analyzer import, `tsa_explore` reuse, mutating action, or fallback.
4. Schema/evidence tests pin key sets, evidence identity inputs, dangling-link
   rejection, same-locator non-dedup, and conservative aggregation.
5. Freshness tests prove absent oracle is unknown/partial and snapshot mismatch
   stops graph routing.
6. Static truth-table tests cover every passed/failed/not-run/unknown cell and
   prove runtime stays not-run without reducing static completeness.
7. Budget tests pin profile values, sequential routing, exact overrun, unknown
   totals, and decision-relevant truncation.
8. Security tests prove fail-closed validation, zero calls after rejection,
   error redaction, and zero project/cache writes for every outcome.
9. Serializer tests use one frozen result for exact JSON/TOON equality and the
   executable cost invariants above.
10. The pre-registration live menu experiment and artifact validator pass before
   any registry/CLI/codemap change.
11. Conditional Phase B tests prove real handler parity, locked defaults, stdout/
    stderr separation, and compatibility of every pre-existing facade/action.

All deterministic counts use exact assertions and each test covers one behavior.
Regression tests cite their issue/incident. Later Python changes must follow
change-impact and patch-coverage gates. This RFC branch is docs-only.

## Deferred and rejected

- Inline/stdin/branch/PR diffs, runtime execution, cancellation, sessions,
  persistence, LLM planning, and cursors are deferred.
- A task-owned patch parser, repository fingerprint, classifier, graph, keyword
  router, or constraint evaluator is rejected.
- Registering `tsa_explore`, copying its inference, or registering a ninth facade
  before the menu gate is rejected.
- Calling `edit.constraints` without `persist=false` is rejected.
- Calling static assessment `verify_change` is rejected.

## Open questions

1. Should runtime verification be a separate sandboxed API rather than a future
   version of `assess_change`?
2. If the ninth-facade experiment fails, should a later experiment test an
   existing-facade action, or should task outcomes remain Python-only?
