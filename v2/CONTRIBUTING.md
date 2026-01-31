# Contributing to tree-sitter-analyzer v2

Thank you for your interest in contributing to tree-sitter-analyzer v2! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Testing Requirements](#testing-requirements)
- [Code Standards](#code-standards)
- [Pull Request Process](#pull-request-process)

## Code of Conduct

Be respectful, collaborative, and constructive in all interactions.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager
- [fd](https://github.com/sharkdp/fd) (optional but recommended)
- [ripgrep](https://github.com/BurntSushi/ripgrep) (optional but recommended)
- Git

### Installation

1. **Fork and clone the repository:**

   ```bash
   git clone https://github.com/YOUR_USERNAME/tree-sitter-analyzer.git
   cd tree-sitter-analyzer
   git checkout v2-rewrite
   ```

2. **Install dependencies:**

   ```bash
   cd v2
   uv pip install -e ".[dev]"
   ```

3. **Verify installation:**

   ```bash
   uv run pytest tests/ -v
   ```

   You should see all tests passing.

## Development Workflow

We follow **Test-Driven Development (TDD)** methodology. See [docs/tdd-workflow.md](docs/tdd-workflow.md) for detailed guidance.

### The TDD Cycle

1. **RED**: Write a failing test first
2. **GREEN**: Write minimal code to make the test pass
3. **REFACTOR**: Improve code quality while keeping tests green

### Example Workflow

```bash
# 1. Create a new branch
git checkout -b feature/my-feature

# 2. Write a failing test
cat > tests/test_my_feature.py << 'EOF'
def test_my_feature():
    from tree_sitter_analyzer_v2 import my_feature
    assert my_feature() == "expected"
EOF

# 3. Run test (should FAIL)
uv run pytest tests/test_my_feature.py -v

# 4. Implement the feature
# ... write code in tree_sitter_analyzer_v2/ ...

# 5. Run test (should PASS)
uv run pytest tests/test_my_feature.py -v

# 6. Run all tests
uv run pytest tests/ -v

# 7. Commit and push
git add .
git commit -m "feat: add my feature"
git push origin feature/my-feature
```

## Testing Requirements

### Coverage Target

- **Overall**: 80% minimum
- **Core modules**: 90% minimum
- **New code**: 100% (all new code must have tests)

### Test Categories

```bash
# Run unit tests
uv run pytest tests/unit/ -v

# Run integration tests
uv run pytest tests/integration/ -v

# Run end-to-end tests
uv run pytest tests/e2e/ -v

# Run all tests with coverage
uv run pytest tests/ --cov=tree_sitter_analyzer_v2 --cov-report=html
```

### Writing Tests

**DO:**
- ✅ Write tests BEFORE implementation
- ✅ Use descriptive test names (`test_parser_handles_invalid_syntax`)
- ✅ Test edge cases and error conditions
- ✅ Use fixtures from `conftest.py`
- ✅ Keep tests isolated and independent

**DON'T:**
- ❌ Write implementation before tests
- ❌ Skip tests "because it's simple"
- ❌ Test implementation details (test behavior)
- ❌ Write tests that depend on execution order
- ❌ Mock everything (integration tests need real interactions)

## Code Standards

### Code Quality

We use automated tools to maintain code quality:

```bash
# Linting
uv run ruff check tree_sitter_analyzer_v2/

# Formatting
uv run ruff format tree_sitter_analyzer_v2/

# Type checking
uv run mypy tree_sitter_analyzer_v2/
```

### Style Guidelines

- **Maximum line length**: 100 characters
- **Maximum file length**: 300 lines (if longer, split into modules)
- **Type hints**: Required for all functions and methods
- **Docstrings**: Required for all public APIs

### File Organization

```python
"""
Module docstring explaining purpose.

This should include:
- What the module does
- Key classes/functions
- Usage examples if helpful
"""

# Standard library imports
import sys
from pathlib import Path
from typing import Optional

# Third-party imports
import pytest

# Local imports
from tree_sitter_analyzer_v2.core import Parser


class MyClass:
    """Brief description of class.

    More detailed explanation if needed.

    Attributes:
        name: Description of attribute
    """

    def __init__(self, name: str) -> None:
        """Initialize MyClass.

        Args:
            name: Description of parameter
        """
        self.name = name

    def do_something(self, value: int) -> str:
        """Brief description of method.

        Args:
            value: Description of parameter

        Returns:
            Description of return value

        Raises:
            ValueError: When value is invalid
        """
        if value < 0:
            raise ValueError("Value must be non-negative")
        return f"{self.name}: {value}"
```

## Pull Request Process

### Before Submitting

1. **Run all tests:**
   ```bash
   uv run pytest tests/ -v
   ```

2. **Check code quality:**
   ```bash
   uv run ruff check tree_sitter_analyzer_v2/
   uv run ruff format tree_sitter_analyzer_v2/
   uv run mypy tree_sitter_analyzer_v2/
   ```

3. **Verify coverage:**
   ```bash
   uv run pytest tests/ --cov=tree_sitter_analyzer_v2 --cov-report=term
   ```

### Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## How Has This Been Tested?
Describe the tests you ran to verify your changes.

## Checklist
- [ ] Tests added (TDD: tests written FIRST)
- [ ] All tests passing
- [ ] Code coverage >= 80%
- [ ] Type hints added
- [ ] Docstrings added
- [ ] Code formatted with ruff
- [ ] mypy passes
- [ ] Documentation updated (if needed)
```

### Review Process

1. **Automated checks**: CI/CD runs tests and quality checks
2. **Code review**: At least one maintainer reviews
3. **Feedback**: Address review comments
4. **Merge**: Once approved and checks pass

## Common Tasks

### Adding a New Language

See detailed guide in [docs/adding-languages.md](docs/adding-languages.md) (to be created in Phase 5).

### Adding an MCP Tool

See detailed guide in [docs/adding-mcp-tools.md](docs/adding-mcp-tools.md) (to be created in Phase 3).

### Updating Documentation

Documentation is in `v2/docs/`. Update relevant files and verify:

```bash
# Check that examples run correctly
uv run python docs/examples/example_name.py
```

## Getting Help

- **Questions**: Open a discussion on GitHub
- **Bugs**: Open an issue with reproduction steps
- **Feature requests**: Open an issue with use case description

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to tree-sitter-analyzer v2! 🚀
