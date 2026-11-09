# TSA 信任度 dogfood（2026-11-09）

> 为什么 agent 仍然先伸手拿 rg，以及要改什么才能反过来。
> 本文所有数字都带状态；未复现的观测已剔除，无法归因的已标为「不确定」。

## 最终状态（2026-11-10，随 PR #1939 收束）

本文件按时间记录，早期章节里的数字是**当轮**的测量值，不代表现状。现状如下：

| 项 | 现状 | 依据 |
|---|---|---|
| P0-1 坏 `--project-root` | 已修（fail-closed `INVALID_PROJECT_ROOT`） | §3 |
| P0-2 `--call-graph` 无索引 | 已修（0.53 s `INDEX_MISSING`） | §3 |
| P1-1 陈旧索引 | 已修（`WARN` + `SOURCE_INDEX_MISMATCH`） | §3 |
| P1-2 uql 假 `complete` | 已修（`SYMBOL_NOT_DEFINED` gap） | §3 |
| P1-3 `--callers` 行号 | 已修（`call_site_line`） | §3 / 第 9 轮 |
| **P1-4 change-impact 测试选择召回** | **未修（需设计：依赖图 + 文本引用通道）** | §4 |
| P2 系列（hotspot 档位 / index-meta / agent-summary-only / codemap parity） | 已修 | §3 |
| §11 no-op 索引成本 | 已修：9.08 s → **0.66–0.86 s**（记录生命周期，不动 #1253） | §11 第 26–29 轮 |
| §12 agent 原生原语（etag/304/delta/capabilities/absence/UQL hint） | 全部落地，CLI+MCP 双面 | §12 |
| RFC-0044 缺席证书 | 五种全部实现，status = implemented | `rfcs/0044-…` |

唯一遗留项 **P1-4** 已在第 42 轮补上第一通道的一半：`change-impact` 现在additionally 输出
`text_reference_tests`（「文本引用了改动模块、但依赖图没选中」的测试文件，附 `matched` 证据与
`text_reference_count`）。实测对 `tree_sitter_analyzer/cache/search.py`：依赖图选中 58 个测试，
文本通道另外指出 **11** 个文件，其中包括此前漏掉的 4 个直接引用者。

它**不**并入 `tests_to_run`——文本匹配不能当确定依赖，所以只作为 advisory 供 agent 取舍。

第 43 轮给这条通道加了**两级证据**（`confidence`）：

| 级别 | 含义 | 实测（`cache/search.py` 一行改动） |
|---|---|---|
| `import` | 文件里确实有 `import …cache.search` 或 `from …cache import search` | 13 个 |
| `mention` | 只在注释/字符串/其他文本里出现 | 3 个 |

排序上 import 级在前，`text_reference_note` 直接点出「13 of them import it directly: confidence=import」。
诚实边界：`import` 证明的是**导入**，不是「一定会执行到」，因此仍不进 `tests_to_run`；
把它升级为「可进 focused command 的召回」需要先量化误报率，仍是下一阶段的设计题。

**误报率实测（第 44 轮，4 个 import 级候选逐个单独运行并统计对 `cache/search.py` 的覆盖）**：

| 候选测试文件 | 单独运行时对 `cache/search.py` 的覆盖率 |
|---|---|
| `tests/unit/test_index_snapshot.py` | **80.98 %** |
| `tests/unit/test_ast_cache_cascade_search.py` | **96.74 %** |
| `tests/unit/test_ast_cache_symbols.py` | 11.96 % |
| `tests/unit/test_ast_cache_tool.py` | 11.96 % |

**4/4 都真实执行到被改动模块**，即这一层的「误报率」在当前样本上是 0——它们是依赖图真漏掉的覆盖，不是文本巧合。
因此升级门槛应为「够大的样本 + 明确上限」：我建议至少 20 个真实改动的抽样全为真阳性后，再把 import 级候选并入 `focused_test_command`（并对数量设上限），
在那之前保持 advisory —— 采样 4 个不足以支撑一个会改变 CI 选择面的默认行为。

**第 45 轮扩样（5 个不同模块）发现一个真实缺陷并已修**：通道把 `tests/` 下的**辅助模块**
（`_ast_cache_helpers.py`、`known_answer/_runner.py`）也算成了「测试文件」——pytest 对它们
直接 `rc=5`（0 收集）。现在只列 pytest 可收集的文件（`test_*.py` / `*_test.py`，排除
`conftest.py`）。过滤后抽样：

| 模块 | 首个 import 级候选 | 单独运行时对该模块覆盖率 |
|---|---|---|
| `cache/indexer.py` | `tests/unit/test_ast_cache_cache_directory.py` | **48.42 %** |
| `mcp/tools/callers_tool.py` | `tests/unit/test_aliased_import_callers_1670.py` | **53.24 %** |
| `uql/output.py` | `tests/contracts/test_agent_native_surface_contract.py` | 19.25 % |
| `capabilities.py` | 同上 | 40.32 % |
| `mcp/tools/callees_tool.py` | 同上 | 13.13 % |

7/7 可用样本全部真实执行到被改动模块（误报率 0）；此前那 2 个「不可运行」样本被过滤器消除。

**第 46 轮再扩 6 个模块**（累计 **12 个可用样本，误报率仍为 0**）：

| 模块 | 首个 import 级候选 | 覆盖率 |
|---|---|---|
| `uql/engine.py` | `tests/unit/uql/test_uql_engine.py` | **94.95 %** |
| `mcp/tools/text_search_tool.py` | `tests/unit/mcp/tools/test_text_search_tool.py` | **67.20 %** |
| `ast_cache.py` | `tests/unit/test_aliased_import_callers_1670.py` | **66.08 %** |
| `mcp/tools/nav_facade.py` | `tests/contracts/test_agent_native_surface_contract.py` | 19.06 % |
| `cli_main.py` | `tests/contracts/test_agent_docs_contract.py` | 15.64 % |
| `mcp/tools/change_impact_tool.py` | `tests/benchmarks/claims/test_safety_layers_smoke.py` | 不可单独运行 |

最后一行又是一类真实缺陷：`tests/benchmarks/` 下的基准脚本可被 pytest 收集，但单独运行需要数据集
（实测 `FileNotFoundError`）。已把 `tests/benchmarks/` 排除出补充列表，并加测试固定。

**累计 12/12 可用样本为真阳性**；离 20 的升级门槛还差 8 个，条件不变。

**第 47 轮补齐到 20 个样本（全部真阳性，误报率 0）**：

