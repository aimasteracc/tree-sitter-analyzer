# RFC-0015: 瞬間 UML 图族 — Instant UML Family

- **Status**: implemented (Phase 1 #462; P2-A #472; P2-B #475; all in v1.23.0)
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-11
- **Last updated**: 2026-06-11 (adversarial review round 1 — lead-triaged verdicts applied)
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/uml_export.py` (lines 313–356 today: `sequence_diagram`)
  - `tree_sitter_analyzer/mcp/tools/uml_tool.py` (`CodeGraphUMLTool`, `validate_arguments`, schema)
  - `tree_sitter_analyzer/mcp/tools/viz_facade.py` (action registration)
  - `tree_sitter_analyzer/cli/argument_groups/_analysis_codegraph.py` (`--uml-*` flags)
  - `tree_sitter_analyzer/cli/commands/mcp_commands/_builders.py` (`_build_uml_tool_args`)
  - `tree_sitter_analyzer/cli/commands/mcp_commands/_specs_extended.py` (UML spec)
  - `tests/unit/test_uml_tool.py`
  - `tests/unit/test_uml_export.py`
  - `tests/unit/test_uml_export_renderers.py`
  - `tests/unit/cli/test_uml_cli.py`
  - `tests/unit/cli/test_uml_export_cli_contract.py`
  - `tests/unit/mcp/test_output_cost_invariants.py` (differential invariant — Phase 1)

## Summary

The existing `viz action=uml` family has three live bugs (file/class-scoping params
silently dropped, a broken `max_edges` validator that rejects valid integer inputs via
the bool-guard path, and whole-project diagrams polluted by test-corpus classes) and
misses two diagram types valuable to AI agents (control-flow `activity` and
state-machine `state`). This RFC fixes the three Phase-1 defects in the existing
diagrams, then adds the two new diagram types in Phase 2. A small observability
label for sequence-diagram call resolution (`call_path+synapse_resolved`) is folded
into Phase 1 as a one-liner — no behaviour change.

## Motivation

### Live bugs found 2026-06-11 (reproduced by lead)

**viz-08 (RFC-0013 antecedent):** `viz action=uml diagram=class file_path="..."`
passes a `file_path` param that `CodeGraphUMLTool`'s schema does not declare
(`uml_tool.py:40–92`). The facade's `_project_args` whitelists caller args against
the inner's `inputSchema.properties`; any undeclared param is stripped before the
inner sees it. The result is always a 209-node, ~74 000-char whole-project flood
regardless of the intended scope. RFC-0013's `ignored_params` field will make the
drop visible, but the real fix is to **declare and honour** the scoping params so the
drop does not occur at all. Same issue applies to `class_name`.

**`max_edges` validator bug (`uml_tool.py:102–105`):** The validator uses:

```python
for key in ("max_edges", "max_depth", "max_paths", "package_depth"):
    value = arguments.get(key)
    if value is not None and (not isinstance(value, int) or value < 1):
        raise ValueError(f"{key} must be a positive integer")
```

**Verified root cause (P2-1, 2026-06-11):** The MCP stdio JSON-RPC path
(`json.loads`) preserves `int` literals as Python `int`; the standard transport does
not introduce floats. The `apply_toon_format_to_response` / TOON path only touches
the *output* dict, never the incoming arguments. The reject-on-`max_edges=30`
incident occurred because `isinstance(True, int)` is `True` in Python (bool is a
subclass of int) **and** because some LLM clients emit JSON numbers with a decimal
point (`30.0`) even when the schema declares `"type": "integer"`. In the
`_clean_bespoke_args` / facade normalization path (`facade_tool.py`), arguments pass
through as-is (no coercion), so a `30.0` from the LLM arrives at `validate_arguments`
as a Python `float`, which is not `isinstance(…, int)`, causing the spurious reject.

Two failure modes requiring fixes:

1. **Float input from LLM (confirmed root cause):** LLM clients sometimes emit
   `30.0` in JSON even when `"type": "integer"` is declared. `isinstance(30.0, int)`
   is `False` in Python (unlike JavaScript/JSON semantics), so the validator raises
   `"max_edges must be a positive integer"` for a valid caller intent of 30. This
   must be fixed in both `uml_tool.py` **and** `codegraph_sitemap_tool.py` (shared
   pattern) by extracting a shared validator util `_validate_positive_int`.

2. **Bool pass-through (silent data loss):** Python's `bool` is a subclass of `int`;
   `isinstance(True, int)` is `True` and `True < 1` is `False` (since `True == 1`).
   A caller passing `max_edges=True` silently gets `max_edges=1`, losing all but one
   edge with no error. The fix must exclude `bool` explicitly.

The correct fix: accept any non-bool `int` ≥ 1 and any whole-number `float` ≥ 1
(coercing it to `int` in place); reject booleans, fractions, and non-numeric values
with a precise error message. The fix is extracted to a shared validator utility
(`_validate_positive_int`) used by both `uml_tool.py` and `codegraph_sitemap_tool.py`
for consistency. (Per-tool divergence would leave `sitemap_tool` vulnerable to the
same float class after this RFC lands — rejected for that reason.)

**Test-corpus pollution:** `ClassHierarchy.all_classes()` returns every class in
the indexed project, including test fixtures (e.g. `Cat`, `Animal`, `TestFoo` from
`tests/` and `test_data/`). A whole-project class diagram on TSA itself emits 209
nodes, dozens of which are test-corpus classes that are noise for architecture
consumers. The fix is a default `include_tests=False` param that strips paths
whose `Path.parts` overlap `_TEST_DIRS = frozenset({"tests", "test_data",
"fixtures"})`.

### Phase-2 gaps felt by AI agents

Agents navigating control flow today use `nav action=call_path` to trace edges but
have no single-function **visual** of branches and loops. A `diagram=activity`
diagram (control-flow graph → Mermaid `flowchart TD`) closes this gap in one call.
Similarly, finite-state machines encoded as Python `enum`s or `match` expressions
have no visual summary; a `diagram=state` (`stateDiagram-v2`) provides one —
honestly labelled "static approximation" because full FSM extraction requires
execution.

### Sequence-diagram observability gap (folded into Phase 1)

`UMLExporter.sequence_diagram` calls `CallPathFinder.find_path`
(`uml_export.py:313–356`), which does BFS over the `edges` table. The `_fwd_state`
/ `_fwd_hop` helpers in `call_path.py` **already** read `callee_resolved_file` from
the metadata JSON blob (lines 62 and 70 respectively). There is no "sequence
enhancement" gap to fill here — the resolved file is already used in BFS traversal.
The only missing piece is an **observability label**: when at least one hop has
`callee_resolved_file` populated, `metadata["source"]` should read
`"call_path+synapse_resolved"` instead of `"call_path"` so consumers can tell
whether synapse resolution contributed. This is a one-liner metadata annotation with
no behaviour change, folded into Phase 1 as part of the sequence-diagram PR.

**Stale-file / query-time parse costs for activity and state (Phase 2):** The
`activity` and `state` diagrams require reading AST *bodies*, which are **not**
cache-resident — `ast_symbol_rows` stores only `name`, `kind`, `file_path`,
`language`, `line`, `end_line` (see `_ast_cache_schema.py:405–413`). Each call
therefore requires a **disk read + tree-sitter parse of the file** at query time.
Cost implications:

- Single-function `activity` diagram: one file read + parse, typically < 50 ms.
- `state` diagram: one or more file reads depending on how many Enum classes are
  found; capped by `max_nodes`.

Stale/deleted-file behavior: if the file has changed since indexing, the current
on-disk content is parsed (best-effort); `metadata["note"]` records
`"parsed from current file content; may differ from indexed symbols"`. If the file
is missing (deleted after indexing), the tool returns `verdict="NOT_FOUND"` with a
`next_step` message explaining that the indexed symbol's source file no longer exists.

A rule-11 latency invariant for these diagram types is defined in the test plan.

## Detailed design

### Phase 1 — Fix the existing family

#### P1-A: file/class scoping for `diagram=class`

Add two new parameters to `CodeGraphUMLTool.get_tool_schema()` under `properties`:

```python
"file_path": {
    "type": "string",
    "description": (
        "Limit class diagram to classes defined in this file "
        "and their direct bases/dependents from the full project."
    ),
},
"class_name": {
    "type": "string",
    "description": (
        "Show the named class plus its direct superclasses and "
        "immediate subclasses (neighbourhood subgraph, up to max_edges)."
    ),
},
```

`UMLExporter.class_diagram` gains three optional keyword-only parameters:

```python
def class_diagram(
    self,
    max_edges: int = 200,
    include_external_bases: bool = True,
    *,
    file_path: str | None = None,
    class_name: str | None = None,
    include_tests: bool = False,
) -> UMLDiagram:
```

Scoping semantics (applied in order; first match wins):

1. **`class_name` given** — build the neighbourhood subgraph: the named class,
   all its direct superclasses (one hop up), and all its direct subclasses (one hop
   down). `max_edges` caps the result; `truncated=True` when the cap fires.
2. **`file_path` given** — include only classes whose `file` column in
   `ast_symbols` matches `file_path` (resolved relative to `project_root`). Also
   include direct bases that live outside the file so inheritance arrows are
   correct. `max_edges` caps as usual.
3. **Neither given** — whole-project view (current behaviour), subject to
   `include_tests`.

`include_tests=False` (new default) strips any class whose resolved `file` path
contains a path segment in `_TEST_DIRS`. Call `include_tests=True` to restore the
current whole-project behaviour.

`package_diagram` and `component_diagram` also gain `include_tests` (with the same
default) so the whole-project import graphs are similarly clean.

Scoping metadata labels: `metadata["scope"]` is `"file"`, `"class_neighbourhood"`,
or `"whole_project"` according to which branch fired.

#### P1-B: fix the `max_edges` validator and extract shared util

Extract to a new module `tree_sitter_analyzer/mcp/tools/_validators.py`:

```python
def _validate_positive_int(arguments: dict, key: str) -> None:
    """Validate and in-place coerce a positive-integer argument.

    Accepts non-bool int >= 1 and whole-number float >= 1 (coerced to int).
    Rejects booleans, fractional floats, non-numeric values, and zero/negative
    inputs with a precise ValueError.

    In-place coercion is safe because validate_arguments always runs before
    execute and the facade passes a projected copy, so the mutation is contained.
    """
    value = arguments.get(key)
    if value is None:
        return
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a positive integer, got bool {value!r}")
    if isinstance(value, float):
        if value != int(value) or value < 1:
            raise ValueError(
                f"{key} must be a positive integer, got float {value!r}"
            )
        arguments[key] = int(value)
        return
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} must be a positive integer, got {value!r}")
```

`CodeGraphUMLTool.validate_arguments` calls `_validate_positive_int` for each of
`("max_edges", "max_depth", "max_paths", "package_depth")`.

`CodeGraphSitemapTool.validate_arguments` calls `_validate_positive_int` for each
of `("max_files", "max_symbols")` (removing the inline guard so both tools share
the same logic and float-handling path).

#### P1-C: `include_tests` parameter and sentinel constant

In `uml_export.py`, add:

```python
_TEST_DIRS: frozenset[str] = frozenset({"tests", "test_data", "fixtures"})


