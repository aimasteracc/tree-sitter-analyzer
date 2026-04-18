# Feature Envy Detector

## Goal
Detect methods that access other objects' data more than their own, indicating misplaced methods that should be moved to the class they're most interested in.

## MVP Scope
- Detection types: feature_envy, method_chain, inappropriate_intimacy
- 4 languages: Python, JS/TS, Java, Go
- Pure tree-sitter AST analysis
- Independent module, no cross-analyzer dependencies

## Detection Types

### feature_envy
A method makes more calls/attribute accesses on foreign objects than on self/this.
- Python: method accesses `other_obj.attr` more than `self.attr`
- JS/TS: method accesses `otherObj.prop` more than `this.prop`
- Java: method accesses `other.get()` more than `this.get()` or own fields
- Go: method accesses `other.Field` more than receiver fields

### method_chain
Excessive method chaining on foreign objects (3+ chained calls on different object).
- `a.getB().getC().doThing()` — 3+ hops through foreign objects
- Suggests the method should be closer to the data it uses

### inappropriate_intimacy
Two classes accessing each other's private/internal data too much.
- Count cross-class field accesses between pairs of classes
- Flag pairs with high mutual access counts

## Technical Approach
1. Parse each file, extract class definitions and their methods
2. For each method, count self/this accesses vs foreign object accesses
3. Detect method chains by tracing chained method calls
4. Compare cross-class access patterns for intimacy detection
5. Report findings with severity and suggestions

## Test Standard
- Unit tests: 35+ tests covering all detection types, 4 languages
- MCP tool tests: 10+ tests for tool integration
- CI: ruff check + mypy --strict + pytest
