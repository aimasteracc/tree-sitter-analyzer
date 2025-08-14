## tree-sitter-analyzer v0.9.2 (2025-08-14)

### Highlights
- MCP module version aligned with core `__version__` (consistency across adapters)
- English-only tool descriptions, messages, and code comments; README_zh/README_ja synced 1:1 with English README
- Security validator hardened for absolute paths; allows temp-dir paths in test environments
- Initialization errors normalized to `MCPError` for protocol compliance
- 1358/1358 tests passing; coverage 74.82%

### MCP Workflow (3-step)
- `check_code_scale`: File scale and complexity metrics
- `analyze_code_structure`: Full structure table with line positions
- `extract_code_section`: Extract code by line range

### Recommended MCP Configuration (Claude Desktop)
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ],
      "env": {"TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}"}
    }
  }
}
```

### Security
- Absolute path policy tightened; project-root boundary strictly enforced
- Temp directory whitelisted for tests to avoid false negatives

### Upgrade Notes
- No breaking API changes
- MCP tool names are stable (`check_code_scale`, `analyze_code_structure`, `extract_code_section`)
- Ensure IDE config points to the new entrypoint if switching from legacy setups

### Thanks
Thanks to contributors for quality improvements and i18n synchronization.


