# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **[日本語](README_ja.md)** | **简体中文**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-6246%20passed-brightgreen.svg)](#-质量与测试)
[![Coverage](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![Version](https://img.shields.io/badge/version-1.10.0-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

> 🚀 **AI时代的企业级代码分析工具** - 深度AI集成 · 强大搜索 · 17种语言 · 智能分析

---

## ✨ v1.10.0 最新更新

- **格式变更管理系统**: 新增格式变更检测和行为配置文件比较功能
- **增强语言支持**: Go、Rust、Kotlin现已成为核心依赖
- **C++格式化器**: 新增C++代码格式化支持
- **项目治理**: 添加CODE_OF_CONDUCT.md和GOVERNANCE.md
- **6,246个测试** 100%通过率，80.33%覆盖率

📖 完整版本历史请查看 **[更新日志](CHANGELOG.md)**。

---

## 🎬 功能演示

<!-- GIF占位符 - 创建说明请参见 docs/assets/demo-placeholder.md -->
*演示GIF即将推出 - 展示SMART工作流的AI集成*

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

## 🏆 质量与测试

| 指标 | 数值 |
|------|------|
| **测试** | 6,246 通过 ✅ |
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
| [更新日志](CHANGELOG.md) | 版本历史 |

---

**🎯 专为处理大型代码库和AI助手的开发者打造**

*让每一行代码都能被AI理解，让每个项目都能突破Token限制*
