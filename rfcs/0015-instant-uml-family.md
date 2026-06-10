# RFC-0015: 瞬間 UML 图族 — Instant UML Family

- **Status**: draft
- **Author(s)**: @aimasteracc
- **Created**: 2026-06-11
- **Last updated**: 2026-06-11
- **Tracking issue**: TBD
- **Affected source paths** (pin them — reviewers watch for drift here):
  - `tree_sitter_analyzer/uml_export.py`
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

## Summary

The existing `viz action=uml` family has three live bugs (file/class-scoping params
silently dropped, a broken `max_edges` validator that rejects valid floats, and
whole-project diagrams polluted by test-corpus classes) and misses two diagram
types valuable to AI agents (control-flow `activity` and state-machine `state`).
This RFC fixes the three Phase-1 defects in the existing diagrams, then adds the
two new diagram types in Phase 2, and enhances sequence-diagram call resolution to
use synapse-resolved edges where available.

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

Two failure modes:

1. **Float coercion (confirmed live):** Some MCP clients and JSON deserializers
   emit `30.0` (a Python `float`) instead of `30` (a Python `int`). Because
   `isinstance(30.0, int)` is `False` in Python, `not isinstance(30.0, int)` is
   `True`, and the validator raises `"max_edges must be a positive integer"` for a
   perfectly valid caller intent of 30. This is the bug described as "max_edges=30
   rejected by a broken validator for a positive integer."

2. **Bool pass-through (silent data loss):** Python's `bool` is a subclass of
   `int`: `isinstance(True, int)` is `True` and `True < 1` is `False` (since
   `True == 1`). A caller passing `max_edges=True` silently gets `max_edges=1`,
   losing all but one edge with no error. The fix must exclude `bool` explicitly:
   require `not isinstance(value, bool)` before accepting as int.

The correct fix accepts any non-bool `int` ≥ 1 and any whole-number `float` ≥ 1
(coercing it to `int` in place), and rejects booleans, fractions, and non-numeric
values with a precise error message.

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

### Sequence-diagram call-resolution gap

`UMLExporter.sequence_diagram` calls `CallPathFinder.find_path`
(`uml_export.py:321–352`), which does BFS over `ast_call_edges` SQL rows — a pure
static call graph. Dynamic dispatch (virtual methods, callbacks, MRO hops) produces
empty paths. The synapse resolver already writes resolved-callee information into
`callee_resolved_file` in the metadata JSON blob of the same SQLite rows
(`call_path.py:41`). Where that field is populated, the sequence diagram should
prefer the resolved callee over the raw static callee, following the dispatch hop.

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

#### P1-B: fix the `max_edges` validator (`uml_tool.py:102–105`)

```python
# BEFORE (broken):
for key in ("max_edges", "max_depth", "max_paths", "package_depth"):
    value = arguments.get(key)
    if value is not None and (not isinstance(value, int) or value < 1):
        raise ValueError(f"{key} must be a positive integer")

# AFTER (fixed):
for key in ("max_edges", "max_depth", "max_paths", "package_depth"):
    value = arguments.get(key)
    if value is None:
        continue
    # bool is a subclass of int in Python; treat as invalid regardless of value.
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a positive integer, got bool {value!r}")
    # Accept whole-number floats (e.g. 30.0 from JSON deserializers); coerce.
    if isinstance(value, float):
        if value != int(value) or value < 1:
            raise ValueError(
                f"{key} must be a positive integer, got float {value!r}"
            )
        arguments[key] = int(value)  # in-place coerce for downstream
        continue
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{key} must be a positive integer, got {value!r}")
```

In-place coercion of `arguments[key]` is safe: `validate_arguments` is always called
before `execute` consumes the dict, and the facade passes a projected copy (not the
original caller dict), so the mutation is contained.

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

This comment is visible to anyone reading the diagram source or using a Mermaid
renderer that displays comment lines.

### Phase 2 — New diagram types

#### P2-A: `diagram=activity` — single-function control-flow graph

A structural CFG for a single function, rendered as `flowchart TD`.

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
   - `if` / `elif` branch (condition text, ≤ 40 chars)
   - `for` / `while` loop (loop-header text, ≤ 40 chars)
   - `return` / `raise` / `yield` statement (kind + first 20 chars of expression)
   - implicit exit (if the function can fall off the end)
3. Add directed edges: sequential flow, true/false branch edges for conditionals,
   back-edge for loop headers. `break` / `continue` are terminal nodes (not wired
   to loop exits — that requires dominance analysis, which is out of scope).
4. Render as `flowchart TD` using `render_flowchart_mermaid`.

**Prepend to Mermaid output:**

```
%% NOTE: activity diagram is a structural AST approximation.
%% Exception edges, async suspension, and dynamic dispatch are not modelled.
```

New method: `UMLExporter.activity_diagram(function_name, file_path=None, max_nodes=50) -> UMLDiagram`.
Returns `diagram_type="activity"`, `mermaid_type="flowchart"`.

