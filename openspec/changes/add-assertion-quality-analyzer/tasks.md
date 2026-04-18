# Assertion Quality Analyzer

## Goal
Analyze test assertion quality beyond coverage and smell detection. Fill the gap between "has tests" and "has good tests."

## MVP Scope
- 4 detection modes: assertion_strength, assertion_specificity, assertion_distribution, missing_edge_assertion
- 4 languages: Python, JS/TS, Java, Go
- MCP tool registration (analysis toolset)
- 40+ tests

## Technical Approach
- Independent module: analysis/assertion_quality.py + mcp/tools/assertion_quality_tool.py
- Tree-sitter AST parsing for assertion patterns
- No overlap with test_smells (which detects presence/pattern, not quality)

## Sprint Plan
- Sprint 1: Core engine (Python support, 4 detection modes) — ~400 lines
- Sprint 2: Multi-language (JS/TS, Java, Go) — ~300 lines
- Sprint 3: MCP Tool + tests — ~200 lines
