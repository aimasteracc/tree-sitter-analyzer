# Agent Envelope Contract

One page for agents and MCP-client authors: what every tree-sitter-analyzer
(TSA) MCP response envelope guarantees, what each `verdict` obliges you to do,
how honest truncation works, and how JSON control fields support recovery.
Everything here is backed by source constants and protected
against drift by
[`tests/integration/docs/test_agent_envelope_contract_doc.py`](../tests/integration/docs/test_agent_envelope_contract_doc.py),
which imports the live constants and fails when this page and the code
disagree.

JSON is the only public wire format. For the tool surface itself, see the
[MCP Tools Codemap](CODEMAPS/mcp-tools.md).

## The minimum envelope

Every tool response is a JSON object. The typed contract lives in
[`tree_sitter_analyzer/mcp/tools/tool_response.py`](../tree_sitter_analyzer/mcp/tools/tool_response.py)
(`ToolResponse` + `validate_tool_response`):

- `success` (bool) — always present. `true` = the tool ran end-to-end.
- `error` (str) — present **iff** `success` is `false`. Human-readable;
  error envelopes usually also carry `error_type` and a recovery `hint`.
- `verdict` (str) — when present, it is EXACTLY one of the canonical strings
  below. On JSON success paths a missing verdict is back-filled with `INFO`
  by the safety net in
  [`tree_sitter_analyzer/mcp/utils/format_helper.py`](../tree_sitter_analyzer/mcp/utils/format_helper.py),
  so agents can always branch on it.
- `agent_summary` (object) — token-lean triage block:
  `summary_line` + `verdict` + `next_step`. `summary_line` is also mirrored
  to the top level.
- `next_step` (str) — one concrete recommended next action (see conventions
  below).

## Verdict alphabet

Source of truth: `CANONICAL_VERDICTS` in
[`tree_sitter_analyzer/mcp/tools/tool_response.py`](../tree_sitter_analyzer/mcp/tools/tool_response.py)
(mirrored by `_response_builder.CANONICAL_VERDICTS` and
`base_tool._LEGAL_VERDICTS`; the response factory `build_response()` rejects
anything else at construction time). Safety verdicts grade edit risk: the
modification-guard maps impact `none/low/medium/high` →
`SAFE/CAUTION/REVIEW/UNSAFE`
([`tree_sitter_analyzer/mcp/tools/modification_guard_tool.py`](../tree_sitter_analyzer/mcp/tools/modification_guard_tool.py)).

<!-- drift:verdict-alphabet:start -->
| Verdict | Meaning | Agent obligation |
|---|---|---|
| `SAFE` | No meaningful risk detected (impact `none`; edit-safety green). | Proceed directly. Run the `verification_command` / nearby tests after the change; no extra review needed. |
| `CAUTION` | Low risk or a notable-but-non-blocking signal (impact `low`, e.g. import cycles present). | Proceed, but follow `next_step` first (usually: run the listed tests *before* editing, keep the change focused). |
| `REVIEW` | Medium risk — blast radius or findings need human/agent inspection (impact `medium`, >threshold affected files). | Do NOT edit blindly. Inspect the listed callers/downstream files, then re-check with `edit action=impact` before changing anything. |
| `UNSAFE` | High risk — wide blast radius, architectural-constraint violation, or guarded file (impact `high`). | Stop. Treat as a blocker: narrow the change, fix the violation, or escalate. Never auto-apply an edit on `UNSAFE`. |
| `INFO` | Informational result; no risk judgement implied. Also the canonical default when a tool has no opinion. | Nothing mandated. Consume the payload; use `next_step` if you need to go deeper. |
| `WARN` | The tool succeeded but found warning-level conditions (degraded data, smells, stale cache). | Read `warnings` / the payload findings and decide; do not ignore silently — surface the warning in your own output if you act on the data. |
| `ERROR` | The call failed (`success: false`). | Read `error` (+ `hint` when present), fix the invocation or environment, retry. Do not consume other payload fields as valid results. |
| `NOT_FOUND` | The tool ran fine but the requested symbol/file/path does not exist in the index. | Treat as an empty result, not a failure. Check spelling, qualify the name (`ClassName.method`), or rebuild the index (`index action=build`) before retrying. |
<!-- drift:verdict-alphabet:end -->

