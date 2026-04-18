# Async/Await Pattern Analyzer

## Goal
Detect async/await anti-patterns that cause silent bugs invisible to normal code review.

## MVP Scope
- Python: missing await, async without await, fire-and-forget async calls
- JavaScript/TypeScript: unhandled promises, missing await, promise chain mixing
- Java: @Async misuse, CompletableFuture anti-patterns
- Go: goroutine leaks, unbuffered channel issues
- Severity levels: error, warning, info
- TOON + JSON output

## Technical Approach
- Reuse existing queries from tree_sitter_analyzer/queries/ (python.py, javascript.py, go.py, java.py)
- Follow env_tracker.py pattern: TreeSitterQueryCompat + per-language dispatch
- Independent module: analysis/async_patterns.py + mcp/tools/async_patterns_tool.py
- 4 language support

## Sprints
- Sprint 1: Core Detection Engine (Python focus) - ~30 tests
- Sprint 2: Multi-Language Support (JS/TS, Java, Go) - ~25 tests
- Sprint 3: MCP Tool Integration - ~15 tests
