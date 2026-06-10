# RFC-0012: Eliminate TOON/JSON metadata duplication in MCP responses

- **Status**: accepted (Phase 1 implemented; Phase 2 deferred)
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-08
- **Last updated**: 2026-06-08
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/mcp/utils/format_helper.py`
  - `tree_sitter_analyzer/mcp/tools/*` (66 call sites of `apply_toon_format_to_response`)
  - `tests/**` (62 test files reference `toon_content`)

## Summary

When an MCP tool returns `output_format="toon"`, the response today carries the
**same metadata twice**: once inside the `toon_content` blob (which re-encodes
the *entire* result) and again as top-level JSON keys (everything except a small
set of bulk data arrays). For metadata-heavy decision tools this makes the TOON
response **larger than the JSON it was supposed to shrink**. This RFC removes the
duplication so `toon_content` and the retained JSON metadata are **disjoint**,
without changing the locked MCP `toon` default (CLAUDE.md §1).

## Motivation

TOON exists to save tokens for LLM agents (CLAUDE.md §1: "TOON is 50-70% more
token-efficient than JSON"). That holds for **bulk/tabular** payloads. It does
**not** hold for **metadata-heavy decision tools** — measured on the real index:

| Tool | pure JSON | actual TOON-mode response | ratio |
|------|----------:|--------------------------:|------:|
| `file_health` | 2749 ch | **5394 ch** | **196%** (≈2×) |
| `analyze_scale` | 5126 ch | **8052 ch** | **157%** |

Root cause (`format_helper.py::apply_toon_format_to_response`):

1. `toon_content = format_as_toon(result)` encodes the **whole** result — all
   metadata included.
2. `_copy_metadata_fields` then copies back **every** field except a fixed set
   of bulk arrays (`results`, `matches`, `content`, `files`, `items`, `data`,
   `table_output`, `partial_content_result`, `analysis_result`).
3. So `success / verdict / agent_summary / queue_ledger / summary_line /
   verification_command / …` live in **both** halves.

`redundant_fields` only strips bulk arrays. Decision tools (`file_health`,
`change_impact`, `safe_to_edit`, `project_health`, `trace_impact`, …) have **no**
such arrays — nothing is stripped, so the response is JSON **plus** a full TOON
copy ≈ 1.6–2.0×. Every agent call pays this. The pain-feeler is the AI agent,
and token cost is real money (the exact rationale §1 cites for keeping TOON).

This RFC is **not** a §1 default flip. §1 explicitly says: *"If TOON-vs-JSON
divergence causes a real bug, fix the divergence (e.g. make TOON carry the same
scalar fields, per F7/N8), don't flip the default."* Removing the duplication is
that fix.

## Detailed design

### Invariant (target)

> In a `toon` response, **`toon_content` and the top-level JSON keys are
> disjoint.** `toon_content` carries the human/LLM-readable rendering of the
> *full* result; the retained JSON keys carry only the small, machine-branchable
> **scalar control surface** an agent reads without parsing TOON.

### Phase 1 — `compact_only` opt-in (safe, ships first)

Add a `compact_only` parameter, default `False` (byte-parity for every existing
caller). When `True`, the TOON response keeps only the **control-surface
scalars** alongside `toon_content` and drops the duplicated metadata:

```python
# format_helper.py

#: The minimal scalar control surface an agent branches on without parsing the
#: TOON blob. Everything else is recoverable from ``toon_content``. Includes
#: ``summary_line``: the canonical envelope always (re)populates it (see "MCP
#: boundary ordering" below), it is a single cheap scalar, and it is the single
#: most-read triage line — so it is retained rather than fought.
TOON_CONTROL_SURFACE: frozenset[str] = frozenset({
    "success", "format", "toon_content",
    "verdict", "error", "error_type",
    "output_format", "summary_line",
})

def apply_toon_format_to_response(
    result: dict[str, Any],
    output_format: str = "json",
    *,
    compact_only: bool = False,
) -> dict[str, Any]:
    """Apply TOON formatting.

    ``compact_only=True`` drops metadata fields already encoded inside
    ``toon_content``, keeping only ``TOON_CONTROL_SURFACE`` keys alongside the
    blob. Default ``False`` preserves the legacy (duplicating) shape so no
    existing caller or golden test changes until it opts in.
    """
```

MCP surface: tools that accept it advertise `compact_only` (boolean, default
`false`) in their input schema and forward it. CLI mirror: `--compact-toon`
(or per-tool `--<tool>-compact`) forwarding the same — parity preserved.

Measured effect (file_health): 5394 → ≈ 2750 ch (**~49%** smaller; on par with
pure JSON, but in the agent-preferred TOON shape).

#### MCP boundary ordering — the compact pass MUST run last (Codex P2, #391)

`apply_toon_format_to_response` runs **inside** each tool's `execute`, but the
MCP server boundary then post-processes every success response:
`handle_call_tool` → `ensure_canonical_success_envelope`
(`tool_registration.py:69-85`) → `_populate_summary_line` +
`_populate_agent_summary_block` (`error_recovery.py:364-433`) **unconditionally
re-add** `summary_line` and a minimal `agent_summary` (`{summary_line,
next_step, verdict}`). So stripping those inside `apply_toon_format_to_response`
alone is undone before the response ships — the documented "only
`TOON_CONTROL_SURFACE` keys" shape is **not** achievable that way, and a test
asserting on `tool.execute()` output would be testing the wrong (pre-boundary)
surface.

Resolution: the compact reduction is **idempotent and applied as the final
boundary step**, after canonical normalization. Concretely:

```python
# tool_registration.py :: handle_call_tool, AFTER ensure_canonical_*_envelope
if _is_compact_toon(result, arguments):      # format == "toon" and compact_only requested
    result = reduce_to_control_surface(result)   # keep TOON_CONTROL_SURFACE ∪ {toon_content}
```

`reduce_to_control_surface` drops everything outside `TOON_CONTROL_SURFACE`
(including the re-added `agent_summary`, `queue_ledger`, …) — all of which are
already inside `toon_content`. Because it runs last, the canonical envelope has
already done its job (and its values are in the blob); the compact pass just
removes the now-redundant top-level copies. `summary_line` and `verdict` stay
because they are in the control surface. This keeps the shipped MCP response
identical to the RFC shape and makes the size/parity assertions test the
**post-boundary** surface (i.e. an e2e `handle_call_tool` call, not
`tool.execute()`).

### Phase 2 — disjoint-by-default (the real fix, gated re-baseline)

Make duplication impossible **by default**, for all tools, by encoding
`toon_content` from the result with the **retained** metadata removed — so the
blob carries the bulk/structured payload and the JSON carries the control
surface, never both:

```python
control = {k: result[k] for k in TOON_CONTROL_SURFACE if k in result}
payload = {k: v for k, v in result.items() if k not in TOON_CONTROL_SURFACE}
toon_content = format_as_toon(payload)          # bulk/structured only
return {**control, "format": "toon", "toon_content": toon_content}
```

This is the correct contract but rewrites the `toon_content` of **every** tool,
so it lands only behind a full golden re-baseline (62 test files) and an
explicit acceptance gate. Phase 2 may be split into its own follow-up RFC if
review prefers to ship Phase 1 first and measure.

> **Same boundary caveat applies (Codex P2).** Phase 2 also runs inside
> `execute`, so the canonical post-hook would re-add `agent_summary`/
> `summary_line` at the top level — and since Phase 2 puts non-control metadata
> *into* `toon_content`, that re-add would resurrect the duplication. Phase 2
> therefore depends on the same "compact/disjoint reduction runs as the final
> boundary step" rule defined above (or on making
> `ensure_canonical_success_envelope` compact-aware). Either way the reduction
> must be idempotent and post-normalization.

#### Error handling

Unchanged: the `try/except` fallback in `apply_toon_format_to_response` still
returns the JSON result if TOON encoding raises. `compact_only` never drops
`success`/`error`/`error_type`, so failure envelopes stay fully branchable.

## Three-Surface impact (CLI ↔ MCP parity)

- MCP default stays `toon` (§1 LOCKED — **not** touched).
- CLI default stays `json` (§1 LOCKED — **not** touched).
- New `compact_only` is mirrored: MCP param `compact_only` ↔ CLI `--compact-toon`,
  1:1. A parity test asserts both reach the same builder argument.
- The asymmetry being *reduced* here (duplicated metadata) is not an intentional
  one — it is the bug §1/F7/N8 told us to fix.

## Drawbacks

- Phase 2 re-baselines 62 golden/parity test files — real churn, must be one
  reviewable diff.
- An agent that *only* parsed `toon_content` and relied on it ALSO containing
  scalar metadata would need to read the top-level keys instead (they are still
  present — and richer — as JSON). Phase 1 avoids this entirely (opt-in).
- A third response shape (`compact_only`) adds a small contract surface; capped
  by keeping it a pure subset of the existing one.

## Alternatives

- **A: flip MCP default to JSON.** ❌ Rejected — violates §1 LOCKED (user
  decision r37b). Not on the table.
- **B: do nothing.** ❌ Rejected — measured 1.6–2.0× waste on the most-called
  decision tools is exactly the cost §1 exists to avoid.
- **C: strip *all* non-scalar metadata from JSON by default (no flag).** =
  Phase 2; higher blast radius, hence gated separately rather than first.
- **D: per-tool bespoke stripping.** ❌ Rejected — 66 call sites, drift-prone;
  the fix belongs in the one formatter.

## Prior art

- TOON spec (this repo's `format_as_toon`) — compact tabular encoding; designed
  for arrays, not for duplicating scalar envelopes.
- mycelium MCP responses keep a thin control envelope + a single rendered body;
  no double-encoding. We adopt the disjoint-envelope idea.

## Test plan (RED-first)

- **Boundary (Phase 1, the Codex-P2 guard):** assert through the **full MCP
  boundary** (`handle_call_tool`, not `tool.execute()`) that a `compact_only`
  success response, *after* `ensure_canonical_success_envelope` has run, ships
  only `TOON_CONTROL_SURFACE ∪ {toon_content}` — i.e. the canonical post-hook
  did **not** re-inflate `agent_summary`/`queue_ledger` back onto the wire. This
  RED test is the regression target for the boundary-ordering fix.
- **Unit (Phase 1):** `compact_only=True` on `file_health` → response contains
  `toon_content` + only `TOON_CONTROL_SURFACE` keys; no `agent_summary`/
  `queue_ledger` duplicated at top level; `success`/`verdict`/`summary_line`
  still present.
- **Idempotence:** applying the compact reduction twice == once (it runs after
  normalization and must not depend on call count).
- **Unit:** `compact_only=False` (default) → byte-identical to today (guards
  every existing golden).
- **Size regression:** assert `len(compact) < len(legacy_toon)` for a
  metadata-heavy tool, and `compact ≤ pure_json` (the headline win), measured on
  the post-boundary response.
- **Parity:** `--compact-toon` CLI flag reaches the same builder arg as the MCP
  `compact_only` param.
- **Phase 2 (separate gate):** golden re-baseline; assert `toon_content` and
  top-level keys are disjoint for a representative tool of each family
  (bulk: `search_content`; metadata: `file_health`), again post-boundary.

## Acceptance criteria

- [x] `compact_only` param added to `apply_toon_format_to_response`, default `False`.
- [x] `TOON_CONTROL_SURFACE` defined and documented (incl. `summary_line`).
- [x] **Boundary pass**: compact reduction runs as the final step in
      `handle_call_tool`, after `ensure_canonical_success_envelope`, and is
      idempotent (Codex P2 #391).
- [x] Post-boundary test proves the canonical post-hook does not re-inflate a
      compact response (`tests/unit/mcp/test_toon_compact_only.py`).
- [x] Default-path output unchanged (existing goldens pass untouched).
- [x] At least the decision tools (`file_health`, `change_impact`, `safe_to_edit`,
      `project_health`) forward `compact_only` on MCP + CLI.
- [x] Size-regression test green (compact < legacy).
- [x] CLI↔MCP parity test green (`--compact-toon` → `compact_only`).
- [x] Docs/CODEMAPS + README updated (CLI flag count 272→273).
- [ ] (Phase 2, if accepted) disjoint-by-default with full golden re-baseline.

## What this RFC does NOT do (deferred)

- Does **not** change the MCP `toon` / CLI `json` defaults (§1 LOCKED).
- Does **not** change the TOON grammar/encoder itself.
- Does **not** touch `project_health` source-extension scope (§4 LOCKED).

## Open questions

1. Ship Phase 1 only, or commit to Phase 2 in the same RFC? (Recommendation:
   accept Phase 1 now; spin Phase 2 into a follow-up once size deltas are
   measured in the wild.)
2. ~~Should `summary_line` be in the control surface?~~ **Resolved (Codex P2,
   #391): yes.** The canonical post-hook re-populates it on every success
   anyway, it is one cheap scalar, and it is the highest-value triage line —
   added to `TOON_CONTROL_SURFACE`.
3. CLI flag shape: one global `--compact-toon` vs per-tool `--<tool>-compact`?
4. Boundary fix placement: a final reduction pass in `handle_call_tool` (this
   RFC's choice — localized, idempotent) vs threading `compact_only` into
   `ensure_canonical_success_envelope` so it skips re-population. The former
   keeps the normalizer unaware of formatting; the latter avoids a second
   walk. Open for review.
