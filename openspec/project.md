# Project Context

## Purpose
**Tree-sitter Analyzer** is an enterprise-grade code analysis tool designed for the AI era. It provides deep AI integration, powerful file search capabilities, intelligent code analysis, and multi-language support to enable AI assistants to understand and analyze codebases of any size, breaking through token limits.

## Tech Stack
- **Python 3.10+** - Core runtime and API
- **Tree-sitter** - High-performance syntax parsing engine
- **MCP (Model Context Protocol)** - AI tool integration protocol
- **asyncio** - Asynchronous programming support
- **pathlib** - Modern path handling
- **fd + ripgrep** - High-performance file discovery and content search
- **cachetools** - Intelligent caching system
- **chardet** - Encoding detection
- **pydantic** - Data validation and settings
- **pytest** - Testing framework

## Project Conventions

### Code Style
- **Python 3.10+** - Follow PEP 8, use type hints extensively
- **Black** - Code formatting (line-length 88)
- **Ruff** - Linting and code quality
- **isort** - Import organization
- **mypy** - Static type checking
- **Naming**: Use descriptive names, snake_case for functions/variables, PascalCase for classes

### Architecture Patterns
- **Plugin-based Architecture** - Extensible language support through plugins
- **Unified Element System** - Single element list management for all code elements
- **MCP Server Pattern** - Standardized AI tool integration
- **Async/Await** - Non-blocking operations for file I/O and network
- **Factory Pattern** - Language detector and plugin manager
- **Command Pattern** - CLI interface design

### Testing Strategy
- **1893 comprehensive tests** with 71.48% coverage
- **pytest** with asyncio support
- **Unit tests** - Individual components
- **Integration tests** - MCP server and tool integration
- **Cross-platform testing** - Windows, macOS, Linux
- **Quality gates** - All tests must pass before merge

### Git Workflow
- **GitFlow strategy** - main/development/feature branches
- **Conventional commits** - Structured commit messages
- **Pre-commit hooks** - Quality checks before commit
- **Release automation** - Automated version management and PyPI publishing

## Domain Context
**Code Analysis and AI Integration**
- **Tree-sitter parsing** - Understand AST structures for multiple languages
- **Language plugins** - Java (1103 lines), Python (584 lines), JavaScript (1445 lines)
- **MCP tools** - check_code_scale, analyze_code_structure, extract_code_section, query_code, list_files, search_content, find_and_grep
- **SMART Workflow** - Set, Map, Analyze, Retrieve, Trace methodology for AI assistants
- **Element types** - classes, methods, fields, imports, packages with unified management
- **Query system** - Tree-sitter queries with filtering capabilities

## Important Constraints
- **Python 3.10+ required** - Modern Python features and type hints
- **Project boundary security** - All file operations must respect project root
- **Cross-platform compatibility** - Support Windows, macOS, Linux
- **Performance requirements** - Handle large files (1000+ lines) efficiently
- **Memory constraints** - Smart caching to avoid excessive memory usage
- **Token limit optimization** - Enable AI to process large codebases

## External Dependencies
- **Tree-sitter language parsers** - tree-sitter-java, tree-sitter-python, tree-sitter-javascript, etc.
- **fd (sharkdp/fd)** - Fast file discovery tool
- **ripgrep (BurntSushi/ripgrep)** - Fast content search tool
- **MCP protocol** - Model Context Protocol for AI tool integration
- **PyPI** - Package distribution and dependency management
- **GitHub Actions** - CI/CD pipeline for testing and releases
