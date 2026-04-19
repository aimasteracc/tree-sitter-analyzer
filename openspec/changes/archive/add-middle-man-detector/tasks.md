# Middle Man Detector

## Goal
Detect classes that just delegate to other classes without adding value — the Middle Man smell.

## MVP Scope
- Detect classes where most methods just call a single delegate field
- Detect delegation chains (A delegates to B delegates to C)
- 4 languages: Python, JS/TS, Java, Go
- 30+ tests
- MCP tool integration

## Technical Approach
- Pure AST traversal, single-file scope
- For each class: count methods that are pure delegation (call one field's method, return result)
- If delegation ratio > threshold (70%), flag as middle man
- Follows existing 64-analyzer architecture exactly
- No new dependencies

## Issue Types
1. middle_man_class - class with high delegation ratio (≥70% of methods delegate)
2. delegation_chain - method that chains delegations through multiple objects
