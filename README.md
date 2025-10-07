# Tree-sitter Analyzer

**English** | **[日本語](README_ja.md)** | **[简体中文](README_zh.md)**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-2046%20passed-brightgreen.svg)](#quality-assurance)
[![Coverage](https://img.shields.io/badge/coverage-69.67%25-green.svg)](#quality-assurance)
[![Quality](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#quality-assurance)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Version](https://img.shields.io/badge/version-1.6.2-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

## 🚀 Enterprise-Grade Code Analysis Tool for the AI Era

> **Deep AI Integration · Powerful File Search · Multi-Language Support · Intelligent Code Analysis**

## 📋 Table of Contents

- [💡 Key Features](#-key-features)
- [📋 Prerequisites (Required for All Users)](#-prerequisites-required-for-all-users)
- [🚀 Quick Start](#-quick-start)
  - [🤖 AI Users (Claude Desktop, Cursor, etc.)](#-ai-users-claude-desktop-cursor-etc)
  - [💻 CLI Users (Command Line Tools)](#-cli-users-command-line-tools)
  - [👨‍💻 Developers (Source Development)](#-developers-source-development)
- [📖 Usage Workflow & Examples](#-usage-workflow--examples)
  - [🔄 AI Assistant SMART Workflow](#-ai-assistant-smart-workflow)
  - [⚡ Complete CLI Commands](#-complete-cli-commands)
- [🛠️ Core Features](#️-core-features)
- [🏆 Quality Assurance](#-quality-assurance)
- [📚 Documentation & Support](#-documentation--support)
- [🤝 Contributing & License](#-contributing--license)

---

## 💡 Key Features

Tree-sitter Analyzer is an enterprise-grade code analysis tool designed for the AI era, providing:

### 🤖 Deep AI Integration
- **MCP Protocol Support** - Native support for Claude Desktop, Cursor, Roo Code, and other AI tools
- **SMART Workflow** - Systematic AI-assisted code analysis methodology
- **Break Token Limits** - Enable AI to understand code files of any size
- **Natural Language Interaction** - Complete complex code analysis tasks using natural language

### 🔍 Powerful Search Capabilities
- **Intelligent File Discovery** - High-performance file search based on fd with multiple filtering conditions
- **Precise Content Search** - Regular expression content search based on ripgrep
- **Two-Stage Search** - Combined workflow of finding files then searching content
- **Project Boundary Protection** - Automatic detection and respect for project boundaries to ensure security

### 📊 Intelligent Code Analysis
- **Fast Structure Analysis** - Understand code architecture without reading the entire file
- **Precise Code Extraction** - Support for extracting precise code snippets by line range
- **Complexity Analysis** - Cyclomatic complexity calculation and code quality metrics
- **Unified Element System** - Revolutionary unified code element management architecture

### 🌍 Enterprise-Grade Multi-Language Support
- **Java** - Full support (1103 lines of plugin code, 73% coverage), including Spring, JPA frameworks
- **Python** - Full support (584 lines of plugin code, 63% coverage), including type annotations, decorators
- **JavaScript** - Enterprise-grade support (1445 lines of plugin code, 68% coverage), including ES6+, React/Vue/Angular, JSX
- **TypeScript** - **Complete support** (1553 lines of plugin code, 29% coverage), including interfaces, types, decorators, TSX/JSX, framework detection
- **More Languages** - Basic support for C/C++, Rust, Go

### 🏆 Production Ready
- **2,046 Tests** - 100% pass rate, enterprise-grade quality assurance
- **69.67% Coverage** - Comprehensive test suite
- **Cross-Platform Support** - Full compatibility with Windows, macOS, Linux
- **Continuous Maintenance** - Active development and community support

---

## 📋 Prerequisites (Required for All Users)

Whether you're an AI user, CLI user, or developer, you need to install the following tools first:

### 1️⃣ Install uv (Required - for running tools)

**uv** is a fast Python package manager used to run tree-sitter-analyzer.

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Verify installation:**
```bash
uv --version
```

### 2️⃣ Install fd and ripgrep (Required for search functionality)

**fd** and **ripgrep** are high-performance file and content search tools used for advanced MCP features.

```bash
# macOS
brew install fd ripgrep

# Windows (recommended using winget)
winget install sharkdp.fd BurntSushi.ripgrep.MSVC

# Windows (alternative methods)
# choco install fd ripgrep
# scoop install fd ripgrep

# Ubuntu/Debian
sudo apt install fd-find ripgrep

# CentOS/RHEL/Fedora
sudo dnf install fd-find ripgrep

# Arch Linux
sudo pacman -S fd ripgrep
```

**Verify installation:**
```bash
fd --version
rg --version
```

> **⚠️ Important Note:** 
> - **uv** is required for running all features
> - **fd** and **ripgrep** are required for using advanced file search and content analysis features
> - If fd and ripgrep are not installed, basic code analysis features will still work, but file search features will be unavailable

---

## 🚀 Quick Start

### 🤖 AI Users (Claude Desktop, Cursor, etc.)

**For:** Users who use AI assistants (such as Claude Desktop, Cursor) for code analysis

#### ⚙️ Configuration Steps

**Claude Desktop Configuration:**

1. Find the configuration file location:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/claude/claude_desktop_config.json`

2. Add the following configuration:

**Basic Configuration (Recommended - Auto-detect project path):**
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

**Advanced Configuration (Manually specify project path):**
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
        "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project",
        "TREE_SITTER_OUTPUT_PATH": "/absolute/path/to/output/directory"
      }
    }
  }
}
```

3. Restart your AI client

4. Start using! Tell the AI:
   ```
   Please set the project root directory to: /path/to/your/project
   ```

**Other AI Clients:**
- **Cursor**: Built-in MCP support, refer to Cursor documentation for configuration
- **Roo Code**: Supports MCP protocol, use the same configuration format
- **Other MCP-compatible clients**: Use the same server configuration

---

### 💻 CLI Users (Command Line Tools)

**For:** Developers who prefer using command-line tools

#### 📦 Installation

```bash
# Basic installation
uv add tree-sitter-analyzer

# Popular language pack (recommended)
uv add "tree-sitter-analyzer[popular]"

# Full installation (including MCP support)
uv add "tree-sitter-analyzer[all,mcp]"
```

#### ⚡ Quick Experience

```bash
# View help
uv run python -m tree_sitter_analyzer --help

# Analyze file size (1419 lines completed instantly)
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# Generate detailed structure table
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# Precise code extraction
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106
```

---

### 👨‍💻 Developers (Source Development)

**For:** Developers who need to modify source code or contribute

#### 🛠️ Development Environment Setup

```bash
# Clone repository
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer

# Install dependencies
uv sync --extra all --extra mcp

# Run tests
uv run pytest tests/ -v

# Generate coverage report
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html
```

#### 🔍 Code Quality Checks

```bash
# AI-generated code check
uv run python llm_code_checker.py --check-all

# Quality check
uv run python check_quality.py --new-code-only
```

---

## 📖 Usage Workflow & Examples

### 🔄 AI Assistant SMART Workflow

The SMART workflow is the recommended process for analyzing code using AI assistants. The following demonstrates the complete workflow using `examples/BigService.java` (a large service class with 1419 lines):

- **S** (Set): Set project root directory
- **M** (Map): Precisely map target files
- **A** (Analyze): Analyze core structure
- **R** (Retrieve): Retrieve key code
- **T** (Trace): Trace dependencies

---

#### **S - Set Project (First Step)**

**Tell the AI:**
```
Please set the project root directory to: C:\git-public\tree-sitter-analyzer
```

**The AI will automatically call** the `set_project_path` tool.

> 💡 **Tip**: You can also pre-set this through the `TREE_SITTER_PROJECT_ROOT` environment variable in MCP configuration.

---

#### **M - Map Target Files (Find files to analyze)**

**Scenario 1: Don't know where the file is, search first**

```
Find all Java files containing "BigService" in the project
```

**The AI will call** the `find_and_grep` tool and return results showing 8 matches in BigService.java.

**Scenario 2: Known file path, use directly**
```
I want to analyze the file examples/BigService.java
```

---

#### **A - Analyze Core Structure (Understand file size and organization)**

**Tell the AI:**
```
Please analyze the structure of examples/BigService.java, I want to know how large this file is and what main components it contains
```

**The AI will call** the `analyze_code_structure` tool and return:
```json
{
  "file_path": "examples/BigService.java",
  "language": "java",
  "metrics": {
    "lines_total": 1419,
    "lines_code": 906,
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

**Key Information:**

- File has **1419 lines** total
- Contains **1 class**, **66 methods**, **9 fields**, **1 package**, **total of 85 elements**

---

#### **R - Retrieve Key Code (Deep dive into specific implementation)**

**Scenario 1: View complete structure table**
```
Please generate a detailed structure table for examples/BigService.java, I want to see a list of all methods
```

**The AI will generate a Markdown table containing:**

- Class information: package name, type, visibility, line range
- Field list: 9 fields (DEFAULT_ENCODING, MAX_RETRY_COUNT, etc.)
- Constructor: BigService()
- Public methods: 19 (authenticateUser, createSession, generateReport, etc.)
- Private methods: 47 (initializeService, checkMemoryUsage, etc.)

**Scenario 2: Extract specific code snippet**
```
Please extract lines 93-106 of examples/BigService.java, I want to see the specific implementation of memory checking
```

**The AI will call** the `extract_code_section` tool and return the checkMemoryUsage method code.

---

#### **T - Trace Dependencies (Understand code relationships)**

**Scenario 1: Find all authentication-related methods**
```
Find all methods related to authentication (auth) in examples/BigService.java
```

**The AI will call query filtering** and return the authenticateUser method (lines 141-172).

**Scenario 2: Find entry point**
```
Where is the main method in this file? What does it do?
```

**The AI will locate:**

- **Location**: Lines 1385-1418
- **Function**: Demonstrates various features of BigService (authentication, sessions, customer management, report generation, performance monitoring, security checks)

**Scenario 3: Understand method call relationships**
```
Which methods call the authenticateUser method?
```

**The AI will search the code** and find the call in the `main` method:
```java
service.authenticateUser("testuser", "password123");
```

---

### 💡 SMART Workflow Best Practices

1. **Natural Language First**: Describe your needs in natural language, AI will automatically choose the appropriate tools
2. **Progressive Approach**: First understand the overall structure (A), then dive into specific code (R)
3. **Trace as Needed**: Only use tracing (T) when you need to understand complex relationships
4. **Combined Use**: You can combine multiple steps in one conversation

**Complete Example Conversation:**
```
I want to understand the large file examples/BigService.java:
1. How large is it? What main features does it contain?
2. How is the authentication feature implemented?
3. What public API methods are there?
```

The AI will automatically:
1. Analyze file structure (1419 lines, 66 methods)
2. Locate and extract the `authenticateUser` method (lines 141-172)
3. Generate a list of public methods (19 public methods)

---

### ⚡ Complete CLI Commands

#### 📊 Code Structure Analysis Commands

```bash
# Quick analysis (display summary information)
uv run python -m tree_sitter_analyzer examples/BigService.java --summary

# Detailed analysis (display complete structure)
uv run python -m tree_sitter_analyzer examples/BigService.java --structure

# Advanced analysis (including complexity metrics)
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced

# Generate complete structure table
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# Specify output format
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=json
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# Precise code extraction
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106

# Specify programming language
uv run python -m tree_sitter_analyzer script.py --language python --table=full
```

#### 🔍 Query and Filter Commands

```bash
# Query specific elements
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key classes

# Filter query results
# Find specific method
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# Find authentication-related methods (pattern matching)
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~auth*"

# Find public methods with no parameters (compound conditions)
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=0,public=true"

# Find static methods
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "static=true"

# View filter syntax help
uv run python -m tree_sitter_analyzer --filter-help
```

#### 📁 File System Operation Commands

```bash
# List files
uv run list-files . --extensions java
uv run list-files . --pattern "test_*" --extensions java --types f
uv run list-files . --types f --size "+1k" --changed-within "1week"

# Search content
uv run search-content --roots . --query "class.*extends" --include-globs "*.java"
uv run search-content --roots tests --query "TODO|FIXME" --context-before 2 --context-after 2
uv run search-content --files examples/BigService.java examples/Sample.java --query "public.*method" --case insensitive

# Two-stage search (find files first, then search content)
uv run find-and-grep --roots . --query "@SpringBootApplication" --extensions java
uv run find-and-grep --roots examples --query "import.*SQLException" --extensions java --file-limit 10 --max-count 5
uv run find-and-grep --roots . --query "public.*static.*void" --extensions java --types f --size "+1k" --output-format json
```

#### ℹ️ Information Query Commands

```bash
# View help
uv run python -m tree_sitter_analyzer --help

# List supported query keys
uv run python -m tree_sitter_analyzer --list-queries

# Display supported languages
uv run python -m tree_sitter_analyzer --show-supported-languages

# Display supported extensions
uv run python -m tree_sitter_analyzer --show-supported-extensions

# Display common queries
uv run python -m tree_sitter_analyzer --show-common-queries

# Display query language support
uv run python -m tree_sitter_analyzer --show-query-languages
```

---

## 🛠️ Core Features

### 📊 Code Structure Analysis
- Class, method, field statistics
- Package information and import dependencies
- Complexity metrics (cyclomatic complexity)
- Precise line number positioning

### ✂️ Intelligent Code Extraction
- Precise extraction by line range
- Preserve original formatting and indentation
- Include position metadata
- Efficient handling of large files

### 🔍 Advanced Query Filtering
- **Exact Match**: `--filter "name=main"`
- **Pattern Match**: `--filter "name=~auth*"`
- **Parameter Filter**: `--filter "params=2"`
- **Modifier Filter**: `--filter "static=true,public=true"`
- **Compound Conditions**: Combine multiple conditions for precise queries

### 🔗 AI Assistant Integration
- **Claude Desktop** - Full MCP support
- **Cursor IDE** - Built-in MCP integration
- **Roo Code** - MCP protocol support
- **Other MCP-compatible tools** - Universal MCP server

### 🌍 Multi-Language Support
- **Java** - Full support (1103 lines of plugin), including Spring, JPA frameworks
- **Python** - Full support (584 lines of plugin), including type annotations, decorators
- **JavaScript** - Enterprise-grade support (1445 lines of plugin), including ES6+, React/Vue/Angular, JSX
- **TypeScript** - **Complete support** (1553 lines of plugin), including interfaces, types, decorators, TSX/JSX, framework detection
- **C/C++, Rust, Go** - Basic support

### 📁 Advanced File Search
Powerful file discovery and content search based on fd and ripgrep:
- **ListFilesTool** - Intelligent file discovery with multiple filtering conditions
- **SearchContentTool** - Intelligent content search with regular expressions
- **FindAndGrepTool** - Combined discovery and search, two-stage workflow

### 🏗️ Unified Element System
- **Single Element List** - Unified management of all code elements (classes, methods, fields, imports, packages)
- **Consistent Element Types** - Each element has an `element_type` attribute
- **Simplified API** - Clearer interfaces and reduced complexity
- **Better Maintainability** - Single source of truth for all code elements

---

## 🏆 Quality Assurance

### 📊 Quality Metrics
- **1,893 Tests** - 100% pass rate ✅
- **71.48% Code Coverage** - Comprehensive test suite
- **Zero Test Failures** - Production ready
- **Cross-Platform Support** - Windows, macOS, Linux

### ⚡ Latest Quality Achievements (v1.6.0)
- ✅ **Cross-Platform Path Compatibility** - Fixed Windows short path names and macOS symlink differences
- ✅ **Enterprise-Grade Reliability** - 50+ comprehensive test cases ensure stability
- ✅ **GitFlow Implementation** - Professional development/release branch strategy
- ✅ **AI Collaboration Optimization** - Specialized quality control for AI-assisted development

### ⚙️ Running Tests
```bash
# Run all tests
uv run pytest tests/ -v

# Generate coverage report
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html --cov-report=term-missing

# Run specific tests
uv run pytest tests/test_mcp_server_initialization.py -v
```

### 📈 Test Coverage Details

**Core Modules:**
- **Language Detector**: 98.41% (Excellent) - Automatic programming language recognition
- **CLI Main Entry**: 94.36% (Excellent) - Command-line interface
- **Query Filter System**: 96.06% (Excellent) - Code query and filtering
- **Query Service**: 86.25% (Good) - Query execution engine
- **MCP Error Handling**: 82.76% (Good) - AI assistant integration error handling

**Language Plugins:**
- **Java Plugin**: 73.00% (Good) - 1103 lines of code, full enterprise-grade support
- **JavaScript Plugin**: 68.31% (Good) - 1445 lines of code, modern ES6+ feature support
- **Python Plugin**: 63.26% (Good) - 584 lines of code, full type annotation support

**MCP Tools:**
- **File Search Tool**: 88.77% (Excellent) - fd/ripgrep integration
- **Content Search Tool**: 92.70% (Excellent) - Regular expression search
- **Combined Search Tool**: 91.57% (Excellent) - Two-stage search

### ✅ Documentation Verification Status

**All content in this README has been verified:**
- ✅ **All Commands Tested** - Every CLI command has been run and verified in a real environment
- ✅ **All Data Authentic** - Coverage rates, test counts, and other data come directly from test reports
- ✅ **SMART Workflow Authentic** - Demonstrated based on actual BigService.java (1419 lines)
- ✅ **Cross-Platform Verified** - Tested on Windows, macOS, Linux environments

**Verification Environment:**
- Operating Systems: Windows 10, macOS, Linux
- Python Version: 3.10+
- Project Version: tree-sitter-analyzer v1.6.2
- Test Files: BigService.java (1419 lines), sample.py (256 lines), MultiClass.java (54 lines)

---

## 📚 Documentation & Support

### 📖 Complete Documentation
- **[User MCP Setup Guide](MCP_SETUP_USERS.md)** - Simple configuration guide
- **[Developer MCP Setup Guide](MCP_SETUP_DEVELOPERS.md)** - Local development configuration
- **[Project Root Configuration](PROJECT_ROOT_CONFIG.md)** - Complete configuration reference
- **[API Documentation](docs/api.md)** - Detailed API reference
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute code
- **[Onboarding & Training Guide](training/README.md)** - System onboarding materials for new members/maintainers

### 🤖 AI Collaboration Support
This project supports AI-assisted development with specialized quality control:

```bash
# Pre-generation checks for AI systems
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all
```

📖 **Detailed Guides**:
- [AI Collaboration Guide](AI_COLLABORATION_GUIDE.md)
- [LLM Coding Guidelines](LLM_CODING_GUIDELINES.md)

### 💝 Sponsors & Acknowledgments

**[@o93](https://github.com/o93)** - *Primary Sponsor & Supporter*
- 🚀 **MCP Tool Enhancement**: Sponsored comprehensive MCP fd/ripgrep tool development
- 🧪 **Test Infrastructure**: Implemented enterprise-grade test coverage (50+ comprehensive test cases)
- 🔧 **Quality Assurance**: Supported bug fixes and performance improvements
- 💡 **Innovation Support**: Enabled early release of advanced file search and content analysis features

**[💖 Sponsor this project](https://github.com/sponsors/aimasteracc)** to help us continue building excellent tools for the developer community!

---

## 🤝 Contributing & License

### 🤝 Contributing Guide

We welcome contributions of all kinds! Please check the [Contributing Guide](CONTRIBUTING.md) for details.

### ⭐ Give us a Star!

If this project helps you, please give us a ⭐ on GitHub - it's the greatest support for us!

### 📄 License

MIT License - See [LICENSE](LICENSE) file for details.

---

**🎯 Built for developers handling large codebases and AI assistants**

*Let every line of code be understood by AI, let every project break through token limits*