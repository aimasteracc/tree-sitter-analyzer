# Tree-sitter Analyzer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1358%20passed-brightgreen.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-74.54%25-green.svg)](#testing)
[![Quality](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#quality)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

## � 突破  LLM Token 限制，让 AI 理解任意大小的代码文件

> **一个革命性的代码分析工具，专为 AI 时代设计**

想象一下：你有一个 1,400+ 行的 Java 服务类，Claude 或 ChatGPT 因为 token 限制无法分析。现在，Tree-sitter Analyzer 让 AI 助手能够：

- ⚡ **3 秒内**获取完整代码结构概览
- 🎯 **精确提取**任意行范围的代码片段  
- 📍 **智能定位**类、方法、字段的确切位置
- 🔗 **无缝集成** Claude Desktop、Cursor、Roo Code 等 AI IDE

**不再因为文件太大而让 AI 束手无策！**

---

## 🚀 30 秒快速体验

### 🤖 AI 用户（Claude Desktop、Cursor、Roo Code 等）

**📦 1. 一键安装**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**⚙️ 2. 配置 AI 客户端**

**Claude Desktop 配置：**

将以下内容添加到配置文件：
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`  
- **Linux**: `~/.config/claude/claude_desktop_config.json`

**基础配置（推荐）：**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ]
    }
  }
}
```

**高级配置（指定项目根目录）：**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run", "--with", "tree-sitter-analyzer[mcp]",
        "python", "-m", "tree_sitter_analyzer.mcp.server"
      ],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project"
      }
    }
  }
}
```

**其他 AI 客户端：**
- **Cursor**: 内置 MCP 支持，参考 Cursor 文档配置
- **Roo Code**: 支持 MCP 协议，查看相应配置指南
- **其他 MCP 兼容客户端**: 使用相同的服务器配置

**⚠️ 配置说明：**
- **基础配置**: 工具会自动检测项目根目录（推荐）
- **高级配置**: 如需指定特定目录，请使用绝对路径替换 `/absolute/path/to/your/project`
- **避免使用**: `${workspaceFolder}` 等变量在某些客户端中可能不被支持

**🎉 3. 重启 AI 客户端，开始分析巨型代码文件！**

### 💻 开发者（CLI）

```bash
# 安装
uv add "tree-sitter-analyzer[popular]"

# 检查文件规模（1419 行大型服务类，瞬间完成）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 生成结构表格（1 个类，66 个方法，清晰展示）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 精确提取代码片段
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105
```

---

## ❓ 为什么选择 Tree-sitter Analyzer？

### � 解决真实痛点点

**传统方式的困境：**
- ❌ 大文件超出 LLM token 限制
- ❌ AI 无法理解代码结构
- ❌ 需要手动拆分文件
- ❌ 上下文丢失，分析不准确

**Tree-sitter Analyzer 的突破：**
- ✅ **智能分析**：无需读取完整文件即可理解结构
- ✅ **精确定位**：准确到行号的代码提取
- ✅ **AI 原生**：专为 LLM 工作流优化
- ✅ **多语言支持**：Java、Python、JavaScript/TypeScript 等

### ✨ 核心优势

#### ⚡ **闪电般的分析速度**
```bash
# 1419 行大型 Java 服务类分析结果（< 1 秒）
Lines: 1419 | Classes: 1 | Methods: 66 | Fields: 9 | Imports: 8
```

#### 📊 **精确的结构表格**
| 类名 | 类型 | 可见性 | 行范围 | 方法数 | 字段数 |
|------|------|--------|--------|--------|--------|
| BigService | class | public | 17-1419 | 66 | 9 |

#### 🔄 **AI 助手三步工作流**
- **Step 1**: `check_code_scale` - 检查文件规模和复杂度
- **Step 2**: `analyze_code_structure` - 生成详细结构表格
- **Step 3**: `extract_code_section` - 按需提取代码片段

---

## 🛠️ 强大功能一览

### � ***代码结构分析**
无需读取完整文件，即可获得：
- 类、方法、字段统计
- 包信息和导入依赖
- 复杂度指标
- 精确的行号定位

### ✂️ **智能代码提取**
- 按行范围精确提取
- 保持原始格式和缩进
- 包含位置元数据
- 支持大文件高效处理

### 🔗 **AI 助手集成**
通过 MCP 协议深度集成：
- Claude Desktop
- Cursor IDE  
- Roo Code
- 其他支持 MCP 的 AI 工具

### � **多语言言支持**
- **Java** - 完整支持，包括 Spring、JPA 等框架
- **Python** - 完整支持，包括类型注解、装饰器
- **JavaScript/TypeScript** - 完整支持，包括 ES6+ 特性
- **C/C++、Rust、Go** - 基础支持

---

## 📖 实战示例

### 💬 AI IDE 提示词（复制即用）

#### 🔍 **步骤1：检查文件规模**

**提示词：**
```
使用 MCP 工具 check_code_scale 分析文件规模
参数：{"file_path": "examples/BigService.java"}
```

**返回格式：**
```json
{
  "file_path": "examples/BigService.java",
  "language": "java",
  "metrics": {
    "lines_total": 1419,
    "lines_code": 1419,
    "elements": {
      "classes": 1,
      "methods": 66,
      "fields": 9
    }
  }
}
```

#### 📊 **步骤2：生成结构表格**

**提示词：**
```
使用 MCP 工具 analyze_code_structure 生成详细结构
参数：{"file_path": "examples/BigService.java"}
```

**返回格式：**
- 完整的 Markdown 表格
- 包含类信息、方法列表（含行号）、字段列表
- 方法签名、可见性、行范围、复杂度等详细信息

#### ✂️ **步骤3：提取代码片段**

**提示词：**
```
使用 MCP 工具 extract_code_section 提取指定代码段
参数：{"file_path": "examples/BigService.java", "start_line": 100, "end_line": 105}
```

**返回格式：**
```json
{
  "file_path": "examples/BigService.java",
  "range": {"start_line": 100, "end_line": 105},
  "content": "实际代码内容...",
  "content_length": 245
}
```

#### 💡 **重要提示**
- **参数格式**：使用 snake_case（`file_path`、`start_line`、`end_line`）
- **路径处理**：相对路径自动解析到项目根目录
- **安全保护**：工具自动进行项目边界检查
- **工作流程**：建议按步骤1→2→3的顺序使用

### � CLI 命令示例

```bash
# 快速分析（1419行大文件，瞬间完成）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 详细结构表格（66个方法清晰展示）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 精确代码提取（内存使用监控代码片段）
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105

