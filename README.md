# Tree-sitter Analyzer

An extensible multi-language code analyzer framework using Tree-sitter with dynamic plugin architecture, designed to solve the problem of large code files exceeding LLM single-pass token limits.

**Available as both CLI tool and MCP server.**

## Core Features

1. **Code Scale Analysis** - Get overall structure without reading complete files
2. **Targeted Code Extraction** - Extract specific line ranges efficiently  
3. **Code Position Information** - Get detailed position data for precise extraction

## Installation

```bash
# Using uv (recommended)
uv add "tree-sitter-analyzer[java]"

# Using pip
pip install "tree-sitter-analyzer[java]"
```

## Usage

### CLI Commands

```bash
# Code scale analysis
python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text

# Partial code extraction
python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86

# Position information table
python -m tree_sitter_analyzer examples/Sample.java --table=full
```

### MCP Server

```bash
# Start MCP server
python -m tree_sitter_analyzer.mcp.server
```

## Documentation

For detailed documentation in Chinese, see [README_zh.md](README_zh.md).

## License


## Development

For developers and contributors:

```bash
# Clone the repository
git clone https://github.com/your-username/tree-sitter-analyzer.git
cd tree-sitter-analyzer

# Install development dependencies
uv sync

# Run tests
pytest tests/ -v
```
MIT License