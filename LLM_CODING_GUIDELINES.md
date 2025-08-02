# LLM Coding Guidelines for Tree-sitter Analyzer

This document provides comprehensive guidelines for AI/LLM systems when generating code for the Tree-sitter Analyzer project. Following these guidelines ensures high-quality, maintainable code that integrates seamlessly with the existing codebase.

## 🎯 Core Principles

### 1. Quality First
- **Always prioritize code quality over speed of delivery**
- **Follow established patterns and conventions**
- **Write self-documenting code with clear intent**

### 2. Consistency
- **Match existing code style and architecture**
- **Use established naming conventions**
- **Follow project-specific patterns**

### 3. Maintainability
- **Write code that future developers can easily understand**
- **Include comprehensive documentation**
- **Design for extensibility and modification**

## 📋 Pre-Generation Checklist

Before generating any code, ensure you understand:

- [ ] **Project Structure**: Familiarize yourself with the codebase organization
- [ ] **Existing Patterns**: Study how similar functionality is implemented
- [ ] **Dependencies**: Understand what libraries and frameworks are used
- [ ] **Testing Strategy**: Know how tests are structured and written
- [ ] **Documentation Standards**: Understand the documentation requirements

## 🐍 Python Code Standards

### Type Hints (MANDATORY)

```python
# ✅ CORRECT: Always include type hints
def analyze_file(file_path: str, language: Optional[str] = None) -> AnalysisResult:
    """Analyze a code file and return results."""
    pass

# ❌ INCORRECT: Missing type hints
def analyze_file(file_path, language=None):
    pass
```

### Docstrings (MANDATORY)

```python
# ✅ CORRECT: Google-style docstrings
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

### Error Handling

```python
# ✅ CORRECT: Specific exception handling
try:
    result = parse_file(file_path)
except FileNotFoundError:
    raise AnalysisError(f"File not found: {file_path}")
except UnicodeDecodeError as e:
    raise AnalysisError(f"Encoding error in {file_path}: {e}")

# ❌ INCORRECT: Bare except clause
try:
    result = parse_file(file_path)
except:
    pass
```

### Import Organization

```python
# ✅ CORRECT: Organized imports
# Standard library
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Third-party
import tree_sitter
from pydantic import BaseModel

# Local imports
from .models import AnalysisResult
from .utils import log_info
```

## 🏗️ Architecture Guidelines

### Plugin System Integration

```python
# ✅ CORRECT: Follow plugin pattern
class NewLanguagePlugin(LanguagePlugin):
    """Plugin for analyzing NewLanguage code."""
    
    def get_language_name(self) -> str:
        """Return the language name."""
        return "newlanguage"
    
    def create_extractor(self) -> ElementExtractor:
        """Create an element extractor for this language."""
        return NewLanguageExtractor()
