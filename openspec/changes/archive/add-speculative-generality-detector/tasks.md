# Speculative Generality Detector

## Goal
Find the abstract class with only one implementation — that's complexity pretending to be architecture.

## MVP Scope
- Detect abstract classes/interfaces with 0-1 implementations
- Detect unused type parameters (declared but never referenced in body)
- Detect unused hook methods (abstract methods never overridden in subclasses)
- Detect overly broad interfaces (interfaces with too many abstract methods)
- 4 languages: Python, JS/TS, Java, Go
- 30+ tests
- MCP tool integration

## Technical Approach
- Pure AST traversal, single-file scope
- Pattern: collect class/interface definitions, count implementations per file
- Follows existing 61-analyzer architecture exactly
- No new dependencies

## Issue Types
1. speculative_abstract_class - abstract class/interface with 0-1 implementations
2. unused_type_parameter - generic param declared but never used in method body
3. unused_hook - abstract/virtual method never overridden
4. overly_broad_interface - interface with 5+ abstract methods
