# RFC-0033: Native search independence

- **Status**: accepted — 用户于 2026-09-09 明确要求移除 rg/fd 依赖
- **Created**: 2026-09-09
- **Tracking**: 用户发布准备任务；内部扫描实现 PR #1423
- **Affected source paths**: `source_lines.py`, `mcp/tools/{trace_impact_tool,search_facade,project_facade,modification_guard_tool}.py`, `mcp/utils/project_index/`, `cli/`, 安装脚本与测试

## Summary

TSA 的索引发现与源码核验改用进程内实现，删除仍包装外部 rg/fd 的公开接口、缓存及安装步骤。符号、AST、调用图和可选语义索引继续承担候选定位；实时文本核验用于核对当前源码。

## Motivation

删除部分薄包装后，`search.batch`、`project.files`、`project.tools`、内部 trace 和项目文件发现仍依赖外部程序。安装、工具指南和测试跳过条件掩盖了这些残留。发布前必须同时清理运行时与用户可见契约。

## Detailed design

### 原生扫描

- 文件发现使用标准库和项目已有的 `pathspec`，不启动外部搜索进程。
- 遵守每层 `.gitignore`、`.ignore`、`.rgignore`；保留后者仅用于已有忽略配置兼容。
- 排除隐藏路径、构建/依赖缓存目录、符号链接与非普通文件；重叠扫描根去重。
- 不承诺复刻 fd 的全套参数、全局忽略配置或所有隐藏文件策略。
- 符号核验使用固定字面量、智能大小写和可选单词边界，保留原文件行号。
- 命中计数独立于返回展示条数。二进制文件不作为源码处理。
- 发现预算为 200,000 个目录项；扫描预算为单文件 10 MiB、总计 512 MiB、100,000 个命中行，默认检查 5 秒软截止时间。
- 目录/文件读取失败、单文件过大或预算耗尽返回失败，不能把部分扫描报告为完整成功。软截止检查不等同于对阻塞文件系统 I/O 的硬时限保证。
- trace 的调用分类仍是启发式，文本命中不等同于 AST 直接调用边；修改守卫保留两类计数的区别。

### 公开表面移除与迁移

| 移除 | 迁移 |
|---|---|
| `search action=batch` | 已知符号用 `search action=symbol`；结构表达式用 `search action=query` |
| `project action=files` | 索引结构用 `structure action=sitemap`；任意实时文件发现由宿主或有界原生文件操作完成 |
| `project action=tools` | 安装诊断用 doctor；索引诊断用 `index action=status` |
| `list-files` 入口 | 同上，不再提供 fd 参数转发 |
| `ripgrep_occurrences` | 守卫响应改为 `source_occurrences`，`count_unit` 同步改名 |

`map_structure` / `discover_files` 指向索引 sitemap，因此要求先建立 AST 索引；不能把它描述成实时文件系统搜索。索引缺失/过期不能证明源码中没有某个符号。检索指南明确区分候选发现、排序与源码核验。

不引入新的语义后端，也不改变索引存储或新鲜度认证协议。删除旧工具的专用缓存、参数构造器、诊断、测试与安装说明；已退役测试不再通过跳过而保留。

## Three-Surface impact (CLI ↔ MCP parity)

同步删除 `--batch-search`、`--batch-search-queries-json`、`--check-tools` 和 `list-files` console script，以及对应 MCP action/legacy mapping。主 CLI 的长选项从 356 变为 353，8 个公共门面保持不变，action 从 87 变为 84。

`--trace-impact --trace-impact-symbol NAME` 与 `nav action=trace symbol=NAME` 继续对应；所有返回使用 JSON。更新 CLI/MCP codemap、生成的 action 文档和中英日西安装说明。

## Drawbacks and alternatives

原生全仓库扫描目前较慢。在 2026-09-09 本机约 2,700 文件的工作树、暖文件系统、三次中位数对比中，两组 Python 符号扫描的文件/行命中一致；原生约 0.46–0.49 秒，rg 约 0.024–0.026 秒。此结果不是跨平台 SLA，也不能用于推断端到端 agent 用时。文件发现的三个 `.gitkeep` 差异来自隐藏文件策略，不能宣称全参数等价。

保留可选 rg/fd 加速会继续维持两套运行路径，与用户的去依赖方向不符。引入 Rust 搜索扩展会增加构建和分发成本，暂不采用。索引查询优先减少反复全仓库扫描，但不能用热索引延迟替代冷构建与实时核验成本。

## Prior art

[zvec-grep 的检索策略](https://github.com/zvec-ai/zvec-grep/blob/6fa85a8e28c0b5a0f651c27f09f0247627c5d5c3/src/client/search-policy.ts) 区分最终一致与等待新鲜索引；[检索管线](https://github.com/zvec-ai/zvec-grep/blob/6fa85a8e28c0b5a0f651c27f09f0247627c5d5c3/src/engine/pipeline/search-index.ts) 组合候选检索。借鉴候选发现、精确核验和显式新鲜度的分工；该项目自身仍使用 ripgrep，不作为去依赖实现直接引入。

## Test plan (RED-first)

先锁定不依赖外部程序的行为：禁止 `subprocess.Popen` 的真实 trace/项目发现测试在旧实现下应失败；新扫描器测试覆盖嵌套忽略、重叠根、符号链接、大小写、Unicode、行号、计数和预算错误。

删除入口时，先更新精确 action/flag 契约及旧 action 拒绝用例；真实索引别名测试禁止外部进程，并验证命中内容而非仅比较两个失败响应。移除 `requires_fd` / `requires_ripgrep` 跳过机制，执行快速门、完整本地命令和完整 OS/Python CI。Python 改动运行局部覆盖率及 patch gate。

## Acceptance criteria

- [ ] 内部文件发现与 trace 不启动外部搜索进程
- [ ] 旧 MCP action、CLI 参数、console script 及死代码全部移除
- [ ] 无 rg/fd 安装步骤或缺少它们而跳过测试的机制
- [ ] CLI↔MCP parity 与 codemap 自检通过
- [ ] 迁移说明、安装文档与内置检索 skill 一致
- [ ] 完整本地测试及跨平台 CI 通过

## Deferred

通用正则搜索接口、全仓库扫描吞吐优化、宿主自身搜索实现替换，以及新的语义检索依赖均不属于本次发布准备。