def _is_test_path(file_path: str) -> bool:
    return any(part in _TEST_DIRS for part in Path(file_path).parts)
```

Add `include_tests` to `CodeGraphUMLTool.get_tool_schema()`:

```python
"include_tests": {
    "type": "boolean",
    "default": False,
    "description": (
        "Include test-corpus classes (under tests/, test_data/, fixtures/) "
        "in whole-project diagrams. Default False."
    ),
},
```

#### P1-D: honest truncation note in Mermaid output

When `UMLDiagram.truncated` is `True`, the Mermaid renderers (`render_class_mermaid`,
`render_flowchart_mermaid`) append:

```
%% NOTE: diagram truncated — only the top N edges shown.
%% Pass a higher max_edges value to see more, or use file_path / class_name to scope.
```

#### P1-E: sequence-diagram observability label (one-liner, folds into Phase 1 PR)

In `UMLExporter.sequence_diagram` (`uml_export.py:313–356`), after collecting
`paths` from `CallPathFinder`, check whether any hop has a non-empty
`callee_resolved_file`:

```python
has_resolved = any(
    hop.get("callee_file")
    for path in result_dict.get("paths", [])
    for hop in path.get("hops", [])
)
source_label = "call_path+synapse_resolved" if has_resolved else "call_path"
# ... existing metadata dict: replace "source": "call_path" with source_label
```

This is a metadata-only annotation. `call_path.py:62/70` already read
`callee_resolved_file` in BFS; no BFS behaviour changes.

### Phase 2 — New diagram types

#### P2-A: `diagram=activity` — single-function control-flow graph

A structural CFG for a single function, rendered as `flowchart TD`.
Requires a **disk read + tree-sitter parse** per call (AST bodies are not
cache-resident; `ast_symbol_rows` stores only `name/kind/file_path/language/line/end_line`).

**New parameters:**

| param | type | default | description |
|-------|------|---------|-------------|
| `function_name` | string | **required** | Function to graph (module.function or bare name; first match used) |
| `file_path` | string | optional | Disambiguate when multiple functions share a name |
| `max_nodes` | integer | 50 | Cap on CFG nodes; `truncated=True` when exceeded |

**Algorithm (tree-sitter AST walk):**

1. Locate the function body node via `ast_symbols` (kind=function/method, filtered
   by `file_path` if given).
2. Walk the body's AST, emitting one CFG node per:
   - entry point (function name label)
   - `if` / `elif` branch (condition text, <= 40 chars)
   - `for` / `while` loop (loop-header text, <= 40 chars)
   - `return` / `raise` / `yield` statement (kind + first 20 chars of expression)
   - implicit exit (if the function can fall off the end)
3. Add directed edges: sequential flow, true/false branch edges for conditionals,
   back-edge for loop headers. `break` / `continue` are terminal nodes (not wired
   to loop exits — dominance analysis is out of scope).
4. Render as `flowchart TD` using `render_flowchart_mermaid`.

**Prepend to Mermaid output:**

```
%% NOTE: activity diagram is a structural AST approximation.
%% Exception edges, async suspension, and dynamic dispatch are not modelled.
```

New method: `UMLExporter.activity_diagram(function_name, file_path=None, max_nodes=50) -> UMLDiagram`.
Returns `diagram_type="activity"`, `mermaid_type="flowchart"`.

**Stale/deleted-file behavior:** activity ALWAYS re-parses the current file from
disk (AST bodies are not cache-resident), so `metadata["note"]` is ALWAYS set to
`"parsed from current file content; may differ from indexed symbols"` on every
successful diagram — regardless of whether the file changed since indexing.
File missing -> `verdict="NOT_FOUND"` with `next_step`.

**Zero-transition NOT_FOUND:** if the AST walk produces zero nodes (function body
empty or unparseable), return `verdict="NOT_FOUND"` with a `next_step` explaining
the heuristic limitation (e.g. "activity diagram found no control-flow nodes in
`function_name`; the function may be a stub or use a pattern not yet supported").

**CLI:** extend `--uml` enum to include `activity`. New flags: `--uml-function`
(function name, string) and `--uml-max-nodes` (integer, default 50). Note:
`--uml-file-path` (added in P1-A) also serves `activity` for disambiguation.

#### P2-B: `diagram=state` — FSM approximation from enums/match

State-machine approximation rendered as `stateDiagram-v2`.
Requires a **disk read + tree-sitter parse** per Enum file (AST bodies not cache-resident).

**New parameters:**

| param | type | default | description |
|-------|------|---------|-------------|
| `class_name` | string | optional | Limit to a named `Enum` subclass |
| `file_path` | string | optional | Scope to a single file |
| `max_nodes` | integer | 30 | Cap on state nodes |

**Algorithm:**

1. Query `ast_symbols` for `Enum` subclasses (kind=class, inherits `Enum`).
   Apply `class_name` / `file_path` filters if given.
2. Each enum member becomes a `[*] --> StateName` initial-state edge.
3. Scan `match` / `case` patterns in function bodies via AST walk: each `case` arm
   whose subject matches an enum member and whose body assigns to the same variable
   becomes a `StateA --> StateB` transition (heuristic).
4. Render as `stateDiagram-v2` using new `render_state_mermaid`.

**Stale/deleted-file behavior:** same as P2-A — parse current file content on
staleness, NOT_FOUND on missing file.

**Zero-transition NOT_FOUND:** zero detected transitions -> `verdict="NOT_FOUND"` +
`next_step` explaining the heuristic limitation ("state diagram found no enum
members or match-pattern transitions; the class may not encode a finite-state
machine in a pattern this heuristic recognises").

**Prepend to Mermaid output:**

```
%% NOTE: state diagram is a static approximation.
%% Guard conditions, timers, and exception-driven transitions are not captured.
```

`metadata["analysis_kind"] = "static_approximation"`.

New method: `UMLExporter.state_diagram(class_name=None, file_path=None, max_nodes=30) -> UMLDiagram`.
Returns `diagram_type="state"`, `mermaid_type="stateDiagram-v2"`.

**CLI:** extend `--uml` enum to include `state`. Uses `--uml-class-name` (added in
P1-A) for class filter.

### Output-size budgets (flood prevention)

`_DEFAULT_MAX_EDGES = 200` in `uml_tool.py` produces ~74 000-char output for
whole-project class diagrams. Replace with per-diagram constants:

| diagram | new default | old default | rationale |
|---------|-------------|-------------|-----------|
| `class` (whole-project) | 80 edges / 60 nodes | 200 | ~8 000 chars; use scoping for more |
| `class` (file-scoped) | 50 edges | 200 | single file rarely exceeds this |
| `class` (neighbourhood) | 30 edges | 200 | direct neighbourhood only |
| `package` | 60 edges | 200 | package count bounded by depth |
| `component` | 40 edges | 200 | top-level components only |
| `sequence` | unchanged | — | call-path depth is the natural cap |
| `activity` | 50 nodes | — | single function |
| `state` | 30 nodes | — | FSMs are small by definition |

`_DEFAULT_MAX_EDGES` is split into `_DEFAULT_CLASS_MAX_EDGES`,
`_DEFAULT_PACKAGE_MAX_EDGES`, `_DEFAULT_COMPONENT_MAX_EDGES` constants.
The old `_DEFAULT_MAX_EDGES = 200` is removed.

### MCP surface (facade + action)

No structural change to the `viz` facade (`viz_facade.py`). `viz action=uml` continues
to route to `CodeGraphUMLTool`. The facade's public schema uses
`additionalProperties: True`, so new params pass through to the inner unchanged.

The inner tool (`uml_tool.py`) is updated:

- `diagram` enum extended: `["class", "package", "component", "sequence", "activity", "state"]`.
- New properties declared: `file_path`, `class_name`, `include_tests`, `function_name`, `max_nodes`.
- `validate_arguments` extended: `diagram=activity` requires `function_name`;
  `diagram=sequence` still requires `source` and `target`.

No new facade action is added — all diagram types are variants of `viz action=uml`.

### Error handling

| condition | response |
|-----------|----------|
| `diagram=activity` without `function_name` | `ValueError("function_name is required for activity diagrams")` |
| `diagram=activity` — zero CFG nodes detected | `verdict="NOT_FOUND"` + `next_step` explaining heuristic limit |
| `diagram=state` — zero transitions detected | `verdict="NOT_FOUND"` + `next_step` explaining heuristic limit |
| `file_path` passed to `diagram=sequence` | `ignored_params=["file_path"]` via RFC-0013; sequence uses `source`/`target` |
| `class_name` passed to `diagram=package` or `diagram=component` | `ignored_params=["class_name"]` via RFC-0013 |
| Unknown `diagram` value | `ValueError("Unsupported UML diagram: ...")` (unchanged) |
| AST parse failure in P2-A/P2-B (file exists, tree-sitter error) | Return `UMLDiagram(nodes=[], edges=[], truncated=False)` with `metadata["error"]` set; do NOT raise |
| Function/class file missing (deleted after indexing) | `verdict="NOT_FOUND"` + `next_step` |
| File stale (changed since indexing) | Parse current file; `metadata["note"]` records the staleness |
| RFC-0013 `ignored_params` for scoping params on sequence/package/component | **Deferred pending RFC-0013 implementation.** Interim behavior: silently ignored today, documented here. |

## Three-Surface impact (CLI <-> MCP parity)

TSA holds a hard CLI<->MCP parity rule. All new/changed params:

| MCP param (`viz action=uml ...`) | CLI flag | Phase |
|----------------------------------|----------|-------|
| `file_path` | `--uml-file-path` (NEW) | P1 |
| `class_name` | `--uml-class-name` (NEW) | P1 |
| `include_tests` | `--uml-include-tests` (NEW, `store_true`) | P1 |
| `diagram=activity` | `--uml activity` (extend enum) | P2 |
| `function_name` | `--uml-function` (NEW, string) | P2 |
| `diagram=state` | `--uml state` (extend enum) | P2 |
| `max_nodes` | `--uml-max-nodes` (NEW, `type=int`, default 50) | P2 |

Existing flags unchanged: `--uml-source`, `--uml-target`, `--uml-max-edges`,
`--uml-max-depth`, `--uml-max-paths`, `--uml-package-depth`,
`--uml-no-external-bases`.

`_build_uml_tool_args` in `_builders.py` is updated to read and pass all new params.

TOON default on MCP, JSON on CLI — intentional per CLAUDE.md §1 (LOCKED).

## Drawbacks

- **CFG fidelity limits:** The `activity` diagram is a structural AST
  approximation. Exception propagation, async suspension, generator yields beyond
  the first, and dynamic dispatch are not modelled. The Mermaid comment and
  `metadata["analysis_kind"] = "structural_approximation"` mitigate
  misinterpretation.
- **State-machine approximation honesty:** The `state` diagram heuristic (enum
  members + `match`/`case` patterns) produces false-positive transitions when
  `match` is used for non-FSM pattern matching. The "static approximation" label is
  the only mitigation.
- **Default-cap change breaks pinned tests:** Lowering `_DEFAULT_MAX_EDGES` from
  200 to per-diagram values will red-light any test that pins `edge_count == 200`
  at the old default. Specifically, `test_uml_tool_schema_lists_diagrams` (which
  today asserts `enum == ["class", "package", "component", "sequence"]`) must be
  re-pinned to `["class", "package", "component", "sequence", "activity", "state"]`
  after Phase 2. `test_class_diagram_execute_with_mock_exporter` pins the
  `FakeExporter.class_diagram(max_edges: int, include_external_bases: bool)` kwargs
  — after P1-A adds `file_path`, `class_name`, and `include_tests` kwargs, the
  FakeExporter signature must be updated to accept the new params. These are correct
  RED-first regressions, not regressions to hide.
- **`include_tests=False` default changes whole-project node count:** Any test that
  pins the exact node count at 209 will go RED. The new pin is the measured value
  after test-corpus exclusion. RED is correct — the old count was inflated noise.
- **In-place mutation of `arguments`:** The float->int coercion mutates the caller's
  projected dict. Safe because `validate_arguments` runs before `execute` and the
  facade passes a projected copy. Documented in inline comments.
- **Query-time parse latency for P2-A/P2-B:** Activity and state diagrams require a
  disk read + tree-sitter parse per call (not from cache). Cost is bounded by the
  single-file scope (`max_nodes` caps walk early). A rule-11 latency invariant in
  the test plan pins the ceiling.

## Alternatives

- **A: Keep `class` whole-project only; advise agents to use `nav action=context`
  for file-scoped structure.** Rejected — Mermaid diagrams are consumed by
  non-agentic UIs (renderers, markdown previews). The viz-08 silent-drop is a
  correctness bug regardless.
- **B: New facade action `viz action=cfg` for control-flow graphs.** Rejected —
  the diagram family is unified under `viz action=uml`. A separate action fragments
  the discovery surface with no benefit.
- **C: Separate `viz action=uml` (existing) and `viz action=uml2` (new types).**
  Rejected — same fragmentation concern as B.
- **D: Increase `max_edges` default instead of adding scoping params.** Rejected —
  74 000-char flood is already above useful MCP token budgets. More edges = more
  noise. Scoping + lower caps are the correct fix.
- **E: Hard-reject float `max_edges`; do not coerce.** Rejected — the bug is an
  LLM-client artifact (LLMs emit `30.0` even with `"type": "integer"` in schema),
  not a user error. Coercion is the lenient-correct behaviour.
- **F: Fix viz-08 only via RFC-0013 `ignored_params` (make drop visible, not
  prevent it).** Rejected for the scoping case — RFC-0013 makes drops visible
  but the right fix is to declare the params so drops do not occur.
- **G: Per-tool float-guard in uml_tool.py only, not a shared util.** Rejected —
  `codegraph_sitemap_tool.py` has the same guard pattern (`isinstance(value, bool)
  or not isinstance(value, int)`) without float handling; divergence after this RFC
  leaves it vulnerable. Shared util is the consistent fix.

## Prior art

- **Mermaid.js:** `classDiagram`, `sequenceDiagram`, `flowchart TD`, and
  `stateDiagram-v2` are native Mermaid diagram types. TSA maps AST-derived
  structures to these types directly; no Mermaid rendering engine is introduced.
- **PlantUML / Doxygen:** generate class and sequence diagrams from source. TSA
  diverges by using its indexed SQLite AST cache, so diagrams are available
  on-demand without a separate parse pass.
- **pyflowchart** (cdfmlr/pyflowchart): Python-specific CFG-to-flowchart. TSA
  adopts the same structural-approximation approach but uses tree-sitter's
  cross-language AST, enabling `activity` for Go, Rust, TypeScript, etc.
- **rust-analyzer / clangd:** `callHierarchy` LSP responses are the structural
  equivalent of `diagram=sequence`; TSA renders the same information as Mermaid
  rather than JSON.
- **codegraph (colbymchenry):** The `uml` facet in `codegraph_query` already covers
  flowchart rendering (`codegraph_visualization_hub.py`). TSA extends further with
  `classDiagram` and `stateDiagram-v2`.

## Test plan (RED-first)

All tests are **unit tests** (no xdist, no full-suite run, exact assertions only).
Write each test first to confirm RED; implement to GREEN.

### Phase 1

#### P1-A schema / scoping

```python
# tests/unit/test_uml_tool.py

