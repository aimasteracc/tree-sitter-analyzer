# Tree-sitter Analyzer -- Architecture

## Layered Architecture

```
+===================================================================+
|  Interfaces                                                       |
|  CLI (argparse)  |  MCP Server (stdio/HTTP)  |  Python SDK       |
+==================+===========================+====================+
         |                    |                      |
         v                    v                      v
+===================================================================+
|  MCP Tool Layer (26 tools + 2 discovery meta-tools)                    |
|  understand_codebase | analyze_code_structure | java_patterns | code_diff | code_smell_detector | code_clone_detection |
|  error_recovery | health_score | semantic_impact | quick_risk_assessment |
|  get_code_outline | query_code | read_partial | list_files |
|  search_content | find_and_grep | check_code_scale | get_project_summary |
|  modification_guard | trace_impact | dependency_query | build_project_index |
|  batch_search | check_tools | ci_report | tools/list | tools/describe      |
|  ------- security boundary: BaseMCPTool -> SecurityValidator -----|
+===================================================================+
         |
         v
+===================================================================+
|  Tool Registry (singleton)                                        |
|  ToolEntry (metadata) | ToolRegistry (registration/discovery)     |
|  6 toolsets: analysis 🔍 | query 🔎 | navigation 🧭               |
|             safety 🛡️ | diagnostic 🩺 | index 📚                  |
+===================================================================+
         |
         v
+===================================================================+
|  Core Engine                                                      |
|  UnifiedAnalysisEngine (singleton per project root)               |
|    |- AnalysisRequest (dataclass, from_mcp_arguments)             |
|    |- QueryService (tree-sitter query execution + filtering)      |
|    |- Parser (tree-sitter grammar loading + AST construction)     |
|    |- ASTChunker (semantic chunking: OOP / script / function)     |
|    |- CacheService (3-tier: L1 fast / L2 medium / L3 long-term)  |
|    |- PerformanceMonitor (operation timing)                       |
|    |- AnalysisSession (audit recording + SHA256 file integrity)   |
+===================================================================+
         |
         v
+===================================================================+
|  Language Plugins (17 languages, extensible)                      |
|  PluginManager -> auto-discover from entry points + local files   |
|  ElementExtractor (ABC) -> extract classes, methods, fields, etc. |
|  LanguagePlugin (Protocol) -> analyze_file(request)               |
+===================================================================+
         |
         v
+===================================================================+
|  Queries (Python modules per language)                            |
|  Predefined tree-sitter queries: methods, classes, functions,     |
|  imports, interfaces, structs, traits, etc.                       |
+===================================================================+
         |
         v
+===================================================================+
|  Tree-sitter Parsers (grammar WASM / shared lib)                  |
+===================================================================+
```

## Data Flow

```
Source File
    |
    v
+--------------------+
| Encoding Detection |----> safe_decode / chardet / iterative fallback
+--------------------+
    |
    v
+--------------------+
| Tree-sitter Parse  |----> AST (language-specific grammar)
+--------------------+
    |
    v
+----------------------+
| Plugin Extraction    |----> List[CodeElement]
+----------------------+
    |
    v
+----------------------+
| Query Execution      |----> filtered/specific elements
+----------------------+
    |
    v
+----------------------+
| AnalysisResult       |----> metrics + elements + errors (immutable)
+----------------------+
    |
    v
+----------------------+
| Formatter Registry   |----> compact | full | TOON | markdown | csv | json
+----------------------+       (TOON: 54-56% token reduction for LLM context)
    |
    v
Output (CLI stdout / MCP JSON-RPC / SDK return)
```

## Key Directories

| Path | Responsibility |
|------|---------------|
| `core/` | Analysis engine, parser, query service, AST chunker, cache, session |
| `languages/` | 17+ language plugins for element extraction |
| `queries/` | Predefined tree-sitter queries per language |
| `formatters/` | Output formatters + TOON encoder (Registry pattern) |
| `mcp/` | MCP server, 26 tools + 2 discovery meta-tools, SDK, intent aliases, streamable HTTP, tool registry |
| `analysis/` | Dependency graph, health score (A-F grading), error recovery |
| `security/` | Boundary manager, input validator, ReDoS regex checker |
| `cli/` | Argument parsing, validation, info commands |
| `plugins/` | Plugin base classes (ElementExtractor ABC, LanguagePlugin Protocol) |
| `encoding_utils.py` | Encoding detection, safe decode/encode, file I/O with fallback |

## Key Design Decisions

### 1. Immutable Data with Frozen Dataclasses

`AnalysisResult`, `DependencyGraph`, `FileHealthScore`, and `CacheEntry` use
`frozen=True`. Prevents hidden side effects and enables safe concurrent access.

### 2. Iterative Encoding (Not Recursive)

The TOON encoder uses an explicit stack rather than recursion. Eliminates stack
overflow risk on deeply nested AST output.

### 3. Singleton Engine per Project Root

`EngineManager` maintains one `UnifiedAnalysisEngine` per project root, sharing
parser, cache, and plugin manager across all MCP tool invocations.

### 4. 3-Tier Cache (L1 / L2 / L3)

`CacheService` implements hierarchical caching with content-hash-based
invalidation. Unchanged files skip re-analysis entirely.

### 5. Graceful Error Recovery

`error_recovery.py` provides regex-based fallback when tree-sitter parsing
fails. Returns partial results rather than failing completely.

### 6. Security at the Boundary

Every MCP tool inherits `BaseMCPTool` which enforces path normalization,
boundary checks, null-byte injection detection, and ReDoS prevention.

### 7. Tool Registry Pattern

`ToolRegistry` is a singleton that manages all MCP tools with metadata:
- `ToolEntry` stores tool metadata (name, toolset, category, schema, handler, availability)
- 6 toolsets organize tools by functionality (analysis, query, navigation, safety, diagnostic, index)
- `tools/list` and `tools/describe` enable runtime tool discovery
- Dynamic availability checking via optional `check_fn` callbacks

### 8. Plugin Discovery via Entry Points

Adding a new language requires one plugin file + one query module, with no
changes to the core engine.

## Extension Points

| Extension | Steps |
|-----------|-------|
| New language | Create `languages/x_plugin.py`, add queries in `queries/x.py` |
| New MCP tool | Create `mcp/tools/x_tool.py` extending `BaseMCPTool`, register in server |
| New output format | Create `formatters/x_formatter.py`, register with `FormatterRegistry` |
| New analysis pass | Add module in `analysis/`, call from engine or MCP tool |
