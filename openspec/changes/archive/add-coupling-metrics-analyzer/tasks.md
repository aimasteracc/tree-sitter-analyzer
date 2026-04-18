# Coupling Metrics Analyzer

## Goal
Quantify module coupling intensity: fan-out (dependencies), fan-in (dependents), instability, and abstractness.

## MVP Scope
- Per-file metrics: fan_out, fan_in, instability (fan_out / (fan_in + fan_out))
- Project-level summary: most coupled files, most critical files
- Risk classification: STABLE (instability < 0.3), UNSTABLE (> 0.7), FLEXIBLE (0.3-0.7)
- MCP tool: coupling_metrics registered to analysis toolset

## Technical Approach
- Reuse DependencyGraph output as input (zero new AST parsing)
- Independent analysis module + MCP tool (matches 54 existing tools)
- ~400 lines engine + ~200 lines MCP tool + ~400 lines tests
- 4 languages via existing dependency_graph builder

## Sprint Plan
- [x] Sprint 1: Core engine + tests + MCP tool (all in one sprint)

## Dependencies
- dependency_graph.py (DependencyGraph dataclass, DependencyGraphBuilder)
- BaseMCPTool, handle_mcp_errors, ToonEncoder (existing)
