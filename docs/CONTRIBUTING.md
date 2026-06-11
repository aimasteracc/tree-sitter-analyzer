# Contributing to tree-sitter-analyzer

Thank you for your interest in contributing! This document provides guidelines for contributing to tree-sitter-analyzer.

## Quick Start

```bash
# 1. Fork and clone the repository
git clone https://github.com/YOUR_USERNAME/tree-sitter-analyzer.git

# 2. Create a feature branch from develop
git checkout -b feature/my-feature origin/develop

# 3. Make your changes and run tests
uv run pytest tests/ -v

# 4. Push and create a PR to develop
git push origin feature/my-feature
```

## Branch Strategy (GitFlow)

This project follows the GitFlow branching model.

> **Details**: See [GITFLOW.md](../GITFLOW.md)

### Branch Structure

| Branch | Purpose | Direct Push |
|--------|---------|-------------|
| `main` | Production-ready code | ❌ **Forbidden** |
| `develop` | Integration branch | ❌ PR only |
| `feature/*` | Feature development | ✅ Allowed |
| `release/*` | Release preparation | ✅ Allowed |
| `hotfix/*` | Emergency fixes | ✅ Allowed |

### ⚠️ Important: Direct pushes to main are forbidden

```
❌ Wrong: Push directly to main
   git push origin main

✅ Correct: feature → develop → release → main
```

### Contributor Workflow

```
1. Create a feature branch from develop
   git checkout -b feature/my-feature origin/develop

2. Develop and test your feature

3. Push your feature branch
   git push origin feature/my-feature

4. Create a PR to develop
   → Review → Merge

5. Release: develop → release → main
```

## Development Workflow

### 1. Determine Change Type

```
What are you changing?
  │
  ├─ New feature / Bug fix / Refactoring
  │   └─ Create feature/* branch → PR to develop
  │
  └─ Typo fix / Minor improvement
      └─ Create feature/* branch → PR to develop
```

### 2. Feature Development Flow

```bash
# 1. Create a feature branch from develop
git fetch origin
git checkout -b feature/my-feature origin/develop

# 2. Implement your changes

# 3. Run tests
uv run pytest tests/ -v

# 4. Run quality checks
uv run pre-commit run --all-files

# 5. Push your feature branch
git push origin feature/my-feature

# 6. Create a PR to develop
```

### 3. Pre-Push Checklist

```bash
# 1. Run tests locally
uv run pytest tests/ -v

# 2. Run quality checks
uv run pre-commit run --all-files

# 3. Verify system dependencies
fd --version
rg --version

# 4. Push
git push
```

## Task-Specific Guides

### 🌐 Adding New Language Support

When adding support for a new programming language, **always** follow this checklist:

> **📋 Required Reading**: [New Language Support Checklist](new-language-support-checklist.md)

This checklist includes:
- Language plugin implementation steps
- Formatter creation and registration
- **Golden master test creation** (Required!)
- Documentation updates (README.md, README_ja.md, README_zh.md)

⚠️ **Important**: Forgetting golden master tests will prevent detection of future regressions.

```bash
# Run language-specific tests
uv run pytest tests/unit/languages/ -v

# Run golden master tests
uv run pytest tests/regression/test_plugin_golden_masters.py -v -k "{language}"
```

## Code Quality

### Test Requirements

- **Coverage**: New code requires ≥80% coverage
- **Existing tests**: All tests must pass
- **Test types**: 
  - Unit tests: Individual component testing
  - Integration tests: Component interaction testing
  - E2E tests: End-to-end workflow testing

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage report
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=term-missing

# Run specific test file
uv run pytest tests/integration/docs/test_readme_structure.py -v

