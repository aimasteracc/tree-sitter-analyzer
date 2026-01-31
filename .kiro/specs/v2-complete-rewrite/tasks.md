# Implementation Plan: V2 Complete Rewrite - TDD-First Approach

## Overview

Complete rewrite of tree-sitter-analyzer from scratch using Test-Driven Development (TDD) methodology. The project will support 17 programming languages with MCP integration, TOON + Markdown output, fd + ripgrep search, and dual CLI/API interfaces.

**Timeline**: 6-8 weeks with 10-20 hours per week effort (60-160 total hours)

**Key Updates** (2026-01-31):
- ✅ Preserve fd + ripgrep search functionality (critical for AI assistants)
- ✅ Output formats: **TOON + Markdown only** (remove JSON)
- ✅ Dual interfaces: **CLI (testing) + API (Agent Skills) + MCP (AI integration)**

---

## Requirements

- **TDD Methodology**: Write tests FIRST, then implementation
- **17 Language Support**: Python, TypeScript, JavaScript, Java, C, C++, C#, Go, Rust, Kotlin, PHP, Ruby, SQL, HTML, CSS, YAML, Markdown
- **Search Integration**: fd (file search) + ripgrep (content search)
- **MCP Protocol Integration**: Full Claude Desktop/Cursor/Roo Code support
- **Output Formats**: TOON (token-optimized) + Markdown (human-readable)
- **Interfaces**: CLI + Python API + MCP Server
- **Performance**: Sub-100ms response for typical files, <100ms fd search
- **Quality**: 80%+ test coverage, 100% type hints

---

## Architecture Changes

