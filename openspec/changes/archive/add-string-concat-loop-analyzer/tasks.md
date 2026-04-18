# String Concatenation in Loops Analyzer

## Goal
Detect string concatenation inside loops that causes O(n^2) performance

## MVP Scope
- Detect += / + on strings inside for/while loops
- Detect StringBuilder misuse patterns
- 4 languages: Python, JS/TS, Java, Go
- Report hotspots with line numbers

## Technical Approach
- AST traversal: find loop nodes, then search for string assignment/concat inside
- Python: augmented_assignment += inside for/while
- JS/TS: += inside for/while/do-while/for-of/for-in
- Java: += inside for/while, StringBuilder in loop
- Go: += inside for
- Check if left-hand side is a string variable (type annotation or heuristic)
