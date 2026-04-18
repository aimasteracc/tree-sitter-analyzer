# Variable Mutability Analyzer

## Goal
Detect variable mutability issues: shadowing, unused assignments, constant reassignment, and iteration mutation.

## MVP Scope
- 4 detection modes: shadow_variable, unused_assignment, reassigned_constant, mutation_in_iteration
- 5 languages: Python, JS/TS, Java, Go
- Independent analysis module + MCP tool
- 40+ tests

## Technical Approach
- Independent module (consistent with 39 existing analyzers)
- Scope stack tracking for shadow detection
- AST-based unused assignment analysis (no data flow)
- Pattern matching for constant reassignment and iteration mutation
- Standard MCP tool with text/json/toon output
