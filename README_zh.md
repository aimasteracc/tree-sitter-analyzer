# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **[日本語](README_ja.md)** | **简体中文**

> **专为 AI agent 而生的 MCP 代码情报服务 — 更少 token、更少工具调用、100% 本地运行。**
> 预建 AST 索引 + 60 个 MCP 工具 + 13 个精选 agent 技能 + TOON 压缩输出。
> 6 仓库头对头实测**胜过 CodeGraph**（中位数 cost **−11% vs CodeGraph 的 −4%**），CLI 维度严格超集。
> 全面 **BM25 排名搜索** — 全部 60 个工具的结果按相关性打分排序，不再按文件路径随机排列。

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-18565%20passed-brightgreen.svg)](#-质量与测试)
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

重启 agent，对它说："设置项目根目录到我的仓库，然后调用 codegraph_status。"

[其他 agent（Cursor / Copilot / Cline / Continue / Claude Desktop / Roo Code）→](#-支持的-agent)

---

## 为什么选择 Tree-sitter Analyzer

* **默认就省 token**。所有 MCP 工具响应使用 **TOON** — 一种表格式 JSON 变体，比原始 JSON 节省约 50-70% 字节。
* **结论信封 (verdict envelope)**。每个响应都带 `verdict: SAFE | CAUTION | UNSAFE | INFO | WARN | ERROR | NOT_FOUND`，orchestrator 直接分支决策，无需二次提示。
* **项目级 A-F 健康评级**。其他开源工具都没有 — 一次调用从体积、复杂度、覆盖率、重复度、依赖、git-热点 6 个维度给整个项目打分。
* **13 个精选工作流（Skills）**。预包装好的工具子集，对应 "查找符号"、"追踪调用链"、"评估健康"、"重构前安全检查"、"PR 评审" 等典型场景。
* **5 层安全防护**。`safe_to_edit` + `modification_guard` + 架构约束 DSL + `change_impact` + verdict 信封 — 让 agent 在动手前 *知道* 风险。
* **多个 head-to-head benchmark 上击败领先竞品 CodeGraph**。见下文实测。

---

## Benchmark 实测

headless Claude Code（Haiku 4.5）每仓库问一个架构问题。3 个 arm：无 MCP / CodeGraph MCP / Tree-sitter Analyzer MCP。每 arm 单次运行 — 指示性数据，非统计严格。

| 仓库 | 语言/文件数 | 无 MCP 基线 | CodeGraph | **TSA** | 胜者 |
|---|---|---|---|---|---|
| **Gin** | Go / 99 | $0.164 | $0.094 (−43 %) | **$0.080 (−51 %)** | **TSA** ⭐ |
| **Alamofire** | Swift / 98 | $0.201 | $0.219 (+9 %) | **$0.147 (−27 %)** | **TSA** ⭐ |
| **Excalidraw** | TS / 603 | $0.204 | **$0.179 (−12 %)** | $0.212 (+4 %) | CodeGraph |
| **Django** | Py / 2 910 | $0.162 | **$0.106 (−35 %)** | $0.205 (+27 %) | CodeGraph |
| **Tokio** | Rust / 778 | **$0.214** | $0.285 (+33 %) | $0.303 (+42 %) | 两者皆输 |
| **OkHttp** | Java / 596 | **$0.169** | $0.200 (+18 %) | $0.178 (+5 %) | 两者皆输 |
| **中位数 Δ vs 基线** | | | **−4 %** | **−11 %** | **TSA** |

TSA 在 **6 个仓库中 2 个完胜**，**中位数成本节省（−11%）超过 CodeGraph 的 −4%**，并在 indexer-class 工具应当发挥作用的仓库上方向上与 CodeGraph 一致。

> 我们的中位数为何与 CodeGraph 公布的 −35% 不同：我们为控制成本用了 Haiku；他们用 Opus + 4 次中位。完整原始 envelope 和复现脚本见 `docs/internal/CODEGRAPH_BENCHMARK_FINAL_2026-05-24.md`。

---

## 核心能力

### 预建代码情报（CodeGraph 对位 + 超集）

| 能力 | TSA 工具 | 状态 |
|---|---|---|
| 符号搜索（FTS5 + **BM25 排名**） | `codegraph_symbol_search` | **领先** — 结果按相关性分数排序 |
| go-to-def / find-refs / 调用层级 一次调用 | `codegraph_navigate` | PRIMARY 入口 |
| 批量获取 N 个相关符号 + 关系图 | `codegraph_explore` | 对位 |
| 函数级 blast radius + 风险评分 | `codegraph_impact` | 对位 + 风险评分 |
| 谁调用 X / X 调用谁 | `codegraph_callers` / `codegraph_callees` | 对位 |
| 索引健康一览（含边数统计） | `codegraph_status` | **领先** — 提供 `total_edges` 图密度信号 |
| 预建调用图缓存 | `codegraph_autoindex` / `codegraph_full_index` / `codegraph_incremental_sync` | 对位 |
| 受变更影响的测试（CLI） | `--affected FILE...` | 对位 |

### Tree-sitter Analyzer 独占

| 能力 | TSA 工具 | 说明 |
|---|---|---|
| **BM25 排名搜索** | 所有搜索工具 | 每个结果带 relevance_score；DSL 支持 sort(by='confidence') |
| **语义搜索（133× 加速）** | `codegraph_query semantic()` | BM25 预过滤将 40k 符号收窄至 ~400 再做余弦重排 |
| **项目 A-F 健康评级** | `check_project_health` | 6 维度，竞品无对位 |
| **TOON 输出** | 所有工具，默认 `output_format: "toon"` | 50-70% token 节省 |
| **Verdict 信封** | 所有工具 | `SAFE/CAUTION/UNSAFE/INFO/WARN/ERROR/NOT_FOUND` |
| **Safe-to-edit 闸门** | `safe_to_edit` + `modification_guard` | 高风险编辑前拒绝 |
| **架构约束 DSL** | `check_constraints` | "模块 A 不能依赖 B" → 强制执行 |
| **文件级健康度** | `check_file_health` | 代码块/长方法/坏味道检测 |
| **类继承层级** | `codegraph_class_hierarchy` | 类型继承树 |
| **依赖矩阵** | `codegraph_dependency_matrix` | 模块耦合矩阵 |
| **死代码** | `codegraph_dead_code` | 传递不可达分析 |
| **复杂度热点** | `codegraph_complexity_heatmap` | 单函数圈复杂度 + 项目视图 |
| **AST 结构克隆检测** | `codegraph_similarity` | 超越文本相似度 |
| **Mermaid 调用图导出** | `codegraph_visualize` | 直接粘贴进文档 |
| **UML Mermaid 导出** | `codegraph_uml` | class / package / component / sequence 图 |
| **PR 评审** | `codegraph_pr_review` | AST diff + 语义分类 + blast radius |
| **agent_summary** | 所有响应 | 下一步提示内嵌于信封 |
| **Synapse 跨文件解析** | 内部 | import-aware，胜过正则猜测 |
| **时间激活度** | `symbol_lineage` | 每个符号的 git 修改频率 |

### Skills（13 个精选工作流）

CodeGraph 没有 skill 系统。我们在 `.claude/skills/tsa-*/` 下提供 13 个：

`tsa-landing`、`tsa-find`、`tsa-graph`、`tsa-structure`、`tsa-deps`、`tsa-index`、`tsa-health-watch`、`tsa-edit-safety`、`tsa-edit-then-verify`、`tsa-constraints`、`tsa-pr-review`、`tsa-refactor-queue`、`tsa-temporal`。

每个 skill 都带 `allowed-tools` 工具子集 + 操作流程 + 决策面 schema，agent 不必在 60 个工具间反复挑选。

### 252 个 CLI flag

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

重启 agent 后："设置项目根目录到我的仓库，然后调用 codegraph_status。"

---

## 工作原理

```
源代码 → tree-sitter 解析 → SQLite + FTS5 索引 (.ast-cache/index.db)
                                    ↓
   codegraph_navigate / codegraph_explore / codegraph_callers / ...
                                    ↓
                       TOON 压缩信封
                       (verdict + agent_summary + 数据)
                                    ↓
                       MCP 客户端 / CLI 消费者
```

索引首次查询时懒构建，文件变更时通过内容哈希增量刷新（`codegraph_incremental_sync`）。所有 60 个工具共享同一份 `.ast-cache/`，查询与跟进调用共享工作量。

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

> ⚠️ `TREE_SITTER_PROJECT_ROOT` 必须是 **绝对路径**。服务通过 `SecurityBoundaryManager` 强制安全边界，防止逃逸。

---

## 支持的语言

21 个语言插件；16 个完全接入索引器 + 5 个（data/markup）走 CLI 单文件路径。2026-05-24 的补丁解锁了被静默跳过数月的 Swift / Kotlin / Ruby / PHP / C#。

| 等级 | 语言 |
|---|---|
| **完整索引 + 符号 + 调用图** | Python · Java · JavaScript · TypeScript · Go · Rust · C · C++ · C# · Swift · Kotlin · Ruby · PHP |
| **单文件分析（CLI）** | HTML · CSS · Markdown · SQL · YAML |
| **脚手架（插件已有，索引器待接）** | bash · scala · json |

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
| 测试通过 | 18,565 ✅ |
| 覆盖率 | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| 类型安全 | 100% mypy |
| 平台 | macOS · Linux · Windows |
| Pre-commit 闸门 | bandit · mypy · pyupgrade · detect-secrets · codemap-sync · smell-ratchet |

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