def test_uml_schema_declares_file_path() -> None:
    tool = CodeGraphUMLTool()
    assert "file_path" in tool.get_tool_schema()["properties"]  # RED before fix

def test_uml_schema_declares_class_name() -> None:
    tool = CodeGraphUMLTool()
    assert "class_name" in tool.get_tool_schema()["properties"]  # RED before fix

def test_uml_schema_declares_include_tests() -> None:
    tool = CodeGraphUMLTool()
    props = tool.get_tool_schema()["properties"]
    assert "include_tests" in props                               # RED before fix
    assert props["include_tests"]["default"] is False

# tests/unit/test_uml_export.py  (uses mock ASTCache)

def test_class_diagram_file_scoped_scope_field(mock_cache_two_files) -> None:
    exporter = UMLExporter("/repo", mock_cache_two_files)
    diagram = exporter.class_diagram(file_path="src/a.py")
    assert diagram.metadata["scope"] == "file"                   # RED before fix

def test_class_diagram_class_neighbourhood_scope_field(mock_cache_two_files) -> None:
    exporter = UMLExporter("/repo", mock_cache_two_files)
    diagram = exporter.class_diagram(class_name="MyClass")
    assert diagram.metadata["scope"] == "class_neighbourhood"    # RED before fix
    assert "MyClass" in diagram.nodes

