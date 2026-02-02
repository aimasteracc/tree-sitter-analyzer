# Phase 8: Code Graph System - World-Class Design

**Date**: 2026-02-01
**Status**: DESIGN COMPLETE - Ready for TDD Implementation
**Priority**: PROJECT HIGHLIGHT

---

## Executive Summary

**Vision**: Build a self-analyzing code graph system that enables AI to instantly understand project structure, prevent code hallucinations, and provide precise code navigation without reading entire codebases.

**Core Value**: Using tree-sitter-analyzer v2 to analyze itself, creating a meta-cognitive system that demonstrates the tool's power while solving real AI code comprehension problems.

**Technology Stack**: NetworkX (pure Python, no database), TOON format, incremental updates

---

## Problem Statement

### Current Pain Points

1. **AI Code Hallucination**: LLMs generate code referencing non-existent functions/classes
2. **Slow Project Comprehension**: Reading entire codebase wastes tokens and time
3. **Change Impact Unknown**: Modifying a function - who calls it? What breaks?
4. **Manual Navigation**: Human developers manually trace code paths

### User Requirements (from A1-A3)

- **A1**: Use NetworkX (no database dependency)
- **A2**: Make this a project highlight feature
- **A3**: Help LLM quickly locate code changes, prevent hallucinations, understand projects instantly

---

## Architecture Design

### 4-Layer Architecture

```
+-----------------------------------------+
|   Layer 4: MCP Tools (LLM Interface)    |
|   - build_code_graph                    |
|   - query_code_graph                    |
|   - export_graph_for_llm                |
+-----------------------------------------+
              v
+-----------------------------------------+
|   Layer 3: Query Interface              |
|   - find_definition(name)               |
|   - get_callers(function_id)            |
|   - get_call_chain(start, end)          |
|   - find_impact(changed_files)          |
+-----------------------------------------+
              v
+-----------------------------------------+
|   Layer 2: Core Graph Engine            |
|   - CodeGraphBuilder                    |
|   - NodeExtractor (Module/Class/Function)|
|   - EdgeBuilder (IMPORTS/CONTAINS/CALLS)|
|   - IncrementalUpdater (mtime-based)    |
+-----------------------------------------+
              v
+-----------------------------------------+
|   Layer 1: Persistence                  |
|   - NetworkX Graph (.gpickle)           |
|   - TOON Index (.toon)                  |
|   - SQLite Fast Index (.db)             |
+-----------------------------------------+
```

---

## Data Model

### Node Types

```python
# Module Node
{
    "id": "tree_sitter_analyzer_v2.core.analysis_engine",
    "type": "MODULE",
    "file_path": "/path/to/analysis_engine.py",
    "imports": ["pathlib.Path", "typing.Dict"],
    "mtime": 1738368000.0,
    "loc": 450,
    "complexity": 12
}

# Class Node
{
    "id": "UnifiedAnalysisEngine",
    "type": "CLASS",
    "module_id": "tree_sitter_analyzer_v2.core.analysis_engine",
    "start_line": 45,
    "end_line": 320,
    "methods": ["__init__", "analyze_file", "_ensure_initialized"],
    "decorators": ["singleton"],
    "bases": ["BaseEngine"],
    "loc": 275,
    "complexity": 8
}

# Function Node
{
    "id": "analyze_file",
    "type": "FUNCTION",
    "class_id": "UnifiedAnalysisEngine",  # or None for module-level
    "module_id": "tree_sitter_analyzer_v2.core.analysis_engine",
    "start_line": 150,
    "end_line": 200,
    "params": ["file_path", "request"],
    "return_type": "AnalysisResult",
    "calls": ["_ensure_initialized", "parser.parse"],
    "is_async": true,
    "loc": 50,
    "complexity": 4
}

# Import Node
{
    "id": "pathlib.Path",
    "type": "IMPORT",
    "module": "pathlib",
    "name": "Path",
    "alias": null,
    "from_import": true
}
```

### Edge Types

```python
EDGE_TYPES = {
    "IMPORTS": "Module imports another module/class/function",
    "CONTAINS": "Module contains class, class contains method",
    "CALLS": "Function calls another function",
    "INHERITS": "Class inherits from another class",
    "IMPLEMENTS": "Class implements interface (future)",
    "DECORATES": "Decorator applied to function/class (future)"
}
```

---

## Core Functions

### F1: Project Graph Building

**Function**: `build_project_graph(project_root: Path, language: str = "python") -> CodeGraph`

**Algorithm**:
```python
1. Discover all source files (*.py) in project_root
2. For each file in parallel:
   a. Parse with tree-sitter-analyzer v2
   b. Extract nodes: Module → Classes → Functions
   c. Extract imports
   d. Store mtime for incremental updates
3. Build CONTAINS edges (Module → Class → Function)
4. Build IMPORTS edges (resolve import paths)
5. Build CALLS edges (match function_call to definitions)
6. Persist to .gpickle and .toon
7. Return CodeGraph object
```

