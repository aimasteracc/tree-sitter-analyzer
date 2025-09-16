# Tree-sitter Analyzer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1699%20passed-brightgreen.svg)](#quality-assurance)
[![Coverage](https://img.shields.io/badge/coverage-74.42%25-green.svg)](#quality-assurance)
[![Quality](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#quality-assurance)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Version](https://img.shields.io/badge/version-1.3.5-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

## 🚀 Break LLM Token Limits, Let AI Understand Code Files of Any Size

> **Revolutionary Code Analysis Tool Designed for the AI Era**

## 📋 Table of Contents

- [🚀 Break LLM Token Limits](#-break-llm-token-limits-let-ai-understand-code-files-of-any-size)
- [📋 Table of Contents](#-table-of-contents)
- [💡 Unique Features](#-unique-features)
- [📊 Real-time Demo and Results](#-real-time-demo-and-results)
- [🚀 30-Second Quick Start](#-30-second-quick-start)
  - [🤖 AI Users (Claude Desktop, Cursor, etc.)](#-ai-users-claude-desktop-cursor-etc)
  - [💻 Developers (CLI)](#-developers-cli)
- [❓ Why Choose Tree-sitter Analyzer](#-why-choose-tree-sitter-analyzer)
- [📖 Practical Usage Examples](#-practical-usage-examples)
- [🛠️ Core Features](#️-core-features)
- [📦 Installation Guide](#-installation-guide)
- [🔒 Security and Configuration](#-security-and-configuration)
- [🏆 Quality Assurance](#-quality-assurance)
- [🤖 AI Collaboration Support](#-ai-collaboration-support)
- [📚 Documentation](#-documentation)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

## 💡 Unique Features

Imagine this: you have a Java service class with over 1400 lines, and Claude or ChatGPT can't analyze it due to token limits. Now, Tree-sitter Analyzer enables AI assistants to:

- ⚡ **Get complete code structure overview in 3 seconds**
- 🎯 **Accurate extraction** of code snippets from any line range
- 📍 **Smart positioning** of exact locations for classes, methods, and fields
- 🔗 **Seamless integration** with Claude Desktop, Cursor, Roo Code, and other AI IDEs
- 🏗️ **Unified element management** - All code elements (classes, methods, fields, imports) in a unified system

**No more AI being helpless with large files!**

## 📊 Real-time Demo and Results

### ⚡ **Lightning-fast Analysis Speed**
```bash
# Analysis result of 1419-line large Java service class (< 1 second)
Lines: 1419 | Classes: 1 | Methods: 66 | Fields: 9 | Imports: 8 | Packages: 1
Total Elements: 85 | Complexity: 348 (avg: 5.27, max: 15)
```

### 📊 **Precise Structure Table**
| Class Name | Type | Visibility | Line Range | Method Count | Field Count |
|------------|------|------------|------------|--------------|-------------|
| BigService | class | public | 17-1419 | 66 | 9 |

### 🔄 **AI Assistant SMART Workflow**
- **S**: `set_project_path` - Setup project root directory
- **M**: `list_files`, `search_content`, `find_and_grep` - Map target files with precision
- **A**: `analyze_code_structure` - Analyze core structure with unified elements
- **R**: `extract_code_section` - Retrieve essential code snippets on demand
- **T**: Advanced dependency tracing (when needed)

---

## 🚀 30-Second Quick Start

### 🤖 AI Users (Claude Desktop, Cursor, etc.)

**📋 0. Prerequisites (for Advanced MCP Tools)**
For advanced file search and content analysis features, install these tools first:
```bash
# Install fd and ripgrep (see Prerequisites section for detailed instructions)
# macOS
brew install fd ripgrep

# Windows (using winget - recommended)
winget install sharkdp.fd BurntSushi.ripgrep.MSVC

# Windows (alternative methods)
# choco install fd ripgrep
# scoop install fd ripgrep

# Ubuntu/Debian
sudo apt install fd-find ripgrep
```

**📦 1. One-click Installation**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**⚙️ 2. AI Client Configuration**

**Claude Desktop Configuration:**

Add the following to your configuration file:
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

**Advanced Configuration (Specify Project Root Directory):**
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
- **Roo Code**: Supports MCP protocol, check corresponding configuration guides
- **Other MCP-compatible clients**: Use the same server configuration

**⚠️ Configuration Notes:**
- **Basic Configuration**: Tool automatically detects project root directory (recommended)
- **Advanced Configuration**: If you need to specify a particular directory, replace `/absolute/path/to/your/project` with an absolute path
- **Avoid Using**: Variables like `${workspaceFolder}` may not be supported in some clients

**🎉 3. Restart AI client and start analyzing large code files!**

### 💻 Developers (CLI)

```bash
# Installation
uv add "tree-sitter-analyzer[popular]"

# Check file size (1419-line large service class, completed instantly)
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# Generate structure table (1 class, 66 methods, clearly displayed)
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# Precise code extraction
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105
```

---

## ❓ Why Choose Tree-sitter Analyzer

### 🎯 Solve Real Pain Points

**Traditional Method Difficulties:**
- ❌ Large files exceed LLM token limits
- ❌ AI cannot understand code structure
- ❌ Need to manually split files
- ❌ Context loss leads to inaccurate analysis

**Tree-sitter Analyzer Breakthrough:**
- ✅ **Smart Analysis**: Understand structure without reading complete files
- ✅ **Precise Positioning**: Accurate line-by-line code extraction
- ✅ **AI Native**: Optimized for LLM workflows
- ✅ **Multi-language Support**: Java, Python, JavaScript/TypeScript, etc.

## 📖 Practical Usage Examples

### 💬 AI IDE Prompts (SMART Analysis Workflow)

> **✅ Test Verification Status:** All prompts below have been tested and verified in real environments, ensuring 100% availability
>
> **🎯 SMART Analysis Workflow:**
> - **S** - Setup project (set_project_path)
> - **M** - Map target files (precision pattern matching)
> - **A** - Analyze core structure (analyze_code_structure)
> - **R** - Retrieve essential code (extract_code_section)
> - **T** - Trace dependencies (when needed)
>
> **⚠️ Important Notes:**
> - Follow SMART workflow sequence for optimal results
> - For files within the project, use **relative paths** (e.g., `examples/BigService.java`)
> - For files outside the project, use **absolute paths** (e.g., `C:\git-public\tree-sitter-analyzer\examples\BigService.java`)
> - All tools support both Windows and Unix style paths
> - Project path should point to your code repository root directory

#### 🔧 **S - Setup Project (Required First Step)**

**Option 1: Configure in MCP Settings**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "python", "-m", "tree_sitter_analyzer.mcp.server"],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

**Option 2: Tell AI Directly (Recommended, More Natural)**

**Method 1: Explicit Setup Request**
```
Please help me set the project root directory, the path is: C:\git-public\tree-sitter-analyzer
```

**Method 2: Provide Project Information**
```
My project is at: C:\git-public\tree-sitter-analyzer
Please set this path as the project root
```

**Method 3: Simple Statement**
```
Project path: C:\git-public\tree-sitter-analyzer
```

**AI will automatically call the appropriate tool to set the path, no need to remember complex command formats**

**⚠️ Important Notes:**
- After setting project path, you can use relative paths to reference files within the project
- Example: `examples/BigService.java` instead of full paths
- Once project path is successfully set, all subsequent analysis commands will automatically use this root directory

#### 🗺️ **M - Map Target Files (Precision Pattern Matching)**

> **📋 Prerequisites:** This step requires `fd` and `ripgrep` tools to be installed. See [Prerequisites](#prerequisites) section for installation instructions.

**Smart File Discovery:**
```
Find all Python files in the project
```

```
List all Java files larger than 10KB
```

```
Find configuration files (*.json, *.yaml, *.toml) in the project
```

**Intelligent Content Search:**
```
Search for "def authenticate" in all Python files with context
```

```
Find all TODO comments in source files
```

```
Search for "class.*Service" patterns in all files, case insensitive
```

**Combined Discovery & Search:**
```
Find all Python files and search for "async def" functions
```

```
Search for "class.*Service" in all source files
```

**Return Format:**
```json
{
  "success": true,
  "results": [
    {
      "file": "tree_sitter_analyzer/core/query_service.py",
      "line": 20,
      "text": "class QueryService:",
      "matches": [[0, 18]]
    }
  ],
  "count": 25,
  "meta": {
    "searched_file_count": 256,
    "truncated": false,
    "fd_elapsed_ms": 225,
    "rg_elapsed_ms": 2969
  }
}
```

#### 🔍 **A - Analyze Core Structure**

**Method 1: Explicit Analysis Request**
```
Please help me analyze this file: examples/BigService.java
```

**Method 2: Describe Analysis Needs**
```
I want to understand the size and structure of this Java file: examples/BigService.java
```

**Method 3: Simple Request**
```
Analyze this file: examples/BigService.java
```

**Alternative using absolute path:**
```
Please analyze this file: C:\git-public\tree-sitter-analyzer\examples\BigService.java
```

**💡 Tip: After setting project path, using relative paths is recommended, more concise and convenient**

**Return Format:**
```json
{
  "file_path": "examples/BigService.java",
  "language": "java",
  "metrics": {
    "lines_total": 1419,
    "lines_code": 907,
    "lines_comment": 246,
    "lines_blank": 267,
    "elements": {
      "classes": 1,
      "methods": 66,
      "fields": 9,
      "imports": 8,
      "packages": 1,
      "total": 85
    },
    "complexity": {
      "total": 348,
      "average": 5.27,
      "max": 15
    }
  }
}
```

#### 📊 **R - Retrieve Essential Code**

**Method 1: Explicit Table Request**
```
Please generate a detailed structure table for this file: examples/BigService.java
```

**Method 2: Describe Table Needs**
```
I want to see the complete structure of this Java file, including all classes, methods, and fields: examples/BigService.java
```

**Method 3: Simple Request**
```
Generate structure table: examples/BigService.java
```

**Alternative using absolute path:**
```
Please generate a detailed structure table: C:\git-public\tree-sitter-analyzer\examples\BigService.java
```

**💡 Tip: After setting project path, using relative paths is recommended, more concise and convenient**

**Return Format:**
- Complete Markdown table
- Including class information, method list (with line numbers), field list
- Method signatures, visibility, line ranges, complexity, and other detailed information

#### ✂️ **Precise Code Extraction**

**Method 1: Explicit Extraction Request**
```
Please extract lines 93-105 of this file: examples/BigService.java
```

**Method 2: Describe Extraction Needs**
```
I want to see the code content from lines 93 to 105 of this Java file: examples/BigService.java
```

**Method 3: Simple Request**
```
Extract lines 93-105: examples/BigService.java
```

**Alternative using absolute path:**
```
Please extract code snippet: C:\git-public\tree-sitter-analyzer\examples\BigService.java, lines 93-105
```

**💡 Tip: After setting project path, using relative paths is recommended, more concise and convenient**

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

#### 🔗 **T - Trace Dependencies (Advanced Analysis)**

**Error Handling Enhancement (v0.9.7):**
- Improved `@handle_mcp_errors` decorator with tool name recognition
- Better error context for easier debugging and troubleshooting
- Enhanced file path security validation

**Find Specific Methods:**
```
Please help me find the main method in this file: examples/BigService.java
```

**Find Authentication-related Methods:**
```
I want to find all authentication-related methods: examples/BigService.java
```

**Find Public Methods with No Parameters:**
```
Please help me find all public getter methods with no parameters: examples/BigService.java
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
      "content": "public static void main(String[] args) {\n        System.out.println(\"BigService Demo Application\");\n        System.out.println(\"==========================\");\n\n        BigService service = new BigService();\n\n        // Test basic functions\n        System.out.println(\"\\n--- Testing Basic Functions ---\");\n        service.authenticateUser(\"testuser\", \"password123\");\n        service.createSession(\"testuser\");\n\n        // Test customer management\n        System.out.println(\"\\n--- Testing Customer Management ---\");\n        service.updateCustomerName(\"CUST001\", \"New Customer Name\");\n        Map<String, Object> customerInfo = service.getCustomerInfo(\"CUST001\");\n\n        // Test report generation\n        System.out.println(\"\\n--- Testing Report Generation ---\");\n        Map<String, Object> reportParams = new HashMap<>();\n        reportParams.put(\"start_date\", \"2024-01-01\");\n        reportParams.put(\"end_date\", \"2024-12-31\");\n        service.generateReport(\"sales\", reportParams);\n\n        // Test performance monitoring\n        System.out.println(\"\\n--- Testing Performance Monitoring ---\");\n        service.monitorPerformance();\n\n        // Test security check\n        System.out.println(\"\\n--- Testing Security Check ---\");\n        service.performSecurityCheck();\n\n        System.out.println(\"\\n--- Demo Completed ---\");\n        System.out.println(\"BigService demo application finished successfully.\");\n    }"
    }
  ],
  "count": 1,
  "file_path": "examples/BigService.java",
  "language": "java",
  "query": "methods"
}
```


#### 💡 **SMART Workflow Best Practices**
- **Natural Language**: Tell AI directly in natural language what you want, no need to remember complex parameter formats
- **Sequential Flow**: Follow S→M→A→R→T sequence for optimal analysis results
- **Path Processing**: After setting project path, relative paths automatically resolve to project root directory
- **Security Protection**: Tool automatically performs project boundary checks to ensure security
- **Smart Understanding**: AI automatically understands your needs and calls appropriate tools
- **Performance**: All MCP tools are optimized for speed with built-in timeouts and result limits
- **Dependency Tracing**: Use T step only when you need to understand complex relationships between code elements

### 🛠️ CLI Command Examples

```bash
# Quick analysis (1419-line large file, completed instantly)
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# Detailed structure table (66 methods clearly displayed)
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# Precise code extraction (memory usage monitoring code snippet)
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105

# Multi-language support test (Python file)
uv run python -m tree_sitter_analyzer examples/sample.py --table=full

# Small file quick analysis (54-line Java file)
uv run python -m tree_sitter_analyzer examples/MultiClass.java --advanced

# Silent mode (only show results)
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --quiet

# 🔍 Query Filter Examples (v0.9.6+)
# Find specific methods
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# Find authentication-related methods
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~auth*"

# Find public methods with no parameters
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=0,public=true"

# Find static methods
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "static=true"

# View filter syntax help
uv run python -m tree_sitter_analyzer --filter-help
```

---

## 🏗️ Architecture Improvements (v1.2.0+)

### 🔄 **Unified Element Management System**

Tree-sitter Analyzer now features a revolutionary unified architecture that integrates all code elements into a unified system:

#### **Before (Traditional Architecture):**
- Independent collections of classes, methods, fields, and imports
- Inconsistent data structures across different analysis modes
- Complex maintenance and potential inconsistencies

#### **After (Unified Architecture):**
- **Single `elements` list**: All code elements (classes, methods, fields, imports, packages) unified
- **Consistent element types**: Each element has an `element_type` attribute for easy identification
- **Simplified API**: Clearer interfaces and reduced complexity
- **Better maintainability**: Single source of truth for all code elements

#### **Benefits:**
- ✅ **Consistency**: Unified data structures across all analysis modes
- ✅ **Simplicity**: Easier to use and understand
- ✅ **Extensibility**: Easy to add new element types
- ✅ **Performance**: Optimized memory usage and processing
- ✅ **Backward compatibility**: Existing APIs continue to work seamlessly

#### **Supported Element Types:**
- `class` - Classes and interfaces
- `function` - Methods and functions
- `variable` - Fields and variables
- `import` - Import statements
- `package` - Package declarations

---

## 🛠️ Core Features

### 📊 **Code Structure Analysis**
Get insights without reading complete files:
- Class, method, and field statistics
- Package information and import dependencies
- Complexity metrics
- Precise line number positioning

### ✂️ **Smart Code Extraction**
- Precise extraction by line range
- Maintains original format and indentation
- Includes position metadata
- Supports efficient processing of large files

### 🔍 **Advanced Query Filtering**
Powerful code element query and filtering system:
- **Exact matching**: `--filter "name=main"` to find specific methods
- **Pattern matching**: `--filter "name=~auth*"` to find authentication-related methods
- **Parameter filtering**: `--filter "params=2"` to find methods with specific parameter counts
- **Modifier filtering**: `--filter "static=true,public=true"` to find static public methods
- **Compound conditions**: `--filter "name=~get*,params=0,public=true"` to combine multiple conditions
- **CLI/MCP consistency**: Same filtering syntax used in command line and AI assistants

### 🔗 **AI Assistant Integration**
Deep integration through MCP protocol:
- Claude Desktop
- Cursor IDE
- Roo Code
- Other MCP-compatible AI tools

### 🔍 **Advanced File Search & Content Analysis (v1.2.4+)**
Powerful file discovery and content search capabilities powered by fd and ripgrep:

#### **📋 Prerequisites**
To use the advanced MCP tools (ListFilesTool, SearchContentTool, FindAndGrepTool), you need to install the following command-line tools:

**Install fd (fast file finder):**
```bash
# macOS (using Homebrew)
brew install fd

# Windows (using winget - recommended)
winget install sharkdp.fd

# Windows (using Chocolatey)
choco install fd

# Windows (using Scoop)
scoop install fd

# Ubuntu/Debian
sudo apt install fd-find

# CentOS/RHEL/Fedora
sudo dnf install fd-find

# Arch Linux
sudo pacman -S fd
```

**Install ripgrep (fast text search):**
```bash
# macOS (using Homebrew)
brew install ripgrep

# Windows (using winget - recommended)
winget install BurntSushi.ripgrep.MSVC

# Windows (using Chocolatey)
choco install ripgrep

# Windows (using Scoop)
scoop install ripgrep

# Ubuntu/Debian
sudo apt install ripgrep

# CentOS/RHEL/Fedora
sudo dnf install ripgrep

# Arch Linux
sudo pacman -S ripgrep
```

**Verify Installation:**
```bash
# Check fd installation
fd --version

# Check ripgrep installation
rg --version
```

> **⚠️ Important:** Without these tools installed, the advanced MCP file search and content analysis features will not work. The basic MCP tools (analyze_code_structure, extract_code_section, etc.) will continue to work normally.

#### **🗂️ ListFilesTool - Smart File Discovery**
- **Advanced filtering**: File type, size, modification time, extension-based filtering
- **Pattern matching**: Glob patterns and regex support for flexible file discovery
- **Metadata enrichment**: File size, modification time, directory status, and extension information
- **Performance optimized**: Built on fd for lightning-fast file system traversal

#### **🔎 SearchContentTool - Intelligent Content Search**
- **Regex & literal search**: Flexible pattern matching with case sensitivity controls
- **Context-aware results**: Configurable before/after context lines for better understanding
- **Multiple output formats**: Standard results, count-only, summary, and grouped by file
- **Encoding support**: Handle files with different text encodings
- **Performance limits**: Built-in timeout and result limits for responsive operation

#### **🎯 FindAndGrepTool - Combined Discovery & Search**
- **Two-stage workflow**: First discover files with fd, then search content with ripgrep
- **Comprehensive filtering**: Combine file discovery filters with content search patterns
- **Advanced options**: Multiline patterns, word boundaries, fixed strings, and case controls
- **Rich metadata**: File discovery timing, search timing, and result statistics
- **Token optimization**: Path optimization and result grouping to minimize AI token usage

#### **✨ Key Benefits:**
- 🚀 **Enterprise-grade reliability**: 50+ comprehensive test cases ensuring stability
- 🎯 **Token-efficient**: Multiple output formats optimized for AI assistant interactions
- 🔧 **Highly configurable**: Extensive parameter support for precise control
- 📊 **Performance monitoring**: Built-in timing and result statistics
- 🛡️ **Error resilient**: Comprehensive error handling and validation

### 🌍 **Multi-language Support**
- **Java** - Full support, including Spring, JPA frameworks
- **Python** - Full support, including type annotations, decorators
- **JavaScript/TypeScript** - Full support, including ES6+ features
- **C/C++, Rust, Go** - Basic support

---

## 📦 Installation Guide

### 👤 **End Users**
```bash
# Basic installation
uv add tree-sitter-analyzer

# Popular language packages (recommended)
uv add "tree-sitter-analyzer[popular]"

# MCP server support
uv add "tree-sitter-analyzer[mcp]"

# Complete installation
uv add "tree-sitter-analyzer[all,mcp]"
```

### 👨‍💻 **Developers**
```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

---

## 🔒 Security and Configuration

### 🛡️ **Project Boundary Protection**

Tree-sitter Analyzer automatically detects and protects project boundaries:

- **Auto-detection**: Based on `.git`, `pyproject.toml`, `package.json`, etc.
- **CLI control**: `--project-root /path/to/project`
- **MCP integration**: `TREE_SITTER_PROJECT_ROOT=/path/to/project` or use auto-detection
- **Security guarantee**: Only analyze files within project boundaries

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

**Option 2: Manually specify project root directory**
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
- **1,514 tests** - 100% pass rate ✅
- **74.24% code coverage** - Industry-leading level
- **Zero test failures** - Fully CI/CD ready
- **Cross-platform compatibility** - Windows, macOS, Linux

### ⚡ **Latest Quality Achievements (v1.3.5)**
- ✅ **Cross-platform path compatibility** - Fixed Windows short path names and macOS symbolic link differences
- ✅ **Windows environment** - Implemented robust path normalization using Windows API
- ✅ **macOS environment** - Fixed `/var` vs `/private/var` symbolic link differences
- ✅ **Comprehensive test coverage** - 1699 tests, 74.42% coverage
- ✅ **GitFlow implementation** - Professional development/release branch strategy. See [GitFlow documentation](GITFLOW.md) for details.

### ⚙️ **Running Tests**
```bash
# Run all tests
uv run pytest tests/ -v

# Generate coverage report
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html --cov-report=term-missing

# Run specific tests
uv run pytest tests/test_mcp_server_initialization.py -v
```

### 📈 **Coverage Highlights**
- **Language detector**: 98.41% (Excellent)
- **CLI main entry**: 94.36% (Excellent)
- **Query filtering system**: 96.06% (Excellent)
- **MCP fd/rg tools**: 93.04% (Excellent) - *Enhanced in v1.3.2 with cache format compatibility fix*
- **Query service**: 86.25% (Good)
- **Error handling**: 82.76% (Good)

---

## 🤖 AI Collaboration Support

### ⚡ **Optimized for AI Development**

This project supports AI-assisted development with dedicated quality control:

```bash
# AI system code generation pre-check
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
- **[Takeover and Training Guide](training/README.md)** - System onboarding materials for new members/maintainers

---

## 💝 Sponsors & Acknowledgments

We are grateful to our sponsors who make this project possible:

### 🌟 **Special Thanks**

**[@o93](https://github.com/o93)** - *Primary Sponsor & Supporter*
- 🚀 **MCP Tools Enhancement**: Sponsored the comprehensive MCP fd/ripgrep tools development
- 🧪 **Testing Infrastructure**: Enabled enterprise-grade test coverage (50+ comprehensive test cases)
- 🔧 **Quality Assurance**: Supported bug fixes and performance improvements
- 💡 **Innovation Support**: Made early release of advanced file search and content analysis features possible

*"Thanks to @o93's generous support, we were able to deliver powerful MCP tools that revolutionize how AI assistants interact with codebases. This sponsorship directly enabled the development of ListFilesTool, SearchContentTool, and FindAndGrepTool with comprehensive test coverage."*

### 🤝 **Become a Sponsor**

Your support helps us:
- 🔬 Develop new features and tools
- 🧪 Maintain comprehensive test coverage
- 📚 Create better documentation
- 🚀 Accelerate development cycles

**[💖 Sponsor this project](https://github.com/sponsors/aimasteracc)** to help us continue building amazing tools for the developer community!

---

## 🤝 Contributing

We welcome all forms of contributions! Please see [Contributing Guide](CONTRIBUTING.md) for details.

### ⭐ **Give Us a Star!**

If this project has been helpful to you, please give us a ⭐ on GitHub - this is the greatest support for us!

---

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details.

---

**🎯 Built for developers dealing with large codebases and AI assistants**

*Let every line of code be understood by AI, let every project break through token limits*

---

## ✅ Prompt Testing Verification

All AI prompts in this document have been thoroughly tested in real environments, ensuring:

- **100% Availability** - All prompts work correctly
- **Multi-language Support** - Supports Java, Python, JavaScript and other mainstream languages
- **Path Compatibility** - Both relative and absolute paths are fully supported
- **Windows/Linux Compatibility** - Cross-platform path formats are automatically handled
- **Real-time Verification** - Tested using real code files

**Test Environment:**
- Operating System: Windows 10
- Project: tree-sitter-analyzer v1.3.5
- Test Files: BigService.java (1419 lines), sample.py (256 lines), MultiClass.java (54 lines)
- Test Coverage: 1699 tests passed, 74.42% coverage
- Test Tools: All MCP tools (check_code_scale, analyze_code_structure, extract_code_section, query_code, list_files, search_content, find_and_grep)

**🚀 Start Now** → [30-Second Quick Start](#-30-second-quick-start)
