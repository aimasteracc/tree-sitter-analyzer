# Error Propagation Analyzer

## Goal
Trace error/exception propagation through call chains, detect silent error swallowing, unhandled exception types, and missing propagation paths.

## MVP Scope
- Detect: raise/throw statements, try/except blocks, re-raise patterns
- Build lightweight error flow graph per function
- Report: unhandled raises, swallowed errors without propagation, missing finally cleanup
- Languages: Python, JavaScript/TypeScript, Java
- Tests: 40+ tests (analysis + MCP tool)

## Technical Approach
- Standalone analyzer inheriting BaseAnalyzer
- Per-function: identify raises/throws, catches, re-raises
- Cross-function: build call graph to trace error flow
- Output: ErrorPropagationResult with paths, gaps, risk scores
- Register as MCP tool in tool_registration.py
