# S6/S7/S7+: LanguageProfile — Tasks

| Task | Status | Files | Acceptance |
|------|--------|-------|------------|
| T1: LanguageProfile dataclass | **completed** | `core/types.py` | frozen, immutable, all fields defined |
| T2: GenericLanguageParser | **completed** | `languages/generic_parser.py` | parse() returns LanguageParseResult |
| T3: TDD tests for generic parser | **completed** | `tests/unit/test_generic_parser.py` | 58 tests (exceeds 15) |
| T4: Go profile + tree-sitter dep | **completed** | `languages/profiles.py`, `pyproject.toml` | Go parsing works |
| T5: Go language tests | **completed** | `tests/unit/test_generic_parser.py::TestGoParser` | 8 tests |
| T6: Rust profile + tree-sitter dep | **completed** | `languages/profiles.py`, `pyproject.toml` | Rust parsing works |
| T7: Rust language tests | **completed** | `tests/unit/test_generic_parser.py::TestRustParser` | 8 tests |
| T8: C profile + tree-sitter dep | **completed** | `languages/profiles.py`, `pyproject.toml` | C parsing works |
| T9: C language tests | **completed** | `tests/unit/test_generic_parser.py::TestCParser` | 8 tests |
| T10: SupportedLanguage + registry | **completed** | `core/types.py`, `core/language_registry.py` | 11 langs detected |
| T11: MCP tools integration | **completed** | `mcp/tools/analyze.py` | All new langs via registry |
| T12: Full regression | **completed** | `tests/` | 1242 passed, 0 failures |

## S7+: Extended Language Support

| Task | Status | Files | Acceptance |
|------|--------|-------|------------|
| T13: C++ profile + tree-sitter dep | **completed** | `languages/profiles.py`, `pyproject.toml` | C++ parsing works |
| T14: C++ language tests | **completed** | `tests/unit/test_generic_parser.py::TestCppParser` | 8 tests |
| T15: Kotlin profile + tree-sitter dep | **completed** | `languages/profiles.py`, `pyproject.toml` | Kotlin parsing works |
| T16: Kotlin language tests | **completed** | `tests/unit/test_generic_parser.py::TestKotlinParser` | 6 tests |
| T17: PHP profile + tree-sitter dep | **completed** | `languages/profiles.py`, `pyproject.toml` | PHP parsing works |
| T18: PHP language tests | **completed** | `tests/unit/test_generic_parser.py::TestPhpParser` | 6 tests |
| T19: Ruby profile + tree-sitter dep | **completed** | `languages/profiles.py`, `pyproject.toml` | Ruby parsing works |
| T20: Ruby language tests | **completed** | `tests/unit/test_generic_parser.py::TestRubyParser` | 6 tests |
| T21: Full regression after S7+ | **completed** | `tests/` | 1242 passed, 0 failures |

## Summary

- **Total languages**: 11 (Python, Java, TypeScript, JavaScript, Go, Rust, C, C++, Kotlin, PHP, Ruby)
- **Total new tests**: 58 in `test_generic_parser.py`
- **Total regression**: 1242 passed, 4 skipped, 0 failures
- **Architecture**: Data-driven `LanguageProfile` + `GenericLanguageParser` pattern