| 模块 | 候选 | 覆盖率 |
|---|---|---|
| `uql/coverage.py` | `tests/unit/uql/test_uql_coverage.py` | 84.11 % |
| `graph/read_interrupt.py` | `tests/integration/test_snapshot_tables_p3_lite.py` | 80.00 % |
| `cache/stable_failures.py` | `tests/unit/test_ast_cache_index_project.py` | 79.80 % |
| `mcp/tools/utils/change_impact_response.py` | `tests/unit/mcp/test_change_impact_tool_git_and_verification.py` | 45.63 % |
| `capabilities.py` | `tests/contracts/test_agent_native_surface_contract.py` | 40.32 % |
| `cache/query.py` | `tests/unit/test_fts_porter_stemming.py` | 29.12 % |
| `mcp/tools/symbol_search_tool.py` | `tests/unit/languages/test_typescript_extraction_fixes.py` | 10.90 % |
| `mcp/tools/utils/change_impact_text_refs.py` | 自己的测试 | 93.14 % |

**20/20 真阳性**，升级门槛达成。

**第 48 轮尝试升级时发现更重要的东西（因此没有升级）**：在 builder 层把 import 级候选并入
选择时，候选数为 **0**——因为用 `_build_test_plan(changed_files=[…search.py])` 这条路径，
依赖图**已经选中**了此前「漏掉」的 4 个文件：

```
tests/unit/test_index_snapshot.py            -> True
tests/unit/test_ast_cache_symbols.py         -> True
tests/unit/test_ast_cache_tool.py            -> True
tests/unit/test_ast_cache_cascade_search.py  -> True
```

也就是说：第 42 轮用 `--change-impact-mode diff`（git diff）测到的「漏 4 个」，
在「显式 scope/changed_files」路径上并不成立。**真正的缺陷可能是 diff 模式与 scope 模式的
选择范围不一致，而不是文本召回不足**。

因此本轮**回滚了 builder 层的并入改动**（它在此路径下不会触发，只会变成不可覆盖的死代码），
保留 advisory 通道作为安全网，并把下一步改成：**对比 diff 模式与 scope 模式的 `tests_to_run`，
定位差异来源**。这比给一个不成立的前提加默认行为更接近「可靠」。

## 0. 环境与方法

| 项 | 值 |
|---|---|
| 代码 | `develop @ 5f8017521`（`git fetch` 后由 `v1.32` 快进 365 个提交） |
| 版本 | TSA 3.1.1 |
| 机器 | macOS，10 核，本地 SSD |
| 语料 | 本仓库自身：2917 个可索引源文件，37.1 MB，82,350 个符号 |
| 索引 | cold build 35.1 s（lead 单跑）/ 36.7 s / 37.97 s（并发时），`.ast-cache` 402 MB |
| 方法 | 3 个独立探针（正确性 / 契约诚实性 / 可用性），各在自己的 worktree 冷启动；lead 对每条 P0/P1 独立复现后才写入本文 |

**一句话结论**：能力已经不缺（调用图、覆盖测试、proof-carrying completeness 都是 rg 做不到的）；
缺的是**信任契约**——答案的 tier 前置条件不可见、单次成本不可预测、有 6 处会在失败或过期时仍给
出「正常」信号、以及 371 个 flag / 90,979 字节 help 构成的发现成本。

## 1. grep 的信任为什么成立

1. **零前置**：无索引、无状态、无 daemon。任何 checkout 立刻可用。
2. **语义最小且精确**：「哪些行匹配」，不多说一个字，因此几乎不可能错。
3. **即时**：本仓库全量字面量扫描 0.05 s。一个任务里调 20 次也不觉得贵。
4. **确定性**：同一 tree、同一参数，输出逐字节相同。
5. **可编程**：exit 0=命中 / 1=无命中 / 2=错误；stdout 只有数据；stderr 只有诊断。
6. **零学习**：一个命令，不用读文档。

TSA 在第 2、4、5 条上已经做得不错，第 1、3、6 条是结构性短板，而第 2 条有 6 个破口。

## 2. 记分卡

| 维度 | 等级 | 证据 |
|---|---|---|
| 正确性（索引热且新） | A− | text-search 与 `rg -F` 在 9 组字面量上逐行一致（含 49,020 行量级）；能正确忽略字符串字面量里的 `class X:`（rg 会误报）；`import X as Y` 别名穿透比 rg/AST 更强 |
| 正确性（边界/截断） | D+ | `--symbol-search` 丢精确匹配（见 P0-3）；`--callers` 3/14 行号是定义行（P1-3）；change-impact 漏 4/8 直接引用测试（P1-4） |
| 诚实性（降级时） | C+ | 无索引时 `--callers` 的 WARN 是教科书级诚实；但坏 `--project-root`、过期索引、uql NOT_FOUND 三处仍撒谎（P0-1/P1-1/P1-2） |
| 确定性 | A | 4 个命令 2 次运行 sha256 完全一致（outline/callers/text-search/uql）；唯一路径依赖是输出里的绝对路径 |
| 成本可预测性 | C− | rg 0.05 s；TSA 单跳 0.2–1.6 s，但同一族命令可跳到 15 s / 47 s（P0-2/P1-7），冷索引 35 s |
| 可编程性 | B | stdout JSON 纯净 5/5、零 traceback 泄漏；但错误路径会把 90,979 字节 usage 打到 stdout（P2-1），`--hotspot` verdict 出字母表（P2-3） |
| 发现成本 | D | 371 个 flag、help 90,979 字节；找到正确答案平均 1.75 次尝试；读完必要文档约 30k tokens；`--text-search` 从未被表述为 rg 替代 |

## 3. 已验证的问题（P0–P2，全部含复现命令）

### P0-1 `--project-root` 不存在时谎报「没人调用」

```
$ tsa --project-root /no/such/dir/zzz --callers main --format json
exit=0  success=true  verdict=NOT_FOUND  caller_count=0  data_source="parse"
next_step: "Call-graph index is empty or has not been built yet. Build it with ..."
```

脚本会把「根目录打错」读成「这个符号没有调用方」。契约要求这种情况是 `ERROR`，不是 `NOT_FOUND`。
**判定：bug（非设计）。**

### P0-2 无索引时 `--call-graph` 静默全量解析 15.4 s；`--callers` 却正确拒绝

同一状态（移走 `.ast-cache`）、同一符号 `main`：

| 命令 | 结果 | 耗时 |
|---|---|---|
| `--callers main` | `WARN` + `INDEX_MISSING` + `MISSING_INDEX` + 精确 next_step | 0.25 s |
| `--call-graph callers --call-graph-function main` | `INFO`，401 callers，**无 error_code / 无 completeness / 无 data_source** | **15.36 s** |
| `--uql symbol('main').callers()` | exit 1，`ERROR` + `UQL_INDEX_UNAVAILABLE` | 0.28 s |
| `--hotspot` | exit 0，`CRITICAL`，无 `index_missing`/无 `completeness` | — |

