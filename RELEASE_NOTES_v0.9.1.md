# Release Notes v0.9.1 - MCP Tools Unification

## 🎯 Major Feature: Superior MCP Tools Workflow Design

This release introduces a **revolutionary MCP tools unification** that solves LLM token limit problems with an intuitive 3-step workflow.

### 🔧 Unified Tool Names (Superior Design)

| Tool Name | Purpose | When to Use |
|-----------|---------|-------------|
| `check_code_scale` | **STEP 1:** Check file scale and complexity | Always use FIRST for any code file |
| `analyze_code_structure` | **STEP 2:** Generate structure tables with line positions | Use when file is large (>100 lines) |
| `extract_code_section` | **STEP 3:** Extract specific code sections | Use line positions from structure table |

### 🎉 Key Advantages

#### ✅ **Clear Workflow Guidance**
- Step-by-step process prevents LLM confusion
- Each tool description includes usage timing
- Emoji indicators for easy recognition

#### ✅ **Consistent Parameter Naming**
- All parameters use `snake_case` convention
- `file_path` (not `filepath` or `filePath`)
- `start_line`, `end_line` (not `startLine`, `endLine`)
- `format_type` (not `formatType`)

#### ✅ **Enhanced Error Messages**
- Clear tool availability information
- Helpful parameter validation
- Specific usage guidance

#### ✅ **Simplified Codebase**
- Removed backward compatibility complexity
- Clean, maintainable tool definitions
- Focused on LLM usability

### 🧪 Test Results

**All tests passing:** ✅ **306 tests**
- 138 MCP tests: All passed
- 120 Core functionality tests: All passed  
- 48 CLI/API tests: All passed

### 📖 Documentation Updates

- **README.md**: Updated with unified workflow examples
- **CHANGELOG.md**: Detailed improvement documentation
- **Parameter Guide**: Clear naming standards
- **Usage Examples**: Step-by-step workflow demonstrations

### 🚀 Benefits for LLM Integration

1. **Eliminates Confusion**: Clear tool selection with numbered steps
2. **Prevents Errors**: Consistent parameter naming reduces mistakes
3. **Improves Efficiency**: Targeted code extraction saves tokens
4. **Enhances UX**: Intuitive workflow for AI assistants

### 💡 Example Workflow

```json
// STEP 1: Check file scale
{"tool": "check_code_scale", "parameters": {"file_path": "src/BigFile.java"}}

// STEP 2: Get structure (if file is large)  
{"tool": "analyze_code_structure", "parameters": {"file_path": "src/BigFile.java"}}

// STEP 3: Extract specific code
{"tool": "extract_code_section", "parameters": {"file_path": "src/BigFile.java", "start_line": 45, "end_line": 67}}
```

### 🔄 Migration Guide

**No breaking changes for core functionality** - only MCP tool names are unified.

**Old tool names removed:**
- `analyze_code_scale` → `check_code_scale`
- `read_code_partial` → `extract_code_section`
- `format_table` → `analyze_code_structure`

### 📦 Installation

```bash
pip install tree-sitter-analyzer==0.9.1
```

### 🎯 Why This Design is Superior

This implementation prioritizes **LLM usability** with:
- Clear step-by-step workflow
- Consistent naming patterns
- Comprehensive usage guidance
- Simplified tool selection

**Perfect for AI assistants working with large codebases!** 🤖✨

---

**Full Changelog**: [CHANGELOG.md](CHANGELOG.md)  
**GitHub Release**: https://github.com/aimasteracc/tree-sitter-analyzer/releases/tag/v0.9.1