This is a complete rewrite, so all files will be new:
- **v2/** - New clean codebase directory
- **v2/core/** - Core parsing and analysis engine
- **v2/search.py** - fd + ripgrep integration
- **v2/plugins/** - Plugin system architecture
- **v2/languages/** - Language-specific implementations
- **v2/formatters/** - Output formatting (TOON, Markdown)
- **v2/mcp/** - MCP server and tools
- **v2/cli/** - CLI interface
- **v2/api/** - Python API interface
- **v2/tests/** - TDD test suite

---

## Implementation Steps

### Phase 0: Foundation & TDD Setup (Week 1, 10-20h)

#### **T0.1: Project Scaffold**
- **Objective**: Create clean project structure with TDD focus
- **TDD Approach**:
  - Write test for project structure validation
  - Test that all required directories exist
  - Test that pyproject.toml is valid
- **Acceptance Criteria**:
  - [ ] v2/ directory structure created
  - [ ] pyproject.toml with dependencies: tree-sitter, mcp, pytest
  - [ ] pytest configured with coverage
  - [ ] Pre-commit hooks for quality checks
- **Estimated Hours**: 2-3h
- **Dependencies**: None
- **Risk**: Low
- **Files to Create**:
  - `v2/pyproject.toml`
  - `v2/tests/test_project_structure.py`
  - `v2/.pre-commit-config.yaml`
  - `v2/setup.cfg` (pytest config)

#### **T0.2: Testing Framework**
- **Objective**: Set up comprehensive testing infrastructure
- **TDD Approach**:
  - Write meta-test to verify pytest setup
  - Test fixture loading
  - Test coverage reporting
- **Acceptance Criteria**:
  - [ ] pytest runs successfully
  - [ ] Coverage reporting works
  - [ ] Test fixtures defined
  - [ ] Test categories established (unit/integration/e2e)
- **Estimated Hours**: 2-3h
- **Dependencies**: T0.1
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/conftest.py`
  - `v2/tests/fixtures/`
  - `v2/tests/unit/__init__.py`
  - `v2/tests/integration/__init__.py`
  - `v2/tests/e2e/__init__.py`

#### **T0.3: MCP Hello World**
- **Objective**: Minimal MCP server that responds to ping
- **TDD Approach**:
  - Write test for MCP server initialization
  - Write test for ping response
  - Test JSON-RPC protocol compliance
- **Acceptance Criteria**:
  - [ ] MCP server starts
  - [ ] Responds to initialize request
  - [ ] Responds to ping
  - [ ] Returns capability list
- **Estimated Hours**: 3-4h
- **Dependencies**: T0.2
- **Risk**: Medium (MCP protocol complexity)
- **Files to Create**:
  - `v2/tests/test_mcp_server.py` (FIRST!)
  - `v2/mcp/__init__.py`
  - `v2/mcp/server.py`
  - `v2/mcp/protocol.py`

#### **T0.4: fd + ripgrep Detection**
- **Objective**: Detect and validate fd + ripgrep binaries
- **TDD Approach**:
  - Write test for binary detection
  - Test error when binaries missing
  - Test version compatibility
  - Test subprocess integration
- **Acceptance Criteria**:
  - [ ] Detect fd binary (shutil.which)
  - [ ] Detect ripgrep binary
  - [ ] Raise clear error if missing
  - [ ] Instructions for installation
- **Estimated Hours**: 2h
- **Dependencies**: T0.2
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/unit/test_binary_detection.py` (FIRST!)
  - `v2/utils/binaries.py`

#### **T0.5: CI/CD Pipeline**
- **Objective**: Automated testing on every commit
- **TDD Approach**:
  - Write test to validate workflow YAML
  - Test that all required checks are defined
- **Acceptance Criteria**:
  - [ ] Tests run on push/PR
  - [ ] Coverage reported to Codecov
  - [ ] Type checking with mypy
  - [ ] Linting with ruff
- **Estimated Hours**: 2-3h
- **Dependencies**: T0.2
- **Risk**: Low
- **Files to Create**:
  - `v2/.github/workflows/test.yml`
  - `v2/.github/workflows/quality.yml`
  - `v2/codecov.yml`

#### **T0.6: Development Workflow Documentation**
- **Objective**: Document TDD workflow and conventions
- **TDD Approach**:
  - Write test to validate documentation exists
  - Test that examples run correctly
- **Acceptance Criteria**:
  - [ ] TDD workflow documented
  - [ ] Contribution guidelines
  - [ ] Code style guide
  - [ ] Example TDD cycle
- **Estimated Hours**: 1-2h
- **Dependencies**: T0.1
- **Risk**: Low
- **Files to Create**:
  - `v2/CONTRIBUTING.md`
  - `v2/docs/tdd-workflow.md`
  - `v2/docs/conventions.md`

---

### Phase 1: Core Parser + Search Engine (Week 2-3, 20-40h)

#### **T1.1: Parser Interface Design**
- **Objective**: Define abstract parser interface
- **TDD Approach**:
  - Write interface tests using Protocol
  - Test parse() method signature
  - Test AST node structure
  - Test error handling interface
- **Acceptance Criteria**:
  - [ ] ParserProtocol defined
  - [ ] AST node types defined
  - [ ] Error types defined
  - [ ] 100% test coverage
- **Estimated Hours**: 3-4h
- **Dependencies**: T0.2
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/unit/test_parser_protocol.py` (FIRST!)
  - `v2/core/protocols.py`
  - `v2/core/types.py`
  - `v2/core/exceptions.py`

#### **T1.2: Tree-sitter Wrapper**
- **Objective**: Wrap tree-sitter with clean interface
- **TDD Approach**:
  - Write test for parser initialization
  - Test parsing simple Python file
  - Test parsing errors
  - Test AST traversal
- **Acceptance Criteria**:
  - [ ] Parse Python files
  - [ ] Return standardized AST
  - [ ] Handle syntax errors gracefully
  - [ ] Memory efficient (no leaks)
- **Estimated Hours**: 5-6h
- **Dependencies**: T1.1
- **Risk**: Medium (tree-sitter API complexity)
- **Files to Create**:
  - `v2/tests/unit/test_tree_sitter_wrapper.py` (FIRST!)
  - `v2/core/parser.py`
  - `v2/core/ast_utils.py`

#### **T1.3: Search Engine (fd + ripgrep)**
- **Objective**: Wrap fd and ripgrep for fast search
- **TDD Approach**:
  - Write test for file search (fd)
  - Test content search (ripgrep)
  - Test error handling
  - Test result parsing
  - Mock subprocess for testing
- **Acceptance Criteria**:
  - [ ] find_files() using fd
  - [ ] search_content() using ripgrep
  - [ ] Parse output correctly
  - [ ] Handle binary not found
  - [ ] Performance <100ms for typical searches
- **Estimated Hours**: 4-5h
- **Dependencies**: T0.4
- **Risk**: Medium (subprocess integration)
- **Files to Create**:
  - `v2/tests/unit/test_search_engine.py` (FIRST!)
  - `v2/search.py`
  - `v2/tests/fixtures/search_fixtures/` (sample files for testing)

#### **T1.4: Language Detection**
- **Objective**: Detect language from file extension/content
- **TDD Approach**:
  - Write test for extension mapping
  - Test shebang detection
  - Test content-based detection
  - Test ambiguous cases
- **Acceptance Criteria**:
  - [ ] Detect by extension (.py → Python)
  - [ ] Detect by shebang (#!/usr/bin/env python)
  - [ ] Detect by content patterns
  - [ ] Return confidence score
- **Estimated Hours**: 3-4h
- **Dependencies**: T1.1
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/unit/test_language_detector.py` (FIRST!)
  - `v2/core/detector.py`
  - `v2/core/language_patterns.py`

#### **T1.5: First Three Languages (Python, TypeScript, Java)**
- **Objective**: Implement parsing for 3 core languages
- **TDD Approach**:
  - Write test for each language parser
  - Test common constructs (classes, functions)
  - Test language-specific features
  - Test edge cases
- **Acceptance Criteria**:
  - [ ] Python: classes, functions, imports
  - [ ] TypeScript: interfaces, types, modules
  - [ ] Java: classes, methods, packages
  - [ ] All pass tree-sitter parsing
- **Estimated Hours**: 8-10h
- **Dependencies**: T1.2
- **Risk**: Medium (language-specific quirks)
- **Files to Create**:
  - `v2/tests/unit/test_python_parser.py` (FIRST!)
  - `v2/tests/unit/test_typescript_parser.py` (FIRST!)
  - `v2/tests/unit/test_java_parser.py` (FIRST!)
  - `v2/languages/python_parser.py`
  - `v2/languages/typescript_parser.py`
  - `v2/languages/java_parser.py`

---

### Phase 2: Plugin System Architecture (Week 3-4, 20-40h)

#### **T2.1: Plugin Interface**
- **Objective**: Design extensible plugin system
- **TDD Approach**:
  - Write test for plugin interface
  - Test plugin discovery
  - Test plugin lifecycle
  - Test plugin communication
- **Acceptance Criteria**:
  - [ ] LanguagePlugin protocol
  - [ ] Plugin registration
  - [ ] Plugin configuration
  - [ ] Error isolation
- **Estimated Hours**: 4-5h
- **Dependencies**: T1.1
- **Risk**: Medium (architecture decision)
- **Files to Create**:
  - `v2/tests/unit/test_plugin_interface.py` (FIRST!)
  - `v2/plugins/base.py`
  - `v2/plugins/registry.py`
  - `v2/plugins/loader.py`

#### **T2.2: Element Extraction**
- **Objective**: Extract code elements (classes, functions, etc.)
- **TDD Approach**:
  - Write test for element types
  - Test extraction from AST
  - Test element relationships
  - Test metadata extraction
- **Acceptance Criteria**:
  - [ ] Extract classes with methods
  - [ ] Extract functions with parameters
  - [ ] Extract imports/exports
  - [ ] Maintain source locations
- **Estimated Hours**: 5-6h
- **Dependencies**: T2.1
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/unit/test_element_extraction.py` (FIRST!)
  - `v2/plugins/extractors/base.py`
  - `v2/models/elements.py`
  - `v2/plugins/extractors/utils.py`

#### **T2.3: Python Plugin**
- **Objective**: Complete Python language plugin
- **TDD Approach**:
  - Write comprehensive Python feature tests
  - Test decorators, async, type hints
  - Test Python 3.10+ features
  - Test error recovery
- **Acceptance Criteria**:
  - [ ] All Python constructs supported
  - [ ] Decorators extracted
  - [ ] Type hints preserved
  - [ ] Docstrings captured
- **Estimated Hours**: 5-6h
- **Dependencies**: T2.2, T1.5
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/unit/test_python_plugin.py` (FIRST!)
  - `v2/plugins/languages/python.py`
  - `v2/plugins/languages/python_queries.scm`

#### **T2.4: TypeScript Plugin**
- **Objective**: Complete TypeScript language plugin
- **TDD Approach**:
  - Write TypeScript/JavaScript tests
  - Test interfaces, generics, decorators
  - Test JSX/TSX support
  - Test module systems
- **Acceptance Criteria**:
  - [ ] TypeScript types extracted
  - [ ] Interfaces captured
  - [ ] Generics handled
  - [ ] JSX preserved
- **Estimated Hours**: 5-6h
- **Dependencies**: T2.2, T1.5
- **Risk**: Medium (TS complexity)
- **Files to Create**:
  - `v2/tests/unit/test_typescript_plugin.py` (FIRST!)
  - `v2/plugins/languages/typescript.py`
  - `v2/plugins/languages/typescript_queries.scm`

#### **T2.5: Java Plugin**
- **Objective**: Complete Java language plugin
- **TDD Approach**:
  - Write Java feature tests
  - Test annotations, generics
  - Test inner classes
  - Test lambda expressions
- **Acceptance Criteria**:
  - [ ] Java classes with inheritance
  - [ ] Annotations extracted
  - [ ] Generics preserved
  - [ ] Package structure maintained
- **Estimated Hours**: 5-6h
- **Dependencies**: T2.2, T1.5
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/unit/test_java_plugin.py` (FIRST!)
  - `v2/plugins/languages/java.py`
  - `v2/plugins/languages/java_queries.scm`

---

### Phase 3: Output Formatters (Week 4, 8-12h)

#### **T3.1: TOON Formatter (from v1)**
- **Objective**: Port TOON formatter from v1, simplify
- **TDD Approach**:
  - Write test for TOON format structure
  - Test token counting
  - Test compression ratio
  - Test reversibility
  - Use v1 fixtures as test data
- **Acceptance Criteria**:
  - [ ] 50%+ token reduction
  - [ ] Preserves all information
  - [ ] Parseable format
  - [ ] Consistent output
  - [ ] Pass v1 TOON tests
- **Estimated Hours**: 4-5h
- **Dependencies**: T2.2
- **Risk**: Low (porting existing code)
- **Files to Create**:
  - `v2/tests/unit/test_toon_formatter.py` (FIRST!)
  - `v2/formatters/toon.py` (port from v1)
  - `v2/formatters/toon_types.py`

#### **T3.2: Markdown Formatter (new)**
- **Objective**: Create human-readable Markdown formatter
- **TDD Approach**:
  - Write test for Markdown structure
  - Test heading hierarchy
  - Test code block formatting
  - Test nested structures
- **Acceptance Criteria**:
  - [ ] Classes formatted as sections
  - [ ] Methods as bulleted lists
  - [ ] Code blocks for signatures
  - [ ] Human-readable output
- **Estimated Hours**: 3-4h
- **Dependencies**: T2.2
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/unit/test_markdown_formatter.py` (FIRST!)
  - `v2/formatters/markdown.py`

#### **T3.3: Formatter Registry**
- **Objective**: Registry for TOON + Markdown formatters
- **TDD Approach**:
  - Write test for formatter registration
  - Test format selection
  - Test unknown format error
  - Test format listing
- **Acceptance Criteria**:
  - [ ] Register TOON formatter
  - [ ] Register Markdown formatter
  - [ ] get(format_name) returns formatter
  - [ ] Error on unknown format
  - [ ] List supported formats: ['toon', 'markdown']
- **Estimated Hours**: 1-2h
- **Dependencies**: T3.1, T3.2
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/unit/test_formatter_registry.py` (FIRST!)
  - `v2/formatters/__init__.py`

---

### Phase 4: MCP Integration (Week 4-5, 16-24h)

#### **T4.1: MCP Tool Interface**
- **Objective**: Design MCP tool system
- **TDD Approach**:
  - Write test for tool registration
  - Test tool schema generation
  - Test argument validation
  - Test response formatting
- **Acceptance Criteria**:
  - [ ] Tool base class
  - [ ] Schema auto-generation
  - [ ] Argument validation
  - [ ] Error handling
- **Estimated Hours**: 4-5h
- **Dependencies**: T0.3
- **Risk**: Medium (MCP spec compliance)
- **Files to Create**:
  - `v2/tests/unit/test_mcp_tools.py` (FIRST!)
  - `v2/mcp/tools/base.py`
  - `v2/mcp/tools/registry.py`
  - `v2/mcp/tools/validators.py`

#### **T4.2: Analyze Tool**
- **Objective**: MCP tool for code analysis
- **TDD Approach**:
  - Write test for analyze_code_structure
  - Test different languages
  - Test output formats (TOON/Markdown)
  - Test error cases
- **Acceptance Criteria**:
  - [ ] Analyze single file
  - [ ] Return structured data
  - [ ] Support TOON/Markdown output
  - [ ] Handle errors gracefully
- **Estimated Hours**: 4-5h
- **Dependencies**: T4.1, T2.3-T2.5, T3.3
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/integration/test_analyze_tool.py` (FIRST!)
  - `v2/mcp/tools/analyze.py`

#### **T4.3: Search Tools (fd + ripgrep)**
- **Objective**: MCP tools for file/content search
- **TDD Approach**:
  - Write test for find_files tool
  - Write test for search_content tool
  - Test result formatting
  - Test error handling
  - Mock fd/rg in tests
- **Acceptance Criteria**:
  - [ ] find_files MCP tool (uses fd)
  - [ ] search_content MCP tool (uses ripgrep)
  - [ ] Results formatted for AI consumption
  - [ ] Performance <200ms
- **Estimated Hours**: 4-5h
- **Dependencies**: T4.1, T1.3
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/integration/test_search_tools.py` (FIRST!)
  - `v2/mcp/tools/search.py`

#### **T4.4: Query Tool**
- **Objective**: MCP tool for querying code elements
- **TDD Approach**:
  - Write test for query syntax
  - Test filtering capabilities
  - Test different query types
  - Test performance with large files
- **Acceptance Criteria**:
  - [ ] Query by element type
  - [ ] Filter by attributes
  - [ ] Regex support
  - [ ] Performance <100ms
- **Estimated Hours**: 4-5h
- **Dependencies**: T4.1
- **Risk**: Medium (query language design)
- **Files to Create**:
  - `v2/tests/integration/test_query_tool.py` (FIRST!)
  - `v2/mcp/tools/query.py`
  - `v2/core/query_engine.py`

#### **T4.5: Security Validation**
- **Objective**: Validate all file access and operations
- **TDD Approach**:
  - Write test for path traversal prevention
  - Test file access boundaries
  - Test regex safety (ReDoS)
  - Test resource limits
- **Acceptance Criteria**:
  - [ ] No path traversal
  - [ ] Project boundary enforced
  - [ ] Safe regex patterns
  - [ ] Memory limits
- **Estimated Hours**: 3-4h
- **Dependencies**: T4.1
- **Risk**: High (security critical)
- **Files to Create**:
  - `v2/tests/unit/test_security.py` (FIRST!)
  - `v2/mcp/security/validator.py`
  - `v2/mcp/security/boundaries.py`

---

### Phase 5: CLI + API Interfaces (Week 5, 10-16h)

#### **T5.1: CLI Interface**
- **Objective**: Command-line interface with fd/rg integration
- **TDD Approach**:
  - Write test for CLI commands
  - Test argument parsing
  - Test output formatting
  - Test error handling
  - Mock analyzer for testing
- **Acceptance Criteria**:
  - [ ] `analyze` command
  - [ ] `search-files` command (fd)
  - [ ] `search-content` command (ripgrep)
  - [ ] Format options: --format toon|markdown
  - [ ] Help documentation
  - [ ] Markdown output default for CLI
- **Estimated Hours**: 5-6h
- **Dependencies**: T4.2, T4.3
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/e2e/test_cli.py` (FIRST!)
  - `v2/cli/__init__.py`
  - `v2/cli/main.py`
  - `v2/__main__.py`

#### **T5.2: Python API Interface**
- **Objective**: Clean Python API for programmatic use
- **TDD Approach**:
  - Write test for API initialization
  - Test analyze_file() method
  - Test search methods
  - Test error handling
  - Test usage as Agent Skill
- **Acceptance Criteria**:
  - [ ] TreeSitterAnalyzerAPI class
  - [ ] analyze_file(path, format)
  - [ ] analyze_file_raw(path) → Elements
  - [ ] search_files(pattern, extensions)
  - [ ] search_content(pattern, file_types)
  - [ ] Full type hints
  - [ ] Docstrings for all methods
- **Estimated Hours**: 4-5h
- **Dependencies**: T4.2, T4.3
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/integration/test_api.py` (FIRST!)
  - `v2/api/__init__.py`
  - `v2/api/interface.py`
  - `v2/examples/agent_skill_example.py`

#### **T5.3: API Documentation**
- **Objective**: Complete API reference and examples
- **TDD Approach**:
  - Write test that examples run correctly
  - Test API completeness
  - Test docstring coverage
- **Acceptance Criteria**:
  - [ ] API reference documentation
  - [ ] Usage examples (basic + advanced)
  - [ ] Agent Skill integration example
  - [ ] Performance tips
  - [ ] Migration guide from v1
- **Estimated Hours**: 2-3h
- **Dependencies**: T5.2
- **Risk**: Low
- **Files to Create**:
  - `v2/docs/api-reference.md`
  - `v2/docs/examples.md`
  - `v2/docs/agent-skills.md`
  - `v2/examples/` (runnable examples)

---

### Phase 6: Remaining Languages (Week 6-7, 20-40h)

#### **T6.1: C/C++ Plugins**
- **Objective**: Support C and C++ languages
- **TDD Approach**:
  - Write test for C constructs
  - Write test for C++ features
  - Test preprocessor directives
  - Test templates/macros
- **Acceptance Criteria**:
  - [ ] C functions and structs
  - [ ] C++ classes and templates
  - [ ] Preprocessor handling
  - [ ] Header/source pairing
- **Estimated Hours**: 4-5h
- **Dependencies**: T2.2
- **Risk**: Medium (preprocessor complexity)
- **Files to Create**:
  - `v2/tests/unit/test_c_plugin.py` (FIRST!)
  - `v2/tests/unit/test_cpp_plugin.py` (FIRST!)
  - `v2/plugins/languages/c.py`
  - `v2/plugins/languages/cpp.py`

#### **T6.2: Web Languages (HTML, CSS, JavaScript)**
- **Objective**: Support web development languages
- **TDD Approach**:
  - Write test for HTML structure
  - Write test for CSS rules
  - Write test for JS (share with TS)
  - Test embedded scripts/styles
- **Acceptance Criteria**:
  - [ ] HTML tags and attributes
  - [ ] CSS selectors and rules
  - [ ] JavaScript (via TS plugin)
  - [ ] Mixed content handling
- **Estimated Hours**: 3-4h
- **Dependencies**: T2.2, T2.4
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/unit/test_html_plugin.py` (FIRST!)
  - `v2/tests/unit/test_css_plugin.py` (FIRST!)
  - `v2/plugins/languages/html.py`
  - `v2/plugins/languages/css.py`

#### **T6.3: System Languages (Go, Rust, Kotlin)**
- **Objective**: Support modern system languages
- **TDD Approach**:
  - Write test for each language
  - Test unique features (channels, traits, etc.)
  - Test package systems
  - Test error handling patterns
- **Acceptance Criteria**:
  - [ ] Go functions and interfaces
  - [ ] Rust traits and lifetimes
  - [ ] Kotlin classes and objects
  - [ ] Package management
- **Estimated Hours**: 5-6h
- **Dependencies**: T2.2
- **Risk**: Medium (language complexity)
- **Files to Create**:
  - `v2/tests/unit/test_go_plugin.py` (FIRST!)
  - `v2/tests/unit/test_rust_plugin.py` (FIRST!)
  - `v2/tests/unit/test_kotlin_plugin.py` (FIRST!)
  - `v2/plugins/languages/go.py`
  - `v2/plugins/languages/rust.py`
  - `v2/plugins/languages/kotlin.py`

#### **T6.4: Scripting Languages (PHP, Ruby, C#)**
- **Objective**: Support popular scripting languages
- **TDD Approach**:
  - Write test for dynamic features
  - Test class systems
  - Test unique syntax
  - Test framework patterns
- **Acceptance Criteria**:
  - [ ] PHP classes and traits
  - [ ] Ruby modules and mixins
  - [ ] C# classes and interfaces
  - [ ] Framework detection
- **Estimated Hours**: 4-5h
- **Dependencies**: T2.2
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/unit/test_php_plugin.py` (FIRST!)
  - `v2/tests/unit/test_ruby_plugin.py` (FIRST!)
  - `v2/tests/unit/test_csharp_plugin.py` (FIRST!)
  - `v2/plugins/languages/php.py`
  - `v2/plugins/languages/ruby.py`
  - `v2/plugins/languages/csharp.py`

#### **T6.5: Data Languages (SQL, YAML, Markdown)**
- **Objective**: Support data and markup languages
- **TDD Approach**:
  - Write test for SQL queries
  - Write test for YAML structure
  - Write test for Markdown elements
  - Test nested structures
- **Acceptance Criteria**:
  - [ ] SQL tables and queries
  - [ ] YAML keys and values
  - [ ] Markdown headers and code blocks
  - [ ] Proper nesting
- **Estimated Hours**: 3-4h
- **Dependencies**: T2.2
- **Risk**: Low
- **Files to Create**:
  - `v2/tests/unit/test_sql_plugin.py` (FIRST!)
  - `v2/tests/unit/test_yaml_plugin.py` (FIRST!)
  - `v2/tests/unit/test_markdown_plugin.py` (FIRST!)
  - `v2/plugins/languages/sql.py`
  - `v2/plugins/languages/yaml.py`
  - `v2/plugins/languages/markdown.py`

---

### Phase 7: Optimization & Polish (Week 7-8, 10-20h)

#### **T7.1: Caching Layer**
- **Objective**: Add intelligent caching
- **TDD Approach**:
  - Write test for cache hits/misses
  - Test cache invalidation
  - Test memory limits
  - Test thread safety
- **Acceptance Criteria**:
  - [ ] File-level caching
  - [ ] Query result caching
  - [ ] LRU eviction
  - [ ] Thread-safe
- **Estimated Hours**: 3-4h
- **Dependencies**: T1.2
- **Risk**: Medium (concurrency)
- **Files to Create**:
  - `v2/tests/unit/test_cache.py` (FIRST!)
  - `v2/core/cache.py`
  - `v2/core/cache_keys.py`

#### **T7.2: Performance Benchmarks**
- **Objective**: Establish performance baselines
- **TDD Approach**:
  - Write benchmark framework
  - Test timing accuracy
  - Test memory profiling
  - Test regression detection
- **Acceptance Criteria**:
  - [ ] Parse time <100ms for typical files
  - [ ] Memory <50MB for typical projects
  - [ ] MCP response <200ms
  - [ ] fd search <100ms
  - [ ] ripgrep search <200ms
  - [ ] Automated regression alerts
- **Estimated Hours**: 3-4h
- **Dependencies**: All phases
- **Risk**: Low
- **Files to Create**:
  - `v2/benchmarks/test_performance.py`
  - `v2/benchmarks/fixtures/`
  - `v2/benchmarks/baseline.json`

#### **T7.3: Documentation**
- **Objective**: Complete user and developer documentation
- **TDD Approach**:
  - Write test for code examples
  - Test installation instructions
  - Test MCP integration guide
- **Acceptance Criteria**:
  - [ ] README with quick start
  - [ ] Installation guide (including fd/rg)
  - [ ] CLI reference
  - [ ] API reference
  - [ ] MCP integration guide
  - [ ] Language support matrix
  - [ ] Migration guide from v1
- **Estimated Hours**: 3-4h
- **Dependencies**: All phases
- **Risk**: Low
- **Files to Create**:
  - `v2/README.md`
  - `v2/docs/installation.md`
  - `v2/docs/cli-reference.md`
  - `v2/docs/mcp-integration.md`
  - `v2/docs/languages.md`
  - `v2/docs/migration-v1-to-v2.md`

---

## Testing Strategy

### TDD Workflow (MANDATORY)
1. **RED**: Write failing test FIRST
2. **GREEN**: Write minimal code to pass
3. **REFACTOR**: Improve code quality
4. **VERIFY**: Check coverage >80%

### Test Categories
- **Unit Tests**: Individual functions/methods (60% of tests)
- **Integration Tests**: Component interactions (25% of tests)
- **E2E Tests**: Full workflows (10% of tests)
- **Performance Tests**: Benchmarks (5% of tests)

### Coverage Requirements
- **Overall**: 80% minimum
- **Core modules**: 90% minimum
- **Plugins**: 85% minimum
- **MCP tools**: 90% minimum
- **Search engine**: 85% minimum
- **Formatters**: 90% minimum

---

## Risks & Mitigations

### **Risk: fd/ripgrep Not Installed**
- **Mitigation**: Clear error message with installation instructions, graceful degradation to Python alternatives

### **Risk: MCP Protocol Changes**
- **Mitigation**: Abstract protocol layer, version detection, compatibility mode

### **Risk: Tree-sitter API Breaking Changes**
- **Mitigation**: Pin versions, wrapper abstraction, migration guide

### **Risk: Performance Regression**
- **Mitigation**: Automated benchmarks, performance budget, profiling

### **Risk: Language Support Complexity**
- **Mitigation**: Start with 3 languages, incremental addition, shared patterns

---

## Success Criteria

- [ ] All 17 languages supported with >85% element extraction accuracy
- [ ] MCP server works in Claude Desktop/Cursor/Roo Code
- [ ] TOON format achieves 50%+ token reduction
- [ ] Markdown format human-readable and complete
- [ ] fd file search <100ms for 10K files
- [ ] ripgrep content search <200ms for 1M lines
- [ ] Response time <100ms for typical files
- [ ] Test coverage >80% overall, >90% for core
- [ ] Zero security vulnerabilities
- [ ] Documentation complete and accurate
- [ ] CI/CD pipeline green
- [ ] Performance benchmarks passing
- [ ] CLI + API + MCP all functional
- [ ] Can replace v1.9.17.1 in production

---

## Weekly Milestones

### Week 1 (10-20h)
- [ ] Foundation complete (Phase 0)
- [ ] MCP responds to ping
- [ ] fd + ripgrep detection working
- [ ] CI/CD running

### Week 2-3 (20-40h)
- [ ] Core parser working (Phase 1)
- [ ] 3 languages parsing
- [ ] Search engine (fd + ripgrep) working
- [ ] Language detection works

### Week 3-4 (20-40h)
- [ ] Plugin system complete (Phase 2)
- [ ] 3 full language plugins
- [ ] Element extraction working

### Week 4 (8-12h)
- [ ] TOON + Markdown formatters complete (Phase 3)
- [ ] 50% token reduction achieved
- [ ] Human-readable Markdown output

### Week 4-5 (16-24h)
- [ ] MCP tools working (Phase 4)
- [ ] Security validated
- [ ] Search tools integrated
- [ ] Integration tested

### Week 5 (10-16h)
- [ ] CLI interface complete (Phase 5)
- [ ] API interface complete
- [ ] Documentation for both

### Week 6-7 (20-40h)
- [ ] All 17 languages (Phase 6)
- [ ] Full language coverage

### Week 7-8 (10-20h)
- [ ] Optimization complete (Phase 7)
- [ ] Documentation ready
- [ ] Production release candidate

---

## Notes

**Remember the TDD Mantra**:
> "No production code without a failing test first!"

**Daily Workflow**:
1. Pick task from current phase
2. Write failing test
3. Implement to pass test
4. Refactor if needed
5. Verify coverage
6. Commit with descriptive message

**Test File Naming**:
- Unit: `test_<module>_unit.py`
- Integration: `test_<feature>_integration.py`
- E2E: `test_<workflow>_e2e.py`

**Output Format Priority**:
- MCP tools: Default to TOON (token-optimized for AI)
- CLI: Default to Markdown (human-readable)
- API: Caller's choice

**Search Integration**:
- Always use fd/ripgrep when available
- Provide clear installation instructions if missing
- Mock in tests for CI/CD without binaries

---

This comprehensive task breakdown provides a clear TDD-first roadmap for the v2 rewrite, with specific emphasis on:
- ✅ fd + ripgrep integration for fast search
- ✅ TOON + Markdown output formats (no JSON)
- ✅ CLI + API + MCP interfaces
- ✅ Test requirements before implementation

Each task includes exactly what tests to write first, ensuring true TDD methodology throughout the 6-8 week development cycle.