```

### MCP Tool Implementation

```python
# ✅ CORRECT: Follow MCP tool pattern
class NewAnalysisTool(BaseTool):
    """Tool for performing new type of analysis."""
    
    name: str = "new_analysis"
    description: str = "Perform new type of code analysis"
    
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the analysis tool."""
        try:
            # Implementation here
            return {"status": "success", "result": result}
        except Exception as e:
            return {"status": "error", "message": str(e)}
```

## 🧪 Testing Requirements

### Test Structure

```python
# ✅ CORRECT: Comprehensive test structure
class TestNewFeature:
    """Test suite for new feature."""
    
    def test_feature_success_case(self):
        """Test successful execution of feature."""
        # Arrange
        input_data = create_test_data()
        
        # Act
        result = new_feature(input_data)
        
        # Assert
        assert result is not None
        assert result.status == "success"
    
    def test_feature_error_handling(self):
        """Test error handling in feature."""
        with pytest.raises(SpecificError):
            new_feature(invalid_input)
```

### Test Coverage Requirements

- **Minimum 90% line coverage for new code**
- **Test both success and failure cases**
- **Include edge cases and boundary conditions**
- **Test error handling and exception paths**

## 🚫 Common Anti-patterns to Avoid

### 1. Mutable Default Arguments

```python
# ❌ INCORRECT
def process_items(items=[]):
    items.append("new")
    return items

# ✅ CORRECT
def process_items(items: Optional[List[str]] = None) -> List[str]:
    if items is None:
        items = []
    items.append("new")
    return items
```

### 2. Bare Exception Handling

```python
# ❌ INCORRECT
try:
    risky_operation()
except:
    pass

# ✅ CORRECT
try:
    risky_operation()
except SpecificError as e:
    log_error(f"Operation failed: {e}")
    raise AnalysisError(f"Failed to process: {e}") from e
```

### 3. String Concatenation in Loops

```python
# ❌ INCORRECT
result = ""
for item in items:
    result += str(item)

# ✅ CORRECT
result = "".join(str(item) for item in items)
```

### 4. Missing Type Hints

```python
# ❌ INCORRECT
def analyze(data):
    return process(data)

# ✅ CORRECT
def analyze(data: Dict[str, Any]) -> AnalysisResult:
    return process(data)
```

## 📊 Performance Guidelines

### Memory Management

```python
# ✅ CORRECT: Use generators for large datasets
def process_large_file(file_path: str) -> Iterator[CodeElement]:
    """Process large file efficiently."""
    with open(file_path, 'r') as f:
        for line in f:
            if element := parse_line(line):
                yield element

# ❌ INCORRECT: Load everything into memory
def process_large_file(file_path: str) -> List[CodeElement]:
    with open(file_path, 'r') as f:
        return [parse_line(line) for line in f.readlines()]
```

### Caching

```python
# ✅ CORRECT: Use appropriate caching
from functools import lru_cache

@lru_cache(maxsize=128)
def get_language_parser(language: str) -> Language:
    """Get cached language parser."""
    return Language(library_path, language)
```

## 🔍 Code Review Checklist

Before submitting generated code, verify:

### Functionality
- [ ] Code implements the required functionality correctly
- [ ] All edge cases are handled appropriately
- [ ] Error conditions are properly managed

### Quality
- [ ] Code follows PEP 8 and project conventions
- [ ] All functions have type hints and docstrings
- [ ] Variable and function names are descriptive
- [ ] Code is readable and well-structured

### Testing
- [ ] Comprehensive tests are included
- [ ] Tests cover success and failure cases
- [ ] Test names are descriptive and clear
- [ ] Tests follow project testing patterns

### Documentation
- [ ] All public APIs are documented
- [ ] Complex logic is explained with comments
- [ ] Examples are provided where helpful
- [ ] README updates are included if needed

### Integration
- [ ] Code integrates properly with existing systems
- [ ] Dependencies are properly managed
- [ ] No breaking changes to public APIs
- [ ] Follows established architectural patterns

## 🛠️ Development Workflow

### 1. Analysis Phase
- Study existing codebase patterns
- Understand the specific requirements
- Identify integration points
- Plan the implementation approach

### 2. Implementation Phase
- Write code following all guidelines
- Include comprehensive type hints
- Add detailed docstrings
- Implement proper error handling

### 3. Testing Phase
- Write comprehensive tests
- Ensure high test coverage
- Test edge cases and error conditions
- Verify integration with existing code

### 4. Documentation Phase
- Update relevant documentation
- Add code examples if needed
- Update README if necessary
- Document any new APIs or changes

### 5. Quality Assurance
- Run all quality checks
- Ensure code passes all tests
- Verify performance requirements
- Check for security issues

## 📚 Resources and References

### Project-Specific Resources
- [Code Style Guide](CODE_STYLE_GUIDE.md)
- [Contributing Guidelines](CONTRIBUTING.md)
- [Architecture Documentation](docs/architecture.md)

### External Resources
- [PEP 8 Style Guide](https://pep8.org/)
- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)

## 🎯 Success Metrics

Generated code should achieve:
- **90%+ test coverage**
- **Zero linting errors**
- **All type checks pass**
- **Performance benchmarks met**
- **Security scans pass**
- **Documentation completeness**

Remember: **Quality over quantity**. It's better to generate less code that meets all standards than more code that requires extensive revision.

## 🤖 LLM-Specific Instructions

### Before Writing Any Code

1. **ALWAYS** run the quality check script first to understand current state:
   ```bash
   python check_quality.py --new-code-only
   ```

2. **ALWAYS** study existing similar implementations in the codebase

3. **ALWAYS** check the current test coverage and patterns

### Code Generation Template

When generating new code, use this template:

```python
#!/usr/bin/env python3
"""
Module: [module_name]

