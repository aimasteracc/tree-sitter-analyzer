# Logging Pattern Analyzer

## Goal
Detect logging anti-patterns that make production debugging harder.

## MVP Scope
- Detect silent error swallowing (catch blocks with no logging)
- Detect inconsistent log levels (error in info-level context)
- Detect sensitive data in log calls (passwords, tokens, keys)
- Detect missing logging in critical paths (error handlers, finally blocks)
- Support 4 languages: Python, JS/TS, Java, Go

## Technical Approach
- Independent analysis module: analysis/logging_patterns.py
- MCP tool: mcp/tools/logging_patterns_tool.py
- Uses TreeSitterQueryCompat for AST queries
- Architecture consistent with env_tracker/import_sanitizer pattern

## Sprints
- Sprint 1: Core Detection Engine (Python focus) - ~30 tests ✅
- Sprint 2: Multi-Language Support (JS/TS, Java, Go) - ~20 tests ✅
- Sprint 3: MCP Tool Integration - ~15 tests ✅

## Status: COMPLETE

**Totals**:
- 39 analysis tests passing (4 languages)
- 10 MCP tool tests passing
- Total: 49 tests passing
- MCP tool registered in analysis toolset
