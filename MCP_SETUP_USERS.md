# MCP Setup Guide for Users

**Simple setup for using Tree-sitter Analyzer with Claude Desktop**

## Prerequisites

- Claude Desktop installed
- Basic command line knowledge

## Step 1: Install uv (Package Manager)

uv is a fast Python package manager that handles everything automatically.

### Windows
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### macOS/Linux
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Verify Installation
```bash
uv --version
```

## Step 2: Configure Claude Desktop

### Find Your Config File

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Linux:**
```
~/.config/claude/claude_desktop_config.json
```

### Add Configuration

Open the config file and add this configuration:

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", 
        "--with", 
        "tree-sitter-analyzer[mcp]",
        "python", 
        "-m", 
        "tree_sitter_analyzer.mcp.server"
      ]
    }
  }
}
```

## Step 3: Restart Claude Desktop

Close and restart Claude Desktop completely.

## Step 4: Test the Setup

In Claude Desktop, try asking:

### Basic Usage Examples

**Check code scale:**
> "What's the overall complexity and size of examples/Sample.java?"

**Analyze code structure:**
> "Please analyze the structure of examples/Sample.java and show me a detailed table"

**Extract specific code:**
> "Show me lines 84-86 from examples/Sample.java"

**Universal analysis:**
> "Analyze this code file with automatic language detection"

You should see the tree-sitter-analyzer tools being used automatically.

## Available Tools

Once configured, you'll have access to these tools:

1. **analyze_code_scale** - Get code metrics and complexity
   ```json
   {
     "tool": "analyze_code_scale",
     "arguments": {
       "file_path": "examples/Sample.java",
       "include_complexity": true,
       "include_details": true
     }
   }
   ```

2. **analyze_code_structure** - Generate detailed structure tables
   ```json
   {
     "tool": "analyze_code_structure",
     "arguments": {
       "file_path": "examples/Sample.java",
       "format_type": "full"
     }
   }
   ```

3. **read_code_partial** - Extract specific line ranges
   ```json
   {
     "tool": "read_code_partial",
     "arguments": {
       "file_path": "examples/Sample.java",
       "start_line": 84,
       "end_line": 86
     }
   }
   ```

4. **analyze_code_universal** - Universal analysis with auto-detection
   ```json
   {
     "tool": "analyze_code_universal",
     "arguments": {
       "file_path": "examples/Sample.py",
       "analysis_type": "comprehensive"
     }
   }
   ```

## Troubleshooting

### Tool Not Available
- Restart Claude Desktop completely
- Check config file syntax with a JSON validator
- Verify uv is installed: `uv --version`

### Permission Issues
- On Windows: Run as administrator
- On macOS/Linux: Check file permissions

### Still Having Issues?
- Check Claude Desktop logs
- Test manual installation: `uv run --with "tree-sitter-analyzer[mcp]" python -c "import tree_sitter_analyzer; print('OK')"`

## Need Help?

- [GitHub Issues](https://github.com/aimasteracc/tree-sitter-analyzer/issues)
- [Developer Setup Guide](MCP_SETUP_DEVELOPERS.md) - For local development

