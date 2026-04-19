# Late-Binding Closure Detector

## Goal
Detect closures inside loops that capture loop variables by reference, causing the closure to always see the final loop value.

## MVP Scope
- Detect lambda/function/arrow_function inside for/while/comprehension loops
- Check if closure body references loop-bound variable
- Support Python, JavaScript, TypeScript, Java
- 18 tests passing

## Technical Approach
- Pure AST traversal via BaseAnalyzer pattern
- Extract loop-bound variable names per language
- Recursively scan loop body for closure nodes that reference those variables
- MCP tool registered in tool_registration.py

## Status: DONE