**CLI:** extend `--uml` enum to include `activity`. New flags: `--uml-function`
(function name, string) and `--uml-max-nodes` (integer, default 50). Note:
`--uml-file-path` (added in P1-A) also serves `activity` for disambiguation.

#### P2-B: `diagram=state` — FSM approximation from enums/match

State-machine approximation rendered as `stateDiagram-v2`.

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

**Prepend to Mermaid output:**

```
%% NOTE: state diagram is a static approximation.
%% Guard conditions, timers, and exception-driven transitions are not captured.
```

`metadata["analysis_kind"] = "static_approximation"`.

New method: `UMLExporter.state_diagram(class_name=None, file_path=None, max_nodes=30) -> UMLDiagram`.
Returns `diagram_type="state"`, `mermaid_type="stateDiagram-v2"`.

**CLI:** extend `--uml` enum to include `state`. Uses `--uml-class-name` (added
in P1-A) for class filter.

#### P2-C: sequence diagram — synapse-resolved dispatch hops

`CallPathFinder._bfs_sql_forward` reads `callee_resolved_file` from the metadata JSON
blob (`call_path.py:41`). The sequence path currently ignores this field and always
uses the raw callee name.

Enhancement: when a BFS hop has `callee_resolved_file` populated (synapse resolver
ran), use the resolved callee symbol (resolved file + callee name from metadata)
instead of the raw static callee. This follows a virtual-method dispatch hop one
level deeper than the static graph.

Fallback: if `callee_resolved_file` is absent, use the static callee name as today.
`metadata["source"]` becomes `"call_path+synapse_resolved"` when at least one
resolved hop was used; otherwise remains `"call_path"`.

No new params or schema changes. This is a transparent improvement to
`diagram=sequence`.

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
| `file_path` passed to `diagram=sequence` | `ignored_params=["file_path"]` via RFC-0013; sequence uses `source`/`target` |
| `class_name` passed to `diagram=package` or `diagram=component` | `ignored_params=["class_name"]` via RFC-0013 |
| Unknown `diagram` value | `ValueError("Unsupported UML diagram: ...")` (unchanged) |
| AST parse failure in P2-A CFG walk | Return `UMLDiagram(nodes=[], edges=[], truncated=False)` with `metadata["error"]` set; do NOT raise |
| Function not found for `diagram=activity` | `verdict="NOT_FOUND"` with `agent_summary.next_step` hint |

## Three-Surface impact (CLI ↔ MCP parity)

TSA holds a hard CLI↔MCP parity rule. All new/changed params:

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
  at the old default. Those tests must be re-pinned to measured values. This is
  correct under the exact-assertion rule.
- **`include_tests=False` default changes whole-project node count:** Any test that
  pins the exact node count at 209 will go RED. The new pin is the measured value
  after test-corpus exclusion. RED is correct — the old count was inflated noise.
- **In-place mutation of `arguments`:** The float→int coercion mutates the caller's
  projected dict. Safe because `validate_arguments` runs before `execute` and the
  facade passes a projected copy. Documented in inline comments.

## Alternatives

- **A: Keep `class` whole-project only; advise agents to use `nav action=context`
  for file-scoped structure.** ❌ Rejected — Mermaid diagrams are consumed by
  non-agentic UIs (renderers, markdown previews). The viz-08 silent-drop is a
  correctness bug regardless.
- **B: New facade action `viz action=cfg` for control-flow graphs.** ❌ Rejected —
  the diagram family is unified under `viz action=uml`. A separate action fragments
  the discovery surface with no benefit.
- **C: Separate `viz action=uml` (existing) and `viz action=uml2` (new types).** ❌
  Rejected — same fragmentation concern as B.
- **D: Increase `max_edges` default instead of adding scoping params.** ❌ Rejected —
  74 000-char flood is already above useful MCP token budgets. More edges = more
  noise. Scoping + lower caps are the correct fix.
- **E: Hard-reject float `max_edges`; do not coerce.** Rejected — the bug is a
  deserializer artifact (LLM clients emit `30.0`), not a user error. Coercion is
  the lenient-correct behaviour.
- **F: Fix viz-08 only via RFC-0013 `ignored_params` (make drop visible, not
  prevent it).** ❌ Rejected for the scoping case — RFC-0013 makes drops visible
  but the right fix is to declare the params so drops do not occur.

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
    assert len(test_nodes) == 3                                   # exact pin; re-measure if fixture changes
```

#### P1-B validator

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

### Phase 2

```python
# tests/unit/test_uml_tool.py

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
    # fixture: function with 1 if-branch → entry + condition + true-body + false-body + exit = 5 nodes
    exporter = UMLExporter("/repo", mock_simple_function_cache)
    diagram = exporter.activity_diagram("simple_func")
    assert len(diagram.nodes) == 5   # exact pin — re-measure if fixture changes

def test_state_diagram_mermaid_type_and_comment(mock_enum_cache) -> None:
    exporter = UMLExporter("/repo", mock_enum_cache)
    diagram = exporter.state_diagram(class_name="TrafficLight")
    assert diagram.mermaid_type == "stateDiagram-v2"
    assert "%% NOTE: state diagram is a static approximation" in diagram.mermaid
    assert diagram.metadata["analysis_kind"] == "static_approximation"

