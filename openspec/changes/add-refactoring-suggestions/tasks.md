# Refactoring Suggestions

## Goal

"Tell me how to fix my code smells"

Refactoring Suggestions provides actionable, step-by-step guidance to fix code quality issues detected by code_smell_detector. Instead of just reporting problems, it generates specific refactoring steps with before/after examples.

## MVP Scope

1. **Suggestion Engine**: Generate refactoring suggestions based on code_smell_detector results
2. **Pattern-Based Recommendations**: Use AST pattern matching to suggest specific refactorings
3. **Multi-Language Support**: Python, JavaScript, Java, Go, C#, TypeScript
4. **MCP Tool Integration**: Expose as `refactoring_suggestions` tool in analysis toolset
5. **Diff Format Output**: Show before/after code for each suggestion

## Technical Approach

### Refactoring Patterns

| Code Smell | Refactoring Suggestion |
|-----------|----------------------|
| God Class | Extract Class, Extract Method |
| Long Method | Extract Method, Replace Temp with Query |
| Deep Nesting | Guard Clauses, Extract Method |
| Magic Numbers | Replace Magic Number with Constant |
| Many Imports | Remove Unused Imports, Façade Pattern |
| Large Class | Extract Class, Extract Subclass |

### Module Structure

```
tree_sitter_analyzer/analysis/refactoring_suggestions.py
- RefactoringSuggestion: dataclass (type, title, description, severity, code_diff)
- RefactoringAdvisor (class)
  - suggest_fixes(file_path, smell_results): list[RefactoringSuggestion]
  - generate_extract_method(node): RefactoringSuggestion
  - generate_extract_class(node): RefactoringSuggestion
  - generate_guard_clause(node): RefactoringSuggestion
  - generate_constant_extraction(node): RefactoringSuggestion

tree_sitter_analyzer/mcp/tools/refactoring_suggestions_tool.py
- refactoring_suggestions MCP tool
- Schema: file_path, min_severity, include_diff
- Output formats: TOON, JSON, diff
```

### Dependencies

- Existing code_smells.py module
- Existing tree-sitter language parsers
- unidiff library for diff generation (optional)

## Implementation Plan

### Sprint 1: Suggestion Engine (15+ tests)

- [ ] Create `analysis/refactoring_suggestions.py` module
- [ ] Implement `RefactoringSuggestion` dataclass
- [ ] Implement `RefactoringAdvisor.suggest_fixes()` base method
- [ ] Implement `generate_extract_method()` suggestion
- [ ] Implement `generate_guard_clause()` suggestion
- [ ] Implement `generate_constant_extraction()` suggestion
- [ ] Add unit tests (15+ tests)

### Sprint 2: Multi-Language Patterns (15+ tests)

- [ ] Python: Extract Method, Guard Clause patterns
- [ ] JavaScript/TypeScript: Extract Method patterns
- [ ] Java: Extract Class, Extract Method patterns
- [ ] Go: Extract Function patterns
- [ ] C#: Extract Method patterns
- [ ] Add integration tests (10+ tests)

### Sprint 3: MCP Tool Integration (15+ tests)

- [ ] Create `mcp/tools/refactoring_suggestions_tool.py`
- [ ] Register to ToolRegistry (analysis toolset)
- [ ] Add schema: file_path, smell_types, min_severity, output_format
- [ ] Implement diff format output (before/after code)
- [ ] Add tool tests (15+ tests)

## Success Criteria

- [ ] 45+ tests passing (15 + 15 + 15)
- [ ] Generates actionable suggestions for at least 5 code smells
- [ ] Supports Python, JavaScript, Java, Go, C#
- [ ] ruff check passes, mypy --strict passes
- [ ] Tool registered and discoverable via tools/list
- [ ] Total tools: 29 → 30

## Exit Criteria

- Sprint 1: Suggestion engine + Python patterns (15+ tests)
- Sprint 2: Multi-language patterns (15+ tests)
- Sprint 3: MCP tool integration (15+ tests)
- Total: 45+ tests pass
- Documentation updated
