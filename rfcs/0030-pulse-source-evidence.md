# RFC-0030: Pulse 的源码版本证据

- **Status**: draft
- **Author(s)**: @aimasteracc
- **Created**: 2026-09-08
- **Last updated**: 2026-09-08
- **Tracking issue**: TRUST-C1 / TRUST-I1，见 `ROADMAP-no1-agent-trust.md`
- **Affected source paths**:
  - `tree_sitter_analyzer/api/pulse.py`
  - `tree_sitter_analyzer/api/pulse_evidence.py`
  - `tree_sitter_analyzer/mcp/tools/pulse_tool.py`
  - `tree_sitter_analyzer/cli/commands/mcp_commands/_specs_pulse.py`
  - `tests/unit/api/test_pulse.py`
  - `tests/unit/mcp/tools/test_pulse_tool.py`
  - `tests/unit/cli/test_mcp_commands.py`

## Summary

Pulse 的单条与批量项目查询必须在同一份源码认证快照上读取，并把认证证据
放在不可被格式精简或 token 预算裁掉的外层。没有当前源码证据时，明确返回
stale、missing 或 unknown，不返回冒充当前结果的旧符号或确定性“未找到”。
本 RFC 细化 RFC-0025 的认证消费者，不声称已经实现常驻认证或即时性能目标。

## Motivation

`develop@87002488` 的两文件实测：完整索引后，把 `tsa_probe_leaf` 改名为
`tsa_probe_leaf_v2`，旧名称的 Pulse 仍返回 `success=true` 和旧调用者；新名称
则报不存在。显式增量同步后恢复。SQL SAVEPOINT 保证数据库内一致，却不能
证明数据库对应当前源码。Agent 无法区分输入拼写错误与证据过期。

同样，只检查目标文件 hash 不足够：目标没变，新增或删除的调用者也会改变
调用关系。批次内每个目标各自开保存点，还可能读到不同索引版本。

## Detailed design

### 认证与数据读取必须共用所有者

复用 `index_snapshot` 的快照租约、连接获取、资源预算和源码再验证。
禁止“先调用 status，再用另一个 ASTCache 连接查数据”：两步之间可以发生写入。
项目级消费者只接受 complete、非空 source generation、非空 snapshot ID 的
认证能力；partial 只证明可读，不能证明完整或当前。

1. 参数校验先执行。空批次无索引访问，返回零结果；不能捏造 fresh。
2. 有效非空请求获取一个认证租约。没有索引时不创建 `.ast-cache`，不自动建库。
3. 单条或整批次通过该租约的连接调用现有 `query_pulse`，复用 SQL 和模型。
4. 在结果发布前，重新核验源码 generation。失败时丢弃整个结果，不泄露部分
   旧结果、not-found 或前一目标的成功。异常必须关闭连接获取上下文并释放租约。
5. 成功响应携带同一 snapshot ID 与 generation。批次每个目标共享外层证据，
   不能以多个不同 generation 的结果拼出“完整批次”。

认证只覆盖声明的 source scope，不能宣称未索引语言、目录或动态绑定已精确。
Git 热度、可选 LSP 富化等不同来源也不能因源码 fresh 就被升级为精确或实时。

### 返回契约

外层新增 `source_evidence`，所有 JSON 展示格式相同，预算只裁剪结果内容：

```json
{
  "success": true,
  "source_evidence": {
    "freshness": "fresh",
    "snapshot_id": "owner-issued-id",
    "source_generation": "owner-issued-generation",
    "reason": null
  },
  "result": {}
}
```

`fresh` 的含义是该次查询末尾的源码再验证通过；不是结果返回后源码永不变化。
失败保持 `success=false`，增加稳定 `error_code` 和相同的证据结构，无 `result`
或 `results` 数据。错误分类采用明确集合，未知错误绝不能降级成 fresh：

| 条件 | freshness | reason / error_code |
|---|---|---|
| 未设置项目或索引不存在 | missing | 复用 MISSING_PROJECT_ROOT / MISSING_INDEX |
| 确定的源码/索引或 generation 不匹配 | stale | 保留源码认证器的稳定原因 |
| 不完整、预算耗尽、损坏、平台无法认证、并发写入 | unknown | 保留已知原因，其他映射 INDEX_SNAPSHOT_UNKNOWN |
| 已认证快照中确实没有目标 | fresh | SYMBOL_NOT_FOUND；success=false |

