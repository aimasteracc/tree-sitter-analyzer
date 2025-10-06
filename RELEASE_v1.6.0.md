# Release v1.6.0 - Enterprise Python Support & File Output

## 📅 Release Date
January 20, 2025

## 🎯 Release Type
Minor Version Release (1.5.0 → 1.6.0)

## 📝 Release Summary

This release introduces enterprise-grade Python language support matching Java and JavaScript capabilities, along with powerful file output functionality for the `analyze_code_structure` tool.

## 🆕 New Features

### 1. Enterprise-Grade Python Support
- **Advanced Analysis**: Full class hierarchy detection, inheritance tracking, decorators, and comprehensive method analysis
- **Type System**: Complete support for type hints, annotations, generics, Protocol, TypedDict
- **Framework Detection**: Django, Flask, FastAPI framework-specific analysis patterns
- **Comprehensive Queries**: 20+ specialized query types for Python code elements
- **Dedicated Formatter**: Python-specific table formatter with class-based organization

### 2. File Output Feature
- **Automatic Format Detection**: Smart extension detection based on content type
- **Multiple Formats**: JSON, CSV, Markdown, and Text output formats
- **Configurable Output Path**: Environment variable or project root-based configuration
- **Security Validation**: Safe file writing with boundary checks
- **MCP Integration**: Seamless integration with analyze_code_structure tool

### 3. Enhanced Output Formats
- **JSON Export**: Structured data export for programmatic processing
- **Flexible Selection**: Choose between Text, JSON, CSV, and Markdown formats
- **API Compatibility**: Consistent output format across CLI and MCP interfaces

## 📊 Quality Metrics

- **Test Count**: 1,869+ tests (up from 1,797)
- **Code Coverage**: 71.90%+ (comprehensive coverage across all new features)
- **New Test Suites**: 
  - 264 tests for file output manager
  - 175 tests for enhanced table format tool
- **Zero Breaking Changes**: Full backward compatibility maintained

## 🔧 Technical Details

### Files Modified
- 18 files changed
- 2,919 additions
- 250 deletions

### Key Components
- `tree_sitter_analyzer/languages/python_plugin.py` - Enhanced Python language support
- `tree_sitter_analyzer/formatters/python_formatter.py` - New Python formatter
- `tree_sitter_analyzer/mcp/utils/file_output_manager.py` - New file output manager
- `tree_sitter_analyzer/mcp/tools/table_format_tool.py` - Enhanced with file output
- `tree_sitter_analyzer/queries/python.py` - Comprehensive Python queries

### New Test Files
- `tests/mcp/test_tools/test_file_output_manager.py` - 264 tests
- `tests/mcp/test_tools/test_table_format_tool.py` - 175 tests

## 📚 Documentation Updates

### New Documentation
- `FILE_OUTPUT_FEATURE_SUMMARY.md` - Complete file output feature guide
- `PYTHON_SUPPORT_SUMMARY.md` - Python language support documentation
- `examples/file_output_demo.py` - Interactive demonstration script

### Updated Documentation
- `README.md` - English version with v1.6.0 features
- `README_zh.md` - Chinese version with v1.6.0 features
- `README_ja.md` - Japanese version with v1.6.0 features
- `CHANGELOG.md` - Detailed release notes

## 🚀 Usage Examples

### Enhanced Python Analysis
```bash
# Analyze Python files with full enterprise support
uv run python -m tree_sitter_analyzer examples/sample.py --language python --advanced

# Generate detailed structure tables
uv run python -m tree_sitter_analyzer examples/sample.py --language python --table full
```

### File Output Feature
```bash
# Save analysis results to file
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --output-file analysis_report

# Specify output format
uv run python -m tree_sitter_analyzer examples/BigService.java --table=json --output-file data.json
```

### MCP Tool Usage
```json
{
  "tool": "analyze_code_structure",
  "arguments": {
    "file_path": "src/BigService.java",
    "format_type": "json",
    "output_file": "analysis_report"
  }
}
```

## 🔄 Upgrade Instructions

### From v1.5.x to v1.6.0

1. **Update Package**:
   ```bash
   pip install --upgrade tree-sitter-analyzer
   # or
   uv add tree-sitter-analyzer@1.6.0
   ```

2. **No Configuration Changes Required**: All existing configurations work seamlessly

3. **Optional**: Configure file output path:
   ```json
   {
     "env": {
       "TREE_SITTER_OUTPUT_PATH": "/path/to/output/directory"
     }
   }
   ```

4. **Verify Installation**:
   ```bash
   python -c "import tree_sitter_analyzer; print(tree_sitter_analyzer.__version__)"
   ```

## 🔗 Links

- **GitHub Release**: https://github.com/aimasteracc/tree-sitter-analyzer/releases/tag/v1.6.0
- **PyPI Package**: https://pypi.org/project/tree-sitter-analyzer/1.6.0/
- **Documentation**: https://github.com/aimasteracc/tree-sitter-analyzer#readme
- **Changelog**: https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CHANGELOG.md

## 🙏 Acknowledgments

Special thanks to all contributors and users who provided feedback and helped shape this release.

## 📞 Support

- **Issues**: https://github.com/aimasteracc/tree-sitter-analyzer/issues
- **Discussions**: https://github.com/aimasteracc/tree-sitter-analyzer/discussions
- **Email**: aimasteracc@gmail.com

---

**🎉 Enjoy the enhanced Python support and file output capabilities!**
