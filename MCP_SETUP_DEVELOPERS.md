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

#### Recommended Development Configuration

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
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}"
      }
    }
  }
}
```

**Important:** Replace `/absolute/path/to/tree-sitter-analyzer` with your actual project path.

## Project Root Configuration Options

The MCP server supports multiple ways to configure the project root directory for security and functionality:

### Configuration Priority (Highest to Lowest)

1. **Command Line Argument** (Highest Priority)
2. **Environment Variable** (Medium Priority)
3. **Auto-Detection** (Lowest Priority)

### Option 1: Environment Variable (Recommended)

```json
{
  "mcpServers": {
    "tree-sitter-analyzer-dev": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/tree-sitter-analyzer", "python", "-m", "tree_sitter_analyzer.mcp.server"],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}"
      }
    }
  }
}
```

**Benefits:**
- ✅ Automatically adapts to current workspace
- ✅ Works with any IDE supporting workspace variables
- ✅ Flexible and dynamic configuration

### Option 2: Command Line Argument

```json
{
  "mcpServers": {
    "tree-sitter-analyzer-dev": {
      "command": "uv",
      "args": [
        "run", "--directory", "/path/to/tree-sitter-analyzer",
        "python", "-m", "tree_sitter_analyzer.mcp.server",
        "--project-root", "/specific/project/path"
      ]
    }
  }
}
```

**Use cases:**
- 🎯 Fixed project path requirements
- 🎯 Override environment variable settings
- 🎯 Multi-project environments

### Option 3: Auto-Detection (Zero Configuration)

```json
{
  "mcpServers": {
    "tree-sitter-analyzer-dev": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/tree-sitter-analyzer", "python", "-m", "tree_sitter_analyzer.mcp.server"]
    }
  }
}
```

**How it works:**
- 🔍 Searches for project markers (.git, pyproject.toml, package.json, etc.)
- 🔍 Traverses up directory tree from server working directory
- 🔍 Falls back to current working directory if no markers found

**Supported project markers:**
- Version control: `.git`, `.hg`, `.svn`
- Python: `pyproject.toml`, `setup.py`, `requirements.txt`
- JavaScript: `package.json`, `yarn.lock`, `node_modules`
- Java: `pom.xml`, `build.gradle`, `gradlew`
- And many more...

## Testing Project Root Configuration

### Test Auto-Detection

```bash
# Test from project directory
cd /your/project/directory
uv run python -m tree_sitter_analyzer.mcp.server --help

# Should show detected project root in logs
```

### Test Command Line Override

```bash
# Test explicit project root
uv run python -m tree_sitter_analyzer.mcp.server --project-root /specific/path --help
```

### Test Environment Variable

```bash
# Test environment variable
export TREE_SITTER_PROJECT_ROOT=/your/project
uv run python -m tree_sitter_analyzer.mcp.server --help
```

### Test Priority Handling

```bash
# Test priority (command line should win)
export TREE_SITTER_PROJECT_ROOT=/env/path
uv run python -m tree_sitter_analyzer.mcp.server --project-root /cmd/path --help
# Should use /cmd/path
```

## Debugging Project Root Issues

### Check Current Configuration

```bash
# Run with verbose logging
uv run python -c "
from tree_sitter_analyzer.project_detector import detect_project_root
import logging
logging.basicConfig(level=logging.INFO)
result = detect_project_root()
print(f'Detected project root: {result}')
"
```

### Verify Security Boundaries

```bash
# Test file access validation
uv run python -c "
from tree_sitter_analyzer.security import SecurityValidator
validator = SecurityValidator('/your/project/root')
is_valid, msg = validator.validate_file_path('/your/project/root/src/file.py')
print(f'Valid: {is_valid}, Message: {msg}')
"
```

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
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text
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
