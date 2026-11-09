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

## Absence certificates (`nav action=callers`, RFC-0044)

An empty answer can be a fact. When `caller_count == 0`, `completeness == "complete"`
(every required caller check ran) and there is no unresolved / name-only / declaring-file
site, the response carries:

```json
"absence": {
  "kind": "unreferenced",
  "confidence": "proven",
  "evidence": [{"kind": "complete_call_graph", "detail": "..."}],
  "next_step": "..."
}
```

Rules:

- The field appears **only** on a `complete` zero-caller answer. An `incomplete` or
  `unknown` answer never carries it — no certificate beats a false one.
- `confidence: "proven"` is the only value emitted today; RFC-0044 defines the future
  `possible` value for rules that cannot run (e.g. an unreadable manifest).
- Implemented kinds: `unreferenced`, `entry_point` (console script / package `__main__.py`),
  `script` (file starts with `#!`), `untested` (`nav action=test_map`: resolved target with
  zero test call edges and zero name-only candidates), and the honest downgrade `unknown` with
  `confidence: "possible"` when the list is empty but evidence is incomplete — its
  `incomplete_call_graph` evidence names the open sites so the agent knows what to close.
- A `NOT_FOUND` answer never carries `absence` at all: "not in the index" is not
  "nobody calls it". Consumers must treat unknown `kind` values as informational.
- **Identification vs absence** (2026-11-10): `entry_point` and `script` assert "reachable
  from outside the call graph", which is provable without RFC-0040 completeness; they therefore
  carry `identification_only: true` plus `symbol_defined` evidence even when the answer is
  `NOT_FOUND` with `NON_CALL_REFERENCES` (a real entry point often looks like that). The negative
  claims — `unreferenced`, `untested` — still require `completeness: "complete"`.
  `SYMBOL_NOT_DEFINED` never gets a certificate of any kind: not being indexed is not being an entry.
- The certificate is part of the answer content, so it participates in `answer_etag`.

## Re-asking an answer (ETag / `If-None-Match`)

Four answers support the incremental loop: `callers`, `callees`, `test_map` and `search action=uql`.

- `answer_etag` covers the answer **content** plus its scope: source freshness for the relation
  answers, the index generation for `test_map` and UQL.
- A matching `if_none_match` returns a minimal `{unchanged: true}` payload; a stale answer is
  re-sent in full rather than reported as unchanged. A stale scope never yields a 304.
- UQL's `index_generation` is part of the fingerprint, so re-indexing always changes it.

## `next_step` conventions

- One concrete, imperative action — a command or a tool call, not prose
  ("raise limit", "run `uv run pytest …`", "narrow with `:in(path)`").