（`--hotspot` 这一行由 lead 独立复现；顺带发现它会在只读查询中重建一个空 `.ast-cache`，见 P2-4。）

这正是 #1562 想消灭的「大仓库上无提示阻塞数分钟」——预算只装在了 `--callers` 一条路径上。
**判定：bug（与 #1562 的意图冲突，不是被批准的设计）。**

### P0-3 `--symbol-search` 会丢掉精确匹配的定义

```
$ tsa --symbol-search analyze --symbol-search-limit 5000 --format json
match_count=4917  truncated=true  exact=3
exact: api/__init__.py:267, core/_analysis_engine_analysis_mixin.py:15, project_graph.py:858
```

索引 DB 里 `SELECT ... WHERE name='analyze'` 有 **4** 行，第 4 行是
`tests/unit/mcp/test_query_symbol_search_scenarios.py:316 _Engine.analyze`。

根因：`cache/search.py:search_symbols_cascade` 把「测试文件降权」当**第一排序键**（#607），
精确的测试内定义被排到数千条 fts5 模糊命中之后，再被 `[:limit]` 切掉；`match_count` 报的是切后数量。
**判定：bug。** 注意 #607 的降权本身是设计，修复必须保留降权顺序（例如精确层先占名额，再按降权排序填充）。

### P1-1 索引过期时 verdict 仍是 `INFO`

```
$ printf '\ndef probe():\n    main()\n' >> tree_sitter_analyzer/cli_main.py   # 不重建索引
$ tsa --callers main --format json
verdict=INFO  caller_count=342（与改动前完全相同；源码新增了 1 个调用点）  error_code=null
source_evidence.freshness="stale"   # 只埋在嵌套字段
next_step: "Source changed since the index was built: ... This answer reflects the index, not the edit"
```

`docs/agent-envelope-contract.md` 明说 `WARN` 涵盖 "stale cache"。诚实信息存在，但只存在于散文
next_step 和嵌套 freshness 里；只读 `verdict`/`error_code` 的脚本完全看不见。
**判定：bug（违反自家信封契约）。**

### P1-2 `--uql` 对不存在的符号返回 `NOT_FOUND` + `completeness: complete`

```
$ tsa --uql "symbol('zzz_nonexistent').callers()" --format json
verdict=NOT_FOUND  completeness=complete  completeness_reasons=[]
stages=[{symbol,n=0,c=complete},{callers,n=0,c=complete}]  next_step=null
```

同一个问题走 `--callers zzz` 得到的是 `unknown` + `SYMBOL_NOT_DEFINED` + 修复建议。
两个入口对同一事实给出相反的「可收工」信号。
**判定：bug（跨入口语义不一致）。**

### P1-3 `--callers` 的行号有时是定义行而不是调用行

`tsa --callers search_symbols_cascade` 返回 14 条，其中 3 条的 `line` 就是被调方法的定义行：

```
_ast_cache_query_mixin.py:39   receiver=ASTCacheQueryMixin      confidence_tier=proven
symbol_search_tool.py:65       receiver=_SnapshotSearchCache    confidence_tier=proven
codegraph_context_tool.py:738  receiver=_Surface                confidence_tier=proven
```

调用真实发生在函数体内（如 39 行那是 `def`，调用在 46 行）。`confidence_tier=proven` 让这个偏差
看起来被证明过。**判定：输出契约的坐标语义与 agent 预期不一致（不是采集错误）。**

2026-11-09 复核（第 8 轮）：边数据本身是对的——`edges` 行里 `line=46` 是调用点、`caller_line=39`
是调用方定义行；`cache.query_callers()` 把调用点放在 `callee_line`、定义行放在 `caller_line`，
而 `_sql_native_callers` 用 `caller_line` 填 `line`。也就是说：**有调用点坐标，只是没有输出**。
同一份数据里模块级调用点（`<module>` 行）已经把 `line` 当作调用点，命名调用方却给定义行——这才是
「跳到行号看到 def」的原因。

**已实现（2026-11-09 第 9 轮）**：调用方条目新增 `call_site_line`，`line`/`end_line` 保持
「调用方函数定义范围」的现有语义。两条路径都补齐——SQL 路径直接取边的 `callee_line`；调用图路径
（本仓库因 optional grammar 不可认证时走这条）用一次 `query_callers` 把 (file, caller) 映射回调用点。
实测 `--callers search_symbols_cascade`：条目 `line=41`（定义行）同时给出 `call_site_line=48`（调用行）。
`docs/CODEMAPS/cli.md` 已注明两者区别；新增两条测试覆盖命名调用方与 `<module>` 调用点。

### P1-4 `--change-impact` 的测试选择漏掉 4/8 直接引用该模块的测试

对 `tree_sitter_analyzer/cache/search.py` 加一行注释后：

- 选中：44 个测试，`tests_to_run_count=44`，`risk=high`，`affected_count=923`
- 直接引用该模块符号的测试文件共 8 个，其中 **4 个未被选中**：
  `tests/unit/hyphae/test_evaluator.py`、`tests/unit/hyphae/test_select_tool.py`、
  `tests/unit/test_index_snapshot_capability.py`、`tests/unit/test_codegraph_context_tool.py`

即选中的不是「直接引用」的超集（同时混入了大量无关 ast_cache 测试）。
**判定：bug（召回缺口，直接冲击 VCSR 北极星）。** 注：本次改动是注释级，行为风险低；
但工具并不知道这一点，仍报 `risk=high`。

### P1-5 项目里只要有一个文件解析失败，`--symbol-resolve` / `--symbol-search` 就永远是 `WARN`

本仓库有 3 个 lua/swift fixture 因可选 grammar 未安装而 `error`，于是：

```
$ tsa --symbol-resolve SecurityValidator --format json
verdict=WARN  definition_count=1（正确答案）
source_evidence={freshness:"unknown", reason:"CALL_GRAPH_INCOMPLETE"}
```

同一个索引，`--callers` 却能给出 `verdict=INFO, completeness=complete`。
最小对照实验：只有 2 个 py 文件的小项目 → `INFO/fresh`；加一个 `.lua` 文件再索引 → 立刻
`WARN/freshness=unknown/CALL_GRAPH_INCOMPLETE`（答案本身不变）。