def test_sequence_source_reflects_synapse(mock_resolved_call_path) -> None:
    exporter = UMLExporter("/repo")
    diagram = exporter.sequence_diagram("caller_fn", "target_fn")
    assert diagram.metadata["source"] == "call_path+synapse_resolved"

def test_sequence_source_falls_back_without_synapse(mock_unresolved_call_path) -> None:
    exporter = UMLExporter("/repo")
    diagram = exporter.sequence_diagram("caller_fn", "target_fn")
    assert diagram.metadata["source"] == "call_path"

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

## Acceptance criteria

### Phase 1 (shippable independently)

- [ ] `CodeGraphUMLTool.get_tool_schema()` declares `file_path`, `class_name`, and `include_tests` in `properties`.
- [ ] `validate_arguments` accepts `max_edges=30.0` (coerced to `int`); rejects `max_edges=True`, `max_edges=False`, `max_edges=30.5`.
- [ ] `UMLExporter.class_diagram(file_path="...")` returns only in-file classes plus their direct bases (`metadata["scope"] == "file"`).
- [ ] `UMLExporter.class_diagram(class_name="...")` returns the neighbourhood subgraph (`metadata["scope"] == "class_neighbourhood"`).
- [ ] `UMLExporter.class_diagram()` (no scoping params) excludes test-corpus classes by default; `include_tests=True` restores them.
- [ ] `viz action=uml diagram=class file_path="..."` passes `file_path` through the facade to the inner (viz-08 closed).
- [ ] Whole-project TSA class diagram node count is exactly N (N to be pinned from post-fix measurement; previously 209, test-corpus now excluded).
- [ ] Truncated diagrams include `%% NOTE: diagram truncated` Mermaid comment; non-truncated diagrams do not.
- [ ] `_DEFAULT_MAX_EDGES = 200` replaced with per-diagram constants.
- [ ] CLI flags `--uml-file-path`, `--uml-class-name`, `--uml-include-tests` added and wired via `_build_uml_tool_args`.
- [ ] All Phase-1 tests above GREEN.
- [ ] CLI↔MCP parity test for Phase-1 flags GREEN.
- [ ] Docs/CODEMAPS updated.

### Phase 2

- [ ] `diagram` enum includes `"activity"` and `"state"` in schema.
- [ ] `UMLExporter.activity_diagram(function_name, file_path, max_nodes)` implemented: `mermaid_type="flowchart"`, `%% NOTE: activity` comment in Mermaid.
- [ ] `UMLExporter.state_diagram(class_name, file_path, max_nodes)` implemented: `mermaid_type="stateDiagram-v2"`, `analysis_kind="static_approximation"`.
- [ ] `sequence_diagram` metadata `source` reflects `"call_path+synapse_resolved"` when resolved edges were used.
- [ ] CLI flags `--uml-function`, `--uml-max-nodes` added and wired.
- [ ] All Phase-2 tests above GREEN.
- [ ] CLI↔MCP parity test for Phase-2 flags GREEN.
- [ ] Docs/CODEMAPS updated.

## What this RFC does NOT do (deferred)

- Does **not** implement a formal CFG with dominance analysis, exception edges, or async task graphs (`diagram=activity` is a structural approximation only).
- Does **not** add `diagram=deployment`, `diagram=er`, or `diagram=mindmap` types (no relational schema index; no deployment topology index).
- Does **not** change `package_diagram` or `component_diagram` to support fine-grained (file/class) scoping; they remain whole-project import-graph views.
- Does **not** add live-subscription (Hyphae push) for UML outputs; diagrams are snapshot-on-demand.
- Does **not** implement sequence-diagram generation for dynamic-dispatch targets where synapse resolution is unavailable; static call-graph BFS remains the fallback.
- Does **not** touch RFC-0013 implementation; `ignored_params` and this RFC are complementary (RFC-0013 surfaces remaining undeclared drops; RFC-0015 removes the most-requested ones by declaring the params).

## Open questions

1. **Activity diagram branch labels:** Should true/false branch edges be labelled
   `"Yes"`/`"No"` or `"True"`/`"False"`, or carry the condition text (potentially
   long, truncated at 40 chars)?
2. **Float coercion scope:** Should coercion also apply to `max_depth`,
   `max_paths`, and `package_depth`, or only `max_edges`? This RFC coerces all
   four for consistency.
3. **`--uml-include-tests` flag ergonomics:** `store_true` means the flag re-adds
   test classes. An alternative is `--uml-all` to turn off all exclusion filters.
4. **Phase-2 shipping granularity:** Should `activity` and `state` land in a
   single PR or in separate focused PRs?
5. **`_TEST_DIRS` sentinel placement:** Shared between `uml_export.py` and
   `project_health_tool.py` (which has a similar filter). Move to a shared
   constant module, or keep co-located with the consuming code?
