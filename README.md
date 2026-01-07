# 🌳 Tree-sitter Analyzer

**English** | **[日本語](README_ja.md)** | **[简体中文](README_zh.md)**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-8409%20passed-brightgreen.svg)](#-quality--testing)
[![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Version](https://img.shields.io/badge/version-1.10.3-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

> 🚀 **Enterprise-Grade Code Analysis Tool for the AI Era** - Deep AI Integration · Powerful Search · 17 Languages · Intelligent Analysis

---

## ✨ What's New in v1.10.0

- **Format Change Management System**: Complete system for tracking and managing format changes with database tracking and pre-commit validation
- **Behavior Profile Comparison**: CLI tool for comparing code analysis behavior profiles between versions
- **Enhanced Language Support**: Added Go, Rust, and Kotlin to core dependencies for comprehensive systems programming language support
- **C++ Formatter**: Dedicated formatter with Bandit security scanning
- **Project Governance**: Added comprehensive governance documents and CI/CD workflows
- **6,246 tests** with 100% pass rate and 80.33% coverage

📖 **[Full Changelog](CHANGELOG.md)** for complete version history.

---

## 🎬 See It In Action

<!-- GIF placeholder - see docs/assets/demo-placeholder.md for creation instructions -->
*Demo GIF coming soon - showcasing AI integration with SMART workflow*

---

## 🚀 5-Minute Quick Start

### Prerequisites

```bash
# Install uv (required)
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Install fd + ripgrep (required for search features)
brew install fd ripgrep          # macOS
winget install sharkdp.fd BurntSushi.ripgrep.MSVC  # Windows
```

📖 **[Detailed Installation Guide](docs/installation.md)** for all platforms.

### Verify Installation

```bash
uv run tree-sitter-analyzer --show-supported-languages
```

---

## 🤖 AI Integration

Configure your AI assistant to use Tree-sitter Analyzer via MCP protocol.

### Claude Desktop / Cursor / Roo Code

Add to your MCP configuration:

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": [
        "--from", "tree-sitter-analyzer[mcp]",
        "tree-sitter-analyzer-mcp"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "/path/to/your/project",
        "TREE_SITTER_OUTPUT_PATH": "/path/to/output/directory"
      }
    }
  }
}
```

**Configuration file locations:**
- **Claude Desktop**: `%APPDATA%\Claude\claude_desktop_config.json` (Windows) / `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
- **Cursor**: Built-in MCP settings
- **Roo Code**: MCP configuration

After restart, tell the AI: `Please set the project root directory to: /path/to/your/project`

📖 **[MCP Tools Reference](docs/api/mcp_tools_specification.md)** for complete API documentation.

---

## 💻 Common CLI Commands

### Installation

```bash
uv add "tree-sitter-analyzer[all,mcp]"  # Full installation
```

### Top 5 Commands

```bash
# 1. Analyze file structure
uv run tree-sitter-analyzer examples/BigService.java --table full

# 2. Quick summary
uv run tree-sitter-analyzer examples/BigService.java --summary

# 3. Extract code section
uv run tree-sitter-analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106

# 4. Find files and search content
uv run find-and-grep --roots . --query "class.*Service" --extensions java

# 5. Query specific elements
uv run tree-sitter-analyzer examples/BigService.java --query-key methods --filter "public=true"
```

<details>
<summary>📋 View Output Example</summary>

```
╭─────────────────────────────────────────────────────────────╮
│                   BigService.java Analysis                   │
├─────────────────────────────────────────────────────────────┤
│ Total Lines: 1419 | Code: 906 | Comments: 246 | Blank: 267  │
│ Classes: 1 | Methods: 66 | Fields: 9 | Complexity: 5.27 avg │
╰─────────────────────────────────────────────────────────────╯
```

</details>

📖 **[Complete CLI Reference](docs/cli-reference.md)** for all commands and options.

---

## 🌍 Supported Languages

| Language | Support Level | Key Features |
|----------|---------------|--------------|
| **Java** | ✅ Complete | Spring, JPA, enterprise features |
| **Python** | ✅ Complete | Type annotations, decorators |
| **TypeScript** | ✅ Complete | Interfaces, types, TSX/JSX |
| **JavaScript** | ✅ Complete | ES6+, React/Vue/Angular |
| **C** | ✅ Complete | Functions, structs, unions, enums, preprocessor |
| **C++** | ✅ Complete | Classes, templates, namespaces, inheritance |
| **C#** | ✅ Complete | Records, async/await, attributes |
| **SQL** | ✅ Enhanced | Tables, views, procedures, triggers |
| **HTML** | ✅ Complete | DOM structure, element classification |
| **CSS** | ✅ Complete | Selectors, properties, categorization |
| **Go** | ✅ Complete | Structs, interfaces, goroutines |
| **Rust** | ✅ Complete | Traits, impl blocks, macros |
| **Kotlin** | ✅ Complete | Data classes, coroutines |
| **PHP** | ✅ Complete | PHP 8+, attributes, traits |
| **Ruby** | ✅ Complete | Rails patterns, metaprogramming |
| **YAML** | ✅ Complete | Anchors, aliases, multi-document |
| **Markdown** | ✅ Complete | Headers, code blocks, tables |

