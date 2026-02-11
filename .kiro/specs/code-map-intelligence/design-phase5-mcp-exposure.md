# Design: Phase 5 — Expose Code Intelligence via MCP Tools

## Problem
`trace_call_flow`, `impact_analysis`, `gather_context` are implemented and tested
(61 tests) but have ZERO exposure to MCP/API/CLI. Users and AI assistants cannot
use these features.

## Solution: CodeIntelligenceTool MCP Tool

### Single tool with `action` parameter (like a mini-router)

```python
class CodeIntelligenceTool(BaseTool):
    name = "code_intelligence"

    actions:
      - "scan"           → ProjectCodeMap.scan() → TOON summary
      - "trace_calls"    → result.trace_call_flow(name) → TOON
      - "impact"         → result.impact_analysis(name) → TOON
      - "gather_context" → result.gather_context(query) → TOON
      - "dead_code"      → result.dead_code → TOON list
      - "hot_spots"      → result.hot_spots → TOON list
```

### Why one tool instead of six?
- Scan is expensive (~13s for 188 files). Single tool caches the scan result.
- All intelligence actions share the same CodeMapResult.
- Fewer MCP tool registrations = simpler for AI to discover.

### Caching Strategy
- `_cached_result: CodeMapResult | None` persists between calls
- `_cached_project: str | None` tracks which project is cached
- Re-scan only if project path changes

### Task Breakdown

| Task | Description | Files |
|------|-------------|-------|
| T5.1 | Create `CodeIntelligenceTool` class | `mcp/tools/intelligence.py` |
| T5.2 | Register in server + __init__ | `mcp/server.py`, `mcp/tools/__init__.py` |
| T5.3 | Write integration tests | `tests/integration/test_intelligence_tool.py` |