定义查询不需要调用边；用调用图认证门去卡它，会让「WARN = 降级」在绝大多数真实仓库里退化成噪声。
**判定：设计需要校准（signal calibration），不是纯 bug。**

### P1-6 `.tsa/index-meta.json` 是与真实缓存矛盾的第二个真相源

```
$ cat .tsa/index-meta.json   → {"files_indexed": 176, "languages": ["python"], ...}
$ tsa --ast-cache --ast-cache-mode stats → 2917 文件 / 82350 符号
```

**判定：bug（第二真相源）。**

### P1-7 `--uql` 多定义符号的 callees 成本跳两个数量级

```
$ tsa --uql "symbol('main').callees()" --format json   → 47.7 s / 52.1 s / 47.7 s
  stages: symbol n=176 (complete), callees n=434 (unknown)
$ tsa --uql "symbol('main').callers()"                  → 1.25 s / 1.59 s
```

`symbol('main')` 解析到 176 个同名定义，逐定义展开 callees。成本由符号的「同名定义数」决定，
agent 无法预算。**判定：bug（成本不可预测；需要 cap 或单定义默认语义）。**

### P2-1 错误路径把 90,979 字节 usage 打到 stdout（违反 CLAUDE.md §3）

```
$ tsa --trace-from x.py --format json   → exit 1, stderr 32B "ERROR: File path not specified."
                                          stdout 90,979B  ← 整份 usage
```

`cli_main.py:364` 的 `parser.print_help()` 未指定 `sys.stderr`。`--format json | jq` 直接炸；
不检查退出码的脚本会把 usage 当数据。`--partial-read-requests-json "{"` 同样触发。
**判定：bug（一条 `file=sys.stderr` 的修复）。**

### P2-2 `--text-search-limit 2000` 的错误 next_step 指错方向

```
ERROR / INVALID_ARGUMENT
next_step: "Narrow the root/globs or resolve the reported source error, then retry."
```

真实约束是 1..1000，输出里没有任何地方说明范围。**判定：bug（错误可诊断性）。**

### P2-3 `--hotspot` 的 `verdict=CRITICAL` 不在八值字母表内

`docs/agent-envelope-contract.md` 写明「字母表外即为 bug」。**判定：bug。**

### P2-4 只读查询会创建空 `.ast-cache`

删掉 `.ast-cache` 后跑 `--callers`：目录被重新创建（0 B），并以解析回退作答
（`data_source=parse`, `completeness=unknown`）。在 2917 文件的本仓库上跑 `--hotspot` 也复现了同样行为。
用「目录是否存在」判断索引健康的脚本会误判。**判定：bug（次要）。**

### P2-5 `--agent-summary-only` 对多数命令逐字节无效

```
--callers build_facade                     3038 → 3038
--class-hierarchy ... LanguagePlugin       7024 → 7024
--symbol-resolve SecurityValidator          546 → 546
```

help 里限定 "For --change-impact"，但 flag 出现在全局 help，agent 会以为省了上下文。
**判定：UX/文档（要么推广为全局信封瘦身，要么改名/作用域化）。**

### P2-6 MCP codemap 漏 11 个 action，而 parity gate 只比 tool 名

8 个 facade 共 94 个 action（含 8 个 `help`）；`docs/CODEMAPS/mcp-tools.md` 的行里漏：

- 8 个 `help`（8/8 未文档化，而这恰是唯一的自描述入口）
- `index action=knowledge`、`index action=schema`
- `viz action=knowledge`

`test_registered_mcp_tools_have_codemap_parity` 只比较 tool 名集合（8 = 8 通过），所以 action 漂移全绿。
**判定：bug（gate 盲区，同类教训见 `docs/AI_LESSONS.md` 的 "A gate must observe every route"）。**

## 4. 成本实测（状态齐全）

| 命令 | warm p50 | cold | 备注 |
|---|---|---|---|
| `--version` | 0.06 s | — | import 不是瓶颈（本体 1 ms，全 lazy） |
| `--help` | 0.13–0.15 s | — | 371 flag 的 argparse 构建 ~70 ms |
| `--outline`（97 行文件） | 0.17–0.23 s | 0.95 s | 无需索引 |
| `--text-search`（37 MB 全扫） | 1.05–1.35 s | 0.42 s | 原生引擎；`rg -F` 同语料 0.05–0.06 s |
| `--callers`（热索引） | 1.04–1.07 s | 0.25 s（拒答）/ 15.36 s（`--call-graph` 静默解析） | 首次调用后 3.34 s（一次性 warm-up） |
| `--symbol-resolve` | 0.58–0.61 s（首调 3.52 s） | 0.29 s 报 `index_not_ready` | 最慢的单跳是「找定义」 |
| `--uql symbol(X).callers()` | 1.25–1.90 s | — | — |
| `--uql symbol('main').callees()` | **47.7–52.1 s** | — | 176 个同名定义 |
| `--change-impact`（干净树） | 0.40 s | — | 一行改动时 5.8 s / 9.3 s |
| `--ast-cache --ast-cache-mode index` | 0.64 s（no-op） | **35.1–38.0 s** | 2917 文件 → 402 MB |
| 同上，在 365 个提交的 checkout 之后 | — | **49.4 s（mode=full, cached=0）** | 大 checkout 后没有增量复用 |

## 5. 已经很强、不要动的地方（信任资产）

- **text-search 与 rg 的一致性**：9 组字面量（含 `def `、`a.b`、`[[`、`\d`、中文、大小写）逐行完全一致；
  49,020 行的规模也精确相等；且尊重 ignore、不扫 `.ast-cache`。
- **AST 语义胜过 grep 的实例**：`tests/integration/_test_phase7_security_integration_helpers.py` 里
  的 `class SecurityValidator:` 位于 `r"""..."""` 字符串内，rg 会误报为定义，TSA 正确只报 1 个真实定义。
- **别名导入穿透**：`import X as _alias` 之后的调用点能被正确归属（rg/AST 朴素法会漏）。
- **诚实的失败**：无索引时 `WARN` + `INDEX_MISSING` + 真实 `source_file_count` + 可执行 next_step + 成本量级。
- **截断契约**：pre-cap total / listed / cap / 带真实数字的 next_step 四件套（callers、text-search 等）。
- **proof-carrying completeness**：13 道检查 + 原因码 + 证据字段（RFC-0040），这是超过 grep 的地方。
- **确定性**：4 个命令两次运行 sha256 相同。
- **文档-代码同步**：371 flag 与 codemap 精确相等；8 个 tool 精确相等（action 层除外，见 P2-6）。

## 6. 路线图：怎样才算「grep 级可信」

### 承诺 1 — 每条答案都声明自己的 tier