获得认证后，某个目标的歧义或查询错误可维持原有 per-target 错误语义，前提是
末尾源码验证通过；认证失败是整批次失败，不是个别目标失败。错误计数不得把
整个认证失败伪装为每个符号各自不存在。

### Python API

保留 `query_pulse(conn, ...)` 的已发布 SQL 级用法与返回类型；其文档明确说明
它不认证当前磁盘源码。项目查询通过共享的 `pulse_evidence` 读取上下文承载，
MCP 单条与批量消费者共同调用，不新增第二份 SQL、索引或符号模型。

```python
with certified_pulse_connection(project_root) as (connection, evidence):
    # 上下文正常退出前检查当前源码；调用者此时才能发布结果。
    result = query_pulse(connection, file_path, symbol_name)
```

上下文必须把末尾检查也包含在异常边界中；不能在 `finally` 中吞掉认证失败。
上下文返回的 evidence 在完整退出之前是候选证据，不能提前流式发送给 Agent。

### 性能与常驻认证

正确性阶段复用既有每次调用认证作为明确的后备路径，记录冷查询、热查询及
批次成本，不把它包装成瞬时热路径。不得为每个批次目标重新认证或复制数据库。
后续常驻认证替换租约获取策略时，仍须满足同一 generation 与失效契约。
只有事件通道健康、无序号缺口、无待处理写入且认证 scope 完整时才能复用；
watcher 重启、事件溢出、根目录切换和外部索引写入必须使其失效。
纯异步“尚未收到事件”不是 fresh 的证明；无法建立读屏障时使用后备认证。

规模热路径验收仍执行 TRUST-S1；每次全仓哈希/全图复制的实现不能通过该门槛。
本 RFC 的正确性阶段通过不解除此性能阻断项。

## Three-Surface impact (CLI ↔ MCP parity)

- CLI `file.py --pulse NAME` 与 MCP `nav action=pulse` 使用同一消费者。
- CLI `--pulse-batch JSON` 与 MCP `nav action=pulse_batch` 使用同一消费者。
- Python SQL API 明示只读数据库语义，共享认证上下文提供项目级证据。
- 不新增顶层工具、CLI 参数或调用者控制的 snapshot/lease 参数，不扩大
  RFC-0022 的 process-local CLI 例外。单次 CLI 调用内部完成获取、读取、释放。
- 源码失败在 CLI 返回非零退出码；stdout 仍是单个 JSON，诊断留在 stderr。

## Drawbacks and alternatives

旧的仅 `index_file` 索引、缺少认证清单的手工数据库会被拒绝；需要完整索引后
再查询。已有快照认证成本可能显著超过 SQL 查询本身，必须单独测量。
默认静默读旧索引被拒绝，因为无法支持编辑决策。仅增加 unknown 标签但继续
把缓存未找到写成确定不存在也被拒绝。仅检查返回路径会漏掉新增调用者，被拒绝。
所有查询默认先同步会修改项目且掩盖过期状态，被拒绝。

## Prior art

本仓库 `index_snapshot` 已有受限租约与查询后再验证；本变更复用这一事实源。
RFC-0025 定义常驻认证及后备认证；RFC-0022 定义 snapshot truth。
本 RFC 不从竞品宣传推导 TSA 的正确性或性能结论。

## Test plan (RED-first)

在已有 Pulse 测试文件增加真实完整索引用例，禁止只 mock freshness 字段：

1. 保存后查询旧名和新名都不能成功或谎报 fresh not-found；同步后新名与调用者正确。
2. 只改调用者、删除调用者、新增调用者均使旧证据失效；目标文件保持不变。
3. 在读取期间或批次两目标间修改源码，整个响应不得发布结果。
4. batch 全部结果共用一个认证能力；数据库更新不能混入另一版本。
5. 缺失索引不产生文件；部分索引、认证超时及损坏均有稳定 unknown 原因。
6. 缺失符号只在当前认证成功时给 SYMBOL_NOT_FOUND；歧义仍不是不存在。
7. 释放路径覆盖查询失败、末尾验证失败、项目切换；不泄漏 registry reader/pin。
8. CLI 与 MCP 对相同真实工作树给出相同 freshness，错误退出与 JSON 均正确。
9. 同进程热查询与整批次记录认证次数和实际成本，不能以 SQL 耗时代替总延迟。

