# Nesting Depth Analyzer

## Goal
Detect deeply nested code structures (4+ levels of if/for/while/try/switch) and identify flattening opportunities. A simpler, more actionable metric than cyclomatic or cognitive complexity.

## MVP Scope
- Function-level max nesting depth measurement
- Depth hotspot tracking (which lines contribute to deep nesting)
- Rating: good (1-3), warning (4), critical (5+)
- 4 languages: Python, JS/TS, Java, Go
- MCP tool integration with TOON + JSON output

## Technical Approach
- Independent module: analysis/nesting_depth.py + mcp/tools/nesting_depth_tool.py
- AST visitor pattern with depth counter for control flow nodes
- Follow cognitive_complexity architecture pattern
- TreeSitterQueryCompat not needed (direct node type checking)

## Sprint 1: Core Analysis Engine (Python)
- [x] Create NestingDepthAnalyzer class in analysis/nesting_depth.py
- [x] NestingDepthResult dataclass (function_name, max_depth, avg_depth, hotspots, rating)
- [x] AST visitor with depth counter for control flow nodes
- [x] Rating system: good/warning/critical
- [x] Python support (if/for/while/try/with)
- [x] Unit tests (15+ tests)

## Sprint 2: Multi-Language Support
- [x] JavaScript/TypeScript support (if/for/while/try/switch)
- [x] Java support (if/for/while/try/switch/synchronized)
- [x] Go support (if/for/switch/select/func literal)
- [x] Integration tests for each language
- [x] 15+ tests

## Sprint 3: MCP Tool Integration
- [x] Create mcp/tools/nesting_depth_tool.py
- [x] TOON + JSON output formats
- [x] Register to analysis toolset
- [x] Tool definition with examples
- [x] 10+ tests
