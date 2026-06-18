# RFC-0018: Correct TOON Wire + Envelope Normalization (the real token win)

- **Status**: draft (revised after 3-arm adversarial review, 2026-06-18)
- **Author(s)**: @aisheng.yu (PM) + dogfood investigation 2026-06-18
- **Created**: 2026-06-18
- **Last updated**: 2026-06-18 (rev 2 — incorporates review findings; **Part B
  "adaptive selection" DROPPED**, encoder-conformance promoted to a hard
  prerequisite, Part A re-scoped to keep contract echoes)
- **Tracking issue**: TBD
- **Supersedes**: extends RFC-0012 (toon-json-dedup, implemented). RFC-0012's
  Phase 1/2 reduced *duplication between* `toon_content` and the top level; this
  RFC fixes the actual cost sink — TOON is **wrapped wrong** (re-serialized
  inside `json.dumps(indent=2)`), and our **TOON encoder is not round-trippable**
  so we cannot safely send it raw yet.
- **Affected source paths**:
  - `tree_sitter_analyzer/formatters/_toon_encoder_string_helpers.py` (quoting gap)
  - `tree_sitter_analyzer/formatters/` (NEW: a TOON decoder + round-trip test)
  - `tree_sitter_analyzer/mcp/server_utils/tool_registration.py` (the wire: `_json_dumps`)
  - `tree_sitter_analyzer/mcp/utils/format_helper.py` (TOON wrap)
  - `tree_sitter_analyzer/mcp/tools/utils/file_health_response.py` + sibling decision tools (payload shape)
  - `tests/unit/mcp/test_output_cost_invariants.py` (token + round-trip oracles)

## Summary

The MCP server sends a TOON response as `json.dumps({…, toon_content:
"<TOON text>"}, indent=2)` — pretty-printed JSON containing an *escaped TOON
string*, paying the JSON envelope **plus** the TOON text. Measured: toon-mode is
**1.66–1.88× JSON** today; sending the **raw TOON document** would be **~0.76×**
(a 2.5× swing) — the entire win is in the wire, not the format. But we cannot
flip the wire yet: our encoder emits scalar-ambiguous strings unquoted
(`"100.0"`→`100.0`) and there is **no decoder**, so raw TOON is **not
round-trippable** — promoting it to the authoritative payload would silently
corrupt string fields. This RFC therefore sequences: **(1) make the encoder
spec-conformant + add a decoder + round-trip oracle** (prerequisite), **(2) wire
the raw TOON document** (the win), **(3) normalize the envelope payload**
(format-independent hygiene, ~90% of a response is redundant) **(4) re-base the
cost oracle on tokens, not bytes, alongside the round-trip oracle.** The
`output_format="toon"` default is untouched and TOON stays the wire for every
tool — **CLAUDE.md §1 LOCK is fully honored, no toon→json output flip.**

> **Dropped in rev 2:** the original "adaptive format selection" (route
> scalar-heavy payloads to JSON) is **removed** — review measured raw TOON
> beating JSON on *every* shape (0.56–0.70× even for pure scalar objects), so a
> JSON fallback only forfeits 30–44% and would re-litigate §1. TOON-always-raw is
> simpler and strictly better.

## Motivation

Measured on `develop` @ `304db4b4` (2026-06-18), `file_health`, tokens via
`tiktoken cl100k_base` (the metric that matters — TOON is *Token*-Oriented):

| Wire the server emits | tokens | vs JSON |
|---|---:|---:|
| json mode | ~161 | 1.00× |
| **toon mode (today: `json.dumps(envelope+toon_content)`)** | ~302 | **1.88×** |
| **raw TOON document (this RFC)** | ~122 | **0.76×** |

Root causes, ranked by blast radius:

**RC-2b (dominant) — TOON is wrapped wrong.** `tool_registration.py:~98` emits
`TextContent(text=json.dumps(result, indent=2))` where `result.toon_content` is a
TOON string. The model receives JSON envelope + escaped TOON + indentation —
both formats paid at once. Fixing only this delivers the full 1.88×→0.76× swing.
TOON is designed to *be* the wire payload (`text/toon`), not a JSON string field.

**RC-0 (blocking RC-2b) — our TOON is not round-trippable.**
`_toon_encoder_string_helpers.py:needs_quotes` only quotes on structural chars,
so a string `"100.0"`/`"true"`/`"null"`/`"42"` is emitted bare and a
spec-compliant decoder reconstructs a float/bool/None/int — **lossy**. There is
**no TOON decoder in the repo at all** (0 hits for `decode_toon`/`from_toon`), so
the "lossless" property RFC-0012 and the spec assume is **unimplemented and
untested**. Until this is fixed, raw TOON on the wire silently corrupts any
string field that looks numeric/boolean (versions, grades like `"100.0"`, ids).

