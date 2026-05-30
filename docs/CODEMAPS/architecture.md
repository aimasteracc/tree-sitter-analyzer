<!-- Generated: 2026-05-22 -->
# Architecture Codemap

High-level topology of the `tree-sitter-analyzer` Python package.

## Subsystem Layout

```
tree_sitter_analyzer/
├── cli/              ← CLI entry points + commands           (cli.md)
├── mcp/              ← MCP server + 23 tools                 (mcp-tools.md)
│   ├── server.py     ← stdio transport, tool registration
│   ├── tools/        ← 23 tool classes
│   ├── server_utils/ ← registration / smart_prompts / intent
│   ├── utils/        ← project_index, search_cache, file_output_factory
│   └── resources/    ← MCP resources (read-only data exposed to AI)
├── languages/        ← 17 tree-sitter plugins                (languages.md)
├── formatters/       ← TOON / JSON / table / CSV / YAML      (formatters.md)
├── core/             ← Parser, engine, AnalysisSession, AnalysisRequest
├── plugins/          ← LanguagePlugin / ElementExtractor base + registry
├── queries/          ← Per-language tree-sitter query files
├── security/         ← Boundary manager, path validator      (security.md)
├── grammar_coverage/ ← Coverage validator + auto-discovery
├── platform_compat/  ← Cross-platform recorder + compare
├── services/         ← Cache service + boundary-aware file IO
└── utils/            ← log, tree-sitter compat, encoding
```

## Data Flow (one analysis request)

```
User → CLI flag / MCP tool call
  ↓
core/request.AnalysisRequest        ← validate input, resolve project root
  ↓
plugins/manager.PluginManager       ← pick LanguagePlugin by extension
  ↓
languages/<lang>_plugin.analyze_file ← tree-sitter parse + extract elements
  ↓
models.AnalysisResult               ← Class/Function/Variable/Import/Annotation
  ↓
formatters/<fmt>_formatter          ← TOON (default for MCP) / JSON / table
  ↓
agent_summary envelope              ← verdict (SAFE/REVIEW/CAUTION/UNSAFE)
  ↓
stdout / stderr / file_output_factory
```

## Cross-Cutting Concerns

### Security boundary
Every path is validated against `TREE_SITTER_PROJECT_ROOT` by `security/validator.py`.
**No tool ever reads outside the project root.** `BoundaryManager` is the single source of truth.

### Token optimization
- **TOON** is the default MCP output format — ~73% smaller than JSON.
- AST results are stored in **SQLite** via `ast_cache.py` (content-hash keyed).
- `incremental_sync.py` reindexes only changed files (mtime + SHA-256).

### Caching layers
1. `ast_cache.py` — persistent SQLite store of parsed AST symbols/imports/structure
2. `_route_cache.py` — SQLite store of detected routes (Flask/Django/Express/Spring)
3. `core/cache_service.py` — in-process LRU for formatter outputs
4. `mcp/utils/search_cache.py` — fd/ripgrep result cache

### MCP / CLI parity
Every MCP tool has a CLI equivalent — enforced by `tests/unit/test_agent_contracts.py`
and `tests/unit/cli/test_mcp_commands.py`. **Adding an MCP tool without a CLI flag is a
contract violation.**

## Entry Points

| Surface | Module | Notes |
|---|---|---|
| `tree-sitter-analyzer` CLI | `cli_main.py` → `cli/` | Human-facing, JSON default |
| `tree-sitter-analyzer-mcp` MCP stdio server | `mcp/server.py` | AI-agent-facing, TOON default |
| `find-and-grep` | `cli/commands/find_and_grep_cli.py` | fd + ripgrep wrapper |
| `tree-sitter-analyzer-cli` (Python API) | `api.py` | Embeddable |

## Critical Invariants (do NOT change without reading [`CLAUDE.md`](../../CLAUDE.md))

1. **MCP default `output_format` = `"toon"`** — locked. Flipping to JSON loses 50-70% token savings.
2. **CLI default `output_format` = `"json"`** — locked. Humans pipe into `jq`.
3. **`project_root` is resolved via `os.path.abspath`** — NOT `os.path.realpath` (macOS symlink trap).
4. **CLI diagnostic output → stderr; payload → stdout** — never mix.
5. **markdown files** are NOT scored by `project_health` — use `markdown_health` for that.

See [`CLAUDE.md` § "Deliberate design decisions"](../../CLAUDE.md) for the rationale and past
rollback incidents.
