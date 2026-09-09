# RFC-0033: Native search independence

- **Status**: draft — 内部去依赖已授权；公开接口删除等待明确主版本裁决
- **Created**: 2026-09-09
- **Tracking**: 用户发布准备任务；内部扫描实现 PR #1423
- **Affected source paths**: `source_lines.py`, `mcp/tools/{trace_impact_tool,search_facade,project_facade,modification_guard_tool}.py`, `mcp/utils/project_index/`, `cli/`, 安装脚本与测试

> 2026-09-09 用户后续允许重新评估适当位置的 rg/fd。[RFC-0034](0034-optional-search-backend-qualification.md) 提议更新可选后端取舍，并将下述“内部不启动外部搜索进程”“无 rg/fd 安装步骤”的验收限定于默认核心路径与核心安装；其接受前仍沿用原约束。原生独立运行、安全边界和公开接口迁移门槛保留。

## Summary

TSA 的索引发现改用进程内实现，实时源码核验使用自带 Python 工作进程隔离阻塞读取。公开接口、缓存及安装步骤的删除按下述主版本门槛推进。符号、AST、调用图和可选语义索引继续承担候选定位；实时文本核验用于核对当前源码。

## Motivation

删除部分薄包装后，`search.batch`、`project.files`、`project.tools`、内部 trace 和项目文件发现仍依赖外部程序。安装、工具指南和测试跳过条件掩盖了这些残留。发布前必须同时清理运行时与用户可见契约。

## Detailed design

### 原生扫描

- 文件发现使用标准库和项目已有的 `pathspec`，不启动外部搜索进程。
- 遵守每层 `.gitignore`、`.ignore`、`.rgignore`；保留后者仅用于已有忽略配置兼容。
- 每个 MCP 扫描根先经过现有 `resolve_and_validate_directory_path` 项目边界验证；空根分量直接拒绝，不扩展为工作目录。
- 排除隐藏路径、构建/依赖缓存目录、符号链接与非普通文件；规范化祖先路径别名，重叠扫描根去重。
- 不承诺复刻 fd 的全套参数、全局忽略配置或所有隐藏文件策略。
- 符号核验使用固定字面量、智能大小写和可选单词边界，保留原文件行号。
- 命中计数独立于最多 10,000 行的返回展示；截断后提示缩小扫描根。工作进程 JSON 响应最多 32 MiB，超过上限返回错误。二进制文件不作为源码处理。
- 发现预算为 200,000 个目录项；扫描预算为单文件 10 MiB、总计 512 MiB、100,000 个命中行，扫描器内部检查默认 5 秒截止时间。
- 目录/文件读取失败、单文件过大或预算耗尽返回失败，不能把部分扫描报告为完整成功。实时 trace 由隔离 Python 工作进程执行；父进程超时后终止并限时回收该工作进程，回收失败也显式报错。进程内文件发现本身仍只有协作式截止检查。
- trace 的调用分类仍是启发式，文本命中不等同于 AST 直接调用边；修改守卫保留两类计数的区别。

### 公开表面移除与迁移

