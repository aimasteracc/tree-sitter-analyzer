# Duplicate Condition Analyzer

## Goal
Detect identical or near-identical if conditions repeated in the same file (DRY violation)

## MVP Scope
- Extract if/elif/else-if condition text from AST
- Find exact duplicates by comparing normalized condition text
- Report repeated conditions with line numbers
- 4 languages: Python, JS/TS, Java, Go

## Technical Approach
- AST traversal: find if/elif/else-if nodes, extract condition text
- Normalize whitespace and compare
- Group identical conditions
- Report groups with 2+ occurrences
