# Code Conventions

This document defines coding conventions for tree-sitter-analyzer v2.

## File Organization

### Maximum File Size

- **Hard limit**: 300 lines
- **Soft target**: 100-200 lines
- **Action**: If file exceeds 300 lines, split into modules

### Directory Structure

```
tree_sitter_analyzer_v2/
├── core/           # Core functionality (parser, analyzer, cache)
├── plugins/        # Plugin system
│   └── languages/  # Language-specific plugins
├── formatters/     # Output formatters (TOON, Markdown)
├── mcp/           # MCP server and tools
│   └── tools/     # Individual MCP tool implementations
├── cli/           # CLI interface
├── api/           # Python API
├── models/        # Data models (dataclasses)
└── utils/         # Utilities (binaries, files, security)
```

### File Naming

- **Modules**: `lowercase_with_underscores.py`
- **Classes**: `PascalCase` (e.g., `TreeParser`)
- **Functions**: `lowercase_with_underscores` (e.g., `parse_file`)
- **Constants**: `UPPER_CASE_WITH_UNDERSCORES`

## Import Organization

Imports should be organized in this order:

```python
"""Module docstring."""

# 1. Future imports (if needed)
from __future__ import annotations

# 2. Standard library imports
import os
import sys
from pathlib import Path
from typing import Any, Optional

# 3. Third-party imports
import pytest
import tree_sitter

# 4. Local imports - absolute
from tree_sitter_analyzer_v2.core import Parser
from tree_sitter_analyzer_v2.models import Element

# NO relative imports except within same package
# from .utils import helper  # Only if within same direct package
```

## Type Hints

### Required for All Functions

```python
# Good
def parse_file(file_path: str, language: str) -> ParseResult:
    """Parse a file."""
    ...

# Bad - no type hints
def parse_file(file_path, language):
    """Parse a file."""
    ...
```

### Complex Types

```python
from typing import Optional, Union, List, Dict, Any
from pathlib import Path

# Use built-in generic types (Python 3.10+)
def process_files(paths: list[str]) -> dict[str, Any]:
    """Process multiple files."""
    ...

# Optional for values that can be None
def get_config(key: str) -> Optional[str]:
    """Get configuration value."""
    ...

# Union for multiple types (prefer specific types over Any)
def handle_input(value: Union[str, int, Path]) -> str:
    """Handle different input types."""
    ...
```

### Avoid `Any` When Possible

```python
# Bad - loses type information
def process(data: Any) -> Any:
    ...

# Good - specific types
def process(data: dict[str, str]) -> list[Element]:
    ...
```

## Docstrings

### Required For

- All public classes
- All public methods/functions
- Complex private methods

### Style: Google Format

```python
def analyze_file(
    file_path: str,
    language: str,
    max_size: int = 10_000_000
) -> AnalysisResult:
    """
    Analyze a source code file.

    This function parses the file using tree-sitter and extracts
    code elements (classes, functions, imports, etc.).

    Args:
        file_path: Path to the file to analyze
        language: Programming language identifier (e.g., 'python')
        max_size: Maximum file size in bytes (default: 10MB)

    Returns:
        AnalysisResult containing extracted elements and metadata

    Raises:
        FileNotFoundError: If file does not exist
        FileTooLargeError: If file exceeds max_size
        UnsupportedLanguageError: If language is not supported

    Example:
        >>> result = analyze_file('example.py', 'python')
        >>> print(result.classes[0].name)
        'MyClass'
    """
    ...
```

### Class Docstrings

```python
class Parser:
    """
    Tree-sitter parser wrapper for multi-language code analysis.

    This class provides a unified interface to tree-sitter parsers
    for different programming languages. It handles:
    - Parser initialization and caching
    - Syntax tree generation
    - Error detection and reporting

    Attributes:
        max_file_size: Maximum file size to parse in bytes
        cache_enabled: Whether to cache parse results

    Example:
        >>> parser = Parser(max_file_size=5_000_000)
        >>> result = parser.parse('print("hello")', 'python')
        >>> result.has_errors
        False
    """

    def __init__(self, max_file_size: int = 10_000_000) -> None:
        """
        Initialize parser.

        Args:
            max_file_size: Maximum file size in bytes
        """
        ...
```

## Error Handling

### Use Specific Exceptions

```python
# Good - specific exception classes
class UnsupportedLanguageError(Exception):
    """Raised when language is not supported."""
    pass

class FileTooLargeError(Exception):
    """Raised when file exceeds size limit."""
    pass

# Use them
def parse(code: str, language: str) -> Result:
    if language not in SUPPORTED_LANGUAGES:
        raise UnsupportedLanguageError(
            f"Language '{language}' is not supported. "
            f"Supported languages: {', '.join(SUPPORTED_LANGUAGES)}"
        )
```

### Always Provide Context

```python
# Good - helpful error message
if not file_path.exists():
    raise FileNotFoundError(
        f"File not found: {file_path}\n"
        f"Current directory: {Path.cwd()}"
    )

# Bad - generic error
if not file_path.exists():
    raise FileNotFoundError(str(file_path))
```

## Function Design

### Keep Functions Small