依照 [既定主版本政策](ROADMAP-no1-agent-trust.md#用户已裁决的边界)，候选迁移版本为 **v2.0.0**，尚待用户明确裁决。本 RFC 不把“去掉依赖”解释为绕过已发布接口的版本门槛。内部替换可先合入 develop；公开 CLI/MCP/Python 接口删除 PR 在具名主版本裁决前保持待审，不合并，不创建或推送会自动发布的 release 分支。发布前还须完成迁移说明和全部验收项。

| 移除 | 迁移 |
|---|---|
| `search action=batch` | 已知符号用 `search action=symbol`；结构表达式用 `search action=query` |
| `project action=files` | 索引结构用 `structure action=sitemap`；任意实时文件发现由宿主或有界原生文件操作完成 |
| `project action=tools` | 安装诊断用 doctor；索引诊断用 `index action=status` |
| `list-files` 入口 | 同上，不再提供 fd 参数转发 |
| `ripgrep_occurrences` | 守卫响应改为 `source_occurrences`，`count_unit` 同步改名 |

`map_structure` / `discover_files` 指向索引 sitemap，因此要求先建立 AST 索引；不能把它描述成实时文件系统搜索。索引缺失/过期不能证明源码中没有某个符号。检索指南明确区分候选发现、排序与源码核验。

不引入新的语义后端，也不改变索引存储或新鲜度认证协议。删除旧工具的专用缓存、参数构造器、诊断与安装说明。测试先逐项登记行为、输入分区、失败见证及保留位置；仅退役接口专属行为随接口删除，混合场景仍有的独立职责迁移到现有测试模块。不得通过新增 skip 隐藏这些职责。

## Three-Surface impact (CLI ↔ MCP parity)

同步删除 `--batch-search`、`--batch-search-queries-json`、`--check-tools` 和 `list-files` console script，以及对应 MCP action/legacy mapping。主 CLI 的长选项从 356 变为 353，8 个公共门面保持不变，action 从 87 变为 84。

`--trace-impact --trace-impact-symbol NAME` 与 `nav action=trace symbol=NAME` 继续对应；所有返回使用 JSON。更新 CLI/MCP codemap、生成的 action 文档和中英日西安装说明。

## Drawbacks and alternatives

不承诺与 rg/fd 的吞吐或全参数等价。隐藏文件策略也并非完全相同。性能比较必须区分冷构建、热索引查询与实时源码核验，不能用其中一种延迟替代另一种，更不能由局部扫描直接推断端到端 agent 用时。本 RFC 不将临时本机测量作为性能承诺。

保留可选 rg/fd 加速会继续维持两套运行路径，与用户的去依赖方向不符。引入 Rust 搜索扩展会增加构建和分发成本，暂不采用。索引查询优先减少反复全仓库扫描，但不能用热索引延迟替代冷构建与实时核验成本。

## Prior art

[zvec-grep 的检索策略](https://github.com/zvec-ai/zvec-grep/blob/6fa85a8e28c0b5a0f651c27f09f0247627c5d5c3/src/client/search-policy.ts) 区分最终一致与等待新鲜索引；[检索管线](https://github.com/zvec-ai/zvec-grep/blob/6fa85a8e28c0b5a0f651c27f09f0247627c5d5c3/src/engine/pipeline/search-index.ts) 组合候选检索。借鉴候选发现、精确核验和显式新鲜度的分工；该项目自身仍使用 ripgrep，不作为去依赖实现直接引入。

## Test plan (RED-first)

先锁定不依赖外部程序的行为：真实 trace 测试只允许项目自带 Python 工作进程，项目发现测试禁止外部进程；旧 rg/fd 实现在这些约束下应失败；新扫描器测试覆盖嵌套忽略、重叠根、符号链接、大小写、Unicode、行号、计数和预算错误。

删除入口时，先更新精确 action/flag 契约及旧 action 拒绝用例；真实索引别名测试禁止外部进程，并验证命中内容而非仅比较两个失败响应。移除 `requires_fd` / `requires_ripgrep` 跳过机制，执行快速门、完整本地命令和完整 OS/Python CI。Python 改动运行局部覆盖率及 patch gate。

### 退役测试逐项清单

清单固定原始提交 `5a2cd86aefd49be89efeb87ee693432fcae1d973`，由 TSA 的 `--query-key functions --format json` 提取旧/新函数集合后逐项归类：
[第 1 部分](evidence/0033-retired-tests-1.jsonl)、[第 2 部分](evidence/0033-retired-tests-2.jsonl)、[第 3 部分](evidence/0033-retired-tests-3.jsonl)。这是函数级迁移登记，不是 pytest 参数展开后的测试数量。每行包含行为、固定提交的输入分区来源、失败见证、退役理由与保留位置。源链接中的装饰器、fixture 和 helper 也是输入契约的一部分；不能只根据函数名判断重复。

`retained_at` 表示删除候选补丁应保留的位置，并不声称该补丁已合入 develop。公开接口删除 PR 合并前必须核对这些位置并执行相应测试。专属包装器、参数转发、输出格式和缓存契约明确退役，不能用“新扫描器有测试”笼统宣称等价覆盖。

混合场景的独立职责按下列方式保留：

- 项目复杂度：原两份 Java 文件、平均复杂度及逐文件结果，迁入现有 User Story 4 模块的独立测试。
- 项目刷新：创建新文件后重新设置同一项目根，精确验证文件数从四变五。
- 并发读取：同时读取源码与项目统计，核对完整源码和文件总数。
- 安全边界：保留原恶意路径、Unix/Windows 绝对路径及项目父目录输入，改验原生 trace 边界；临时父目录也不得放行。
- 未退役别名：保留结构分析别名的真实调用、未知别名错误及索引别名结果验证。
- 通用文件输出：既有 query/read 测试继续验证保存与抑制输出；旧列表专属 count/results 格式不承诺兼容。

清单核对命令：`python -c 'import json,pathlib; rows=[json.loads(line) for p in sorted(pathlib.Path("rfcs/evidence").glob("0033-retired-tests-*.jsonl")) for line in p.read_text().splitlines()]; assert len(rows)==537; assert len({r["original_nodeid"] for r in rows})==537; assert all(r["behavior"] and r["input_partitions"] and r["failure_witness"] and r["retained_at"] for r in rows)'`。该命令检查登记完整性，不替代运行行为测试或审阅原始断言。

## Acceptance criteria

- [ ] 公开接口删除对应的具名主版本裁决完成
- [ ] 内部文件发现与 trace 不启动外部搜索进程
- [ ] 旧 MCP action、CLI 参数、console script 及死代码全部移除
- [ ] 无 rg/fd 安装步骤或缺少它们而跳过测试的机制
- [ ] CLI↔MCP parity 与 codemap 自检通过
- [ ] 迁移说明、安装文档与内置检索 skill 一致
- [ ] 完整本地测试及跨平台 CI 通过

## Deferred

通用正则搜索接口、全仓库扫描吞吐优化、宿主自身搜索实现替换，以及新的语义检索依赖均不属于本次发布准备。
