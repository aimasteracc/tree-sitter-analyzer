# RFC-0044: Absence certificates — answer "it is not there" with proof

- **Status**: implemented (2026-11-10, PR #1939)
- **Author(s)**: agent dogfood round 2026-11-09
- **Created**: 2026-11-09
- **Last updated**: 2026-11-09
- **Tracking issue**: TBD
- **Affected source paths**:
  - `tree_sitter_analyzer/mcp/tools/callers_tool.py` (`absence` block)
  - `tree_sitter_analyzer/mcp/tools/callers_outcomes.py` / `callers_checks.py`
  - `tree_sitter_analyzer/uql/coverage.py` + `uql/output.py` (passthrough)
  - `docs/agent-envelope-contract.md`
  - tests under `tests/unit/mcp/tools/`, `tests/unit/uql/`

## Summary

When TSA answers "nothing calls this", it currently proves only that the
*caller list is complete*. Agents need the stronger, more useful claim —
**why is it absent, and can I rely on that** — e.g. "it is an entry point",
"it is a script", "no test exercises it". This RFC proposes an `absence`
object with a machine-checkable `kind` and the evidence that produced it,
emitted only when the existing completeness machinery already returned
`complete`.

## Motivation

Dogfood 2026-11-09 (`docs/dev/dogfood-trust-2026-11-09.md` §12.5) found that
agents that receive `callers: 0, completeness: complete` still grep by hand
before trusting it, because "complete" says *the list is exact*, not *why it is
empty*. That extra grep is the most common reason an agent pays 40–60 % more
tool calls on a task.

Concrete case from this repository: `main` has 342 resolved callers, but
`python -m tree_sitter_analyzer`'s entry function has none that resolution can
see; an agent cannot distinguish "nobody calls it" from "it is the entry point"
from "resolution cannot see the caller". Both are true, and only the second
justifies acting on the absence.

## Detailed design

### Response shape

```json
"absence": {
  "kind": "entry_point" | "script" | "unreferenced" | "untested" | "unknown",
  "confidence": "proven" | "possible",
  "evidence": [
    {"kind": "console_script", "detail": "pyproject.toml [project.scripts] -> tree_sitter_analyzer"},
    {"kind": "dunder_main", "detail": "tree_sitter_analyzer/__main__.py:11"}
  ],
  "next_step": "..."
}
```

- Emitted **only** when `completeness == "complete"` for the underlying
  question; otherwise omitted (an incomplete answer may not certify absence).
- `kind: "unknown"` is allowed only with `confidence: "possible"` and at least
  one evidence entry explaining what could not be checked.
- Existing top-level fields are unchanged; this is additive.

### Detection rules (bounded, no new index)

| kind | proven when (all must hold) |
|---|---|
| `entry_point` | the target is named in `[project.scripts]` / `[tool.poetry.scripts]`, or it is the `__main__` guard target |
| `script` | the declaring file is under a `scripts/` directory or is executable with a shebang, and the target is module-level |
| `unreferenced` | caller list empty **and** every inbound check ran with no unresolved/name-only sites (already encoded by `completeness_checks`) |
| `untested` | `test_map` empty **and** the test-detection scan covered the project (existing completeness reason set) |

Each rule reads at most the manifest file, the declaring file, and the already
computed completeness checks; no directory walk is added.

### MCP surface

`nav action=callers` and `nav action=test_map` gain the optional `absence`
field. No new action, no new parameter.

### Error handling

If a rule cannot run (manifest unreadable, declaration file excluded), the
answer drops to `kind: "unknown"`, `confidence: "possible"`, with the reason in
`evidence[].detail` — never silently `unreferenced`.

### Concurrency / async

Rules are synchronous reads over already-open connections; no new locking.

## Three-Surface impact (CLI ↔ MCP parity)

- CLI: no new flag. `--callers` / `--test-map` responses carry `absence`.
- MCP: `nav action=callers` / `action=test_map` carry `absence`.
- UQL: passthrough only — `symbol('x').callers()` keeps the stage coverage and
  may expose `absence` from its `callers` stage verbatim.
- Parity contract: no flag, so codemap flag count is unchanged; the mcp-tools
  codemap row text gains "absence".

## Drawbacks

- More payload on empty answers (≈200 B) — cheaper than the hand grep it
  replaces, but it is not free.
- Rule precision: "script" and "entry point" are heuristics; a wrong proof is
  worse than no proof, so every rule must be conservative and default to
  `unknown`.
- Adds a second meaning to "complete" answers; reviewers must resist extending
  `kind` into a general taxonomy.

## Alternatives

- **Alternative A: a separate `nav action=absence` query.** Rejected: doubles
  the round-trip for a fact that is only useful next to the empty answer.
- **Alternative B: prose `next_step` only.** Rejected: agents cannot branch on
  English; the dogfood finding was precisely that prose is not consumed.
- **Alternative C: return absence even when incomplete.** Rejected: it would
  let an unproven absence look authoritative, the exact failure mode
  RFC-0040 exists to prevent.

## Prior art

- rust-analyzer distinguishes "no references" from "not analysed"; its
  `unresolved` diagnostics are the closest analogue to `confidence: possible`.
- Sourcegraph's `type:diff` empty results carry no provenance — the gap this
  RFC fills.
- Codegraph reports `callers: []` with no certificate; we adopt its cheap
  empty-answer path and diverge only in carrying evidence.

## Test plan (RED-first)

1. `tests/unit/mcp/tools/test_callers_reason_evidence.py`:
   - empty callers on a `[project.scripts]` target → `absence.kind == "entry_point"`, `confidence == "proven"`;
   - empty callers with an unresolved site → no `absence` field at all;
   - unreadable manifest → `kind == "unknown"`, `confidence == "possible"`.
2. `tests/unit/mcp/tools/test_test_map*.py`: `untested` only when the scan is complete.
3. `tests/unit/uql/test_uql_output.py`: absence is passed through verbatim and never invented by UQL.
4. Dogfood: re-run the 2026-11-09 transcript and count manual greps on empty answers (target: 0).

## Acceptance criteria

- [x] `absence` emitted only on `complete` answers, with evidence
  (`absence_certificate`; proven kinds `unreferenced` / `entry_point` / `script` / `untested`)
- [x] `unknown`/`possible` covers every non-runnable rule; no silent absence
  (`_unproven_absence` names the open sites; `NOT_FOUND` carries no certificate)
- [x] CLI↔MCP parity tests green; no flag-count change
  (no new flag/action; parity + codemap contracts unchanged and green)
- [x] `docs/agent-envelope-contract.md` documents the field and its proof rule
- [x] Docs/CODEMAPS updated (mcp-tools row text)

Implemented by PR #1939 (`da7f94105`…`a30f5b916`); the UQL counterpart ships as a
weaker `absence_hint` (`possible`) because UQL has stage coverage, not the 13
RFC-0040 caller checks, and points at `nav action=callers` for the certificate.

## What this RFC does NOT do (deferred)

- No general "absence of any symbol/edge" query language.
- No absence certificates for `impact()` / `callees()`.
- No storage of certificates; they are computed per answer.

## Open questions

1. Should `entry_point` also cover pytest fixtures / CLI argument callbacks?
2. Is `confidence: possible` ever actionable, or should it be omitted entirely?
3. Should `absent` answers still include `answer_etag` / delta semantics
   (§12.1–12.2) so repeated empty answers stay cheap?
