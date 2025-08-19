# GitFlow Branch Strategy

This document describes the GitFlow branch strategy implemented for the tree-sitter-analyzer project.

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

1. **Create feature branch**:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-feature-name
   ```

2. **Develop and commit**:
   ```bash
   # Make your changes
   git add .
   git commit -m "feat: add new feature"
   ```

3. **Push and create PR**:
   ```bash
   git push -u origin feature/your-feature-name
   # Create PR to develop branch
   ```

4. **Merge to develop**:
   - After code review and CI checks pass
   - Merge PR to `develop` branch

### Release Process

1. **Create release branch**:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b release/v1.0.0
   ```

2. **Prepare release**:
   - Update version in `pyproject.toml`
   - Update `CHANGELOG.md`
   - Update README files if needed
   - Run tests and quality checks

3. **Commit and push**:
   ```bash
   git add .
   git commit -m "chore: prepare release v1.0.0"
   git push -u origin release/v1.0.0
   ```

4. **Create GitHub release**:
   ```bash
   gh release create v1.0.0 --title "v1.0.0 - Release Title" --notes "Release notes"
   ```

5. **Merge to main and develop**:
   ```bash
   git checkout main
   git merge release/v1.0.0
   git push origin main
   
   git checkout develop
   git merge release/v1.0.0
   git push origin develop
   ```

6. **Clean up**:
   ```bash
   git branch -d release/v1.0.0
   git push origin --delete release/v1.0.0
   ```

### Hotfix Process

1. **Create hotfix branch**:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b hotfix/critical-bug-fix
   ```

2. **Fix the issue**:
   - Make minimal changes to fix the critical bug
   - Update version (patch increment)
   - Update `CHANGELOG.md`

3. **Commit and push**:
   ```bash
   git add .
   git commit -m "fix: critical bug fix"
   git push -u origin hotfix/critical-bug-fix
   ```

4. **Create PR to main**:
   - Create PR from hotfix branch to `main`
   - After review and CI checks pass, merge to `main`

5. **Merge to develop**:
   ```bash
   git checkout develop
   git merge hotfix/critical-bug-fix
   git push origin develop
   ```

6. **Create GitHub release**:
   ```bash
   gh release create v1.0.1 --title "v1.0.1 - Critical Bug Fix" --notes "Hotfix release"
   ```

7. **Clean up**:
   ```bash
   git branch -d hotfix/critical-bug-fix
   git push origin --delete hotfix/critical-bug-fix
   ```

## Best Practices

### Commit Messages

Use conventional commit format:
- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation changes
- `style:` for formatting changes
- `refactor:` for code refactoring
- `test:` for adding tests
- `chore:` for maintenance tasks

### Branch Naming

- **Feature branches**: `feature/descriptive-name`
- **Release branches**: `release/v1.0.0`
- **Hotfix branches**: `hotfix/descriptive-name`

### Quality Checks

Before merging any branch:
1. All tests must pass
2. Code quality checks must pass (Black, Ruff, MyPy)
3. README statistics must be up to date
4. Documentation must be updated if needed

### Version Management

- **Major version**: Breaking changes
- **Minor version**: New features (backward compatible)
- **Patch version**: Bug fixes (backward compatible)

## CI/CD Integration

The project uses GitHub Actions for continuous integration:

- **Push to any branch**: Runs tests and quality checks
- **PR to develop**: Full CI pipeline
- **PR to main**: Full CI pipeline + release preparation
- **Tag creation**: Automatic PyPI release (if configured)

## Current Status

- ✅ **Main branch**: Production-ready code
- ✅ **Develop branch**: Integration branch for features
- ✅ **GitFlow workflow**: Implemented and documented
- ✅ **CI/CD pipeline**: Fully functional
- ✅ **Release process**: Automated with GitHub releases

## Next Steps

1. **Feature development**: Use `feature/*` branches from `develop`
2. **Release preparation**: Use `release/*` branches
3. **Critical fixes**: Use `hotfix/*` branches from `main`
4. **Regular releases**: Follow the release process documented above
