# Magic String Detector

## Goal
Detect hardcoded string literals that should be extracted to named constants: error messages, URLs, file paths, format strings, and repeated strings.

## MVP Scope
- Detect hardcoded strings in function bodies (not in imports/comments)
- Issue types: magic_string (hardcoded literal), repeated_string (same string appears 3+ times)
- Severity: medium (repeated), low (single magic string)
- 4 languages: Python, JS/TS, Java, Go
- 30+ tests

## Technical Approach
- AST traversal to find string_literal nodes inside function bodies
- Skip: import statements, docstrings, type annotations, decorators
- Track repeated strings with a frequency map
- Data classes: MagicStringIssue, MagicStringResult
- MCP tool wrapping follows existing pattern

## Test Standard
- 30+ tests (analysis + MCP tool)
- Test fixtures for each language
- Edge cases: empty strings, test assertions, logging strings
