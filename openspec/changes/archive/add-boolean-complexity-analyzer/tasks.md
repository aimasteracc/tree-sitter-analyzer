# Boolean Complexity Analyzer

## Goal
Detect complex boolean expressions (&&/||/and/or chains) with too many conditions

## MVP Scope
- Count conditions in boolean expressions
- Flag expressions with 4+ conditions
- Suggest extraction into named variables
- 4 languages: Python, JS/TS, Java, Go

## Technical Approach
- Pure AST traversal
- Python: boolean_operator nodes
- C-style: binary_expression with && / || operators
- Recursive condition counting
