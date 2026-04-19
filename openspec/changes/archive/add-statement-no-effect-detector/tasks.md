# Statement-with-No-Effect Detector

## Goal
Detect expression statements that have no effect: x == 5; (meant x = 5;), discarded arithmetic, standalone literals.

## MVP Scope
- Detect comparison/arithmetic/literal expression statements
- Support Python, JavaScript, TypeScript, Java, Go
- 23 tests passing

## Technical Approach
- Pure AST traversal via BaseAnalyzer pattern
- Walk expression_statement nodes, classify child expressions
- MCP tool registered in tool_registration.py

## Status: DONE