新增顶层字段：`tier: "instant" | "indexed"`、`index_state: "present|missing|stale|corrupt"`、`stale: bool`。
规则（应写成可执行不变量，而非散文）：
- `index_state != present` 时**永不**返回 `NOT_FOUND`；
- `stale=true` ⇒ `verdict=WARN`（顶层，不埋在 `source_evidence`）；
- `completeness=complete` 仅在「精确层未被截断」时成立。

### 承诺 2 — 把 instant tier 做成真正的 grep 替代

- 默认入口就是 `--text-search`（零索引 0.42 s），在 help 第一行写清它是字面量检索入口，
  并显式标注「不是 `--symbol-search`」；
- 加字节级预筛（`bytes.find` 过滤候选文件后再解码/计算行列），目标 1.2 s → ≤0.3 s；
- 保留并宣传它比 rg 强的地方：AST 感知（忽略字符串/注释里的伪定义）、ignore 语义、精确 file:line:col。

### 承诺 3 — 让 indexed tier 自暖且诚实

- `--setup` / 首次索引型查询时**后台有界**建索引（现有 `--setup` 已会 warm index，但没有自动触发路径）；
- 大 checkout 后支持真正的增量复用（当前 365 提交 = 49 s 全量）；
- 无索引时的四种表现（WARN/ERROR/静默解析/CRITICAL）统一成一个 `index_state` 契约。

### 承诺 4 — 成本预算，而不是「看情况」

目标（本仓库、warm、p50）：单跳 ≤250 ms，多跳 ≤1 s。为此：
- `--symbol-resolve` 的定义解析改走 SQL 方法表（实测 1 ms），不要为一跳查询 build 整张调用图（1.1 s）；
- `--uql` 的 `symbol()` 多定义默认取单个定义 + 显式 `all_definitions`，或给 callees 阶段加预算与 `truncated`；
- `--callers` 的 freshness 认证成本要能降级（快路径 1 s → 目标 250 ms）。

### 承诺 5 — 收口发现成本

- `--help` 顶部放 8 行「任务 → 唯一命令」索引表（找定义 / 谁调用 / 哪些测试 / 文本检索 / 结构 / 影响面 / 类层级 / 未覆盖）；
- 一个概念一个名字：`--symbol-resolve`（定义）、`--callers`（调用者）、`--text-search`（字面量）、`--test-map`（覆盖测试），其余同义 flag 标别名；
- 8 个 facade 的 `action=help` 进 codemap，并让 parity gate 比较 action 集合（当前只比 tool 名）。

## 7. 先做这 5 件（按性价比排序）

1. **堵住诚实的 6 个洞**：P0-1、P1-1、P1-2、P2-1、P2-3、P1-6。零架构风险，一周内可完成，直接决定「能不能信」。
2. **symbol-search 精确层不被截断**（P0-3）：精确命中先占名额，再按 #607 降权填充；响应加 `dropped_exact`。
3. **统一 `index_state` 契约**（P0-2）：四工具同状态同语义，删掉 `--call-graph` 的静默全量解析。
4. **成本**：symbol 解析 SQL 化（1.1 s → ms 级）、uql 多定义加预算、text-search 字节级预筛。
5. **发现成本**：help 任务表 + `action=help` 进 codemap + action 级 parity gate。

每条验收都应是**可执行不变量**（例如「坏 project-root ⇒ exit≠0 且无 `caller_count` 字段」），
写进 `tests/unit/mcp/test_output_cost_invariants.py` 或对应契约测试，而不是只写进文档。

## 8. 边界与未验证

- 仅 macOS / 10 核 / 本仓库；未测 Windows、MCP 传输层、非 Python 语言（3 个 lua/swift fixture 因缺 grammar 未索引）。
- 延迟为 warm 状态（索引已建）；cold 只在索引构建与无索引拒答两处观测。
- `--class-hierarchy` 曾出现一次 `class_count=0`，后确认是 lead 移动缓存目录导致的本地状态错误，**不是产品缺陷**，已从问题清单剔除。
- change-impact 召回缺口只在「注释级改动」上验证；行为级改动的召回率未测。
- 未验证 `--symbol-search` 的 exact 丢失在其他名字上是否同样发生（`analyze`/`execute` 已复现同类现象）。

## 9. 记忆记录

```json
{"branch":"develop@5f8017521","task":"trust dogfood: can TSA be trusted like grep","tools_used":["--text-search","--callers","--symbol-resolve","--symbol-search","--uql","--class-hierarchy","--change-impact","--ast-cache index","--call-graph"],"signals":{"cold_index_s":35.1,"warm_callers_s":1.05,"text_search_vs_rg":"1.2s vs 0.06s, 9/9 literal parity","uql_callees_multi_def_s":47.7,"project_root_lie":"exit0+NOT_FOUND+caller_count0","stale_verdict":"INFO","symbol_search_exact":"3/4 (DB has 4)","change_impact_recall":"4/8 direct-reference tests missed","stdout_usage_bytes":90979},"decision":"gap is trust contract (tier visibility, cost predictability, 6 honesty holes), not capability","verification":"each P0/P1 reproduced by lead with exact command in report","followups":["fix 6 honesty holes","reserve exact tier in symbol-search","unify index_state","symbol resolve via SQL","help task table + action parity gate"]}
```

## 10. 本轮已修复（2026-11-09，`fix/trust-honesty-signals`）

