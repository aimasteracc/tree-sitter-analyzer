# 🌳 Tree-sitter Analyzer

**English** | **[日本語](README_ja.md)** | **[简体中文](README_zh.md)**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-9600%2B%20passed-brightgreen.svg)](#-quality--testing)
[![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Version](https://img.shields.io/badge/version-1.11.1-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

> **Tree-Sitter-Analyzer is a local-first code context engine for AI-assisted development** — combining fast repository retrieval, AST-based structural analysis, and secure MCP integration.

Its job is not just to parse code. Its job is to help humans and AI agents fetch only the code context they actually need, safely, quickly, and with structural precision.

```
find the right files → find the right matches → extract the right structure → send only the right context
```

*Claude doesn't need to read your entire codebase. Neither do you.*

**17 languages · Project-boundary security · Claude Desktop / Cursor / Roo Code · CLI + Python API**

---

## ✨ What's New in v1.11.1

- **Claude knows your project's skeleton before reading a single file**: `get_project_summary` returns PageRank-ranked architecture nodes — the classes everything else extends. Validated on elasticsearch (40k files), spring-framework (11k), mybatis, spring-petclinic.
- **Touch a critical class? Claude stops you first**: `modification_guard` reads the architecture ranking. Rename `Writeable` in elasticsearch → verdict UNSAFE, rank #1, 4745 callers. No surprises.
- **New language = new file, not a rewrite**: Plugin `edge_extractors/` package — Java, Python, TypeScript ship today. Adding Kotlin is one file + one line.
- **2x faster exploration on unfamiliar projects**: End-to-end tested — 5 tool calls with summary vs 10+ without. Claude skips the blind search phase entirely.
- **Zero-config first-party filtering**: Java reads groupId from pom.xml. Python uses `sys.stdlib_module_names`. No blacklists to maintain. Ever.

📖 **[Full Changelog](CHANGELOG.md)** for complete version history.
---

## 🎬 See It In Action

<!-- GIF placeholder - see docs/assets/demo-placeholder.md for creation instructions -->
*Demo GIF coming soon - showcasing AI integration with SMART workflow*

---

## 🎯 Why Tree-sitter Analyzer

Tree-sitter Analyzer is an open-source, local-first code context engine for helping AI assistants read only what matters in large codebases.

- **Minimal context, not whole-file stuffing**: retrieve the smallest useful code regions before sending them to AI
- **Evidence-based analysis**: combine tree-sitter structure with `fd` and `ripgrep` to surface relevant files, symbols, and paths
- **No heavy preprocessing required**: useful on messy repositories where full indexing can be slow, stale, or difficult to maintain

### Common Use Cases

- Understand what a very large file or module is doing without loading the entire file into an AI prompt
- Trace business logic, UI handlers, or bug-related code paths across a complex repository
- Narrow AI context for Java and other large codebases before asking for analysis or changes

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

This works especially well when your assistant struggles with very large files, noisy repository-wide context, or legacy code that is too expensive to load all at once.

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
| **Outline-First Navigation** | `get_code_outline` — hierarchical structure map before content retrieval | [MCP Tools](docs/api/mcp_tools_specification.md) |
| **MCP Protocol** | Native AI assistant integration | [API Docs](docs/api/mcp_tools_specification.md) |
| **Token Optimization** | TOON format delivers 54-56% token reduction; token-aware controls for large AI workflows | [Features](docs/features.md) |
| **File Search** | fd-based high-performance discovery | [CLI Reference](docs/cli-reference.md) |
| **Content Search** | ripgrep regex search | [CLI Reference](docs/cli-reference.md) |
| **Security** | Project boundary protection | [Architecture](docs/architecture.md) |
| **Error Recovery** | Auto encoding detection (UTF-8/GBK/Shift-JIS), partial parsing, timeout protection | [Architecture](docs/architecture.md) |
| **Performance** | Plugin registry with load metrics, performance regression tests | [Architecture](docs/architecture.md) |

---

## 🔬 Grammar Coverage (MECE Framework)

Tree-sitter Analyzer guarantees **zero False Positives** in grammar coverage validation across all 17 supported languages.

### Phase 1: MECE Architecture (2026-03)

**New Architecture**:
- Tracks **syntactic paths** `(node_type, parent_path)` instead of just node types
- Uses **exact node identity matching** (type + byte range + parent chain + file path)
- Eliminates nested node misclassification (wrapper nodes no longer cause False Positives)

**Why It Matters**:

```python
# OLD method: Position overlap → False Positives
@decorator       # Plugin extracts this
def foo():       # Validator incorrectly marks this as "covered" (it's not!)
    pass

# NEW method: Exact identity matching → Zero False Positives
# Only nodes actually extracted by the plugin are marked as covered
```

### Validation Commands

```bash
# Validate single language
python -c "from tree_sitter_analyzer.grammar_coverage.validator import validate_plugin_coverage_sync; r = validate_plugin_coverage_sync('python'); print(f'{r.coverage_percentage:.1f}% coverage')"

# Validate all languages
python -c "
from tree_sitter_analyzer.grammar_coverage.validator import validate_plugin_coverage_sync
langs = ['python', 'javascript', 'java', 'go', 'typescript', 'c', 'cpp', 'rust', 'ruby', 'php', 'kotlin', 'swift', 'scala', 'bash', 'yaml', 'json', 'sql']
for lang in langs:
    r = validate_plugin_coverage_sync(lang)
    status = '✅' if r.coverage_percentage == 100.0 else '❌'
    print(f'{status} {lang}: {r.coverage_percentage:.1f}% ({r.covered_node_types}/{r.total_node_types})')
"
```

**Example Output** (new format):

```
✅ python: 100.0% (57/57 node types covered)
✅ javascript: 100.0% (58/58 node types covered)
✅ typescript: 100.0% (114/114 node types covered)
...
✅ sql: 100.0% (155/155 node types covered)
```

### MECE Guarantees

- **Mutually Exclusive**: Each node has a unique `(type, parent_path)` → no double counting
- **Collectively Exhaustive**: Full AST traversal → no missing nodes
- **Zero False Positives**: Exact matching → only truly extracted nodes marked as covered

📖 **[Grammar Coverage Framework](docs/grammar-coverage-framework.md)** for technical details and architecture.

---

## 🏆 Quality & Testing

| Metric | Value |
|--------|-------|
| **Tests** | 9,600+ automated tests |
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

## 🔒 Security & Architecture

Tree-sitter Analyzer is designed with **security-by-default** principles for AI-assisted development workflows.

### Security Model

**Project Boundary Enforcement**
- All MCP tools validate file paths against project root boundaries
- No access to files outside the configured project directory
- Symlink traversal prevention
- Path normalization prevents `../` escape attempts

**Input Validation**
- JSON Schema validation on all MCP tool parameters
- Type-safe Python API with strict mypy compliance
- Sanitized user inputs before shell command execution
- Pattern validation for glob/regex searches

**No Remote Execution**
- 100% local processing — no cloud dependencies
- No telemetry or data collection
- No network calls except optional PyPI version checks
- Source code analysis stays on your machine

**Secure Defaults**
- Read-only file operations by default
- Explicit opt-in required for any file modifications
- Sandboxed subprocess execution for external tools (fd, ripgrep)
- Environment variable isolation

### Architecture Principles

```
┌─────────────────────────────────────────────────────────┐
│  AI Assistant (Claude Desktop / Cursor / Roo Code)     │
└────────────────────┬────────────────────────────────────┘
                     │ MCP Protocol (JSON-RPC)
                     ▼
┌─────────────────────────────────────────────────────────┐
│  MCP Server Layer                                       │
│  • Input validation (JSON Schema)                       │
│  • Project boundary checks                              │
│  • Tool dispatch                                        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Analysis Engine                                        │
│  • Tree-sitter AST parsing (17 languages)               │
│  • Fast file search (fd)                                │
│  • Content search (ripgrep)                             │
│  • Output formatting (JSON / TOON)                      │
└─────────────────────────────────────────────────────────┘
```

**Key Security Boundaries**:
1. **MCP Protocol**: AI can only call explicitly defined tools with validated schemas
2. **Project Root**: File operations confined to configured directory
3. **Read-Only**: No destructive operations without explicit user consent
4. **Local-First**: All processing happens on your machine

### Security Testing

- **9,600+ automated tests** including security-focused edge cases
- **100% mypy type safety** prevents entire classes of bugs
- **CI/CD security scans**: Bandit (Python security), safety (dependency vulnerabilities)
- **Manual security review** of all MCP tool implementations

### Reporting Security Issues

Found a security concern? Please email aimasteracc@gmail.com or open a private security advisory on GitHub.

**We do NOT use automated security badge services** — our security posture is documented through architecture, testing, and code review, not third-party scores.

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
| **Test Suite** | 9,600+ automated tests across unit, integration, regression, property, benchmark, and compatibility layers |
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

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **Regression Tests**: Ensure backward compatibility and format stability
- **Property Tests**: Use Hypothesis-based invariant checking
- **Benchmark Tests**: Track performance and regression signals
- **Compatibility Tests**: Validate cross-version behavior

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
