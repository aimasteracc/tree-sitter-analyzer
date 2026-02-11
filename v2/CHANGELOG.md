# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `extract_code_section` Python API (Pain point #9): Extract code by line range via `TreeSitterAnalyzerAPI.extract_code_section()` or standalone `extract_code_section()` function; supports TOON and Markdown output with encoding detection
- AI autonomous development role system (7 roles for continuous development)
- Project roadmap (ROADMAP.md)
- PR template for GitHub
- Release workflow (GitHub Actions)
- Comprehensive CHANGELOG
- CLI unit tests (22 tests, coverage 0% -> 84%)
- Output validator tests (10 tests, coverage 0% -> 100%)
- Security validator edge case tests (coverage 68% -> 77%)
- Encoding detector edge case tests (coverage 75% -> 82%)
- Scale tool extended tests (coverage 78% -> 95%)
- Runnable examples (`examples/basic_analysis.py`, `examples/format_comparison.py`)

### Changed
- Updated README with accurate project stats, badges, and code examples
- Fixed CI/CD to install language packages correctly (`--extra languages`)
- Fixed flaky performance tests (relaxed threshold 200ms -> 500ms)

### Stats
- Tests: 861 -> 903 passing (4 skipped)
- Coverage: 88% -> 91%
- Lint: 0 errors
- Types: 0 errors

## [2.0.0-alpha.1] - 2026-02-10

### Added

#### Core
- Complete v2 rewrite with clean architecture
- Tree-sitter based parser for Python, Java, TypeScript/JavaScript
- Language auto-detection from file extension and content
- Token optimizer for reducing AI context size
- Type system with strict mypy enforcement

#### Analysis
- Code structure analysis (classes, methods, fields, imports)
- Complexity metrics (cyclomatic complexity)
- Code graph builder (call graphs, import graphs)
- Cross-file dependency analysis
- Incremental graph updates
- Symbol table and cross-reference resolution

#### Output Formats
- TOON (Token-Optimized Output Notation) - 50-70% token reduction
- Markdown formatter for human-readable output
- Summary formatter for quick overviews
- Formatter registry with pluggable architecture

#### MCP Server
- 8 MCP tools for AI assistant integration:
  - `check_code_scale` - File metrics and complexity
  - `analyze_code_structure` - Detailed structure table
  - `extract_code_section` - Partial file reading
  - `query_code` - Query methods/classes with filters
  - `search_content` - Ripgrep-powered content search
  - `list_files` - fd-powered file discovery
  - `find_and_grep` - Two-stage search
  - `build_code_graph` - Dependency graph analysis

#### Search
- fd integration for fast file search
- ripgrep integration for fast content search
- Glob pattern support
- Case-sensitive/insensitive search modes

#### CLI
- `analyze` command with format options
- `search-files` command with fd backend
- `search-content` command with ripgrep backend
- Short alias `tsa` for daily use

#### API
- Python API interface (`TreeSitterAnalyzerAPI`)
- Programmatic access to all analysis features

#### Security
- Path traversal prevention
- Project root boundary enforcement
- Regex safety validation (ReDoS prevention)

#### Infrastructure
- 839 tests (unit + integration)
- 88% code coverage
- CI/CD with GitHub Actions (3 OS x 3 Python versions)
- Codecov integration
- Strict mypy type checking (0 errors)
- Ruff linting and formatting (0 errors)
- Contributing guide
- Issue templates (bug report, feature request)

### Architecture Decisions
- Plugin-based language system (one parser per language)
- Unified formatter registry
- fd/ripgrep for search (10-20x faster than pure Python)
- TOON format as primary AI output
- NetworkX for graph analysis
- No over-engineering: max 300 lines per file

### Known Limitations
- Only 3 languages supported (Python, Java, TypeScript/JS) - more planned
- CLI has 0% test coverage (planned for alpha.2)
- MCP server not yet published to PyPI
- No plugin discovery system yet

[Unreleased]: https://github.com/aimasteracc/tree-sitter-analyzer/compare/v2.0.0-alpha.1...HEAD
[2.0.0-alpha.1]: https://github.com/aimasteracc/tree-sitter-analyzer/releases/tag/v2.0.0-alpha.1