# Parallel execution (faster)
uv run pytest tests/ -n auto
```

### Coverage Targets

| Module Category | Coverage Target | Priority |
|-----------------|-----------------|----------|
| Core Engine | ≥85% | Critical |
| Exception Handling | ≥90% | Critical |
| MCP Interface | ≥80% | High |
| CLI Commands | ≥85% | High |
| Formatters | ≥80% | Medium |
| Query Modules | ≥85% | Medium |

## Multi-Language README Updates

When making structural changes to README.md, contributors are responsible for:

### Required Sync Updates

| File | Language | Required |
|------|----------|----------|
| README.md | English | ✅ Primary |
| README_ja.md | Japanese | ✅ Sync required |
| README_zh.md | Chinese | ✅ Sync required |

### README Change Checklist

- [ ] When adding new sections, add the same sections to README_ja.md and README_zh.md
- [ ] When reordering sections, update all READMEs with the same order
- [ ] When changing section emojis, update all READMEs with the same emojis
- [ ] Verify all `tests/integration/docs/` tests pass

### Structure Consistency Verification

```bash
# Run README structure tests
uv run pytest tests/integration/docs/test_readme_structure.py -v
```

These tests verify:
- README is under 500 lines
- All required sections exist
- Section emoji consistency
- Documentation link validity
- Multi-language README structure consistency

## CI/CD Workflow

### GitHub Actions Automation

| Branch | Workflow | Tests | Deploy | PR Creation |
|--------|----------|-------|--------|-------------|
| `develop` | develop-automation.yml | ✅ All | ❌ None | ✅ to main |
| `release/*` | release-automation.yml | ✅ All | ✅ PyPI | ✅ to main |
| `hotfix/*` | hotfix-automation.yml | ✅ All | ✅ PyPI | ✅ to main |
| `main` | ci.yml | ✅ All | ❌ None | ❌ None |
| `feature/*` | ci.yml | ✅ All | ❌ None | ❌ None |

### Main Branch Protection Rules (Recommended)

Configure in GitHub repository Settings → Branches → Branch protection rules:

- [x] **Require a pull request before merging**
- [x] **Require approvals**
- [x] **Require status checks to pass**
- [x] **Do not allow bypassing the above settings**

### Test Environment

- **Python versions**: 3.10, 3.11, 3.12, 3.13
- **OS platforms**: ubuntu-latest, windows-latest, macos-latest
- **System dependencies**: fd, ripgrep
- **Quality checks**: mypy, black, ruff, isort, bandit, pydocstyle

See [CI/CD Overview](ci-cd-overview.md) for details.

## Release Management

### Versioning
- Follow semantic versioning
- Major version bump for breaking changes

### Release Notes
- Update `CHANGELOG.md`
- Substantial changes (public API, MCP tools, `ast_cache` schema, CLI↔MCP parity,
  or any locked design decision) go through the **RFC process** — see [`rfcs/`](../rfcs/).
  This supersedes the old `openspec/` and `.kiro/specs/` workflows, which have been removed.

## Documentation Structure

The repository keeps a small, code-aligned doc set. Start from the indexes rather
than memorizing file paths:

- **[`docs/README.md`](README.md)** — index of every guide (installation, CLI, features, architecture, testing, CI/CD).
- **[`AGENTS.md`](../AGENTS.md)** + **[`docs/CODEMAPS/`](CODEMAPS/)** — agent-facing topology maps (MCP tools, CLI, languages, formatters, security), kept in sync with the registries by `scripts/codemap-sync-check.sh`.
- **[`rfcs/`](../rfcs/)** — design proposals for substantial changes.

```
tree-sitter-analyzer/
├── README.md / CHANGELOG.md / CLAUDE.md / AGENTS.md   # entry points & agent rules
├── GITFLOW.md · SECURITY.md · CODE_OF_CONDUCT.md      # governance (+ _ja / _zh translations)
├── docs/            # user & developer guides — see docs/README.md
│   └── CODEMAPS/    # registry-synced topology maps
├── rfcs/            # design proposals (RFC process)
└── tests/           # test suite + golden masters
```

## Related Documentation

### Development Guides
- [New Language Support Checklist](new-language-support-checklist.md) ⭐
- [Testing Guidelines](TESTING.md)

### CI/CD
- [CI/CD Overview](ci-cd-overview.md)
- [CI/CD Troubleshooting](ci-cd-troubleshooting.md)
