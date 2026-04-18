# Method Chain Analyzer

## Goal
Detect excessively long method/attribute chains (Law of Demeter violations)

## MVP Scope
- Count chain length in member access expressions (a.b.c.d)
- Flag chains with 4+ links (long_chain)
- Flag chains with 6+ links (train_wreck)
- 4 languages: Python, JS/TS, Java, Go
- Report hotspots with line numbers and chain text

## Technical Approach
- Pure AST traversal (same pattern as BooleanComplexityAnalyzer)
- Python: attribute → attribute chains
- JS/TS: member_expression chains
- Java: field_access / method_invocation chains
- Go: selector_expression chains
- Recursive chain length counting
- Frozen dataclasses for results
