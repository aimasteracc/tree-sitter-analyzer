## 📋 Pull Request Description

### 🎯 What does this PR do?

Brief description of the changes in this pull request.

### 🔗 Related Issues

Fixes #(issue number)
Closes #(issue number)
Related to #(issue number)

### 🔄 Type of Change

- [ ] 🐛 Bug fix (non-breaking change which fixes an issue)
- [ ] ✨ New feature (non-breaking change which adds functionality)
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] 📚 Documentation update
- [ ] 🔧 Refactoring (no functional changes)
- [ ] ⚡ Performance improvement
- [ ] 🧪 Test improvements
- [ ] 🏗️ Build/CI changes

## 🧪 Testing

### ✅ Test Coverage

- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] I have tested the changes manually

### 🔍 Test Results

```bash
# Paste test results here
pytest tests/ -v
```

## 📋 Quality Checklist

### 🔧 Code Quality

- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation

### 🛠️ Quality Checks Passed

- [ ] ✅ Black formatting: `uv run black --check .`
- [ ] ✅ Ruff linting: `uv run ruff check .`
- [ ] ✅ Type checking: `uv run mypy tree_sitter_analyzer/`
- [ ] ✅ Security scan: `uv run bandit -r tree_sitter_analyzer/`
- [ ] ✅ All tests pass: `uv run pytest tests/ -v`

### 📊 Quality Check Results

```bash
# Paste quality check results here
python check_quality.py
```

## 📚 Documentation

- [ ] I have updated the README.md if needed
- [ ] I have updated relevant documentation
- [ ] I have added docstrings to new functions/classes
- [ ] I have updated the CHANGELOG.md (if applicable)

## 🔄 Breaking Changes

If this is a breaking change, please describe:

1. What functionality is being changed/removed?
2. Why is this change necessary?
3. How should users migrate their code?
4. Are there any deprecation warnings in place?

## 📸 Screenshots/Examples

If applicable, add screenshots or code examples to help explain your changes.

```python
# Example of new functionality
analyzer = TreeSitterAnalyzer()
result = analyzer.new_method()
```

## 🎯 Performance Impact

- [ ] No performance impact
- [ ] Performance improvement (please quantify)
- [ ] Potential performance regression (please explain)

## 🔍 Additional Notes

Any additional information that reviewers should know about this PR.

## ✅ Final Checklist

- [ ] I have read the [Contributing Guidelines](../docs/CONTRIBUTING.md)
- [ ] I have read the [AI Coding Rules](../docs/ai-coding-rules.md)
- [ ] My changes generate no new warnings
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] Any dependent changes have been merged and published
