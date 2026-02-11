## Description

Brief description of changes.

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Performance improvement
- [ ] Documentation update
- [ ] Test improvement
- [ ] CI/CD or infrastructure change

## How Has This Been Tested?

Describe the tests you ran to verify your changes:

```bash
uv run pytest tests/ -v
```

**Test results:**
- [ ] All existing tests pass
- [ ] New tests added for new code
- [ ] Coverage maintained or improved

## Checklist

- [ ] Tests written FIRST (TDD methodology)
- [ ] All tests passing (`uv run pytest tests/ -v`)
- [ ] Code coverage >= 80% (`uv run pytest tests/ --cov`)
- [ ] Type hints added for all functions (`uv run mypy tree_sitter_analyzer_v2/`)
- [ ] Lint passes (`uv run ruff check tree_sitter_analyzer_v2/`)
- [ ] Format passes (`uv run ruff format --check tree_sitter_analyzer_v2/`)
- [ ] Docstrings added for public APIs
- [ ] CHANGELOG.md updated (if user-facing change)
- [ ] Documentation updated (if needed)

## Related Issues

Closes #(issue number)
