# RFC-0041: Unified, evidence-carrying query language (UQL)

- **Status**: draft (implementation in the same PR series)
- **Author(s)**: @aimasteracc (agent-drafted, owner review pending)
- **Created**: 2026-10-24
- **Last updated**: 2026-10-24
- **Tracking issue**: TBD
- **Related**: RFC-0003 (Hyphae), RFC-0014 (test_map), RFC-0027 L6.1 (answer cache),
  RFC-0028 (completeness reasons), RFC-0040 (proof-carrying callers completeness, #1799),
  #1798 (scoped vs bare callers divergence)
- **Affected source paths**:
  - `tree_sitter_analyzer/uql/` (new: `errors.py`, `ir.py`, `steps.py`, `selector.py`,
    `parser.py`, `coverage.py`, `backends.py`, `relations.py`, `engine.py`, `output.py`)
  - `tree_sitter_analyzer/mcp/tools/uql_tool.py` (new), `search_facade.py`
  - `tree_sitter_analyzer/mcp/tools/tql_tool.py`, `_codegraph_query_dsl.py` (adapters)
  - `tree_sitter_analyzer/cli/argument_groups/_analysis.py`,
    `tree_sitter_analyzer/cli/commands/mcp_commands/_specs_pulse.py`, `mcp/facade_map.py`
  - `tests/unit/uql/`, `tests/unit/mcp/tools/test_uql_tool.py`, `benchmarks/unified_query/`

## Summary

TSA has two query languages that each answer part of an agent's code question
and neither says how much of the answer it examined: **TQL** (`search
action=tql_execute`, a CSS-like selector over the symbol index) and the
**chain DSL** (`search action=chain`, `search('X').callers()...`). This RFC
unifies them into one grammar and one IR, adds composable stages
(source → relate → refine → page) executed in **one call**, and makes every
stage carry its own completeness and reason codes. The total is `complete`
only when every stage is. Relations reuse the existing producers — `nav
action=callers` / `callees` — and consume their completeness contract as-is.
`tql_execute` and `chain` keep working: their parsing now goes through the
single UQL parser and `tql_execute` evaluates through the shared select backend.

## Motivation

Measured on two repositories (§7): the questions agents actually ask — "who
calls X and which tests cover them", "what in module M calls Y and is
untested", "impact of changing X" — take today's best TSA usage 1–13 calls and
up to 21 KB of responses, and the answers often carry **no completeness claim
at all** (TQL, chain, `test_map`, `caller_tree` never make one). Two concrete
failures found while building the baseline:

- `tql_execute '*:calls(#file_content_hash){1,2}:in(tree_sitter_analyzer/)'`
  on TSA returns **0 symbols** (truth: 10) with `verdict: INFO` and no
  coverage field; on rich `*:calls(#blend_rgb){1,2}:in(rich/)` returns 7 of 9.
  An agent cannot tell a wrong 0 from a true 0.
- Hyphae silently returns `[]` for an unknown attribute (`.function[nam=x]`)
  and only rejects an unknown pseudo-class when evaluation reaches it, so a
  typo looks like "no matches".

REA's design rules (`docs/tool-design.md`, `AGENTS.md` §Performance) name the
fix: start from the analyst's question, return the smallest sufficient answer
with provenance and coverage, derive completeness from what was examined
(missing coverage is `unknown`), parse unknown input at the boundary into
typed errors, give each interpretation one owner, and count the whole task in
tokens.

## Detailed design

### 1. One grammar

```ebnf
query      = selector | pipeline ;
selector   = TQL selector (first char in ". # * [ :") ;      (* RFC-0003 grammar *)
pipeline   = source , { "." , stage } ;
source     = "select(" , string , ")"                        (* a TQL selector *)
           | "symbol(" , name | names , [ ", file=" , string ] , ")"
           | "search(" , name | names , ")" ;                 (* chain alias *)
stage      = relation | refinement ;
relation   = "callers(" , [ "depth=" , 1..5 ] , ")"
           | "tests()" | "callees()"
           | "impact(" , [ "depth=" , 1..10 ] , ")" ;
refinement = ( "filter" | "where" | "exclude" | "not" ) , "(" , kv , { "," , kv } , ")"
           | "untested()" | "tested()"
           | "take(" , int , ")" | "sort(by=" , ("name"|"file"|"line") , [ ", desc=" , bool ] , ")" ;
```

`symbol('Cls.m')` is accepted; arguments are literals only (`ast.literal_eval`
plus `true/false/null`), never evaluated. A bare TQL selector is a one-stage
query, so every existing TQL selector is a valid UQL query.

### 2. One IR, one owner

`uql/ir.py` defines frozen dataclasses: `Select`, `SymbolSource`, `Relate`,
`Refine`, `HasTests`, `Take`, `Sort`, `Query`, plus `RawStep` (a step exactly
as written). `uql/steps.py` owns step splitting and literal parsing for
**both** dialects; `uql/parser.py` has `parse_query` (unified) and
`parse_chain` (the legacy chain vocabulary, same lexical owner);
`uql/selector.py` owns TQL selector parsing and validation. The MCP tool,
the CLI flag (`--uql`, which calls the same tool), `tql_execute` and `chain`
all consume these; none re-splits query text.

### 3. Stages and per-stage completeness

| Stage | Producer (reused, not reimplemented) | Own completeness |
| --- | --- | --- |
| `select(sel)` | Hyphae `Evaluator` | `complete` iff the index source gate passes (no unindexed sources of the rows' languages; scoped freshness, or an all-files freshness scan for an empty answer — the gates `nav callers` runs) **and** the selector uses only exhaustive predicates. Edge / temporal / rule / branch pseudo-classes → `unknown` `SELECTOR_PREDICATE_UNPROVEN` (hint: use a relation stage). Cap hit → `incomplete` `SELECT_CAP_REACHED`. |
| `symbol(n)` | Hyphae `#n[class=..][file=..]` | the same source gate; a 0-row answer is `complete` only if the absence scan passes |
| `callers(depth=k)` | `nav action=callers` per expanded node (BFS) | worst of every node's `completeness`, consumed verbatim (reason codes pass through). Missing field → `unknown` `PRODUCER_COVERAGE_MISSING`; failed call → `unknown` `RELATION_ERROR`; listed < counted → `incomplete` `RELATION_LIMIT`; node budget (400 calls) → `incomplete` `RELATION_NODE_BUDGET`. The depth bound is the question, not a gap. |
| `impact(depth=d)` | same BFS, closure semantics | as `callers`, plus an unexpanded frontier at the cap → `incomplete` `RELATION_DEPTH_LIMIT`; rows tagged `caller` / `test`, plus a `files` list |
| `tests()` | `nav action=callers` (input, then each test-file helper) | `test_map`'s definition (test entry points directly or via one helper), but derived from callers so it carries their coverage; a helper called by another helper → `incomplete` `TEST_HELPER_DEPTH` |
| `callees()` | `nav action=callees` | never `complete` (the producer makes no claim): `incomplete` `CALLEE_UNRESOLVED` when some callees did not resolve to a project definition, else `unknown` `CALLEES_COVERAGE_UNREPORTED` |
| `filter` / `exclude` / `take` / `sort` | chain's `filter_symbols` predicates | no gap of their own |
| `untested()` / `tested()` | `tests()` per row | rows whose tests are not a census are kept and flagged `?` (`untested`) or dropped (`tested`); stage → `unknown` / `incomplete` `MEMBERSHIP_UNKNOWN` |

A stage's **effective** coverage folds in the stage before it
(`UPSTREAM_INCOMPLETE` / `UPSTREAM_UNKNOWN`); the query total is the last
effective coverage, so one `unknown` stage makes the total non-`complete`.
Status order: `complete` < `incomplete` (a known lower bound) < `unknown`.
`Coverage` refuses `complete` with reasons and non-`complete` without one.

Relations consume the RFC-0040 payload unchanged: `completeness`,
`completeness_reasons` and the bounded `completeness_checks` proof (carried into
the stage's examined-input evidence under `detail="full"`).

Two producer-request rules keep relation answers faithful to `nav callers`:
a bare name with exactly one indexed definition is sent unscoped (§7 found
the `file_path`-scoped form, which `nav callers` rewrites to `Class.method`
per #1759, measurably less complete; tracked as #1798), and a set holding every definition of a
name is one unscoped union request. Within one query each (relation, name,
file) is asked once.

### 4. Output, paging, errors

Compact (default): one string per row (`"file:line Cls.name"`, `" ?"` for an
undecided membership), per-stage `{op, n, c, r}`, total `completeness` +
`completeness_reasons` (`"stage:CODE"`), `page {offset, returned, total,
next_cursor}`, and — only for inputs whose coverage was not `complete` — up to
three `evidence[]` handles: the exact `nav` request that was sent, so the full
producer evidence (unresolved sites, excluded sites, ...) is one call away.
`detail="full"` returns structured rows with `depth` / `via` provenance and
every examined input.

Paging is across groups in output order (`limit` 1..500, default 50). Cursors
are stateless (`uql1:` + base64 of query digest, offset, 16-hex generation
tag); the next page re-executes the query. A cursor for another query is
`UQL_INVALID_CURSOR`; one from another source generation is
`UQL_STALE_CURSOR`; when the generation cannot be computed, continuation
pages are `incomplete` `CURSOR_GENERATION_UNVERIFIED`. Paging never changes
completeness.

Errors are values (`Result = Ok | Err`) with a closed code set
(`uql/errors.py::ERROR_CODES`, 18 codes) and carry `stage_index`,
`fragment`, `suggestion` and, where mechanical, `fixed_query` the agent can
resend as-is: `|` separators, misspelt stages (`caller()` → `callers()`),
chain-only stages, unknown keywords (lists the accepted ones), out-of-range
depth, stage order, bare words (`parse` → `symbol('parse')`), unknown
pseudo-classes / attributes (did-you-mean), malformed cursors, missing index.

### 5. MCP surface and schema discovery

`search action=uql`, params `query`* / `limit` / `cursor` / `detail`. The
grammar card is the `query` parameter description, served by the existing
facade discovery call `search action=help target_action=uql` — **one**
discovery call, no new action. `tools/list` grows only by the `uql` entry in
the action enum and one sentence in the facade description (short form);
`tql_schema` gains a 6-line pointer section.

### 5b. Performance: one answer, one index moment

A pipeline asks `nav callers` about many symbols, and each call re-ran work
that does not depend on the symbol. The engine runs inside a `query_scope`
(`tree_sitter_analyzer/query_scope.py`, a `ContextVar` memo; worker threads of
the reference scan inherit it via `copy_context`). Inside a scope these steps
run once per answer instead of once per producer call; outside a scope every
call stays live, so single `nav` calls are unchanged:

| Shared step | Where | Before (TSA Q1, 15 producer calls) |
| --- | --- | --- |
| ES alias-edge scan, bucketed by alias name | `graph/alias_edges.py` | 0.30 s per call |
| per-file `stat` in the reference-vocabulary check | `reference_vocab.py` | ~36k stats per answer |
| project walk for unindexed sources | `unindexed_sources.project_files` | 14 walks |
| index-path `realpath` | `cache/generation_routing.logical_index_path` | ~770 calls |
| Python decorator parse per declaring file | `callers_decorators._python_decorators` | 1 parse per call |

Plus, in the engine: one request per (relation, name, file) per query; one
unscoped union request when a set holds every definition of a name; an exact
`symbol()` lookup instead of Hyphae's fuzzy cascade (0.9 s on TSA). Every
memoised value is a pure function of the index and source state the answer is
already pinned to, so no stage's proof changes: the callers tool still runs
all of its RFC-0040 checks per input. Measured warm on TSA Q1
(`symbol('raw_to_path').callers().tests()`): 9.2 s → 2.4 s.

The answer cache (RFC-0027 L6.1) admits `search action=uql`; its key adds the
parsed IR and the index identity to the source generation, `limit`, `cursor`
and `detail`, so an edit (generation) or a refresh (index identity) misses,
and the generation is recomputed on every lookup before a hit is served.

### 6. Backward compatibility

No breaking change in this release line:

- `search action=tql_execute` keeps its request and response shape and gains
  two additive fields, `completeness` and `completeness_reasons`, derived by the
  same select-stage rule (edge / history / rule / branch predicates →
  `unknown` `SELECTOR_PREDICATE_UNPROVEN`). It now
  parses with `uql.selector` and evaluates through `uql.backends.select`.
  Two deliberate fixes: an unknown pseudo-class is rejected at parse time
  (`error: "TQL syntax error: unknown pseudo-class ...", error_code,
  fixed_selector`) instead of `"TQL evaluation failed: ..."`, and an unknown
  attribute is rejected instead of evaluating to `[]`. `#name` rows now carry
  `class` when the per-file function rows have it.
- `search action=chain` is unchanged in behaviour; `_codegraph_query_dsl` is
  an adapter over `uql.parser.parse_chain` (same `ValueError` messages, same
  `_ChainStep`).
- `chain` is **deprecated in the docs** for the questions the pipeline covers (owner
  decision 2026-10-24); it keeps working and emits no runtime warning.
- Deprecation path (documented, not enforced): for questions the pipeline
  covers, prefer `uql`; `chain`'s answer-pack steps (`explore`, `include`,
  `uml`, `semantic`, ...) have no UQL equivalent yet and are rejected by the
  UQL parser with `UQL_CHAIN_ONLY_STAGE` pointing back at `chain`.

## Three-Surface impact (CLI ↔ MCP parity)

| MCP | CLI |
| --- | --- |
| `search action=uql query=Q limit=N cursor=C detail=D` | `--uql Q --uql-limit N --uql-cursor C --uql-detail D` |

`NEW_ACTION_PARITY["search_uql"] = ("search", "uql", "--uql")`. The CLI spec
calls the same `UqlTool`, so the payload is identical.

## 7. Measurement (before / after)

Benchmark: `benchmarks/unified_query/` (oracle, questions, three arms, token
counter). 8 questions × 2 repos: TSA at `f9636cf4` (3,090 files indexed) and
rich at `9d8f9a3` (`git clone --local` from the r10 dogfood repos). Ground
truth is an independent stdlib-`ast` name-based oracle; every target name on
the relevant relation path has exactly one definition, which makes the
name-based edge set exact for these questions. Arms:

- **today** — the cheapest correct-looking combination of existing actions
  (`nav callers include_bodies=false`, `nav test_map`, `nav caller_tree`,
  `tql_execute`, `nav callees` filtered to project-resolved), as a TSA-fluent
  agent would issue them;
- **uql** — one `search action=uql` call;
- **grep** — `git grep` + def-outline greps + body reads (an agent's no-tool
  path; a 60-call budget caps closures that otherwise explode, 1,020 greps /
  373 s on rich Q5).

Bytes are the wire text (`json.dumps(indent=2)` after envelope
normalisation); tokens are **estimates** with tiktoken `o200k_base` over the
request and response of every call (Claude's tokenizer is not public);
`ANSWER_CACHE_BUDGET_MB=0` so no arm is served a memoised answer; time is one
run per question in a warm process (graph built by an untimed first pass).
Discovery (one `tql_schema` for TQL plans, one `help target_action=uql` for
UQL) is reported separately.

| repo | Q | calls today / uql / grep | tokens today / uql / grep | correct today / uql / grep | uql claims | warm s today / uql | cold s today / uql |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tsa | Q1 | 13 / 1 / 47 | 5,171 / 1,971 / 16,901 | exact / 1/2 / 0/2 | complete,incomplete | 1.04 / 2.41 | 2.45 / 4.12 |
| tsa | Q2 | 1 / 1 / 14 | 4,033 / 984 / 6,091 | 0/1 / 0/1 / exact | incomplete | 0.71 / 0.80 | 1.64 / 2.28 |
| tsa | Q3 | 1 / 1 / 18 | 190 / 1,189 / 7,905 | 0/1 / exact / exact | unknown | 1.40 / 1.97 | 1.50 / 3.03 |
| tsa | Q4 | 2 / 1 / 60 | 5,808 / 2,273 / 16,472 | exact / exact / 1/2 | complete,incomplete | 0.89 / 1.06 | 2.06 / 2.19 |
| tsa | Q5 | 2 / 1 / 14 | 716 / 987 / 3,073 | 0/3 / 0/3 / exact | unknown,unknown,unknown | 1.54 / 1.50 | 2.39 / 2.53 |
| tsa | Q6 | 1 / 1 / 7 | 3,236 / 994 / 3,317 | exact / exact / exact | complete | 0.83 / 1.03 | 1.91 / 2.45 |
| tsa | Q7 | 1 / 1 / 10 | 443 / 1,033 / 6,638 | exact / exact / exact | incomplete | 0.20 / 1.17 | 1.26 / 2.48 |
| tsa | Q8 | 1 / 1 / 3 | 683 / 813 / 1,289 | 0/1 / 0/1 / exact | incomplete | 2.33 / 2.88 | 3.45 / 4.08 |
| rich | Q1 | 6 / 1 / 15 | 4,191 / 1,043 / 5,872 | exact / exact / 0/2 | incomplete,incomplete | 0.17 / 1.07 | 1.05 / 1.79 |
| rich | Q2 | 7 / 1 / 10 | 3,953 / 1,029 / 2,102 | exact / exact / exact | incomplete | 0.27 / 0.82 | 0.92 / 1.17 |
| rich | Q3 | 1 / 1 / 15 | 536 / 988 / 5,520 | 0/1 / exact / 0/1 | incomplete | 0.16 / 0.76 | 0.16 / 1.70 |
| rich | Q4 | 2 / 1 / 28 | 4,491 / 1,166 / 4,130 | 1/2 / exact / exact | complete,incomplete | 0.23 / 0.69 | 0.94 / 1.55 |
| rich | Q5 | 2 / 1 / 61 | 592 / 894 / 24,170 | 1/3 / exact / 0/3 | incomplete,incomplete,incomplete | 0.15 / 0.78 | 0.26 / 1.47 |
| rich | Q6 | 1 / 1 / 4 | 2,114 / 818 / 2,819 | exact / exact / exact | incomplete | 0.11 / 0.38 | 0.92 / 1.24 |
| rich | Q7 | 1 / 1 / 4 | 181 / 788 / 1,804 | exact / exact / exact | incomplete | 0.05 / 0.19 | 0.10 / 1.46 |
| rich | Q8 | 1 / 1 / 3 | 836 / 781 / 3,114 | 0/1 / 0/1 / 0/1 | incomplete | 0.03 / 0.26 | 0.41 / 0.56 |

| repo | arm | calls | tokens | exact answers | wrong `complete` |
| --- | --- | ---: | ---: | ---: | ---: |
| tsa | today | 22 | 20,280 | 4/8 | 0 |
| tsa | uql | 8 | 10,244 | 4/8 | 0 |
| tsa | grep | 173 | 61,686 | 6/8 | 0 |
| rich | today | 21 | 16,894 | 4/8 | 0 |
| rich | uql | 8 | 7,507 | 7/8 | 0 |
| rich | grep | 140 | 49,531 | 4/8 | 0 |

One-time grammar discovery (not included above): `tql_schema` 721 tokens for
the TQL plans today; `help target_action=uql` 845 tokens.

Times are medians of 3 interleaved rounds (today and uql alternate per
question in fresh processes on a shared machine): **warm** = first execution
of the question in a process already warmed by an unrelated `nav callers`
call; **cold** = the question as the first call of a fresh process. They are
*tool* wall time only; today's multi-call plans additionally pay one model
round trip per call (Q1: 13 on TSA, 6 on rich), which is not measured here.

What the numbers say:

- **Calls:** 8 vs 22 (TSA) and 8 vs 21 (rich); grep needs 140–173.
- **Tokens (whole task, o200k estimate):** −49% on TSA (10.2k vs 20.3k) and
  −56% on rich (7.5k vs 16.9k). UQL costs *more* tokens on the three
  single-call questions whose today answer is tiny (TSA/rich Q3, Q5, Q7) —
  there the extra bytes are the per-stage coverage and evidence handles; on
  Q3 and Q5 today's tiny answer is also wrong.
- **Correctness:** 0 wrong `complete` in every arm. Exact answers: rich 7/8
  vs 4/8; TSA 4/8 vs 4/8, and every UQL miss on TSA is labelled
  `incomplete` / `unknown`, while today's misses (Q2, Q3, Q5, Q8) carry no
  claim. Grep looks strong on TSA because the oracle is also name-based
  (it shares grep's assumptions); grep never makes a claim.
- **Wall time: not at parity.** UQL is slower per question in tool time:
  TSA warm 0.8–2.9 s vs 0.2–2.3 s, rich 0.2–1.1 s vs 0.03–0.3 s; cold adds
  ~1 s of import and first-walk cost. The gap is the proof: every relation
  input runs `nav callers`' full RFC-0040 checks, which `test_map`,
  `caller_tree` and TQL do not. The query scope (§5b) cut TSA Q1 from 9.2 s
  to 2.4 s; the remainder is per-input proof work.

## Drawbacks

- **Latency.** Proof costs time: each relation node is a full `nav callers`
  call including its absence gates (~0.3–1.5 s warm on TSA). Questions that
  fan out (`tests()` over 12 callers, `untested()`) are slower than
  `test_map`, which makes no claim. The answer cache (RFC-0027 L6.1) and the
  per-query memo help on repeats; a batch callers entry point would help more.
- **`complete` is rarer.** Most TSA answers end `incomplete` / `unknown`
  because the producers report real gaps. That is the honest state; RFC-0040
  (proof-carrying callers) is what moves it.
- **Stateless cursors re-execute** the query per page.

## Alternatives

- **Upgrade `tql_execute` in place** — rejected: its response shape and the
  selector-only grammar cannot express multi-stage answers without breaking
  callers.
- **Extend `chain`** — rejected as the base: no completeness anywhere in its
  pipeline, duplicated relation lists, and its answer-pack steps (`explore`,
  `include`) have different semantics. Its lexical layer is reused.
- **Reimplement relations over `edges` SQL** — rejected: a second
  interpretation of call edges is exactly the divergence (#1740/#1759/#1773)
  REA's single-owner rule forbids; `nav callers` stays the owner.

## Prior art

REA `docs/tool-design.md` (completeness from examined coverage, typed
errors, single owner, whole-task token accounting) and `docs/mcp-contracts.md`
(`relationship_coverage`, `residual_unknowns`, continuations); mycelium
Hyphae (RFC-0003); jQuery-style chaining (TSA chain DSL).

## Test plan (RED-first)

- `tests/unit/uql/test_uql_parser.py` — grammar → IR; every error code with its
  fix (separator, misspelt stage, chain-only, keyword, depth, order, bare
  word, unbalanced, selector syntax, unknown pseudo / attribute, nested
  validation); closed code registry.
- `tests/unit/uql/test_uql_engine.py` — propagation with an in-memory producer:
  verbatim reason pass-through, one `unknown` input → stage and total
  `unknown`, upstream inheritance, missing / failed producer, list limit,
  source gate, unproven predicates, `tests()` helper walk + nested helper,
  `untested()` membership, depth bound vs closure cap, callees never
  complete, per-query memo, union requests.
- `tests/unit/uql/test_uql_output.py` — compact labels, bounded first page,
  pages concatenate to the whole answer, last page, paging keeps
  completeness, foreign / malformed / stale cursors, unverifiable generation,
  evidence handles only for gaps, full detail provenance, compact < full.
- `tests/unit/mcp/tools/test_uql_tool.py` — real index: callers rows, stage
  completeness equals `nav callers` verbatim, `tests()` via helper,
  `tql_execute` ↔ `uql` select parity, `chain` ↔ `uql` callers parity,
  identical typed rejection, missing index, strict schema, `help` serves the
  grammar card, action advertised.
- `tests/unit/mcp/tools/test_tql_tool.py` — parse-time pseudo-class error,
  unknown attribute no longer silent.
- Contracts: CLI ↔ MCP parity (`search_uql`), facade action docs regenerated,
  grammar-card and `tools/list` size invariants in
  `tests/unit/mcp/test_output_cost_invariants.py`.

## Acceptance criteria

- [x] One grammar and IR; `tql_execute` / `chain` parse through it
- [x] Stages select → relate → refine → page in one call with per-stage
      completeness; total complete only if every stage is
- [x] Typed parse / validation errors with a suggested fix
- [x] Compact default, `detail="full"` opt-in, bounded pages with cursors
- [x] Relations consume `nav callers` completeness as-is (no edits to
      `callers_tool.py` / `callers_reasons.py`)
- [x] Benchmark before/after recorded (§7); 0 wrong `complete`
- [x] CLI ↔ MCP parity test green
- [ ] Owner review of the deprecation path for `chain`
- [x] Docs (facade action reference, CODEMAPS) updated

## What this RFC does NOT do (deferred)

- `imports()` relation: the import-graph producer has no coverage contract;
  adding it now could only ever answer `unknown`. Deferred until it does.
- Retiring `chain` answer-pack steps or `tql_execute`.
- Server-side result retention for cursors; a batch callers entry point.

## Open questions

Answered by the owner (2026-10-24): `uql` joins the answer cache with an
IR + index-identity + generation + paging/detail key (done, §5b);
`tql_execute` reports derived completeness (done, §6); the scoped/bare
callers divergence is #1798 (workaround kept, RFC-0040 owns the fix);
`chain` is deprecated in docs only (done, §6).

1. Tool wall time is above today's best multi-call workflow on most
   questions (§7). Is "fewer calls, fewer tokens, labelled coverage" worth
   ~0.5–1.5 s more tool time per question, given today's plans pay one model
   round trip per extra call? The next lever is a batched `nav callers`
   entry point that runs the per-input RFC-0040 checks over one shared
   target set.
2. Default `limit` 50 — measured fine for these questions; revisit with
   fan-out-heavy repos.