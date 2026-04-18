# Architectural Boundary Analyzer

## Goal
Detects layered architecture violations — when code imports across boundaries it shouldn't (e.g., UI layer directly importing from Repository layer, skipping Service layer).

## MVP Scope
- Define standard layer patterns (controller → service → repository/dao)
- Map directory/package names to layers via convention patterns
- Use DependencyGraphBuilder to extract imports
- Detect cross-layer violations (skip-level imports)
- Detect circular dependencies between layers
- Compute architectural compliance score
- Support Python, Java, TypeScript, C#
- MCP tool wrapper
- 30+ tests

## Technical Approach
- Reuse `DependencyGraphBuilder` from `dependency_graph.py` (same pattern as `coupling_metrics.py`)
- Layer detection: regex-based directory/package name matching
- Violation detection: compare layer numbers of source and target files
- Result dataclass with violations, compliance score, layer summary
- MCP tool in `architectural_boundary_tool.py`

## Dependencies
- `dependency_graph.py` (DependencyGraphBuilder)
- `utils.py` (setup_logger)
