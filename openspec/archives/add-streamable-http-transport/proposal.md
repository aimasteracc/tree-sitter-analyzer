# Add StreamableHTTP Transport for MCP Server

## Overview

Add StreamableHTTP transport as an alternative to stdio for the MCP server. This enables:
- HTTP-based access from any language/runtime (not just Node.js subprocesses)
- Browser-based MCP clients
- SDK embedding into existing Python web servers (Starlette/FastAPI)

## Motivation

Current server only supports stdio transport (`mcp.server.stdio`). While sufficient for Claude Desktop and Claude Code, it limits:
- Integration with web-based AI tools
- Multi-client access (only one client at a time via stdio)
- SDK embedding into existing Python applications

## Design

### Transport Selection

Add `--transport` CLI flag:
- `--transport stdio` (default, backward compatible)
- `--transport streamable-http` (new, HTTP/SSE-based)

### StreamableHTTP Implementation

Use `mcp.server.streamable_http_manager.StreamableHTTPSessionManager` from the MCP SDK (v1.17.0+). Create a Starlette ASGI app that routes MCP requests to the session manager.

```
tree_sitter_analyzer/mcp/streamable_http_server.py
  - StreamableHTTPServer class
  - ASGI app factory
  - CLI entry point: tree-sitter-analyzer-mcp-http
```

### Configuration

| Flag | Default | Description |
|------|---------|-------------|
| `--transport` | `stdio` | Transport type (stdio / streamable-http) |
| `--host` | `127.0.0.1` | HTTP listen address |
| `--port` | `8080` | HTTP listen port |
| `--stateless` | `false` | Run in stateless mode (no session tracking) |

### Backward Compatibility

- Default transport remains stdio — zero breaking changes
- All existing MCP tool definitions unchanged
- Same `TreeSitterAnalyzerMCPServer` class used for both transports

## Success Criteria

1. `tree-sitter-analyzer-mcp-http` starts an HTTP server on port 8080
2. MCP clients can connect via StreamableHTTP protocol
3. All 15 MCP tools accessible via HTTP
4. `--transport stdio` still works exactly as before
5. TDD: 5+ unit tests for transport selection and HTTP server