def test_class_diagram_excludes_test_classes_by_default(mock_cache_with_test_classes) -> None:
    # fixture returns exactly 2 prod classes + 3 test classes (Cat/Animal/TestBase)
    exporter = UMLExporter("/repo", mock_cache_with_test_classes)
    diagram = exporter.class_diagram()
    test_nodes = [n for n in diagram.nodes if n in {"Cat", "Animal", "TestBase"}]
    assert test_nodes == []                                       # exact: zero

def test_class_diagram_include_tests_restores_all(mock_cache_with_test_classes) -> None:
    exporter = UMLExporter("/repo", mock_cache_with_test_classes)
    diagram = exporter.class_diagram(include_tests=True)
    test_nodes = [n for n in diagram.nodes if n in {"Cat", "Animal", "TestBase"}]
    assert len(test_nodes) == 3        # exact pin; re-measure if fixture changes
```

#### P1-B validator (shared util + uml_tool + sitemap_tool)

```python
# tests/unit/test_uml_tool.py

def test_max_edges_float_whole_number_coerced() -> None:
    tool = CodeGraphUMLTool()
    args: dict = {"diagram": "class", "max_edges": 30.0}
    tool.validate_arguments(args)
    assert args["max_edges"] == 30       # exact
    assert type(args["max_edges"]) is int

