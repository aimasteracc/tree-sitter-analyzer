# Null Safety Analyzer

## Goal
Detect potential None/null dereference risks in code. Find places where a nullable value is used without a safety check.

## MVP Scope
- Single-function scope analysis (no cross-function data flow)
- 4 detection types: unchecked_access, missing_null_check, chained_access, dict_unsafe_access
- 4 languages: Python, JS/TS, Java, Go
- MCP tool with text/json/toon output formats
- 40+ tests

## Technical Approach
- Independent module: analysis/null_safety.py + mcp/tools/null_safety_tool.py
- Pattern: regex + tree-sitter queries for null source detection + usage analysis
- Reuse BaseMCPTool, ToonEncoder, existing language plugin infrastructure
- None sources: function returns, Optional params, dict.get(), nullable assignments
- Safe patterns: if x is not None, x?.foo, Optional.ifPresent, if err != nil

## Detection Details
- Python: None returns, Optional params, dict[key] without key check, bare attribute access on potential None
- JS/TS: null/undefined returns, optional chaining (?.) presence, bare property access on potential null
- Java: null returns, Optional<T>, NPE risk from method chains, missing null guards
- Go: nil pointer dereference, map[key] without comma-ok check, unchecked error returns

## Severity Levels
- HIGH: unchecked_access (None dereference will crash at runtime)
- HIGH: missing_null_check (Optional param used without validation)
- MEDIUM: chained_access (chain breaks if intermediate is None)
- MEDIUM: dict_unsafe_access (KeyError/undefined at runtime)