| 报告项 | 修复 | 验证 |
|---|---|---|
| P2-1 分派失败把 usage 打到 stdout | `cli_main._execute_selected_command` 改为 `parser.print_help(sys.stderr)`；`--help` 仍走 stdout | 子进程测试：`stdout == ""`、usage 在 stderr、exit 1；`tests/unit/cli/test_cli_input_robustness.py` + `tests/integration/cli/test_cli_commands.py` |
| P1-2 uql 对不存在符号报 `complete` | 来源阶段 0 定义 → `unknown` + `SYMBOL_NOT_DEFINED`；`next_step` 给出拼写/限定名/刷新索引三条修复动作 | `--uql "symbol('zzz').callers()"` → `NOT_FOUND/unknown/symbol:SYMBOL_NOT_DEFINED`；`tests/unit/uql/` 139 项通过 |
| 索引残余导致「每次索引都全量重写」 | 新增 `converge_symbol_projection()`（陈旧行 / 缺投影状态 / 过期 FTS 词条），修复路径先收敛再认证；认证器仍然全量复核后才发 marker | 本仓库实测：修复前每次 `index` 重提取 2917 文件约 57 s；修复后 no-op 提取 0 文件，改 6 个文件只提取 6 个；`tests/unit/test_index_symbol_projection.py` + `test_ast_cache_projection_state.py` |
| P1-1 过期索引 verdict 仍 `INFO` | `apply_source_evidence()` 在 `freshness=stale` 时置 `verdict=WARN`、顶层 `stale=true`、把 `SOURCE_INDEX_MISMATCH` 放到原因首位并镜像到 `agent_summary.verdict` | 本仓库实测：改一行后 `--callers main` 从 `INFO/342` 变为 `WARN/342/stale=true/reasons[0]=SOURCE_INDEX_MISMATCH`；`test_callers_reason_evidence.py` |
| P0-1 坏 `--project-root` 谎报 `NOT_FOUND` | `main()` 在分派前校验根目录；不存在时 fail closed：JSON `ERROR` + `INVALID_PROJECT_ROOT` + hint，且不输出任何答案字段；text 模式 stderr 输出、stdout 保持为空 | `--project-root /no/such/dir --callers main --format json` → exit 1、`INVALID_PROJECT_ROOT`、无 `caller_count`；`tests/unit/cli/test_cli_input_robustness.py` |
| P0-2 `--call-graph` 无索引静默全量解析 | `CodeGraphCallTool` 接入同一现场解析预算：无 AST 缓存且源文件 >200 时返回共享的 `WARN` + `INDEX_MISSING` 信封（真实文件数 + 建索引命令）；有缓存时行为不变 | 本仓库移走 `.ast-cache` 后实测：15.4 s / `INFO` / 401 callers → 0.53 s / `WARN` / `INDEX_MISSING` / `source_file_count: 2920`；`tests/unit/test_call_graph_tool.py` |

| P2-3 `--hotspot` 的 `CRITICAL`/`OK` 不在八值字母表 | 顶层 verdict 映射为 CRITICAL→`WARN`、REVIEW→`REVIEW`、无→`INFO`；严重度保留在 `results[].severity` 与 summary_line | `--hotspot --format json` → `WARN`（canonical），首条仍为 `severity: CRITICAL`；`test_handle_hotspot.py` 增加「verdict 必须在 `CANONICAL_VERDICTS` 内」的参数化断言 |

| P1-6 `.tsa/index-meta.json` 是矛盾的第二个真相源 | 删除该写入与私有 helper（仓库内无消费者、无文档，且只读分析会在工作区留下貌似权威的索引健康文件）；`.tsa/config.json`（severity 阈值配置）按原设计保留 | 本仓库 `--hotspot` 后只剩 `.tsa/config.json`；`test_handle_hotspot.py` 删除对应 3 处断言 |

| P2-5 `--agent-summary-only` 空操作 | 显式传入但没有 `--change-impact` 时 fail closed（exit 2、点名触发 flag，走 #1000 的 wiring 规则）；help 写明 requires | 子进程/进程内测试：误用 exit 2 且 stdout 空；`--change-impact --agent-summary-only` 仍正常 | 
| P2-6 MCP codemap 漏 11 个 action | codemap 每个 facade 的 action 列表改为与 `inputSchema` 精确相等，并注明 `action=help` 是运行时发现入口；新增契约测试比较 action 集合（漏/多都报） | `test_every_facade_action_has_codemap_parity`：94 个 action 全等（含 8 个 help、`index knowledge/schema`、`viz knowledge`） |

| 发现成本（§6 承诺 5） | `docs/CODEMAPS/cli.md` 首页新增「任务 → 命令」表（10 个真实任务 + instant/indexed 两层前置条件 + `--text-search` 与 `--symbol-search` 的区别），所有 flag 均对活解析器校验 | 表内 flag 全量校验通过；`codemap-sync --self-check` OK |

当时的待办：P1-3 行号、P1-4 召回、no-op 索引 ~7.4 s。——**现状见文首「最终状态」**：P1-3 与 no-op 成本已解决，只剩 P1-4。

**本轮附带发现（未修复）**：修复后 `--ast-cache --ast-cache-mode index` 的 no-op 仍需 ~7.4 s，profile 显示耗时在 `post_index_backfill`（`run_synapse_backfill` 6.5 s、`backfill_cross_file_edges` 3.5 s）——即每次索引都重跑调用点回填，即使源码没有任何变化。这是下一个效率目标。

## 11. 效率调查：no-op 索引的 ~7.4 s 为什么不能顺手砍掉（2026-11-09）

**观测**：本仓库 `--ast-cache --ast-cache-mode index` 的 no-op 运行 7.3–7.4 s（2919 文件、82k 符号）。
profile 显示大头是 `post_index_backfill`：`run_synapse_backfill` 重新解析了 94,077 条 unknown
调用边（其中 49,109 条被再次写回），加上 `backfill_cross_file_edges`。

**尝试**：当 `changed == 0`（无文件变化）且 `resolution_converged`（`ast_resolve_state` 指纹等于当前
`count:max(indexed_at)`）时跳过回填。实测有效——同一仓库 no-op 从 **7.3 s 降到 2.6–3.2 s**，
响应带 `backfill_skipped: RESOLUTION_CONVERGED`。

**为什么不合并**：两个既有契约测试直接否决了这个改动，且它们记录的是真实事故（PR #1253）：

- `test_fully_cached_missing_marker_reruns_every_backfill`：缓存命中但 call-graph marker 缺失时，
  必须重跑每一道回填——「缓存命中」不能证明「已经收敛」。
- `test_fully_cached_failed_retry_keeps_marker_clear`：上一轮回填失败后的重试必须仍可见地失败，
  marker 保持清空。

**根因**：本仓库 `call_graph_built()` 恒为 `False`——3 个 optional grammar（lua/swift）缺失使调用图
无法认证——而「缓存命中仍重跑回填」正是要恢复该 marker 的自愈路径。#1253 的语义是：只要认证链不完整，
重跑回填就是必须的，哪怕付出 4–5 s。因此这不是性能 bug，而是**自愈契约的代价**，不能用一个
`changed == 0` 的捷径绕过。

**要真正提速，需要先设计**（RFC 级）：

1. 把「投影/解析是否收敛」与「调用图是否可认证」拆成两个独立状态（现在 `call_graph_built`
   把两者混在一起），并让 `INDEX_CACHE` 响应声明各自的原因；
2. 对「仅因 optional grammar 不可认证」的仓库给出稳定的不可认证原因，允许收敛标记单独短路；
3. 或者把 synapse 的「重新解析 unknown 边」改成带 recheck 预算的抽样（记录上次尝试的输入指纹），
   在保持自愈语义的前提下把 no-op 成本降到 <1 s。

