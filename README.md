# Tree-sitter Analyzer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1358%20passed-brightgreen.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-74.82%25-green.svg)](#testing)
[![Quality](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#quality)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

**Solve the LLM token limit problem for large code files.**

An extensible multi-language code analyzer that helps AI assistants understand code structure without reading entire files. Get code overview, extract specific sections, and analyze complexity - all optimized for LLM workflows.

If you find this project useful, please consider giving it a ⭐ on GitHub to support development.

### Quick links
- Prompts for AI IDEs: [jump](#ai-ide-prompts)

## ✨ Why Tree-sitter Analyzer?

**The Problem:** Large code files exceed LLM token limits, making code analysis inefficient or impossible.

**The Solution:** Smart code analysis that provides:
- 📊 **Code overview** without reading complete files
- 🎯 **Targeted extraction** of specific line ranges  
- 📍 **Precise positioning** for accurate code operations
- 🤖 **AI assistant integration** via MCP protocol

## 🚀 Quick Start (5 minutes)

### For AI Assistant Users (Claude Desktop)

1. **Install the package:**
```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# or: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# No need to install the package separately - uv handles it
```

2. **Configure Claude Desktop:**

Add to your Claude Desktop config file:

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux:** `~/.config/claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", 
        "--with", 
        "tree-sitter-analyzer[mcp]",
        "python", 
        "-m", 
        "tree_sitter_analyzer.mcp.server"
      ]
    }
  }
}
```

3. **Restart Claude Desktop** and start analyzing code!

### For CLI Users

```bash
# Install with uv (recommended)
uv add "tree-sitter-analyzer[popular]"

# Step 1: Check file scale
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text

# Step 2: Analyze structure (for large files)
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full

# Step 3: Extract specific lines
uv run python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
```

## 🛠️ Core Features

### 1. Code Structure Analysis
Get comprehensive overview without reading entire files:
- Classes, methods, fields count
- Package information
- Import dependencies
- Complexity metrics

### 2. Targeted Code Extraction
Extract specific code sections efficiently:
- Line range extraction
- Precise positioning data
- Content length information

### 3. AI Assistant Integration
Three-step workflow MCP tools for AI assistants:
- `check_code_scale` - **Step 1:** Get code metrics and complexity
- `analyze_code_structure` - **Step 2:** Generate detailed structure tables with line positions
- `extract_code_section` - **Step 3:** Extract specific code sections by line range

### 4. Multi-Language Support
- **Java** - Full support with advanced analysis
- **Python** - Complete support
- **JavaScript/TypeScript** - Full support
- **C/C++, Rust, Go** - Basic support

## 📖 Usage Examples

<a id="ai-ide-prompts"></a>
### Prompts for AI IDEs (Cursor, Roo Code, Claude Desktop)

Copy these prompts into your AI IDE chat. They guide the assistant to use the MCP tools correctly and safely.

1) Check file scale and complexity
```
Use the MCP tool "check_code_scale" on "examples/Sample.java".
Return: language, total_lines, non_empty_lines, comment_lines, bytes, and a short note if the file likely needs table/structure analysis.
Important: If the path is relative, resolve it against ${workspaceFolder} (project root). Use snake_case argument names.
```

2) Generate structure table (for large files)
```
Use the MCP tool "analyze_code_structure" with:
  {"file_path": "examples/Sample.java", "format_type": "full"}
Return a compact markdown table (classes/methods/fields/imports with start_line/end_line). Keep the table readable in chat. If the file is very large, summarize long sections.
```

3) Extract specific lines (surgery-safe snippet)
```
Use the MCP tool "extract_code_section" with:
  {"file_path": "examples/Sample.java", "start_line": 84, "end_line": 86}
Return a fenced code block with the correct language, and include the exact line numbers in plain text above the block. Do not modify code content.
```

Notes
- Always use snake_case parameter names: `file_path`, `start_line`, `end_line`, `format_type`.
- Relative paths are resolved to the project root (secured boundary). Files outside the boundary must be rejected with a clear message.