```python
# Good - focused function
def validate_file_size(file_path: Path, max_size: int) -> None:
    """Validate that file doesn't exceed size limit."""
    size = file_path.stat().st_size
    if size > max_size:
        raise FileTooLargeError(
            f"File {file_path} is {size} bytes, exceeds limit of {max_size}"
        )

# Bad - too many responsibilities
def process_file(file_path: Path, max_size: int, language: str, format: str):
    """Do everything."""
    # Validate size
    size = file_path.stat().st_size
    if size > max_size:
        raise FileTooLargeError(...)

    # Parse file
    code = file_path.read_text()
    tree = parse(code, language)

    # Extract elements
    elements = extract_elements(tree)

    # Format output
    formatted = format_output(elements, format)

    return formatted
```

### Single Responsibility Principle

Each function should do ONE thing well.

```python
# Good - separate concerns
def load_file(file_path: Path) -> str:
    """Load file contents."""
    return file_path.read_text(encoding='utf-8')

def parse_code(code: str, language: str) -> Tree:
    """Parse code to AST."""
    ...

def extract_elements(tree: Tree) -> list[Element]:
    """Extract elements from AST."""
    ...

# Use them together
code = load_file(file_path)
tree = parse_code(code, language)
elements = extract_elements(tree)
```

## Class Design

### Use Dataclasses for Data

```python
from dataclasses import dataclass

@dataclass
class ParseResult:
    """Result of parsing operation."""
    tree: Tree
    has_errors: bool
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

### Dependency Injection

```python
# Good - dependencies injected
class Analyzer:
    def __init__(
        self,
        parser: Parser,
        cache: Cache,
        formatter: Formatter
    ) -> None:
        self.parser = parser
        self.cache = cache
        self.formatter = formatter

# Bad - creates dependencies internally
class Analyzer:
    def __init__(self):
        self.parser = Parser()  # Hard to test
        self.cache = Cache()    # Hard to mock
```

### Composition Over Inheritance

```python
# Good - composition
class FileAnalyzer:
    def __init__(self, parser: Parser, extractor: ElementExtractor):
        self.parser = parser
        self.extractor = extractor

# Less ideal - deep inheritance
class FileAnalyzer(BaseAnalyzer, Cacheable, Loggable):
    ...
```

## Naming Conventions

### Be Descriptive

```python
# Good - clear intent
def extract_public_methods(class_node: Node) -> list[Method]:
    """Extract public methods from a class node."""
    ...

# Bad - abbreviations
def ext_pub_meth(cn: Node) -> list:
    ...
```

### Boolean Variables

```python
# Good - clear boolean intent
is_valid: bool
has_errors: bool
can_parse: bool
should_cache: bool

# Bad - ambiguous
valid: bool  # valid what? is it valid or needs validation?
errors: bool  # has errors or error count?
```

### Constants

```python
# Good - uppercase
MAX_FILE_SIZE = 10_000_000
SUPPORTED_LANGUAGES = ['python', 'typescript', 'java']
DEFAULT_TIMEOUT = 30

# Bad - lowercase
max_file_size = 10_000_000
```

## Code Comments

### When to Comment

```python
# Good - explain WHY, not WHAT
# Use tree-sitter instead of ast because it handles partial/invalid syntax
parser = TreeSitterParser(language)

# Bad - comment states the obvious
# Create a parser
parser = TreeSitterParser(language)
```

### TODO Comments

```python
# TODO(username): Brief description of what needs to be done
# TODO(issue-123): Link to issue for context
def temporary_workaround():
    # FIXME: This is a temporary hack, replace with proper solution
    ...
```

## Testing Conventions

### Test File Organization

```python
# tests/test_parser.py

class TestParserBasics:
    """Test basic parser functionality."""

    def test_parser_can_initialize(self):
        """Test that parser initializes correctly."""
        ...

    def test_parser_has_default_config(self):
        """Test default configuration."""
        ...

class TestParserPython:
    """Test Python-specific parsing."""

    def test_parser_handles_python_classes(self):
        """Test parsing Python classes."""
        ...

class TestParserErrors:
    """Test error handling."""

    def test_parser_detects_syntax_errors(self):
        """Test syntax error detection."""
        ...
```

### Test Naming

```python
# Good - descriptive test names
def test_parser_rejects_files_over_10mb():
    ...

def test_analyzer_extracts_all_public_methods():
    ...

def test_cache_invalidates_on_file_change():
    ...

# Bad - generic names
def test_parser():
    ...

def test_methods():
    ...
```

## Version Numbers

Use semantic versioning in code:

```python
__version__ = "2.0.0-alpha.1"

# major.minor.patch-prerelease
# 2.0.0-alpha.1
# 2.0.0-beta.1
# 2.0.0-rc.1
# 2.0.0
# 2.1.0
# 3.0.0
```

## Git Commit Messages

```
type(scope): Brief description (max 72 chars)

Longer description if needed, explaining WHY not WHAT.
Wrap at 72 characters.

- Bullet points for multiple changes
- Keep each point focused

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`

---

**Remember**: Consistency is more important than personal preference. Follow these conventions to maintain a clean, readable codebase.
