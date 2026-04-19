# Callback Hell Detector

## Goal
Detect deeply nested callback patterns that make code unreadable and unmaintainable.

## MVP Scope
- [ ] Core analyzer: callback_hell.py (inherits BaseAnalyzer)
- [ ] Detect: callback_hell (4+ levels), deep_callback (3 levels), promise_chain_hell (4+ .then())
- [ ] Languages: Python, JavaScript/TypeScript, Java, Go
- [ ] MCP tool: callback_hell_tool.py registered in tool_registration.py
- [ ] Tests: 35+ tests covering all issue types and languages

## Technical Approach
- Pure AST traversal — track nesting depth of callback-like patterns
- Python: nested function_definition/lambda passed as arguments
- JS/TS: nested function_expression/arrow_function as arguments, chained .then()
- Java: nested anonymous_class_body / lambda_expression
- Go: nested func_literal
- Count nesting depth, flag at thresholds (3=warning, 4+=critical)

## Dependencies
- BaseAnalyzer (analysis/base.py)
- LanguageLoader (language_loader.py)
- tool_registration.py for MCP registration
