# S6: LanguageProfile — Tasks

| Task | Status | Files | Acceptance |
|------|--------|-------|------------|
| T1: LanguageProfile dataclass | pending | `core/types.py` | frozen, immutable, all fields defined |
| T2: GenericLanguageParser | pending | `languages/generic_parser.py` | parse() returns LanguageParseResult |
| T3: TDD tests for generic parser | pending | `tests/unit/test_generic_parser.py` | ≥ 15 tests |
| T4: Go profile + tree-sitter dep | pending | `languages/profiles.py`, `pyproject.toml` | Go parsing works |
| T5: Go language tests | pending | `tests/unit/test_go_parser.py` | ≥ 10 tests |
| T6: Rust profile + tree-sitter dep | pending | `languages/profiles.py`, `pyproject.toml` | Rust parsing works |
| T7: Rust language tests | pending | `tests/unit/test_rust_parser.py` | ≥ 10 tests |
| T8: C profile + tree-sitter dep | pending | `languages/profiles.py`, `pyproject.toml` | C parsing works |
| T9: C language tests | pending | `tests/unit/test_c_parser.py` | ≥ 10 tests |
| T10: SupportedLanguage + registry | pending | `core/types.py`, `core/language_registry.py` | New langs detected |
| T11: MCP tools integration | pending | `mcp/tools/analyze.py` | analyze_code_structure supports new langs |
| T12: Full regression | pending | `tests/` | 0 failures |