**Performance**: Parallel processing, ~100 files/second

### F2: Incremental Updates

**Function**: `update_graph(graph: CodeGraph, changed_files: List[Path]) -> CodeGraph`

**Algorithm**:
```python
1. For each changed file:
   a. Check if mtime changed
   b. If unchanged, skip
   c. If changed:
      - Remove old nodes/edges for this file
      - Re-parse and extract new nodes
      - Rebuild edges involving this file
2. Update .gpickle and .toon
3. Return updated graph
```

**Key Optimization**: Only reprocess changed files, not entire project

### F3: LLM-Friendly Queries

#### Q1: Find Definition
```python
def find_definition(graph: CodeGraph, name: str) -> List[Node]:
    """Find all definitions of a function/class/module by name."""
    return [node for node in graph.nodes if node.name == name]
```

#### Q2: Get Callers
```python
def get_callers(graph: CodeGraph, function_id: str) -> List[Node]:
    """Find all functions that call this function."""
    return [source for source, target in graph.in_edges(function_id)]
```

#### Q3: Get Call Chain
```python
def get_call_chain(graph: CodeGraph, start: str, end: str) -> List[List[str]]:
    """Find all call paths from start function to end function."""
    return list(nx.all_simple_paths(graph, start, end))
```

#### Q4: Find Impact
```python
def find_impact(graph: CodeGraph, changed_functions: List[str]) -> Set[str]:
    """Find all functions affected by changes (direct + indirect callers)."""
    impacted = set()
    for func in changed_functions:
        # BFS traversal to find all callers recursively
        impacted.update(nx.ancestors(graph, func))
    return impacted
```

### F4: TOON Export for LLM

**Function**: `export_for_llm(graph: CodeGraph, max_tokens: int = 4000) -> str`

**Output Format** (TOON):
```
PROJECT: tree-sitter-analyzer-v2
MODULES: 45
CLASSES: 87
FUNCTIONS: 324
EDGES: 1250

MODULE: core.analysis_engine | LOC:450 | CC:12
  CLASS: UnifiedAnalysisEngine | L:45-320
    FUNC: analyze_file | L:150-200 | ASYNC | CC:4
      CALLS: _ensure_initialized, parser.parse
      CALLED_BY: mcp.server.analyze_tool, cli.main
    FUNC: _ensure_initialized | L:100-130 | CC:2
      CALLS: PluginManager.get_plugin
      CALLED_BY: analyze_file (3 times)

MODULE: languages.python_parser | LOC:850 | CC:18
  CLASS: PythonParser | L:30-850
    FUNC: parse | L:100-200 | ASYNC | CC:6
      CALLS: tree_sitter.Parser.parse
      CALLED_BY: UnifiedAnalysisEngine.analyze_file

CALL_CHAIN: cli.main → analyze_file → _ensure_initialized → PluginManager.get_plugin
```

**Token Optimization**:
- Omit unchanged modules (incremental diffs)
- Compress repeated patterns
- Use abbreviations (FUNC, CC for complexity)
- Focus on high-impact nodes (public APIs)

---

## Implementation Plan

### Milestone 1: Basic Graph Construction (6-8h)

**Tests to Write (TDD - RED phase)**:
```python
# tests/unit/test_code_graph_builder.py
test_build_module_node()           # Extract module metadata
test_build_class_node()            # Extract class with methods
test_build_function_node()         # Extract function with params/return
test_build_contains_edges()        # Module → Class → Function
test_persist_and_load_graph()     # Pickle round-trip
test_analyze_self()                # Analyze tree-sitter-analyzer v2
```

**Implementation (GREEN phase)**:
1. Add `networkx` to `pyproject.toml`
2. Create `tree_sitter_analyzer_v2/graph/builder.py`
3. Implement `CodeGraphBuilder`:
   - `_extract_module_node(file_path, analysis_result)`
   - `_extract_class_nodes(analysis_result)`
   - `_extract_function_nodes(analysis_result)`
   - `_build_contains_edges(graph, nodes)`
   - `save_graph(graph, output_path)`
   - `load_graph(input_path)`
4. Validate by building graph of v2 project itself

**Acceptance Criteria**:
- 80%+ test coverage
- Can build graph of tree-sitter-analyzer v2 (45 modules, 87 classes, 324 functions)
- Graph persists to .gpickle successfully
- Load time < 100ms for cached graph

### Milestone 2: Call Relationship Analysis (4-6h)

