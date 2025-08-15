# AI Collaboration Guide for Tree-sitter Analyzer

This guide provides best practices for collaborating with AI/LLM systems when working on the Tree-sitter Analyzer project. It ensures that AI-generated code maintains the high quality standards of the project.

## 🤖 For AI Systems

### Initial Setup Commands

Before generating any code, AI systems should run these commands to understand the project state:

```bash
# 1. Check current code quality
uv run python check_quality.py --new-code-only

# 2. Run LLM-specific code checker
uv run python llm_code_checker.py --check-all

# 3. Review test coverage
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=term-missing

# 4. Check current project structure
find tree_sitter_analyzer -name "*.py" | head -20
```

### Code Generation Workflow

1. **Analysis Phase**
   ```bash
   # Study existing patterns
   grep -r "class.*Plugin" tree_sitter_analyzer/
   grep -r "def.*extract" tree_sitter_analyzer/
   ```

2. **Implementation Phase**
   - Follow the templates in `LLM_CODING_GUIDELINES.md`
   - Use the code generation template
   - Include comprehensive type hints and docstrings

3. **Quality Assurance Phase**
   ```bash
   # Format and lint
   uv run black . && uv run isort . && uv run ruff check . --fix
   
   # Type checking
   uv run mypy tree_sitter_analyzer/
   
   # Run tests
   uv run pytest tests/ -v
   
   # LLM-specific checks
   uv run python llm_code_checker.py [new_file.py]
   
   # Final quality check
   uv run python check_quality.py
   ```

### Mandatory Patterns

#### 1. Exception Handling
```python
# ✅ ALWAYS use project-specific exceptions
from tree_sitter_analyzer.exceptions import AnalysisError

try:
    result = risky_operation()
except SpecificError as e:
    raise AnalysisError(f"Operation failed: {e}") from e
```

#### 2. Logging
```python
# ✅ ALWAYS use project logging
from tree_sitter_analyzer.utils import log_info, log_error

def process_data(data):
    log_info(f"Processing {len(data)} items")
    try:
        # Process data
        log_info("Processing completed successfully")
    except Exception as e:
        log_error(f"Processing failed: {e}")
        raise
```

#### 3. Type Hints
```python
# ✅ MANDATORY for all functions
from typing import Dict, List, Optional

def analyze_code(file_path: str, options: Optional[Dict[str, Any]] = None) -> AnalysisResult:
    """Analyze code with proper type hints."""
    pass
```

### Quality Gates

AI-generated code MUST pass all these checks:

- [ ] ✅ `uv run python llm_code_checker.py [file]` - No issues
- [ ] ✅ `uv run black --check .` - Properly formatted
- [ ] ✅ `uv run ruff check .` - No linting errors
- [ ] ✅ `uv run mypy tree_sitter_analyzer/` - Type checks pass
- [ ] ✅ `uv run pytest tests/ -v` - All tests pass
- [ ] ✅ Test coverage ≥90% for new code
- [ ] ✅ All public functions have docstrings
- [ ] ✅ Proper error handling implemented

## 👨‍💻 For Human Developers

### Working with AI-Generated Code

#### 1. Review Checklist

When reviewing AI-generated code:

```bash
# Quick quality check
uv run python llm_code_checker.py path/to/ai_generated_file.py

# Comprehensive review
uv run python check_quality.py --new-code-only
```

#### 2. Common AI Code Issues

Watch out for these common problems:

- **Missing type hints** - AI sometimes forgets return types
- **Generic exceptions** - AI may use `Exception` instead of `AnalysisError`
- **Inadequate docstrings** - May be too brief or missing examples
- **Missing error handling** - AI might not handle edge cases
- **Inconsistent patterns** - May not follow project conventions

#### 3. Improvement Workflow

```bash
# 1. Run AI code checker
uv run python llm_code_checker.py ai_generated_file.py

# 2. Fix identified issues
# [Manual fixes based on checker output]

# 3. Verify fixes
uv run python llm_code_checker.py ai_generated_file.py

# 4. Run full quality check
uv run python check_quality.py
```

### Requesting AI Assistance

#### Effective Prompts

```markdown
# ✅ GOOD: Specific request with context
"Create a new language plugin for Rust following the existing Java plugin pattern. 
Include proper type hints, comprehensive docstrings, error handling, and tests. 
The plugin should extract functions, classes, and imports."

# ❌ BAD: Vague request
"Add Rust support"
```

#### Include Context

Always provide:
- Existing code patterns to follow
- Specific requirements and constraints
- Expected input/output formats
- Error handling requirements
- Testing expectations

## 🔧 Tools and Scripts

### Available Quality Tools

1. **`check_quality.py`** - Comprehensive project quality check
2. **`llm_code_checker.py`** - AI-specific code quality checker
3. **Pre-commit hooks** - Automatic quality checks on commit
4. **GitHub Actions** - CI/CD quality gates

### Usage Examples

```bash
# Check specific AI-generated file
uv run python llm_code_checker.py tree_sitter_analyzer/new_feature.py

# Check all files for AI-specific issues
uv run python llm_code_checker.py --check-all

# Run comprehensive quality check
uv run python check_quality.py

# Check only new/modified code
uv run python check_quality.py --new-code-only

# Auto-fix common issues
uv run black . && uv run isort . && uv run ruff check . --fix
```

## 📊 Quality Metrics

### Success Criteria

AI-generated code should achieve:

| Metric | Target | Command |
|--------|--------|---------|
| Test Coverage | ≥90% | `uv run pytest --cov=tree_sitter_analyzer` |
| Type Coverage | 100% | `uv run mypy tree_sitter_analyzer/` |
| Linting Score | 0 errors | `uv run ruff check .` |
| Security Score | 0 issues | `bandit -r tree_sitter_analyzer/` |
| Documentation | 100% public APIs | `uv run python llm_code_checker.py` |

### Performance Benchmarks

- Function execution time: <100ms for typical operations
- Memory usage: <50MB for standard analysis
- Test execution time: <30 seconds for full suite

## 🚨 Red Flags

Immediately reject AI-generated code that has:

- ❌ Bare `except:` clauses
- ❌ Missing type hints on public functions
- ❌ No docstrings on public APIs
- ❌ Generic `Exception` usage instead of specific types
- ❌ Print statements instead of logging
- ❌ Mutable default arguments
- ❌ No error handling
- ❌ No tests

## 🎯 Best Practices

### For AI Systems

1. **Always study existing code first**
2. **Follow established patterns religiously**
3. **Include comprehensive tests**
4. **Use project-specific exceptions**
5. **Add detailed docstrings with examples**
6. **Handle all error conditions**
7. **Run quality checks before submission**

### For Human Developers

1. **Review AI code thoroughly**
2. **Run quality checkers on AI contributions**
3. **Provide clear, specific requirements**
4. **Give feedback on AI code quality**
5. **Maintain coding standards consistently**

## 📚 Resources

- [LLM Coding Guidelines](LLM_CODING_GUIDELINES.md) - Detailed coding standards
- [Code Style Guide](CODE_STYLE_GUIDE.md) - Project style guide
- [Contributing Guidelines](CONTRIBUTING.md) - General contribution guide
- [Architecture Documentation](docs/architecture.md) - System architecture

## 🔄 Continuous Improvement

This guide evolves based on:
- AI code quality patterns observed
- Common issues identified
- Developer feedback
- Project requirements changes

Report issues or suggestions for this guide in GitHub discussions.

---

**Remember**: The goal is not to restrict AI capabilities, but to channel them effectively to produce high-quality, maintainable code that integrates seamlessly with the existing project.
