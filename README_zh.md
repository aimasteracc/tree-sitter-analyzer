# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **[日本語](README_ja.md)** | **简体中文**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-8942%20passed-brightgreen.svg)](#-质量与测试)
[![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Version](https://img.shields.io/badge/version-1.11.0-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

> 🔎 **面向大型仓库的 AI 证据式代码导航** - MCP 集成 · 最小上下文提取 · 无需重型预处理的搜索

*Claude 不需要读完整个代码库。你也不用了。*

---

## ✨ v1.11.0 最新更新

- **Claude 不读一行代码就知道项目骨架**: `get_project_summary` 返回 PageRank 排名的架构节点——所有其他类继承的那些类。已在 elasticsearch（4万文件）、spring-framework（1.1万）、mybatis、spring-petclinic 验证
- **碰关键类？Claude 先拦你**: `modification_guard` 读取架构排名。重命名 elasticsearch 的 `Writeable` → verdict UNSAFE、rank #1、4745 callers。零意外
- **新语言 = 新文件，不改已有代码**: 插件 `edge_extractors/` 包——Java、Python、TypeScript 开箱即用。添加 Kotlin 只需1个文件+1行注册
- **陌生项目探索效率翻倍**: 端到端实测——有 summary 5次工具调用 vs 没有10+次。Claude 跳过盲目搜索阶段
- **零配置的 first-party 过滤**: Java 从 pom.xml 读 groupId。Python 用 `sys.stdlib_module_names`。不需要维护任何黑名单

📖 完整版本历史请查看 **[更新日志](CHANGELOG.md)**。
---

---

## 🎬 功能演示

<!-- GIF占位符 - 创建说明请参见 docs/assets/demo-placeholder.md -->
*演示GIF即将推出 - 展示SMART工作流的AI集成*

---

## 🎯 Tree-sitter Analyzer 解决什么问题

Tree-sitter Analyzer 是一个开源的 MCP 和 CLI 工具集，帮助 AI 助手在大型代码库中只读取真正需要的部分。

- **不是整文件硬塞，而是最小上下文**: 在把代码交给 AI 之前，先缩小到最有用的代码片段
- **基于证据的分析**: 结合 tree-sitter 的结构解析与 `fd`、`ripgrep`，定位相关文件、符号和路径
- **不依赖重型预处理**: 对那些全库索引慢、易过期、难维护的复杂仓库更友好

### 常见使用场景

- 不把整个大文件都塞给 AI，也能理解某个超大文件或模块到底在做什么
- 在复杂仓库里追踪业务逻辑、UI 处理链路或与 bug 相关的代码路径
- 在 Java 等大型代码库中，先缩小 AI 所需上下文，再让它继续分析或修改

---

## 🚀 5分钟快速开始

### 前置条件

```bash
# 安装 uv (必需)
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 安装 fd + ripgrep (搜索功能必需)
brew install fd ripgrep          # macOS
winget install sharkdp.fd BurntSushi.ripgrep.MSVC  # Windows
```

📖 各平台详细安装说明请查看 **[安装指南](docs/installation.md)**。

### 验证安装

```bash
uv run tree-sitter-analyzer --show-supported-languages
```

---

## 🤖 AI集成

通过MCP协议配置AI助手使用Tree-sitter Analyzer。

当你的 AI 助手面对超大文件、噪音很多的全仓库上下文，或者一次性加载成本很高的遗留代码时，这种方式尤其有用。

### Claude Desktop / Cursor / Roo Code

添加到MCP配置：

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uvx",
      "args": [
        "--from", "tree-sitter-analyzer[mcp]",
        "tree-sitter-analyzer-mcp"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "/path/to/your/project",
        "TREE_SITTER_OUTPUT_PATH": "/path/to/output/directory"
      }
    }
  }
}
```

**配置文件位置:**
- **Claude Desktop**: `%APPDATA%\Claude\claude_desktop_config.json` (Windows) / `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
- **Cursor**: 内置MCP设置
- **Roo Code**: MCP配置

重启后，告诉AI: `请将项目根目录设置为: /path/to/your/project`

📖 完整API文档请查看 **[MCP工具参考](docs/api/mcp_tools_specification.md)**。

---

## 💻 常用CLI命令

### 安装

```bash
uv add "tree-sitter-analyzer[all,mcp]"  # 完整安装
```

### 最常用的5个命令

```bash
# 1. 分析文件结构
uv run tree-sitter-analyzer examples/BigService.java --table full

# 2. 快速摘要
uv run tree-sitter-analyzer examples/BigService.java --summary

# 3. 提取代码片段
uv run tree-sitter-analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106

# 4. 查找文件并搜索内容
uv run find-and-grep --roots . --query "class.*Service" --extensions java

# 5. 查询特定元素
uv run tree-sitter-analyzer examples/BigService.java --query-key methods --filter "public=true"
```

<details>
<summary>📋 查看输出示例</summary>