本轮结论：优化已实测有效但**回滚**，优先级让给正确性；下一次需带 RFC/设计说明再动。

**第 25 轮进展**：

1. 安全的半边已实现——调用图**已认证**且解析已收敛时，no-op 索引直接跳过回填，响应带
   `backfill_skipped: CERTIFIED_CONVERGED`；缺 marker/失败重试的两条 #1253 契约测试
   原样通过（本仓库 `call_graph_built()` 恒 False，所以本仓库不进入这条路径，实测 no-op
   仍是 8.06 s，符合预期）。
2. 本仓库这类「永远无法认证」的仓库需要的是**重试预算**而不是跳过：
   `rfcs/0045-backfill-retry-budget.md` 给出设计（把「多久重试一次」与「要不要重试」分开，
   失败/变更/force 一律立刻重试，仅对「刚成功但无法认证」的 no-op 生效），
   RED-first 测试计划与三条 #1253 不变式都写在里面。

3. 第二条**契约安全**的证据也已实现：当上一轮是「只差已记录稳定失败」的收敛刷新
   （#1671 记录，只在全部错误都是稳定失败、回填零错误的完整运行结束时签发，#1735 复用）时，
   同样跳过回填（`backfill_skipped: CONVERGED_STABLE_FAILURES`）。
   本仓库实测仍未触发（该库没有这条记录），no-op 仍是 9.08 s——原因是 3 个缺 grammar 的
   解析错误没有被登记为稳定失败，记录因此从未签发。

**第 26 轮的决定性测量（同一台机器、同一份 2921 文件语料，均标注冷/热）**

| 状态 | 实测 |
|---|---|
| 冷索引（`--ast-cache-mode index`，全新缓存） | **37.39 s**，索引 2921 文件，签发 3 条稳定失败记录 |
| 热 no-op（有记录：`record.now = 3`） | **0.72–0.86 s** |
| 热 no-op（**遗留缓存**：没有记录） | **9.08 s** |

也就是说：那 7–9 秒不是回填本身贵，而是**记录缺失**让每次 no-op 都重跑回填。
一旦缓存里存在 #1671 的稳定失败记录（一次完整刷新就会签发），零变化判定生效，
no-op 降到 **0.72 s**——**12 倍**，而且完全走既有机制，没有动 #1253 的任何契约。

所以正确的产品修复不是重试预算，而是**让记录不丢**：

1. 遗留缓存（记录从未签发 / 被清除）在下次增量 run 时把父版本的记录继承下来
   （内容未变 ⇒ 记录绑定的 (文件, 摘要, 原因) 仍然成立）；
2. 或者提供一次性迁移，把「上一轮是完整刷新且只差稳定失败」的缓存补签发记录。

RFC-0045 的重试预算因此降级为兜底方案：只有当记录确实无法签发（例如失败不是
稳定失败）时才需要它。

**第 28–29 轮实测（同一机器/语料，冷热标注）**：

| 场景 | 实测 |
|---|---|
| 编辑 5 个文件后索引（记录随之重签） | 4.67 s |
| 还原 1 个文件后索引 | 3.72 s |
| 零变化 no-op（记录在） | **0.66 s** |

记录生命周期闭环完成：`zero_change_hint`（遗留缓存）+ `inherit_record`（零变化世代继承）
+ 既有 #1671 签发路径。RFC-0045 已标记 **superseded**。

## 12. Agent-native primitives（只有 agent 会要求的东西）

前面 11 节是把工具修到「不撒谎、可预算」。这一节是反过来问：**如果按 agent 的工作方式重新设计，
TSA 应该长成什么样？** 人用工具是一次一问；agent 是**同一个问题反复问、增量问、跨轮次问**。
由此得到 6 个原语，按「实现成本 × 对 agent 的杠杆」排序。

### 12.1 答案 ETag + `If-None-Match`（最高杠杆）

agent 每个回合都会重问「X 的调用者是谁吗」，而绝大多数时候答案是**没变**。HTTP 早就有 304：
这里缺一个同价物。

- 响应新增 `answer_etag`（由 `action + 归一化参数 + 索引 generation + 作用域源码状态` 派生）。
- 请求可带 `if_none_match`；命中时返回最小载荷 `{success:true, unchanged:true, answer_etag}`（≈80 B），
  而不是 15 KB 的完整调用方列表。
- **可靠性条件**：只有在「同一索引 generation + 作用域源码复核一致 + 完整性不是 unknown」时才允许
  返回 unchanged；任何一项不确定都必须回完整答案。ETag 是承诺，不是猜测。
- 验收：编辑作用域外文件 → 仍返回 304；编辑作用域内文件 → 自动回完整答案（WARN + stale）。
- **已落地（第 10–11 轮，`nav action=callers`）**：响应新增 `answer_etag`（`sha256:` 前缀，只覆盖
  问题/答案内容/证据状态，忽略耗时与绝对路径）；请求可带 `if_none_match`，命中且未过期时返回
  ≈400 B 的 `{unchanged: true}`（不再回 15 KB 列表）。命中条件是「内容指纹相等 **且** 作用域未过期」，
  任何 stale/不确定状态一律回完整答案——实测 stale 后即使 etag 文本相同也回完整答案。

### 12.2 增量答案（`--since <answer_etag>`）

比 304 更进一步：不是「没变」，而是「**变在哪**」。只返回新增/消失的调用方条目
（`added[] / removed[] / unchanged_count`），像 `git diff` 之于 `cat`。对 agent 的长会话尤其关键：
它已经在上下文里持有上一版答案，只想要 delta。

**已落地（第 12 轮，`nav action=callers` 的无状态增量）**：请求带 `previous_entries`（上一次答案的
条目，agent 本来就在上下文里），服务端按 `(file, line, call_site_line, name)` 对齐后回
`{delta: {added, removed, unchanged_count}}`；作用域过期时一律回完整答案。实测新增一个调用方并重建
索引后：`added=1, unchanged=1`，响应里没有 `callers` 列表。

### 12.3 成本预检（`--cost`）

本仓库已经证明成本可以跨两个数量级（`--uql` 1.2 s vs 47 s）。agent 需要**先问价**：
`tsa --cost "symbol('main').callees()"` → `{tier, estimate_ms, files_scanned, may_exceed_budget}`。
有了它，agent 可以先选同义的便宜查询，而不是撞上 47 s 才发现。

### 12.4 能力清单（`--capabilities`）

