# OpenSpec Change: add-streamable-http-transport

## Summary
Add StreamableHTTP transport as an alternative to stdio for the MCP server.

## Tasks
- [x] T1: Create StreamableHTTP server module (streamable_http_server.py)
- [x] T2: Add --transport/--host/--port CLI args to server.py
- [x] T3: Write TDD tests for transport selection and ASGI app
- [x] T4: Verify backward compatibility (default stdio unchanged)

## Success Criteria
1. `tree-sitter-analyzer-mcp-http` starts an HTTP server on port 8080
2. MCP clients can connect via StreamableHTTP protocol
3. All 15 MCP tools accessible via HTTP
4. `--transport stdio` still works exactly as before
5. 7 unit tests passing
