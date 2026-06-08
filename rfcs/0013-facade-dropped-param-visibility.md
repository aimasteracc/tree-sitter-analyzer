# RFC-0013: Facade dropped-parameter visibility (no silent scope/filter drops)

- **Status**: draft
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-09
- **Last updated**: 2026-06-09
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/mcp/tools/facade_tool.py` (`_project_args`, `execute`)
  - `tests/unit/mcp/tools/test_facade_tool.py`
  - `tests/unit/test_agent_contracts.py` (envelope contract)

## Summary

When a caller passes a parameter that the routed inner tool does not declare,
the facade's `_project_args` whitelist **silently drops it**. The agent's intent
(scope, filter, target, mode) is lost with no signal, and the tool returns a
confident *whole-project* default. This RFC makes every dropped caller parameter
**visible** in the response (an `ignored_params` field + a `WARN`-tinged
`agent_summary.next_step`), so an agent can detect that its filter was not
honored instead of acting on a wrong-scoped answer.

## Motivation

The zero-defect MCP audit (2026-06-09) found four HIGH "silent wrong success"
findings. Three were fixed by mapping the specific param to the inner's
identifier (structure-01 `symbol`→`class_name`, project-05 `path`→`roots`) or by
honoring an existence signal (edit-08). The **fourth (viz-08)** has no clean
per-tool fix: `uml`/`graph` are whole-project tools that do not (and should not)
scope by `file_path`, yet `viz action=uml file_path="does/not/exist.py"`
returns a full 209-node project diagram — because the facade dropped `file_path`
before the inner saw it. The common root cause across all four is **systemic**:

> The facade silently discards any caller param not in the inner's schema.

An AI agent cannot tell the difference between "the filter was applied and the
whole project genuinely matched" and "the filter was silently dropped." That
ambiguity is exactly what produces confident wrong answers. The pain-feeler is
the agent; the cost is acting on bad scope. Making drops visible fixes viz-08
*and* hardens every current and future facade action against this class.

## Detailed design

### Data structures

`_project_args` already computes the inner's declared property names
(`inner_props`) and the cleaned caller args. It currently returns only the
whitelisted subset. We additionally compute the **dropped set**:

```python
# facade control keys (action/scope/mode/output_format/compact_only/...) are
# infrastructure, never "intent" — they must NOT be reported as ignored.
_NEVER_REPORT = _FACADE_CONTROL_KEYS | {"output_format", "compact_only"}

def _project_args(self, inner, args):
    cleaned = {k: v for k, v in args.items() if k not in _FACADE_CONTROL_KEYS}
    inner_props = self._inner_property_names(inner)
    # ... existing R3 normalize (symbol->function_name / ->class_name) ...
    if not inner_props:
        return cleaned, []  # cannot whitelist; nothing dropped
    projected = {k: v for k, v in cleaned.items() if k in inner_props}
    dropped = sorted(
        k for k in cleaned
        if k not in inner_props and k not in _NEVER_REPORT
    )
    return projected, dropped
```

### Algorithms

In `FacadeTool.execute`, after the inner returns its (dict) result, if `dropped`
is non-empty **and** the result is a success dict, annotate it — without
overwriting any field the inner set:

```python
projected, dropped = self._project_args(inner, arguments)
result = await inner.execute(projected)
if dropped and isinstance(result, dict) and result.get("success") is not False:
    result.setdefault("ignored_params", dropped)
    # surface it where agents look: agent_summary.next_step
    summary = result.get("agent_summary")
    if isinstance(summary, dict):
        note = (
            f"NOTE: these params are not supported by '{self.facade_name}"
            f" action={arguments.get('action')}' and were ignored: {dropped}. "
            "The result is NOT scoped by them."
        )
        summary["next_step"] = (note + " " + summary.get("next_step", "")).strip()
    result.setdefault("verdict", result.get("verdict", "INFO"))
