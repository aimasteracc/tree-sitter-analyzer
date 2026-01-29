# Design - GitHub Workflow Optimization

## Technology Choices
- **GitHub Actions**: Core automation platform.
- **Composite Actions**: For centralizing setup logic.
- **Astral uv**: Fast Python package installer and resolver.
- **Pytest Markers**: For intelligent test selection.

## Architecture Design

### 1. Unified Setup Action (`.github/actions/setup-analyzer`)
A new composite action that will:
- Checkout code (optional, or assume already done).
- Install `uv`.
- Install Python (versionable).
- Enable `uv` caching.
- Install system dependencies (`fd`, `ripgrep`).
- Set environment variables (UTF-8, etc.).

### 2. Optimized `reusable-quality.yml`
- Use the unified setup action.
- Combine jobs if possible or ensure they share the same cached environment.
- Use `uv sync` once and then run all quality tools.

### 3. Smart `reusable-test.yml`
- Use the unified setup action.
- Fix the marker logic: `not (requires_ripgrep and requires_fd)` is likely wrong. We should just run all tests if we install both.
- Implement "Paths Filter" to skip tests if no code changed (e.g., only docs or workflows changed).

## Implementation Details

### Setup Action Schema
```yaml
inputs:
  python-version: { default: "3.11" }
  os: { required: true }
  install-sys-deps: { default: true }
```

### Path Filtering
Use `actions/labeler` or `dorny/paths-filter` to detect changes in `tree_sitter_analyzer/` and `tests/`.

## Boundary Case Handling
- Handle Windows-specific `choco` vs Linux `apt` differences in the setup action.
- Ensure `CODECOV_TOKEN` is passed correctly in test workflows.
