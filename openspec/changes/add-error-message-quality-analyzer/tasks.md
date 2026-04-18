# Error Message Quality Analyzer

## Goal
Detect poor error messages in raise/throw statements

## MVP Scope
- Classify messages as: good, generic, empty, vague
- Detect generic words: "error", "failed", "exception"
- 4 languages: Python (raise), JS/TS (throw), Java (throw), Go (errors.New)
- Report poor messages with line numbers

## Technical Approach
- Pure AST traversal
- Per-language raise/throw extraction
- String message analysis (no LLM)
