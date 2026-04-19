# Unused Parameter Detector

## Goal
Detect function/method parameters that are never referenced in the function body, indicating dead code, incomplete refactoring, or misleading APIs.

## MVP Scope
- [ ] Core analyzer: unused_parameter.py (inherits BaseAnalyzer)
- [ ] Detect: unused_parameter, unused_callback_param, unused_self_param
- [ ] Languages: Python, JavaScript/TypeScript, Java, Go
- [ ] MCP tool: unused_parameter_tool.py registered in tool_registration.py
- [ ] Tests: 35+ tests covering all issue types and languages

## Technical Approach
- Pure AST traversal (no type inference or scope analysis)
- For each function/method: collect parameter names, scan body for identifier references
- Flag parameters whose names never appear as identifiers in the body
- Edge cases: skip _ prefix (Go/Python convention), skip self/cls (Python), skip this (Java)
- Node type mapping per language (same pattern as dead_store.py)

## Dependencies
- BaseAnalyzer (analysis/base.py)
- LanguageLoader (language_loader.py)
- tool_registration.py for MCP registration
