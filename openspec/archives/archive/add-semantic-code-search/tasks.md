# Semantic Code Search - Hybrid Adaptive System

## Goal

Enable developers to query their codebase using natural language or simple patterns, with fast deterministic tools for simple queries and LLM-powered semantic understanding for complex ones.

## Inspiration

From office-hours design discussion: "The 'whoa' moment is being able to ask 'Show me all functions that handle user authentication' and getting actual results with code snippets, call graphs, and blast radius."

## MVP Scope

1. **Query Classifier** - Pattern matching for simple vs complex queries
2. **Fast Path Executor** - Integration with grep/ast-grep/existing MCP tools
3. **LLM Integration** - Fallback for complex semantic queries
4. **Adaptive Learning** - Cache query→tool mappings for faster subsequent queries
5. **CLI + MCP Tool** - `tree-sitter search` command

## Technical Approach

### Hybrid Architecture

```
User Query → Query Classifier → Fast Path (grep/ast-grep) or LLM Path → Result Formatter
                                      ↓
                              Query Cache (git SHA invalidation)
```

### Sprint Breakdown

**Sprint 1: Query Classifier + Fast Path (3-5 days)** ✅ COMPLETE
- [x] Pattern matching for simple queries (regex-based)
- [x] Integration with grep/ripgrep/ast-grep
- [x] Result formatter (unified output)
- [x] 49 tests written (exceeds 5+ target)

**Sprint 2: LLM Integration (3-5 days)** ✅ COMPLETE
- [x] LLM query parser (OpenAI/Anthropic support)
- [x] Query → tool call translation
- [x] Result ranking and relevance scoring (placeholder)
- [x] Error handling for LLM failures
- [x] 18 tests written (exceeds 5+ target)

**Sprint 3: Adaptive Learning (2-3 days)** ✅ COMPLETE
- [x] Query cache with git SHA invalidation
- [x] Pattern learning (LLM → fast path promotion)
- [x] Simple metrics logging
- [x] 27 tests written (exceeds 5+ target)

**Sprint 4: CLI + MCP Tool (2-3 days)** ✅ COMPLETE
- ✅ CLI command: `tree-sitter search` (--search, --search-format, --search-no-cache, --search-provider)
- ✅ MCP tool registration (semantic_search in query toolset)
- ✅ Documentation with 10+ example queries (CHANGELOG.md, README.md, ARCHITECTURE.md)
- ✅ Integration tests (test_semantic_search_cli.py: 11 tests, test_semantic_search_tool.py: 11 tests)
- ✅ 5+ tests (22 tests total, exceeds target)

## Success Criteria

- [x] Simple queries return in <1 second (no LLM) ✅ Sprint 1
- [ ] Complex queries return in <5 seconds (with LLM)
- [x] 50%+ of queries handled by fast path (MVP) ✅ Sprint 1
- [x] CLI + MCP tool both functional ✅ Sprint 4
- [x] 20+ tests covering all paths ✅ Sprint 1 (49 tests)
- [x] Documentation with 10+ example queries ✅ Sprint 4

## Dependencies

- tree-sitter (existing)
- tree-sitter-analyzer core (existing)
- grep/ripgrep (system tools)
- Optional: openai, anthropic, llama-cpp-python (for LLM)

## Related Work

- dependency_query MCP tool (can be reused)
- trace_impact MCP tool (can be reused)
- query_code MCP tool (can be reused)
- understand_codebase MCP tool (can be reused)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