## Acceptance criteria

- [ ] 单条与批量默认读取绑定认证连接，查询后源码验证不可绕过
- [ ] stale/missing/unknown 与 fresh not-found 可区分，预算不移除证据
- [ ] 旧名、新名、增改删调用者、读期间保存的真实测试通过
- [ ] 三平台缺失/不完整/完整索引路径验证，失败不洗白为通过
- [ ] CLI↔MCP parity 与真实 CLI smoke 通过
- [ ] 冷暖及批次成本记录，TRUST-S1 未验证时仍标记性能未达标
- [ ] 文档/CODEMAPS 更新，补丁覆盖率、快速门禁和审查通过

## Deferred and open questions

常驻认证、未保存缓冲区和行业排名仍按上游路线图单独验收。本 RFC 不以
增加证据字段宣称完成整个神经系统。性能阈值沿用预注册测量流程，不在失败后修改。

## 本地实现验证记录（尚未合入）

2026-09-08，`fix/pulse-source-evidence` 基于 `develop@87002488`，macOS /
Python 3.14.3。源码认证消费者已经接入单条与批量工具，CLI 复用同一入口。
193 项 API/工具/CLI/对等/生成文档测试通过；快速门禁 2,024 passed、28 skipped，
25.57 秒；补丁覆盖率无新增可执行漏测；Ruff、MyPy 与 sdist/wheel 构建通过。

真实两文件 CLI：完整索引后 `fresh`；保存改名后旧名、新名均 exit 1 且
`stale/SOURCE_INDEX_MISMATCH`；增量同步后新名及两目标 batch 均 exit 0 且
`fresh`。单次端到端 Pulse 0.137–0.167 秒，batch 0.139 秒，仅小样本诊断。
原生 Windows/Linux、持续事件失效、规模热路径和外部审查尚未完成，不勾选总验收。

### 2026-09-08 规模诊断与 Windows 阻断

macOS / Python 3.14.3，同进程，合成 Python 链式调用语料：每文件一个函数，
除首文件外各导入并调用前一文件。每个规模完整建库后查询末端函数五次。
这是诊断，不是预注册 SLA、真实大仓库或竞品对照。

| 文件数 | 建库秒数 | 查询秒数（全部五次样本） | 中位数秒 | 源码核验次数 | 核验累计秒 |
|---|---|---|---|---|---|
| 100 | 0.8387 | 0.0464 / 0.0339 / 0.0219 / 0.0201 / 0.0214 | 0.0219 | 15 | 0.0903 |
| 1,000 | 1.4334 | 0.1821 / 0.1773 / 0.1757 / 0.1756 / 0.1763 | 0.1763 | 15 | 0.6141 |
| 10,000 | 13.2437 | 1.9192 / 1.8726 / 1.8730 / 1.8947 / 1.8794 | 1.8794 | 15 | 6.8297 |

全部查询返回 fresh，但每次三轮源码核验，规模热路径明显未达标。不能直接
删减核验次数来宣称问题解决；常驻认证替代方案仍须证明事件缺口、外部保存、
重启和读屏障的失效行为。

第一种实验启动方式失败：stdin 脚本达到并行索引阈值后，macOS spawn 无法
导入 `<stdin>`，子进程反复启动失败，实验被中断（exit 130）。确认所有相关
进程退出后改用带主入口保护的真实脚本，才得到表中结果。启动失败单独保留，
不混入成功查询延迟；嵌入式索引的清晰失败诊断另行跟进。

PR #1404 的 Windows Python 3.11 测试已经失败，原因是默认认证器返回
`WAL_PRIVATE_SNAPSHOT_UNSUPPORTED`，而不是测试时序偶发错误。安装资格测试
通过不能证明 Pulse 的 Windows 功能通过。目前保持 draft，禁止把失败改成 skip。
现有 portable constraint snapshot 只接受无非空 WAL 的稳定主库，不能直接
用它替换 WAL 私有快照后宣称平台支持；Windows 路径需要满足源码与数据库身份、
完整 WAL 字节及查询后验证的同一契约，仍是合入阻断项。

本地还补齐了认证错误分类：租约获取、连接获取、查询后验证的权限异常，
单条和批量均返回稳定的 unknown 证据；复用既有 read-existing 错误映射，
未知异常原因映射 INDEX_SNAPSHOT_UNKNOWN，不将异常原文当成协议代码。
