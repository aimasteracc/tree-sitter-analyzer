# Switch Smells Analyzer

## Goal
Detect complex switch/match/select statements that should use polymorphism

## MVP Scope
- Count cases in switch/match/select statements
- Flag 5+ cases (too_many_cases)
- Flag 4+ cases without default (missing_default)
- 4 languages: Python (match), JS/TS (switch), Java (switch), Go (switch/select)

## Technical Approach
- Pure AST traversal
- Per-language switch statement types
- Python wildcard detection for default cases