8 个 facade、94 个 action、371 个 flag，agent 的规划成本全在「有哪些动作、它们的代价与前置条件」。
`--capabilities --format json` 应给出每个 action 的：`tier`（instant/indexed）、`preconditions`、
`cost_class`、**可直接复制的最小调用示例**、以及 `repair`（失败时该做什么的结构化动作，而不是英文句子）。
它比 90 KB 的 help 更接近「机器可规划的 API 描述」。

**已落地（第 14 轮，模块层）**：`tree_sitter_analyzer/capabilities.py` 的 `build_capability_manifest()`
从注册表派生这份清单——8 个 facade、94 个 action，每个 action 带 `tier`（instant/indexed）、
`preconditions`、`cost_class`、最小调用示例、`self_describing`。实测 14 个 instant / 70 个 indexed。
CLI `--capabilities` 与 MCP 暴露留到下一轮（新 flag 需要同步 codemap 与 README 的 flag 计数，单独一步做）。

### 12.5 缺席证书（negative-space answers）

`complete` 现在证明的是「列全了」；agent 更需要「**证明不存在**」：例如「这是入口点，所以没有调用者」
「这是脚本，没有被任何测试覆盖」。把 proof-carrying completeness 扩展到缺席结论，
返回 `absence: {kind: "entry_point"|"unreferenced"|"untested", evidence: [...]}`，
让 agent 敢于据此决策，而不是保守地再 grep 一遍。

**已实现**：`unreferenced`（第 18 轮）、`entry_point`（第 19 轮，读 `[project.scripts]` /
`[tool.poetry.scripts]` 与包 `__main__.py`）、`script`（第 22 轮，shebang 硬证据）。三者都是
`proven` 并附证据；空答案但证据不全时降级为 `unknown` + `possible`（附开放站点计数），
`NOT_FOUND` 一律不签证书。`untested`（`nav action=test_map`）也已实现（第 24 轮）。

**设计已提交（第 17 轮）**：`rfcs/0044-absence-certificates.md` —— `absence: {kind, confidence, evidence}`
只在底层问题 `complete` 时出现；`entry_point / script / unreferenced / untested` 四个保守规则，
任一规则读不到就降为 `unknown`/`possible` 并写明原因；不新增 action、不新增 flag（三面 parity 不变）。

### 12.6 答案作用域与过期条件（`expires_when`）

agent 常把答案缓存到下一轮。返回 `expires_when: {files: [...], index_generation: "..."}`，
agent 只要看到这几条文件没动、index 没重建，就可以安全复用——不需要重新提问。

### 12.8 让 agent 在它真正会读的地方发现这些能力

能力写进 RFC 与技能包还不够：agent 的第一站是 `docs/CODEMAPS/`。第 30 轮把主循环写进了
两处发现路径——`docs/CODEMAPS/cli.md` 的任务表新增三行（304 式重问 / 增量重问 / 预检），
并在下方给出「第 1 次问、第 N 次问」的具体命令对照；`docs/CODEMAPS/mcp-tools.md` 的
`nav` 与 `nav_test_map` 行注明 `answer_etag`、`absence` 与 `if_none_match` / `previous_entries`。

### 实施顺序

1. **12.1 + 12.2**（一个 PR）：都依赖同一份「答案身份 + 源码状态」派生，先做 ETag 再做 delta。
2. **12.3 + 12.4**（一个 PR）：成本预检与能力清单共享同一张静态元数据表。
3. **12.5**（需要 RFC）：缺席证书涉及完整性语义扩展。
4. **12.6**：作为 12.1 的附带字段落地。

这些都不是人类用户会主动要求的交互，但对 agent 的「反复问、增量问」是数量级的改进——
也正是「离不开」的来源：不是功能多，而是**重问几乎免费**。

### 12.7 用法食谱：把「重问」变成「增量问」

三个原语（`answer_etag` / `if_none_match` / `previous_entries`）已经可用。agent 在做多轮任务时的推荐循环：

```text
第 1 轮   ask:   --callers target
          keep:  answer_etag, callers[]

第 N 轮   ask:   --callers target  +  previous_entries: <第 1 轮的 callers[]>
          get:   {delta: {added, removed, unchanged_count}, answer_etag}
          use:   只把 added / removed 读进上下文；unchanged 不重读

只想知道「有没有变」
          ask:   --callers target  +  if_none_match: <上一轮 answer_etag>
          get:   {unchanged: true}（≈400 B）——没变就直接跳过
```

三条可靠性规则（实现里已强制，不是约定）：

1. `unchanged` 只在「内容指纹相同 **且** 作用域未过期」时成立；否则回完整答案。
2. `delta` 用调用方身份 `(file, line, call_site_line, name)` 对齐，不靠位置猜。
3. 任何 `stale`/unknown 状态都会让两个原语失效并回完整答案——宁可多传 15 KB，不给假结论。

**收益量级**：一个 10 轮的「盯着某个函数」任务，从 10 × 15 KB ≈ 150 KB 降到 15 KB + 9 × 400 B ≈ 19 KB；
真正省下的是 agent 的上下文预算，而这正是长任务最先耗尽的东西。

## 13. Agent 工作流实测（第 35 轮，同一台机器，本仓库 2921 文件）

把 §12 的原语按 agent 的真实顺序跑一遍，记录**输出形状与耗时**（机器：macOS 10 核；状态：暖索引）：

| 步骤 | 命令 | 结果 | 耗时 |
|---|---|---|---|
| 1. 出手前预检 | `--capabilities nav.callers` | `indexed` tier，`precondition_met: true` | 1.31 s |
| 2. 第一次问 | `--callers build_facade` | 4 个调用方，`answer_etag: sha256:698e5990…`，`callers[]` ≈ 1.2 KB | 7.04 s |
| 3. 只问「有没有变」 | 同问 + `--if-none-match <etag>` | `{unchanged: true, …}`，**7 个键**（无 `callers[]`） | 2.12 s |
| 4. 只问「变在哪」 | 同问 + `--previous-entries-json <上一轮 callers[]>` | `added 0 / removed 0 / unchanged 4`，`completeness: complete` | 1.75 s |

**诚实解读（重要）**：第 3 步的耗时下降主要来自缓存回暖，**不是**因为跳过了计算——304 路径仍然是「先算出完整答案，再只回最小载荷」。真正被省掉的是**上下文成本**：7 个键 vs 1.2 KB 的调用方列表，十轮下来就是 12 KB vs 1 KB 量级。

要让延迟也下降，需要服务端按 etag 记住答案（下一阶段可做：`answer_etag → 缓存条目`，命中即跳过图查询）。当前实现刻意不做，因为那会引入新的失效面。

结论：原语按设计工作——**省的是 agent 最容易耗尽的东西（上下文），不是 CPU**。