def test_max_edges_float_fractional_rejected() -> None:
    tool = CodeGraphUMLTool()
    with pytest.raises(ValueError, match="max_edges"):
        tool.validate_arguments({"diagram": "class", "max_edges": 30.5})

def test_max_edges_bool_true_rejected() -> None:
    tool = CodeGraphUMLTool()
    with pytest.raises(ValueError, match="max_edges"):
        tool.validate_arguments({"diagram": "class", "max_edges": True})

def test_max_edges_bool_false_rejected() -> None:
    tool = CodeGraphUMLTool()
    with pytest.raises(ValueError, match="max_edges"):
        tool.validate_arguments({"diagram": "class", "max_edges": False})

# tests/unit/mcp/tools/test_validators.py  (new file — shared util)

def test_sitemap_tool_accepts_float_whole_number() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import CodeGraphSitemapTool
    tool = CodeGraphSitemapTool()
    args = {"mode": "full", "max_files": 50.0}
    tool.validate_arguments(args)
    assert args["max_files"] == 50
    assert type(args["max_files"]) is int

def test_sitemap_tool_rejects_bool_max_files() -> None:
    from tree_sitter_analyzer.mcp.tools.codegraph_sitemap_tool import CodeGraphSitemapTool
    tool = CodeGraphSitemapTool()
    with pytest.raises(ValueError, match="max_files"):
        tool.validate_arguments({"mode": "full", "max_files": True})
