# Sprint 3: Incremental Scan — Requirements

## Problem
`ProjectCodeMap.scan()` performs a full re-scan every time (~10s for 100K LOC).
For MCP tools, this means AI assistants wait 10+ seconds between calls.
Second call to same project should be <500ms, not another 10s.

## Goal
Add mtime-based file-level caching to `ProjectCodeMap` so that:
1. First scan: unchanged (full parse)
2. Second scan (same project, no changes): <500ms
3. Second scan (1 file changed): only re-parse that file, rebuild index

## Non-Goals
- Parallel parsing (Phase A2, separate sprint)
- Git diff mode (Phase A3, separate sprint)
- Persistent disk cache (future, pickle-based)

## Acceptance Criteria
- AC1: `scan()` returns identical `CodeMapResult` whether incremental or full
- AC2: Second scan with 0 changes completes in <500ms (vs ~10s)
- AC3: If 1 file changes, only that file is re-parsed
- AC4: If a file is deleted, its symbols/modules are removed
- AC5: If a new file is added, it is picked up
- AC6: All existing 998 tests still pass
- AC7: New tests cover: no-change, one-change, add-file, delete-file scenarios
