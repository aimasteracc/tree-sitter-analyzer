# Code Style Guide for Tree-sitter Analyzer

This document outlines the coding standards and best practices for contributing to the Tree-sitter Analyzer project.

## 🎯 Overview

We maintain high code quality standards to ensure:
- **Consistency** across the codebase
- **Readability** for all contributors
- **Maintainability** for long-term development
- **Reliability** through comprehensive testing

## 🐍 Python Code Style

### PEP 8 Compliance

We follow [PEP 8](https://pep8.org/) with these specific configurations:

```python
# Line length: 88 characters (Black default)
# Indentation: 4 spaces
# Quote style: Double quotes preferred
```

### Code Formatting

We use **Black** for automatic code formatting:

```bash
# Format all code
uv run black .

# Check formatting
uv run black --check .
```

### Linting

We use **Ruff** for fast linting:

```bash
# Lint code
uv run ruff check .

# Auto-fix safe issues
uv run ruff check . --fix
```

### Import Organization

We use **isort** with Black compatibility:

```python
# Standard library imports
import os
import sys
from pathlib import Path

# Third-party imports
import tree_sitter
from typing import Dict, List, Optional

# Local imports
from .models import AnalysisResult
from .utils import log_info
```

## 📝 Type Hints

### Required Type Hints

All public functions and methods must have type hints:

```python
def analyze_file(file_path: str, language: Optional[str] = None) -> AnalysisResult:
    """Analyze a code file and return results."""
    pass

class JavaElementExtractor:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

    def extract_functions(self, tree: Tree, source_code: str) -> List[Function]:
        return []
```

### Type Hint Guidelines

- Use `Optional[T]` for nullable values
- Use `Union[T, U]` sparingly; prefer specific types
- Use `List[T]`, `Dict[K, V]` for containers
- Use `Callable[[Args], Return]` for function types
- Import types from `typing` module

## 📚 Documentation

### Docstring Style

We use Google-style docstrings:

```python
def extract_functions(source_code: str, language: str) -> List[Function]:
    """Extract function definitions from source code.
    
    Args:
        source_code: The source code to analyze
        language: Programming language (e.g., 'python', 'java')
    
    Returns:
        List of Function objects found in the code
    
    Raises:
        AnalysisError: If parsing fails
        ValueError: If language is not supported
    
    Example:
        >>> functions = extract_functions("def hello(): pass", "python")
        >>> len(functions)
        1
    """
    pass
```

### Documentation Requirements

- All public classes, functions, and methods must have docstrings
- Include type information in docstrings when helpful
- Provide examples for complex functions
- Document exceptions that may be raised

## 🧪 Testing Standards

### Test Structure

```python
class TestJavaPlugin:
    """Test suite for Java plugin analysis."""

    async def test_analyze_java_file_success(self):
        """Test successful analysis of Java file using new plugin system."""
        # Arrange
        from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine
        engine = get_analysis_engine()
        file_path = "examples/Sample.java"

        # Act
        result = await engine.analyze_file(file_path)

        # Assert
        assert result is not None
        assert result.language == "java"
        assert len(result.classes) > 0
```

### Test Coverage

- Aim for 90%+ test coverage
- Test both success and failure cases
- Include edge cases and error conditions
- Use meaningful test names that describe the scenario

### Test Organization

```
tests/
├── test_core/           # Core functionality tests
├── test_languages/      # Language-specific tests
├── test_mcp/           # MCP server tests
├── test_cli/           # CLI tests
└── conftest.py         # Shared test fixtures
```

## 🏗️ Architecture Guidelines

### Class Design

```python
class LanguagePlugin:
    """Base class for language-specific plugins."""
    
    def __init__(self) -> None:
        self._language_name = self.get_language_name()
    
    @abstractmethod
    def get_language_name(self) -> str:
        """Return the language name."""
        pass
    
    @abstractmethod
    def create_extractor(self) -> ElementExtractor:
        """Create an element extractor for this language."""
        pass
```

### Error Handling

```python
# Use specific exception types
class AnalysisError(Exception):
    """Raised when code analysis fails."""
    pass

# Provide helpful error messages
def parse_file(file_path: str) -> Tree:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        raise AnalysisError(f"File not found: {file_path}")
    except UnicodeDecodeError as e:
        raise AnalysisError(f"Encoding error in {file_path}: {e}")
```

### Logging

```python
from .utils import log_info, log_warning, log_error

def analyze_code(content: str) -> AnalysisResult:
    log_info(f"Starting analysis of {len(content)} characters")
    
    try:
        result = perform_analysis(content)
        log_info(f"Analysis completed: {len(result.elements)} elements found")
        return result
    except Exception as e:
        log_error(f"Analysis failed: {e}")
        raise
```

## 🔧 Performance Guidelines

### Memory Management

- Use generators for large data processing
- Clear caches when appropriate
- Avoid keeping large objects in memory unnecessarily

### Caching

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def get_language_parser(language: str) -> Language:
    """Get cached language parser."""
    return Language(library_path, language)
```

## 🚫 Common Anti-patterns to Avoid

### Don't Do This

```python
# Avoid bare except clauses
try:
    risky_operation()
except:  # ❌ Too broad
    pass

# Avoid mutable default arguments
def process_items(items=[]):  # ❌ Dangerous
    items.append("new")
    return items

# Avoid string concatenation in loops
result = ""
for item in items:
    result += str(item)  # ❌ Inefficient
```

### Do This Instead

```python
# Use specific exception handling
try:
    risky_operation()
except SpecificError as e:  # ✅ Specific
    log_error(f"Operation failed: {e}")

# Use None as default
def process_items(items=None):  # ✅ Safe
    if items is None:
        items = []
    items.append("new")
    return items

# Use join for string concatenation
result = "".join(str(item) for item in items)  # ✅ Efficient
```

## 🔍 Code Review Checklist

Before submitting code, ensure:

- [ ] Code follows PEP 8 and passes Black formatting
- [ ] All functions have type hints and docstrings
- [ ] Tests are included and pass
- [ ] No security vulnerabilities (Bandit check)
- [ ] Performance considerations addressed
- [ ] Error handling is appropriate
- [ ] Logging is meaningful and not excessive
- [ ] Documentation is updated if needed

## 🛠️ Development Tools

### Required Tools

```bash
# Install development dependencies
uv sync --extra all --extra mcp

# Install pre-commit hooks
uv run pre-commit install
```

### Quality Check Script

```bash
# Run comprehensive quality checks
python check_quality.py

# Run with auto-fix
python check_quality.py --fix

# Run new code only (faster)
python check_quality.py --new-code-only
```

## 📋 Commit Message Format

Use conventional commit format:

```
type(scope): description

[optional body]

[optional footer]
```

Examples:
```
feat(mcp): add new analyze_code_universal tool
fix(cli): handle missing file gracefully
docs(readme): update installation instructions
test(core): add edge case tests for parser
refactor(plugins): simplify plugin registration
```

## 🎯 Summary

Following these guidelines ensures:
- Consistent, readable code
- Reliable functionality through testing
- Easy maintenance and collaboration
- High-quality user experience

For questions about code style, refer to this guide or ask in GitHub discussions.
