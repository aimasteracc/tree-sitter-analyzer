# TDD Workflow Guide

This guide explains the Test-Driven Development (TDD) workflow for tree-sitter-analyzer v2.

## Table of Contents

- [Why TDD?](#why-tdd)
- [The TDD Cycle](#the-tdd-cycle)
- [Practical Examples](#practical-examples)
- [Best Practices](#best-practices)
- [Common Pitfalls](#common-pitfalls)

## Why TDD?

**Benefits:**
- ✅ **Better design**: Writing tests first forces you to think about API design
- ✅ **Confidence**: High test coverage means you can refactor safely
- ✅ **Documentation**: Tests serve as living documentation
- ✅ **Fewer bugs**: Catch issues early in development
- ✅ **Faster development**: Less debugging time overall

**The v2 Commitment:**
- All code in v2 is developed using TDD
- Minimum 80% test coverage (90% for core modules)
- Tests are written BEFORE implementation

## The TDD Cycle

### 1. RED: Write a Failing Test

Write a test for functionality that doesn't exist yet. The test MUST fail.

```python
# tests/test_parser.py
def test_parser_handles_python_file():
    """Test that parser can parse a simple Python file."""
    from tree_sitter_analyzer_v2.core.parser import Parser

    parser = Parser()
    result = parser.parse("print('hello')", language="python")

    assert result is not None
    assert result.has_errors is False
```

**Run the test:**
```bash
uv run pytest tests/test_parser.py -v
```

**Expected output:**
```
FAILED tests/test_parser.py::test_parser_handles_python_file
ModuleNotFoundError: No module named 'tree_sitter_analyzer_v2.core.parser'
```

✅ **Good**: Test fails because code doesn't exist yet.

### 2. GREEN: Write Minimal Code

Write JUST ENOUGH code to make the test pass. Don't add extra features.

```python
# tree_sitter_analyzer_v2/core/parser.py
from typing import Any

class Parser:
    """Minimal parser implementation."""

    def parse(self, code: str, language: str) -> Any:
        """Parse code and return result."""
        # Minimal implementation to pass test
        return type('Result', (), {'has_errors': False})()
```

**Run the test:**
```bash
uv run pytest tests/test_parser.py -v
```

**Expected output:**
```
PASSED tests/test_parser.py::test_parser_handles_python_file
```

✅ **Good**: Test passes with minimal code.

### 3. REFACTOR: Improve Code Quality

Now that the test passes, improve the code while keeping tests green.

```python
# tree_sitter_analyzer_v2/core/parser.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class ParseResult:
    """Result of parsing operation."""
    tree: Optional[Any] = None
    has_errors: bool = False

class Parser:
    """Tree-sitter parser wrapper."""

    def parse(self, code: str, language: str) -> ParseResult:
        """
        Parse code using tree-sitter.

        Args:
            code: Source code to parse
            language: Language identifier

        Returns:
            ParseResult with AST tree
        """
        # Better implementation with proper types
        return ParseResult(has_errors=False)
```

**Run tests:**
```bash
uv run pytest tests/test_parser.py -v
```

✅ **Good**: Tests still pass after refactoring.

### 4. REPEAT

Continue the cycle for each new feature:
1. Write failing test (RED)
2. Make it pass (GREEN)
3. Improve code (REFACTOR)

## Practical Examples

### Example 1: Adding a New Method

**Scenario**: Add a method to check if a file is too large to parse.

**Step 1 - RED: Write failing test**

```python
# tests/test_parser.py
def test_parser_detects_large_files():
    """Test that parser can detect files that are too large."""
    from tree_sitter_analyzer_v2.core.parser import Parser

    parser = Parser(max_file_size=1000)  # 1KB max

    # Small file - should be OK
    assert parser.is_file_too_large("hello.py", size=500) is False

    # Large file - should be rejected
    assert parser.is_file_too_large("huge.py", size=2000) is True
```

**Run test (should FAIL):**
```bash
uv run pytest tests/test_parser.py::test_parser_detects_large_files -v
# AttributeError: 'Parser' object has no attribute 'is_file_too_large'
```

**Step 2 - GREEN: Minimal implementation**

```python
# tree_sitter_analyzer_v2/core/parser.py
class Parser:
    def __init__(self, max_file_size: int = 10_000_000):  # 10MB default
        self.max_file_size = max_file_size

    def is_file_too_large(self, file_path: str, size: int) -> bool:
        """Check if file is too large to parse."""
        return size > self.max_file_size
```

**Run test (should PASS):**
```bash
uv run pytest tests/test_parser.py::test_parser_detects_large_files -v
# PASSED
```

**Step 3 - REFACTOR: Improve**

```python
# tree_sitter_analyzer_v2/core/parser.py
from pathlib import Path

class Parser:
    def __init__(self, max_file_size: int = 10_000_000):
        """
        Initialize parser.

        Args:
            max_file_size: Maximum file size in bytes (default: 10MB)
        """
        self.max_file_size = max_file_size

    def is_file_too_large(self, file_path: str, size: int | None = None) -> bool:
        """
        Check if file exceeds size limit.

        Args:
            file_path: Path to file
            size: File size in bytes (optional, will be determined if not provided)

        Returns:
            True if file is too large
        """
        if size is None:
            size = Path(file_path).stat().st_size
        return size > self.max_file_size
```

### Example 2: Testing Error Cases

**Always test error conditions!**

```python
# tests/test_parser.py
def test_parser_handles_invalid_syntax():
    """Test that parser detects syntax errors."""
    from tree_sitter_analyzer_v2.core.parser import Parser

    parser = Parser()
    result = parser.parse("def broken(", language="python")

    assert result.has_errors is True
    assert result.error_message is not None

def test_parser_raises_on_unknown_language():
    """Test that parser raises error for unknown language."""
    from tree_sitter_analyzer_v2.core.parser import Parser, UnsupportedLanguageError

    parser = Parser()

    with pytest.raises(UnsupportedLanguageError):
        parser.parse("some code", language="unknown_lang")
```

## Best Practices

### DO

✅ **Write tests first, always**
```python
# First: tests/test_feature.py
def test_feature():
    assert my_feature() == expected

# Then: tree_sitter_analyzer_v2/feature.py
def my_feature():
    return expected
```

✅ **Test one thing at a time**
```python
def test_parser_handles_python():
    """Test Python parsing only."""
    # Focus on one aspect

def test_parser_handles_typescript():
    """Test TypeScript parsing separately."""
    # Separate test for different language
```

✅ **Use descriptive test names**
```python
# Good
def test_parser_rejects_files_larger_than_10mb():
    ...

# Bad
def test_parser():
    ...
```

✅ **Test edge cases**
```python
def test_parser_handles_empty_file():
    ...

def test_parser_handles_unicode_characters():
    ...

def test_parser_handles_extremely_long_lines():
    ...
```

### DON'T

❌ **Don't write implementation first**
```python
# Bad: Implementation without tests
def new_feature():
    return "something"

# Then later...
def test_new_feature():  # Test after implementation
    assert new_feature() == "something"
```

❌ **Don't skip tests for "simple" code**
```python
# Even simple code needs tests
def add(a: int, b: int) -> int:
    return a + b

# Write test:
def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0
```

❌ **Don't test implementation details**
```python
# Bad: Testing internal implementation
def test_parser_uses_tree_sitter_internally():
    parser = Parser()
    assert hasattr(parser, '_tree_sitter_instance')

# Good: Test behavior
def test_parser_returns_valid_ast():
    parser = Parser()
    result = parser.parse("code", "python")
    assert result.is_valid()
```

## Common Pitfalls

### Pitfall 1: Writing Tests After Implementation

**Problem:**
```python
# Wrote code first
def calculate(x):
    return x * 2

# Then wrote test
def test_calculate():
    assert calculate(5) == 10
```

**Why it's bad**: Tests might just confirm what code does, not what it should do.

**Solution**: Write test first to define requirements.

### Pitfall 2: Testing Too Much in One Test

**Problem:**
```python
def test_everything():
    """Test all parser features."""
    parser = Parser()
    assert parser.parse("python", "py")
    assert parser.is_valid()
    assert parser.get_errors() == []
    assert parser.format() == "formatted"
    # ... 20 more assertions
```

**Solution**: Split into focused tests.

```python
def test_parser_parses_python():
    ...

def test_parser_validates_syntax():
    ...

def test_parser_formats_output():
    ...
```

### Pitfall 3: Not Running Tests Frequently

**Problem**: Writing lots of code, then running tests.

**Solution**: Run tests after EVERY change.

```bash
# Use pytest-watch for automatic test running
pip install pytest-watch
ptw -- tests/
```

## Measuring Success

Check your TDD practice quality:

```bash
# Coverage report
uv run pytest tests/ --cov=tree_sitter_analyzer_v2 --cov-report=term-missing

# Should show:
# - 80%+ overall coverage
# - 90%+ for core modules
# - 100% for new code
```

## TDD Checklist

Before committing code, verify:

- [ ] Tests written BEFORE implementation
- [ ] All tests passing
- [ ] Coverage >= 80% (90% for core)
- [ ] Edge cases tested
- [ ] Error conditions tested
- [ ] Code refactored for clarity
- [ ] No skipped tests
- [ ] No commented-out code

---

**Remember**: TDD is a discipline. It feels slow at first but makes development faster and more reliable in the long run.

Follow the mantra: **RED → GREEN → REFACTOR → REPEAT**