- On truncation it MUST state the real shown/total numbers (`"showing 3 of
  39 callers"`), never a stale template count (#448).
- Inside `agent_summary` the same key carries the recommended follow-up for
  the verdict (e.g. the pre-edit verification command on `SAFE`).
- Treat it as the default next call when you have no better plan; it is
  advisory, not binding.

## Repeat answers: cache provenance vs ETag (two different guarantees)

There are two independent mechanisms, and an Agent should know which one it is
relying on:

| mechanism | what it answers | how to read it |
|---|---|---|
| answer cache (RFC-0027) | "was this answer reused without recomputation?" | `provenance.served_from` is exactly `"cache"` or `"computed"` |
| `answer_etag` / `if_none_match` (§12.1) | "is this the same answer I already have?" | a matching etag returns `{unchanged: true}` instead of the payload |

A third, weaker field exists for reuse **without asking again**: `callers` returns
`expires_when: {files, index_generation}` — the declaring file plus every caller file, and the
active index generation. While those files are untouched and the generation is unchanged, the
answer may be reused; when the generation is unreadable it is `null`, and only the files can be
trusted.

They answer different questions — cached means *the server did not recompute*,
unchanged means *you already hold this content*. A cached answer can still differ
from what you hold (another turn may have changed the scope), and an unchanged
answer can be produced without any cache.

Cache soundness, verified 2026-11-10 by editing a file between two identical
`edit action=safe` calls on a temp project:

| call | `provenance.served_from` | wall clock |
|---|---|---|
| first | `computed` | 132 ms |
| identical repeat | `cache` | **0 ms** |
| same call after an edit | `computed` | 13 ms |

`safe` means single-process. The on-disk answer cache is keyed by the source
fingerprint (and per `docs/dev/callers-gate.md`, by every answer's cache key incl.
line endings), so an edit invalidates it rather than serving the previous verdict;
an unquiet tree skips the cache by design rather than risking a stale hit.

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
The first eight come from the call-edge layer and can combine; the rest come from
the gates that re-check an edge-level `complete` and appear alone, with one
exception: when the non-call reference scan reports `SOURCE_INDEX_MISMATCH`, it
is followed by `NON_CALL_REFERENCES` (and `ACCESSOR_NOT_CALL_EDGES`) if those
still hold for the unchanged files (#1672).

`complete` is proof-carrying (RFC-0040): it is returned only when every check in
`REQUIRED_CHECKS` ([`callers_checks.py`](../tree_sitter_analyzer/mcp/tools/callers_checks.py))
ran over the queried target set and found nothing. A check that did not run makes the
answer `unknown` (or `incomplete` with callers listed) with a code naming it. The bounded
`completeness_checks` field shows the proof: `{"required": 13, "checked": 13}` on a census (14 when the opt-in SCIP check `scip_agreement` applies);
otherwise `not_checked` maps each check that did not run to its code, and `not_run` counts
the gates skipped after an earlier gate decided.
<!-- drift:completeness-reasons:start -->
| Code | Meaning | What to do |
|---|---|---|
| `UNRESOLVED_INBOUND_UNCHECKED` | The unresolved-edge count or the declaring-file guard could not be read. | Retry; rebuild the index if it persists. |
| `NAME_ONLY_INBOUND_UNCHECKED` | The name-only inbound check could not run (the same-name method definitions in the named file could not be read from the call graph; RFC-0040). | Retry; rebuild the index if it persists. |
| `UNATTRIBUTED_CALL_SITES_UNCHECKED` | The module-level call sites could not be counted (RFC-0040). | Retry; rebuild the index if it persists. |
| `UNRESOLVED_INBOUND` | Inbound edges name the target but did not resolve to its definition (`unresolved_inbound`). | Read `unresolved_inbound_sites`; qualify the name to narrow. |
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
| `ACCESSOR_UNCHECKED` | The declaration could not be read, so a property/accessor (whose reads are not call edges) cannot be ruled out (RFC-0040). | Read the declaration; search attribute reads. |
| `DECORATOR_MAY_REGISTER` | A decorator may register the target for dispatch. When the decorator is on the target's own definition, it is listed as a `registration` caller entry and the answer is `incomplete` (PR-4). | The `registration` entry is a known use; the framework-side callers cannot be listed. Otherwise inspect the decorator. |
| `OVERRIDE_DISPATCH` | Java: the target carries `@Override`, or (#1884) it is a non-static, non-private method without `@Override` whose declaring type (named, anonymous or an enum constant body) has a supertype or that is named like a `java.lang.Object` method, and a call through its supertype could reach it without a call edge naming it. For a method without `@Override`, a supertype closure that resolves in the project and declares no method of that name proves it overrides nothing; a closure that cannot be resolved does not. A JDK interface with a known member set (`Cloneable`, `Serializable`, `AutoCloseable`, `Closeable`, `Flushable`, `Comparable`, `Runnable`, `Iterable`; no project type of that name) ends the walk; a method named like one of its members overrides it. Either the overridden method is not proved to be declared in the project (an external, `java.lang` or unresolved supertype, a `java.lang.Object` method; e.g. an override of `java.lang.ClassValue.computeValue`, which the JDK calls), or a call named like it is bound elsewhere and may dispatch here (`next_step` names up to 3 sites). Also (#1894) a non-static, non-private method with a body declared in a class or interface that is not `final`, when a project subtype (found from source, transitively) inherits it and has another supertype declaring the same name (`class B extends A implements I`: `m()` in a default method of `I` runs `A.m`): it passes only when every call edge named like it is bound to this declaration or outside the project. A JDK type with that member, a subtype whose supertypes do not resolve, a clause that may name the type but does not resolve, or more than 128 subtypes also block. Subtypes outside the project are not considered. Python (#1896): a class-body member whose class has a project subclass (found from source through the import resolver, transitively; `A[int]` counts as `A`) whose ancestry holds another class, unrelated to the declaring one, that declares the same name (`class B(A, I)`: `self.m()` in `I.run` runs `A.m`). It passes only when no call edge named like it may dispatch there: outside the project, a plain `m()` call, bound to this declaration, or with a receiver class (the class around `self.` / `cls.` / `super().`, or the class the edge is bound to) in no such subclass's ancestry. A base that may name the class but cannot be followed (`mix(A)`), a subclass whose ancestry cannot be followed, a file that may declare a subclass but cannot be read or parsed, or more than 4096 subclasses also block; a mangled `__m` and members of external bases are not checked; subclasses outside the project are not considered. `next_step` names the subclass, the other class and up to 3 sites. `@SuppressWarnings`, `@Deprecated`, `@SafeVarargs` and `@FunctionalInterface` register nothing and do not block (PR-2). | For an external supertype, the callers are outside the project. Otherwise read the named sites and check each receiver's type. |
| `DYNAMIC_SUPERTYPE` | JS/TS: the target is a class member that may override a supertype member (an instance or static method, accessor or field; not a constructor), and its class, or a class above it, has an `extends` clause the index cannot follow: a call (`extends mix(Proc)`), a conditional, a cast, a local value, an import that does not resolve to one project class, an unknown identifier, a duplicated name or a cycle (#1882). The index records no inheritance edge for it, so a call through a supertype (`this.getQuery()` in a base class) could reach the target without a call edge naming it. The chain is read from source; a package import or an ECMAScript / web platform global (`Error`, `HTMLElement`) ends it as a known external class. Also reported when a file on the chain could not be read or parsed, and when the declaring Java file of a method checked for `OVERRIDE_DISPATCH` could not be (#1884). Python (#1883): the same for any class member when its class, or a project class above it, has a base the index cannot follow: a call (`class V1(mix(Proc))`), a starred argument, a conditional, a subscripted project class (`GProc[int]`), a name bound to a value (`Alias = Proc`) or bound twice, an unbound name, an import that does not resolve to one project file, a `**` class keyword, or a `metaclass=` that is not external, may rebind the bases in `__new__` or defines `mro`. Standard-library and third-party classes, builtins (`object`, `Exception`) and their subscripts (`Generic[T]`) end the walk; no Python member is exempt. `next_step` names the class, its file and line, and the clause. | Read what the clause evaluates to, and search those classes for calls of the method through `this` / `self` or a supertype receiver. |
| `SCIP_UNLISTED_REFERENCE` | Opt-in SCIP evidence (TS/JS; `scip.status` is `used`): the SCIP index references the target at a place that no listed caller and no open site covers (`scip.unlisted_references`). The check is `scip_agreement`, required only when the SCIP layer is used. | Read each `scip.unlisted_references` entry: it is a caller or a use TSA did not attribute. |
| `SCIP_AGREEMENT_UNCHECKED` | Opt-in SCIP evidence: the `scip_agreement` check could not be evaluated. | Retry; regenerate the SCIP index and its manifest if it persists. |
<!-- drift:completeness-reasons:end -->

### Evidence behind the codes (#1672)

Every code that names sites carries them in the same bounded shape: a list
capped at 20, the exact total beside it, and a `*_truncated` flag.

| Code | Count | Sites (`file`, `line`, …) | Total / truncated |
|---|---|---|---|
| `UNRESOLVED_INBOUND` (#1706) | `unresolved_inbound` | `unresolved_inbound_sites` (+ `caller`, `callee`) | `unresolved_inbound_sites_total` / `unresolved_inbound_sites_truncated` |
| `UNRESOLVED_IN_DECLARING_FILE` | `unresolved_in_declaring_files` | `unresolved_sites` (+ `mechanism`, `callee`) | `unresolved_sites_total` / `unresolved_sites_truncated` |
| `NAME_ONLY_INBOUND` | `name_only_inbound` (callers) | `name_only_sites` (+ `caller`) | `name_only_sites_total` / `name_only_sites_truncated` |
| `NON_CALL_REFERENCES` | `non_call_references` | `non_call_reference_sites` (capped at 5) | `non_call_references` |
| `SOURCE_INDEX_MISMATCH` (reference scan) | `stale_reference_files_total` | `stale_reference_files` (paths, capped at 5) | `stale_reference_files_total` |

`name_only_sites[].line` is the call line from the call-graph edge; when no edge
line is readable it falls back to the caller's definition line. `next_step`
names the first three sites inline and says how many more there are.

`unresolved_inbound` is the length of `unresolved_inbound_sites` before the cap,
so the count and the sites describe the same edges. `caller` is `<module>` for a
module-level site; `callee` is the call's source text (`api.open`).

PR-3: a JS/TS site the call graph already binds is not counted by either guard.
`reason_code: listed_caller_edge` marks a listed caller's own call into the
target; `graph_bound_elsewhere` marks `this.m()` bound to the enclosing class's
own `m` when the source proves the target unreachable through that `this`. Such
sites appear in `excluded_sites` (declaring-file guard) and in
`unresolved_inbound_excluded` (capped at 20, total in
`unresolved_inbound_excluded_total`; the field is absent when nothing was
dropped).

**Ranking (#1706).** `name_only_sites` and `unresolved_inbound_sites` are ranked
before the cap, by how close the site is to the target:

1. the declaring file;
2. files that import the target's class (or function) name or its module;
3. every other file.

Within a tier, production files come before test files, then path and line. A
same-named call reaches `Class.method` only if its receiver is a `Class`
instance, and the declaring file and its importers are where such instances are
built; a file that never names the class gets one only through a parameter.

**`next_step` names the primary reason's evidence (#1706)**, whether or not
callers were listed: the unresolved sites first, then the name-only sites; the
non-call reference sites, with what to check at each (a callback, a rebinding,
or a re-export under another name); the declaring-file sites; the module-level
count. A gate reason without a site list (decorator, unindexed files) restates
its hint for a listed set of callers. The generic "Review callers above…" is
given only for a `complete` answer.

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
alias, a re-exported alias, or an alias that is also used without a call (a
callback, an assignment, `__all__`) keeps the import line as a reference; the
non-call uses are listed in `non_call_reference_sites` too. With no caller at
all, the import line always stays a reference (#1645).

**Through a module attribute (#1705).** `import pkg.hub as owner; owner._f()`
(or `import pkg.hub; pkg.hub._f()`, or `from pkg import hub`) where `hub` binds
`_f` by `from .core import f as _f` is a caller of `core.f`, with
`resolution_kind: "import_alias"` and `import_alias: "_f"`. A plain re-export
(`hub` does `from .core import f`; `owner.f()`) resolves to `core.f` too. Both
follow re-exports for up to 4 hops. When one file binds the same module alias
to several modules (function-local imports), the import inside the calling
function picks the module. The call is **not** resolved, and stays only a
possible caller, when the attribute is rebound in `hub` (assignment, `global`,
`del`), or when the calling file assigns it or names it in a string
(`owner._f = fake`, `monkeypatch.setattr(owner, "_f", ...)`). Such a site is
listed in `non_call_reference_sites` under the alias (`alias: "_f"`), not just
the import line. Because the alias is used from another module, it is a
re-export: the import line in `hub` stays a reference.

### Per-caller confidence tier (#1854)

Every `nav action=callers` caller entry carries `confidence_tier`, derived only
from the two resolution fields already on the entry. Each field gives a tier and
the entry gets the less confident of the two; any value not in the table below
(missing, misspelled, a future kind) is `unconfirmed_receiver`.

| Field | Value | Tier |
|---|---|---|
| `callee_resolution` | `local`, `project` | `proven` |
| `callee_resolution` | `stdlib`, `external`, `builtin`, `unknown` | `unconfirmed_receiver` |
| `resolution_kind` | absent, `import_alias` | `proven` |
| `resolution_kind` | `annotated_receiver` | `inferred` |
| `resolution_kind` | `scip` | `scip` (opt-in SCIP evidence, below) |

`proven`: the resolver bound the call edge to a project definition (self/cls,
an import, the same file, a unique function, a class-name or constructed
receiver and its MRO). `inferred`: the binding rests on a type annotation
(RFC-0038). `unconfirmed_receiver`: a same-named call whose edge is not bound to
a project definition; this is what an unscoped bare-name query lists when the
name has several definitions.

The tier is presentation only. It never enters the RFC-0040 checks: an
unconfirmed call site still counts as unresolved evidence, and
`completeness` / `completeness_reasons` are the same whatever the order or
folding. `order=confidence` (opt-in; the default `order=index` keeps the
existing order) sorts proven, then inferred, then unconfirmed, stable within a
tier, before the `limit` cut. `format=compact` uses `order=confidence` and folds
the `unconfirmed_receiver` callers of the page into one line,
`+N unconfirmed-receiver candidates (include_unconfirmed=true to list)`, with the
same number in `unconfirmed_collapsed`; `include_unconfirmed=true` lists them.
The listed and the folded callers together are the callers of the full answer.
The numeric `confidence` (0.8) of an annotated entry is a different field.

### Registration entries (PR-4)

A decorator such as `@app.get("/items")` or `@pytest.fixture` hands the function
to a framework when the `def` runs; the framework then calls it under another
name, so the call graph has no edge. When `DECORATOR_MAY_REGISTER` is the only
blocker and the decorator is on **the target's own definition**, the answer
lists it as a caller entry and becomes `incomplete`:

```json
{"completeness": "incomplete", "completeness_reasons": ["DECORATOR_MAY_REGISTER"],
 "caller_count": 1,
 "callers": [{"name": "<module>", "file": "app/routes.py", "line": 12,
              "language": "python", "callee_resolution": "local",
              "callee_resolved_file": "app/routes.py",
              "resolution_kind": "registration", "via": "@app.get(\"/items\")",
              "confidence_tier": "registration"}],
 "next_step": "'read_items' is registered by `@app.get(\"/items\")` (app/routes.py:12), listed as `registration` entries. The framework calls it through that registration, and those framework-side callers cannot be listed, so the list is incomplete; ..."}
```

- `line` is the decorator's line; `name` is `<module>` (the decorator runs when
  the module body runs); `via` is the decorator text.
- `confidence_tier: "registration"` is its own tier, ranked after `proven` and
  before `inferred`, so a registration is never mistaken for a call edge.
  `format=compact` lists it (it is not folded) as
  `@app.get("/items")  app/routes.py:12  registration`.
- It is never `complete`: the gate keeps its code.
- Soundness: Python only (a Java annotation such as `@Override` registers
  nothing); exactly one declaration backs the query, in the queried file; the
  definition's name and class chain match the query; it is a direct statement of
  the module body or of class bodies nested in it (a `def` inside a function,
  `if` or `try` runs conditionally and gets no entry); only decorators outside
  `KNOWN_WRAPPERS` (`functools.lru_cache`, `staticmethod`, ...) are listed. Any
  read or parse failure keeps the answer `unknown`.

### Open-site bound (`open_sites`, PR-4)

Every `unknown` answer carries `open_sites`, a bound on what keeps it from
`complete`. `complete` and `incomplete` answers do not carry it.

```json
{"completeness": "unknown", "completeness_reasons": ["NAME_ONLY_INBOUND"],
 "caller_count": 0,
 "name_only_sites": [{"file": "user.py", "line": 2, "caller": "use"}],
 "non_call_reference_sites": [{"file": "user.py", "line": 6}],
 "non_call_references": 1,
 "open_sites": {"total": 2, "enumerated": true,
                "fields": ["name_only_sites", "non_call_reference_sites"]},
 "next_step": "The bound is exhaustive (`open_sites`): these 2 site(s) are all that keep 'Box.fetch' from a complete answer: user.py:2; user.py:6. Read them instead of searching; ..."}
```

`enumerated: true` means: the `total` distinct `(file, line)` sites in the
`fields` lists are **all** the evidence that blocks `complete`. If none of them
calls the target or passes it on (a callback, a rebinding) for a later call,
nothing else in the indexed project does. Read those sites; do not grep. The
verdict stays `unknown`: with 0 known callers, `incomplete` would claim a caller
exists.

This is a trust claim like `complete`. It is `true` only when every failed
check has a site list that is not truncated (its `*_total` equals its length):

| Failed check | Site list |
|---|---|
| `UNRESOLVED_INBOUND` | `unresolved_inbound_sites` |
| `UNRESOLVED_IN_DECLARING_FILE` | `unresolved_sites` |
| `NAME_ONLY_INBOUND` | `name_only_sites`, only when every line is a call line from an edge (no fallback to the caller's definition line) |
| `NON_CALL_REFERENCES` | `non_call_reference_sites` (capped at 5, so at most 5 references), only when every later gate passes |

When the edge layer decides the answer, the review gates (freshness, target,
unindexed files, reference freshness, accessor, non-call references, decorator)
did not run; they are run for the bound, and it is `true` only if they all pass
or only the non-call gate fails. The non-call sites found that way are added to
the answer. Any other case is `{"enumerated": false, "reason": ...}`:

- `SITES_TRUNCATED`: a site list was capped;
- `NO_SITE_LIST`: a failed check has no exhaustive site list (accessor,
  decorator, unattributed module-level sites, an empty call graph, a gate that
  did not run, approximate name-only lines).

`format=compact` adds one line before the verdict line,
`open: k sites (exhaustive)  a.py:3; b.py:9` (up to 10 sites, then
`+n more (format=verbose)`), and the machine field
`open_sites: {"total": k, "enumerated": true}`; a non-enumerated bound is
omitted from compact.

The alias is **re-exported** (#1709) when another file imports that name
(`from .hub import _f`), calls it through a module object (`owner._f()`), or
mentions it in any other way in a file the reference scan read. The re-export
sites are listed in `non_call_reference_sites` with `alias: "_f"`. Another file
that binds the same name **on its own**, by renaming something
(`from .other import g as _f`, or its own `from .core import f as _f`) or by
defining `_f`, is not a re-export: its uses are checked against its own import
line.
### Opt-in SCIP evidence (`scip`, TS/JS)

A compiler-grade SCIP index (scip-typescript) can bind call sites TSA enumerated
but could not bind. It is opt in: set `TSA_SCIP_INDEX=<path>` (relative to the
project root) or put the index at `.ast-cache/scip/index.scip`. TSA never runs
the indexer. Beside the index, `<index>.manifest.json` records the git tree,
the hash of every uncommitted or untracked file, the lockfile hashes and the
index hash; write it right after indexing with
`python -m tree_sitter_analyzer.mcp.tools.callers_scip_manifest --project . --index <index>`.

Without either opt-in the answer has no `scip` field and no extra check: it is
exactly the answer without this layer. With it, `scip.status` is one of:

| `scip.status` | Meaning |
|---|---|
| `used` | The manifest matches the project; the evidence below applies. |
| `stale` | No manifest, or it no longer matches (another commit, edited or untracked files, a changed lockfile, a rewritten index). No evidence. |
| `absent` | `TSA_SCIP_INDEX` names a missing file. No evidence. |
| `invalid` | The index or manifest cannot be decoded, or another indexer wrote it. No evidence. |
| `unsupported_language` | The target is not TS/JS (Python and Java stay out). No evidence. |

`used` also reports `scip.target`: `{"mapped": true, "symbols": [...]}`, or
`{"mapped": false, "reason": ...}` (`not_found`, `ambiguous`,
`file_not_indexed`, `tsa_definition_mismatch`) and then no evidence. When there
is no evidence, `completeness_checks.not_applicable` holds
`{"scip_agreement": <status or target_<reason>>}` and the answer is today's.

With evidence, SCIP only classifies the sites TSA listed (`unresolved_inbound_sites`,
`unresolved_sites`, `name_only_sites`):

- `proven_target`: every occurrence of the name on the site resolves to the
  target or to a trusted other symbol, at least one to the target, and TSA and
  SCIP agree on the enclosing definition. The definition is listed as a caller
  with `resolution_kind: "scip"`, `confidence_tier: "scip"`.
- `proven_other`: every occurrence resolves to a trusted other symbol: a bare
  call bound to another function, a subclass override, a member of an
  unrelated class that declares a private / `#private` / protected member, or
  a core ECMAScript type. The site is dropped with `reason_code:
  "SCIP_RESOLVED_OTHER"` (in `excluded_sites`, `unresolved_inbound_excluded`
  and `scip.resolved_other`).
- otherwise `open`, as today: interfaces, type literals, non-nominal classes,
  lib.dom / `@types`, `.d.ts` declarations, supertype members, locals and
  function-valued properties are never trusted, and a line whose text holds
  the name more often than SCIP reports, or a position with two symbols, gives
  no evidence.

SCIP never removes a TSA caller; a listed caller in whose span SCIP sees no
reference is logged in `scip.disagreements`. A SCIP reference to the target
outside every listed caller and open site fails the `scip_agreement` check
(`SCIP_UNLISTED_REFERENCE`), and an exhaustive `open_sites` bound becomes
`{"enumerated": false, "reason": "SCIP_UNLISTED_REFERENCE"}`. A reference
inside an import or export-list statement (`import {…} from`, `import type`,
`export {…} from`, `export *`), on any of its lines (#1892), is not a use and
is not counted; only positions inside a statement tree-sitter parsed without
errors qualify, so dynamic `import()`, `export const` values and code after
the statement on its last line still count. `scip.sites`
counts the three outcomes; lists in `scip` are capped at 20 with `*_total`
beside them.
### Inherited `self.m()` calls (#1677)

When the enclosing class does not define `m`, `self.m()` / `cls.m()` is a
certain caller of the nearest definition of `m` in the class's MRO (C3), across
files, provided every base up the chain resolves to a project class or is a
standard-library class without such an attribute. If a base does not resolve
(for example a third-party class), the call is only a name-only possible caller
and keeps the answer non-`complete` (`NAME_ONLY_INBOUND`). Overrides of `m` in
subclasses of the enclosing class remain possible targets.

#1699: the same nearest-in-MRO rule applies to `super().m()` (the first `m` after
the enclosing class), to module-level singletons, constructor-typed locals and
fixtures, and annotated parameters and returns whose class inherits `m`. When
several base branches define `m`, the C3 order decides. A nested function that
reads a closure variable bound by `x = T(...)` in the enclosing function gets
that type unless it rebinds the name.

#1739: in Python, these MRO rules are the **only** way a `self.m()` / `cls.m()`
call becomes certain. The call is certain for the enclosing class's own `m`, or
for the nearest `m` in a fully known MRO. If the MRO reaches an external or
unresolved base before a project `m` (for example `class T(Thread)` calling
`self.join()`, or `class D(dict)` calling `self.keys()`), the call is not a
caller of any project method, even when the project has exactly one method
with that name. That method only gets a name-only possible caller, so its
answer stays non-`complete`. `self` / `cls` is a method receiver only when it
is the first parameter of a function defined directly in a class body. When
it is a lambda parameter, the parameter of a module-level or nested function,
or not the first parameter, it is an ordinary unproven receiver. Such calls
are stored as `(self).m`.

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
| `INDEX_WRITER_BUSY` | true | 5000 | `recapture` | `INDEX_WRITER_BUSY` (publication lease wait timed out, or Windows could not replace the selector atomically), `INDEX_GENERATION_SEAL_BUSY` (another connection still held the private build database for the whole 10 s seal wait; nothing was published) | Wait `retry_after_ms`, then retry; if it stays busy, stop the other writer for this project. |
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
