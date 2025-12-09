# CI/CD Secrets Reference

## Overview

This document provides a comprehensive reference for all secrets and environment variables used in the tree-sitter-analyzer CI/CD workflows.

## Required Secrets

### 1. CODECOV_TOKEN

**Purpose**: Upload test coverage reports to Codecov

**Used By**:
- develop-automation.yml
- release-automation.yml
- hotfix-automation.yml
- ci.yml

**How to Obtain**:
1. Visit https://codecov.io/
2. Sign in with GitHub account
3. Navigate to the tree-sitter-analyzer repository
4. Go to Settings → General
5. Copy the repository upload token

**How to Set**:
1. Go to GitHub repository Settings
2. Navigate to Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `CODECOV_TOKEN`
5. Value: Paste the token from Codecov
6. Click "Add secret"

**Failure Impact**: Coverage reports won't be uploaded, but workflows will continue (non-blocking)

### 2. PYPI_API_TOKEN

**Purpose**: Deploy packages to PyPI

**Used By**:
- release-automation.yml
- hotfix-automation.yml

**How to Obtain**:
1. Visit https://pypi.org/
2. Sign in to your account
3. Go to Account settings → API tokens
4. Click "Add API token"
5. Name: `tree-sitter-analyzer-deploy`
6. Scope: Select "Project: tree-sitter-analyzer"
7. Click "Add token"
8. Copy the token (starts with `pypi-`)

**How to Set**:
1. Go to GitHub repository Settings
2. Navigate to Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `PYPI_API_TOKEN`
5. Value: Paste the token from PyPI
6. Click "Add secret"

**Failure Impact**: Deployment to PyPI will fail (blocking for release/hotfix workflows)

**Security Notes**:
- Never commit this token to version control
- Rotate token if compromised
- Use project-scoped tokens (not account-wide)
- Store securely in GitHub Secrets only

### 3. GITHUB_TOKEN

**Purpose**: Create pull requests and interact with GitHub API

**Used By**:
- develop-automation.yml
- release-automation.yml
- hotfix-automation.yml

**How to Obtain**: Automatically provided by GitHub Actions (no manual setup required)

**Permissions Required**:
```yaml
permissions:
  contents: write
  pull-requests: write
```

**Failure Impact**: PR creation will fail (blocking)

**Notes**:
- Automatically available in all workflows
- Permissions are set in workflow files
- No manual configuration needed

## Environment Variables

### Workflow-Level Variables

#### PYTHON_VERSION

**Purpose**: Specify Python version for quality checks and coverage

**Default**: `3.11`

**Used By**: All workflows

**Configuration**:
```yaml
inputs:
  python-version:
    default: '3.11'
    type: string
```

#### UV_SYSTEM_PYTHON

**Purpose**: Configure uv to use system Python

**Default**: `1`

**Used By**: All workflows

**Configuration**:
```yaml
env:
  UV_SYSTEM_PYTHON: 1
```

### Test Matrix Variables

#### matrix.os

**Purpose**: Operating system for test execution

**Values**:
- `ubuntu-latest`
- `windows-latest`
- `macos-latest`

**Used By**: All test jobs

#### matrix.python-version

**Purpose**: Python version for test execution

**Values**:
- `"3.10"`
- `"3.11"`
- `"3.12"`
- `"3.13"`

**Used By**: All test jobs

## Secret Management Best Practices

### Security Guidelines

1. **Never Commit Secrets**
   - Never commit secrets to version control
   - Use `.gitignore` for local secret files
   - Use GitHub Secrets for CI/CD

2. **Rotate Regularly**
   - Rotate PYPI_API_TOKEN every 6 months
   - Rotate CODECOV_TOKEN if compromised
   - Update GitHub Secrets after rotation

3. **Limit Scope**
   - Use project-scoped tokens when possible
   - Avoid account-wide tokens
   - Use minimal required permissions

4. **Monitor Usage**
   - Review GitHub Actions logs regularly
   - Monitor for unauthorized access
   - Set up alerts for failed authentications

### Access Control

1. **Repository Settings**
   - Limit who can modify secrets
   - Require admin approval for secret changes
   - Enable audit logging

2. **Branch Protection**
   - Require status checks before merging
   - Require pull request reviews
   - Restrict who can push to protected branches

3. **Workflow Permissions**
   - Use minimal required permissions
   - Explicitly declare permissions in workflows
   - Review permissions regularly

## Troubleshooting

### CODECOV_TOKEN Issues

**Symptom**: Coverage upload fails

**Solutions**:
1. Verify token is set correctly in GitHub Secrets
2. Check token hasn't expired
3. Verify repository is configured in Codecov
4. Check Codecov service status

**Workaround**: Coverage upload failures don't block workflows

### PYPI_API_TOKEN Issues

**Symptom**: Deployment to PyPI fails with 403 Forbidden

**Solutions**:
1. Verify token is set correctly in GitHub Secrets
2. Check token hasn't been revoked
3. Verify token has correct project scope
4. Generate new token if needed

**Workaround**: None - deployment requires valid token

### GITHUB_TOKEN Issues

**Symptom**: PR creation fails with permission errors

**Solutions**:
1. Verify workflow has correct permissions
2. Check branch protection rules
3. Verify GitHub Actions is enabled
4. Check repository settings

**Workaround**: Manually create PR if automated creation fails

## Verification Checklist

Before deploying workflows, verify:

- [ ] CODECOV_TOKEN is set in GitHub Secrets
- [ ] PYPI_API_TOKEN is set in GitHub Secrets (for release/hotfix)
- [ ] GITHUB_TOKEN permissions are configured in workflows
- [ ] All secrets are valid and not expired
- [ ] Repository is configured in Codecov
- [ ] PyPI project exists and token has access
- [ ] Branch protection rules are configured
- [ ] GitHub Actions is enabled for repository

## Secret Rotation Procedure

### Rotating CODECOV_TOKEN

1. Generate new token in Codecov
2. Update GitHub Secret with new token
3. Trigger test workflow to verify
4. Revoke old token in Codecov

### Rotating PYPI_API_TOKEN

1. Generate new token in PyPI
2. Update GitHub Secret with new token
3. Test deployment on test release branch
4. Revoke old token in PyPI

### Emergency Revocation

If a secret is compromised:

1. **Immediately revoke** the token in the source service (Codecov/PyPI)
2. **Generate new token** with different name
3. **Update GitHub Secret** with new token
4. **Review logs** for unauthorized usage
5. **Document incident** for future reference

## Related Documentation

- [CI/CD Overview](ci-cd-overview.md)
- [CI/CD Troubleshooting Guide](ci-cd-troubleshooting.md)
- [CI/CD Migration Guide](ci-cd-migration-guide.md)
- [GitHub Actions Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
