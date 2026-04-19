# Empty Block Detector

## Goal
Detect empty code blocks that may hide bugs or indicate dead code: empty function bodies, empty if/else/try/catch/finally blocks, empty loops.

## MVP Scope
- Detect empty block: block with only whitespace/comments (or completely empty)
- Issue types: empty_function, empty_catch, empty_block, empty_loop
- Severity: high (empty catch), medium (empty function), low (empty if/else/loop)
- 4 languages: Python, JS/TS, Java, Go
- 30+ tests

## Technical Approach
- Pure AST traversal: check block children count (excluding comments)
- Per-language block node types
- Data classes: EmptyBlockIssue, EmptyBlockResult
- MCP tool wrapping follows existing pattern

## Test Standard
- 30+ tests (analysis + MCP tool)
- Test fixtures for each language
- Edge cases: blocks with only comments, nested empty blocks, pass statement in Python