```

#### P1-C truncation comment

```python
def test_truncated_class_diagram_has_mermaid_comment(monkeypatch) -> None:
    # force truncation by patching _clamp_edges to return truncated=True
    ...
    assert "%% NOTE: diagram truncated" in diagram.mermaid

def test_non_truncated_diagram_has_no_truncation_comment(monkeypatch) -> None:
    ...
    assert "%% NOTE: diagram truncated" not in diagram.mermaid
```

#### P1-D viz-08 integration

```python
# tests/unit/mcp/tools/test_viz_facade_uml.py  (new file)

def test_file_path_not_dropped_after_fix() -> None:
    from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade
    from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool
    facade = build_viz_facade("/repo")
    inner = facade.action_map["uml"]
    projected = FacadeTool._project_args.__func__(
        facade, inner,
        {"action": "uml", "diagram": "class", "file_path": "src/foo.py"},
    )
    assert "file_path" in projected         # was ABSENT before fix
    assert projected["file_path"] == "src/foo.py"

def test_class_name_not_dropped_after_fix() -> None:
    from tree_sitter_analyzer.mcp.tools.viz_facade import build_viz_facade
    from tree_sitter_analyzer.mcp.tools.facade_tool import FacadeTool
    facade = build_viz_facade("/repo")
    inner = facade.action_map["uml"]
    projected = FacadeTool._project_args.__func__(
        facade, inner,
        {"action": "uml", "diagram": "class", "class_name": "MyClass"},
    )
    assert "class_name" in projected        # was ABSENT before fix
```

#### P1-E sequence-diagram observability

```python
# tests/unit/test_uml_export.py

def test_sequence_source_reflects_synapse(mock_resolved_call_path) -> None:
    exporter = UMLExporter("/repo")
    diagram = exporter.sequence_diagram("caller_fn", "target_fn")
    assert diagram.metadata["source"] == "call_path+synapse_resolved"

def test_sequence_source_falls_back_without_synapse(mock_unresolved_call_path) -> None:
    exporter = UMLExporter("/repo")
    diagram = exporter.sequence_diagram("caller_fn", "target_fn")
    assert diagram.metadata["source"] == "call_path"
```

#### Output-cost differential invariant (rule-11, Phase 1)

Add to `tests/unit/mcp/test_output_cost_invariants.py`:

```python
def test_class_diagram_scoped_smaller_than_unscoped(tmp_path) -> None:
    """Scoped class diagram bytes < unscoped bytes (rule-11 differential invariant).

    Scoping (file_path or class_name) restricts the node/edge set, so the
    serialized response for a scoped request MUST be strictly smaller than
    the unscoped whole-project response on the same project. If this assertion
    goes RED, a scoping implementation bug inflated the output — investigate
    before re-pinning.

    Exact == pin not applicable here because bytes vary with project content;
    the invariant is the *relationship* between scoped and unscoped (CLAUDE.md
    rule-11 exception for nondeterministic values — assert a documented
    invariant, not a hand-waved bound).
    """
    import asyncio, json
    from tree_sitter_analyzer.mcp.tools.uml_tool import CodeGraphUMLTool
    # Skeleton — implementer fills in with real indexed tmp_path fixture once
    # the Phase-1 UMLExporter scoping is implemented and the index is wired.
    # The relationship invariant: scoped_bytes < unscoped_bytes is the contract.
    pass  # RED until implemented with a real indexed fixture
