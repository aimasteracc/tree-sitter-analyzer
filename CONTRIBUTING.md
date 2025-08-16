# Contributing to Tree-sitter Analyzer

We welcome contributions! This guide will help you get started.

## 🚀 Quick Start for Contributors

### Development Setup

```bash
# Clone the repository
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer

# Install development dependencies
uv sync --extra all --extra mcp

# Verify setup
uv run python -c "import tree_sitter_analyzer; print('Setup OK')"
```

### Running Tests

> This project uses `uv run` for all local commands (including Windows/PowerShell). Do not call `pytest` or `python` directly to ensure consistent interpreter and virtual environment.

```bash
# Run all tests (1216+ tests)
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=tree_sitter_analyzer

# Run specific test file
uv run pytest tests/test_mcp_tools.py -v

# Run tests for specific functionality
uv run pytest tests/test_quiet_option.py -v
uv run pytest tests/test_partial_read_command_validation.py -v
```

## 🛠️ Development Workflow

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Follow existing code style
   - Add tests for new functionality
   - Update documentation if needed

3. **Test your changes**
   ```bash
   # Run tests
   uv run pytest tests/ -v

   # Run code quality checks
   uv run black --check . && uv run ruff check . && uv run mypy .

   # Test CLI functionality
   uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text
   ```

4. **Submit a pull request**
   - Describe your changes clearly
   - Include test results
   - Reference any related issues

## 📝 Code Style

- Follow PEP 8 for Python code
- Use type hints where appropriate
- Write clear docstrings
- Keep functions focused and small

📖 **For detailed guidelines, see our `CODE_STYLE_GUIDE.md`**

### 🔧 Pre-commit Hooks (Recommended)

Install pre-commit hooks to automatically check code quality:

```bash
# Install pre-commit
uv add --dev pre-commit

# Install hooks
uv run pre-commit install

# Run hooks manually (optional)
uv run pre-commit run --all-files
```

### Code Quality Checks

Before submitting your changes, run these quality checks:

```bash
# Format code with Black
uv run black .

# Check code formatting
uv run black --check .

# Lint with Ruff (faster alternative to flake8)
uv run ruff check .

# Auto-fix Ruff issues (safe fixes only)
uv run ruff check . --fix

# Type checking with mypy (note: has many legacy issues)
uv run mypy . --no-error-summary

# Run all quality checks at once
uv run black --check . && uv run ruff check . && uv run mypy .

# Or use our quality check script (recommended)
uv run python check_quality.py

# Auto-fix issues and run checks
uv run python check_quality.py --fix

# Focus on new code only (skip legacy issues) - RECOMMENDED FOR NEW CONTRIBUTORS
uv run python check_quality.py --new-code-only --fix
```

### Quality Check Script

Our `check_quality.py` script provides:

- **Black code formatting** (auto-fixes with `--fix`)
- **Ruff linting** (auto-fixes safe issues with `--fix`)
- **MyPy type checking** (skipped in `--new-code-only` mode)
- **Quick test run**

**Recommended workflow for new contributors:**
```bash
uv run python check_quality.py --new-code-only --fix
```

This will auto-format your code and fix safe issues while skipping the ~300 legacy type issues.

### Quality Standards

**For new contributions:**
- All code must pass Black formatting
- New code should not introduce Ruff warnings
- Type hints should be provided for new functions
- Tests should be included for new functionality
- Line length: 88 characters (Black default)

**Legacy code reality:**
- The project has ~300 historical code quality issues
- Focus on not introducing new issues
- Feel free to improve code you're modifying, but it's not required
- Large-scale quality improvements should be separate PRs

**For New Contributors:**
- Focus on not introducing NEW quality issues
- You can optionally fix existing issues in files you're modifying
- Use `uv run ruff check . --fix` to auto-fix safe issues
- Large-scale quality improvements should be separate PRs

## 🐛 Reporting Issues

- Use GitHub Issues
- Include error messages and stack traces
- Provide sample code files when possible
- Specify your Python version and OS

## 💡 Feature Requests

- Open a GitHub Issue with the "enhancement" label
- Describe the use case clearly
- Explain how it would benefit users

## 🧪 Testing Guidelines

- Write tests for new features
- Ensure existing tests pass (1283+ tests should pass)
- Test with multiple programming languages
- Test both CLI and MCP functionality
- Test error handling and edge cases
- Include tests for new CLI options (like --quiet)
- Test MCP tool functionality and parameter validation
- Follow the existing test patterns in the codebase

## 📚 Documentation

- Update README.md for user-facing changes
- Add docstrings to new functions/classes
- Update MCP setup guides if needed

## 📊 README Data Maintenance

**Important:** README files contain dynamic statistics that need regular updates!

### Data That Needs Synchronization

1. **Test Statistics**
   - Test count: `1,358 tests`
   - Code coverage: `74.54%`
   - Location: Badges and quality metrics sections

2. **Version Information**
   - Current version: From `pyproject.toml`
   - Location: Quality achievements section

3. **Example File Statistics**
   - BigService.java lines: `1419 lines`
   - Method count: `66 methods`
   - Field count: `9 fields`
   - Class count: `1 class`
   - Import count: `8 imports`

### Auto-update README Statistics
```bash
# Run this script after significant changes
python scripts/update_readme_stats.py
```

### When to Update
- Add/remove test files
- Modify examples/BigService.java
- Update version numbers in pyproject.toml
- Before releases
- After major feature additions

### Automated Checks
- **Pre-commit Hook**: Runs on `git push`
- **GitHub Actions**: Validates README consistency on PRs
- **CI/CD**: Ensures main branch README is always current

### Development Workflow
1. Make code changes
2. Run quality checks: `uv run python check_quality.py --new-code-only --fix`
3. Update README stats: `python scripts/update_readme_stats.py`
4. Commit and push changes

Thank you for contributing! 🎉
