# Add Dependency Graph + Health Score

## Overview

Add project-level visualization capabilities: a dependency graph that maps
import/usage relationships between files, and a health score (A-F) that
assesses each file's maintainability based on size, complexity, and coupling.

## Design

### Dependency Graph

Build a directed graph where:
- Nodes = source files
- Edges = import/usage relationships (A imports B → edge A→B)

Algorithm:
1. Scan all source files via `list_files`
2. For each file, extract imports via `query_code("imports")`
3. Resolve import paths to files in the project
4. Build adjacency list
5. Compute graph metrics: in-degree, out-degree, PageRank

Output formats: JSON adjacency list, DOT (Graphviz), Mermaid

### Health Score

Grade each file A-F based on:
- **Size** (>500 lines = penalty, >1000 = heavy penalty)
- **Complexity** (nesting depth, cyclomatic via method count)
- **Coupling** (fan-out = import count, fan-in = how many files import this)
- **Annotation density** (high annotations = framework coupling)

Scoring:
```
score = 100
score -= min(lines / 10, 30)          # Size penalty (max 30)
score -= min(methods * 2, 20)         # Complexity penalty (max 20)
score -= min(fan_out * 3, 20)         # Outgoing coupling (max 20)
score -= min(fan_in * 2, 15)          # Incoming coupling (max 15)
score -= min(annotations, 15)          # Framework coupling (max 15)

A: 90-100 | B: 75-89 | C: 60-74 | D: 40-59 | F: 0-39
```

### Implementation

```
tree_sitter_analyzer/analysis/dependency_graph.py  — graph builder
tree_sitter_analyzer/analysis/health_score.py       — scoring engine
tree_sitter_analyzer/mcp/tools/dependency_graph_tool.py  — MCP tool
tree_sitter_analyzer/mcp/tools/health_score_tool.py       — MCP tool
```

## Success Criteria

1. `analyze_dependencies` returns JSON adjacency list for any project
2. `compute_health_score` returns A-F grade per file
3. Graph output in DOT and Mermaid formats
4. PageRank identifies critical files
5. TDD: 10+ tests
6. All existing tests pass
