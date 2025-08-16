# Project Structure & Organization

## Root Directory Layout

```
tree-sitter-analyzer/
├── .git/                           # Git repository
├── .github/                        # GitHub workflows and templates
├── .kiro/                          # Kiro IDE configuration and steering
├── tree_sitter_analyzer/          # Main package source code
├── tests/                          # Comprehensive test suite
├── examples/                       # Sample files for testing and demos
├── docs/                           # Documentation
├── dist/                           # Build artifacts (generated)
├── .venv/                          # Virtual environment (generated)
└── Configuration files (see below)
```

## Core Package Structure (`tree_sitter_analyzer/`)

```
tree_sitter_analyzer/
├── __init__.py                     # Package initialization
├── __main__.py                     # Module entry point
├── api.py                          # Public API interface
├── cli_main.py                     # CLI entry point
├── models.py                       # Data models and types
├── utils.py                        # Utility functions
├── exceptions.py                   # Custom exception classes
├── encoding_utils.py               # File encoding utilities
├── file_handler.py                 # File operations
├── language_detector.py            # Language detection logic
├── language_loader.py              # Tree-sitter language loading
├── output_manager.py               # Output formatting and display
├── project_detector.py             # Project root detection
├── query_loader.py                 # Query management
├── table_formatter.py              # Table output formatting
├── core/                           # Core analysis engine
├── cli/                            # CLI command implementations
├── formatters/                     # Output formatters
├── interfaces/                     # Interface adapters (CLI, MCP)
├── languages/                      # Language-specific plugins
├── mcp/                            # MCP server implementation
├── plugins/                        # Plugin system
├── queries/                        # Tree-sitter queries
├── security/                       # Security validation
└── validation/                     # Input validation
```

## Key Subdirectories

### `core/` - Analysis Engine
- `analysis_engine.py` - Main analysis orchestration
- `query_engine.py` - Query execution engine
- Core business logic for code analysis

### `cli/` - Command Line Interface
- `commands.py` - CLI command implementations
- `parser.py` - Argument parsing
- Command-line specific logic

### `languages/` - Language Plugins
- `java_plugin.py` - Java language support
- `python_plugin.py` - Python language support
- `javascript_plugin.py` - JavaScript language support
- Language-specific analysis logic

### `mcp/` - Model Context Protocol
- `server.py` - MCP server implementation
- `tools.py` - MCP tool definitions
- AI assistant integration

### `security/` - Security Framework
- `boundary_manager.py` - Project boundary validation
- `validator.py` - Input validation and sanitization
- `regex_checker.py` - Safe regex pattern validation

## Test Structure (`tests/`)

```
tests/
├── conftest.py                     # Pytest configuration and fixtures
├── test_*.py                       # Unit tests (main level)
├── test_core/                      # Core engine tests
├── test_interfaces/                # Interface adapter tests
├── test_languages/                 # Language plugin tests
├── test_mcp/                       # MCP server tests
├── test_plugins/                   # Plugin system tests
├── test_security/                  # Security framework tests
└── __pycache__/                    # Compiled test files (generated)
```

## Configuration Files

### Package Configuration
- `pyproject.toml` - Main package configuration, dependencies, build settings
- `uv.lock` - Dependency lock file
- `pytest.ini` - Test configuration

### Code Quality
- `.pre-commit-config.yaml` - Pre-commit hooks configuration
- Quality tools configured in `pyproject.toml`

### Documentation
- `README.md` - Main documentation (English)
- `README_zh.md` - Chinese documentation
- `README_ja.md` - Japanese documentation
- `CONTRIBUTING.md` - Contribution guidelines
- `CODE_STYLE_GUIDE.md` - Code style standards
- `CHANGELOG.md` - Version history

### Deployment & Release
- `DEPLOYMENT_GUIDE.md` - Deployment instructions
- `PYPI_RELEASE_GUIDE.md` - PyPI release process
- `upload_to_pypi.py` - Release automation script
- `build_standalone.py` - Standalone build script

## Examples Directory (`examples/`)

- `BigService.java` - Large Java service class (1419 lines, 66 methods) - main demo file
- `Sample.java` - Smaller Java example (178 lines, 8 classes)
- `MultiClass.java` - Multi-class Java example
- `sample.py` - Python example
- `*.json` - Analysis result examples
- Demo and testing files for various languages

## Naming Conventions

### Files and Directories
- **Snake case** for Python files: `analysis_engine.py`
- **Lowercase** for directories: `tree_sitter_analyzer/`
- **Descriptive names** that indicate purpose

### Code Organization
- **One class per file** when possible
- **Logical grouping** by functionality
- **Clear separation** between interfaces, core logic, and plugins

### Import Structure
```python
# Standard library imports
import os
from pathlib import Path

# Third-party imports
import tree_sitter
from typing import Dict, List

# Local imports
from .models import AnalysisResult
from .utils import log_info
```

## Plugin Architecture

### Language Plugins
- Each language has its own plugin file
- Plugins implement common interface
- Dynamic loading and registration
- Extensible for new languages

### Entry Points
- Defined in `pyproject.toml`
- Automatic plugin discovery
- Support for external plugins

## Security Boundaries

### Project Root Detection
- Automatic detection from `.git`, `pyproject.toml`, etc.
- Configurable via CLI `--project-root`
- Environment variable `TREE_SITTER_PROJECT_ROOT`

### File Access Control
- All file operations validated against project boundaries
- Path traversal attack prevention
- Symlink safety checks

## Build Artifacts (Generated)

### Distribution
- `dist/` - Wheel and source distributions
- Built via `uv build`

### Cache Directories
- `.mypy_cache/` - MyPy type checking cache
- `.pytest_cache/` - Pytest execution cache
- `.ruff_cache/` - Ruff linting cache
- `__pycache__/` - Python bytecode cache

## Development Workflow

1. **Setup**: `uv sync --extra all --extra mcp`
2. **Code**: Follow structure and naming conventions
3. **Test**: Add tests in appropriate `test_*/` directories
4. **Quality**: Run `uv run python check_quality.py --new-code-only --fix`
5. **Commit**: Pre-commit hooks ensure quality
