<!-- Generated: 2026-05-24 -->
# Languages Codemap

21 language plugins under `tree_sitter_analyzer/languages/` (16 single-file + 5 subdir packages).
Each implements the `LanguagePlugin` interface (`tree_sitter_analyzer/plugins/base.py`).

## Supported Languages

| Language | Plugin module | Extractor split | Notes |
|---|---|---|---|
| Java | `java_plugin.py` | `_java_*_helpers.py` ×4 | Spring/JPA awareness; **fixture file — DO NOT refactor** (see CLAUDE.md memory rule) |
| Python | `python_plugin/` | submodules | Type annotations, decorators, async |
| TypeScript | `typescript_plugin/` | submodules | Interfaces, types, TSX/JSX |
| JavaScript | `javascript_plugin/` | submodules | ES6+, JSX |
| C | `c_plugin.py` | `_c_*_helpers.py` ×8 | functions, structs, unions, enums, preprocessor |
| C++ | `cpp_plugin.py` | `_cpp_*_helpers.py` ×11 | classes, templates, namespaces |
| C# | `csharp_plugin.py` | `csharp_helpers.py` | records, async/await, attributes |
| Go | `go_plugin.py` | `_go_*_helpers.py` ×6 | structs, interfaces, goroutines |
| Rust | `rust_plugin.py` | inline | traits, impl, macros, derive |
| Kotlin | `kotlin_plugin.py` | `kotlin_helpers.py` | data classes, coroutines |
| Scala | `scala_plugin.py` | inline | objects/traits, scaladoc |
| Swift | `swift_plugin.py` | `_swift_plugin_*.py` ×3 | classes, structs, protocols; `.swift` + `.swiftinterface` (issue #131) |
| Ruby | `ruby_plugin.py` | `ruby_helpers.py` | Rails patterns, metaprogramming |
| PHP | `php_plugin.py` | `php_helpers.py` | PHP 8+ attributes, traits |
| HTML | `html_plugin.py` | `html_helpers.py` | DOM elements with role classification |
| CSS | `css_plugin.py` | `css_helpers.py` | selectors + properties |
| SQL | `sql_plugin/` | submodules | tables, views, procedures, triggers |
| YAML | `yaml_plugin.py` | `yaml_helpers.py` | anchors, aliases, multi-doc |
| Markdown | `markdown_plugin/` | submodules | headings, code blocks, tables |
| JSON | `json_plugin.py` | inline | basic structure |
| Bash | `bash_plugin.py` | inline | functions, commands |

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
3. Register in `tree_sitter_analyzer/plugins/registry.py` `_LANGUAGE_PLUGIN_PATHS`.
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
| `tree_sitter_compat.py` | all plugins (handle tree-sitter API version differences) |
| `language_loader.py` | dynamic import of `tree_sitter_<lang>` modules |
| `language_detector.py` | extension → language mapping for unknown files |
| `import_extractors.py` | shared import-row builders across languages |

## See Also

- [`docs/grammar-coverage-framework.md`](../grammar-coverage-framework.md)
- [`docs/new-language-support-checklist.md`](../new-language-support-checklist.md)
- [`tree_sitter_analyzer/plugins/base.py`](../../tree_sitter_analyzer/plugins/base.py) — interface
- [`tree_sitter_analyzer/plugins/registry.py`](../../tree_sitter_analyzer/plugins/registry.py) — language → plugin lookup
- [`scripts/codemap-sync-check.sh`](../../scripts/codemap-sync-check.sh) — pre-commit gate that blocks new `languages/<lang>_plugin/` without a `languages.md` update
