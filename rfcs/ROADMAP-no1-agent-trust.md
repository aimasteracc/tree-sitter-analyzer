# Roadmap — Trusted Agent Change Intelligence No.1 Program

- **Status:** active
- **Branch:** `docs/tsa-trust-consolidation`
- **Mission:** Become the most trusted local code-change intelligence layer for AI coding agents.
- **North star:** Verified Change Success Rate (VCSR), not feature, language, tool, test, or edge count.
- **Claim policy:** Public language is always bounded to named tools, versions, repositories, models, dates, and evidence levels. E0–E3 emit no quantitative competitive wording; E4 permits only the exact admitted bounded sentence, never an unqualified "No.1" claim.

## 2026-09-08 已合入修复与可信反馈复测

本节更新运行证据；下节已裁决的范围和发布边界继续有效。
本次基线为 `develop@0d50d2760ba5f5447393b5df5e21eccc5af42934`。
已合入 [#1405](https://github.com/aimasteracc/tree-sitter-analyzer/pull/1405)
（保存检测、扫描续跑与 watcher 生命周期）、
[#1410](https://github.com/aimasteracc/tree-sitter-analyzer/pull/1410)
（SQLite 复用 WAL 尾部的认证误拒绝）、
[#1411](https://github.com/aimasteracc/tree-sitter-analyzer/pull/1411)
（项目根别名的缓存身份统一）。组合基线 quick gate 为
**2,047 passed、28 skipped，31.63 秒**；既有跳过不算通过。

### 重复测量：可信可恢复，尚非瞬间反馈

环境为 macOS 26.6.2 arm64、Python 3.14.3；合成项目包含 10,000 个
Python 文件。使用真实 ASTCache、PulseTool 和 FileWatcherDaemon，没有模块替换。
先在无 watcher 的同一进程连续查询 20 次，再启动默认 watcher
（轮询 5 秒、debounce 2 秒），等待启动同步完成后连续执行 10 个保存周期。
每次切换末尾文件函数的等长返回值，并恢复原 `mtime_ns`，验证内容检测。
保存后立即查询，收到同步 complete 回调后再次查询；每轮等待上限 60 秒。
保存延迟从写入前计时至同步后的查询返回，包含该实验自己的即时查询成本。

| 观测 | 成功 / 总数 | 最小 / 中位 / 最大耗时 |
|---|---|---|
| 稳定 Pulse 查询返回 fresh | 20 / 20 | 1.734 / 1.755 / 2.643 秒 |
| 保存后立即查询正确拒绝陈旧证据 | 10 / 10 | 全部为 stale / SOURCE_INDEX_MISMATCH |
| 保存至查询恢复 fresh | 10 / 10 | 7.298 / 11.725 / 11.844 秒 |

启动同步耗时 5.422 秒；保存至同步 complete 的中位耗时为 9.599 秒。
watcher 记录 10 个事件、11 次同步、0 个错误，并成功停止。
样本最近秩 95% 分位分别为 2.040 秒和 11.844 秒；它们只描述这
20 / 10 次顺序观测，**不是总体 p95、SLA、跨平台或真实项目性能证明**。
所有失败均保留在分母中；没有以过滤失败后的延迟冒充整体成功率。

另一个独立计时进程以透传包装器记录 `_capture_sources_with_deadline`。
首次查询后，3 次复用同一快照的查询耗时为 1.630 / 1.631 / 1.626 秒，
每次均调用该函数 3 次，累计耗时分别为 1.359 / 1.361 / 1.354 秒，
约占总耗时 83%。这是源码证据采集成本的定位线索，不是删除一致性检查的依据。
优化必须证明同一响应仍绑定同一源码代次，并保留保存、并发写入、替换和删除的拒绝路径。

### 尚未闭合的可信边界

- 旧候选在更新后的完整索引之后恢复执行，仍可删除新结果；同进程顺序重放和
  跨进程实验均已复现。进程内锁无法拒绝已经过时的输入。
  [RFC-0032 / #1412](https://github.com/aimasteracc/tree-sitter-analyzer/pull/1412)
  仍为 draft；schema 代次、写入所有权、崩溃恢复及兼容性取舍尚未实施。
- [#1407](https://github.com/aimasteracc/tree-sitter-analyzer/pull/1407)
  的分批验证仍存在外层命令总长度限制；RFC-0031 的短验证计划入口仍待裁决。
- 本次观测覆盖 Pulse 的一个合成 Python 场景，未证明所有读取入口、原生 Windows
  路径、多语言真实项目或长时间并发场景均满足相同边界。
- 当前可把 TSA 描述为 Agent 的结构化感知与反馈基础设施；它不能替代 Agent 的
  推理、运行时观测或测试。还不能据此宣称“用了就拥有完整大脑和神经网络”，
  更不能宣称行业 No.1。竞争优势仍需按既定 VCSR / E4 规则进行同任务对照验证。

本地原始记录为 `/tmp/tsa-repeated-feedback-proof.json` 与
`/tmp/tsa-feedback-timing-breakdown.json`，复测脚本为
`/tmp/tsa_repeated_feedback_probe.py`；这些是临时诊断附件，未作为仓库基准资产发布。
下一步优先关闭过时写入的数据保护缺口，再以一致性回归证明约束源码认证优化，
并补齐真实项目、原生平台与任务成功率证据；本节不新增性能承诺或授权发版。

## 2026-09-07 执行收敛：先可信，再扩展

本节保留执行优先级与用户裁决；运行证据以上方 2026-09-08 复测为准。
后文的历史基线和十二个月目标不代表已实现能力。
本轮完成的是初审与隔离复现，不是全仓整顿、全量测试有效性证明或发布验收。
既有 RFC 的实现授权、证据和发布门槛仍然有效；本节不绕过这些门槛。

### 用户已裁决的边界

- 内部被替代实现应移除；已经发布的旧 CLI/MCP/Python 接口在下一次明确的
  **主版本升级**统一删除并提供迁移说明，不无限期保留两套业务实现。
- 第一阶段的即时反馈是**文件保存后的自动更新，以及 Agent 编辑前的风险反馈**。
  未保存缓冲区、任意读取事件和编辑器深度集成不属于第一阶段。
- golden/黄金快照是验证方法，不是与 unit/integration/E2E 互斥的执行层级。
- 所有普通修复、文档和架构收敛进入 `develop`；只有经裁决的发布候选进入
  `release/v*`，再按 GITFLOW 合入 `main` 并回合 `develop`。本轮不授权发版。

### 本轮证据与限制

分支比较固定为 `main@915eb0dee2526e6f552f81aafcb07c6019408d87` 与
`develop@c9f777beb7f183c3cad7a153a34142fd1c23480b`：main-only 为 0，
develop-only 为 412 个提交；差异涉及 1,392 个文件、211,994 行增加和
102,091 行删除。祖先关系不证明这 412 个提交都应发布。

隔离索引实验运行于 `2851b611887ceab6a4d23a9b4b25f1b0839892e5`
（PR #1383，尚未合并到上述 develop 基线），macOS、Python 3.12.13、
24 GiB 内存、10 个逻辑 CPU。实验只有两个 Python 文件，没有启用 watcher。
以下是单次诊断，不是正式性能基准，也不能外推到十万文件。

| 场景 | 实测结果 | 裁决 |
|---|---|---|
| 无索引查询状态 | `MISSING_INDEX` | 正确拒绝假装已就绪 |
| 两文件完整索引 | 约 0.148 秒；状态 complete；跨文件 caller 1 条，绑定为 project | 小样本正向链路可用 |
| CLI 重复查询 | 约 0.142 / 0.147 秒 | 两个独立进程，只代表磁盘缓存复用 |
| 同一 MCP 进程重复查询 | 首次 0.0895 秒，后续 0.0025 / 0.0021 / 0.0020 秒 | 存在热路径；当时索引认证 incomplete，不能算可信热查询达标 |
| 保存后旧符号查询 | 旧名称仍为 `match_tier=exact`，附带新名称的当前源码 | 阻断项：同一响应混合两个版本 |
| 保存后新符号 callers | `NOT_FOUND`，但状态工具报告 `SOURCE_INDEX_MISMATCH` | 查询必须携带新鲜度，不能让旧索引误导拼写诊断 |
| 显式增量同步 | 两文件均更新、符号和 caller 随之更新；exit 1、`incomplete` | 数据更新与认证完成是两个状态，不得混为成功 |
| 随后再次无变化同步 | errors=0、backfill_errors=0、manifest_certification_failed=false，仍 incomplete | 需要可操作的未完成原因；根因未在本轮定位 |

复现输入：`leaf.py` 定义 `tsa_probe_leaf(value)`；`service.py` 导入并调用它。
完整索引后将两文件中的名称改为 `tsa_probe_leaf_v2`，实现从 `value + 1`
改为 `value + 2`。针对同一隔离目录依次执行：

```bash
uv run python -m tree_sitter_analyzer --project-root "$PROBE_ROOT" --full-index --full-index-mode full --full-index-max-files 100 --format json
# 修改两个文件后，先查询，不能提前同步而隐藏问题。
uv run python -m tree_sitter_analyzer --project-root "$PROBE_ROOT" --codegraph-status --format json
uv run python -m tree_sitter_analyzer --project-root "$PROBE_ROOT" --symbol-search tsa_probe_leaf --format json
uv run python -m tree_sitter_analyzer --project-root "$PROBE_ROOT" --callers tsa_probe_leaf_v2 --format json
uv run python -m tree_sitter_analyzer --project-root "$PROBE_ROOT" --incremental-sync --format json
```

测试初审也发现两个已核验事实，不代表整个测试树都已审完：

- `tests/integration/test_phase7_integration_suite.py` 的集成、性能、安全等
  路径只等待 `_simulate_integration_step()` 后赋值 `success = True`，没有
  调用其宣称验证的能力。它只能证明报告流程，不能证明企业就绪或系统正确。
- `test_mcp_list_files_p1.py` 重导出 p1a/p1b；三个文件一起 collect 得到
  **46 个 node ID，对应 23 个原始测试函数**。这是重复收集的具体证据。
  其他“相似测试”仍须比较输入和行为断言，不能凭相同被测函数就删除。

### 目标架构：一个事实源，多个有版本的视图

```text
文件保存 / Agent 编辑前事件
  -> 项目与工作树隔离、事件序号、立即标记相关证据待更新
  -> 单写者增量流水线：文件清单 -> 解析 -> 符号/边差异 -> 受影响绑定
  -> 原子发布 generation：源码证据 + 符号 + 边 + 完整性
  -> 有界查询与版本绑定的反馈：影响位置、约束、测试建议、unknown
  -> MCP / CLI / 订阅通知 / 生成式参考文档
```

现有 `graph/edge_store.py` 已提供 SQLite 统一边表及 calls/imports/extends/
implements/references 等关系类型；枚举中存在类型不等于所有语言都完整产生它。
`knowledge_graph/builder.py` 从 AST/edges 构建投影，`knowledge_graph/stores.py`
提供可选 LadybugDB/Cypher 镜像。暂不增加 Neo4j 或第二个权威事实库。
可视化与图数据库镜像是可重建视图，不得各自决定源代码真相。

每次查询的符号坐标、源码片段和关系必须绑定同一 generation；无法绑定时返回
明确的 stale/partial/unknown。`match_tier=exact` 只表示名称匹配，不表示事实新鲜。
“零匹配”“未索引”“解析失败”“事件待处理”“预算截断”必须可区分。
静态解析不可能消除动态语言所有歧义；未知关系不能改名为精确影响。

保存后先快速报告“已变更、证据待更新”，再发布可信影响结果。编辑前反馈通过
Agent hook/MCP 请求获得，不能声称磁盘 watcher 能感知尚未发生的编辑意图。
watcher 要覆盖原子替换、创建/删除/重命名、事件乱序与丢失、队列溢出、重启、
分支切换、多工作树和并发查询；事件丢失必须重新核对清单，不能静默沿用旧图。

### 执行工作包与退出条件

| 顺序 / ID | 范围 | 退出条件 |
|---|---|---|
| P0 / TRUST-C1 | 索引版本一致性与认证诊断 | 上述混版本复现变红再修绿；查询明确显示证据版本；同步未完成有稳定原因；不以重试洗白不一致 |
| P0 / TRUST-T1 | 虚假测试与重复收集试点 | 报告模拟不再被算成系统验证；重复 node ID 有明确去重；保留的断言能抓住具名真实故障 |
| P1 / TRUST-A1 | 新旧实现责任清单及逐项收敛 | 每个删除项都有当前入口、消费者、唯一职责、替代实现和回归证据；更新入口后旧实现不再可达，再删除 |
| P1 / TRUST-I1 | 保存后刷新及编辑前反馈 | 同进程/跨进程冷暖启动、增改删重命名、watcher恢复与并发读在声明平台实测；旧边清除、新绑定出现、输出版本一致 |
| P2 / TRUST-S1 | 1万/10万/30万文件规模阶梯 | 固定机器、语料字节数/符号数/边数/语言/扇出；记录构建、热查、刷新 p50/p95、峰值内存、队列与失败率；全部失败保留分母 |
| P2 / TRUST-D1 | 文档与代码可验证同步 | 同一能力清单生成 schema/CLI/语言参考；文档例子可执行；失效参考区分确定与候选；三语共享事实、不复制手工数字 |
| P3 / TRUST-R1 | develop 发布价值逐项裁决 | 每个能力有 keep/migrate/experimental/remove 决策及依赖闭包；被排除实验真正不进入发布构建；升级路径与跨平台门槛通过 |

依赖：C1 在 I1 之前；T1 与 C1 可独立推进；A1 先清点，删除按 C1/T1 的
保护网逐批落地；S1 在可信增量闭环后才评价性能；D1 的事实源来自收敛后的
运行时能力表。R1 接受经过验证的能力切片，不等所有愿景完成才发布，也不
按 git commit 日期把依赖链割断。普通工作包拆成可独立验证的 develop PR。

大规模热路径不得每次全仓读取、全图复制或重复解析未变化文件；用有界图扩展、
按需源码、背压和可恢复批次控制成本。`KnowledgeGraphBuilder.build()` 当前
读取全量文件行，默认无上限时也读取全量边，不能直接当作实时热查询路径。
规模目标尚未达标；延迟和内存预算在固定语料的首轮基线后预注册，不能在失败
后改阈值来获得绿灯。可先用合成语料定位瓶颈，最终必须加入具名真实大仓库。

### 测试、删除与文档的统一规则

- 测试采用三个正交维度：执行层级 unit/integration/E2E；验证方法
  example/property/golden/mutation；运行成本 quick/full_language/slow/benchmark。
  contract/regression 描述被保护的约定或事故，不因目录名字就自动具备有效性。
- 删除测试前列出其行为、输入分区、失败见证和保留位置；同一实现的不同边界
  输入不算重复。golden 保留跨语言代表性与复杂结构，不用全量快照覆盖所有细节。
  覆盖率只是漏测信号；静态 test_map 不等于执行覆盖，更不等于约束有效。
- 不降低 pytest 时限、不关闭 xdist、不新增无追踪 skip、不把失败测试改成
  仅断言“返回了对象”。沿用 AGENTS.md 的 quick/comprehensive 两层命令。
- 旧实现删除不是按 `legacy`、mixin、adapter 文件名扫除。仍有唯一职责的
  代码先迁移职责；持久化缓存的旧格式明确迁移或版本化失效；外部接口按主版本政策。
- 代码能生成的是接口、字段、语言支持和结构事实；设计动机与使用承诺由人审。
  保存时使相关文档事实失效并刷新局部生成视图，CI 校验 committed 输出和示例；
  不让 LLM 每次保存都重写整本文档，也不自动改写历史报告来贴合当前结果。

### 发布与团队边界

优先候选是可靠解析/绑定、可信增量与查询、编辑影响与有效验证、安装诊断和
一致的 JSON 契约。图可视化/镜像可保持可选；学习、语义检索和更高层任务 API
按各自证据及 RFC 授权判定实验状态。移除重复搜索封装与格式不意味着移除内部
CSV 批量导入等不同职责。没有逐项验证之前，不把上述候选写成“可发布”。

PM/主代理负责架构决策、证据复核和验收；Spark 负责限定路径、限定输出的
调查与机械工作，按既有团队规则最多两个工作者并发。模型用量不足时暂停派发，
不得冒称指定模型已完成。本轮架构 Spark 审计因配额停止，发布/测试初审已返回；
主代理复核了本节列出的具体事实，尚无全仓“可安全删除”清单。

## 1. Strategic position

TSA will win a narrow category before expanding: **local, polyglot, evidence-backed change intelligence for autonomous coding agents**.

The product promise is:

> Understand the relevant code, plan a safe change, and verify the result with fresh, auditable evidence. When evidence is insufficient, say `unknown` rather than guess.

The default user journey becomes three task outcomes:

1. `understand(task)` — entry points, relevant source, relationships, freshness, evidence.
2. `plan_change(task | diff)` — blast radius, constraints, affected tests, unknowns, verification plan.
3. `assess_change(diff)` — static structural/classification/constraint findings with explicit freshness and runtime `not_run`; it does not claim runtime verification.

Existing MCP/CLI primitives remain the implementation substrate and compatibility surface. New top-level UX must compose them rather than duplicate engines.

## 2. Baseline

Baseline captured by dogfooding the current repository. The values below were
measured on 2026-08-08 with
`uv run python -m tree_sitter_analyzer --project-health --format json`. The
executable baseline is bound to `origin/develop` commit
`c0b59748f7b2885b27e9fb810ff9822b9906426f`; this branch changes documentation
only. Re-measure rather than carrying these values forward after that source
commit changes.


| Signal | Current state |
|---|---|
| Project-health scope | 1,985 analyzed files |
| Health | 1,602 A / 347 B / 32 C / 4 D / 0 F; verdict `REVIEW`; weakest dimension `structure` |
| Constraints | `SAFE` |
| Resolver registry xref | `register_language`: 15 callers, 1 callee |
| Main technical moat | conservative language-gated resolution and edit-safety loop |
| Main product risk | broad surface and inconsistent claims/support-language wording |
| Main adoption risk | install/runtime friction and low external validation |
| Main execution risk | benchmark complexity hotspots and maintainer concentration |
| Observed onboarding failure | project requires uv `>=0.11.0`; local uv `0.10.8` blocks normal `uv run` |

## 3. Scorecard and gates

### North star

**Verified Change Success Rate (VCSR)** is the percentage of pre-registered agent tasks that:

- modify only allowed paths;
- satisfy exact behavioral oracles;
- pass the declared verification command;
- leave no stale symbol or edge rows;
- contain no high-confidence unsupported relationship used to justify the change.

### Quality gates

| Dimension | Gate |
|---|---|
| Change outcome | VCSR reported by repository and task class; no weighted score may hide a regression |
| Reliability | successful indexed trials >=99%; all timeouts/product failures remain in denominator |
| Citations | deterministic citation-location validity >=99% |
| Trust | exact stale-row and stale-edge counts = 0 for incremental fixtures |
| Quality | RFC-0021 non-inferiority gate passes before cost/latency claims |
| Efficiency win | paired 95% CI upper bound for cost or latency ratio <=0.80 under RFC-0021 rules |
| Onboarding | fresh-machine install -> first trusted answer succeeds >=95%, then ratchets to >=99% |
| Warm query | publish P50/P95 by repository size; no headline without reproducible artifact |
| Community | at least 3 active external maintainers/reviewers before enterprise-support claims |
| Evidence | E2 internal complete matrix -> E3 second machine -> E4 public independent reproduction |

## 4. Operating rules

### Stop

- Stop treating new flags, actions, scaffolds, languages, diagrams, or test count as strategic progress.
- Stop adding public surfaces when an existing facade can compose the outcome.
- Stop copying measured numbers manually into multiple documents.
- Stop publishing broad leadership wording before the evidence ladder permits it.
- Stop model-backed benchmark spend until model-free setup, provenance, budget, isolation, and replay gates pass.

### Continue

- Continue local-first operation, project-root security, MCP/CLI parity, JSON for both MCP and CLI, and fail-closed benchmarks.
- Continue conservative resolution: a visible `unknown` is safer than a confident unsupported edge.
- Continue dogfooding before edits and following the emitted verification command after edits.
- Continue exact behavioral tests, but prefer realistic corpus failures over coverage-only growth.

### Start

- Start task-outcome APIs, edge evidence/provenance, claim generation, install-funnel qualification, and external reproduction.
- Start deleting or demoting low-use public surface based on explicit compatibility policy.
- Start publishing reproducible SLO curves for install, index, warm query, incremental refresh, and task outcomes.
- Start recruiting independent oracle reviewers and resolver owners.

## 5. Twelve-month roadmap

### Wave 0 — Program control, bounded E0 canary, and E1 qualification (days 0-30)

**Outcome:** one source of truth, a bounded E0 production-canary path, and separately qualified measurable onboarding.

- Land this roadmap, task ledger, ownership model, and claim policy.
- Complete the NO1-002C/002D production-canary operator path without weakening trust gates; its real bounded run remains E0 operational evidence and cannot advance the RFC-0021 ladder.
- Qualify a separate reproducible install/smoke result before assigning E1 or unlocking E2 setup.
- Create a machine-readable claim registry bound to benchmark artifact digests.
- Generate one canonical language support-depth matrix from code/contract evidence.
- Add a clean-machine install qualification that covers an installed-but-outdated uv.
- Freeze the three-task API and edge-evidence contracts as reviewed RFCs.

**Exit gate:** the bounded E0 canary is replayable, a distinct E1 install/smoke qualification is reproducible, claims have one source, install-to-first-answer is measured, and no new unbounded claim is possible.

### Wave 1 — Complete internal evidence and minimum product path (days 31-90)

**Outcome:** RFC-0021 E2 evidence and a usable three-task prototype.

- Finish manifest-bound setup validation for all seven pinned repositories and required arms.
- Run the complete pre-registered warm matrix only after setup and budget gates pass.
- Qualify one second current indexed competitor at the install/conformance boundary; it is not an RFC-0021 v1 matrix arm. Any comparative inclusion requires a separately reviewed v2 experiment with a re-frozen manifest, matrix cardinality, fairness policy, and endpoints; unavailability remains `NOT_EVALUATED`.
- Implement `understand`, `plan_change`, and `assess_change` as orchestration over existing primitives.
- Attach freshness, evidence, resolution kind, and confidence policy to task-level conclusions.
- Split optional heavyweight dependencies from the default install path.
- Publish reproducible cold-start, index, warm-query, incremental, token, and tool-call baselines.

**Exit gate:** complete E2 artifacts; task APIs pass exact contract tests; fresh install succeeds >=95%; no quality regression is hidden by efficiency.

### Wave 2 — Agent change outcomes (months 4-6)

**Outcome:** prove that better graph evidence produces better code changes.

- Add pre-registered bugfix, refactor, API migration, and affected-test tasks.
- Measure VCSR across at least three agent clients/models without pooling backends.
- Make the three-task API the recommended agent path while retaining facade compatibility.
- Harden multi-agent/worktree freshness, concurrent reads, serialized writes, and crash recovery.
- Ship deep integrations for Claude Code, Cursor, and Codex with doctor and lifecycle checks.
- Publish at least three external design-partner case studies, including failures.

**Exit gate:** task-outcome benchmark is reproducible; ten external teams have completed real workflows; retained usage grows for two consecutive cohorts.

### Wave 3 — Independent reproduction and ecosystem (months 7-9)

**Outcome:** E3 evidence and contribution leverage beyond one maintainer.

- Reproduce the complete primary conclusion on a clean independent machine.
- Complete independent blind review and disclose disagreements/adjudications.
- Stabilize the resolver/framework SDK and adversarial conformance suite.
- Certify community plugins only when extraction, resolution, incremental, and miswire gates pass.
- Publish signed artifacts, SBOM/provenance, compatibility policy, and an LTS line.

**Exit gate:** E3 reached; at least three external maintainers/reviewers own defined areas; two external plugins pass certification.

### Wave 4 — Public bounded leadership and team product (months 10-12)

**Outcome:** E4 bounded leadership evidence and a sustainable adoption/business layer.

- Publish raw artifacts, exact commands, checksums, failures, versions, and bounded conclusions.
- Obtain third-party reproduction before using "best among tested tools" wording.
- Ship optional team capabilities: shared index, policy distribution, audit trail, private plugins, RBAC/SSO, and support SLO.
- Keep correctness and evidence protocols open; monetize collaboration, governance, and operations.
- Decide expansion only from task outcomes and retained-user evidence.

**Exit gate:** E4 reached for a named benchmark version, ten public production cases, and a credible multi-maintainer support model.

## 6. Team topology

The program uses role-based agents with isolated worktrees for implementation. Per `LOOP.md`, no more than two L2 agents run concurrently.

| Role | Accountability | Initial owner |
|---|---|---|
| Program Orchestrator | critical path, dependency gates, final integration, GitFlow | parent agent |
| Trust & Benchmark Lead | RFC-0021, NO1-002C/D, provenance, replay, claim ladder | `no1-canary-implementer` (NO1-003B) |
| Product/API Lead | three-task contracts, compatibility, Agent UX | RFC-0022/0023 drafts complete; next NO1-010A through their stated gates |
| Runtime Lead | install, packaging, indexing SLO, concurrency | NO1-006A package/MCP and manual content-bound outdated-uv slices qualified at run `31288611024` |
| Evidence/Claims Lead | claim registry, support matrix, generated docs | NO1-004A/B and NO1-005A merged; future E4 admission remains external |
| Independent Reviewer | oracle signatures, blind review, E3 reproduction | human/external agent; cannot be benchmark author |
| Community/GTM Lead | integrations, design partners, case studies | human-led with research agents |

Agents may prepare artifacts and code, but these gates remain human-controlled: model spend authorization, independent oracle signature, production judge acceptance, public claims, release, and merge.

## 7. First 90-day task ledger

### P0 — active/next

| ID | Task | Owner role | Depends on | Acceptance and verification |
|---|---|---|---|---|
| NO1-003A | Program roadmap and task ledger | Program Orchestrator | none | roadmap reviewed; branch obeys GitFlow; `--change-impact` reports exact verification |
| NO1-003B | Production canary operator runbook and offline rehearsal | Trust Lead | NO1-002D | fixture remains `NOT_EVALUATED`; production callbacks only after signed attestation + judge ACCEPT; focused production-trust tests |
| NO1-003D | Implement and qualify the production dispatcher/admission boundary | Runtime + Trust Leads | NO1-003B | separately reviewed dispatcher consumes the qualified bound spec exactly once, preserves kill switch/budget/attestation/judge gates, and performs no model call during qualification |
| NO1-003C | Execute one real bounded E0 Gin production canary | Human Operator + Trust Lead | NO1-003D, NO1-008A | immutable complete bundle, budget ledger, policy audit, and replay; callbacks remain forbidden until model-free setup, signed attestation, human budget, and judge gates pass; the admitted manifest remains E0 and cannot unlock E1/E2 or public/No.1 wording |
| NO1-004A | Claim registry schema and validator (complete) | Evidence Lead | NO1-003A | every quantitative README marketing claim is registry-generated with names/versions, metric/unit/numerator/denominator, benchmark/date/corpus/repo commit, repository set, model/backend, evidence level, and an independently reproduced digest admitted by the code-owned trust root; stale/mixed/self-attested claims fail closed |
| NO1-004B | Generated claim/support snippets (complete) | Evidence Lead | NO1-004A, NO1-005A | deterministic claim marker plus whole-README coverage rejects manual quantitative marketing; command/version data and the independent language inventory generator are excluded |
| NO1-005A | Canonical language support-depth inventory | Product Lead | none | pipeline registration dimensions derived from executable registries; cross-file E2E remains tri-state and requires positive fixtures |
| NO1-006A | Fresh-install qualification harness | Runtime Lead | none | one exact wheel passes native macOS/Linux/Windows package-to-MCP-first-answer qualification; the separate outdated slice requires Linux/macOS `manual_content_bound_remediation`, records Windows `NOT_APPLICABLE_NO_NATIVE_INSTALLER` with `passed=false`, and keeps mutable automatic bootstrap explicitly unqualified |
| NO1-006B | Default dependency split RFC and measured baseline | Runtime Lead | NO1-006A | wheel/download/startup/dependency counts measured before design; no big-bang rewrite |
| NO1-007A | RFC: `understand/plan_change/assess_change` | Product/API Lead | NO1-003A | fixed schemas, compatibility map, evidence fields, no duplicate analysis engine |
| NO1-007B | RFC: edge evidence/confidence/freshness | Product/API + Trust | NO1-007A | confidence semantics calibrated; `unknown` never promoted without evidence |

Integration chronology: NO1-004A/B and NO1-007A/B were implemented against the
program-policy draft and merged before this governance PR. That parallel merge
history does not mark NO1-003A complete; NO1-003A closes only when PR #1238 itself
lands on `develop`.

NO1-004A/004B closure is deliberately a zero-public-claim state: the only
checked-in record is blocked E0 and emits no wording. Unsupported historical
benchmark/performance numbers were removed from the main README. A future
number can appear there only as the exact deterministic E4 sentence generated
from a digest-verified artifact; E0–E3 and blocked records cannot emit text.

### P1 — after P0 gates

| ID | Task | Owner role | Depends on | Acceptance and verification |
|---|---|---|---|---|
| NO1-008A | Seven-repository model-free setup qualification | Benchmark Lead | separate RFC-0021 E1 qualification | exact source partitions, zero unallowed parse errors, pinned tool/repo fingerprints, and no model callbacks; any failure blocks NO1-008B and later model-backed phases |
| NO1-008B | E2 warm confirmatory matrix | Benchmark Lead + Human Operator | NO1-008A | exact expected cells, five repeats, complete evaluations, failures retained |
| NO1-009A | Select and qualify second indexed competitor | Trust Lead + Independent Reviewer | NO1-003A | frozen version/install/conformance path; unavailable arm is `NOT_EVALUATED`, never a TSA win; it is not added to the frozen RFC-0021 v1 matrix without a separately reviewed v2 experiment and recomputed cells |
| NO1-010A | Three-task prototype | Product/API Lead | NO1-007A/B | MCP/CLI parity or explicit internal-only status; exact contract tests; real CLI smoke |
| NO1-010B | Agent change-outcome benchmark RFC | Benchmark + Product | NO1-008B, NO1-010A | bugfix/refactor/migration/test-selection oracles; VCSR primary endpoint |
| NO1-011A | Lightweight default install implementation | Runtime Lead | NO1-006B | compatibility preserved; fresh-install success and startup improve on all axes |
| NO1-012A | Performance/SLO artifact pipeline (TRUST-S1) | Runtime Lead | NO1-006A, TRUST-I1 | byte-stable reports; P50/P95 by repo size only after the trusted incremental loop passes; no benchmark-only pytest misuse |
| NO1-013A | Three-client integration qualification | Community/GTM | NO1-010A | Claude Code, Cursor, Codex install/index/query/uninstall scenarios pass |

## 8. Dependency graph

```text
NO1-003A
  ├─ NO1-004A ─ NO1-004B
  ├─ NO1-007A ─ NO1-007B ─ NO1-010A
  ├─ NO1-005A ─ NO1-004B
  └─ NO1-009A

NO1-002D ─ NO1-003B ─ NO1-003D (dispatcher; no model call)
[separate RFC-0021 E1 qualification] ─ NO1-008A (model-free setup) ─ NO1-008B ─ NO1-010B
NO1-003D + NO1-008A ─ NO1-003C (bounded E0 canary; both are required)

NO1-006A ─ NO1-006B ─ NO1-011A
NO1-006A + TRUST-I1 ─ NO1-012A / TRUST-S1

NO1-010A ─ NO1-010B
         └─ NO1-013A
```

## 9. Definition of done for every implementation task

1. Run TSA change-impact before edits and record the affected surface.
2. Use focused TSA navigation/health/safety queries instead of blind scanning.
3. Work on a GitFlow-compliant branch/worktree; never push directly to `develop` or `main`.
4. Add exact behavioral tests to existing test files unless the subsystem is genuinely new.
5. Run post-edit change-impact and its reported verification command.
6. For Python changes, run focused coverage and the patch-coverage gate.
7. Update codemaps in the same commit when a guarded registry changes.
8. Preserve locked defaults: JSON for both MCP and CLI, stderr diagnostics, project-root behavior.
9. Record failures and unfavorable benchmark results; never weaken a gate to create a headline.
10. Produce a concise dogfood feedback record for project memory or the final handoff.

## 10. Current execution order

NO1-006A completed at `refs/heads/develop` commit `c91b026a9a11d044f1f67fda9e060db45aebd7f3` in [workflow run `31288611024`, attempt `1`](https://github.com/aimasteracc/tree-sitter-analyzer/actions/runs/31288611024/attempts/1). One exact wheel (`sha256:c1cb3520542fd14dad60ddec55dfac6afbdaa424e7a4a39d875be1801d98f9e8`) passed native Linux, macOS, and Windows package-to-MCP-first-answer axes. Native Linux and macOS additionally proved real uv `0.10.9` detection, fail-closed behavior with mutable bootstrap disabled, and recovery through the content-bound uv `0.11.0`; Windows honestly records installer recovery as `NOT_APPLICABLE_NO_NATIVE_INSTALLER` with `passed=false` while preserving its real old `uv.exe` and package/MCP evidence. The no-checkout read-only job independently verified all axis bytes, identities, causal sidecars, exact package aggregate (`sha256:04cfdbb96643c7ea34f90707fdf9f3778513c763632c3946ce5532cba25635af`), exact outdated aggregate (`sha256:a110bfc1e423b9c1961f0d02cd2ab676c425b001c23d2449921add73e2860e45`), and deterministic run-bound sandboxes before the tiny OIDC job issued attestations for all three subjects. Pinned post-run verification records and durable evidence are preserved in [`rfcs/evidence/no1-006a/c91b026a9a11d044f1f67fda9e060db45aebd7f3-attempt-1/`](evidence/no1-006a/c91b026a9a11d044f1f67fda9e060db45aebd7f3-attempt-1/). This evidence proves the attested source ref and run identity, not a branch-protection snapshot. Automatic mutable bootstrap remains explicitly unqualified, and this completion does not upgrade canary, benchmark, comparison, cross-file E2E, or public-claim evidence.

1. Prioritize TRUST-C1/T1, then TRUST-I1 under the 2026-09-07 execution gates. NO1-006B dependency-split baseline work may proceed independently. NO1-012A is the TRUST-S1 performance/SLO work package and waits for TRUST-I1; before that gate, only non-measurement report-schema infrastructure may proceed. None of these tasks upgrades canary, benchmark, comparison, cross-file E2E, or public-claim evidence.
2. Establish and record a distinct reproducible RFC-0021 E1 install/smoke qualification, then complete NO1-008A's model-free seven-repository setup; any setup failure blocks every model-backed phase.
3. Implement and independently review NO1-003D's production dispatcher without invoking a model.
4. Only after NO1-003D, NO1-008A, human budget, signed attestation, and judge gates pass, execute NO1-003C as a bounded E0 canary; retain failures and do not relabel it E1.
5. Qualify NO1-009A only at the second competitor's install/conformance boundary; adding it to comparisons requires a separately reviewed RFC-0021 v2 experiment.
6. Proceed with NO1-006B/010A/012A only through their ledger prerequisites and exact native/contract qualification gates; E0–E3 cannot emit public leadership wording.

## 11. Recorded wants — evidenced, unscheduled

Moved here from a draft of [RFC-0029](0029-does-this-test-constrain-this-code.md)
so they are not frozen inside an RFC that is not about them (`README.md`: a
merged RFC is immutable except for status and clarifications). Evidence is
preserved verbatim from the 2026-08-19/20 session; both are **E0** and neither
has a scheduled wave yet. Their priority should be measured against what
RFC-0029 actually removes once it ships, rather than guessed now.

### 11.1 Finding clustering across a session

Five line-ending defects were found in one day — `ImportGraph`
normpath-vs-POSIX cache keys, a corpus digest on an unpinned `*.jsonl`,
`detect-secrets` rewriting 67 paths to backslashes, repeated CRLF commit churn,
and a CI retry path that could never fire — each reported separately, hours
apart, by a different reviewer. The class was named on the fifth. Clustering
would have compressed five point fixes into one invariant.

Substrate: `decision_journal.py` exists and is reachable from a CLI flag.
Measured 2026-08-19: `.ast-cache/decision_journal.db` **does exist** (created
11:03, gitignored, so per-checkout) and its `decision` table holds **0 rows**.
The conclusion "the substrate has never been used" is correct; the earlier
evidence for it ("the database does not exist") was wrong, and "exists with 0
rows" is the stronger evidence — a file that was created and never written to is
proof of a wired-but-unused path, whereas a missing file is also consistent with
the feature never having been reachable.

### 11.2 Belief provenance

Three false beliefs were held with confidence and propagated in one day:

1. that 23 `mypy` errors were technical debt — they are a Windows host artifact
   (`mypy --platform linux` is clean), and three agents were instructed to
   preserve a debt that did not exist;
2. that an 1880-line module was pre-existing — it was introduced by the PR under
   review;
3. that a benchmark block was spec-level — false for two of seven gates.

RFC-0027 L9 records *predictions*; nothing records *beliefs* or where they came
from. A belief that is never written down cannot be falsified later, which is the
same failure mode CLAUDE.md §11 names for non-functional claims.
