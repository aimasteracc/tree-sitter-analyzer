Analyzing directory: tree_sitter_analyzer_v2
======================================================================
Found 42 Python files

Processing: search.py
Processing: __main__.py
Processing: api\interface.py
Processing: cli\main.py
Processing: core\detector.py
Processing: core\exceptions.py
Processing: core\parser.py
Processing: core\protocols.py
Processing: core\types.py
Processing: formatters\markdown_formatter.py
Processing: formatters\registry.py
Processing: formatters\toon_formatter.py
Processing: graph\builder.py
Processing: graph\export.py
Processing: graph\incremental.py
Processing: graph\queries.py
Processing: languages\java_parser.py
Processing: languages\python_parser.py
Processing: languages\typescript_parser.py
Processing: mcp\server.py
Processing: security\validator.py
Processing: utils\binaries.py
Processing: utils\encoding.py
Processing: mcp\tools\analyze.py
Processing: mcp\tools\base.py
Processing: mcp\tools\extract.py
Processing: mcp\tools\find_and_grep.py
Processing: mcp\tools\query.py
Processing: mcp\tools\registry.py
Processing: mcp\tools\scale.py
Processing: mcp\tools\search.py

Combined Graph Statistics:
  Total nodes: 318
  Total edges: 504

Combined TOON Output (summary mode):
----------------------------------------------------------------------
MODULES: 29
CLASSES: 35
FUNCTIONS: 103

MODULE: search
  CLASS: SearchEngine
    FUNC: find_files
      CALLS: _parse_fd_output
    FUNC: search_content
      CALLS: _parse_rg_output
  CLASS: FindFilesTool
    FUNC: get_name
    FUNC: get_description
    FUNC: get_schema
    FUNC: execute
  CLASS: SearchContentTool
    FUNC: get_name
    FUNC: get_description
    FUNC: get_schema
    FUNC: execute

MODULE: __main__

MODULE: interface
  CLASS: TreeSitterAnalyzerAPI
    FUNC: analyze_file
    FUNC: analyze_file_raw
    FUNC: search_files
    FUNC: search_content

MODULE: main
  FUNC: create_parser
  FUNC: cmd_analyze
  FUNC: cmd_search_files
  FUNC: cmd_search_content
  FUNC: main
    CALLS: create_parser

MODULE: detector
  CLASS: LanguageDetector
    FUNC: detect_from_path
    FUNC: detect_from_content
      CALLS: detect_from_path, _detect_shebang, _detect_content_patterns, _combine_signals

MODULE: exceptions
  CLASS: ParserError
  CLASS: UnsupportedLanguageError
  CLASS: ParseError
  CLASS: FileTooLargeError
  CLASS: SecurityViolationError

MODULE: parser
  CLASS: TreeSitterParser
    FUNC: language
    FUNC: parse
      CALLS: _ensure_initialized, _check_tree_has_errors, _convert_node

MODULE: protocols
  CLASS: ParserProtocol
    FUNC: language
    FUNC: parse

MODULE: types
  CLASS: ASTNode
  CLASS: ParseResult
    FUNC: is_valid
  CLASS: SupportedLanguage
    FUNC: name
    FUNC: extensions
    FUNC: from_extension
    FUNC: from_name

MODULE: markdown_formatter
  CLASS: MarkdownFormatter
    FUNC: format
      CALLS: _encode

MODULE: registry
  CLASS: Formatter
    FUNC: format
  CLASS: FormatterRegistry
    FUNC: register
    FUNC: get
      CALLS: list_formats
    FUNC: list_formats
  CLASS: ToolRegistry
    FUNC: register
    FUNC: get
      CALLS: list_tools
    FUNC: list_tools
    FUNC: get_all_schemas
  FUNC: get_default_registry

MODULE: toon_formatter
  CLASS: ToonFormatter
    FUNC: format
      CALLS: _encode

MODULE: builder
  CLASS: CodeGraphBuilder
    FUNC: build_from_file
      CALLS: _extract_module_node, _extract_class_node, _extract_function_node, _build_calls_edges
    FUNC: save_graph
    FUNC: load_graph

