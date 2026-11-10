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
| **P1-4 change-impact 测试选择召回** | **撤回：测量比较的是「被截断的可见列表」，选择本身包含那些文件**（`tests_to_run_omitted_count: 13`） | §4 / 第 49 轮 |
| P2 系列（hotspot 档位 / index-meta / agent-summary-only / codemap parity） | 已修 | §3 |
| §11 no-op 索引成本 | 已修：9.08 s → **0.66–0.86 s**（记录生命周期，不动 #1253） | §11 第 26–29 轮 |
| └ **复测（2026-11-10，第 64 轮）** | 改动累积后首次 6.66 s、紧随的 no-op **0.72 s**；记录仍在（`tsa.converged_refresh`，extractor_version 55） | 本轮实测 |
| §12 agent 原生原语（etag/304/delta/capabilities/absence/UQL hint） | 全部落地，CLI+MCP 双面 | §12 |
| RFC-0044 缺席证书 | 五种全部实现，status = implemented | `rfcs/0044-…` |

唯一被记录为「遗留」的 P1-4，**在第 49 轮被证明是测量错误并撤回**（见下）。

### P1-4 的完整经过（保留，因为它是这个仓库最重要的教训之一）

| 轮次 | 动作 | 结果 |
|---|---|---|
| 1 | 记录「change-impact 漏 4/8 个直接引用测试」 | 依据：可见 `tests_to_run` 与 grep 对比 |
| 42 | 加「文本引用」advisory 通道 | 能列出「图没选中」的文件 |
| 43 | 给通道加证据分级（import / mention） | import 级优先 |
| 44–47 | 20 个模块抽样统计精度 | 20/20 真阳性 |
| 48 | 尝试并入选择 | 候选数 0，发现前提可疑 |
| 49 | 用 `--change-impact-include-details` 复测 | **选择本身包含那些文件；43 选中 / 30 可见 / 13 被截断** |

**结论**：P1-4 不存在召回缺陷，是**把显示截断当成缺失**。响应一直带着
`tests_to_run_omitted_count`，是我没有读它。

因此第 50 轮**移除了那条文本通道**：在默认配置（`include_details=false`）下，它会对
「其实已被选中、只是没显示」的文件说「不在依赖图的选择里」——这不是保险，而是**制造新的
不实陈述**，与本分支的目标相反。它留下的唯一东西是第 28 条 AI 教训与这段经过记录。

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

### 12.2 增量答案（`--previous-entries-json`）

比 304 更进一步：不是「没变」，而是「**变在哪**」。只返回新增/消失的调用方条目
（`added[] / removed[] / unchanged_count`），像 `git diff` 之于 `cat`。对 agent 的长会话尤其关键：
它已经在上下文里持有上一版答案，只想要 delta。

**已落地（第 12 轮，`nav action=callers` 的无状态增量；CLI 旗标是 `--previous-entries-json`）**：请求带 `previous_entries`（上一次答案的
条目，agent 本来就在上下文里），服务端按 `(file, line, call_site_line, name)` 对齐后回
`{delta: {added, removed, unchanged_count}}`；作用域过期时一律回完整答案。实测新增一个调用方并重建
索引后：`added=1, unchanged=1`，响应里没有 `callers` 列表。

### 12.3 成本预检（`--capabilities FACADE.ACTION`）

本仓库已经证明成本可以跨两个数量级（`--uql` 1.2 s vs 47 s）。agent 需要**先问价**，
但**没有** `--cost "<query>"` 这种按查询估算的旗标——那是另一个设计（需要按查询复杂度建模）。

现有的是**按动作**的预检，这也是诚实的那一半：

```
tsa --capabilities nav.callers
→ {tier: "indexed", cost_class: "indexed", preconditions: [], index_present: true, precondition_met: true}
```

- `tier` / `cost_class`：`instant`（~毫秒级、不需要索引）还是 `indexed`（需要索引，可能秒级）；
- `precondition_met`：前置条件是否满足（例如索引在不在），**失败即拒绝**，不会跑到一半才报错；
- `example`：一条可直接复制的调用样例。

**修订（2026-11-10，第 67 轮）**：本节此前写有 `tsa --cost "symbol('main').callees()"`
返回 `{tier, estimate_ms, files_scanned, may_exceed_budget}`——该旗标与这些字段**都不存在**。
按查询估算仍未实现；在它存在之前，agent 应使用上面的按动作预检。

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

agent 常把答案缓存到下一轮。`callers` 现在返回
`expires_when: {files: [...], index_generation: "…"}`：`files` 是**声明文件 + 每个调用方文件**
（这个答案的全部输入），`index_generation` 是读到的活动世代（读不到时为 `null`，此时只能靠 files 判断）。

agent 只要这几条文件没动、世代没变，就可以**不重问**继续复用上一轮答案。

> 修订（2026-11-10，第 66 轮）：本节此前描述的字段**并不存在**——文档先于实现。
> 现在它存在且有测试；这也是「撤回声明要写回原处」的一个实例。

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

### 13.1 复测（2026-11-10，第 65 轮，同一台机器，索引已收敛）

同一工作流重跑，记录**本轮**数字（上表是第 35 轮，间隔约 30 个提交）：

| 步骤 | 结果 | 耗时 | 载荷 |
|---|---|---|---|
| 1. 预检 | `indexed` / `precondition_met: true` | 269 ms | 440 B |
| 2. 首问 | 4 个调用方 + `answer_etag` | 929 ms | 4006 B |
| 3. 同 etag 重问 | `unchanged: true`（5–7 个键） | 874 ms | **440 B**（降 9.1×） |
| 4. delta 重问 | `unchanged_count: 4` | 872 ms | 596 B |

**怎么读（否则会得出错误结论）**：CLI 单次调用约 0.8 s 是**进程启动**，不是分析——所以「304 也要 874 ms」
并不说明省不了时间。真正的收益是**载荷**（4006 → 440 B）与 **MCP 常驻进程内避免的重复计算**；
而第 2 步从 7.04 s 降到 0.93 s，说明**收敛记录（§11）才是问答成本的主项**。


## 14. 第 82 轮发现（未修，已量化）：大 PR 的 focused 命令可达 11 KB

用 TSA 自己分析本 PR（`--change-impact --change-impact-mode branch`）：

| 指标 | 值 |
|---|---|
| 改动文件 | 75 |
| 受影响 | 932 |
| 选中测试 | 236 |
| **focused 命令** | **11,308 字符 / 12 批** |
| 风险 | high |

命令本身是**正确的**（每批 ≤6000 字符，覆盖全部 236 个测试），但对 agent 不友好——它要一次性
吞下 11 KB 才能开始跑。

我尝试在默认（summary-only）响应里加 `focused_test_batch_count` / `focused_test_command_bytes`
两个整数，被仓库**已有的两条契约**挡下：
`test_agent_summary_only_response_omits_noisy_details`（默认载荷键集固定）与
`test_realistic_diff_default_reply_size_is_pinned`（默认回复字节数钉死）。**这两个字段已回滚。**

正确方向不是加字段，而是把 `focused_test_command` 变成**结构化批次**
（`focused_test_commands: [...]`），让 agent 逐条执行；这需要重写 `join_verification_steps`
的输出形状并重新钉死尺寸契约，属于独立一轮的工作——不在一个已验证可合并的 PR 结尾硬塞。
