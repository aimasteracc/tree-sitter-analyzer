# Regex Safety / ReDoS Detector

## Goal
Find regex patterns vulnerable to catastrophic backtracking (ReDoS).

## MVP Scope
- Detect nested quantifiers: (x+)+, (x*)*, etc.
- Detect overlapping alternation: (a|ab)
- Detect quantified alternation with inner quantifiers
- Support: Python (re.*), JS (/pattern/, new RegExp), Java (Pattern.compile), Go (regexp.Compile)
- 42 tests passing

## Technical Approach
- BaseAnalyzer subclass with pure AST pattern extraction
- Custom regex string analyzer for vulnerability detection
- MCP tool: regex_safety