**RC-1 (independent, format-agnostic) — the payload is ~90% redundant.**
`file_health` (1406 B JSON, 21 fields) carries the file path 4× (20% of the
response), `line_count == lines`, an `agent_next_action` block shipping
`mcp_command:""`/`cli_command:""`/`post_edit_commands:[]`, and four identical
score keys. The genuinely-unique signal is ~80–120 B. This is true in JSON mode
too — it is payload hygiene, not a format problem. **Correction (review):** the
*test-pinned* costly field is `summary_line` (48 test files), `health_score`
(13), `agent_next_action` shape (25) — **not** the score aliases
`total_score`/`overall_score` (0 test pins). RC-1's fix must target the former.

## Detailed design

### Part 1 (PREREQUISITE) — make TOON round-trippable

1. **Quote scalar-ambiguous strings.** Extend `needs_quotes` to also quote any
   string that would otherwise parse as a TOON number / `true` / `false` /
   `null` (per spec v3.2 §scalars). Add fixtures: `"100.0"`, `"true"`, `"null"`,
   `"42"`, `"1e5"`, `"-3"` must survive round-trip as strings.
2. **Add a `ToonDecoder`.** New module `formatters/toon_decoder.py` implementing
   `decode_toon(text) -> dict|list`, spec-conformant, including array-table
   header+rows. Sparse/union rows (`[{a,b},{a}]`) must round-trip unambiguously —
   define the missing-cell encoding explicitly (emit explicit `null`, not an
   empty trailing cell) so absent ≠ `""` ≠ `0`.
3. **Round-trip oracle (correctness, not cost).**
   `assert decode_toon(format_as_toon(x)) == x` over a corpus covering scalars,
   nested objects, uniform arrays, sparse arrays, comma/quote-bearing strings.

```python
# formatters/toon_decoder.py  (NEW)
def decode_toon(text: str) -> dict | list:
    """Parse a TOON document back to the JSON data model. Inverse of
    format_as_toon. MUST satisfy decode_toon(format_as_toon(x)) == x."""
```

### Part 2 (THE WIN) — wire the raw TOON document

Gated behind Part 1. When the response is TOON, `TextContent.text` **is** the
TOON document; verdict/success live as TOON keys at the top, so no JSON envelope
is needed.

```python
# tool_registration.py
def _emit(result: dict) -> list[TextContent]:
    if result.get("format") == "toon" and "toon_content" in result:
        return [TextContent(type="text", text=result["toon_content"])]
    return [TextContent(type="text", text=_json_dumps(result))]
```

**Consumer migration (mandatory, same PR):** ~35 test files + any external client
call `json.loads(wire)` to read `verdict`/`success`. They must switch to
`decode_toon` (now available from Part 1) or the server must offer a
`output_format="json"` opt-out path that those callers use. The
`docs/agent-envelope-contract.md` canonical example updates to show the TOON
document. Error envelopes (`success=False`) stay JSON — small, scalar, must be
maximally parseable.

### Part 3 (INDEPENDENT) — envelope payload normalization (format-agnostic)

Applies on **both** CLI(JSON) and MCP surfaces; shrinks both. **Re-scoped after
review** — only the genuinely-redundant fields, NOT the contract echoes:

