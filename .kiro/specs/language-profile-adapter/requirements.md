# S6: LanguageProfile Unified Adapter — Requirements

## Problem

Adding a new language currently requires:
1. Writing a full parser class (300-700 LOC each)
2. Manually wiring into `SupportedLanguage` enum
3. Adding tree-sitter dependency
4. Registering in `parser_registry` / `language_registry`
5. Writing extraction logic that is 80% identical across languages

Three parsers (Python 500L, Java 770L, TypeScript 700L) share ~80% identical patterns:
- AST traversal for functions/classes/imports
- Line number extraction
- Visibility/modifier detection
- Docstring/comment extraction

## Goal

Create a data-driven `LanguageProfile` system where adding a new language requires:
1. A `LanguageProfile` dataclass (~30-50 lines of configuration)
2. A tree-sitter dependency
3. **Zero new parser class**

## Acceptance Criteria

- AC1: `LanguageProfile` dataclass defines all language-specific AST node mappings
- AC2: `GenericLanguageParser` uses a profile to extract functions/classes/imports
- AC3: Go language added using only a LanguageProfile (no GoParser class)
- AC4: Rust language added using only a LanguageProfile
- AC5: C language added using only a LanguageProfile
- AC6: Existing Python/Java/TypeScript parsers continue to work (backward compatible)
- AC7: All existing tests pass (zero regression)
- AC8: New languages have ≥ 10 unit tests each

## Non-functional Requirements

- Profile is a frozen dataclass (immutable after creation)
- Thread-safe (profiles are read-only)
- Lazy tree-sitter loading preserved
- <10 LOC to add a simple language
