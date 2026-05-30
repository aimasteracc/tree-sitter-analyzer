# Tasks: Complete SLF001 Elimination (144→0)

## Background

Eliminate all 144 SLF001 (cross-class private member access) violations across the
entire codebase using the public alias pattern, `@property` accessors, and module-level
function calls. Three phases across three sessions.

## Phase A — ASTCache + Core layer (144→87, committed)

Spec: `expose-ast-cache-get-conn/tasks.md` + core layer work

- [x] **A1** ASTCache.get_conn() public alias (31 violations eliminated)
- [x] **A2** QueryExecutor public aliases: create_error_result, execution_stats, query_loader, process_captures
- [x] **A3** UnifiedAnalysisEngine._get_or_create() classmethod refactor
- [x] **A4** PerformanceMonitor.set_duration = _set_duration alias

## Phase B — Formatter layer (87→24, committed)

- [x] **B1** BaseTableFormatter: convert_visibility, extract_doc_summary, clean_csv_text aliases
- [x] **B2** ToonEncoder: handle_dict_start/key, handle_list_start/item, handle_array_table aliases
       NOTE: encode_to_json used (not fallback_to_json) to avoid collision with constructor bool attr
- [x] **B3** ToonFormatter: encoder.encode_to_json() call
- [x] **B4** CppTableFormatter: format_class_details, format_method_row, create_compact_signature, shorten_type
- [x] **B5** PythonTableFormatter: all convert_*_for_python, format_* helpers
- [x] **B6** _CppFormatterConvertMixin: convert_class/function/variable/import_element aliases
- [x] **B7** JavaTableFormatterClassMixin: module-level fn calls, format_class_section alias
- [x] **B8** JavaTableFormatterCompactMixin: create_compact_signature alias; shorten_type() direct call
- [x] **B9** All companion modules (_python_formatter_*.py, _toon_encoder_task_helpers.py,
       _typescript_formatter_*.py, _cpp_formatter_helpers.py): formatter.xxx not ._xxx
- [x] **B10** Test fixes: test_cpp_formatter_helpers.py _make_formatter(), test_python_formatter_conversion.py FakeFormatter

## Phase C — MCP tools + infrastructure layer (24→0, committed)

- [x] **C1** ASTCache.fts5_available @property (5 callers in ast_cache_tool, symbol_search, _fts_fast_path)
- [x] **C2** FileWatcher.poll_interval + backend @properties (ast_cache_tool callers)
- [x] **C3** TreeSitterAnalyzerMCPServer: ensure_initialized, validate_file_path_security,
       handle_set_project_path, handle_extract_code_section method aliases + tool_instances/tools @properties
- [x] **C4** SharedCache: initialize = _initialize alias
- [x] **C5** MarkdownExtractorStateMixin: reset_caches = _reset_caches alias
- [x] **C6** _QueryState: reset_seen_symbols() setter method
- [x] **C7** project_graph.py: self.graph.all_nodes() instead of self.graph._nodes
- [x] **C8** CachedDependencyGraph: add all_nodes() to match DependencyGraph protocol
- [x] **C9** synapse_resolver/_context.py: # noqa: SLF001 for same-class different-instance access
- [x] **C10** ast_cache.py git_activation._activation_disabled(): # noqa: SLF001 (module-level function)
- [x] **C11** _java_formatter_class_mixin.py: fix noqa comment placement

## Verification

- [x] **V1** SLF001 violations: 144 → 0
- [x] **V2** Full test suite: 18053 passed, 100 skipped, 2 xfailed, 0 failed
- [x] **V3** Golden master regression: 78/78 passed
- [x] **V4** All commits on feature/code-intelligence-architecture branch
