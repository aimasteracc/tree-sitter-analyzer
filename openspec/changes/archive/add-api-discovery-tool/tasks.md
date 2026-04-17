# API Discovery Tool

## Goal

Comprehensive API endpoint inventory for understanding API surface area across multiple frameworks.

## Inspiration

From tree-sitter-analyzer docs: query patterns exist for `flask_route`, `fastapi_endpoint`, `django_model` but no dedicated tool for API discovery.

## MVP Scope

1. **Framework Detection**: Flask, FastAPI, Django (Python), Express (JavaScript/TypeScript), Spring Boot (Java)
2. **Endpoint Extraction**: Route path, HTTP method, handler function, file location, line number
3. **Organization**: Group by framework, file, route prefix
4. **Metrics**: Total endpoints, by framework, by HTTP method
5. **MCP Tool Integration**: `api_discovery` tool in analysis toolset

## Technical Approach

### Detection Algorithm

```
1. Scan files for framework-specific patterns:
   - Flask: @app.route, @bp.route, Blueprint()
   - FastAPI: @app.get, @app.post, @router.*, APIRouter()
   - Django: urlpatterns, @api_view, path(), re_path()
   - Express: app.get, app.post, router.*, express.Router
   - Spring: @GetMapping, @PostMapping, @RequestMapping

2. Extract endpoint metadata:
   - Route path (including parameters)
   - HTTP methods (GET, POST, PUT, DELETE, etc.)
   - Handler function name
   - File location and line number

3. Organize results:
   - Group by framework
   - Group by file/module
   - Sort by route prefix (common prefixes together)

4. Generate metrics:
   - Total endpoints per framework
   - HTTP method distribution
   - Route depth (nested levels)
```

### Module Structure

```
tree_sitter_analyzer/analysis/api_discovery.py
- FrameworkType: enum (FLASK, FASTAPI, DJANGO, EXPRESS, SPRING)
- ApiEndpoint: dataclass (framework, path, methods, handler, file, line)
- discover_endpoints(project_root): List[ApiEndpoint]
- detect_flask_routes(file_path): List[ApiEndpoint]
- detect_fastapi_endpoints(file_path): List[ApiEndpoint]
- ...

tree_sitter_analyzer/mcp/tools/api_discovery_tool.py
- ApiDiscoveryTool MCP tool
- schema: project_root, frameworks, include_metrics, output_format
- TOON and JSON output formats
```

### Dependencies

- Existing element extractors: For decorator/function extraction
- Language plugins: For framework-specific pattern matching
- TOON encoder: For compact output

## Implementation Plan

### Sprint 1: Core Detection Engine
- [x] Create `analysis/api_discovery.py` module
- [x] Implement `ApiEndpoint` dataclass
- [x] Implement Flask route detection (@app.route, @bp.route)
- [x] Implement FastAPI endpoint detection (@app.get, @app.post, @router)
- [x] Write unit tests (21 tests)

### Sprint 2: Multi-Framework Support
- [x] Django: urlpatterns + @api_view detection
- [x] Express: app.get/post/put/delete + router detection
- [x] Spring Boot: @GetMapping/@PostMapping detection
- [x] Add integration tests (5 tests)

### Sprint 3: MCP Tool Integration
- [x] Create `mcp/tools/api_discovery_tool.py`
- [x] Implement schema (project_root, frameworks, include_metrics, output_format)
- [x] Register to ToolRegistry (analysis toolset)
- [x] Add TOON format output with endpoint grouping
- [x] Write tool tests (25 tests)

## Success Criteria

- [x] 46 tests passing (21 + 5 + 25, exceeds 35+ target)
- [x] Detects endpoints in test projects with <10% false positive rate
- [x] ruff check passes, mypy --strict passes
- [x] Integrated into MCP toolset (32 tools total, 19 analysis tools)

## References

- tree-sitter-analyzer query patterns: flask_route, fastapi_endpoint
- CodeFlow: API surface analysis concept
- Flask/FastAPI/Django routing documentation

## Completed: 2026-04-17

Commit: e6cc303a

All 3 sprints complete, 46 tests passing, MCP tool registered and working.