```

### Phase 2

```python
# tests/unit/test_uml_tool.py

def test_uml_tool_schema_lists_diagrams() -> None:
    # Re-pin after Phase 2 — was ["class", "package", "component", "sequence"]
    tool = CodeGraphUMLTool()
    assert tool.get_tool_schema()["properties"]["diagram"]["enum"] == [
        "class", "package", "component", "sequence", "activity", "state"
    ]

def test_activity_diagram_requires_function_name() -> None:
    tool = CodeGraphUMLTool()
    with pytest.raises(ValueError, match="function_name is required"):
        tool.validate_arguments({"diagram": "activity"})

def test_activity_in_diagram_enum() -> None:
    tool = CodeGraphUMLTool()
    assert "activity" in tool.get_tool_schema()["properties"]["diagram"]["enum"]

def test_state_in_diagram_enum() -> None:
    tool = CodeGraphUMLTool()
    assert "state" in tool.get_tool_schema()["properties"]["diagram"]["enum"]

# tests/unit/test_uml_export.py

def test_activity_diagram_mermaid_type_and_comment(monkeypatch, mock_ast_walk) -> None:
    exporter = UMLExporter("/repo", mock_ast_walk)
    diagram = exporter.activity_diagram("my_func", file_path="src/mod.py")
    assert diagram.mermaid.startswith("flowchart TD")
    assert "%% NOTE: activity diagram is a structural AST approximation" in diagram.mermaid
    assert diagram.metadata["diagram_type"] == "activity"

def test_activity_diagram_node_count_exact(mock_simple_function_cache) -> None:
    # fixture: function with 1 if-branch -> entry + condition + true-body + false-body + exit = 5 nodes
    exporter = UMLExporter("/repo", mock_simple_function_cache)
    diagram = exporter.activity_diagram("simple_func")
    assert len(diagram.nodes) == 5   # exact pin — re-measure if fixture changes

def test_activity_diagram_zero_nodes_returns_not_found(mock_empty_function_cache) -> None:
    exporter = UMLExporter("/repo", mock_empty_function_cache)
    result = exporter.activity_diagram("empty_func")
    assert result.metadata.get("verdict") == "NOT_FOUND"

def test_state_diagram_mermaid_type_and_comment(mock_enum_cache) -> None:
    exporter = UMLExporter("/repo", mock_enum_cache)
    diagram = exporter.state_diagram(class_name="TrafficLight")
    assert diagram.mermaid_type == "stateDiagram-v2"
    assert "%% NOTE: state diagram is a static approximation" in diagram.mermaid
    assert diagram.metadata["analysis_kind"] == "static_approximation"

def test_state_diagram_zero_transitions_returns_not_found(mock_no_transition_enum) -> None:
    exporter = UMLExporter("/repo", mock_no_transition_enum)
    result = exporter.state_diagram(class_name="EmptyEnum")
    assert result.metadata.get("verdict") == "NOT_FOUND"

# tests/unit/cli/test_uml_cli.py

def test_phase1_cli_flags_registered() -> None:
    from tree_sitter_analyzer.cli_main import create_argument_parser
    parser = create_argument_parser()
    long_flags = {a.option_strings[-1] for a in parser._actions if a.option_strings}
    for flag in ("--uml-file-path", "--uml-class-name", "--uml-include-tests"):
        assert flag in long_flags, f"Phase-1 CLI flag missing: {flag}"

def test_phase2_cli_flags_registered() -> None:
    from tree_sitter_analyzer.cli_main import create_argument_parser
    parser = create_argument_parser()
    long_flags = {a.option_strings[-1] for a in parser._actions if a.option_strings}
    for flag in ("--uml-function", "--uml-max-nodes"):
        assert flag in long_flags, f"Phase-2 CLI flag missing: {flag}"
```

**Rule-11 latency invariant (Phase 2, activity/state disk-parse):**

Add to `tests/unit/mcp/test_output_cost_invariants.py`:

```python
def test_activity_diagram_parse_cost_bounded(tmp_path) -> None:
    """Activity diagram parse is bounded: one file read + one tree-sitter parse.

    Rule-11 invariant: a single-function activity diagram must NOT trigger more
    than one parse (verified by monkeypatching the parser and asserting call_count
    == 1). This catches regressions where the implementation re-parses multiple
    files or re-parses the same file.
    """
    # Skeleton — implementer fills in with mock tree-sitter parse call counter.
    pass
