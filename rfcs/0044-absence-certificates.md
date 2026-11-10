# RFC-0044: Absence certificates — answer "it is not there" with proof

- **Status**: implemented (2026-11-10, PR #1939)
- **Author(s)**: agent dogfood round 2026-11-09
- **Created**: 2026-11-09
- **Last updated**: 2026-11-10
- **Tracking issue**: TBD
- **Affected source paths**:
  - `tree_sitter_analyzer/mcp/tools/callers_agent_fields.py` (`absence` rules)
  - `tree_sitter_analyzer/mcp/tools/callers_tool.py` (wiring)
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
  "kind": "entry_point" | "unreferenced" | "untested" | "unknown",
  "confidence": "proven" | "possible",
  "evidence": [
    {"kind": "complete_call_graph", "detail": "every required caller check ran; ..."},
    {"kind": "console_script", "detail": "[project.scripts] tsa = \"pkg.cli:main\""}
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
| `entry_point` | a `[project.scripts]` / `[tool.poetry.scripts]` entry names exactly the declaring module file (path-segment boundary; flat or `src/` layout; `pkg:f` → `pkg/__init__.py`) and an undotted attribute that the file defines as a module-level function |
| ~~`script`~~ | **withdrawn** (PR #1939 review): a shebang / `scripts/` location / `__main__.py` is a property of the file, not evidence about one function in it — see below |
| `unreferenced` | caller list empty **and** every inbound check ran with no unresolved/name-only/declaring-file/module-level/non-call sites **and** the answer is not stale |
| `untested` | never `proven` today: `test_map` follows direct test callers plus one helper hop only, so indirect coverage through non-test callers is unchecked; emitted as `confidence: "possible"` with `no_direct_test_caller` evidence |

**Why `script` / `__main__` were withdrawn.** A function that a shebang script or a
`__main__.py` really runs is called from that file's module-level code, so it already has a
`<module>` caller and needs no certificate. A function with zero callers in such a file is not
run by it — certifying it "not dead code" would be a proof weaker than its evidence. Such a
function now gets plain `unreferenced` (complete answer) or the `unknown`/`possible` downgrade.

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

## Identification vs absence (added 2026-11-10, during implementation)

A smoke test found the rules firing less often than specified: `entry_point` / `script` were gated
on `completeness == "complete"`, but a real entry point resolves to `NOT_FOUND` with
`NON_CALL_REFERENCES` (the declaring file holds non-call references), so the certificate never
appeared for exactly the objects it was written for.

The distinction: a console-script `entry_point` is an **identification fact** — the object is
invoked from outside the analysed graph — so it holds without a complete caller list. It ships
with `identification_only: true` and `symbol_defined` evidence (the declaring file defines the
function at module level) in that case. `unreferenced` is a **negative claim** and keeps
requiring `complete`. `SYMBOL_NOT_DEFINED` still yields no certificate at all: not being indexed
is not being an entry. (The `script` / `__main__` identifications were withdrawn in review; see
the detection-rules table.)


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
  (`absence_certificate` in `callers_agent_fields.py`; proven kinds `unreferenced` /
  `entry_point`; `untested` is `possible` only; `script` withdrawn in review —
  pinned by `tests/unit/mcp/tools/test_callers_agent_fields_trust.py`)
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
