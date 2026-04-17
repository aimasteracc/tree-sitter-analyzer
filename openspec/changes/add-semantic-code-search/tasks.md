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

**Sprint 1: Query Classifier + Fast Path (3-5 days)**
- Pattern matching for simple queries (regex-based)
- Integration with grep/ripgrep/ast-grep
- Result formatter (unified output)
- 5+ tests

**Sprint 2: LLM Integration (3-5 days)**
- LLM query parser (OpenAI/Anthropic/local support)
- Query → tool call translation
- Result ranking and relevance scoring
- Error handling for LLM failures
- 5+ tests

**Sprint 3: Adaptive Learning (2-3 days)**
- Query cache with git SHA invalidation
- Pattern learning (LLM → fast path promotion)
- Simple metrics logging
- 5+ tests

**Sprint 4: CLI + MCP Tool (2-3 days)**
- CLI command: `tree-sitter search`
- MCP tool registration
- Documentation with 10+ example queries
- Integration tests
- 5+ tests

## Success Criteria

- [ ] Simple queries return in <1 second (no LLM)
- [ ] Complex queries return in <5 seconds (with LLM)
- [ ] 50%+ of queries handled by fast path (MVP)
- [ ] CLI + MCP tool both functional
- [ ] 20+ tests covering all paths
- [ ] Documentation with 10+ example queries

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