📖 **[Features Documentation](docs/features.md)** for language-specific details.

---

## 📊 Features Overview

| Feature | Description | Learn More |
|---------|-------------|------------|
| **SMART Workflow** | Set-Map-Analyze-Retrieve-Trace methodology | [Guide](docs/smart-workflow.md) |
| **MCP Protocol** | Native AI assistant integration | [API Docs](docs/api/mcp_tools_specification.md) |
| **Token Optimization** | Up to 95% token reduction | [Features](docs/features.md) |
| **File Search** | fd-based high-performance discovery | [CLI Reference](docs/cli-reference.md) |
| **Content Search** | ripgrep regex search | [CLI Reference](docs/cli-reference.md) |
| **Security** | Project boundary protection | [Architecture](docs/architecture.md) |

---

## 🏆 Quality & Testing

| Metric | Value |
|--------|-------|
| **Tests** | 6,246 passed ✅ |
| **Coverage** | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| **Type Safety** | 100% mypy compliance |
| **Platforms** | Windows, macOS, Linux |

```bash
# Run tests
uv run pytest tests/ -v

# Generate coverage report
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html
```

---

## 🛠️ Development

### Setup

```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

### Quality Checks

```bash
uv run pytest tests/ -v                    # Run tests
uv run python check_quality.py --new-code-only  # Quality check
uv run python llm_code_checker.py --check-all   # AI code check
```

📖 **[Architecture Guide](docs/architecture.md)** for system design details.

---

## 🤝 Contributing & License

We welcome contributions! See **[Contributing Guide](docs/CONTRIBUTING.md)** for development guidelines.

### ⭐ Support

If this project helps you, please give us a ⭐ on GitHub!

### 💝 Sponsors

**[@o93](https://github.com/o93)** - Lead Sponsor supporting MCP tool enhancement, test infrastructure, and quality improvements.

**[💖 Sponsor this project](https://github.com/sponsors/aimasteracc)**

### 📄 License

MIT License - see [LICENSE](LICENSE) file.

---

## 🧪 Testing

### Test Coverage

| Metric | Value |
|--------|-------|
| **Total Tests** | 2,411 tests ✅ |
| **Test Pass Rate** | 100% (2,411/2,411) |
| **Code Coverage** | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| **Type Safety** | 100% mypy compliance |

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test category
uv run pytest tests/unit/ -v              # Unit tests
uv run pytest tests/integration/ -v         # Integration tests
uv run pytest tests/regression/ -m regression  # Regression tests
uv run pytest tests/benchmarks/ -v         # Benchmark tests

# Run with coverage
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

# Run property-based tests
uv run pytest tests/property/

# Run performance benchmarks
uv run pytest tests/benchmarks/ --benchmark-only
```

### Test Documentation

| Document | Description |
|----------|-------------|
| [Test Writing Guide](docs/test-writing-guide.md) | Comprehensive guide for writing tests |
| [Regression Testing Guide](docs/regression-testing-guide.md) | Golden Master methodology and regression testing |
| [Testing Documentation](docs/TESTING.md) | Project testing standards |

### Test Categories

- **Unit Tests** (2,087 tests): Test individual components in isolation
- **Integration Tests** (187 tests): Test component interactions
- **Regression Tests** (70 tests): Ensure backward compatibility and format stability
- **Property Tests** (75 tests): Hypothesis-based property testing
- **Benchmark Tests** (20 tests): Performance monitoring and regression detection
- **Compatibility Tests** (30 tests): Cross-version compatibility validation

### CI/CD Integration

- **Test Coverage Workflow**: Automated coverage checks on PRs and pushes
- **Regression Tests Workflow**: Golden Master validation and format stability checks
- **Performance Benchmarks**: Daily benchmark runs with trend analysis
- **Quality Checks**: Automated linting, type checking, and security scanning

### Contributing Tests

When contributing new features:

1. **Write Tests**: Follow the [Test Writing Guide](docs/test-writing-guide.md)
2. **Ensure Coverage**: Maintain >80% code coverage
3. **Run Locally**: `uv run pytest tests/ -v`
4. **Check Quality**: `uv run ruff check . && uv run mypy tree_sitter_analyzer/`
5. **Update Docs**: Document new tests and features

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Installation Guide](docs/installation.md) | Setup for all platforms |
| [CLI Reference](docs/cli-reference.md) | Complete command reference |
| [SMART Workflow](docs/smart-workflow.md) | AI-assisted analysis guide |
| [MCP Tools API](docs/api/mcp_tools_specification.md) | MCP integration details |
| [Features](docs/features.md) | Language support details |
| [Architecture](docs/architecture.md) | System design |
| [Contributing](docs/CONTRIBUTING.md) | Development guidelines |
| [Test Writing Guide](docs/test-writing-guide.md) | Comprehensive test writing guide |
| [Regression Testing Guide](docs/regression-testing-guide.md) | Golden Master methodology |
| [Changelog](CHANGELOG.md) | Version history |

---

**🎯 Built for developers working with large codebases and AI assistants**

*Making every line of code understandable to AI, enabling every project to break through token limitations*
