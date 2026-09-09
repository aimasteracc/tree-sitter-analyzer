<!-- Generated: 2026-05-22; doc-code re-sync: 2026-08-19 -->
# Architecture Codemap

High-level topology of the `tree-sitter-analyzer` Python package.

## Subsystem Layout

```
tree_sitter_analyzer/
├── cli/              ← CLI entry points + commands           (cli.md)
├── mcp/              ← MCP server + 8 facade tools             (mcp-tools.md)
│   ├── server.py     ← stdio transport, tool registration
│   ├── tools/        ← 146 modules / 79 inner tool classes (delegated from facades)
│   ├── server_utils/ ← registration / smart_prompts / intent
│   ├── utils/        ← project_index, search_cache, file_output_factory
│   └── resources/    ← MCP resources (read-only data exposed to AI)
├── languages/        ← 22 tree-sitter plugins                (languages.md)
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
├── verification_plan.py ← 有界描述符、完整 argv 计划与阶段摘要
├── verification_runner.py ← 重新分析校验、顺序执行、日志预算与进程回收
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

### Response format
- **JSON** is the only MCP and CLI response format. There is no alternate compact wire encoding.
- AST results are stored in **SQLite** via `ast_cache.py` (content-hash keyed).
- `incremental_sync.py` reindexes only changed files (mtime + SHA-256).
- `indexing_snapshot.py` freezes one ordered project scope for both full-index
  phases and detects selected files that mutate while the operation is running.

监听链路由 `file_watcher.py` 调度，`file_watcher_polling.py` 保存可续跑的扫描游标，
比较原始内容摘要和文件元数据。片尾耗尽预算的指纹读取在新切片重试一次；
重试仍失败则继续后续文件，保留旧指纹。异常路径只影响其自身；删除在遍历完成后确认。
POSIX 枚举通过固定父目录描述符和 no-follow 打开，并核对目录身份；Windows
仅在建立搜索句柄时短暂固定祖先目录，随后释放禁止重命名的句柄。
普通源码被替换成特殊文件或超过读取上限时触发失效，只有明确永久拒绝的候选
才清除旧索引行；临时读取或时限故障保留记录，并撤销完整认证。
轮询完整基线建立后、原生观察器启用后，均异步请求一次索引对齐，以覆盖启动窗口；
启动请求与后续文件通知共用防抖同步队列，不计作文件事件。
默认 full-index、sync 和 watcher 在 `.ast-cache/index-generations/generations/<id>/index.db`
构建私有副本；`cache/generation_store.py` 在独立 SQLite 发布租约内核对父版本和源码，
通过原子替换 `active.json` 发布。旧进程写入 `.ast-cache/index.db` 不影响新版本。
`cache/generation_routing.py` 统一默认读路径；已发布 ASTCache 使用只读连接，显式修改
也经私有副本发布。`cache/generation_reads.py` 在 MCP 调用内固定版本，下次调用刷新缓存读路径；
旧读会话继续可用，约束持久化也发布私有副本；当前不自动回收版本。
同进程 watcher 从候选捕获到提交使用逻辑数据库共享锁；跨进程并发发布通过父身份
比较拒绝过期候选。完成激活标记阻止选择器或版本目录丢失后退回旧库；首次激活中断仅允许
持有发布租约的写者重试，普通读者仍拒绝缺失选择器。
POSIX 发布包含文件与目录同步；Windows 目录掉电持久性仍不作保证。
停止时在统一超时预算内等待监听和计时器线程；未退出的后台线程仍计入运行状态，
并阻止启动替代线程，停止请求后的新防抖请求不再启动。
候选捕获、发现或冻结失败，以及逐文件、回填、清单认证错误和同步异常，
会在后台指数退避重试，间隔最高 60 秒；
永久类型或字节上限拒绝不触发重试，已排队的文件通知不会被重试推迟。
这些观察只用于触发同步，不能替代 `index_source_snapshot.py` 的完整范围认证。

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
| `tree-sitter-analyzer-mcp` MCP stdio server | `mcp/server.py` | AI-agent-facing, JSON output |
| `miswire-audit` | `miswire_audit.py` | Run-on-your-repo cross-language correctness demo |
| `list-files` / `search-content` / `find-and-grep` | `cli/commands/*_cli.py` | fd / ripgrep / fd+rg standalone utilities |
| Python API (no console script) | `api/__init__.py` | Authoritative implementation of the existing `tree_sitter_analyzer.api` API; Pulse/serialization/semantic live in explicit submodules |

The former sibling `api.py` has been removed. Existing Python imports and public
function signatures remain unchanged; consumers must not load the removed file
by pathname. API regression routing watches `tree_sitter_analyzer/api/**`.

Pulse 的模块边界：`api/pulse.py` 保留公开名字、快照事务、查询和预算实现；
`api/_pulse_models.py` 仅定义共用冻结 DTO，`api/_pulse_sql.py` 仅保存固定 SQL。
`api/serialization.py` 直接依赖 DTO，不反向依赖查询入口；两个私有叶子模块均不导入
`pulse.py`。单请求内的读取绑定同一快照，不表示只执行一次 SQL。

### 缓存版本收敛

`cache/schema_extensions.py` 是扩展迁移及当前版本常量的唯一实现；
`cache/schema.py` 注册结构要求，`_ast_cache_database_mixin.py` 按顺序调用，
`index_snapshot_schema.py` 共用当前版本并验证所有消费列。

| 版本 | 定义 |
|---|---|
| 13 | 历史 manifest 迁移，编号固定不随 reader 版本变化 |
| 14 | canonical `ast_index.certified_at` |
| 15 | canonical `ast_symbol_activation.activation_state` |
| 16 | Pulse 注释、提交消息及旧实验 15 的 canonical 缺列修复 |
| 17 | LSP 缓存；保留旧实验已有的解析行 |

从 v13、canonical v15 或实验 Pulse v15 升级时，扩展迁移共用保存点；
DDL、数据修复和版本凭证一起提交或回滚。未知未来 v18 不写入即拒绝。
消息或 activation_state 为 NULL 的非 disabled 行一次性置 pending，原统计和消息
保留到刷新完成；重复初始化不重置已完成状态。
lazy flush 保留 DB 失败的 pending 重试资格，提交消息沿用有界 SHA 批次与负缓存；
消息失败不发布 computed。Pulse 不将 pending/disabled 显示为有效热度，时序谓词对
尚有 pending/disabled 的索引保守报 unknown/error，不宣称完整零匹配。
每个启用 activation 的项目索引周期都独立执行有界 flush，包括图 marker 有效的
全缓存周期；禁用周期不消费队列。变更影响的热区读取仅采信 computed 状态，缺失或
未计算证据通过 activation_diagnostic 保留在完整及精简响应中。

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
- `setup_qualification_executor.py` — keyless, single-attempt producer entrypoint
- `receipt_v3.py` — strict detached receipt body and domain-separated dual signatures
- `receipt_v3_signer.py` — stdout-only isolated executor/approver signer CLIs
- `verifier.py` — fresh public-key-only per-cell dm-verity/image/core recomputation
- `verifier_aggregate.py` — mandatory-public-config exact-14 manifest authority and CLI
- `Dockerfile.no1-008a` — digest-base multi-target producer/signer/verifier images
- `scripts/no1_008a_operator.sh` — Linux root/dm-verity isolated four-role operator

Receipt v2 remains fail-closed and cannot be upgraded through the E0 orchestrator.
Receipt v3 is detached from the dm-verity core snapshot. Even a 14/14 v3 verdict
is only `SETUP_QUALIFIED`: every benchmark claim stays E0, non-publishable, and
has no winner or dominance/unlock authority.

## Critical Invariants (do NOT change without reading [`CLAUDE.md`](../../CLAUDE.md))

1. **MCP and CLI `output_format` = `"json"`** — locked. One response contract serves agents, humans, and `jq`.
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
