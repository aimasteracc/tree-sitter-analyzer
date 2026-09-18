# Roadmap — Agent-Native Workbench

- **Status:** active proposal
- **Design:** [RFC-0036](0036-agent-native-core-workflow.md)
- **Mission:** 让 TSA 成为 Agent 在结构化检索、编辑决策和验证闭环中的默认工具。
- **North star:** 在不降低正确性的前提下，提高真实任务成功率并减少总调用轮数、
  恢复次数和端到端等待时间。

## Product position

TSA 的优势不是替代所有 grep 或文件编辑。Agent 已知一个代码实体、但不知道它的
结构、关系、影响或验证方式时，应自然选择 TSA。任意文本、配置、日志和未知语言
继续由通用 grep 处理，写入继续由宿主 edit 工具处理。

## Current baseline — 2026-09-18

| Signal | Observed baseline | Product implication |
|---|---:|---|
| MCP surface | 8 facades / 84 business actions | 能力足够，优先降低选择成本 |
| CLI surface | 356 flags | 不能要求 Agent 记住整个表面 |
| Tool definitions | 36,469 JSON bytes | 需要按 action 渐进发现 |
| Full native index | 31.33 s, ~98 KiB response | 构建必须后台化且默认只给摘要 |
| Context query | 2.35 s, ~15 KiB response | 高频结果要有预算与去重 |
| Stale symbol probe | stale coordinates + live body, INFO | 编辑入口必须统一源码证据 |
| Parameter typo probe | `limt` silently dropped | 首先修复错误成功 |

以上均为一次本机诊断，不是 SLA 或总体分位数。

## Milestone 0 — Trust the call

**Outcome:** Agent 可以相信所传参数确实生效。

- direct inner route 对未知、拼错、sibling 参数返回 `INVALID_ARGUMENT`；
- 错误包含 `invalid_arguments`、`allowed_arguments`、`suggestions` 和 next step；
- bespoke route 形成 schema 迁移清单；
- agent envelope 文档与 JSON-only 运行时对账；
- MCP 与 CLI 未知参数行为具备契约测试。

**Exit:** 真实 8 facade 场景无静默参数丢弃；兼容例外逐条列出，不能用总 catch
掩盖。当前 PR 只交付 direct route 的第一条 Red-Green 切片。

## Milestone 1 — Learn five moves

**Outcome:** Agent 不加载 84 个业务 action 的完整说明即可完成常见编辑。

- 发布五步 core profile：symbol → outline → pulse → impact → verify；
- 单 action schema 可按需机器读取；
- search 返回规范 target，后续 action 直接消费；
- 默认正文去重，扩大范围需显式请求；
- 对同名实体返回候选，不自动选定。

**Exit:** 代表性 transcript 的参数恢复轮数和工具调用数相对当前基线下降；门面和
action 总数不增加。

## Milestone 2 — Trust every read

**Outcome:** 所有用于编辑判断的结果都说明自己是否当前、是否完整。

- search/resolve/pulse 共享 snapshot owner 和 `source_evidence`；
- stale 坐标不能与当前正文拼成成功响应；
- `fresh NOT_FOUND` 与 missing/stale/unknown 分开；
- `total_count=null` 表示无法证明总量；continuation 可重放；
- 文件级直接解析作为诚实 fallback。

**Exit:** 真实改名、等长改写、增删调用者、并发写入和损坏索引测试全部 fail
closed；Linux、macOS、Windows 给出经过验证的平台语义。

## Milestone 3 — Hide index mechanics

**Outcome:** 常见调用不要求 Agent 手工管理索引。

- 索引构建默认返回有界摘要；
- 常驻认证只在事件序列无缺口、无待写入且 scope 完整时复用；
- 缺少可信读屏障时回退到认证路径，不猜 fresh；
- 记录冷启动、暖查询、保存后恢复和批次复用的端到端成本；
- 可选 `rg` / `fd` 后端只加速候选枚举，原生实现保持基线。

**Exit:** 预注册性能门槛通过，同时 stale/concurrency corpus 无回退。只提高速度但
降低证据强度不算完成。

## Milestone 4 — Close the edit loop

**Outcome:** TSA 把编辑前判断与编辑后事实连接起来。

- impact 返回有来源的最小验证计划、未知风险和 stop condition；
- host 完成 patch 后，verify 比较符号/签名/关系变化；
- 计划与当前 diff 不一致时返回 `PLAN_CHANGED`；
- baseline failure、timeout 和 skipped test 保留在结果中；
- patch allowlist 和项目根安全边界覆盖完整工作流。

**Exit:** NO1-010B 首条纵向任务从定位到终态 oracle PASS，非 allowed 文件 digest
不变；随后扩展到 refactor、migration、test-selection 和失败场景。

## Milestone 5 — Earn default status