**Tests to Write**:
```python
test_extract_function_calls()      # Parse function_call nodes
test_resolve_function_call_target() # Match call to definition
test_build_calls_edges()           # A calls B edge
test_handle_import_alias()         # from X import Y as Z
test_get_callers_query()           # Find who calls this function
test_get_call_chain_query()        # Trace A → B → C path
```

**Implementation**:
1. Extend `PythonParser` to extract `function_call` nodes
2. Implement `CallResolver`:
   - `resolve_call_target(call_name, context_module, imports)`
   - Handle: `foo()`, `obj.method()`, `Module.function()`
3. Build CALLS edges in `CodeGraphBuilder`
4. Implement query functions in `graph/queries.py`

**Acceptance Criteria**:
- Correctly resolves 95%+ function calls in v2 project
- Handles import aliases correctly
- `get_call_chain` finds paths up to depth 5

### Milestone 3: LLM Optimization (2-4h)

**Tests to Write**:
```python
test_export_toon_format()          # TOON output generation
test_token_count_under_limit()     # Respects max_tokens
test_layered_summary()             # Module-level vs detail
test_incremental_export()          # Only export changed modules
```

**Implementation**:
1. Create `graph/exporters.py`:
   - `TOONGraphExporter`
   - `export_layered_summary(graph, max_tokens)`
   - `export_module_detail(graph, module_id)`
2. Token counting using `tiktoken`
3. Compression strategies:
   - Abbreviations (FUNC, CC, LOC)
   - Omit private functions (starts with `_`)
   - Summarize large classes (only public API)

**Acceptance Criteria**:
- Full v2 graph exports to < 4000 tokens (TOON)
- Layered export: 500 tokens (overview), 3500 tokens (details)
- Token count accuracy within 5%

### Milestone 4: Incremental Updates (2-4h)

**Tests to Write**:
```python
test_detect_changed_files()        # mtime comparison
test_update_single_file()          # Replace nodes for one file
test_update_preserves_other_nodes() # Don't touch unchanged
test_rebuild_affected_edges()      # Update CALLS edges
test_incremental_performance()     # 10x faster than full rebuild
```

**Implementation**:
1. Add `mtime_cache` to graph metadata
2. Implement `IncrementalUpdater`:
   - `detect_changes(graph, project_root)`
   - `update_file(graph, file_path, new_analysis)`
   - `rebuild_edges_for_file(graph, file_path)`
3. Optimize by only rebuilding edges involving changed nodes

**Acceptance Criteria**:
- Incremental update of 1 file takes < 50ms
- 10x faster than full rebuild for small changes
- Graph consistency verified after updates

---

## MCP Tool Integration

### Tool 1: build_code_graph

**Schema**:
```json
{
  "name": "build_code_graph",
  "description": "Build a code graph for a project to enable instant structure understanding",
  "inputSchema": {
    "type": "object",
    "properties": {
      "project_root": {"type": "string"},
      "language": {"type": "string", "default": "python"},
      "output_format": {"type": "string", "enum": ["toon", "json"], "default": "toon"},
      "include_private": {"type": "boolean", "default": false}
    },
    "required": ["project_root"]
  }
}
```

**Output**:
```toon
PROJECT: tree-sitter-analyzer-v2
STATUS: SUCCESS
BUILD_TIME: 2.3s
GRAPH_STATS:
  MODULES: 45
  CLASSES: 87
  FUNCTIONS: 324
  EDGES: 1250

TOP_MODULES (by complexity):
  1. languages.typescript_parser (CC:45, LOC:709)
  2. core.analysis_engine (CC:32, LOC:450)
  3. languages.python_parser (CC:28, LOC:850)

GRAPH_SAVED: .kiro/code_graph.gpickle
INDEX_SAVED: .kiro/code_graph.toon
```

### Tool 2: query_code_graph

**Schema**:
```json
{
  "name": "query_code_graph",
  "description": "Query code graph to find definitions, callers, call chains",
  "inputSchema": {
    "type": "object",
    "properties": {
      "graph_path": {"type": "string"},
      "query_type": {"type": "string", "enum": ["find_definition", "get_callers", "get_call_chain", "find_impact"]},
      "target": {"type": "string"},
      "end_target": {"type": "string"}
    },
    "required": ["graph_path", "query_type", "target"]
  }
}
```

**Example Query**:
```json
{
  "graph_path": ".kiro/code_graph.gpickle",
  "query_type": "get_callers",
  "target": "UnifiedAnalysisEngine.analyze_file"
}
```

**Output**:
```toon
QUERY: get_callers
TARGET: UnifiedAnalysisEngine.analyze_file
CALLERS: 12

DIRECT_CALLERS:
  1. mcp.tools.analyze.AnalyzeTool.execute (L:45)
  2. cli.commands.analyze.analyze_command (L:78)
  3. tests.integration.test_api.test_analyze_java_file (L:23)

CALL_CHAIN_EXAMPLE:
  cli.main → analyze_command → UnifiedAnalysisEngine.analyze_file
```

