# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **[日本語](README_ja.md)** | **简体中文**

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/) [![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org) [![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) [![Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer) [![适配 Claude Code · Cursor · MCP](https://img.shields.io/badge/适配-Claude%20Code%20%C2%B7%20Cursor%20%C2%B7%20MCP-6f42c1.svg)](#supported-agents)

**AI agent 可以信赖的代码情报** — 跨语言结构分析，为 agent 原生设计（MCP + CLI）。

TSA 使用 tree-sitter 索引代码库，向 AI 编程 agent 提供调用图、符号搜索与结构查询 — **8 个 MCP 工具** + CLI，完全本地运行，零遥测。

**为什么不同：**
* **跨语言正确性是护城河。** 语言族门控可阻止仅基于名称的跨语言绑定。
* **为 agent 原生设计。** **8 个 MCP 工具**提供 TOON 输出与 verdict 信封，也可通过 CLI 和精选工作流使用。
* **广度与正确性兼备。** 13 种语言为 `pipeline_registered`（管线注册态，非 E2E：Python · Go · Rust · Java · JS · TS · C · C++ · C# · Swift · Kotlin · Ruby · PHP）。这只是注册与接线证据，不代表跨文件调用解析已经验证。

> 从 v1.x 升级？见 [docs/MIGRATION.md](docs/MIGRATION.md)。

---

## 立即上手

> **需要 Python 3.10+**（检查：`python3 --version`）。如需安装请访问 [python.org](https://www.python.org/downloads/)。

### 自动安装（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/aimasteracc/tree-sitter-analyzer/main/install.sh | bash
```

`install.sh` 会检测 `uv` 是否已安装（未安装则自动安装），并自动检测 Claude Desktop / Claude Code / Cursor / VS Code 的配置文件，写入 MCP 配置项。安装完成后可运行 `tree-sitter-analyzer --doctor` 验证配置。

为 **Claude Code** 一行安装：

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

重启 agent，对它说："用 `index` 工具调用 action=status。"

> **PyPI / uvx 用户 — 安装 skills：** `tsa-*` skills 已打包在 wheel 中。执行一次即可安装：
> ```bash
> tree-sitter-analyzer --install-skills
> ```
> git clone 用户已在 `.claude/skills/` 下有这些文件，无需操作。

[其他 agent（Cursor / Copilot / Cline / Continue / Claude Desktop / Roo Code）→](#-支持的-agent)

### 快速安装

#### 1. 安装依赖

```bash
# uv（必需）
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# fd + ripgrep（搜索功能必需）
brew install fd ripgrep                                # macOS
winget install sharkdp.fd BurntSushi.ripgrep.MSVC      # Windows
```

#### 2. 安装 Tree-sitter Analyzer

```bash
# 独立安装(持久 CLI 命令):
uv tool install "tree-sitter-analyzer[all,mcp]"
# — 也可完全不安装:下方 MCP 配置通过 uvx 按需运行。
# 在 uv 管理的 Python 项目内则用: uv add "tree-sitter-analyzer[all,mcp]"
```

#### 3. 接入你的 agent

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

**在你自己的仓库上检查解析器行为**（无需安装，会先重建索引）：

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

该命令报告可能的跨语言名称冲突，供你检查自己仓库中的解析器行为。结果是诊断信息，不是竞争性 benchmark 主张。

---

## 为什么选择 Tree-sitter Analyzer

* **关注 token 的输出。** MCP 响应默认使用 **TOON**；载荷行为由 [output-cost invariants](tests/unit/mcp/test_output_cost_invariants.py) 保护，已知的 decision-tool 限制由 [RFC-0018](rfcs/0018-response-envelope-normalization-and-adaptive-toon.md) 跟踪。
* **结论信封（verdict envelope）。** 每个响应都带 `verdict: SAFE | CAUTION | UNSAFE | INFO | REVIEW | WARN | ERROR | NOT_FOUND`，orchestrator 可直接按结果分支。
* **项目级 A-F 健康评级。** 综合体积、复杂度、覆盖率、重复度、依赖、结构与 git 热点进行评估。
* **精选工作流（Skills）。** 为“查找符号”“追踪调用链”“评估健康”“重构前安全检查”“PR 评审”等场景提供预包装的工具子集。
* **分层安全防护。** `edit action=safe` + `edit action=guard` + 架构约束 DSL + `edit action=impact` + verdict 信封，帮助 agent 在编辑前判断风险。
* **CLI/MCP 对等与统一查询 DSL。** agent 和 shell 用户可使用相同的分析原语。

---

## 核心能力

### 预建代码情报（CodeGraph 对位 + 超集）

| 能力 | TSA 工具 | 状态 |
|---|---|---|
| 符号搜索（FTS5 + **BM25 排名**） | `search` action=symbol | **领先** — 结果按相关性分数排序 |
| go-to-def / find-refs / 调用层级组合请求 | `nav` action=navigate | PRIMARY 入口 |
| 批量获取 N 个相关符号 + 关系图 | `structure` action=explore | 对位 |
| 函数级 blast radius + 风险评分 | `nav` action=impact | 对位 + 风险评分 |
| 谁调用 X / X 调用谁 | `nav` action=callers / action=callees | 对位 |
| 索引健康一览（含边数统计） | `index` action=status | **领先** — 提供 `total_edges` 图密度信号 |
| 预建调用图缓存 | `index` action=auto / action=full / action=sync | 对位 |
| 受变更影响的测试（CLI） | `--affected FILE...` | 对位 |

### Tree-sitter Analyzer 独占

| 能力 | TSA 工具 | 说明 |
|---|---|---|
| **BM25 排名搜索** | 所有搜索工具 | 每项结果提供 min-max 标准化 relevance_score；DSL 支持 sort(by='confidence') |
| **语义搜索（BM25 预过滤）** | `search` action=chain（`semantic()` DSL） | 在余弦重排前进行词法预过滤 |
| **项目 A-F 健康评级** | `health` action=project | 综合体积、复杂度、依赖、覆盖率、重复、结构与 git 热点 |
| **TOON 输出** | 所有工具，默认 `output_format: "toon"` | 紧凑的表格式编码；decision tool 由 RFC-0018 跟踪 |
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
| **文件定向** | `project` action=smart | 在组合响应中返回健康度 + 导出符号 + 依赖 + 编辑风险 |
| **架构决策日志** | `project` action=journal | 跨会话持久化推理 — 竞品均无此能力 |

### Skills

TSA 在 `.claude/skills/tsa-*/` 下提供精选工作流：

`tsa-landing`、`tsa-find`、`tsa-graph`、`tsa-structure`、`tsa-deps`、`tsa-index`、`tsa-health-watch`、`tsa-edit-safety`、`tsa-edit-then-verify`、`tsa-constraints`、`tsa-pr-review`、`tsa-refactor-queue`、`tsa-temporal`。

每个 skill 都带 `allowed-tools` 工具子集 + 操作流程 + 决策面 schema，agent 不必在 8 个工具间反复挑选。

### 323 个 CLI flag

CodeGraph CLI 的严格超集。亮点：

```bash
tree-sitter-analyzer --table full <file>          # 方法/签名/复杂度表
tree-sitter-analyzer --partial-read --start-line N --end-line M <file>
tree-sitter-analyzer --project-health             # 项目 A-F 评级
# 注意：--callers / --callees 需要调用图索引 — 请先运行 --full-index
tree-sitter-analyzer --full-index                 # 构建调用图索引（只需运行一次）
tree-sitter-analyzer --callers <symbol>           # 谁调用
tree-sitter-analyzer --codegraph-impact <fn>      # blast radius + 风险
tree-sitter-analyzer --affected <file...>         # 受影响的测试
tree-sitter-analyzer --dead-code                  # 传递不可达
tree-sitter-analyzer --check-constraints          # 架构规则
tree-sitter-analyzer --safe-to-edit <file>        # 风险时拒绝
```

完整接口见 [`docs/CODEMAPS/cli.md`](docs/CODEMAPS/cli.md)。

---

## 定量主张治理

公开的 benchmark、性能或竞争性数字只能由 [`benchmarks/codegraph_compare/claim_registry.json`](benchmarks/codegraph_compare/claim_registry.json) 中绑定来源的 registry 生成。E4 证据必须严格绑定工具名称与版本、测量值、语料、benchmark 日期/版本以及 artifact digest。低于 E4 的证据只保留在内部，不能生成公开文案。参见 [benchmark runbook](benchmarks/codegraph_compare/README.md)。

<!-- BEGIN GENERATED QUANTITATIVE CLAIMS -->
<!-- END GENERATED QUANTITATIVE CLAIMS -->

没有生成条目表示当前没有获准公开的定量主张。上面的定性描述是有边界的产品能力，不是经过测量的优越性主张。

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

验证：`claude mcp list`。捆绑的 `tsa-*` skills 会从 `.claude/skills/` 自动发现。

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

<!-- BEGIN GENERATED LANGUAGE SUPPORT INVENTORY -->
由运行时 registry 生成。**22 个语言插件**；13 个为 `pipeline_registered`（非 E2E），3 个为 `index_admitted`，0 个为 `call_dispatch_only`，5 个 data/markup，1 个脚手架。注册状态不保证跨文件正向绑定。
| 等级 | 语言 |
|---|---|
| **`pipeline_registered`（管线注册态，非 E2E）** | C · C++ · C# · Go · Java · JavaScript · Kotlin · PHP · Python · Ruby · Rust · Swift · TypeScript |
| **`index_admitted`（索引准入态）** | Bash · Lua · Scala |
| **`call_dispatch_only`（仅 call dispatch）** |  |
| **单文件分析（CLI）** | CSS · HTML · Markdown · SQL · YAML |
| **脚手架（插件已有，索引器待接）** | JSON |

Lua 已获索引准入，并具备 call dispatch 与 resolver slot，但 import dispatch 和跨文件 E2E 证据仍未确认。
<!-- END GENERATED LANGUAGE SUPPORT INVENTORY -->

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
| 测试通过 | 全面的测试套件 ✅ |
| 覆盖率 | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| 类型安全 | mypy |
| 平台 | macOS · Linux · Windows |
| Pre-commit 闸门 | ruff · bandit · mypy · pyupgrade · detect-secrets · tsa-codemap-sync |

```bash
uv run pytest -q                                # 完整套件
uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # 开发期快速循环
PYTEST_XDIST_AUTO_NUM_WORKERS=1 uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # 降低 CPU 负载
PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run pytest -q --maxfail=1 -m "not slow and not full_language and not integration"  # 平衡并行度
uv run pytest --lf --maxfail=1                  # 只重跑上次失败的测试
uv run python check_quality.py --new-code-only  # 质量闸门
```

---

## 故障排查

| 症状 | 修复 |
|---|---|
| `.swift / .kt / .rb / .php / .cs` 显示 `unsupported language` | 升级到 ≥ 1.12.x — 5 语言 gap 已在 commit `50e99a8f` 中修复。extras 门控语言的语法模块不随基础安装捆绑;运行 `pip install "tree-sitter-analyzer[swift]"`(或 `kotlin`、`ruby`、`php`、`csharp`)补装 |
| MCP 服务在客户端中不出现 | `TREE_SITTER_PROJECT_ROOT` 必须是**绝对路径**；编辑配置后重启客户端。另见 [TREE\_SITTER\_PROJECT\_ROOT 使用了相对路径](#tree_sitter_project_root-使用了相对路径) |
| `database is locked` | 关闭其他占用 `.ast-cache/index.db` 的进程；持续存在则 `rm -rf .ast-cache && tree-sitter-analyzer --autoindex` |
| 首次调用慢 | 首次调用会建索引。后续亚秒。预先跑 `--full-index` 即可分摊 |
| Agent 选错工具 | 使用 `tsa-*` skill（`/tsa-graph`、`/tsa-find` 等）— 每个 skill 把可见工具限定到一个工作流 |

### TREE\_SITTER\_PROJECT\_ROOT 使用了相对路径

**症状：** MCP 服务启动时无报错，但 TSA 返回错误的分析结果，或出现类似 `project root not found` 的错误。

**根本原因：** `TREE_SITTER_PROJECT_ROOT` 设置了相对路径（如 `./myproject`）。`uvx` 启动服务时，进程工作目录可能与安装时不同，导致相对路径解析到错误位置。

**修复方法：** 始终使用绝对路径：

```bash
# 正确
"TREE_SITTER_PROJECT_ROOT": "/home/user/myproject"

# 也正确（install.sh 在安装时自动解析）
"TREE_SITTER_PROJECT_ROOT": "$(pwd)"        # 或 $(realpath .)

# 错误
"TREE_SITTER_PROJECT_ROOT": "./myproject"
"TREE_SITTER_PROJECT_ROOT": "myproject"
```

运行 `tree-sitter-analyzer --doctor` 可验证你的配置。

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
* 发布历史：[CHANGELOG.md](CHANGELOG.md)。