**Outcome:** 用真实 Agent 任务证明 TSA 值得默认选择。

发布资格必须同时记录：

- 终态 oracle PASS 比例；
- 错误编辑和越界写入数量；
- 工具调用轮数、参数恢复轮数和端到端等待时间；
- stale/unknown/partial 处理是否正确；
- TSA-first 与 grep/read 基线的同任务结果。

阈值在运行 corpus 前注册。未达到时继续保留为可选结构工具，不使用“标准”“默认”
或“No.1”公开表述。

## Conditional milestone — Agent cycle coordinator

仓库已有 internal-only 的 `tree_sitter_analyzer.task` 组合内核。先用 paired live-Agent
A/B 比较当前 8-facade 菜单与候选协调入口，固定模型、corpus、随机化、重复次数和
判分规则。静态菜单字节或 token 估计不能替代真实运行。

只有 discovery、终态成功率、turn 和输入输出成本达到预注册门槛，才另案公开
`understand / plan_change / assess_change` transport。协调层复用现有 primitive 与
diff snapshot；普通写入留给宿主，测试执行保持显式 `edit.verify`，CLI 在单次进程
内完成 snapshot 生产、消费和释放。

## Test and CI ladder

| Layer | Purpose | Command / gate |
|---|---|---|
| Red-Green | 单一行为 | change-impact 返回的 focused command |
| Patch | 新增可执行行均被有效测试 | focused coverage + `check_patch_coverage.py` |
| Quick | 常规回归，5 分钟内 | `uv run pytest -q` |
| PR | 代表性跨平台矩阵 | reusable-test PR profile + MCP smoke |
| Nightly/manual | corpus、mutation、benchmark、故障注入 | 专用路由 |
| Release | 全平台、全 corpus、构建和文档契约 | full profile |

测试必须断言行为值和终态 oracle，不接受只检查字段存在、只跑 suite、或只证明
conformance 而没有证明 Agent 任务价值的假绿。

## Immediate queue

1. [x] 合入 direct route 参数严格性第一切片。
2. [x] 清理 agent envelope 中退役的 TOON 描述。
3. [x] 给五个核心 action 提供按需 schema 响应，不增加顶层工具或业务动作。
4. [x] 让 symbol search/resolve 复用 Pulse 的源码认证与 freshness 错误模型；认证命中
   绑定同一个 snapshot owner，未认证空结果不能宣称 `NOT_FOUND`，stale/concurrent
   路径 fail closed。
5. [x] 建立第一条 NO1-010B E0 reference transcript harness：真实执行
   `index.full → search.symbol → structure.outline → edit.safe → host edit →`
   `edit.impact → edit.verify → registered verification → oracle`，并验证非 allowed
   文件摘要不变。运行命令：
   `uv run python -m tree_sitter_analyzer.no1_010b --corpus benchmarks/no1_010b/corpus.jsonl --reference-transcript-task no1-010b/0001-bugfix-dispatch-unknown-route`。
6. [x] 把 transcript 扩展到 refactor、migration、test-selection 和失败场景：0003
   验证跨文件重构，0004 精确匹配 `selected_tests`，0007 验证废弃调用迁移，0006
   保留 `FAIL / VERIFICATION_FAILED`。完成 RFC-0026 B1 沙箱前保持
   `E0 / REFERENCE_ONLY`，不发布 VCSR 或默认工具声明。
7. [x] 在正确性稳定后优化索引冷启动、热查询和保存恢复。

### Performance checkpoint — 2026-09-18 E0

同一台 macOS 主机、同一工作树和相同三项可选语法排除条件下，全量索引从
35.45 秒降至 28.073 秒（约 20.8%）；其中 AST 阶段从 30.781 秒降至
23.182 秒（约 24.7%）。优化把项目类方法的唯一性与类归属建立为一次性反向索引，
不再为每条调用边遍历全项目类方法。全量重建已清空边表，因此显式跳过逐文件失效
扫描，避免把增量正确性修复带入冷启动热路径。

已发布索引上的 `codegraph-query resolve_callee` 以独立进程连续运行 5 次，中位数为
0.152 秒，5 次都返回 20 个结果。单文件保存与恢复各执行一次完整增量发布，端到端
分别为 11.017 秒和 11.381 秒；两次均只重建 1 个文件，`backfill_errors=0`、
`completeness=complete`、`published=true`，恢复后源码摘要与原值一致。

保存路径同时补齐两个正确性条件：弱 cross-file 候选不能覆盖已认证的文件与符号
绑定；新增同名方法会撤销既有唯一绑定，删除后可重新绑定并恢复调用图认证。这些是
单机 E0 诊断，不构成跨平台 SLA 或公开性能声明；后续发布仍由 benchmark、并发与
stale corpus 门禁决定。