### Tool 3: export_graph_for_llm

**Schema**:
```json
{
  "name": "export_graph_for_llm",
  "description": "Export code graph in token-optimized TOON format for LLM consumption",
  "inputSchema": {
    "type": "object",
    "properties": {
      "graph_path": {"type": "string"},
      "max_tokens": {"type": "integer", "default": 4000},
      "focus_modules": {"type": "array", "items": {"type": "string"}},
      "detail_level": {"type": "string", "enum": ["summary", "detailed"], "default": "summary"}
    },
    "required": ["graph_path"]
  }
}
```

---

## Performance Targets

| Operation | Target | Strategy |
|-----------|--------|----------|
| Build full graph (v2 project, 45 modules) | < 3s | Parallel parsing |
| Load cached graph | < 100ms | Pickle deserialization |
| Incremental update (1 file) | < 50ms | mtime check, selective rebuild |
| Query: find_definition | < 10ms | NetworkX node lookup |
| Query: get_call_chain (depth 5) | < 100ms | BFS with early stopping |
| TOON export (4000 tokens) | < 200ms | Pre-computed summaries |

---

## Testing Strategy

### Test Coverage Target: 80%+

**Unit Tests** (30 tests):
- `test_code_graph_builder.py` (12 tests) - Node/edge extraction
- `test_call_resolver.py` (8 tests) - Call resolution logic
- `test_incremental_updater.py` (6 tests) - mtime-based updates
- `test_toon_exporter.py` (4 tests) - TOON format generation

**Integration Tests** (10 tests):
- `test_graph_integration.py`:
  - Build graph of real project (v2 itself)
  - Query graph for actual code
  - Verify call chains exist
  - Test incremental updates on file changes

**Performance Tests** (5 tests):
- `test_graph_performance.py`:
  - Build time < 3s for v2 project
  - Load time < 100ms
  - Query time < 10ms
  - Incremental update < 50ms

**Validation Tests**:
- Build graph of tree-sitter-analyzer v2
- Verify key metrics:
  - Modules: 45 ± 5
  - Classes: 87 ± 10
  - Functions: 324 ± 30
  - CALLS edges: 800+ (dense call graph)

---

## Success Criteria

**Functional**:
- [ ] Build graph of tree-sitter-analyzer v2 successfully
- [ ] Resolve 95%+ function calls correctly
- [ ] Export to TOON format under 4000 tokens
- [ ] Incremental updates work correctly

**Quality**:
- [ ] 80%+ test coverage (per TDD requirement)
- [ ] All tests passing
- [ ] Performance targets met

**UX**:
- [ ] MCP tools integrated and documented
- [ ] Clear error messages
- [ ] TOON output readable by LLM

**Highlight**:
- [ ] Self-analyzing capability (tree-sitter-analyzer analyzes itself)
- [ ] Demonstrates tool's power
- [ ] Solves real AI comprehension problem

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Call resolution accuracy < 95% | Test on real codebase (v2), handle edge cases iteratively |
| Graph too large for memory | Use SQLite for large projects (future), focus on Python-only initially |
| Token budget exceeded | Layered export, on-demand detail fetching |
| Incremental update bugs | Extensive testing, validate graph consistency after updates |
| Complex call chains (depth > 10) | Limit BFS depth, return "Too deep" after depth 10 |

---

## Future Enhancements (Post-MVP)

1. **Multi-language Support**: Extend to TypeScript, Java, Go
2. **Type Flow Analysis**: Track data types through call chain
3. **Dependency Graph**: Package-level dependencies
4. **Change Impact UI**: Visualize affected code on file edit
5. **SQLite Index**: Fast queries without loading full graph
6. **Git Integration**: Track code changes across commits
7. **Complexity Trends**: Historical complexity metrics

---

## References

- NetworkX Documentation: https://networkx.org/
- Tree-sitter Python Bindings: https://github.com/tree-sitter/py-tree-sitter
- TOON Format Spec: `formatters/toon_formatter.py`
- MCP Protocol: https://modelcontextprotocol.io/

---

## Timeline Estimate

- **Milestone 1**: 6-8 hours (Basic Graph Construction)
- **Milestone 2**: 4-6 hours (Call Relationship Analysis)
- **Milestone 3**: 2-4 hours (LLM Optimization)
- **Milestone 4**: 2-4 hours (Incremental Updates)

**Total**: 14-22 hours (world-class TDD development)

---

**Next Step**: Begin TDD implementation of Milestone 1 - Basic Graph Construction

**Status**: READY FOR IMPLEMENTATION

---

**Design Complete - Ready for World-Class TDD Implementation!**
