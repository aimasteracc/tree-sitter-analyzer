# Technology Stack & Build System

## Current Version & Statistics

- **Version**: v1.6.1 (Latest stable release)
- **Test Suite**: 1,893 tests with 71.48% code coverage
- **MCP Tools**: 12 specialized tools for AI integration
- **Build Status**: Beta (Development Status :: 4 - Beta)

## Build System & Package Management

- **Primary**: `uv` (fast Python package manager) - used for all development and user installations
- **Build Backend**: `hatchling` (modern Python build system)
- **Package Distribution**: PyPI with multiple installation options

## Core Technology Stack

### Language & Runtime
- **Python**: 3.10+ (required minimum, supports 3.10-3.13)
- **Tree-sitter**: v0.24.0 (core parsing engine)
- **Async Support**: `asyncio` for MCP server operations

### Key Dependencies
- **MCP**: v1.12.3+ (Model Context Protocol for AI integration)
- **Character Detection**: `chardet` v5.0.0+ (encoding detection)
- **Caching**: `cachetools` v5.0.0+ (performance optimization)

### Language Parsers
- `tree-sitter-java` v0.23.5+
- `tree-sitter-python` v0.23.6+
- `tree-sitter-javascript` v0.23.1+
- `tree-sitter-typescript` v0.20.0+
- `tree-sitter-cpp` v0.23.4+
- Additional parsers for C, Rust, Go

## Development Tools

### Code Quality
- **Formatter**: Black (88 character line length)
- **Linter**: Ruff (fast Python linter)
- **Type Checker**: MyPy (with strict configuration)
- **Import Sorting**: isort (Black-compatible)

### Testing Framework
- **Test Runner**: pytest v8.4.1+
- **Coverage**: pytest-cov v4.0.0+
- **Async Testing**: pytest-asyncio v1.1.0+
- **Mocking**: pytest-mock v3.14.1+

### Pre-commit Hooks
- **Setup**: `pre-commit` v3.0.0+
- **Hooks**: Black, Ruff, MyPy integration

## Common Commands

### Development Setup
```bash
# Clone and setup development environment
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

### Testing
```bash
# Run all tests (1,893 tests)
uv run pytest tests/ -v

# Run with coverage report (71.48% coverage)
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

# Run specific test categories
uv run pytest tests/test_mcp_server_initialization.py -v
uv run pytest tests/test_formatters_comprehensive.py -v
```

### Code Quality Checks
```bash
# Format code
uv run black .

# Check formatting
uv run black --check .

# Lint code
uv run ruff check .

# Auto-fix safe issues
uv run ruff check . --fix

# Type checking
uv run mypy .

# Run all quality checks
uv run python check_quality.py

# Auto-fix and check (recommended for new contributors)
uv run python check_quality.py --new-code-only --fix
```

### Building & Distribution
```bash
# Build package
uv build

# Upload to PyPI (maintainers only)
uv run python upload_to_pypi.py
```

### CLI Usage
```bash
# Basic analysis (large file demo)
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# Structure analysis (66 methods clearly displayed)
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# Partial reading (extract specific code section)
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105

# Quiet mode
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --quiet
```

### MCP Server
```bash
# Start MCP server (development)
uv run python -m tree_sitter_analyzer.mcp.server

# Start with project root
TREE_SITTER_PROJECT_ROOT=/path/to/project uv run python -m tree_sitter_analyzer.mcp.server
```

## Installation Options

### End Users
```bash
# Basic installation
uv add tree-sitter-analyzer

# Popular languages (Java, Python, JS, TS)
uv add "tree-sitter-analyzer[popular]"

# With MCP server support
uv add "tree-sitter-analyzer[mcp]"

# Full installation
uv add "tree-sitter-analyzer[all,mcp]"
```

## MCP Tools Architecture

### Available MCP Tools (12 tools)
- `analyze_code_structure` - Code structure analysis with line positioning
- `check_code_scale` - File size and complexity metrics
- `extract_code_section` - Precise line-range code extraction
- `query_code` - Tree-sitter query execution
- `list_files` - Advanced file listing with fd integration
- `search_content` - Content search with ripgrep integration
- `find_and_grep` - Two-stage file finding and content search
- `read_partial_tool` - Partial file reading
- `table_format_tool` - Table formatting for analysis results
- `universal_analyze_tool` - Universal code analysis
- `set_project_path` - Project root configuration
- `base_tool` - Base tool functionality

## Architecture Notes

- **Plugin System**: Dynamic plugin architecture for language support
- **Caching**: Multi-level caching for parsers and analysis results
- **Security**: Project boundary validation and input sanitization
- **Performance**: Optimized for large file handling with minimal memory usage
- **Cross-platform**: Windows, macOS, Linux compatibility
- **AI Integration**: Native MCP protocol support for seamless AI assistant integration
