# Agent Envelope Contract

One page for agents and MCP-client authors: what every tree-sitter-analyzer
(TSA) MCP response envelope guarantees, what each `verdict` obliges you to do,
how honest truncation works, and which fields survive `compact_only`
compaction. Everything here is backed by source constants and protected
against drift by
[`tests/integration/docs/test_agent_envelope_contract_doc.py`](../tests/integration/docs/test_agent_envelope_contract_doc.py),
which imports the live constants and fails when this page and the code
disagree.

For TOON *syntax* (the format inside `toon_content`), see the
[TOON Format Guide](toon-format-guide.md). For the tool surface itself, see
the [MCP Tools Codemap](CODEMAPS/mcp-tools.md).

## The minimum envelope

Every tool response is a JSON object. The typed contract lives in
[`tree_sitter_analyzer/mcp/tools/tool_response.py`](../tree_sitter_analyzer/mcp/tools/tool_response.py)
(`ToolResponse` + `validate_tool_response`):

- `success` (bool) — always present. `true` = the tool ran end-to-end.
- `error` (str) — present **iff** `success` is `false`. Human-readable;
  error envelopes usually also carry `error_type` and a recovery `hint`.
- `verdict` (str) — when present, it is EXACTLY one of the canonical strings
  below. On TOON/JSON success paths a missing verdict is back-filled with
  `INFO` by the safety net in
  [`tree_sitter_analyzer/mcp/utils/format_helper.py`](../tree_sitter_analyzer/mcp/utils/format_helper.py)
  (`apply_toon_format_to_response`), so agents can always branch on it.
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

## Control surface (`compact_only`, RFC-0012)

TOON responses (`output_format: "toon"`, the MCP default) put the full payload
in `toon_content` and keep scalar metadata alongside it. Passing
`compact_only: true` strips even that metadata down to the **control
surface** — the only keys an agent may branch on without parsing the TOON
blob. Source of truth: `TOON_CONTROL_SURFACE` in
[`tree_sitter_analyzer/mcp/utils/format_helper.py`](../tree_sitter_analyzer/mcp/utils/format_helper.py);
the reduction (`reduce_to_control_surface`) is idempotent and is re-applied at
the MCP boundary
([`tree_sitter_analyzer/mcp/server_utils/tool_registration.py`](../tree_sitter_analyzer/mcp/server_utils/tool_registration.py))
*after* canonical-envelope normalization re-adds `summary_line`.

<!-- drift:control-surface:start -->
| Field | Why it survives compaction |
|---|---|
| `success` | The one mandatory branch: did the call work at all. |
| `format` | `"toon"` marker — tells the client the payload is in `toon_content`. |
| `toon_content` | The full TOON-encoded payload (everything stripped from the top level is recoverable here). |
| `verdict` | Canonical branching verdict (table above). |
| `error` | Failure description on `success: false`. |
| `error_type` | Machine-stable error category for programmatic handling. |
| `output_format` | Echo of the requested format. |
| `summary_line` | Highest-value one-line triage signal; re-populated at the boundary on every success anyway. |
| `hint` | Recovery hint on error envelopes — the sharpest edge an agent must not have to dig out of the blob. |
| `file_path` | Echo of the call's subject file. |
| `pr_url` | Echo of the PR a review-tool call targeted. |
| `pr_number` | Echo of the PR number, same rationale. |
| `deprecation` | Legacy-name shim migration warning — the shim's only in-band signal, injected after `toon_content` is built, so it must survive. |
<!-- drift:control-surface:end -->

Everything else in a TOON response is duplicated metadata and is dropped
under `compact_only`; parse `toon_content` when you need the full payload.

## Worked examples (paste-real)

All three were produced by running the tool classes' `execute()` directly
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
  "data_source": "parse",
  "function": "build_response",
  "caller_count": 39,
  "callers_listed": 3,
  "listed_cap": 3,
  "truncated": true,
  "warnings": [
    "stale_cache: most edges have callee_resolution='unknown'. Run `uv run tree-sitter-analyzer --ast-cache --ast-cache-mode force` or rebuild with `--mode resolve` to populate Synapse resolution columns."
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

### Example 3 — control surface (`health action=file`, TOON + `compact_only`)

```bash
uv run python - <<'EOF'
import asyncio, json
from tree_sitter_analyzer.mcp.tools.file_health_tool import FileHealthTool

async def main():
    tool = FileHealthTool(".")
    r = await tool.execute({
        "file_path": "tree_sitter_analyzer/mcp/utils/format_helper.py",
        "output_format": "toon",
        "compact_only": True,
    })
    print("top-level keys:", sorted(r.keys()))
    print(json.dumps(r, indent=2))

asyncio.run(main())
EOF
```

```text
top-level keys: ['file_path', 'format', 'success', 'summary_line', 'toon_content', 'verdict']
```

```json
{
  "format": "toon",
  "toon_content": "success: true\nfile_path: tree_sitter_analyzer/mcp/utils/format_helper.py\ngrade: B\nverdict: SAFE\ntotal_score: 89.5\n...<trimmed — full payload lives here>",
  "success": true,
  "file_path": "tree_sitter_analyzer/mcp/utils/format_helper.py",
  "verdict": "SAFE",
  "summary_line": "tree_sitter_analyzer/mcp/utils/format_helper.py grade=B score=89.5 smells=1 weakest=dependencies"
}
```

Every top-level key is a member of `TOON_CONTROL_SURFACE` (control-surface
keys that this particular call has no value for — `error`, `hint`,
`pr_url`… — are simply absent). The agent branches on
`success`/`verdict`/`summary_line` and only parses `toon_content` when it
needs the dimensions/smells detail.

## Drift protection

The verdict table and the control-surface table above sit between
`<!-- drift:…:start/end -->` markers.
[`tests/integration/docs/test_agent_envelope_contract_doc.py`](../tests/integration/docs/test_agent_envelope_contract_doc.py)
imports `CANONICAL_VERDICTS` and `TOON_CONTROL_SURFACE` and asserts exact set
equality with the documented rows — adding/removing a verdict or a
control-surface field without updating this page turns CI red.
