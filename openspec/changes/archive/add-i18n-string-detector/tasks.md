# i18n String Detector

## Goal
Detect user-visible strings in code that need internationalization (i18n). Find hardcoded text in print/raise/log/UI functions that should be extracted for translation.

## MVP Scope
- Detect string literals in output function calls (print, raise, console.log, etc.)
- Classify visibility: USER_VISIBLE, LIKELY_VISIBLE, INTERNAL
- Support 4 languages: Python, JS/TS, Java, Go
- MCP tool registration (analysis toolset)

## Technical Approach
- Independent module: analysis/i18n_strings.py + mcp/tools/i18n_strings_tool.py
- Tree-sitter query for string_literal extraction
- Parent call_expression matching against output function lists
- Visibility classification engine

## Sprint 1: Core Detection Engine (Python) ✅
- [x] Create I18nStringDetector class with dataclasses
- [x] String visibility classifier (USER_VISIBLE / LIKELY_VISIBLE / INTERNAL)
- [x] Python output function detection (print, raise, logging, sys.stderr)
- [x] String filtering (empty, single-char, regex, format specifiers)
- [x] ~20 tests

## Sprint 2: Multi-Language Support ✅
- [x] JS/TS: console.log/warn/error, alert, throw new Error, process.stderr
- [x] Java: System.out.println, Logger, throw new Exception
- [x] Go: fmt.Print/Printf, log.Print, errors.New, fmt.Errorf
- [x] ~20 tests

## Sprint 3: MCP Tool Integration ✅
- [x] Create mcp/tools/i18n_strings_tool.py
- [x] TOON + JSON output formats
- [x] Register to analysis toolset
- [x] ~12 tests
