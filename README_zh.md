# Tree-sitter Analyzer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1358%20passed-brightgreen.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-74.82%25-green.svg)](#testing)
[![Quality](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#quality)

**解决大型代码文件的 LLM Token 限制问题。**

一个可扩展的多语言代码分析器，帮助 AI 助手在无需读取整文件的情况下理解代码结构。可获取代码概览、按行区间抽取片段、分析复杂度——全部针对 LLM 工作流优化。

## ✨ 为什么选择 Tree-sitter Analyzer？

**问题：** 大型代码文件会超出 LLM Token 限制，导致分析困难。

**解决方案：** 智能代码分析提供：
- 📊 **代码概览** 无需读完整文件
- 🎯 **目标提取** 精确的行区间抽取
- 📍 **精确定位** 便于后续代码操作
- 🤖 **AI 助手集成** 通过 MCP 协议

## 🚀 5 分钟快速开始

### 面向 AI 助手用户（Claude Desktop）

1. **安装：**
```bash
# 安装 uv（快速 Python 包管理器）
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# 或：powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# 无需单独安装本包，uv 会自动处理
```

2. **配置 Claude Desktop：**

将以下内容添加到设置文件：

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux:** `~/.config/claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "tree-sitter-analyzer[mcp]",
        "python",
        "-m",
        "tree_sitter_analyzer.mcp.server"
      ]
    }
  }
}
```

3. **重启 Claude Desktop** 开始分析代码！

### 面向 CLI 用户

```bash
# 使用 uv 安装（推荐）
uv add "tree-sitter-analyzer[popular]"

# 步骤 1：检查文件规模
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text

# 步骤 2：分析结构（针对大文件）
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full

# 步骤 3：按行抽取片段
uv run python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
```

## 🛠️ 核心功能

### 1. 代码结构分析
无需读全文件即可获取：
- 类、方法、字段数量
- 包信息
- 导入依赖
- 复杂度指标

### 2. 目标代码抽取
高效提取指定代码区间：
- 行范围抽取
- 位置元数据
- 内容长度信息

### 3. AI 助手集成（MCP）
三步工作流工具：
- `check_code_scale` - 第一步：文件规模与复杂度
- `analyze_code_structure` - 第二步：生成带行号的结构表
- `extract_code_section` - 第三步：按行范围抽取代码

### 4. 多语言支持
- **Java** - 完整支持与高级分析
- **Python** - 完整支持
- **JavaScript/TypeScript** - 完整支持
- **C/C++、Rust、Go** - 基础支持

## 📖 使用示例

### AI 助手（通过 Claude Desktop）

**步骤 1：检查规模**
```
使用工具：check_code_scale
参数：{"file_path": "examples/Sample.java"}
```

**步骤 2：结构分析（>100 行建议执行）**
```
使用工具：analyze_code_structure
参数：{"file_path": "examples/Sample.java", "format_type": "full"}
```

**步骤 3：按行抽取（利用步骤 2 的行号）**
```
使用工具：extract_code_section
参数：{"file_path": "examples/Sample.java", "start_line": 84, "end_line": 86}
```

> 注意：参数一律使用 snake_case：`file_path`, `start_line`, `end_line`, `format_type`

### CLI 使用

**步骤 1：基础分析（检查文件规模）**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text
```

**步骤 2：结构分析（大文件推荐）**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full
```

**步骤 3：目标抽取（读取特定片段）**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
```

**其他选项：**
```bash
# 静默模式（抑制 INFO，仅显示错误）
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text --quiet

# 配合静默模式输出表格
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full --quiet
```

## 🔧 安装选项

### 最终用户
```bash
# 基础安装
uv add tree-sitter-analyzer

# 流行语言（Java、Python、JS、TS）
uv add "tree-sitter-analyzer[popular]"

# 启用 MCP 服务器支持
uv add "tree-sitter-analyzer[mcp]"

# 完整安装
uv add "tree-sitter-analyzer[all,mcp]"
```

### 开发者
```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

## 📚 文档

- **[面向用户的 MCP 设置指南](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/MCP_SETUP_USERS.md)**
- **[面向开发者的 MCP 设置指南](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/MCP_SETUP_DEVELOPERS.md)**
- **[项目根目录配置](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/PROJECT_ROOT_CONFIG.md)**
- **[API 文档](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/docs/api.md)**
- **[贡献指南](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CONTRIBUTING.md)**

### 🔒 项目根目录配置

Tree-sitter-analyzer 自动检测并加固项目边界：

- 自动检测：基于 `.git`、`pyproject.toml`、`package.json` 等
- CLI：`--project-root /path/to/project`
- MCP：设置环境变量 `TREE_SITTER_PROJECT_ROOT=${workspaceFolder}`
- 安全性：仅分析项目边界内的文件

**推荐 MCP 配置：**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "--with", "tree-sitter-analyzer[mcp]", "python", "-m", "tree_sitter_analyzer.mcp.server"],
      "env": {"TREE_SITTER_PROJECT_ROOT": "${workspaceFolder}"}
    }
  }
}
```

## 🧪 测试与质量

本项目保持企业级质量，测试完善：

### 📊 质量指标
- **1358 个测试** - 100% 通过 ✅
- **74.82% 覆盖率** - 行业标准
- **跨平台** - Windows / macOS / Linux

### 🏆 最近质量成果（v0.8.2）
- ✅ 测试套稳定化 - 修复所有 31 个失败用例
- ✅ 格式化模块覆盖率从 0% → 42.30%
- ✅ 错误处理覆盖率 61.64% → 82.76%
- ✅ 新增 104 个关键模块测试

### 🔧 运行测试
```bash
pytest tests/ -v

pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

pytest tests/test_formatters_comprehensive.py -v
pytest tests/test_core_engine_extended.py -v
pytest tests/test_mcp_server_initialization.py -v
```

### 📈 覆盖率亮点
- 格式化器：42.30%
- 错误处理：82.76%
- 语言检测：98.41%
- CLI 主入口：97.78%
- 安全框架：78%+

## 📄 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE)。

## 🤝 贡献

欢迎贡献！请参阅我们的 [贡献指南](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CONTRIBUTING.md)。

### 🤖 AI/LLM 协作

本项目支持 AI 辅助开发并提供专门质量控制：

```bash
# AI 系统在生成代码前执行
python check_quality.py --new-code-only
python llm_code_checker.py --check-all

# AI 生成代码的审查
python llm_code_checker.py path/to/new_file.py
```

📖 参阅 [AI 协作指南](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/AI_COLLABORATION_GUIDE.md) 与 [LLM 编码规范](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/LLM_CODING_GUIDELINES.md)。

---

**献给处理大型代码库与 AI 助手的开发者。**