```
╭─────────────────────────────────────────────────────────────╮
│                   BigService.java 分析                       │
├─────────────────────────────────────────────────────────────┤
│ 总行数: 1419 | 代码: 906 | 注释: 246 | 空行: 267            │
│ 类: 1 | 方法: 66 | 字段: 9 | 平均复杂度: 5.27               │
╰─────────────────────────────────────────────────────────────╯
```

</details>

📖 完整命令和选项请查看 **[CLI参考手册](docs/cli-reference.md)**。

---

## 🌍 支持的语言

| 语言 | 支持级别 | 主要特性 |
|------|----------|----------|
| **Java** | ✅ 完整支持 | Spring、JPA、企业级特性 |
| **Python** | ✅ 完整支持 | 类型注解、装饰器 |
| **TypeScript** | ✅ 完整支持 | 接口、类型、TSX/JSX |
| **JavaScript** | ✅ 完整支持 | ES6+、React/Vue/Angular |
| **C** | ✅ 完整支持 | 函数、结构体、联合体、枚举、预处理器 |
| **C++** | ✅ 完整支持 | 类、模板、命名空间、继承 |
| **C#** | ✅ 完整支持 | Records、async/await、属性 |
| **SQL** | ✅ 增强支持 | 表、视图、存储过程、触发器 |
| **HTML** | ✅ 完整支持 | DOM结构、元素分类 |
| **CSS** | ✅ 完整支持 | 选择器、属性、分类 |
| **Go** | ✅ 完整支持 | 结构体、接口、goroutine |
| **Rust** | ✅ 完整支持 | Trait、impl块、宏 |
| **Kotlin** | ✅ 完整支持 | 数据类、协程 |
| **PHP** | ✅ 完整支持 | PHP 8+、属性、Trait |
| **Ruby** | ✅ 完整支持 | Rails模式、元编程 |
| **YAML** | ✅ 完整支持 | 锚点、别名、多文档 |
| **Markdown** | ✅ 完整支持 | 标题、代码块、表格 |

📖 语言特性详情请查看 **[功能文档](docs/features.md)**。

---

## 📊 功能概览

| 功能 | 描述 | 了解更多 |
|------|------|----------|
| **SMART工作流** | Set-Map-Analyze-Retrieve-Trace方法论 | [指南](docs/smart-workflow.md) |
| **MCP协议** | 原生AI助手集成 | [API文档](docs/api/mcp_tools_specification.md) |
| **Token优化** | 最高95%的Token减少 | [功能](docs/features.md) |
| **文件搜索** | 基于fd的高性能发现 | [CLI参考](docs/cli-reference.md) |
| **内容搜索** | ripgrep正则搜索 | [CLI参考](docs/cli-reference.md) |
| **安全性** | 项目边界保护 | [架构](docs/architecture.md) |

---

## 🔬 语法覆盖率（MECE框架）

Tree-sitter Analyzer 在所有17种支持语言的语法覆盖率验证中保证**零误报**。

### 第1阶段：MECE架构（2026-03）

**新架构**：
- 追踪**语法路径** `(node_type, parent_path)`，而非仅追踪节点类型
- 使用**精确节点身份匹配**（类型 + 字节范围 + 父节点链 + 文件路径）
- 消除嵌套节点误分类（包装节点不再导致误报）

---

## 🏆 质量与测试

| 指标 | 数值 |
|------|------|
| **测试** | 8,942 通过 ✅ |
| **覆盖率** | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| **类型安全** | 100% mypy合规 |
| **平台** | Windows、macOS、Linux |

```bash
# 运行测试
uv run pytest tests/ -v

# 生成覆盖率报告
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html
```

---

## 🔒 安全与架构

Tree-sitter Analyzer采用**默认安全**原则设计，专为AI辅助开发工作流程打造。

### 安全模型

**项目边界强制**
- 所有MCP工具都会根据项目根目录边界验证文件路径
- 无法访问配置的项目目录之外的文件
- 防止符号链接遍历
- 路径规范化防止 `../` 转义尝试

**输入验证**
- 对所有MCP工具参数进行JSON Schema验证
- 具有严格mypy合规性的类型安全Python API
- 在shell命令执行前对用户输入进行清理
- 对glob/regex搜索进行模式验证

**无远程执行**
- 100%本地处理——无云依赖
- 无遥测或数据收集
- 除可选的PyPI版本检查外无网络调用
- 源代码分析保留在您的计算机上

**安全默认值**
- 默认为只读文件操作
- 任何文件修改都需要明确选择加入
- 外部工具（fd、ripgrep）的沙盒子进程执行
- 环境变量隔离

### 架构原则

```
┌─────────────────────────────────────────────────────────┐
│  AI助手 (Claude Desktop / Cursor / Roo Code)           │
└────────────────────┬────────────────────────────────────┘
                     │ MCP协议 (JSON-RPC)
                     ▼
┌─────────────────────────────────────────────────────────┐
│  MCP服务器层                                            │
│  • 输入验证 (JSON Schema)                              │
│  • 项目边界检查                                         │
│  • 工具调度                                            │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│  分析引擎                                               │
│  • Tree-sitter AST解析 (17种语言)                      │
│  • 快速文件搜索 (fd)                                   │
│  • 内容搜索 (ripgrep)                                  │
│  • 输出格式化 (JSON / TOON)                            │
└─────────────────────────────────────────────────────────┘
```

