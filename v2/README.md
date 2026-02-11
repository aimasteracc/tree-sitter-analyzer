# Tree-Sitter Analyzer v2

[![Tests](https://github.com/aimasteracc/tree-sitter-analyzer/actions/workflows/test.yml/badge.svg?branch=v2-rewrite)](https://github.com/aimasteracc/tree-sitter-analyzer/actions/workflows/test.yml)
[![Quality](https://github.com/aimasteracc/tree-sitter-analyzer/actions/workflows/quality.yml/badge.svg?branch=v2-rewrite)](https://github.com/aimasteracc/tree-sitter-analyzer/actions/workflows/quality.yml)
[![codecov](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/v2-rewrite/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

> Enterprise-grade code analysis for the AI era. Built for AI assistants with token optimization, fast search, and multi-language support.

## Why tree-sitter-analyzer?

AI assistants need to understand code, but raw source files waste tokens and lose structure. tree-sitter-analyzer solves this:

| Problem | Solution |
|---------|----------|
| AI context windows are limited | **TOON format**: 50-70% token reduction |
| AI can't parse code structure | **Tree-sitter parsing**: AST-level understanding |
| Searching large codebases is slow | **fd + ripgrep**: 10-20x faster than grep |
| AI tools lack code context | **MCP server**: Seamless AI assistant integration |

## Quick Start

### Installation

```bash
# Clone and install
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer/v2

# Install with uv (recommended)
uv sync --extra dev --extra languages

# Verify
uv run pytest tests/ -q --no-cov
```

### CLI Usage

```bash
# Analyze a Python file
uv run tsa analyze src/main.py

# Get a quick summary
uv run tsa analyze src/main.py --summary

# TOON format (minimal tokens for AI)
uv run tsa analyze src/main.py --format toon

# Search files (uses fd)
uv run tsa search-files . "*.py"

# Search content (uses ripgrep)
uv run tsa search-content . "def main"
```

### Python API

```python
from tree_sitter_analyzer_v2.api import TreeSitterAnalyzerAPI

api = TreeSitterAnalyzerAPI(project_root="/path/to/project")

# Analyze a file
result = api.analyze_file("src/main.py")
print(result["classes"])    # List of classes with methods, fields
print(result["functions"])  # Top-level functions

# Format for AI consumption
formatted = api.analyze_file("src/main.py", format="toon")
```

### MCP Server (for AI Assistants)

Add to your AI assistant's MCP configuration:

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"]
    }
  }
}
```

**Available MCP Tools:**
- `check_code_scale` - File metrics: lines, classes, methods, complexity
- `analyze_code_structure` - Detailed structure table
- `extract_code_section` - Read specific line ranges
- `query_code` - Query methods, classes with filters
- `search_content` - Ripgrep-powered content search
- `list_files` - fd-powered file discovery
- `find_and_grep` - Two-stage file find + content search
- `build_code_graph` - Cross-file dependency analysis

## Features

### Multi-Language Support

Currently supported: **Python**, **Java**, **TypeScript/JavaScript**

Planned (v2.0 GA): C/C++, C#, Go, Rust, Kotlin, PHP, Ruby, SQL, HTML, CSS, YAML, Markdown

### Token-Optimized Output (TOON)

TOON format reduces token usage by 50-70% while preserving all structural information:

```
# Standard JSON output: ~800 tokens
{"classes": [{"name": "Calculator", "methods": [{"name": "add", ...}]}]}

# TOON output: ~300 tokens
CLS Calculator L1-50
  MTD add(a:int,b:int)->int L5 PUB
  MTD subtract(a:int,b:int)->int L15 PUB
  FLD result:int L3 PRI
```

### Code Graph Analysis

Analyze cross-file dependencies, call chains, and import graphs:

```python
# Build a code graph for your project
result = api.build_code_graph(directory="src/", graph_type="calls")
# Returns: nodes, edges, entry points, complexity metrics
```

### Fast Search

Powered by [fd](https://github.com/sharkdp/fd) and [ripgrep](https://github.com/BurntSushi/ripgrep):

```bash
# Find all Python files (fd)
uv run tsa search-files . --type py

# Search for class definitions (ripgrep)
uv run tsa search-content . "class.*Service" --type py
```

## Project Stats

| Metric | Value |
|--------|-------|
| Tests | **903 passing** (4 skipped) |
| Coverage | **91%** |
| Lint errors | **0** (ruff) |
| Type errors | **0** (mypy) |
| Languages | Python, Java, TypeScript/JS |
| MCP Tools | 8 |

## Development

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- [fd](https://github.com/sharkdp/fd) (optional, for fast file search)
- [ripgrep](https://github.com/BurntSushi/ripgrep) (optional, for fast content search)

### Setup

```bash
cd v2
uv sync --extra dev --extra languages
```

### Quality Checks

```bash
# Run all tests
uv run pytest tests/ -v

# Lint
uv run ruff check tree_sitter_analyzer_v2/

# Format
uv run ruff format tree_sitter_analyzer_v2/

# Type check
uv run mypy tree_sitter_analyzer_v2/
```

### TDD Workflow

We follow strict Test-Driven Development. See [docs/tdd-workflow.md](docs/tdd-workflow.md).

```
1. RED    - Write a failing test
2. GREEN  - Write minimal code to pass
3. REFACTOR - Improve while keeping tests green
```

## Architecture

```
tree_sitter_analyzer_v2/
├── core/           # Parser, detector, types, token optimizer
├── languages/      # Python, Java, TypeScript parsers
├── formatters/     # TOON, Markdown, Summary formatters
├── graph/          # Code graph: builder, imports, cross-file analysis
├── mcp/            # MCP server + 8 tools
├── api/            # Python API interface
├── cli/            # Command-line interface
├── search.py       # fd + ripgrep integration
└── security/       # Path validation, security checks
```

**Design Principles:**
- No file exceeds 300 lines
- 100% type hints (mypy strict mode)
- TDD: all code written tests-first
- AI-first: TOON format by default for MCP

## Roadmap

See [ROADMAP.md](ROADMAP.md) for detailed plans.

**Next milestones:**
- **v2.0.0-alpha.2**: Project polish, 90%+ coverage, examples
- **v2.0.0-alpha.3**: 5 more languages (C/C++, Go, Rust, C#, Kotlin)
- **v2.0.0-beta.1**: MCP production-ready
- **v2.0.0**: General availability with 17 languages

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Priority areas:**
1. Language plugins (add new language support)
2. Performance optimization
3. Documentation and examples
4. Test coverage improvements

## License

MIT License - see [LICENSE](../LICENSE) for details.

## Acknowledgments

- [tree-sitter](https://tree-sitter.github.io/) - Incremental parsing
- [fd](https://github.com/sharkdp/fd) - Fast file finder
- [ripgrep](https://github.com/BurntSushi/ripgrep) - Fast content search
- [Anthropic MCP](https://modelcontextprotocol.io/) - AI tool protocol

---

> **Note**: v2 is a complete rewrite in alpha. For stable production use, see [v1.9.17.1](https://github.com/aimasteracc/tree-sitter-analyzer/releases/tag/v1.9.17.1).
