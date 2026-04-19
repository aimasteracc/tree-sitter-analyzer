# God Class Detector

## Goal
Detect classes that are too large and have too many responsibilities (the opposite of Lazy Class).

## MVP Scope
- Count public methods, private methods, fields per class
- Detect god_class: 10+ methods AND 10+ fields
- Detect low_cohesion: methods share <30% of fields they access
- Severity: high (15+ methods), medium (10-14), low (7-9 with other signals)
- 4 languages: Python, JS/TS, Java, Go

## Technical Approach
- Pure AST traversal, per-language class/method/field node types
- Reuse existing analyzer pattern (see lazy_class, feature_envy)
- Data classes: ClassInfo, GodClassIssue, GodClassResult
- MCP tool wrapping follows existing pattern

## Test Standard
- 30+ tests (analysis + MCP tool)
- Test fixtures for each language
- Edge cases: nested classes, anonymous classes, interfaces
