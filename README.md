# Tree-sitter Analyzer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/1504-brightgreen.svg)](#quality-assurance)
[![Coverage](https://img.shields.io/badge/coverage-74.30%25-green.svg)](#quality-assurance)
[![Quality](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#quality-assurance)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

## 🚀 Break Through LLM Token Limits, Let AI Understand Code Files of Any Size

> **A revolutionary code analysis tool designed for the AI era**

## 📋 Table of Contents

- [🚀 Break Through LLM Token Limits](#-break-through-llm-token-limits-let-ai-understand-code-files-of-any-size)
- [📋 Table of Contents](#-table-of-contents)
- [💡 What Makes This Special](#-what-makes-this-special)
- [📊 Live Demo & Results](#-live-demo--results)
- [🚀 30-Second Quick Start](#-30-second-quick-start)
  - [🤖 For AI Users (Claude Desktop, Cursor, etc.)](#-for-ai-users-claude-desktop-cursor-etc)
  - [💻 For Developers (CLI)](#-for-developers-cli)
- [❓ Why Choose Tree-sitter Analyzer](#-why-choose-tree-sitter-analyzer)
- [📖 Practical Usage Examples](#-practical-usage-examples)
- [🛠️ Core Features](#️-core-features)
- [📦 Installation Guide](#-installation-guide)
- [🔒 Security & Configuration](#-security--configuration)
- [🏆 Quality Assurance](#-quality-assurance)
- [🤖 AI Collaboration Support](#-ai-collaboration-support)
- [📚 Documentation](#-documentation)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

## 💡 What Makes This Special

Imagine: You have a 1,400+ line Java service class that Claude or ChatGPT can't analyze due to token limits. Now, Tree-sitter Analyzer enables AI assistants to:

- ⚡ **Get complete code structure overview in 3 seconds**
- 🎯 **Precisely extract** any line range of code snippets  
- 📍 **Smart positioning** exact locations of classes, methods, fields
- 🔗 **Seamless integration** with Claude Desktop, Cursor, Roo Code and other AI IDEs

**No more AI helplessness due to large files!**

## 📊 Live Demo & Results

### ⚡ **Lightning-Fast Analysis Speed**
```bash
# 1419-line large Java service class analysis result (< 1 second)
Lines: 1419 | Classes: 1 | Methods: 66 | Fields: 9 | Imports: 8
```

### 📊 **Precise Structure Tables**
| Class Name | Type | Visibility | Line Range | Methods | Fields |
|------------|------|------------|------------|---------|--------|
| BigService | class | public | 17-1419 | 66 | 9 |

### 🔄 **AI Assistant Three-Step Workflow**
- **Step 1**: `check_code_scale` - Check file scale and complexity
- **Step 2**: `analyze_code_structure` - Generate detailed structure tables
- **Step 3**: `extract_code_section` - Extract code snippets on demand

---

## 🚀 30-Second Quick Start

### 🤖 For AI Users (Claude Desktop, Cursor, etc.)

**📦 1. One-Click Installation**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**⚙️ 2. Configure AI Client**

**Claude Desktop Configuration:**

Add the following to your config file:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`  
- **Linux**: `~/.config/claude/claude_desktop_config.json`

**Basic Configuration (Recommended):**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ]
    }
  }
}
```

**Advanced Configuration (Specify Project Root):**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project"
      }
    }
  }
}
```

**Other AI Clients:**
- **Cursor**: Built-in MCP support, refer to Cursor documentation for configuration
- **Roo Code**: Supports MCP protocol, check respective configuration guides
- **Other MCP-compatible clients**: Use the same server configuration

**⚠️ Configuration Notes:**
- **Basic Configuration**: Tool will auto-detect project root (recommended)
- **Advanced Configuration**: If you need to specify a particular directory, use absolute path to replace `/absolute/path/to/your/project`
- **Avoid using**: Variables like `${workspaceFolder}` may not be supported in some clients

**🎉 3. Restart AI client and start analyzing massive code files!**

### 💻 For Developers (CLI)

```bash
# Install
uv add "tree-sitter-analyzer[popular]"

# Check file scale (1419-line large service class, instant completion)
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# Generate structure table (1 class, 66 methods, clearly displayed)
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# Precise code extraction
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105
```

---

## ❓ Why Choose Tree-sitter Analyzer

### 🎯 Solving Real Pain Points

**Traditional Approach Dilemmas:**
- ❌ Large files exceed LLM token limits
- ❌ AI cannot understand code structure
- ❌ Manual file splitting required
- ❌ Context loss leads to inaccurate analysis

**Tree-sitter Analyzer's Breakthrough:**
- ✅ **Smart Analysis**: Understand structure without reading complete files
- ✅ **Precise Positioning**: Accurate line-by-line code extraction
- ✅ **AI Native**: Optimized for LLM workflows
- ✅ **Multi-language Support**: Java, Python, JavaScript/TypeScript, etc.

## 📖 Practical Usage Examples

### 💬 AI IDE Prompts (Copy and Use)

#### 🔍 **Step 1: Check File Scale**

**Prompt:**
```
Use MCP tool check_code_scale to analyze file scale
Parameters: {"file_path": "examples/BigService.java"}
```

**Return Format:**
```json
{
  "file_path": "examples/BigService.java",
  "language": "java",
  "metrics": {
    "lines_total": 1419,
    "lines_code": 1419,
    "elements": {
      "classes": 1,
      "methods": 66,
      "fields": 9
    }
  }
}
```

#### 📊 **Step 2: Generate Structure Table**

**Prompt:**
```
Use MCP tool analyze_code_structure to generate detailed structure
Parameters: {"file_path": "examples/BigService.java"}
```

**Return Format:**
- Complete Markdown table
- Including class info, method list (with line numbers), field list
- Method signatures, visibility, line ranges, complexity and other detailed information

#### ✂️ **Step 3: Extract Code Snippets**

**Prompt:**
```
Use MCP tool extract_code_section to extract specified code section
Parameters: {"file_path": "examples/BigService.java", "start_line": 93, "end_line": 105}
```

**Return Format:**
```json
{
  "file_path": "examples/BigService.java",
  "range": {
    "start_line": 93,
    "end_line": 105,
    "start_column": null,
    "end_column": null
  },
  "content": "    private void checkMemoryUsage() {\n        Runtime runtime = Runtime.getRuntime();\n        long totalMemory = runtime.totalMemory();\n        long freeMemory = runtime.freeMemory();\n        long usedMemory = totalMemory - freeMemory;\n\n        System.out.println(\"Total Memory: \" + totalMemory);\n        System.out.println(\"Free Memory: \" + freeMemory);\n        System.out.println(\"Used Memory: \" + usedMemory);\n\n        if (usedMemory > totalMemory * 0.8) {\n            System.out.println(\"WARNING: High memory usage detected!\");\n        }\n",
  "content_length": 542
}
```

#### 🔍 **Step 4: Smart Query Filtering (v0.9.6+)**

**Enhanced Error Handling (v0.9.7):**
- Improved `@handle_mcp_errors` decorator with tool name identification
- Better error context for debugging and troubleshooting
- Enhanced security validation for file paths

**Find specific methods:**
```
Use MCP tool query_code to precisely find code elements
Parameters: {"file_path": "examples/BigService.java", "query_key": "methods", "filter": "name=main"}
```

**Find authentication-related methods:**
```
Use MCP tool query_code to find authentication methods
Parameters: {"file_path": "examples/BigService.java", "query_key": "methods", "filter": "name=~auth*"}
```

**Find parameterless public methods:**
```
Use MCP tool query_code to find getter methods
Parameters: {"file_path": "examples/BigService.java", "query_key": "methods", "filter": "params=0,public=true"}
```

**Return Format:**
```json
{
  "success": true,
  "results": [
    {
      "capture_name": "method",
      "node_type": "method_declaration",
      "start_line": 1385,
      "end_line": 1418,
      "content": "public static void main(String[] args) { ... }"
    }
  ],
  "count": 1
}
```

#### 💡 **Important Notes**
- **Parameter Format**: Use snake_case (`file_path`, `start_line`, `end_line`)
- **Path Handling**: Relative paths auto-resolve to project root
- **Security Protection**: Tool automatically performs project boundary checks
- **Workflow**: Recommended to use in order: Step 1 → 2 → 4 (Query Filtering) → 3 (Precise Extraction)
- **Filter Syntax**: Supports `name=value`, `name=~pattern*`, `params=number`, `static/public/private=true/false`

### 🛠️ CLI Command Examples

```bash
# Quick analysis (1419-line large file, instant completion)
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# Detailed structure table (66 methods clearly displayed)
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# Precise code extraction (memory usage monitoring code snippet)
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105

# Silent mode (display results only)
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --quiet

# 🔍 Query filtering examples (v0.9.6+)
# Find specific methods
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# Find authentication-related methods
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~auth*"

# Find parameterless public methods
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=0,public=true"

# Find static methods
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "static=true"

# View filter syntax help
uv run python -m tree_sitter_analyzer --filter-help
```

---

## 🛠️ Core Features

### 📊 **Code Structure Analysis**
Get insights without reading complete files:
- Class, method, field statistics
- Package information and import dependencies
- Complexity metrics
- Precise line number positioning

### ✂️ **Smart Code Extraction**
- Extract by line range precisely
- Maintain original formatting and indentation
- Include position metadata
- Support efficient processing of large files

### 🔍 **Advanced Query Filtering**
Powerful code element querying and filtering system:
- **Exact matching**: `--filter "name=main"` Find specific methods
- **Pattern matching**: `--filter "name=~auth*"` Find authentication-related methods  
- **Parameter filtering**: `--filter "params=2"` Find methods with specific parameter counts
- **Modifier filtering**: `--filter "static=true,public=true"` Find static public methods
- **Compound conditions**: `--filter "name=~get*,params=0,public=true"` Combine multiple conditions
- **CLI/MCP consistency**: Same filtering syntax in command line and AI assistants

### 🔗 **AI Assistant Integration**
Deep integration via MCP protocol:
- Claude Desktop
- Cursor IDE  
- Roo Code
- Other MCP-supporting AI tools

### 🌍 **Multi-Language Support**
- **Java** - Full support, including Spring, JPA frameworks
- **Python** - Complete support, including type annotations, decorators
- **JavaScript/TypeScript** - Full support, including ES6+ features
- **C/C++, Rust, Go** - Basic support

---

## 📦 Installation Guide

### 👤 **End Users**
```bash
# Basic installation
uv add tree-sitter-analyzer

# Popular languages package (recommended)
uv add "tree-sitter-analyzer[popular]"

# MCP server support
uv add "tree-sitter-analyzer[mcp]"

# Full installation
uv add "tree-sitter-analyzer[all,mcp]"
```

### 👨‍💻 **Developers**
```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

---

## 🔒 Security & Configuration

### 🛡️ **Project Boundary Protection**

Tree-sitter Analyzer automatically detects and protects project boundaries:

- **Auto-detection**: Based on `.git`, `pyproject.toml`, `package.json`, etc.
- **CLI Control**: `--project-root /path/to/project`
- **MCP Integration**: `TREE_SITTER_PROJECT_ROOT=/path/to/project` or use auto-detection
- **Security Guarantee**: Only analyze files within project boundaries

**Recommended MCP Configuration:**

**Option 1: Auto-detection (Recommended)**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "--with", "tree-sitter-analyzer[mcp]", "python", "-m", "tree_sitter_analyzer.mcp.server"]
    }
  }
}
```

**Option 2: Manual Project Root Specification**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "--with", "tree-sitter-analyzer[mcp]", "python", "-m", "tree_sitter_analyzer.mcp.server"],
      "env": {"TREE_SITTER_PROJECT_ROOT": "/path/to/your/project"}
    }
  }
}
```

---

## 🏆 Quality Assurance

### 📊 **Quality Metrics**
- **1,1504** - 100% pass rate ✅
- **74.44% Code Coverage** - Industry-leading level
- **Zero Test Failures** - Complete CI/CD ready
- **Cross-platform Compatible** - Windows, macOS, Linux

### ⚡ **Latest Quality Achievements (v1.0.0)**
- ✅ **Cross-Platform Path Compatibility** - Fixed Windows short path names and macOS symlink differences
- ✅ **Windows Environment** - Implemented robust path normalization using Windows API
- ✅ **macOS Environment** - Fixed `/var` vs `/private/var` symlink differences
- ✅ **Comprehensive Test Coverage** - 74.44% coverage with 1504 tests
- ✅ **GitFlow Implementation** - Professional branching strategy with develop/release branches. See [GitFlow Documentation](GITFLOW.md) for details.

### ⚙️ **Running Tests**
```bash
# Run all tests
uv run pytest tests/ -v

# Generate coverage report
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

# Run specific tests
uv run pytest tests/test_mcp_server_initialization.py -v
```

### 📈 **Coverage Highlights**
- **Language Detector**: 98.41% (Excellent)
- **CLI Main Entry**: 94.36% (Excellent)
- **Query Filtering System**: 96.06% (Excellent)
- **Query Service**: 86.25% (Good)
- **Error Handling**: 82.76% (Good)

---

## 🤖 AI Collaboration Support

### ⚡ **Optimized for AI Development**

This project supports AI-assisted development with specialized quality controls:

```bash
# AI system pre-code generation checks
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all

# AI-generated code review
uv run python llm_code_checker.py path/to/new_file.py
```

📖 **Detailed Guides**:
- [AI Collaboration Guide](AI_COLLABORATION_GUIDE.md)
- [LLM Coding Guidelines](LLM_CODING_GUIDELINES.md)

---

## 📚 Documentation

- **[User MCP Setup Guide](MCP_SETUP_USERS.md)** - Simple configuration guide
- **[Developer MCP Setup Guide](MCP_SETUP_DEVELOPERS.md)** - Local development configuration
- **[Project Root Configuration](PROJECT_ROOT_CONFIG.md)** - Complete configuration reference
- **[API Documentation](docs/api.md)** - Detailed API reference
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute

---

## 🤝 Contributing

We welcome all forms of contributions! Please check the [Contributing Guide](CONTRIBUTING.md) for details.

### ⭐ **Give Us a Star!**

If this project helps you, please give us a ⭐ on GitHub - it's the greatest support for us!

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

**🎯 Built for developers dealing with large codebases and AI assistants**

*Let every line of code be understood by AI, let every project break through token limits*

**🚀 Start Now** → [30-Second Quick Start](#-30-second-quick-start)
