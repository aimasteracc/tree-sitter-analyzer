# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **[日本語](README_ja.md)** | **简体中文**

> **专为 AI agent 而生的 MCP 代码情报服务 — 更少 token、更少工具调用、100% 本地运行。**
> 预建 AST 索引 + **8 个 MCP 工具**（从 v1.x 的 63 个精简而来）+ 13 个精选 agent 技能 + TOON 压缩输出。
> **tool-definition 开销降低约 80%** — 市场上唯一同时具备 rich-output（verdict + TOON）和 Roo/Cursor 兼容的 code-intel MCP。
> CodeGraph 的**严格 CLI 超集**，更快的索引、一次调用的 jQuery 风格查询 DSL，以及 **跨 13 种语言都不会错连的调用图**。在同一仓库的两个工具实时索引上，CodeGraph 产生 **745 处**跨语言错连（例如把 Python 的 `sorted()` 连到 Swift 的 func），TSA 只有 **6 处**（约 **390× 更干净**）。成本曾是 CodeGraph 唯一的优势，RFC-0006 已弥合大部分 —— 见[与 CodeGraph 的对比](#与-codegraph-的对比)。
> **BM25 排名搜索** — 所有 8 个 facade 的结果按相关性打分排序，不再按文件路径随机排列。
>
> 竞品工具数对比：CodeGraph ~12 · Rhizome 1 · **TSA 8（rich-output）** · TSA v1.x 为 63。
> 从 v1.x 升级？见 [docs/MIGRATION.md](docs/MIGRATION.md)。

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-18493%20passed-brightgreen.svg)](#-质量与测试)
[![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

---

## 立即上手

为 **Claude Code** 一行安装：

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

重启 agent，对它说："用 `index` 工具调用 action=status。"

> **PyPI / uvx 用户 — 安装 skills：** 13 个 `tsa-*` skills 已打包在 wheel 中。执行一次即可安装：
> ```bash
> tree-sitter-analyzer --install-skills
> ```
> git clone 用户已在 `.claude/skills/` 下有这些文件，无需操作。

[其他 agent（Cursor / Copilot / Cline / Continue / Claude Desktop / Roo Code）→](#-支持的-agent)

**用一条命令在你自己的仓库上验证 correctness 优势**（无需安装、无需 CodeGraph，会先重建索引）：

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

它会显示一个 name-only 代码索引（多数工具的设计）会把多少调用跨语言错连（例如 Python 的 `sorted()` → Swift 的 func），对比 TSA 的数量。实测：[HuggingFace `tokenizers`](benchmarks/codegraph_compare/MISWIRE-AUDIT-EXAMPLES.md) 上 name-only 为 **1,259 处**（含 JS `tokenize()` → Rust），TSA 为 **0**。ruff **7557×**、polars **9016×**。单语言仓库（gin/Go）两者均为 **0**，无误报。

---

## 为什么选择 Tree-sitter Analyzer

* **默认就省 token**。所有 MCP 工具响应使用 **TOON** — 一种表格式 JSON 变体，比原始 JSON 节省约 50-70% 字节。
* **结论信封 (verdict envelope)**。每个响应都带 `verdict: SAFE | CAUTION | UNSAFE | INFO | WARN | ERROR | NOT_FOUND`，orchestrator 直接分支决策，无需二次提示。
* **项目级 A-F 健康评级**。其他开源工具都没有 — 一次调用从体积、复杂度、覆盖率、重复度、依赖、结构、git-热点 7 个维度给整个项目打分。
* **13 个精选工作流（Skills）**。预包装好的工具子集，对应 "查找符号"、"追踪调用链"、"评估健康"、"重构前安全检查"、"PR 评审" 等典型场景。
* **5 层安全防护**。`safe_to_edit` + `modification_guard` + 架构约束 DSL + `change_impact` + verdict 信封 — 让 agent 在动手前 *知道* 风险。
* **CodeGraph 的严格 CLI 超集、更快索引、一次调用查询 DSL** —— 诚实成本对比见[下文](#与-codegraph-的对比)。

---

## 与 CodeGraph 的对比

> **更正（2026-06）。** 此前本节声称「中位数成本 −11% 胜过 CodeGraph」。那次 benchmark 有 harness bug：TSA arm 的 MCP server 启动时未指定项目根，分析的是 **tree-sitter-analyzer 自身的源码**而非目标仓库，数据无意义。该 bug 已修复（harness 现在传 `--project-root`），夸大的结论予以撤回，下面是诚实的对比。

### Agent token 成本 —— CodeGraph 每任务约便宜 1.5×

在修复后的 harness 上（Claude Sonnet，gin + django，MCP arm，零错误），每任务**中位数成本**：

| arm | 中位数成本 | tool calls | file reads |
|---|---|---|---|
| CodeGraph MCP | **约 $0.27** | 7 | 2 |
| Tree-sitter Analyzer MCP | 约 $0.44 | 7 | 1 |
| 无 MCP（grep/read） | 约 $0.34 | 14 | 7 |

两个 indexer 工具调用次数相同；TSA 每次调用的响应更丰富（更多图 + 内联源码），因而在 cache-write token 上贵约 1.5×。我们大幅削减了每个工具的默认输出（nav context、call tree、symbol search、chain DSL），把差距从约 2–4× 降到约 1.5×，但**就一次性问答的 token 效率而言，CodeGraph 仍是更省的 indexer**，我们如实报告。

### TSA 领先之处

- **索引构建速度。** 移除 commit 后冗余的 edge-refresh pass，django 冷索引（约 2,950 文件）从 **181 秒 → 97 秒（−46%）**；仓库越大收益越大。未变更文件的重索引是 content-hash 查表。
- **严格的 CLI 超集。** 每个 MCP 工具都有 CLI 等价物（CodeGraph 的 CLI 更薄）；*行为*默认值（排名、上限、截断）在两个界面保持同步。唯一刻意分歧的是输出格式 —— MCP 默认 TOON（对 agent 省 token），CLI 默认 JSON（人类/`jq` 友好）。
- **一次调用的表达力。** jQuery 风格 chain DSL —— `search('X').callees(depth=2).explore(include_code=true).answer(compact=true)` —— 一次调用返回整条流程的子图 + 源码，支持 JS 风格 `true`/`false`，agent 可自然书写。
- **结构化 + token 友好的输出。** MCP 默认 TOON（比 JSON 小 50–70%）、per-call 截断提示、全排序路径一致的测试文件降权。
- **广度。** 健康评分、safe-to-edit / change-impact 门控、13 个 curated Skills、广泛语言支持。

### 调用图正确性 —— TSA 正确解析 CodeGraph 错连的调用

token 成本只是一个维度；代码情报工具的**首要**职责是**正确的图**。在本仓库上用两个工具的实时索引对拍，暴露出一类误解析：CodeGraph 把一次调用绑到同名的错误定义上 —— 而 TSA 的解析器已修复以避免它：

| 调用（Python `_resolve_entry_points` / `build_response`） | CodeGraph | TSA |
|---|---|---|
| `sorted()`（Python 内建） | ❌ callee = **`tests/golden/corpus_swift.swift` 里的 Swift `func sorted`**（这一个 Swift 定义被全仓**约 293** 个函数当作 callee 连上） | ✅ 保持 `unknown` —— 不产生跨语言边 |
| `fts_search()` / `fts_search_ranked()` | ❌ 绑到**测试 mock**（`FallbackCache`）而非真实方法 | ✅ 解析到源码方法（`_ast_cache_query.py` / `ast_cache.py`） |

告诉 agent 一个 Python 函数*调用了 Swift 方法*，或者生产代码调用指向测试 mock，都是错误的结构数据。TSA 的解析器在所有解析路径上，按**语言族**给绑定设闸（JS/TS 同族；Python 绝不绑到 Swift/JS），并对非测试调用方**降权测试专用定义**。在两个工具都已索引的任意仓库复现：

```bash
# CodeGraph：返回跨语言 / test-shadow 的 callee
#   （如 `sorted` → corpus_swift.swift，`fts_search` → 测试 mock）
# 解析器修复后的 TSA：语言正确、优先源码
tree-sitter-analyzer --callees _resolve_entry_points --format json
```

> 复现成本数值：`uv run python benchmarks/codegraph_compare/run.py phase full-warm --repos gin,django`。原始 envelope 与 harness 修复在该目录。

---

## 核心能力

### 预建代码情报（CodeGraph 对位 + 超集）

| 能力 | TSA 工具 | 状态 |
|---|---|---|
| 符号搜索（FTS5 + **BM25 排名**） | `search` action=symbol | **领先** — 结果按相关性分数排序 |
| go-to-def / find-refs / 调用层级 一次调用 | `nav` action=navigate | PRIMARY 入口 |
| 批量获取 N 个相关符号 + 关系图 | `structure` action=explore | 对位 |
| 函数级 blast radius + 风险评分 | `nav` action=impact | 对位 + 风险评分 |
| 谁调用 X / X 调用谁 | `nav` action=callers / action=callees | 对位 |
| 索引健康一览（含边数统计） | `index` action=status | **领先** — 提供 `total_edges` 图密度信号 |
| 预建调用图缓存 | `index` action=auto / action=full / action=sync | 对位 |
| 受变更影响的测试（CLI） | `--affected FILE...` | 对位 |

### Tree-sitter Analyzer 独占

| 能力 | TSA 工具 | 说明 |
|---|---|---|
| **BM25 排名搜索** | 所有搜索工具 | min-max 标准化 relevance_score（最佳=1.0/最弱=0.0）；DSL 支持 sort(by='confidence') |
| **语义搜索（133× 加速）** | `search` action=chain（`semantic()` DSL） | BM25 预过滤将 40k 符号收窄至 ~400 再做余弦重排 |
| **项目 A-F 健康评级** | `health` action=project | 7 维度（体积/复杂度/依赖/覆盖率/重复/结构/git热点），竞品无对位 |
| **TOON 输出** | 所有工具，默认 `output_format: "toon"` | 50-70% token 节省 |
| **Verdict 信封** | 所有工具 | `SAFE/CAUTION/UNSAFE/INFO/WARN/ERROR/NOT_FOUND` |
| **Safe-to-edit 闸门** | `edit` action=safe / action=guard | 高风险编辑前拒绝 |
| **架构约束 DSL** | `edit` action=constraints | "模块 A 不能依赖 B" → 强制执行 |
| **文件级健康度** | `health` action=file | 代码块/长方法/坏味道检测 |
| **类继承层级** | `structure` action=class_tree | 类型继承树 |
| **依赖矩阵** | `health` action=matrix | 模块耦合矩阵 |
| **死代码** | `health` action=dead | 传递不可达分析 |
| **复杂度热点** | `health` action=heatmap | 单函数圈复杂度 + 项目视图 |
| **AST 结构克隆检测** | `viz` action=similarity | 超越文本相似度 |
| **Mermaid 调用图导出** | `viz` action=graph | 直接粘贴进文档 |
| **UML Mermaid 导出** | `viz` action=uml | class / package / component / sequence 图 |
| **PR 评审** | `edit` action=pr | AST diff + 语义分类 + blast radius |
| **agent_summary** | 所有响应 | 下一步提示内嵌于信封 |
| **Synapse 跨文件解析** | 内部 | import-aware，胜过正则猜测 |
| **时间激活度** | `nav` action=lineage | 每个符号的 git 修改频率 |
| **单次文件定向** | `project` action=smart | 健康度 + 导出符号 + 依赖 + 编辑风险一次调用（替代 3-4 次调用） |
| **架构决策日志** | `project` action=journal | 跨会话持久化推理 — 竞品均无此能力 |

### Skills（13 个精选工作流）

CodeGraph 没有 skill 系统。我们在 `.claude/skills/tsa-*/` 下提供 13 个：

`tsa-landing`、`tsa-find`、`tsa-graph`、`tsa-structure`、`tsa-deps`、`tsa-index`、`tsa-health-watch`、`tsa-edit-safety`、`tsa-edit-then-verify`、`tsa-constraints`、`tsa-pr-review`、`tsa-refactor-queue`、`tsa-temporal`。

每个 skill 都带 `allowed-tools` 工具子集 + 操作流程 + 决策面 schema，agent 不必在 8 个工具间反复挑选。

### 284 个 CLI flag

CodeGraph 15 命令 CLI 的严格超集。亮点：

```bash
tree-sitter-analyzer --table full <file>          # 方法/签名/复杂度表
tree-sitter-analyzer --partial-read --start-line N --end-line M <file>
tree-sitter-analyzer --project-health             # 项目 A-F 评级
tree-sitter-analyzer --callers <symbol>           # 谁调用
tree-sitter-analyzer --codegraph-impact <fn>      # blast radius + 风险
tree-sitter-analyzer --affected <file...>         # 受影响的测试
tree-sitter-analyzer --dead-code                  # 传递不可达
tree-sitter-analyzer --check-constraints          # 架构规则
tree-sitter-analyzer --safe-to-edit <file>        # 风险时拒绝
```

完整接口见 [`docs/CODEMAPS/cli.md`](docs/CODEMAPS/cli.md)。

---

## 快速开始

### 1. 安装依赖

```bash
# uv（必需）
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# fd + ripgrep（搜索功能必需）
brew install fd ripgrep                                # macOS
winget install sharkdp.fd BurntSushi.ripgrep.MSVC      # Windows
```

### 2. 安装 Tree-sitter Analyzer

```bash
uv add "tree-sitter-analyzer[all,mcp]"
```

### 3. 接入你的 agent

详见**[支持的 agent](#-支持的-agent)**。大多数客户端使用此 MCP 配置：

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "/绝对路径/项目目录" }
    }
  }
}
```

重启 agent 后："用 `index` 工具调用 action=status。"

---

## 工作原理

```
源代码 → tree-sitter 解析 → SQLite + FTS5 索引 (.ast-cache/index.db)
                                    ↓
   nav (navigate) / structure (explore) / nav (callers) / ...
                                    ↓
                       TOON 压缩信封
                       (verdict + agent_summary + 数据)
                                    ↓
                       MCP 客户端 / CLI 消费者
```

索引首次查询时懒构建，文件变更时通过内容哈希增量刷新（`index` action=sync）。所有 8 个工具共享同一份 `.ast-cache/`，查询与跟进调用共享工作量。

---

## 支持的 Agent

<details>
<summary><b>📘 Claude Code</b>（推荐）</summary>

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

验证：`claude mcp list`。13 个 `tsa-*` skills 会从 `.claude/skills/` 自动发现。

**PyPI / uvx 用户** — 安装一次内置 skills：
```bash
tree-sitter-analyzer --install-skills
```
git clone 用户已有，无需操作。
</details>

<details>
<summary><b>📗 Claude Desktop</b></summary>

编辑 `claude_desktop_config.json`（macOS：`~/Library/Application Support/Claude/`，Windows：`%APPDATA%\Claude\`，Linux：`~/.config/Claude/`）：

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "/绝对路径/项目目录" }
    }
  }
}
```
</details>

<details>
<summary><b>📙 GitHub Copilot（VS Code）</b></summary>

创建 `.vscode/mcp.json`（注意：键是 `servers`，不是 `mcpServers`）：

```json
{
  "servers": {
    "tree-sitter-analyzer": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "tree-sitter-analyzer[mcp]", "tree-sitter-analyzer-mcp"],
      "env": { "TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}" }
    }
  }
}
```
</details>

<details>
<summary><b>🖱 Cursor / Cline / Continue / Roo Code</b></summary>

都使用 Claude Desktop 的 `mcpServers` schema。Cursor：**设置 → MCP**。Cline：MCP 面板 → 编辑设置。Continue：`~/.continue/config.json` 下 `experimental.modelContextProtocolServers`。Roo Code：MCP 面板 → 编辑 MCP 设置。
</details>

> ⚠️ `TREE_SITTER_PROJECT_ROOT` 必须是 **绝对路径**。服务通过 `SecurityValidator` 强制安全边界，防止逃逸。

---

## 支持的语言

21 个语言插件；13 个完全接入索引器（符号 + 调用图）+ 2 个已接符号索引（调用图接线待完成）+ 5 个（data/markup）走 CLI 单文件路径 + 1 个脚手架（插件存在，索引接线待完成）。bash 与 scala 于 v1.22.0 毕业；2026-05-24 的补丁解锁了被静默跳过数月的 Swift / Kotlin / Ruby / PHP / C#。

| 等级 | 语言 |
|---|---|
| **完整索引 + 符号 + 调用图** | Python · Java · JavaScript · TypeScript · Go · Rust · C · C++ · C# · Swift · Kotlin · Ruby · PHP |
| **完整索引 + 符号（调用图待接）** | Bash · Scala |
| **单文件分析（CLI）** | HTML · CSS · Markdown · SQL · YAML |
| **脚手架（插件已有，索引器待接）** | json |

CodeGraph 支持相近的集合；两者都还未发布的主流代码语言只有 **Dart、Vue、Svelte、Lua**（下个 sprint backlog）。

---

## 配置

基本零配置。默认值就让你接入 agent 即可忘记：

* **输出格式**：TOON。可通过 `output_format: "json"` 单次覆盖。
* **项目根目录**：`TREE_SITTER_PROJECT_ROOT`（env，MCP）或 `--project-root`（CLI）。
* **缓存位置**：`<project>/.ast-cache/`。可安全删除 — 会自动重建。
* **可选**：`TREE_SITTER_OUTPUT_PATH` 用于大输出写入目标。

---

## 质量与测试

| 指标 | 值 |
|---|---|
| 测试通过 | 17,456 ✅ |
| 覆盖率 | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| 类型安全 | 100% mypy |
| 平台 | macOS · Linux · Windows |
| Pre-commit 闸门 | ruff · bandit · mypy · pyupgrade · detect-secrets · tsa-codemap-sync |

```bash
uv run pytest -q                                # 完整套件
uv run python check_quality.py --new-code-only  # 质量闸门
```

---

## 故障排查

| 症状 | 修复 |
|---|---|
| `.swift / .kt / .rb / .php / .cs` 显示 `unsupported language` | 升级到 ≥ 1.12.x — 5 语言 gap 已在 commit `50e99a8f` 中修复 |
| MCP 服务在客户端中不出现 | `TREE_SITTER_PROJECT_ROOT` 必须是**绝对路径**；编辑配置后重启客户端 |
| `database is locked` | 关闭其他占用 `.ast-cache/index.db` 的进程；持续存在则 `rm -rf .ast-cache && tree-sitter-analyzer --autoindex` |
| 首次调用慢 | 首次调用会建索引。后续亚秒。预先跑 `--full-index` 即可分摊 |
| Agent 选错工具 | 使用 `tsa-*` skill（`/tsa-graph`、`/tsa-find` 等）— 每个 skill 把可见工具限定到一个工作流 |

---

## 开发

```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
uv run pytest -q
```

开发指南见 **[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md)**。

---

## 贡献与许可

* ⭐ GitHub star 帮助其他 AI agent 用户发现本项目。
* 💖 [赞助](https://github.com/sponsors/aimasteracc) — 支持持续的 MCP / Skills 开发。
* 首席赞助人：**[@o93](https://github.com/o93)**。
* MIT 许可证 — 详见 [LICENSE](LICENSE)。