MODULE: export
  FUNC: export_for_llm
    CALLS: _format_function, _add_call_info

MODULE: incremental
  FUNC: detect_changes
  FUNC: update_graph

MODULE: queries
  FUNC: get_callers
  FUNC: get_call_chain
  FUNC: find_definition

MODULE: java_parser
  CLASS: JavaParser
    FUNC: parse
      CALLS: _extract_all

MODULE: python_parser
  CLASS: PythonParser
    FUNC: parse
      CALLS: _extract_imports, _extract_functions, _extract_classes, _has_main_block

MODULE: typescript_parser
  CLASS: TypeScriptParser
    FUNC: parse
      CALLS: _extract_all

MODULE: server
  CLASS: MCPServer
    FUNC: get_capabilities
    FUNC: handle_request
      CALLS: _error_response, _handle_initialize, _handle_shutdown, _handle_ping

MODULE: validator
  CLASS: SecurityValidator
    FUNC: validate_file_path
    FUNC: validate_regex

MODULE: binaries
  CLASS: BinaryNotFoundError
  FUNC: get_fd_path
  FUNC: get_ripgrep_path
  FUNC: check_fd_available
    CALLS: get_fd_path
  FUNC: check_ripgrep_available
    CALLS: get_ripgrep_path
  FUNC: get_fd_version
    CALLS: get_fd_path
  FUNC: get_ripgrep_version
    CALLS: get_ripgrep_path
  FUNC: get_fd_installation_instructions
  FUNC: get_ripgrep_installation_instructions
  FUNC: require_fd
    CALLS: get_fd_path, get_fd_installation_instructions
  FUNC: require_ripgrep
    CALLS: get_ripgrep_path, get_ripgrep_installation_instructions
  FUNC: get_binaries_status
    CALLS: get_fd_path, get_fd_version, get_ripgrep_path, get_ripgrep_version
  FUNC: require_all_binaries
    CALLS: get_binaries_status, get_fd_installation_instructions, get_ripgrep_installation_instructions
  FUNC: can_use_fast_search
    CALLS: check_fd_available, check_ripgrep_available

MODULE: encoding
  CLASS: EncodingCache
    FUNC: get
      CALLS: _get_cache_key
    FUNC: set
      CALLS: _get_cache_key
    FUNC: clear
  CLASS: EncodingDetector
    FUNC: detect_encoding
      CALLS: get, _detect_bom, _try_utf8, _use_chardet, _try_fallbacks, set
    FUNC: read_file_safe
      CALLS: detect_encoding
    FUNC: read_file_streaming
      CALLS: detect_encoding

MODULE: analyze
  CLASS: AnalyzeTool
    FUNC: get_name
    FUNC: get_description
    FUNC: get_schema
    FUNC: execute

MODULE: base
  CLASS: BaseTool
    FUNC: get_name
    FUNC: get_description
    FUNC: get_schema
    FUNC: execute

MODULE: extract
  CLASS: ExtractCodeSectionTool
    FUNC: get_name
    FUNC: get_description
    FUNC: get_schema
    FUNC: get_tool_definition
      CALLS: get_name, get_description, get_schema
    FUNC: execute
      CALLS: _execute_batch, _extract_lines

MODULE: find_and_grep
  CLASS: FindAndGrepTool
    FUNC: get_name
    FUNC: get_description
    FUNC: get_schema
    FUNC: get_tool_definition
      CALLS: get_name, get_description, get_schema
    FUNC: execute

MODULE: query
  CLASS: QueryTool
    FUNC: get_name
    FUNC: get_description
    FUNC: get_schema
    FUNC: execute
      CALLS: _extract_elements, _apply_filters

MODULE: scale
  CLASS: CheckCodeScaleTool
    FUNC: get_name
    FUNC: get_description
    FUNC: get_schema
    FUNC: get_tool_definition
      CALLS: get_name, get_description, get_schema
    FUNC: execute
      CALLS: _execute_batch_mode, _calculate_file_metrics, _extract_structure, _generate_guidance