- **DO collapse** the 4 identical score keys → `score` (verified identical by
  construction: `file_health_response.py:141-144`, `project_health_tool.py:388`).
  Keep aliases for **one deprecation release** (re-opens the r37f7-U4 "agent read
  None" incident otherwise).
- **DO omit** empty `agent_next_action` command fields (no consumer pins the
  empty shape; aligns with Issue #446 intent).
- **DO drop** only `agent_summary.grade` / `agent_summary.score` (0 test pins).
- **DO NOT touch** `agent_summary.verdict` and `agent_summary.summary_line` —
  **these are enforced contracts**, not redundancy: the r37u cross-tool
  invariant (`_AGENT_SUMMARY_KEYS = {"summary_line","verdict"}`, 10+ test files)
  and Issue #446 deliberately make `agent_summary` the canonical dual-read home.
  Their value being identical to the top level is the *point* — it guarantees an
  agent can branch from either location. Dropping them = the exact "agent info
  not transmitted" failure this RFC must avoid.
- **DO NOT collapse** the `file` ↔ `file_path` dual-key in `project_health`
  (documented cross-tool compat vocabulary, `project_health_tool.py:378`).
- **Path-once** applies only to *raw repetition* (e.g. emit the path at top level
  and let `summary_line`/`verification_command` be the only other carriers).

### Error handling / concurrency

Unchanged from today except the wire branch (Part 2). All new helpers return new
dicts (no mutation, per coding-style immutability rule).

## Three-Surface impact (CLI <-> MCP parity)

- MCP default stays `toon`; CLI default stays `json` (§1 intentional asymmetry,
  unchanged). **No toon→json output flip anywhere** — Part B (which would have
  caused one) is dropped.
- Part 3 changes both surfaces identically (same fields, one copy each) → parity
  preserved. The existing parity test `test_n7_file_health_smell_parity.py` must
  stay green and is named as an acceptance gate.
- Part 2 (raw wire) is MCP-only.

## Drawbacks

- **Encoder/decoder work is real** (Part 1) and must land before any wire change
  — but it also fixes a latent correctness bug (type-lossy TOON) that exists
  today regardless of this RFC.
- **Consumer contract churn** (Part 2): ~35 `json.loads(wire)` call sites +
  `agent-envelope-contract.md` migrate in lockstep. High blast radius — gated,
  announced, version-noted.
- **Re-baseline surface (corrected):** ~155 envelope-pinning test files + 44 JSON
  goldens + 18 TOON goldens — larger and differently shaped than RFC-0012's "62".
  Part 3 hits the JSON goldens + unit pins; Part 2 hits the TOON goldens.
- **Score-alias removal** reverses the deliberate r37f7-U4 alias decision →
  one-release deprecation window is mandatory, not optional.

## Alternatives

- **Alt A — Reword the README only** (drop the false "0.52× on decision tools",
  keep "50-70% on bulk/tabular"). Ships *now* as a stopgap (separate issue),
  but concedes the loss instead of fixing it. Not the primary fix.
- **Alt B — Adaptive format selection (route scalar payloads to JSON).**
  **REJECTED by review:** raw TOON beats JSON on every measured shape
  (0.56–0.70×), so a JSON branch forfeits 30–44% and re-litigates §1. Removed.
- **Alt C — Keep a thin JSON header + inline TOON only for bulk bodies.** A
  middle path if full raw-TOON migration of the 35 call sites is judged too
  risky for one release. Preserves `json.loads(wire)` for the header. Listed as
  the fallback if Part 2's migration proves too large to land atomically.
- **Alt D — Drop TOON entirely.** Violates §1; throws away the genuine
  array/tabular win. Rejected.

## Prior art

- **TOON spec v3.2** (`toon-format/spec`, `toonformat.dev`): TOON is the wire
  format (`text/toon`), lossless to JSON, requires quoting scalar-ambiguous
  strings (the gap Part 1 fixes); 39.9% fewer tokens on mixed data. Reference
  decoders exist in TS/Python (`xaviviro/python-toon`) — Part 1 can port rather
  than invent.
- **RFC-0012**: established decision tools have no bulk arrays to strip; this RFC
  concludes the fix is the wire + payload hygiene, not more denylist tuning.

## Test plan (RED-first)

1. `test_toon_roundtrip_scalars` — `"100.0"`/`"true"`/`"null"`/`"42"` survive as
   strings (RED today: decode to non-string types). **Correctness gate for Part 1.**
2. `test_toon_roundtrip_corpus` — `decode_toon(format_as_toon(x)) == x` over the
   corpus incl. sparse arrays (RED today: no decoder exists).
3. `test_wire_toon_is_raw_document` — emitted `TextContent.text` parses via
   `decode_toon` and is **not** `json.dumps`-wrapped (Part 2).
4. `test_decision_envelope_single_score` — exactly one score key (RED: 4).
5. `test_no_empty_guidance_fields` — no `""`/`[]` command fields shipped.
6. `test_agent_summary_keeps_contract_echoes` — `agent_summary.verdict` and
   `.summary_line` **still present and equal to top level** (guards against
   over-aggressive normalization — protects "agent info transmitted").
7. **Token cost oracle** (replaces perma-xfail): measure **tokens of the emitted
   wire** via tiktoken; assert `tokens(toon_wire) < tokens(json_wire)` for
   decision tools (relationship form, per the §0 documented exception) → flips
   the strict-xfail to enforced pass. **No `<= 0.6×` ceiling** (hand-waved bound
   violates the exact-assertion LOCK; use a `<` relationship, or an exact re-pin).

## Acceptance criteria

- [ ] Part 1: `needs_quotes` quotes scalar-ambiguous strings; `ToonDecoder`
      lands; tests 1-2 (round-trip) green. **Prerequisite — merges first.**
- [ ] Part 2: raw-TOON wire; ~35 `json.loads(wire)` consumers migrated to
      `decode_toon` (same PR); `agent-envelope-contract.md` updated; test 3 green.
- [ ] Part 3: score collapse (+ 1-release alias deprecation), empty-guidance
      omitted, `agent_summary.grade/score` dropped; tests 4-6 green; contract
      echoes preserved.
- [ ] Part 4: token cost oracle re-based; strict-xfail flipped to enforced pass;
      round-trip oracle in CI.
- [ ] Goldens re-baselined (44 JSON + 18 TOON) in dedicated commits per PR.
- [ ] `test_n7_file_health_smell_parity` stays green (CLI↔MCP parity gate).
- [ ] README "Why TSA" efficiency claim updated to the now-true measured numbers.
- [ ] Codex review triaged; all P1/P2 resolved.

## Phasing (per review — PRs, not the 4 abstract "Parts")

- **PR 1**: Part 1 (encoder conformance + decoder + round-trip oracle). Self-
  contained correctness fix; mergeable alone; unblocks everything.
- **PR 2**: Part 2 + Part 4 (raw wire + token/round-trip oracle + 35-consumer
  migration + TOON golden rebaseline). Inseparable — the strict-xfail flips to
  XPASS the moment the wire changes, so the oracle re-base must land together.
- **PR 3**: Part 3 (envelope normalization + JSON golden rebaseline). Format-
  independent; can land before or after PR 2; independent of the wire.
- **PR 0 (stopgap, optional, immediate)**: README reword (Alt A).
