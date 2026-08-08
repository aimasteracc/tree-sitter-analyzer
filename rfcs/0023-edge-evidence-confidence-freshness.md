# RFC-0023: Edge evidence, confidence, and freshness

- **Status**: draft; docs-only evidence contract
- **Created / updated**: 2026-08-08
- **Merge-blocking dependency**: [RFC-0022 Phase 0, PR #1235](https://github.com/aimasteracc/tree-sitter-analyzer/pull/1235) MUST merge into `develop` before PR #1236; PR #1236 MUST then rebase on that merge before landing
- **Normative artifacts**: [schema](schemas/edge-evidence-v1.schema.json), [golden bundle](fixtures/edge-evidence-v1-golden.json), [negative mutation corpus](fixtures/edge-evidence-v1-negative.json), [authoritative index status](fixtures/edge-evidence-v1-index-status.json)
- **Implementation authorization**: none

## 1. Boundary and ownership

RFC-0022 owns `task-outcome/v1`, routing, freshness oracles, budgets, and
canonical JSON. This document is intentionally not self-contained: its normative
RFC-0022 dependency is being reviewed in PR #1235. Merge order is #1235, rebase
#1236, then merge #1236; this draft MUST NOT land first or be read as an
implementation of either RFC. This RFC freezes only graph-edge records. It adds
no parser, resolver, graph, cache, facade, CLI, or MCP tool.

The graph primitive owns the observation and MUST put `facade`, `action`,
`action_version`, `producer_rule_id`, and `producer_rule_version` on its wire
observation. The task adapter neither fills these fields from a general action
registry nor derives a rule. It validates the exact wire observation, hashes its
canonical bytes, and projects records. A missing or inconsistent owner produces
only a diagnostic. The primitive does not precompute the result digest or an
evidence ID. This is the sole owner/hash flow and supersedes any contrary reading
of RFC-0022.

`index.status` alone owns snapshot identity, fingerprints, and completeness.
Time, mtime, task hashing, successful queries, and adapter rescans cannot prove
freshness. Only a complete primitive snapshot exactly matching authoritative
status can mint evidence.

## 2. Executable V1 types

V1 validation is deliberately two-part: **JSON Schema shape validation followed
by the ordered semantic algorithm in §3 and §5**. Neither part alone is the
normative validator. `schemas/edge-evidence-v1.schema.json` closes object keys,
output `oneOf` shapes, local types, regexes, nullability, enums, and conditional
fields. JSON Schema does not and is not claimed to enforce ordered ranges,
endpoint equality, reference closure, stable sort, counts, or hash preimages;
the semantic algorithm enforces those cross-field invariants.

`rawEnvelope` is the deliberately broad but closed Phase-A input shape. Its
recognized fields are `schema`, `primitive`, `edge_kind`, `source_endpoint`,
`observation`, `snapshot`, `truncation`, `state`, `target_endpoint`, `candidates`,
`reason`, `proposed_edge_key`, and `freshness_signal`. All may be absent or
ill-typed so the classifier can preserve a precise diagnostic. Unknown keys are
still forbidden. Only after classification may an observation pass the strict
five-state `rawObservation` union.

Endpoint identity and syntax location are deliberately separate:

- `source_endpoint` is a `role="declaration"` locator whose `node_id` equals
  `edge_key.source_node_id`;
- `target_endpoint` is a `role="declaration"` locator whose `node_id` equals
  `edge_key.target_node_id`;
- `observation` contains a non-empty JSON Pointer and a separate
  `role="occurrence"` locator. Its node is the syntax/rule occurrence and need
  not equal either endpoint.

Paths are normalized project-relative paths. Ranges use exactly UTF-8 byte
half-open coordinates or one-based line/column half-open coordinates, and end
must be strictly after start. Absolute paths, traversal, bodies, mixed
coordinates, and empty ranges are invalid.

### Raw primitive observation union

A primitive emits exactly one `edge-observation/v1` alternative:

| `state` | state-specific required data | meaning |
|---|---|---|
| `resolved_unique` | one exact `target_endpoint` | the existing resolver selected exactly one declaration |
| `negative_rule` | one exact `target_endpoint` | the named primitive rule rejects this exact edge |
| `ambiguous` | at least two unique candidate declarations | no target selected |
| `unresolved` | exactly zero candidates | resolution attempted; no target selected |
| `no_target` | literal `PRIMITIVE_REPORTED_NO_TARGET` | primitive explicitly reports no proposed target |

Every alternative also contains strict primitive owner, edge kind, source
endpoint, observation occurrence, snapshot, and truncation. Absence, a short or
empty page, lower rank, ambiguity, unresolved spelling, truncation, or budget
omission can never be converted to `negative_rule`.

### Minted evidence

V1 mints only these exact combinations:

| raw state | assertion | binding | confidence | exact ordered basis |
|---|---|---|---|---|
| `resolved_unique` | `supports` | `resolved_unique` | `supported` | `UNIQUE_RESOLVER_BINDING,TARGET_DECLARATION_FOUND,AUTHORITATIVE_SNAPSHOT_MATCH` |
| `negative_rule` | `contradicts` | `negative_rule` | `confirmed` | `NEGATIVE_RULE,TARGET_DECLARATION_FOUND,AUTHORITATIVE_SNAPSHOT_MATCH` |

`direct` is deferred from V1. No authoritative, complete, version-owned tuple
allowlist `(facade,action,action_version,rule_id,rule_version,language,kind,
construct)` exists yet; inventing a `contains` rule would be false authority.
Calls, imports, contains, extends, and implements can mint only after
`resolved_unique`, or contradict through an actual `negative_rule`.

Both evidence alternatives require fresh complete snapshot data, the three
locators, non-null collection/provenance/contradiction IDs, and an exact result
digest. Numeric confidence and additional bases are invalid.

Diagnostics are not claim-addressable: they have no ID and cannot be cited as
support or contradiction. Their closed reasons are frozen by the schema.

## 3. Normative ordered validator and minting

The normative validator executes these steps in order and never repairs or
fills wire data.

1. Parse JSON. Validate the top-level `rawEnvelope` shape: non-object or unknown
   top-level keys add `MALFORMED_RESULT`; a wrong `schema` adds
   `INCOMPATIBLE_SCHEMA`. Retain recognized fields for classification. For a
   bundle, apply this envelope step to each raw member before validating that
   member against the bundle schema's strict `rawObservation` item shape.
2. The field classifier independently inspects presence and local shape before
   strict-union selection. Missing `facade`, `action`, `action_version`,
   `producer_rule_id`, or `producer_rule_version` adds respectively
   `FACADE_MISSING`, `ACTION_MISSING`, `ACTION_VERSION_MISSING`,
   `RULE_ID_MISSING`, or `RULE_VERSION_MISSING`. Missing/invalid source and
   selected-target locators add `SOURCE_LOCATOR_UNAVAILABLE` and
   `TARGET_LOCATOR_UNAVAILABLE`; absent `proposed_edge_key` and
   `freshness_signal` add `PROPOSED_EDGE_KEY_MISSING` and
   `FRESHNESS_SIGNAL_MISSING`. Missing/invalid snapshot identity and fingerprints
   add `SNAPSHOT_MISSING` and `FINGERPRINT_MISSING`. These precise
   reasons are not replaced merely because the strict union subsequently fails.
3. Compare every present owner field, without normalization, to the invoked
   adapter tuple `(facade,action,action_version)` and the invocation-selected
   generated-registry entry's `(producer_rule_id,producer_rule_version)`. Also
   require `edge_kind` to belong to that entry's closed `allowed_edge_kinds`; an
   out-of-scope kind adds `UNSUPPORTED_KIND`. Any owner disagreement adds the
   single closed reason `OWNER_MISMATCH`. The versioned
   registry and invocation context are comparison authorities only: they MUST NOT
   supply a missing wire value. The executable fixtures pin both authorities; a
   validator MUST NOT infer them from the golden wire values.
4. Validate exactly one strict `rawObservation` state. A residual type, enum,
   path, range, pointer, cardinality, or state-shape failure not already captured
   by a precise reason adds `MALFORMED_RESULT`. In particular, validate a
   normalized project-relative slash path (not absolute, drive-prefixed, `.`,
   `..`, empty-segment, or backslash), and require range end strictly after start.
   For `ambiguous`, candidate declaration `node_id` values MUST be pairwise
   unique; whole-object JSON Schema `uniqueItems` is not declaration identity.
5. Compare `edge_kind` to `proposed_edge_key.kind`; disagreement adds
   `EDGE_KIND_MISMATCH`. Compare `source_endpoint.node_id` and, for selected
   states, `target_endpoint.node_id` to the corresponding fields of
   `proposed_edge_key`; any difference or unusable proposed key adds
   `TARGET_DECLARATION_MISMATCH`. These comparisons are semantic, not JSON Schema
   capabilities.
6. Compare `freshness_signal` and the complete snapshot tuple to an independent
   authoritative `index.status` record. Executable contexts resolve the exact
   status by `authoritative_index_status_fixture` plus `authoritative_status_id`;
   raw observations never supply this authority. The positive contexts pin
   `edge-evidence-v1-index-status.json`. `stale` or `superseded` adds
`STALE_SNAPSHOT`; missing/partial
   completeness adds `SNAPSHOT_MISSING`/`PARTIAL_SNAPSHOT`; any snapshot or
   fingerprint disagreement adds `SNAPSHOT_MISMATCH`. A non-`not_truncated`
   result adds `TRUNCATED`.
7. Validate projected output shape, then run the bundle algorithm in §5. Any
   failure emits no evidence ID. Only a reason-free `resolved_unique` or
   `negative_rule` observation may project the fixed mint row in §2.

The diagnostic reason priority is this exact array; emit every independently
observed reason once in this order:

```json
["INCOMPATIBLE_SCHEMA","FACADE_MISSING","ACTION_MISSING","ACTION_VERSION_MISSING","RULE_ID_MISSING","RULE_VERSION_MISSING","OWNER_MISMATCH","SOURCE_LOCATOR_UNAVAILABLE","AMBIGUOUS_TARGET","UNRESOLVED_TARGET","NO_TARGET","TARGET_LOCATOR_UNAVAILABLE","PROPOSED_EDGE_KEY_MISSING","TARGET_DECLARATION_MISMATCH","EDGE_KIND_MISMATCH","FRESHNESS_SIGNAL_MISSING","SNAPSHOT_MISSING","FINGERPRINT_MISSING","PARTIAL_SNAPSHOT","STALE_SNAPSHOT","SNAPSHOT_MISMATCH","TRUNCATED","UNSUPPORTED_KIND","MALFORMED_RESULT","BUDGET_EXHAUSTED","CONTRADICTORY_EDGE_EVIDENCE"]
```

`reasons` MUST be a non-empty priority-ordered subsequence without duplicates,
and `freshness.reason` MUST equal `reasons[0]`. The schema provides the closed
vocabulary; this equality and ordering are semantic checks.

State/freshness truth table (additional independent failures are appended in
priority order):

| strict state | freshness signal | required state shape | result |
|---|---|---|---|
| `ambiguous` | `current` | at least two unique candidates, proposed target null | zero IDs; `AMBIGUOUS_TARGET` |
| `unresolved` | `current` | exactly zero candidates, proposed target null | zero IDs; `UNRESOLVED_TARGET` |
| `no_target` | `current` | literal reason, proposed target null | zero IDs; `NO_TARGET` |
| any of the above | `stale`/`superseded` | same state shape | zero IDs; state reason then `STALE_SNAPSHOT` |
| `resolved_unique`/`negative_rule` | `stale`/`superseded` | one selected target | zero IDs; `STALE_SNAPSHOT` |
| `resolved_unique`/`negative_rule` | `current` and authoritative match | one selected target matching proposed key | fixed projection and one evidence ID |

Confidence, basis, assertion, binding, and contradiction-group presence are
projection constants, never producer choices. A projection override is malformed.
No stale, partial, missing, mismatched, ambiguous, unresolved, no-target, owner
mismatch, or truncated input can fall through to a positive row.

## 4. Canonical bytes and IDs

Canonical JSON uses RFC-0022's serializer: UTF-8, keys sorted lexicographically,
no insignificant whitespace, separators `,` and `:`, JSON booleans/null, and no
floats. Arrays retain their schema-fixed or stable-sorted order. Hash input is
the canonical bytes of the exact object shown; the prefix is not hashed.

```text
result_sha256 = hex(sha256(canonical(raw edge-observation/v1)))

collection_id = "collection:sha256:" + hex(sha256(canonical({
  scope, snapshot, primitive
})))

provenance_id = "provenance:sha256:" + hex(sha256(canonical({
  primitive, request_sha256, normalized_result_sha256, snapshot,
  success, verdict, truncation, input_evidence_ids
})))

contradiction_group_id = "contradiction:sha256:" + hex(sha256(canonical({
  edge_key, snapshot_id
})))

evidence_id = "evidence:sha256:" + hex(sha256(canonical(
  edge-evidence/v1 record with evidence_id removed
)))
```

All digest text is 64 lowercase hexadecimal characters. `request_sha256` hashes
the exact normalized primitive request. A bundle's
`normalized_request_preimages` contains exactly one canonical JSON string for
each distinct referenced request hash, no missing or extra entry; its SHA-256
MUST equal `request_sha256`. `canonical_preimages` likewise contains exactly one
entry for every collection, provenance, contradiction-group, and evidence ID.
The golden stores both kinds, so request hashes, provenance IDs, and downstream
evidence IDs are independently recomputable rather than trusted literals.

Opposite assertions share a contradiction group only for identical
`(edge_key,snapshot_id)`. Both evidence IDs remain, the claim becomes
`conflicted`, status is at most `partial`, and confidence never breaks the tie.

## 5. Normative bundle semantic algorithm

After every member passes its JSON Schema shape, validate the bundle in this
exact order. On any failure reject the whole bundle with `MALFORMED_RESULT`; do
not mint or retain a subset.

1. Recompute each raw observation digest from canonical bytes. Bind each output
   to exactly one raw digest. Evidence MUST exactly project the raw `primitive`,
   `snapshot`, `proposed_edge_key` as `edge_key`, and all three raw locators
   (`source_endpoint`, selected `target_endpoint`, and `observation`) in addition
   to its digest. A diagnostic MUST exactly project the raw digest inside its
   primitive, owner tuple, snapshot, proposed edge key, locators, `raw_state`,
   and state-derived `observed_binding`; it cannot fabricate diagnostic context.
2. Require every evidence `collection_id` and `provenance_id` to resolve exactly
   once, and every collection item ref to resolve to evidence whose reverse
   collection link equals that collection. Every collection and each referenced
   evidence MUST have identical `primitive` owners. Linked evidence and
   provenance MUST have identical primitive, snapshot, and normalized result
   digest. Provenance input evidence refs must resolve. No duplicate, dangling,
   extra, missing, cross-owner, or swapped-provenance link is permitted.
3. Require collection `item_refs` to be unique and ascending by Unicode code
   point, `returned_count == len(item_refs)`, exact totals to be non-null and
   `total_count >= returned_count`, and non-exact totals to be null.
   `not_truncated` additionally requires an exact total equal to returned count.
4. Recompute collection, provenance, contradiction-group, and evidence IDs from
   §4. Require exactly one matching canonical preimage per ID, canonical bytes
   equal to a fresh serialization of the specified object, and no extra
   preimage. Opposite assertions share a contradiction group iff their exact
   `(edge_key,snapshot_id)` is equal.
5. Parse each normalized request canonical string, recursively reject every
   floating-point JSON value before hashing, require that reserialization is
   byte-identical, recompute its hash, and require exactly one entry for every
   distinct provenance `request_sha256`, with no extra entry.
6. Validate each already source-bound diagnostic reason list against §3 priority
   and require `freshness.reason == reasons[0]`.

A collection ID identifies only `(scope,snapshot,primitive owner)`. Primitive,
collection, item, and RFC-0022 outcome truncation remain distinct. Collection
omission does not mark intact returned fragments truncated; a short page never
proves completeness.

## 6. Authoritative container and compatibility

RFC-0022's fixed required `artifacts` object contains
`edge_collections: []`; it is present and empty when unused. Evidence records stay
in `evidence`, provenance records stay in `provenance`, and diagnostics stay in
`unknowns`. Claims cite evidence only. This additive field is part of the draft
V1 before implementation, not a post-release extension. A pre-RFC-0023 draft
fixture lacking it must be regenerated; there is no deployed V1 reader to
preserve. Once V1 is implemented, removing/retyping it requires V2 negotiation.

The checked-in golden bundle, evaluated against the independent authoritative
status fixture rather than its own freshness claims, contains two real `calls`
observations
(`resolved_unique` and `negative_rule`), their endpoint declarations and distinct
occurrences, one ambiguous diagnostic, two provenance records, two collections,
and two evidence records. Its refs are closed; its seven ID preimages plus the
normalized request preimage recompute exactly, including all downstream IDs. It
is the executable positive fixture for both output alternatives.

## 7. Acceptance and deferrals

`fixtures/edge-evidence-v1-negative.json` is normative executable denial data.
Each case names a `base_context` that fixes the document, the invoked adapter tuple
for every raw member, and the exact versioned generated-rule-registry authority.
The registry authority is the independently executable
`edge-evidence-v1-generated-rule-registry.json`; no validator may treat an
unmutated golden owner value as authority. Each case also names sequential
RFC-6901 mutation operations, the validation phase, the sole expected rejection
reason, zero evidence IDs, and the violated invariant. A
`source_observation_reason`, when present, records the unchanged raw diagnostic
classification and is not the rejection reason. A future validator MUST apply
every case independently and reject it. The dedicated
`edge-evidence-v1-stable-sort-base.json` contains two `resolved_unique` evidence
records owned by the same resolver primitive, with closed reverse links in that
primitive's one collection, matching counts and recomputable preimages; its
sort case reverses only `item_refs`, so stable ordering is the first failure. The
32-case corpus pins invalid paths/ranges, endpoint and edge-kind mismatches, owner
and generated-rule kind authority, declaration-identity uniqueness, raw evidence
and diagnostic projection binding, provenance/evidence matching, independent
status mismatch, collection ownership/order/counts including exact-total lower
bounds, float/preimage/result failures, and all state denials.

Future implementation acceptance MUST validate all six JSON artifacts with the
complete schema-plus-semantic validator, recompute every request, result, and
record ID, and prove each mutation has its expected primary reason. It MUST also
prove no writes under `read_existing`, no direct mint, no stale positive ID, and
exact JSON/TOON decoded-model equality. The E0 contract in this PR only checks
Draft 2020-12 schema validity, canonical hashes, reference closure, authority
fixtures, and the 32 declared denial mutations; a green E0 contract is not proof
that the ordered semantic validator exists.

This RFC is E0 documentation only and authorizes no public surface or registry
change. Closed-world absence, direct syntax evidence, probabilistic confidence,
and a completeness oracle are deferred. Any future direct support requires a new
RFC that names the complete version-owned tuple allowlist and provides real
positive and denial fixtures.
