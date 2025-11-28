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

### 2. Install fd and ripgrep (Required for search functionality)

**fd** and **ripgrep** are high-performance file and content search tools used for advanced MCP functionality.

| Operating System | Package Manager | Installation Command | Notes |
|-----------------|----------------|---------------------|-------|
| **macOS** | Homebrew | `brew install fd ripgrep` | Recommended |
| **Windows** | winget | `winget install sharkdp.fd BurntSushi.ripgrep.MSVC` | Recommended |
| | Chocolatey | `choco install fd ripgrep` | Alternative |
| | Scoop | `scoop install fd ripgrep` | Alternative |
| **Ubuntu/Debian** | apt | `sudo apt install fd-find ripgrep` | Use `fdfind` alias |
| **CentOS/RHEL/Fedora** | dnf | `sudo dnf install fd-find ripgrep` | Official repository |
| **Arch Linux** | pacman | `sudo pacman -S fd ripgrep` | Official repository |

#### Verify fd and ripgrep installation

```bash
fd --version
rg --version
```

> **⚠️ Important Note:** 
> - **uv** is required for running all functionality
> - **fd** and **ripgrep** are required for using advanced file search and content analysis features
> - If fd and ripgrep are not installed, basic code analysis functionality will still be available, but file search features will not work

## Installation Methods

### AI Users (MCP Integration)

For users integrating with AI assistants (Claude Desktop, Cursor, etc.):

**No additional installation required!** The MCP server runs directly using `uv run`.

#### Claude Desktop Configuration

1. Locate the configuration file:
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Linux**: `~/.config/claude/claude_desktop_config.json`

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

> **Note**: `TREE_SITTER_PROJECT_ROOT` is optional - you can set it dynamically via the AI assistant.

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
3. Install fd and ripgrep using winget or Chocolatey
4. Configure PATH if necessary

### macOS

1. Install Homebrew: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
2. Install dependencies: `brew install python@3.10 fd ripgrep`
3. Install uv (see above)

### Linux (Ubuntu/Debian)

```bash
# Install Python
sudo apt update
sudo apt install python3.10 python3.10-venv

# Install fd and ripgrep
sudo apt install fd-find ripgrep

# Note: fd is installed as 'fdfind' on Debian-based systems
# Create alias if needed:
alias fd='fdfind'

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
uv run list-files . --extensions py

# Test content search
uv run search-content --roots . --query "def " --include-globs "*.py"

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

#### "fd: command not found"

Install fd using your package manager (see Prerequisites).

For Debian/Ubuntu, note that fd is installed as `fdfind`:
```bash
alias fd='fdfind'
```

#### "rg: command not found"

Install ripgrep using your package manager (see Prerequisites).

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

