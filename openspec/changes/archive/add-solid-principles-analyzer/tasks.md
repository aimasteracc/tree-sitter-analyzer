# SOLID Principles Analyzer

## Goal
Detect violations of the 5 SOLID design principles in Python, JS/TS, Java, and Go code.

## MVP Scope
- SRP (Single Responsibility): classes with too many methods/lines
- OCP (Open/Closed): isinstance/type-checking dispatch patterns
- LSP (Liskov Substitution): subclass method signature mismatches
- ISP (Interface Segregation): fat interfaces with too many methods
- DIP (Dependency Inversion): direct imports of concrete classes

## Technical Approach
- Independent module following naming_convention.py pattern
- tree-sitter queries for class/method/interface detection
- Per-language violation thresholds
- Violation types: srp_violation, ocp_violation, lsp_violation, isp_violation, dip_violation

## Files
1. tree_sitter_analyzer/analysis/solid_principles.py
2. tree_sitter_analyzer/mcp/tools/solid_principles_tool.py
3. tests/unit/analysis/test_solid_principles.py
4. tests/integration/mcp/test_solid_principles_tool.py

## Test Standard
- 40+ unit tests covering all 5 principles across 4 languages
- 10+ MCP integration tests
- All CI checks pass
