# Loop Complexity Analyzer

## Goal
Detect nested loops and estimate algorithmic complexity (O(n), O(n²), O(n³), etc.)

## MVP Scope
- Detect for/while/foreach loops and list comprehensions
- Count nesting depth of loops
- Estimate complexity: O(1), O(n), O(n²), O(n³), O(2^n)
- Report hotspots with line numbers
- 4 languages: Python, JS/TS, Java, Go

## Technical Approach
- Pure AST traversal (Method A from eng review)
- Pattern: same as NestingDepthAnalyzer (frozen dataclasses, per-language extraction)
- Detect: nested_loop, loop_in_loop, exponential_pattern
- No cross-analyzer dependencies