Description: [Brief description of what this module does]

Author: AI Assistant
Date: [Current date]
"""

# Standard library imports
from typing import Any, Dict, List, Optional

# Third-party imports
# [Add as needed]

# Local imports
from tree_sitter_analyzer.exceptions import AnalysisError
from tree_sitter_analyzer.utils import log_info


class NewClass:
    """[Class description].

    This class [detailed description of purpose and usage].

    Attributes:
        attribute_name: Description of attribute

    Example:
        >>> instance = NewClass()
        >>> result = instance.method()
    """

    def __init__(self, param: str) -> None:
        """Initialize the class.

        Args:
            param: Description of parameter
        """
        self.param = param

    def public_method(self, input_data: Dict[str, Any]) -> List[str]:
        """Public method description.

        Args:
            input_data: Description of input

        Returns:
            Description of return value

        Raises:
            AnalysisError: When [condition]
            ValueError: When [condition]
        """
        try:
            # Implementation here
            return self._private_method(input_data)
        except Exception as e:
            raise AnalysisError(f"Failed to process: {e}") from e

    def _private_method(self, data: Dict[str, Any]) -> List[str]:
        """Private helper method."""
        # Implementation
        return []


# Module-level functions
def utility_function(param: str) -> bool:
    """Utility function description.

    Args:
        param: Parameter description

    Returns:
        Boolean result description
    """
    return True
```

### Test Generation Template

```python
#!/usr/bin/env python3
"""
Tests for [module_name]

Test coverage for [brief description of what's being tested].
"""

import pytest
from unittest.mock import Mock, patch

from tree_sitter_analyzer.[module_path] import NewClass, utility_function
from tree_sitter_analyzer.exceptions import AnalysisError


class TestNewClass:
    """Test suite for NewClass."""

    def test_init_success(self):
        """Test successful initialization."""
        instance = NewClass("test_param")
        assert instance.param == "test_param"

    def test_public_method_success(self):
        """Test successful execution of public method."""
        # Arrange
        instance = NewClass("test")
        input_data = {"key": "value"}

        # Act
        result = instance.public_method(input_data)

        # Assert
        assert isinstance(result, list)
        assert len(result) >= 0

    def test_public_method_error_handling(self):
        """Test error handling in public method."""
        instance = NewClass("test")

        with pytest.raises(AnalysisError):
            instance.public_method(None)

    @patch('tree_sitter_analyzer.[module_path].external_dependency')
    def test_with_mocked_dependency(self, mock_dependency):
        """Test with mocked external dependency."""
        # Setup mock
        mock_dependency.return_value = "mocked_result"

        # Test
        instance = NewClass("test")
        result = instance.public_method({"test": "data"})

        # Verify
        mock_dependency.assert_called_once()
        assert result is not None


class TestUtilityFunction:
    """Test suite for utility functions."""

    def test_utility_function_success(self):
        """Test successful execution of utility function."""
        result = utility_function("valid_input")
        assert isinstance(result, bool)

    def test_utility_function_edge_cases(self):
        """Test edge cases for utility function."""
        assert utility_function("") is False
        assert utility_function("valid") is True


# Integration tests
class TestIntegration:
    """Integration tests for the module."""

    def test_end_to_end_workflow(self):
        """Test complete workflow from start to finish."""
        # Test the complete integration
        pass
```

### Quality Check Commands

After generating code, ALWAYS run these commands:

```bash
# 1. Format code
uv run black .
uv run isort .

# 2. Check linting
uv run ruff check . --fix

# 3. Type checking
uv run mypy tree_sitter_analyzer/

# 4. Run tests
uv run pytest tests/ -v

# 5. Check coverage
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

# 6. Security scan
uv run bandit -r tree_sitter_analyzer/

# 7. Comprehensive quality check
python check_quality.py
```

### Final Verification Checklist

Before considering code generation complete:

- [ ] All quality checks pass
- [ ] Test coverage is ≥90%
- [ ] All functions have type hints
- [ ] All public APIs have docstrings
- [ ] Error handling is comprehensive
- [ ] Code follows project patterns
- [ ] Integration tests pass
- [ ] Documentation is updated
- [ ] No security vulnerabilities
- [ ] Performance is acceptable

**CRITICAL**: Never submit code that doesn't pass all quality checks!
