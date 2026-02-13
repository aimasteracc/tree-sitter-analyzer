# Design: Code Intelligence Graph

**Change ID**: `add-code-intelligence-graph`

---

## Architecture Overview

```
MCP Tools Layer
├── trace_symbol_tool.py          → SymbolIndex + CallGraphBuilder
├── assess_change_impact_tool.py  → ImpactAnalyzer + CallGraph + DependencyGraph
└── check_architecture_health_tool.py → ArchitectureMetrics + DependencyGraph

Intelligence Engine (NEW)
├── models.py              → Data models for all intelligence features
├── symbol_index.py        → Project-wide symbol definition/reference index
├── call_graph.py          → Call graph builder using tree-sitter queries
├── import_resolver.py     → Import path → actual file resolution
├── dependency_graph.py    → File/module dependency graph builder
├── impact_analyzer.py     → Change impact blast radius calculator
├── architecture_metrics.py → Coupling, instability, cycle detection
├── cycle_detector.py      → Tarjan's SCC algorithm
└── formatters.py          → Output formatting (summary, tree, json)

Existing Core (NO CHANGES)
├── analysis_engine.py     → Used by intelligence for per-file analysis
├── query.py               → Used for executing call queries
└── plugins/               → Used for element extraction
```

---

## Key Design Decisions

### 1. Separation from Core
The intelligence module calls `analysis_engine.analyze()` and `QueryExecutor` but does not modify them. This ensures zero regression risk for existing functionality.

### 2. AST-Level Precision
Call graph is built using AST name matching, not semantic analysis. This means:
- `self.validate(data)` matches any method named `validate` in scope
- No type inference: `obj.method()` matches by method name only
- Trade-off: High recall, moderate precision — acceptable for AI assistant use cases

### 3. Lazy Graph Construction
Graphs are built on-demand per MCP tool call, not maintained as a persistent index. This avoids complexity of incremental updates while leveraging existing `CacheService` for per-file analysis results.

### 4. Python-First
All resolvers and queries are implemented for Python first, with extension points for other languages.

---

## Data Models

### CallSite
```python
@dataclass
class CallSite:
    caller_file: str
    caller_function: str | None
    callee_name: str
    callee_object: str | None   # e.g., "self", "cls", module name
    line: int
    raw_text: str
```

### SymbolDefinition
```python
@dataclass
class SymbolDefinition:
    name: str
    file_path: str
    line: int
    end_line: int
    symbol_type: str  # "function", "class", "variable", "method"
    parameters: list[str]
    return_type: str | None
    parent_class: str | None
    docstring: str | None
    modifiers: list[str]
```

### SymbolReference
```python
@dataclass
class SymbolReference:
    symbol_name: str
    file_path: str
    line: int
    ref_type: str  # "call", "import", "inheritance", "type_hint"
    context_function: str | None
```

### DependencyEdge
```python
@dataclass
class DependencyEdge:
    source_file: str
    target_file: str
    target_module: str
    imported_names: list[str]
    is_external: bool
    line: int
```

### ImpactResult
```python
@dataclass
class ImpactResult:
    target: str
    change_type: str
    direct_impacts: list[ImpactItem]
    transitive_impacts: list[ImpactItem]
    affected_tests: list[str]
    risk_level: str  # "low", "medium", "high", "critical"
    total_affected_files: int
```

### ArchitectureReport
```python
@dataclass
class ArchitectureReport:
    path: str
    score: int  # 0-100
    module_metrics: dict[str, ModuleMetrics]
    cycles: list[DependencyCycle]
    layer_violations: list[LayerViolation]
    god_classes: list[GodClassInfo]
    dead_symbols: list[str]
    coupling_matrix: dict[str, dict[str, int]]
```

---

## MCP Tool Interfaces

### trace_symbol
- Input: `symbol` (required), `file_path`, `trace_type`, `depth`, `output_format`
- Output: Definition, usages, call chains, inheritance chain
- Formats: summary, tree, json

### assess_change_impact
- Input: `target` (required), `change_type`, `depth`, `include_tests`
- Output: Direct impacts, transitive impacts, affected tests, risk level
- Formats: summary, json

### check_architecture_health
- Input: `path` (required), `checks[]`, `layer_rules{}`
- Output: Score, metrics, cycles, violations, god classes, dead symbols
- Formats: summary, json
