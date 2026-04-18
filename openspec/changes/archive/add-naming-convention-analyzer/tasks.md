# Naming Convention Analyzer

## Goal
Detect identifiers that violate language naming conventions and provide actionable rename suggestions.

## MVP Scope
- 4 violation types: single_letter_var, inconsistent_style, language_violation, upper_snake_not_const
- 4 languages: Python, JS/TS, Java, Go
- Output: naming quality score (0-100) + violation list with suggestions
- MCP tool: naming_conventions registered to analysis toolset

## Technical Approach
- Tree-sitter AST walking for identifier extraction
- Regex for naming style detection (snake_case, camelCase, PascalCase, UPPER_SNAKE)
- Per-language convention tables
- ~400 lines engine + ~200 lines MCP tool + ~400 lines tests

## Sprint Plan
- [ ] Sprint 1: Core engine (Python support + data structures)
- [ ] Sprint 2: Multi-language support (JS/TS, Java, Go) + MCP tool
- [ ] Sprint 3: Tests + CI verification

## Dependencies
- tree-sitter language modules (already available)
- BaseMCPTool, handle_mcp_errors, ToonEncoder (existing)
