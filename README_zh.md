# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **[日本語](README_ja.md)** | **简体中文**

[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/) [![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org) [![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) [![Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer) [![适配 Claude Code · Cursor · MCP](https://img.shields.io/badge/适配-Claude%20Code%20%C2%B7%20Cursor%20%C2%B7%20MCP-6f42c1.svg)](#supported-agents)

**AI agent 可以信赖的代码情报** — 在[受支持的语言清单](#支持的语言)范围内保持正确的跨语言结构，为 agent 原生设计（MCP + CLI）。

TSA 使用 tree-sitter 索引代码库，向 AI 编程 agent 提供调用图、符号搜索与结构查询 — **8 个 MCP 工具** + CLI，完全本地运行，零遥测。

**为什么不同：**
* **跨语言正确性是护城河。** 语言族门控可阻止仅基于名称的跨语言绑定。
* **为 agent 原生设计。** **8 个 MCP 工具**提供结构化 JSON 输出与 verdict 信封，也可通过 CLI 和精选工作流使用。
* **广度与正确性兼备。** 13 种语言为 `pipeline_registered`（管线注册态，非 E2E）。这只是注册与接线证据，不代表已验证的跨文件调用解析。详见[自动生成的支持深度清单](#支持的语言)。

> 从 v1.x 升级？见 [docs/MIGRATION.md](docs/MIGRATION.md)。

### 神经系统边界 (Pulse / TQL / 语义查询)

TQL 的时间选择器比较的是修改时间戳，而不是修改次数。
`tql_schema` action 记录了裸 `:hot` 与 `:recently_modified` 共享的窗口期与默认值。深度查询保留精确的定义同一性，超出遍历上限时会明确失败。

Pulse 请求返回的是快照绑定的上下文。用于身份信息、关系、反向 import 上下文以及可选的缓存 LSP 增强的 SQL 读取共享相同的 savepoint，且不会结束调用方持有的事务。这并不意味着存在 SQL 往返或延迟保证。

Pulse 的 Python 反向 import 上下文使用现有的模块解析器；这并不代表跨语言模块解析已完全实现。评论上下文需要以启用评论提取的方式重建索引。旧索引以及不支持评论提取的语言会返回 `COMMENTS_NOT_INDEXED`，而不是返回空的成功结果；不需要评论上下文时，可通过文档化的 `max_comments` 设置显式省略。缺失的历史提交信息投影会变为 `pending` 以待惰性刷新；`disabled` 的激活状态会被保留。历史遗留的 NULL 激活状态同样会变为 pending，且不会清除旧消息或计数。已启用的缓存索引周期会继续进行有边界的激活刷新。Pulse 将不可用的激活状态暴露为 `null`，而时间性查询会拒绝不完整的激活证据。刷新通过有边界的批次读取真实的 Git 历史；消息读取失败时会保留为待处理，而不会声称已完成。

语义查询要求使用已知的、已存储的嵌入模型，且维度必须一致。混用或未知的模型会报错，且没有 provider 回退。离线测试使用模型 double；它们不能证明真实 provider 的质量。

Pulse 批处理会保留成功的条目，但只要目标中存在失败就会报告失败。TQL 将缺失或不可读的索引视为错误，这与"索引就绪但无匹配结果"是不同的情况。公开请求校验会在打开索引或调用嵌入 provider 之前，拒绝无效的类型和上限值。

---

## 立即上手

> **需要 Python 3.10+**（检查：`python3 --version`）。如需安装请访问 [python.org](https://www.python.org/downloads/)。

### 自动安装（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/aimasteracc/tree-sitter-analyzer/main/install.sh | bash
```

`install.sh` 会检测 `uv` 是否已安装（未安装则自动安装），并自动检测 Claude Desktop / Claude Code / Cursor / VS Code 的配置文件，写入 MCP 配置项。安装完成后可运行 `tree-sitter-analyzer --doctor` 验证配置。

> **引导信任说明：** 为方便起见，上述命令在 `uv` 缺失或版本过旧时，会通过 TLS 下载并执行官方 `uv` 安装器。该安装器是可变的、**并非内容绑定（content-bound）**的；TSA 会在下载到临时文件前发出警告，并在安装后执行严格的版本校验。如果想避免这个未经验证的引导过程，可以预先手动安装 `uv >= 0.11.0`，或使用以下安全的退出选项（需要引导时会直接退出并给出手动安装说明）：
> ```bash
> curl -fsSL https://raw.githubusercontent.com/aimasteracc/tree-sitter-analyzer/main/install.sh \
>   | TSA_DISABLE_UNVERIFIED_UV_BOOTSTRAP=1 bash
> ```

为 **Claude Code** 一行安装：

```bash
claude mcp add tree-sitter-analyzer \
  --env TREE_SITTER_PROJECT_ROOT="$PWD" \
  -- uvx --from "tree-sitter-analyzer[mcp]" tree-sitter-analyzer-mcp
```

重启 agent，对它说："用 `index` 工具调用 action=status。"
CLI 等效命令（无需 agent）：`tree-sitter-analyzer --codegraph-status`

> **PyPI / uvx 用户 — 安装 skills：** `tsa-*` skills 已打包在 wheel 中。执行一次即可安装：
> ```bash
> tree-sitter-analyzer --install-skills              # 安装到 ./.claude/skills/（仅本项目）
> tree-sitter-analyzer --install-skills-global       # 安装到 ~/.claude/skills/（所有项目共用）
> ```
> git clone 用户已在 `.claude/skills/` 下有这些文件，无需操作。

[其他 agent（Cursor / Copilot / Cline / Continue / Claude Desktop / Roo Code）→](#-支持的-agent)

### 快速安装

#### 1. 安装依赖

```bash
# uv（必需）。该官方便捷安装器是可变的、非内容绑定的；
# 其他手动安装方式见 https://docs.astral.sh/uv/。
curl -LsSf https://astral.sh/uv/install.sh | sh        # macOS / Linux
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# fd + ripgrep（`search action=batch` 多查询文本搜索所需；符号搜索使用 SQLite FTS5，两者都不需要）
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
CLI 等效命令（无需 agent）：`tree-sitter-analyzer --codegraph-status`

**在你自己的仓库上检查解析器行为**（无需安装，会先重建索引）：

```bash
uvx --from tree-sitter-analyzer miswire-audit .
```

该命令报告可能的跨语言名称冲突，供你检查自己仓库中的解析器行为。结果是诊断信息，不是竞争性 benchmark 主张。

---

## 为什么选择 Tree-sitter Analyzer

* **结构化输出。** MCP 响应使用标准 JSON 信封；载荷行为由响应契约测试保护。
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
| **JSON 输出** | 所有工具，默认 `output_format: "json"` | 标准结构化响应信封 |
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

### 356 个 CLI flag

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
tree-sitter-analyzer --uml class                  # Mermaid UML class 图
```

该软件包还保留了独立的文件列表辅助工具：

```bash
list-files <dir>          # fd 风格的文件发现
```

`search-content` 和 `find-and-grep` 已在 develop 分支中移除。详见
[迁移指南](docs/MIGRATION.md) 和 [`CLI codemap`](docs/CODEMAPS/cli.md)。

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
                       JSON 响应信封
                       (verdict + agent_summary + 数据)
                                    ↓
                       MCP 客户端 / CLI 消费者
```

这 8 个 MCP 工具提供索引查询和直接源代码分析。在查询索引中的符号或上下文前，先运行 `tree-sitter-analyzer --ast-cache --ast-cache-mode index --format json` 建立 AST 索引。源文件变更后使用 `index` action=sync 更新。索引查询复用已有 AST 数据；是否自动建索引取决于具体工具。

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
tree-sitter-analyzer --install-skills              # 安装到 ./.claude/skills/（仅本项目）
tree-sitter-analyzer --install-skills-global       # 安装到 ~/.claude/skills/（所有项目共用）
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

<details>
<summary><b>🐳 Docker</b>（本地没有 Python / uv）</summary>

本仓库自带 [`Dockerfile`](Dockerfile)，可从源码构建 MCP 服务器（stdio 传输），因此镜像始终与已提交的代码保持一致。

```bash
# 只需构建一次
docker build -t tree-sitter-analyzer-mcp .

# 针对当前仓库运行（服务器通过 stdio 提供 MCP；-i 保持 stdin 打开）
docker run --rm -i --user "$(id -u):$(id -g)" \
  -v "$PWD:/work" -w /work tree-sitter-analyzer-mcp
```

`--user "$(id -u):$(id -g)"` 会以你的宿主机 UID/GID 运行，因此绑定挂载的仓库下的 `.ast-cache/`、决策日志以及任何 `edit` 写入操作都归你所有，而不是 root。

MCP 客户端配置（容器内的项目根目录是挂载点 `/work`）：

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--user", "1000:1000",
        "-v", "/绝对路径/项目目录:/work",
        "-w", "/work",
        "-e", "TREE_SITTER_PROJECT_ROOT=/work",
        "tree-sitter-analyzer-mcp"
      ]
    }
  }
}
```
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

* **输出格式**：JSON。可显式指定 `output_format: "json"`。
* **项目根目录**：`TREE_SITTER_PROJECT_ROOT`（env，MCP）或 `--project-root`（CLI）。
* **缓存位置**：`<project>/.ast-cache/`。可安全删除 — 会自动重建。
* **可选**：`TREE_SITTER_OUTPUT_PATH` 用于大输出写入目标。

### 快照证据的平台范围

普通文件分析、索引创建/更新及既有索引查询，与认证快照访问相互独立。
Windows 既有操作路径不依赖新增的私有 WAL 快照内核。这些操作可以创建或更新
缓存；认证只读访问遵循独立的契约。

当前快照实现新增的是**仅限 POSIX 的私有数据库/WAL 证据捕获**，要求描述符相对
操作、`O_NOFOLLOW`、项目外的安全临时目录，以及 source、manifest、projection
检查全部成功。它**不交付 Windows 只读快照 parity**，也不扩大显式
`access_mode="read_existing"` 消费者已有的平台资格门。

develop 基线上的 Windows 快照认证原本就不可用，原因码为
`SECURE_FD_SNAPSHOT_UNSUPPORTED`；当前仍不可用，原因码改为
`WAL_PRIVATE_SNAPSHOT_UNSUPPORTED`，返回 `completeness="unknown"` 且没有
snapshot token。这不代表物理索引为空，也不代表普通查询被禁用。新增捕获路径
尚未完成 Windows 原生资格验证，本地能力契约测试不能代替该验证。

逐文件 `certified_at` 状态不能替代完整快照认证。`partial_at` 持久历史
**尚未实现，也不在本 PR 交付范围内**。不完整或无法验证的 projection 不能
授权认证消费者读取。

---

## 质量与测试

| 指标 | 值 |
|---|---|
| 测试通过 | 全面的测试套件 ✅ |
| 覆盖率 | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| 类型安全 | mypy |
| 平台 | 普通操作支持 macOS · Linux · Windows；快照证据适用上方更窄的范围 |
| Pre-commit 闸门 | ruff · bandit · mypy · pyupgrade · detect-secrets · tsa-codemap-sync |

```bash
uv run pytest -q                                # 有边界的本地快速闸门
uv run pytest tests/ -q --timeout=120 -m "not e2e and not network and not benchmark"  # 全面的本地测试套件
PYTEST_XDIST_AUTO_NUM_WORKERS=1 uv run pytest -q --maxfail=1                  # 快速闸门，单 worker（降低 CPU 负载）
PYTEST_XDIST_AUTO_NUM_WORKERS=2 uv run pytest -q --maxfail=1                  # 快速闸门，双 worker（均衡并行）
uv run pytest --lf --maxfail=1                  # 只重跑上次失败的测试
uv run python check_quality.py --new-code-only  # 质量闸门
```

---

## 故障排查

| 症状 | 修复 |
|---|---|
| `.swift / .kt / .rb / .php / .cs` 显示 `unsupported language` | 请更新到当前受支持的版本 — 该语言缺失问题已在 commit `50e99a8f` 中修复。extras 门控语言的语法模块不随基础安装捆绑；运行 `pip install "tree-sitter-analyzer[swift]"`（或 `kotlin`、`ruby`、`php`、`csharp`）补装。 |
| MCP 服务在客户端中不出现 | `TREE_SITTER_PROJECT_ROOT` 必须是**绝对路径**（例如 `$(pwd)` 或 `/home/user/project`）；相对路径会导致服务器解析到错误的目录。编辑配置后重启客户端。运行 `tree-sitter-analyzer --doctor` 可验证配置。 |
| `database is locked` | 关闭其他占用 `.ast-cache/index.db` 的进程；持续存在则运行 `rm -rf .ast-cache && tree-sitter-analyzer --full-index`。 |
| 首次调用慢或提示缺少索引 | 部分工具会自动预热索引。可在索引查询前先运行 `--full-index`。 |
| Agent 选错工具 | 使用 `tsa-*` skill（`/tsa-graph`、`/tsa-find` 等）— 每个 skill 把可见工具限定到其专属工作流。 |

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
