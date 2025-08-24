# GitFlow Branch Strategy

This document describes the GitFlow branch strategy implemented for the tree-sitter-analyzer project.

## GitFlow Diagram

```mermaid
gitGraph
    commit id: "Initial commit"
    branch develop
    commit id: "dev-1"
    
    branch feature/my-feature
    commit id: "feat-1"
    commit id: "feat-2"
    
    checkout develop
    merge feature/my-feature id: "merge-feat"
    
    branch release/v1.0.0
    commit id: "release-prep"
    
    checkout main
    merge release/v1.0.0 tag: "v1.0.0"
    
    checkout develop
    merge release/v1.0.0
    
    checkout main
    branch hotfix/critical-fix
    commit id: "fix-bug"
    
    checkout main
    merge hotfix/critical-fix tag: "v1.0.1"
    
    checkout develop
    merge hotfix/critical-fix
```

## Branch Structure

### Main Branches

- **`main`**: Production-ready code. Always contains the latest stable release.
- **`develop`**: Integration branch for features. Contains the latest delivered development changes.

### Supporting Branches

- **`feature/*`**: Feature development branches. Branch from `develop`, merge back to `develop`.
- **`release/*`**: Release preparation branches. Branch from `develop`, merge to both `main` and `develop`.
- **`hotfix/*`**: Critical bug fixes for production. Branch from `main`, merge to both `main` and `develop`.

## Workflow

### Feature Development

1. **Create feature branch** from `develop`:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-feature-name
   ```

2. **Develop your feature** with regular commits:
   ```bash
   git add .
   git commit -m "feat: Add new feature"
   ```

3. **Push feature branch** and create pull request:
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Merge to develop** after code review and CI passes.

### Release Process

#### Automated Release (Recommended)

The project now uses an **automated release process** from the `develop` branch:

1. **Develop branch updates** trigger automatic:
   - ✅ Test execution
   - ✅ PyPI deployment
   - ✅ README statistics update
   - ✅ Pull request creation to main

2. **Manual review and merge** of the automated PR to main

3. **GitHub release creation** with proper versioning

#### Manual Release Process

For manual releases:

1. **Create release branch** from `develop`:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b release/v1.0.0
   ```

2. **Update version** in `pyproject.toml`:
   ```toml
   version = "1.0.0"
   ```

3. **Update documentation**:
   ```bash
   uv run python scripts/improved_readme_updater.py
   ```

4. **Commit changes**:
   ```bash
   git add .
   git commit -m "chore: Prepare release v1.0.0"
   ```

5. **Merge to main and develop**:
   ```bash
   git checkout main
   git merge release/v1.0.0
   git tag -a v1.0.0 -m "Release v1.0.0"
   git push origin main --tags
   
   git checkout develop
   git merge release/v1.0.0
   git push origin develop
   ```

6. **Delete release branch**:
   ```bash
   git branch -d release/v1.0.0
   git push origin --delete release/v1.0.0
   ```

### Hotfix Process

1. **Create hotfix branch** from `main`:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b hotfix/critical-bug-fix
   ```

2. **Fix the issue** and commit:
   ```bash
   git add .
   git commit -m "fix: Critical bug fix"
   ```

3. **Update version** for hotfix:
   ```bash
   # Update pyproject.toml version (e.g., 1.0.0 -> 1.0.1)
   ```

4. **Merge to main and develop**:
   ```bash
   git checkout main
   git merge hotfix/critical-bug-fix
   git tag -a v1.0.1 -m "Hotfix v1.0.1"
   git push origin main --tags
   
   git checkout develop
   git merge hotfix/critical-bug-fix
   git push origin develop
   ```

5. **Delete hotfix branch**:
   ```bash
   git branch -d hotfix/critical-bug-fix
   git push origin --delete hotfix/critical-bug-fix
   ```

## Automation Features

### Develop Branch Automation

When code is pushed to `develop`, the following happens automatically:

1. **Test Execution**: All tests are run to ensure quality
2. **PyPI Deployment**: Package is built and deployed to PyPI
3. **README Update**: Statistics are automatically updated
4. **PR Creation**: Pull request is created to main branch

### Main Branch Protection

The `main` branch is protected with:

- ✅ **Required status checks**: All CI jobs must pass
- ✅ **Required pull request reviews**: At least 1 approval required
- ✅ **Branch up-to-date requirement**: Must be up-to-date with base branch
- ✅ **Conversation resolution**: All review comments must be resolved

### Automated Release Script

Use the automated release script for manual releases:

```bash
# Dry run to see what would happen
uv run python scripts/automated_release.py --dry-run

# Execute release with new version
uv run python scripts/automated_release.py --version 1.1.0

# Execute release with current version
uv run python scripts/automated_release.py
```

## Best Practices

### Commit Messages

Use conventional commit format:

- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `style:` Code style changes (formatting, etc.)
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

### Branch Naming

- `feature/descriptive-name`: Feature branches
- `release/v1.0.0`: Release branches
- `hotfix/critical-fix`: Hotfix branches

### Quality Checks

Before merging to `develop`:

1. **Run tests locally**:
   ```bash
   uv run pytest tests/ -v
   ```

2. **Check code quality**:
   ```bash
   uv run python check_quality.py --new-code-only
   ```

3. **Update documentation** if needed:
   ```bash
   uv run python scripts/improved_readme_updater.py
   ```

### Version Management

- **Semantic Versioning**: MAJOR.MINOR.PATCH
- **Automatic versioning**: Managed by automated release process
- **Version consistency**: All files updated together

## CI/CD Integration

### GitHub Actions Workflows

1. **`ci.yml`**: Main CI pipeline for all branches
2. **`develop-automation.yml`**: Automated release from develop
3. **`branch-protection.yml`**: Main branch protection setup

### Required Secrets

- `PYPI_API_TOKEN`: For PyPI deployment
- `GITHUB_TOKEN`: For repository operations

## Troubleshooting

### Common Issues

1. **Branch protection errors**: Ensure all required checks pass
2. **PyPI deployment failures**: Check API token and package validity
3. **README update failures**: Verify test statistics are accurate

### Manual Override

For emergency situations, repository administrators can:

1. **Bypass branch protection** (use with caution)
2. **Manual PyPI deployment** if automated process fails
3. **Force push** to main (only in critical situations)

---

**Note**: This GitFlow implementation prioritizes automation and quality assurance while maintaining the flexibility for manual intervention when needed.
