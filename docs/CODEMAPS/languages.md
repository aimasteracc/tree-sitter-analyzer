<!-- Generated: 2026-05-24; doc-code re-sync: 2026-06-17 -->
# Languages Codemap

21 language plugins under `tree_sitter_analyzer/languages/` (16 single-file + 5 subdir packages).
Each implements the `LanguagePlugin` interface (`tree_sitter_analyzer/plugins/base.py`).

## Wiring tiers (canonical breakdown — see README "Supported Languages")

Not every registered plugin is wired into the indexer to the same depth:

- **13 fully wired** (full symbol + call graph): Python, Java, JavaScript, TypeScript, Go, Rust, C, C++, C#, Swift, Kotlin, Ruby, PHP
- **2 symbol-indexed** (call-graph wiring pending): Bash, Scala — both graduated in v1.22.0
- **5 data/markup** (reachable via the single-file CLI path): HTML, CSS, Markdown, SQL, YAML
- **1 scaffold** (plugin exists, indexer wiring pending): JSON

## Supported Languages

| Language | Plugin module | Extractor split | Notes |
|---|---|---|---|
| Java | `languages/java_plugin.py` | `_java_*_helpers.py` ×4 | Spring/JPA awareness; **fixture file — DO NOT refactor** (see CLAUDE.md memory rule) |
| Python | `python_plugin/` | submodules | Type annotations, decorators, async; module constants include chained and same-line assignments |
| TypeScript | `typescript_plugin/` | submodules | Interfaces, types, TSX/JSX; enum kind/export parity and class-field decorators |
| JavaScript | `javascript_plugin/` | submodules | ES6+, JSX; `languages/javascript_plugin/_function_helpers.py` handles class-field arrow methods (is_method, is_static, computed/string/number key names — #890/#892); `queries/javascript.py` VARIABLES + "variable" query include `field_definition` (#891) |
| C | `languages/c_plugin.py` | `_c_*_helpers.py` ×8 | functions, structs, unions, enums, preprocessor; unnamed bitfields are skipped as non-addressable fields |
| C++ | `languages/cpp_plugin.py` | `_cpp_*_helpers.py` ×11 | classes, templates, namespaces; nested template/union type parent metadata and field-reference guards |
| C# | `languages/csharp_plugin.py` | `languages/csharp_helpers.py` | records, async/await, attributes; block and file-scoped namespaces surface as packages |
| Go | `languages/go_plugin.py` | `_go_*_helpers.py` ×6 | structs, interfaces, goroutines |
| Rust | `languages/rust_plugin.py` | inline | traits, impl, macros, derive, enum variants as variables |
| Kotlin | `languages/kotlin_plugin.py` | `languages/kotlin_helpers.py` | data classes, coroutines |
| Scala | `languages/scala_plugin.py` | inline | objects/traits, scaladoc; Scala 3 enum cases, givens, type members, extensions, and AST-cache symbol rows |
| Swift | `languages/swift_plugin.py` | `_swift_plugin_*.py` ×3 | classes, structs, protocols; `.swift` + `.swiftinterface` (issue #131) |
| Ruby | `languages/ruby_plugin.py` | `languages/ruby_helpers.py` | Rails patterns, metaprogramming |
| PHP | `languages/php_plugin.py` | `languages/php_helpers.py` | PHP 8+ attributes, traits |
| HTML | `languages/html_plugin.py` | `languages/html_helpers.py` | DOM elements with role classification |
| CSS | `languages/css_plugin.py` | `languages/css_helpers.py` | selectors + properties |
| SQL | `sql_plugin/` | submodules | tables, views, procedures, triggers; `languages/sql_plugin/table_extractor.py` regex fallback supports ANSI/MySQL/SQL-Server quoted identifiers and populates columns; CTAS (`AS SELECT`) guarded; case-sensitive dedup for quoted names (#880/#881); schema-qualified `CREATE FUNCTION` now extracted (#775); CTAS table name extracted instead of schema name (#808) |
| YAML | `languages/yaml_plugin.py` | `languages/yaml_helpers.py` | anchors, aliases, multi-doc |
| Markdown | `markdown_plugin/` | submodules | headings, code blocks, tables |
| JSON | `languages/json_plugin.py` | inline | basic structure |
| Bash | `languages/bash_plugin.py` | inline | functions, commands |
| Lua | `languages/lua_plugin.py` | inline | extensibility demo; shows new language = 1 file, no central edits (Phase 2 capability system) |

## Shared helpers

Cross-cutting logic shared by several plugins (not a language plugin itself):

- `languages/_complexity_logical.py` — `is_executable_logical_operator()`: counts a `&&`/`||` token toward cyclomatic complexity only when it drives executable control flow. Used by the C/C++/C#/Java walkers to exclude booleans in non-executable contexts (`noexcept`/`requires` specifiers, `#if A && B` preprocessor conditions, default arguments, attributes/annotations, `static_assert`). The cross-language convention is "1 + decision points; each `&&`/`||` is one decision; switch/match counts once" (matching Go/Rust/Swift).
- `languages/_complexity_decisions.py` — `count_decision_complexity()`: AST-node walk for JS/TS cyclomatic complexity (replaces the old keyword-substring text count that inflated complexity for keywords appearing inside identifiers/strings/comments and counted each switch `case`). Counts if / for / for-in/of / while / do-while / switch (once) / catch / ternary plus `&&`/`||`/`??` short-circuit operators (via `_complexity_logical`). Used by the JavaScript and TypeScript extractors.
- `languages/python_plugin/_python_complexity.py` — `python_cyclomatic_complexity()`: AST-node walk for Python cyclomatic complexity (replaces a `re.findall(r"\bkeyword\b", text)` counter that counted keywords in comments/docstrings/strings, counted `match` per-arm, and counted `with`). Counts if / elif / for / while / except / ternary / match (once) / `and`/`or` / comprehension for-and-if clauses. Used by the Python extractor.

## Plugin Contract

Every language plugin implements:

```python
class LanguagePlugin(ABC):
    def get_language_name(self) -> str: ...
    def get_file_extensions(self) -> list[str]: ...
    def get_tree_sitter_language(self) -> tree_sitter.Language | None: ...
    def create_extractor(self) -> ElementExtractor: ...
    async def analyze_file(self, file_path: str, request: AnalysisRequest) -> AnalysisResult: ...
```

`ElementExtractor` returns dict with keys: `functions`, `classes`, `variables`, `imports`,
`packages`, `comments`, `annotations` — flattened to `AnalysisResult.elements`.

## Adding a New Language

1. Add `tree_sitter_<lang>` to `pyproject.toml` dependencies.
2. Create `languages/<lang>_plugin.py` extending `LanguagePlugin`.
3. Register in `tree_sitter_analyzer/languages/` `_LANGUAGE_PLUGIN_PATHS`.
4. Add tree-sitter query file in `queries/<lang>/`.
5. Generate golden corpus + expected.json in `tests/golden/`.
6. Coverage validator (`grammar_coverage/validator.py`) auto-discovers the plugin.
7. Add language to `README.md` supported languages table.

## Grammar Coverage

`grammar_coverage/` validates that each plugin extracts every documented node type:

- **Phase 1** (current): Syntactic Path Coverage — track `(node_type, parent_path)` tuples
- `validate_plugin_coverage(language)` returns `CoverageReport`
- Target: 95%+ for production languages
- See [`docs/grammar-coverage-framework.md`](../grammar-coverage-framework.md)

## Cross-Cutting Helpers

| Module | Used by |
|---|---|
| `utils/tree_sitter_compat.py` | all plugins (handle tree-sitter API version differences) |
| `language_loader.py` | dynamic import of `tree_sitter_<lang>` modules |
| `language_detector.py` | extension → language mapping for unknown files |
| `import_extractors/` | shared per-language import-row builders (top-level package: `import_extractors/_python.py`, `import_extractors/_java.py`, …) |

## See Also

- [`docs/grammar-coverage-framework.md`](../grammar-coverage-framework.md)
- [`docs/new-language-support-checklist.md`](../new-language-support-checklist.md)
- [`tree_sitter_analyzer/plugins/base.py`](../../tree_sitter_analyzer/plugins/base.py) — interface
- [`tree_sitter_analyzer/languages/`](../../tree_sitter_analyzer/languages/) — language → plugin lookup (plugins were reorganised into the `languages/` subdirectory)
- [`scripts/codemap-sync-check.sh`](../../scripts/codemap-sync-check.sh) — pre-commit gate that blocks new `languages/<lang>_plugin/` without a `languages.md` update