```

### PR split (prescribed)

| PR | Contents | Branch |
|----|----------|--------|
| Phase 1 | P1-A (scoping params), P1-B (validator shared util), P1-C (include_tests), P1-D (truncation comment), P1-E (sequence label one-liner), output-size constants, P1 tests + cost invariant skeleton | `feature/uml-phase1` |
| Phase 2 activity | P2-A (activity diagram), activity CLI flags, activity tests + latency invariant | `feature/uml-activity` |
| Phase 2 state | P2-B (state diagram), state CLI flags, state tests | `feature/uml-state` |

All three branch to `develop` (GitFlow). The sequence-label one-liner (P1-E) folds
into the Phase 1 PR — it is a one-line metadata annotation requiring no separate PR.

## Acceptance criteria

### Phase 1 (shippable independently)

- [x] `CodeGraphUMLTool.get_tool_schema()` declares `file_path`, `class_name`, and `include_tests` in `properties`. (shipped #462)
- [x] `_validate_positive_int` extracted to shared util; used by `uml_tool.py` and `codegraph_sitemap_tool.py`. (shipped #462)
- [x] `validate_arguments` accepts `max_edges=30.0` (coerced to `int`); rejects `max_edges=True`, `max_edges=False`, `max_edges=30.5`. (shipped #462)
- [x] `UMLExporter.class_diagram(file_path="...")` returns only in-file classes plus their direct bases (`metadata["scope"] == "file"`). (shipped #462)
- [x] `UMLExporter.class_diagram(class_name="...")` returns the neighbourhood subgraph (`metadata["scope"] == "class_neighbourhood"`). (shipped #462)
- [x] `UMLExporter.class_diagram()` (no scoping params) excludes test-corpus classes by default; `include_tests=True` restores them. (shipped #462)
- [x] `viz action=uml diagram=class file_path="..."` passes `file_path` through the facade to the inner (viz-08 closed). (shipped #462)
- [x] Whole-project TSA class diagram node count is exactly N (N to be pinned from post-fix measurement; previously 209, test-corpus now excluded). (shipped #462)
- [x] Truncated diagrams include `%% NOTE: diagram truncated` Mermaid comment; non-truncated diagrams do not. (shipped #462)
- [x] `_DEFAULT_MAX_EDGES = 200` replaced with per-diagram constants. (shipped #462)
- [x] CLI flags `--uml-file-path`, `--uml-class-name`, `--uml-include-tests` added and wired via `_build_uml_tool_args`. (shipped #462)
- [x] `sequence_diagram` metadata `source` is `"call_path+synapse_resolved"` when resolved hops present, `"call_path"` otherwise (P1-E one-liner). (shipped #462)
- [x] `test_uml_tool_schema_lists_diagrams` still asserts `== ["class", "package", "component", "sequence"]` (Phase 1 does not add activity/state). (shipped #462)
- [x] `test_class_diagram_execute_with_mock_exporter` FakeExporter kwargs updated to accept `file_path`, `class_name`, `include_tests`. (shipped #462)
- [x] Cost invariant skeleton in `test_output_cost_invariants.py`: scoped class diagram bytes < unscoped bytes (full test wired in integration phase). (shipped #462)
- [x] All Phase-1 tests RED-first then GREEN. (shipped #462)
- [x] CLI<->MCP parity test for Phase-1 flags GREEN. (shipped #462)
- [x] Docs/CODEMAPS updated. (shipped #462)

### Phase 2 — activity

- [x] `diagram` enum includes `"activity"` in schema. (shipped #472)
- [x] `UMLExporter.activity_diagram(function_name, file_path, max_nodes)` implemented: `mermaid_type="flowchart"`, `%% NOTE: activity` comment in Mermaid. (shipped #472)
- [x] Zero CFG nodes -> `verdict="NOT_FOUND"` + `next_step`. (shipped #472)
- [x] Stale file -> parse current content + `metadata["note"]`; missing file -> `NOT_FOUND`. (shipped #472)
- [x] `test_uml_tool_schema_lists_diagrams` re-pinned to 6-element enum (5 in P2-A: ["class","package","component","sequence","activity"]). (shipped #472)
- [x] `test_class_diagram_execute_with_mock_exporter` FakeExporter still accepts new params (no regression from Phase 1 re-pin). (shipped #472)
- [x] CLI flags `--uml-function`, `--uml-max-nodes` added and wired. (shipped #472)
- [x] Latency invariant: activity diagram triggers exactly 1 tree-sitter parse (assertion count == 1). (shipped #472)
- [x] All Phase-2 activity tests RED-first then GREEN. (shipped #472)

### Phase 2 — state

- [x] `diagram` enum includes `"state"` in schema. (shipped #475)
- [x] `UMLExporter.state_diagram(class_name, file_path, max_nodes)` implemented: `mermaid_type="stateDiagram-v2"`, `analysis_kind="static_approximation"`. (shipped #475)
- [x] Zero transitions -> `verdict="NOT_FOUND"` + `next_step`. (shipped #475)
- [x] Stale/missing file behavior same as activity. (shipped #475)
- [x] CLI<->MCP parity test for Phase-2 flags GREEN. (shipped #475)
- [x] All Phase-2 state tests RED-first then GREEN. (shipped #475)
- [x] Docs/CODEMAPS updated. (shipped #475)

## What this RFC does NOT do (deferred)

- Does **not** implement a formal CFG with dominance analysis, exception edges, or async task graphs (`diagram=activity` is a structural approximation only).
- Does **not** add `diagram=deployment`, `diagram=er`, or `diagram=mindmap` types.
- Does **not** change `package_diagram` or `component_diagram` to support fine-grained (file/class) scoping; they remain whole-project import-graph views.
- Does **not** add live-subscription (Hyphae push) for UML outputs; diagrams are snapshot-on-demand.
- Does **not** implement sequence-diagram generation for dynamic-dispatch targets where synapse resolution is unavailable; static call-graph BFS remains the fallback.
- Does **not** touch RFC-0013 implementation; `ignored_params` and this RFC are complementary. The two error-handling rows (file_path/class_name dropped on sequence/package/component) are **deferred pending RFC-0013 implementation** — interim behavior is silent ignore, documented above.

## Open questions

1. **Activity diagram branch labels:** Should true/false branch edges be labelled
   `"Yes"`/`"No"` or `"True"`/`"False"`, or carry the condition text (truncated at 40 chars)?
2. **`--uml-include-tests` flag ergonomics:** `store_true` means the flag re-adds
   test classes. An alternative is `--uml-all` to turn off all exclusion filters.
3. **`_TEST_DIRS` sentinel placement:** Shared between `uml_export.py` and
   `project_health_tool.py` (which has a similar filter). Move to a shared
   constant module, or keep co-located with the consuming code?
4. **Float coercion scope confirmed:** This RFC coerces all four integer params
   (`max_edges`, `max_depth`, `max_paths`, `package_depth`) for consistency. No
   objection expected given the verified root cause, but leaving open for review.
