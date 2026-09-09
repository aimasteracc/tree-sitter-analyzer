# Installation Guide

This document provides comprehensive installation instructions for Tree-sitter Analyzer across all platforms and use cases.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation Methods](#installation-methods)
  - [AI Users (MCP Integration)](#ai-users-mcp-integration)
  - [CLI Users](#cli-users)
  - [Developers](#developers)
- [Platform-Specific Instructions](#platform-specific-instructions)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### 1. Install uv (Required)

**uv** is a fast Python package manager required to run tree-sitter-analyzer.

#### macOS/Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### Windows PowerShell

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### Verify uv installation

```bash
uv --version
```

### 2. Git and native search

Install Git for history and change analysis. File discovery and source verification run in Python; TSA does not require ripgrep or fd.

## Installation Methods

### AI Users (MCP Integration)

For users integrating with AI assistants (Claude Desktop, Cursor, etc.):

**No additional installation required!** The MCP server runs directly using `uv run`.

#### Claude Desktop Configuration

1. Locate the configuration file for your OS:

   | OS | Path |
   |---|---|
   | **Windows** | `%APPDATA%\Claude\claude_desktop_config.json` |
   | **macOS** | `~/Library/Application Support/Claude/claude_desktop_config.json` |
   | **Linux** | `~/.config/claude/claude_desktop_config.json` |

2. Add the following configuration:

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
        "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project",
        "TREE_SITTER_OUTPUT_PATH": "/absolute/path/to/output/directory"
      }
    }
  }
}
```

> **Note**: `TREE_SITTER_PROJECT_ROOT` must be an **absolute** path. The server enforces a security boundary (`SecurityValidator`) that rejects relative paths. You can also set it dynamically per-call via the AI assistant, but the value must still be absolute.

3. Restart your AI client
4. Verify by asking the AI to use the tree-sitter-analyzer tools

#### Cursor Configuration

Cursor has built-in MCP support. Use the same configuration format in Cursor settings.

#### Roo Code Configuration

Roo Code supports MCP protocol. Use the same server configuration.

### CLI Users

For developers who prefer command-line tools:

```bash
# Basic installation
uv add tree-sitter-analyzer

# Popular language packages (recommended)
uv add "tree-sitter-analyzer[popular]"

# Complete installation (including MCP support)
uv add "tree-sitter-analyzer[all,mcp]"
```

#### Installation Options

| Option | Description |
|--------|-------------|
| `tree-sitter-analyzer` | Core package only |
| `tree-sitter-analyzer[popular]` | Core + popular language support |
| `tree-sitter-analyzer[all]` | All language support |
| `tree-sitter-analyzer[mcp]` | MCP server support |
| `tree-sitter-analyzer[all,mcp]` | Everything |

### Developers

For contributors who need to modify source code:

```bash
# Clone repository
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer

# Install dependencies
uv sync --extra all --extra mcp

# Verify installation
uv run pytest tests/ -v --tb=short
```

## Platform-Specific Instructions

### Windows

1. Install Python 3.10+ from [python.org](https://python.org) or Microsoft Store
2. Install uv using PowerShell (see above)
3. Install Git for Windows
4. Configure PATH if necessary

### macOS

1. Install Homebrew: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
2. Install dependencies: `brew install python@3.10 git`
3. Install uv (see above)

### Linux (Ubuntu/Debian)

```bash
# Install Python
sudo apt update
sudo apt install python3.10 python3.10-venv

# Install Git
sudo apt install git

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Verification

### Basic Verification

```bash
# Check version
uv run tree-sitter-analyzer --show-supported-languages

# View help
uv run tree-sitter-analyzer --help

# Test basic analysis
uv run tree-sitter-analyzer examples/sample.py --summary
```

### MCP Server Verification

After configuring your AI client:

1. Start your AI client (Claude Desktop, Cursor, etc.)
2. Ask the AI: "Please use the tree-sitter-analyzer to check its version"
3. The AI should respond with version information

### Full Functionality Test

```bash
# Test file search
uv run tree-sitter-analyzer --project-card

# Verify live source references
uv run tree-sitter-analyzer --trace-impact --trace-impact-symbol main --format json

# Test code analysis
uv run tree-sitter-analyzer examples/BigService.java --table full
```

## Troubleshooting

### Common Issues

#### "uv: command not found"

Ensure uv is installed and in your PATH:
```bash
# Check installation
which uv  # macOS/Linux
where uv  # Windows

# Re-install if necessary
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### MCP Server Not Responding

1. Verify the configuration path is correct
2. Check that the command works manually:
   ```bash
   uvx --from tree-sitter-analyzer[mcp] tree-sitter-analyzer-mcp
   ```
3. Restart your AI client completely

#### Permission Denied Errors

Ensure you have read permissions for the project directory:
```bash
# Check permissions
ls -la /path/to/project

# Fix if necessary
chmod -R u+r /path/to/project
```

### Getting Help

- **GitHub Issues**: [Report bugs and request features](https://github.com/aimasteracc/tree-sitter-analyzer/issues)
- **Documentation**: See other guides in the `docs/` directory
- **Contributing Guide**: See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidance

