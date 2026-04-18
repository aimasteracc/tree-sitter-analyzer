# Exception Handling Quality Analyzer

## Goal
Detect exception handling anti-patterns in production code — where errors get silently swallowed.

## MVP Scope
- 4 detection modes: broad_catch, swallowed_exception, missing_context, generic_error_message
- 4 languages: Python, JS/TS, Java, Go
- MCP tool registration (analysis toolset)
- 40+ tests

## Technical Approach
- Independent module: analysis/exception_quality.py + mcp/tools/exception_quality_tool.py
- Tree-sitter AST parsing for try/catch/except/defer structures
- No overlap with logging_patterns (log-level) or error_handling (recovery patterns)

## Sprint Plan
- Sprint 1: Core engine (Python support, 4 detection modes) — ~500 lines
- Sprint 2: Multi-language (JS/TS, Java, Go) — ~400 lines
- Sprint 3: MCP Tool + tests — ~200 lines
