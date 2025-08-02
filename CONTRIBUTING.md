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

```bash
# Run all tests (1283+ tests)
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=tree_sitter_analyzer

# Run specific test file
pytest tests/test_mcp_tools.py -v

# Run tests for specific functionality
pytest tests/test_quiet_option.py -v
pytest tests/test_partial_read_command_validation.py -v
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
   pytest tests/ -v
   uv run python -m tree_sitter_analyzer examples/Sample.java --advanced
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

Thank you for contributing! 🎉