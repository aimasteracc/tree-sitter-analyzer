# PyPI Upload Commands for tree-sitter-analyzer v0.9.1

## 📦 Package Ready for Upload

✅ **Built packages:**
- `dist/tree_sitter_analyzer-0.9.1-py3-none-any.whl`
- `dist/tree_sitter_analyzer-0.9.1.tar.gz`

✅ **Package integrity verified:** All checks passed

## 🚀 Upload Commands

### Option 1: Using uv (Recommended)

```bash
# Set your PyPI API token
set UV_PUBLISH_TOKEN=pypi-your-token-here

# Upload to PyPI
uv publish
```

### Option 2: Using twine

```bash
# Install twine if not already installed
uv add --dev twine

# Upload to PyPI
uv run twine upload dist/*
# When prompted:
# Username: __token__
# Password: pypi-your-token-here
```

### Option 3: Test PyPI First (Recommended)

```bash
# Upload to Test PyPI first
uv publish --publish-url https://test.pypi.org/legacy/ --token pypi-your-test-token

# Test installation
pip install --index-url https://test.pypi.org/simple/ tree-sitter-analyzer==0.9.1

# If successful, upload to production PyPI
uv publish --token pypi-your-production-token
```

## 🔑 Getting PyPI API Token

1. **Create PyPI Account**: https://pypi.org/account/register/
2. **Generate API Token**: https://pypi.org/manage/account/token/
3. **Token Scope**: Select "Entire account" or specific project
4. **Copy Token**: Starts with `pypi-`

## ✅ Pre-Upload Verification

- [x] All 306 tests passed
- [x] Package built successfully
- [x] Package integrity verified
- [x] Version updated to 0.9.1
- [x] Documentation updated
- [x] GitHub tagged and pushed

## 🎯 Post-Upload Verification

After successful upload, verify:

```bash
# Install from PyPI
pip install tree-sitter-analyzer==0.9.1

# Verify version
python -c "import tree_sitter_analyzer; print(tree_sitter_analyzer.__version__)"

# Test MCP tools
python -c "from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer; print('MCP tools ready!')"
```

## 📊 Release Summary

**Version:** 0.9.1  
**Major Feature:** MCP Tools Unification  
**Test Results:** 306/306 passed ✅  
**Key Tools:**
- `check_code_scale` - STEP 1: Check file scale
- `analyze_code_structure` - STEP 2: Generate structure tables  
- `extract_code_section` - STEP 3: Extract code sections

**Ready for production release!** 🚀