**关键安全边界**：
1. **MCP协议**：AI只能调用经过验证模式的明确定义的工具
2. **项目根目录**：文件操作限制在配置的目录内
3. **只读**：没有明确的用户同意不进行破坏性操作
4. **本地优先**：所有处理都在您的计算机上进行

### 安全测试

- **8,942+自动化测试**包括以安全为重点的边缘案例
- **100% mypy类型安全**防止整类bug
- **CI/CD安全扫描**：Bandit（Python安全）、safety（依赖漏洞）
- **手动安全审查**所有MCP工具实现

### 报告安全问题

发现安全问题？请发送电子邮件至aimasteracc@gmail.com或在GitHub上开启私人安全咨询。

**我们不使用自动化安全徽章服务**——我们的安全态势是通过架构、测试和代码审查来记录的，而不是第三方评分。

---

## 🛠️ 开发

### 环境搭建

```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

### 质量检查

```bash
uv run pytest tests/ -v                    # 运行测试
uv run python check_quality.py --new-code-only  # 质量检查
uv run python llm_code_checker.py --check-all   # AI代码检查
```

📖 系统设计详情请查看 **[架构指南](docs/architecture.md)**。

---

## 🤝 贡献与许可

欢迎贡献！开发指南请查看 **[贡献指南](docs/CONTRIBUTING.md)**。

### ⭐ 支持我们

如果这个项目对你有帮助，请在GitHub上给我们一个 ⭐！

### 💝 赞助者

**[@o93](https://github.com/o93)** - 首席赞助者，支持MCP工具增强、测试基础设施和质量改进。

**[💖 赞助此项目](https://github.com/sponsors/aimasteracc)**

### 📄 许可证

MIT许可证 - 详见 [LICENSE](LICENSE) 文件。

---

## 🧪 测试

### 测试覆盖率

| 指标 | 值 |
|------|-----|
| **总测试数** | 8,942 测试 ✅ |
| **测试通过率** | 100% (8,942/8,942) |
| **代码覆盖率** | [![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer) |
| **类型安全** | 100% mypy合规 |

### 运行测试

```bash
# 运行所有测试
uv run pytest tests/ -v

# 运行特定测试类别
uv run pytest tests/unit/ -v              # 单元测试
uv run pytest tests/integration/ -v         # 集成测试
uv run pytest tests/regression/ -m regression  # 回归测试
uv run pytest tests/benchmarks/ -v         # 基准测试

# 包含覆盖率运行
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

# 运行基于属性的测试
uv run pytest tests/property/

# 运行性能基准测试
uv run pytest tests/benchmarks/ --benchmark-only
```

### 测试文档

| 文档 | 描述 |
|------|------|
| [测试编写指南](docs/test-writing-guide.md) | 测试编写的综合指南 |
| [回归测试指南](docs/regression-testing-guide.md) | Golden Master方法和回归测试 |
| [测试文档](docs/TESTING.md) | 项目测试标准 |

### 测试类别

- **单元测试** (8,942+ 测试总计): 隔离测试各个组件
- **回归测试** (70 测试): 确保向后兼容性和格式稳定性
- **属性测试** (75 测试): 基于Hypothesis的属性测试
- **基准测试** (20 测试): 性能监控和回归检测
- **兼容性测试** (30 测试): 跨版本兼容性验证

### CI/CD集成

- **测试覆盖率工作流**: PR和推送上的自动覆盖率检查
- **回归测试工作流**: Golden Master验证和格式稳定性检查
- **性能基准**: 每日基准运行和趋势分析
- **质量检查**: 自动化代码检查、类型检查和安全扫描

### 贡献测试

贡献新功能时：

1. **编写测试**: 遵循[测试编写指南](docs/test-writing-guide.md)
2. **确保覆盖率**: 维持80%以上的代码覆盖率
3. **本地运行**: `uv run pytest tests/ -v`
4. **检查质量**: `uv run ruff check . && uv run mypy tree_sitter_analyzer/`
5. **更新文档**: 记录新测试和功能

---

## 📚 文档

| 文档 | 描述 |
|------|------|
| [安装指南](docs/installation.md) | 各平台安装说明 |
| [CLI参考](docs/cli-reference.md) | 完整命令参考 |
| [SMART工作流](docs/smart-workflow.md) | AI辅助分析指南 |
| [MCP工具API](docs/api/mcp_tools_specification.md) | MCP集成详情 |
| [功能](docs/features.md) | 语言支持详情 |
| [架构](docs/architecture.md) | 系统设计 |
| [贡献](docs/CONTRIBUTING.md) | 开发指南 |
| [测试编写指南](docs/test-writing-guide.md) | 综合测试编写指南 |
| [回归测试指南](docs/regression-testing-guide.md) | Golden Master方法 |
| [更新日志](CHANGELOG.md) | 版本历史 |

---

**🎯 专为处理大型代码库和AI助手的开发者打造**

*让每一行代码都能被AI理解，让每个项目都能突破Token限制*
