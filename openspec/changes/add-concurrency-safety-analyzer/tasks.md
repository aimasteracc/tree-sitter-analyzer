# Concurrency Safety Analyzer

## Goal
Detect concurrency bugs that crash production at 3am: shared mutable state, missing synchronization, race condition patterns.

## MVP Scope
- Single-function/class scope analysis (no cross-file data flow)
- 4 detection types: shared_mutable_state, unsafe_concurrent_access, missing_sync_primitive, check_then_act
- 4 languages: Python, JS/TS, Java, Go
- MCP tool with text/json/toon output formats
- 40+ tests

## Technical Approach
- Independent module: analysis/concurrency_safety.py + mcp/tools/concurrency_safety_tool.py
- Pattern: regex + tree-sitter queries for concurrency pattern detection
- Reuse BaseMCPTool, ToonEncoder, existing language plugin infrastructure
- Approach: Pattern-Based Detection (方案A from eng review)

## Detection Details
- Python: class attrs modified in threading/multiprocessing context, threading.Lock without context manager, multiprocessing.Value/Array without proper guard
- JS/TS: shared closure state mutated in async/await, Promise.all without error handling, mutable variables in concurrent callbacks
- Java: non-volatile field in Runnable/Callable, Collections.synchronizedMap misuse, double-checked locking without volatile
- Go: goroutine accessing shared variable without mutex, map concurrent r/w, WaitGroup Add inside goroutine

## Severity Levels
- HIGH: shared_mutable_state (data race, silent corruption)
- HIGH: unsafe_concurrent_access (concurrent mutation without lock)
- MEDIUM: missing_sync_primitive (thread launched without sync setup)
- MEDIUM: check_then_act (TOCTOU pattern on shared state)
