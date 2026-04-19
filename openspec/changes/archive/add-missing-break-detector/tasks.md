# Missing Break Detector

## Goal
Detect switch/case statements with missing break/return/throw, causing unintentional fall-through.

## MVP Scope
- [ ] Core analyzer: missing_break.py (inherits BaseAnalyzer)
- [ ] Detect: missing_break (unintentional fall-through)
- [ ] Languages: JavaScript/TypeScript, Java, Go (Go has no fall-through by default)
- [ ] MCP tool: missing_break_tool.py registered in tool_registration.py
- [ ] Tests: 30+ tests covering all issue types and languages

## Technical Approach
- Pure AST traversal — walk switch statements, check each case body for terminating statements
- Terminating: break, return, throw, continue
- Skip: last case (default or final), cases with explicit fallthrough comment
- Python: match statements don't have fall-through, so skip
- Go: switch doesn't fall through by default, skip

## Dependencies
- BaseAnalyzer (analysis/base.py)
- LanguageLoader (language_loader.py)
- tool_registration.py for MCP registration
