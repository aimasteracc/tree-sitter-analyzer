# Variable Shadowing Detector

## Goal
Detect inner-scope variables that shadow outer-scope variables of the same name — a silent bug source across Python, JS/TS, Java, and Go.

## MVP Scope
- Detect: function params shadowing outer vars, local vars shadowing params, inner block vars shadowing outer block vars
- Languages: Python, JavaScript/TypeScript, Java, Go
- Test standard: 30+ tests covering all 4 languages

## Technical Approach
- Inherit BaseAnalyzer (no _LANGUAGE_MODULES)
- Scope stack traversal: maintain list of sets, each set = declared names in that scope
- When entering a new scope (function, lambda, block, etc.), push new set
- On variable declaration, check if name exists in any outer scope set
- Report shadowing with line number, inner/outer variable names, scope types
- MCP tool registered via registry.py

## Dependencies
- tree-sitter language modules (existing)
- BaseAnalyzer base class
- MCP tool registration in registry.py