# 静默模式（仅显示结果）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --quiet
```

---

## �  安装选项

### 👤 **最终用户**
```bash
# 基础安装
uv add tree-sitter-analyzer

# 热门语言包（推荐）
uv add "tree-sitter-analyzer[popular]"

# MCP 服务器支持
uv add "tree-sitter-analyzer[mcp]"

# 完整安装
uv add "tree-sitter-analyzer[all,mcp]"
```

### �‍ **开发者**
```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

---

## 🔒 安全与配置

### 🛡️ **项目边界保护**

Tree-sitter Analyzer 自动检测并保护项目边界：

- **自动检测**：基于 `.git`、`pyproject.toml`、`package.json` 等
- **CLI 控制**：`--project-root /path/to/project`
- **MCP 集成**：`TREE_SITTER_PROJECT_ROOT=/path/to/project` 或使用自动检测
- **安全保障**：仅分析项目边界内的文件

**推荐 MCP 配置：**

**方案一：自动检测（推荐）**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "--with", "tree-sitter-analyzer[mcp]", "python", "-m", "tree_sitter_analyzer.mcp.server"]
    }
  }
}
```

**方案二：手动指定项目根目录**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "--with", "tree-sitter-analyzer[mcp]", "python", "-m", "tree_sitter_analyzer.mcp.server"],
      "env": {"TREE_SITTER_PROJECT_ROOT": "/path/to/your/project"}
    }
  }
}
```

---

## 🏆 企业级质量保证

### � **质量指标**
- **1,358 个测试** - 100% 通过率 ✅
- **74.54% 代码覆盖率** - 行业领先水平
- **零测试失败** - 完整 CI/CD 就绪
- **跨平台兼容** - Windows、macOS、Linux

### �  **最新质量成果（v0.9.4）**
- ✅ **测试套件完全稳定** - 修复所有历史问题
- ✅ **格式化模块突破** - 覆盖率大幅提升
- ✅ **错误处理优化** - 企业级异常处理
- ✅ **新增 100+ 综合测试** - 覆盖关键模块

### ⚙️ **运行测试**
```bash
# 运行所有测试
uv run pytest tests/ -v

# 生成覆盖率报告
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

# 运行特定测试
uv run pytest tests/test_mcp_server_initialization.py -v
```

### � **覆覆盖率亮点**
- **语言检测器**：98.41% （优秀）
- **CLI 主入口**：97.78% （优秀）
- **错误处理**：82.76% （良好）
- **安全框架**：78%+ （可靠）

---

## 🤖 AI 协作支持

### ⚡ **专为 AI 开发优化**

本项目支持 AI 辅助开发，提供专门的质量控制：

```bash
# AI 系统代码生成前检查
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all

# AI 生成代码审查
uv run python llm_code_checker.py path/to/new_file.py
```

📖 **详细指南**：
- [AI 协作指南](AI_COLLABORATION_GUIDE.md)
- [LLM 编码规范](LLM_CODING_GUIDELINES.md)

---

## 📚 完整文档

- **[用户 MCP 设置指南](MCP_SETUP_USERS.md)** - 简单配置指南
- **[开发者 MCP 设置指南](MCP_SETUP_DEVELOPERS.md)** - 本地开发配置
- **[项目根目录配置](PROJECT_ROOT_CONFIG.md)** - 完整配置参考
- **[API 文档](docs/api.md)** - 详细 API 参考
- **[贡献指南](CONTRIBUTING.md)** - 如何参与贡献

---

## 🤝 参与贡献

我们欢迎各种形式的贡献！请查看 [贡献指南](CONTRIBUTING.md) 了解详情。

### ⭐ **给我们一个 Star！**

如果这个项目对你有帮助，请在 GitHub 上给我们一个 ⭐，这是对我们最大的支持！

---

## 📄 开源协议

MIT 协议 - 详见 [LICENSE](LICENSE) 文件。

---

## 🎯 总结

Tree-sitter Analyzer 是 AI 时代的必备工具：

- **解决核心痛点** - 让 AI 突破大文件的 token 限制
- **企业级质量** - 1,358 个测试，74.54% 覆盖率
- **开箱即用** - 30 秒配置，支持主流 AI 客户端
- **多语言支持** - Java、Python、JavaScript/TypeScript 等
- **活跃维护** - v0.9.4 最新版本，持续更新

**立即体验** → [30 秒快速体验](#🚀-30-秒快速体验)

---

**�  专为处理大型代码库和 AI 助手的开发者打造**

*让每一行代码都被 AI 理解，让每一个项目都突破 token 限制*
