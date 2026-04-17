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

### Sprint 1: Suggestion Engine (15+ tests) ✅ Complete

- [x] Create `analysis/refactoring_suggestions.py` module
- [x] Implement `RefactoringSuggestion` dataclass
- [x] Implement `RefactoringAdvisor.suggest_fixes()` base method
- [x] Implement `generate_extract_method()` suggestion
- [x] Implement `generate_guard_clause()` suggestion
- [x] Implement `generate_constant_extraction()` suggestion
- [x] Add unit tests (18 tests pass, ruff + mypy clean)

### Sprint 2: Multi-Language Patterns (15+ tests) ✅ Complete

- [x] Python: Extract Method, Guard Clause patterns
- [x] JavaScript/TypeScript: Arrow Function patterns
- [x] Java: Extract Interface patterns
- [x] Go: Extract Interface patterns
- [x] C#: Async/await patterns
- [x] Add integration tests (28 tests pass, ruff + mypy clean)

### Sprint 3: MCP Tool Integration (15+ tests) ✅ Complete

- [x] Create `mcp/tools/refactoring_suggestions_tool.py`
- [x] Register to ToolRegistry (analysis toolset)
- [x] Add schema: file_path, smell_types, min_severity, output_format
- [x] Implement diff format output (before/after code)
- [x] Add tool tests (39 tests pass, ruff + mypy clean)

## Success Criteria

- [x] 45+ tests passing (39 tests: 18 + 10 + 11)
- [x] Generates actionable suggestions for at least 5 code smells
- [x] Supports Python, JavaScript, Java, Go, C#
- [x] ruff check passes, mypy --strict passes
- [x] Tool registered and discoverable via tools/list
- [x] Total tools: 29 → 30

## Exit Criteria

- Sprint 1: Suggestion engine + Python patterns (15+ tests)
- Sprint 2: Multi-language patterns (15+ tests)
- Sprint 3: MCP tool integration (15+ tests)
- Total: 45+ tests pass
- Documentation updated