### CLI Usage

**Step 1: Basic analysis (Check file scale):**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text
```

**Step 2: Structure analysis (For large files that exceed LLM limits):**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full
```

**Step 3: Targeted extraction (Read specific code sections):**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
```

**Additional Options:**
```bash
# Quiet mode (suppress INFO messages, show only errors)
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text --quiet

# Table output with quiet mode
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full --quiet
```

## 🔧 Installation Options

### For End Users
```bash
# Basic installation
uv add tree-sitter-analyzer

# With popular languages (Java, Python, JS, TS)
uv add "tree-sitter-analyzer[popular]"

# With MCP server support
uv add "tree-sitter-analyzer[mcp]"

# Full installation
uv add "tree-sitter-analyzer[all,mcp]"
```

### For Developers
```bash
# Clone and install for development
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

## 📚 Documentation

- **[MCP Setup Guide for Users](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/MCP_SETUP_USERS.md)** - Simple setup for AI assistant users
- **[MCP Setup Guide for Developers](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/MCP_SETUP_DEVELOPERS.md)** - Local development configuration
- **[Project Root Configuration](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/PROJECT_ROOT_CONFIG.md)** - Complete configuration reference
- **[API Documentation](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/docs/api.md)** - Detailed API reference
- **[Contributing Guide](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CONTRIBUTING.md)** - How to contribute

### 🔒 Project Root Configuration

Tree-sitter-analyzer automatically detects and secures your project boundaries:

- **Auto-detection**: Finds project root from `.git`, `pyproject.toml`, `package.json`, etc.
- **CLI**: Use `--project-root /path/to/project` for explicit control
- **MCP**: Set `TREE_SITTER_PROJECT_ROOT=${workspaceFolder}` for workspace integration
- **Security**: Only analyzes files within project boundaries

**Recommended MCP configuration:**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "--with", "tree-sitter-analyzer[mcp]", "python", "-m", "tree_sitter_analyzer.mcp.server"],
      "env": {"TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}"}
    }
  }
}
```

## 🧪 Testing & Quality

This project maintains **enterprise-grade quality** with comprehensive testing:

### 📊 Quality Metrics
- **1358 tests** - 100% pass rate ✅
- **74.82% code coverage** - Industry standard quality
- **Zero test failures** - Complete CI/CD readiness
- **Cross-platform compatibility** - Windows, macOS, Linux

### 🏆 Recent Quality Achievements (v0.8.2)
- ✅ **Complete test suite stabilization** - Fixed all 31 failing tests
- ✅ **Formatters module breakthrough** - 0% → 42.30% coverage
- ✅ **Error handling improvements** - 61.64% → 82.76% coverage
- ✅ **104 new comprehensive tests** across critical modules

### 🔧 Running Tests
```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage report
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

# Run specific test categories
uv run pytest tests/test_formatters_comprehensive.py -v
uv run pytest tests/test_core_engine_extended.py -v
uv run pytest tests/test_mcp_server_initialization.py -v
```

### 📈 Coverage Highlights
- **Formatters**: 42.30% (newly established)
- **Error Handler**: 82.76% (major improvement)
- **Language Detector**: 98.41% (excellent)
- **CLI Main**: 97.78% (excellent)
- **Security Framework**: 78%+ across all modules

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CONTRIBUTING.md) for details.

### 🤖 AI/LLM Collaboration

This project supports AI-assisted development with specialized quality controls:

```bash
# For AI systems - run before generating code
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all

# For AI-generated code review
uv run python llm_code_checker.py path/to/new_file.py
```

📖 **See our [AI Collaboration Guide](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/AI_COLLABORATION_GUIDE.md) and [LLM Coding Guidelines](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/LLM_CODING_GUIDELINES.md) for detailed instructions on working with AI systems.**

---

**Made with ❤️ for developers who work with large codebases and AI assistants.**
