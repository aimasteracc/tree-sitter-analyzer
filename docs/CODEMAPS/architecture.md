<!-- Generated: 2026-05-22; doc-code re-sync: 2026-06-17 -->
# Architecture Codemap

High-level topology of the `tree-sitter-analyzer` Python package.

## Subsystem Layout

```
tree_sitter_analyzer/
├── cli/              ← CLI entry points + commands           (cli.md)
├── mcp/              ← MCP server + 8 facade tools             (mcp-tools.md)
│   ├── server.py     ← stdio transport, tool registration
│   ├── tools/        ← ~74 inner tool classes (delegated from facades)
│   ├── server_utils/ ← registration / smart_prompts / intent
│   ├── utils/        ← project_index, search_cache, file_output_factory
│   └── resources/    ← MCP resources (read-only data exposed to AI)
├── languages/        ← 21 tree-sitter plugins                (languages.md)
├── formatters/       ← TOON / JSON / table / CSV / YAML      (formatters.md)
├── core/             ← Parser, engine, AnalysisSession, AnalysisRequest
├── models/           ← AnalysisResult + Class/Function/Variable/Import models
├── plugins/          ← LanguagePlugin / ElementExtractor base + registry
├── queries/          ← Per-language tree-sitter query files
├── import_extractors/← Per-language import extraction (_python/_java/…)
├── synapse_resolver/ ← Cross-file callee binder (primary call-edge resolution)
├── graph/            ← edge_store.py — single-edge-table call-graph store (B1)
├── constraints/      ← architectural-constraints.yml evaluator/parser/schema
├── hyphae/           ← Hyphae selector DSL (lexer/parser/ast/evaluator) — RFC-0001 reactive push
├── skills/           ← 13 bundled tsa-* agent skills
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
**No tool ever reads outside the project root.** `ProjectBoundaryManager` is the single source of truth.

### Token optimization
- **TOON** is the default MCP output format — 50-70% fewer tokens than JSON (see `CLAUDE.md` §1).
- AST results are stored in **SQLite** via `ast_cache.py` (content-hash keyed).
- `incremental_sync.py` reindexes only changed files (mtime + SHA-256).
- `indexing_snapshot.py` freezes one ordered project scope for both full-index
  phases and detects selected files that mutate while the operation is running.

### Caching layers
1. `ast_cache.py` — persistent SQLite store of parsed AST symbols/imports/structure
2. `_route_cache.py` — SQLite store of detected routes (Flask/Django/Express/Spring)
3. `core/cache_service.py` — in-process LRU for formatter outputs
4. `mcp/utils/search_cache.py` — fd/ripgrep result cache
5. `registry/health_score_cache.py` — persistent per-file health scores keyed by
   source fingerprint plus coverage, weights, moving-window, repository-specific
   git metadata, and scoring-version context

### MCP / CLI parity
Every MCP tool has a CLI equivalent — enforced by `tests/contracts/test_mcp_cli_parity_contract.py`
and `tests/unit/cli/test_mcp_commands.py`. **Adding an MCP tool without a CLI flag is a
contract violation.**

## Entry Points

| Surface | Module | Notes |
|---|---|---|
| `tree-sitter-analyzer` CLI | `cli_main.py` → `cli/` | Human-facing, JSON default |
| `tree-sitter-analyzer-mcp` MCP stdio server | `mcp/server.py` | AI-agent-facing, TOON default |
| `miswire-audit` | `miswire_audit.py` | Run-on-your-repo cross-language correctness demo |
| `list-files` / `search-content` / `find-and-grep` | `cli/commands/*_cli.py` | fd / ripgrep / fd+rg standalone utilities |
| Python API (no console script) | `api.py` | Embeddable library entry |

## Benchmark qualification support

`benchmarks/codegraph_compare/setup_qualification.py` is a compatibility facade for
the NO1-008A E0 evidence boundary. Responsibilities are split into focused modules:

- `setup_qualification_plan.py` — immutable plan models and constants
- `setup_qualification_inventory.py` — Git-backed source inventory
- `setup_qualification_paths.py` — canonical openat filesystem isolation and quiescent snapshot hashing
- `setup_qualification_schema.py` — strict recursive receipt JSON schema
- `setup_qualification_trust.py` — externally supplied Ed25519 verifier trust roots
- `setup_qualification_validation.py` — filesystem, evidence-core, and signature checks
- `setup_qualification_orchestration.py` — non-executing E0 orchestration

## Critical Invariants (do NOT change without reading [`CLAUDE.md`](../../CLAUDE.md))

1. **MCP default `output_format` = `"toon"`** — locked. Flipping to JSON loses 50-70% token savings.
2. **CLI default `output_format` = `"json"`** — locked. Humans pipe into `jq`.
3. **`project_root` resolution must NOT be naively re-canonicalised in `BaseMCPTool.__init__`** — `SecurityValidator`, `PathResolver`, and the test fixtures already agree on a `Path.resolve()` (realpath) resolution; the macOS `/var → /private/var` symlink means a mismatched re-canonicalisation diverges. r36's attempt broke 164 tests on macOS (rolled back).
4. **CLI diagnostic output → stderr; payload → stdout** — never mix.
5. **markdown files** are NOT scored by `project_health` — use `markdown_health` for that.

See [`CLAUDE.md` § "Deliberate design decisions"](../../CLAUDE.md) for the rationale and past
rollback incidents.

## Offline-qualified production canary boundary

`benchmarks/codegraph_compare/production_dispatch.py` is a one-shot, single-cell
gateway; `production_dispatch_validation.py` holds its fail-closed envelope,
ledger-inode, provider, and transport validation helpers. The gateway plus an external supervised-transport authority receipt proving exact-one,
frozen-timeout, and whole-process termination. Unrestricted provider callables and caller-supplied
runners are never executed. A production PASS requires independently pinned
Ed25519 external facts: a fresh nonce/spec claim bound to the dispatch challenge,
a manifest-level cumulative-budget/order reservation, provider-budget reservation
and exact-one usage, supervised process termination, and an immutable-evidence terminal receipt bound to the local evidence digest, provider
usage receipt, and claim ID. Production code keeps public verification keys only;
it provides no authority private keys or receipt issuers. Missing transport or
authority inputs/public-key pins returns `NOT_EVALUATED` before transport with
zero callbacks; invalid or unavailable terminal authority cannot produce PASS.

`benchmarks/codegraph_compare/production_collector.py` creates only a local E0
diagnostic bundle. Its receipt is always `durable=false`; POSIX dirfd collection
is `local-dirfd-diagnostic-only`, and Windows/no-dirfd durability is
`unsupported` without simulated read-only/WORM guarantees. Local journal,
ledger, pathname, inode, and evidence state do not authorize a claim or terminal
result. The dispatcher passes only the local ledger digest to the external
evidence authority. This boundary imports no provider implementation and does
not open `CanaryProtocol` production mode; NO1-003C remains human-authorized.
