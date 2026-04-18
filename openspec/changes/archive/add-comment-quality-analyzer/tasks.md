# Comment Quality Analyzer

## Goal
Detect stale/misleading comments: param mismatches, missing return docs, TODO tracking, and comment rot risk scoring. "Detect comments that lie about what your code actually does."

## MVP Scope
- Parameter annotation matching (docstring params vs actual params)
- Return value annotation matching
- TODO/FIXME/HACK tracking with context
- Comment rot risk scoring (via GitAnalyzer)
- 4 languages: Python, JS/TS, Java, Go

## Technical Approach
- Option A: Independent module (analysis/comment_quality.py + mcp/tools/comment_quality_tool.py)
- Reuse GitAnalyzer for blame-based rot scoring
- Register to analysis toolset

## Sprints
- Sprint 1: Python core engine (~25 tests)
- Sprint 2: Multi-language support (~20 tests)
- Sprint 3: MCP tool + git blame rot scoring (~15 tests)
