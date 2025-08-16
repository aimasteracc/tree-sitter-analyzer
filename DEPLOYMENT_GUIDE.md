# Tree-sitter Analyzer Deployment Guide

This guide explains how to register tree-sitter-analyzer on PyPI and create standalone executable files.

## Table of Contents

1. [PyPI Registration](#pypi-registration)
2. [Creating Standalone Executables](#creating-standalone-executables)
3. [User Installation Instructions](#user-installation-instructions)

## PyPI Registration

### Prerequisites

1. **Create PyPI Accounts**
   - Create account on [PyPI](https://pypi.org/account/register/)
   - Create test account on [TestPyPI](https://test.pypi.org/account/register/)

2. **API Token Setup**
   ```bash
   # Install build tools
   uv add --dev build twine
   
   # Configure authentication (~/.pypirc)
   [distutils]
   index-servers =
       pypi
       testpypi
   
   [pypi]
   username = __token__
   password = <your-pypi-api-token>
   
   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = <your-testpypi-api-token>
   ```

### Upload Process

#### Method 1: Using Automated Script

```bash
# Run upload script (uv unified)
uv run python upload_to_pypi.py
```

This script automatically performs:
- Version validation
- Build package creation
- Test upload to TestPyPI
- Production upload to PyPI
- Cleanup of build artifacts

#### Method 2: Manual Upload

```bash
# 1. Clean previous builds
rm -rf dist/ build/ *.egg-info/

# 2. Build package
uv build

# 3. Test upload to TestPyPI
uv run twine upload --repository testpypi dist/*

# 4. Test installation from TestPyPI
pip install --index-url https://test.pypi.org/simple/ tree-sitter-analyzer

# 5. Upload to production PyPI
uv run twine upload dist/*
```

### Version Management

Update version in `pyproject.toml`:
```toml
[project]
name = "tree-sitter-analyzer"
version = "0.9.5"  # Update this
```

## Creating Standalone Executables

### Using PyInstaller

```bash
# Install PyInstaller
uv add --dev pyinstaller

# Create standalone executable
uv run python build_standalone.py
```

### Build Script Features

The `build_standalone.py` script:
- Creates cross-platform executables
- Includes all necessary dependencies
- Optimizes file size
- Generates distribution packages

### Manual Build Process

```bash
# Create executable
uv run pyinstaller --onefile \
    --name tree-sitter-analyzer \
    --add-data "tree_sitter_analyzer:tree_sitter_analyzer" \
    tree_sitter_analyzer/cli_main.py

# Test executable
./dist/tree-sitter-analyzer examples/Sample.java --advanced
```

## User Installation Instructions

### Standard Installation

```bash
# Basic installation
uv add tree-sitter-analyzer

# With popular languages
uv add "tree-sitter-analyzer[popular]"

# With MCP server support
uv add "tree-sitter-analyzer[mcp]"

# Full installation
uv add "tree-sitter-analyzer[all,mcp]"
```

### Alternative Installation Methods

```bash
# Using pip
pip install tree-sitter-analyzer[popular]

# From source
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

### Verification

```bash
# Test CLI
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced

# Test MCP server
uv run python -m tree_sitter_analyzer.mcp.server
```

## Release Checklist

Before each release:

1. **Update Version**
   - [ ] Update `pyproject.toml` version
   - [ ] Update README statistics: `python scripts/update_readme_stats.py`
   - [ ] Update CHANGELOG.md

2. **Quality Checks**
   - [ ] Run full test suite: `uv run pytest tests/ -v`
   - [ ] Check code quality: `uv run python check_quality.py`
   - [ ] Verify coverage: `uv run pytest tests/ --cov=tree_sitter_analyzer`

3. **Build and Test**
   - [ ] Test build: `uv build`
   - [ ] Test upload to TestPyPI
   - [ ] Test installation from TestPyPI

4. **Release**
   - [ ] Upload to PyPI: `uv run python upload_to_pypi.py`
   - [ ] Create GitHub release
   - [ ] Update documentation

## Troubleshooting

### Common Issues

**Build Failures:**
- Ensure all dependencies are installed: `uv sync --extra all`
- Check Python version compatibility (3.10+)

**Upload Failures:**
- Verify API tokens are correct
- Check if version already exists on PyPI
- Ensure package name is available

**Installation Issues:**
- Clear pip cache: `pip cache purge`
- Use virtual environment
- Check system dependencies

### Getting Help

- Check [GitHub Issues](https://github.com/aimasteracc/tree-sitter-analyzer/issues)
- Review [Contributing Guide](CONTRIBUTING.md)
- Contact maintainers

---

This guide ensures effective distribution of tree-sitter-analyzer to a wide user base.