return result
```

Bespoke routes (`_clean_bespoke_args`) own their own arg handling and are **out
of scope** (they do not whitelist, so they drop nothing).

### MCP surface (facade + action)

No new tool, action, or input param. Purely an **additive output field**
(`ignored_params`) on success responses where the facade dropped caller intent.
Default behavior (nothing dropped) is byte-identical to today.

### Error handling

Unchanged. `ignored_params` is only attached to success responses; error
envelopes are produced upstream and are not annotated.

## Three-Surface impact (CLI ↔ MCP parity)

`_project_args` is MCP-facade-only; the CLI dispatches to inner tools directly
and already rejects unknown flags via argparse (a hard error, not a silent
drop). So the surfaces converge in spirit: CLI = hard reject, MCP = soft
visible-ignore (the MCP facade cannot hard-reject because one facade multiplexes
many inners with disjoint param sets). This asymmetry is **intentional and
documented here**; a parity test asserts the CLI rejects an unknown flag while
the MCP facade reports it in `ignored_params`.

## Drawbacks

- A new optional output field is one more shape for consumers to learn (capped:
  it only appears when something was actually dropped).
- Some legitimately-redundant params (e.g. a caller passing both `symbol` and a
  synonym) could be reported. Mitigated by the R3 normalize running first and by
  `_NEVER_REPORT`.
- It does not *prevent* the drop — it only makes it visible. (Hard rejection was
  considered and rejected; see Alternatives.)

## Alternatives

- **A: Hard-reject unknown params at the facade.** ❌ Rejected — one facade
  routes many inners with disjoint schemas; a param valid for one action is
  "unknown" for its sibling, so strict rejection would break legitimate
  multi-action ergonomics and force agents to over-specify.
- **B: Per-tool fixes only (status quo after structure-01/project-05).** ❌
  Rejected — does not cover viz-08 (uml is whole-project by design) and leaves
  every future facade action exposed to the same silent-drop class.
- **C: Map every plausible alias (path→roots, file_path→…) per inner.** ❌
  Partial and drift-prone; cannot express "uml has no file scope."

## Prior art

- GraphQL/JSON-RPC servers typically reject unknown fields; we cannot (multiplexed
  facade) so we adopt the *visible-ignore* pattern instead.
- mycelium MCP keeps a thin control envelope + explicit body; surfacing
  ignored input mirrors its "tell the agent what actually happened" stance.

## Test plan (RED-first)

- **Unit**: `_project_args` returns `(projected, dropped)`; a caller param absent
  from the inner schema (and not a control key) appears in `dropped`.
- **Unit**: control keys (`action`/`scope`/`mode`/`output_format`/`compact_only`)
  never appear in `dropped`.
- **Unit**: `execute` attaches `ignored_params` + annotates `agent_summary.next_step`
  on a success result; does NOT attach when nothing was dropped (byte-identical).
- **Integration (viz-08)**: `viz action=uml file_path="does/not/exist.py"` →
  success diagram **plus** `ignored_params == ["file_path"]` and a next_step note.
- **Integration**: `viz action=uml diagram="bogus"` still hard-errors (inner
  validation unchanged — illegal *declared* param value is an error, not an ignore).
- **Parity**: CLI rejects an unknown flag (argparse error) while MCP reports it.
- **Regression**: structure-01/project-05/edit-08 PRs stay green (the mapped
  params are consumed, so they are NOT reported as ignored).

## Acceptance criteria

- [ ] `_project_args` returns `(projected, dropped)`; `_NEVER_REPORT` excludes control keys.
- [ ] `execute` attaches `ignored_params` + next_step note on success when params were dropped.
- [ ] Default path (nothing dropped) is byte-identical (existing goldens untouched).
- [ ] viz-08 integration test green (uml reports `ignored_params`).
- [ ] CLI↔MCP parity test green.
- [ ] Docs/CODEMAPS updated (envelope field documented).

## What this RFC does NOT do (deferred)

- Does **not** hard-reject unknown params (Alternative A).
- Does **not** add file-scoping to `uml`/`graph` (they remain whole-project; the
  fix is making the unsupported param visible, not inventing a capability).
- Does **not** change the TOON/JSON defaults (§1 LOCKED) or any verdict ladder.
- Does **not** touch bespoke routes.

## Open questions

1. Field name: `ignored_params` vs `unsupported_params` vs `dropped_params`?
2. Should a drop tint the top-level `verdict` to `WARN` (currently keeps the
   inner's verdict, only annotates next_step)? WARN is louder but may over-fire
   for harmless redundant params.
3. Should `output_format`/`compact_only` ever be reportable, or always control?
