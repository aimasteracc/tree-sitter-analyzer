# MCP Setup Guide for Developers

**Local development setup for Tree-sitter Analyzer MCP server**

## Prerequisites

- Python 3.10+
- uv package manager
- Git
- Claude Desktop (for testing)

## Development Setup

### 1. Clone and Setup Project

```bash
# Clone the repository
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer

# Install development dependencies
uv sync --extra all --extra mcp

# Verify installation
uv run python -c "import tree_sitter_analyzer; print('Development setup OK')"
```

### 2. Configure Claude Desktop for Local Development

Add this configuration to your Claude Desktop config file:

```json
{
  "mcpServers": {
    "tree-sitter-analyzer-dev": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/tree-sitter-analyzer",
        "python",
        "-m",
        "tree_sitter_analyzer.mcp.server"
      ]
    }
  }
}
```

**Important:** Replace `/absolute/path/to/tree-sitter-analyzer` with your actual project path.

### 3. Dual Configuration (Development + Stable)

For testing both versions, use this configuration:

```json
{
  "mcpServers": {
    "tree-sitter-analyzer-dev": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/your/tree-sitter-analyzer",
        "python",
        "-m",
        "tree_sitter_analyzer.mcp.server"
      ],
      "disabled": false
    },
    "tree-sitter-analyzer-stable": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "tree-sitter-analyzer[mcp]",
        "python",
        "-m",
        "tree_sitter_analyzer.mcp.server"
      ],
      "disabled": true
    }
  }
}
```

Switch between versions by changing the `disabled` flag.

## Development Workflow

### 1. Make Changes
```bash
# Edit code
vim tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py

# Run tests
pytest tests/ -v

# Test CLI
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced
```

### 2. Test MCP Server
```bash
# Test server manually
uv run python -m tree_sitter_analyzer.mcp.server

# Should show server initialization logs
```

### 3. Test with Claude Desktop
- Restart Claude Desktop
- Test your changes through the AI assistant
- Check logs for any issues

## Debugging

### Enable Debug Logging
```bash
export TREE_SITTER_ANALYZER_LOG_LEVEL=DEBUG
uv run python -m tree_sitter_analyzer.mcp.server
```

### Common Issues

**Import Errors:**
```bash
# Check dependencies
uv run python -c "import tree_sitter_analyzer.mcp.server"
```

**Path Issues:**
- Use absolute paths in MCP configuration
- Verify project directory structure

**MCP Protocol Issues:**
- Check Claude Desktop logs
- Verify MCP package version: `uv run python -c "import mcp; print(mcp.__version__)"`

## Testing Changes

### Unit Tests
```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_mcp_tools.py -v

# Run with coverage
pytest tests/ --cov=tree_sitter_analyzer
```

### Integration Tests
```bash
# Test MCP tools
uv run python -m pytest tests/test_mcp_integration.py -v
```

### Manual Testing
```bash
# Test CLI commands
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full

# Test partial read
uv run python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
```

## Contributing

1. Create feature branch
2. Make changes
3. Run tests: `pytest tests/ -v`
4. Test MCP integration
5. Submit pull request

## Need Help?

- [GitHub Issues](https://github.com/aimasteracc/tree-sitter-analyzer/issues)
- [User Setup Guide](MCP_SETUP_USERS.md) - For end users
- [API Documentation](docs/api.md)