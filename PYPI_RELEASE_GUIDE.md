# PyPI Release Guide for tree-sitter-analyzer v0.9.9

## 📦 Package Ready for Release

✅ **All tests passed**: 1358 tests  
✅ **Package built**: `dist/tree_sitter_analyzer-0.9.4-py3-none-any.whl`  
✅ **Source distribution**: `dist/tree_sitter_analyzer-0.9.4.tar.gz`  
✅ **Documentation updated**: README, CHANGELOG, release notes  
✅ **GitHub released**: Tagged v0.9.4 and pushed  

## 🚀 Manual PyPI Release Steps

### Option 1: Using uv (Recommended)

1. **Get PyPI API Token**:
   - Go to https://pypi.org/account/register/ (create account if needed)
   - Go to https://pypi.org/manage/account/token/
   - Create a new API token with scope "Entire account"
   - Copy the token (starts with `pypi-`)

2. **Set Environment Variable**:
   ```bash
   # Windows
   set UV_PUBLISH_TOKEN=pypi-your-token-here
   
   # Linux/Mac
   export UV_PUBLISH_TOKEN=pypi-your-token-here
   ```

3. **Upload to PyPI**:
   ```bash
   uv publish
   ```

### Option 2: Using twine

1. **Install twine**:
   ```bash
   uv add --dev twine
   ```

2. **Upload to PyPI**:
   ```bash
   uv run twine upload dist/*
   ```
   - Enter username: `__token__`
   - Enter password: `pypi-your-token-here`

### Option 3: Test PyPI First (Recommended)

1. **Upload to Test PyPI**:
   ```bash
   uv publish --publish-url https://test.pypi.org/legacy/ --token pypi-your-test-token
   ```

2. **Test Installation**:
   ```bash
   pip install --index-url https://test.pypi.org/simple/ tree-sitter-analyzer==0.9.9
   ```

3. **If successful, upload to production PyPI**:
   ```bash
   uv publish --token pypi-your-production-token
   ```

## 📋 Pre-Release Checklist

- [x] All tests pass (1358/1358)
- [x] Version updated in pyproject.toml (0.9.4)
- [x] Version updated in __init__.py (0.9.4)
- [x] CHANGELOG.md updated
- [x] README.md updated
- [x] Release notes created
- [x] Git tagged and pushed
- [x] Package built successfully
- [x] Package integrity verified

## 🎯 Release Highlights

### MCP Tools Unification
- **check_code_scale**: STEP 1 - Check file scale and complexity
- **analyze_code_structure**: STEP 2 - Generate structure tables with line positions  
- **extract_code_section**: STEP 3 - Extract specific code sections

### Key Benefits
- Clear 3-step workflow for LLMs
- Consistent snake_case parameter naming
- Enhanced error messages and guidance
- Simplified codebase (removed backward compatibility)
- 1358 comprehensive tests

## 📊 Test Results Summary

```
MCP Tests:           103 passed ✅
Core Tests:          168 passed ✅  
MCP Server Tests:     35 passed ✅
Total:               1358 passed ✅
```

## 🔗 Post-Release Actions

After successful PyPI upload:

1. **Verify Installation**:
   ```bash
   pip install tree-sitter-analyzer==0.9.9
   python -c "import tree_sitter_analyzer; print(tree_sitter_analyzer.__version__)"
   ```

2. **Update Documentation**:
   - Update installation instructions
   - Announce on relevant channels
   - Update project status

3. **GitHub Release**:
   - Create GitHub release from tag v0.9.4
   - Attach release notes
   - Include built packages

## 🎉 Ready to Release!

The package is fully tested and ready for PyPI release. All 1358 tests pass, documentation is complete, and the MCP tools unification provides significant improvements for LLM integration.

**This release represents a major improvement in usability for AI assistants working with large codebases!**