Anything outside this alphabet (`OK`, `CLEAN`, `n/a`, lowercase variants…) is
a bug; `base_tool._canonicalize_verdict()` normalizes historical drift values
to the canonical set, falling back to `INFO`.

## Truncation contract (honest truncation)

Capped lists must never *silently* under-report (#444, #448). When a tool caps
a list, the envelope carries all four of:

| Field | Semantics |
|---|---|
| `truncated` (bool) | `true` iff anything was omitted. **Never assume `len(list) == total` without checking this flag.** |
| pre-cap total | The EXACT count before slicing — e.g. `caller_count` (callers), `callee_count` (callees), `total_matches` (content search / Hyphae select), `total_dead_functions_transitive` (dead code). Recorded *before* the cap is applied. |
| listed count / cap | What is actually in the response: `callers_listed` / `callees_listed` / `dead_functions_listed` …, plus the cap that was applied as `listed_cap` (driven by the tool's `limit` / `max_count` / `max_dead` argument). |
| `next_step` | Interpolates the *actual* numbers ("showing 3 of 39 …") and says how to get the rest: raise the limit, or narrow the query. |

Reference implementation:
[`tree_sitter_analyzer/mcp/tools/callers_tool.py`](../tree_sitter_analyzer/mcp/tools/callers_tool.py)
(see worked example 1). Per-tool field spellings vary (`caller_count` vs
`total_matches`), but the four-part shape — flag, exact pre-cap total, listed
count + cap, interpolated `next_step` — is the contract.

## `next_step` conventions

- One concrete, imperative action — a command or a tool call, not prose
  ("raise limit", "run `uv run pytest …`", "narrow with `:in(path)`").
- On truncation it MUST state the real shown/total numbers (`"showing 3 of
  39 callers"`), never a stale template count (#448).
- Inside `agent_summary` the same key carries the recommended follow-up for
  the verdict (e.g. the pre-edit verification command on `SAFE`).
- Treat it as the default next call when you have no better plan; it is
  advisory, not binding.

## JSON control fields

Every public response is one JSON object. Agents branch on `success`, `verdict`,
`error_code` / `error_type`, `summary_line`, and `agent_summary.next_step` when
those fields apply. Tool-specific payload remains at the top level; there is no
secondary blob to decode. Evidence fields such as `source_evidence`,
`completeness`, `provenance`, and `action_version` must remain visible when the
corresponding action provides them.

For direct inner routes, unknown or action-inapplicable parameters return
`INVALID_ARGUMENT` before the inner tool runs. The response includes `invalid_arguments`,
`allowed_arguments`, and typo `suggestions`, so an Agent can repair the next
call without parsing prose.

## Completeness reasons (`nav action=callers`)

`nav action=callers` declares `completeness` as `complete`, `incomplete` (the
listed callers are a lower bound) or `unknown` (0 listed callers is not
evidence of absence). An answer that is not `complete` always carries a
machine-readable reason, so you can branch on a code instead of parsing prose
(#1632):

- `completeness_reason` (str | null) — the primary reason; `null` iff
  `completeness == "complete"`.
- `completeness_reasons` (list[str]) — every reason that applies, primary
  first, in the fixed order of the table below; `[]` iff complete. Fixing the
  primary cause does not make the answer a census while others remain.

Source of truth: `COMPLETENESS_REASONS` in
[`tree_sitter_analyzer/mcp/tools/callers_reasons.py`](../tree_sitter_analyzer/mcp/tools/callers_reasons.py).
The first six come from the call-edge layer and can combine; the rest come from
the gates that re-check an edge-level `complete` and appear alone, with one
exception: when the non-call reference scan reports `SOURCE_INDEX_MISMATCH`, it
is followed by `NON_CALL_REFERENCES` (and `ACCESSOR_NOT_CALL_EDGES`) if those
still hold for the unchanged files (#1672).

<!-- drift:completeness-reasons:start -->
| Code | Meaning | What to do |
|---|---|---|
| `UNRESOLVED_INBOUND_UNCHECKED` | The unresolved-edge count or the declaring-file guard could not be read. | Retry; rebuild the index if it persists. |
| `UNRESOLVED_INBOUND` | Inbound edges name the target but did not resolve to its definition (`unresolved_inbound`). | Read those call sites; qualify the name to narrow. |
| `UNRESOLVED_IN_DECLARING_FILE` | A file that declares the target holds unresolved calls that could reach it (computed dispatch or same name; see `unresolved_sites`). | Read `unresolved_sites`. |
| `NAME_ONLY_INBOUND` | Inbound edges match by name only and cannot be bound to this target (`name_only_inbound` callers; `name_only_sites`). | Read `name_only_sites` (`next_step` names them); a site calls the target only if its receiver is an instance of the target's class; qualify the name. |
| `UNATTRIBUTED_CALL_SITES` | Module-level call sites are counted, not listed (`unattributed_call_sites`). | Read them directly. |
| `EMPTY_EVIDENCE_BASE` | The call graph holds no call edges at all. | Build the full index (`index action=full`). |
| `SOURCE_INDEX_MISMATCH` | The index is stale for the files in scope, or the non-call reference scan found the name in a file whose content no longer matches the index (`stale_reference_files`; `source_evidence.freshness` is `stale`). | Refresh the index (`next_step`). |
| `SOURCE_SCOPE_UNKNOWN` | The source could not be revalidated against the index. | Refresh the index. |
| `MISSING_INDEX` | No index backs the answer. | Build the index. |
| `SYMBOL_NOT_DEFINED` | The exact target is not defined in the index (`close_matches`). | Check spelling / qualification. |
| `SYMBOL_IN_EXCLUDED_FILE` | The target is not indexed, but it is defined in a source file the index excludes by a default or configured exclude pattern (`excluded_definition`: `file`, `line`, `exclude_pattern`, `default_exclude`). A refresh never indexes that file. | Read the file directly, or rebuild without that exclude (`index action=full no_default_excludes=true` for a default pattern). |
| `SYMBOL_DEFINITION_UNCHECKED` | The target's definition could not be checked. | Retry. |
| `UNINDEXED_SOURCE_FILES` | Same-language files exist that the index has not seen. | Refresh the index. |
| `UNINDEXED_SOURCE_UNCHECKED` | The project walk for unindexed files failed. | Retry. |
| `NON_CALL_REFERENCES` | The name is used without a call (callback, attribute, string, config, JSON, notebook, template, doctest). | Read `non_call_reference_sites`. |
| `NON_CALL_REFERENCES_UNCHECKED` | The non-call reference scan did not finish within budget. | Retry, or search the name directly. |
| `ACCESSOR_NOT_CALL_EDGES` | The target is a property/accessor; reads are not call edges. | Search attribute reads. |
| `DECORATOR_MAY_REGISTER` | A decorator may register the target for dispatch. | Inspect the decorator. |
<!-- drift:completeness-reasons:end -->

### Evidence behind the codes (#1672)

Every code that names sites carries them in the same bounded shape: a list
capped at 20, the exact total beside it, and a `*_truncated` flag.

| Code | Count | Sites (`file`, `line`, …) | Total / truncated |
|---|---|---|---|
| `UNRESOLVED_IN_DECLARING_FILE` | `unresolved_in_declaring_files` | `unresolved_sites` (+ `mechanism`, `callee`) | `unresolved_sites_total` / `unresolved_sites_truncated` |
| `NAME_ONLY_INBOUND` | `name_only_inbound` (callers) | `name_only_sites` (+ `caller`) | `name_only_sites_total` / `name_only_sites_truncated` |
| `NON_CALL_REFERENCES` | `non_call_references` | `non_call_reference_sites` (capped at 5) | `non_call_references` |
| `SOURCE_INDEX_MISMATCH` (reference scan) | `stale_reference_files_total` | `stale_reference_files` (paths, capped at 5) | `stale_reference_files_total` |

`name_only_sites[].line` is the call line from the call-graph edge; when no edge
line is readable it falls back to the caller's definition line. `next_step`
names the first three sites inline and says how many more there are.

A reference-scan hit in a file whose size, mtime and normalised content digest
no longer match its `ast_index` row is most likely a call added since the last
index (it has no call edge yet), so it is reported as `SOURCE_INDEX_MISMATCH`
with `source_evidence.freshness: "stale"` and the refresh `next_step` — the same
diagnosis the 0-caller path gives for the same edit. The check reuses the stat
evidence the scan already read; it does not stat or hash the whole tree.

### Callers bound through an annotation (RFC-0038)

A caller entry whose call was attributed only through the receiver's annotated
type carries `resolution_kind: "annotated_receiver"`, plus `receiver_type`,
`type_source` (`param` / `local` / `attribute` / `return` / `module`) and `confidence`
(`0.8`). Example: `store.publish()` where `store: GenerationStore`, or
`store = project_store()` with `-> GenerationStore`. Such an edge counts as
resolved only for the method it is bound to. For every other method of that
name it stays an unresolved inbound edge, an override in a subclass included.
So it never makes another answer `complete`.

### Receivers that are not proven (#1669)

A method call `x.m()` is a certain caller of a project method `m` only when the
receiver is proven: `self` / `cls`, an imported module or class, a class name
(`T.m()`, `T().m()`), a local built by `x = T()`, or an annotated type
(RFC-0038). A receiver whose type is unknown (an untyped parameter, `self.x`
without an annotation, a chained attribute, `self.x: list`) never binds to `m`
just because `m` is the only project method of that name. Such a call is at most
a name-only possible caller: it is not listed in `callers`, it keeps the answer
non-`complete` (`NAME_ONLY_INBOUND` / `UNRESOLVED_INBOUND`), and the
over-approximating consumers (impact, test_map, pr_review, risk) still see it.
### Callers through an aliased import (#1670)

A call made through a renamed import, `from m import f as _f; _f()`, is a caller
of `m.f`. Its entry carries `resolution_kind: "import_alias"` and `import_alias`
(the local name used at the call, here `_f`). The import line of such an alias
is not counted as a non-call reference of `f` only when the answer already has
callers and every use of the alias in that file is a call bound to `f`. A public
alias, an alias another module imports or calls, or an alias that is also used
without a call (a callback, an assignment, `__all__`) keeps the import line as a
reference; the non-call uses are listed in `non_call_reference_sites` too. With
no caller at all, the import line always stays a reference (#1645).

## Index write admission codes (RFC-0032)

An index write can be refused before it changes anything: another write
superseded its candidate, another writer holds the index, the supplied candidate
is not bound to the index, or the index storage needs recovery. Every write route
reports this with one of four `error_code` values and the same machine fields:

- MCP `index action=cache` (`mode=index` / `sync` / `invalidate`),
  `index action=full` and `codegraph_incremental_sync` `mode=sync`, including
  the first automatic warm of a never-indexed project (also `auto_index`
  `mode=warm` and `codegraph_refactor`; read-only visualizations fall back to
  parsing source instead);
- the CLI routes that print those responses (`--ast-cache`, `--full-index`,
  `--incremental-sync`), which exit 1 as for any other failure;
- `FileWatcherDaemon.trigger_sync()`, whose result is the same payload. The
  watcher's status (`ast_cache mode=watch_status` → `stats`) carries the last
  one as `last_admission_error` until a later sync completes.

Fields: `error_code`, `retryable`, `retry_after_ms`, `next_action`,
`next_step`, and `cause_code`, the specific internal reason (for example
`INDEX_GENERATION_SUPERSEDED`). `error` keeps the route's existing text. The
Python exceptions behind these codes (`Superseded`, `IndexWriterBusy`, both
`IndexWriteAdmissionError` subclasses) keep their messages, which are the
`cause_code`. Nothing is written in any of these cases, and a one-shot CLI or
MCP call never retries by itself. While another writer holds the publication
lease, a writer waits up to 30 seconds for it before reporting
`INDEX_WRITER_BUSY`; it proceeds as soon as the lease is released.

Source of truth: `ADMISSION_CODES` and `CAUSE_CODES` in
[`tree_sitter_analyzer/cache/admission.py`](../tree_sitter_analyzer/cache/admission.py).

<!-- drift:index-admission-codes:start -->
| Code | retryable | retry_after_ms | next_action | Causes | What to do |
|---|---|---|---|---|---|
| `INDEX_CANDIDATE_SUPERSEDED` | true | 5000 | `recapture` | `INDEX_GENERATION_SUPERSEDED`, `INDEX_GENERATION_SOURCE_CHANGED`, `INDEX_GENERATION_DIRECTORY_CHANGED`, `INDEX_GENERATION_FOREIGN_STORE`, `INDEX_GENERATION_RETIRING`, `INDEX_WRITER_REVISION_SUPERSEDED`, `INDEX_WRITER_CACHE_REPLACED` (custom `db_path`) | Retry the same call; it captures a fresh candidate. Never replay the old candidate. |
| `INDEX_WRITER_BUSY` | true | 5000 | `recapture` | `INDEX_WRITER_BUSY` (publication lease wait timed out, or Windows could not replace the selector atomically) | Wait `retry_after_ms`, then retry; if it stays busy, stop the other writer for this project. |
| `INDEX_CANDIDATE_UNBOUND` | false | 0 | `obtain_bound_candidate` | `INDEX_CANDIDATE_UNBOUND` (Python API only: a `candidate_snapshot` passed to a default-locator write was not captured by `build_index_candidate_snapshot`; custom `db_path` caches still accept unbound candidates) | Do not replay that candidate. Capture a fresh one with `build_index_candidate_snapshot`, or omit `candidate_snapshot`, then retry. |
| `INDEX_RECOVERY_REQUIRED` | false | 0 | `recover_index` | `INDEX_GENERATION_SELECTOR_INVALID`, `INDEX_GENERATION_SELECTOR_MISSING`, `INDEX_GENERATION_PATH_UNSAFE`, `INDEX_GENERATION_LOCK_UNSAFE`, `INDEX_WRITER_STATE_MISSING` (custom `db_path`) | Do not retry. Stop every TSA process for the project, move `.ast-cache` (or the custom database) aside, replacing a linked `.ast-cache` with a real directory, then rebuild with `index action=full mode=full`. |
<!-- drift:index-admission-codes:end -->

The watcher retries only the two retryable codes, with a fresh capture after
5, 10, 20 and 40 seconds and then every 60 seconds. It does not retry
`INDEX_CANDIDATE_UNBOUND` or `INDEX_RECOVERY_REQUIRED`. `INDEX_GENERATION_SOURCE_RECHECK_INCOMPLETE` and
`INDEX_GENERATION_SOURCE_HASH_BUDGET_EXCEEDED` are not admission failures; they
keep their own `error_code`.

## Worked examples (paste-real)

Both examples were produced by running the tool classes' `execute()` directly
against this repository (commit on `develop`, 2026-06-13). Long fields are
trimmed and marked.

### Example 1 — truncation contract (`nav action=callers`)

```bash
uv run python - <<'EOF'
import asyncio, json
from tree_sitter_analyzer.mcp.tools.callers_tool import CodeGraphCallersTool

async def main():
    tool = CodeGraphCallersTool(".")
    r = await tool.execute({
        "function_name": "build_response",
        "limit": 3,
        "output_format": "json",
    })
    print(json.dumps({k: v for k, v in r.items() if k != "callers"}, indent=2))

asyncio.run(main())
EOF
```

```json
{
  "success": true,
  "verdict": "INFO",
  "data_source": "sql",
  "function": "build_response",
  "caller_count": 39,
  "callers_listed": 3,
  "listed_cap": 3,
  "truncated": true,
  "warnings": [
    "stale_cache: this index holds call edges but none was ever resolved (callee_resolution='unknown' everywhere; built before Synapse resolution or the resolution pass never ran). Run `uv run tree-sitter-analyzer --ast-cache --ast-cache-mode index --ast-cache-force` to rebuild the index and populate Synapse resolution columns."
  ],
  "next_step": "showing 3 of 39 callers — raise limit, or qualify with ClassName.method to narrow (dynamic-dispatch names like 'execute' have huge fan-in). Each caller/callee's source body is inlined under 'body' — answer directly, no Read needed. Coordinate-only entries beyond the top-N can be Read on demand."
}
```

Note the full contract: `truncated: true`, exact pre-cap total
(`caller_count: 39`), listed/cap pair (`callers_listed: 3` /
`listed_cap: 3`), and a `next_step` that interpolates the real numbers. The
`callers` list (omitted above) holds the 3 listed entries. `WARN`-grade
degradation here travels in `warnings` while the verdict stays `INFO`.

### Example 2 — verdict branching (`edit action=safe`)

```bash
uv run python - <<'EOF'
import asyncio, json
from tree_sitter_analyzer.mcp.tools.safe_to_edit_tool import SafeToEditTool

async def main():
    tool = SafeToEditTool(".")
    r = await tool.execute({
        "file_path": "tree_sitter_analyzer/mcp/utils/format_helper.py",
        "output_format": "json",
    })
    print(json.dumps(r, indent=2))

asyncio.run(main())
EOF
```

```json
{
  "success": true,
  "file_path": "tree_sitter_analyzer/mcp/utils/format_helper.py",
  "risk_level": "safe",
  "verdict": "SAFE",
  "recommendation": "SAFE to edit (health A, 0 downstream). Standard test pass after the edit is sufficient.",
  "agent_summary": {
    "summary_line": "tree_sitter_analyzer/mcp/utils/format_helper.py risk=safe verdict=SAFE health=A tests=yes",
    "verdict": "SAFE",
    "risk": "safe",
    "edit_strategy": "direct_focused_edit",
    "next_step": "Run pre-edit verification first: uv run pytest tests/unit/mcp/test_utils/test_format_helper.py tests/property/test_format_properties.py tests/regression/test_format_regression.py -q",
    "verification_command": "uv run pytest tests/unit/mcp/test_utils/test_format_helper.py tests/property/test_format_properties.py tests/regression/test_format_regression.py -q",
    "guardrails": ["preserve public API signatures"]
  },
  "health_grade": "A",
  "downstream_count": 0
}
```

(Trimmed for the page: the live response also carries `risk_factors`,
`pre_edit_checklist`, `agent_workflow`, `test_files_nearby`,
`stop_condition` / `preflight_command` / `queue_boundary_command` inside
`agent_summary`, and more.) The obligation on `SAFE` is exactly what
`agent_summary.next_step` says: run the verification command, edit, re-run.

## Drift protection

The verdict table above sits between `<!-- drift:…:start/end -->` markers.
[`tests/integration/docs/test_agent_envelope_contract_doc.py`](../tests/integration/docs/test_agent_envelope_contract_doc.py)
imports `CANONICAL_VERDICTS` and asserts exact set equality with the
documented rows — adding or removing a verdict without updating this page turns
CI red.
