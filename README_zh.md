# Tree-sitter Analyzer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1126%20passed-brightgreen.svg)](#testing)

**解决大型代码文件的LLM令牌限制问题。**

一个可扩展的多语言代码分析器，帮助AI助手理解代码结构而无需读取整个文件。获取代码概览、提取特定部分、分析复杂度——全部针对LLM工作流程进行优化。

## ✨ 为什么选择Tree-sitter Analyzer？

**问题：** 大型代码文件超出LLM令牌限制，使代码分析变得低效或不可能。

**解决方案：** 智能代码分析提供：
- 📊 **代码概览** 无需读取完整文件
- 🎯 **目标提取** 特定行范围
- 📍 **精确定位** 准确的代码操作
- 🤖 **AI助手集成** 通过MCP协议

## 🚀 快速开始（5分钟）

### 面向AI助手用户（Claude Desktop）

1. **安装包：**
```bash
# 安装uv（快速Python包管理器）
curl -LsSf https://astral.sh/uv/install.sh | sh  # macOS/Linux
# 或者：powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows

# 无需单独安装包 - uv会处理
```

2. **配置Claude Desktop：**

添加到您的Claude Desktop配置文件：

**Windows：** `%APPDATA%\Claude\claude_desktop_config.json`
**macOS：** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Linux：** `~/.config/claude/claude_desktop_config.json`

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

3. **重启Claude Desktop** 并开始分析代码！

### 面向CLI用户

```bash
# 使用uv安装（推荐）
uv add "tree-sitter-analyzer[popular]"

# 步骤1：检查文件规模
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text

# 步骤2：分析结构（针对大文件）
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full

# 步骤3：提取特定行
uv run python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
```

## 🛠️ 核心功能

### 1. 代码结构分析
获取全面概览而无需读取整个文件：
- 类、方法、字段计数
- 包信息
- 导入依赖
- 复杂度指标

### 2. 目标代码提取
高效提取特定代码部分：
- 行范围提取
- 精确定位数据
- 内容长度信息

### 3. AI助手集成
为AI助手提供四个强大的MCP工具：
- `analyze_code_scale` - 获取代码指标和复杂度
- `analyze_code_structure` - 生成详细结构表
- `read_code_partial` - 提取特定行范围
- `analyze_code_universal` - 通用分析与自动检测

### 4. 多语言支持
- **Java** - 完整支持与高级分析
- **Python** - 完整支持
- **JavaScript/TypeScript** - 完整支持
- **C/C++、Rust、Go** - 基础支持

## 📖 使用示例

### AI助手使用（通过Claude Desktop）

**步骤1：获取代码概览：**
> "这个Java文件examples/Sample.java的整体复杂度和大小如何？"

**步骤2：分析代码结构（针对大文件）：**
> "请分析examples/Sample.java的结构并显示详细表格"

**步骤3：提取特定代码：**
> "显示examples/Sample.java的第84-86行"

### CLI使用

**步骤1：基础分析（检查文件规模）：**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text
```

**步骤2：结构分析（针对超出LLM限制的大文件）：**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full
```

**步骤3：目标提取（读取特定代码部分）：**
```bash
uv run python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
```

**其他选项：**
```bash
# 静默模式（抑制INFO消息，仅显示错误）
uv run python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text --quiet

# 表格输出与静默模式
uv run python -m tree_sitter_analyzer examples/Sample.java --table=full --quiet
```

## 🔧 安装选项

### 面向最终用户
```bash
# 基础安装
uv add tree-sitter-analyzer

# 包含流行语言（Java、Python、JS、TS）
uv add "tree-sitter-analyzer[popular]"

# 包含MCP服务器支持
uv add "tree-sitter-analyzer[mcp]"

# 完整安装
uv add "tree-sitter-analyzer[all,mcp]"
```

### 面向开发者
```bash
# 克隆并安装用于开发
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

## 📚 文档

- **[用户MCP设置指南](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/MCP_SETUP_USERS.md)** - AI助手用户的简单设置
- **[开发者MCP设置指南](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/MCP_SETUP_DEVELOPERS.md)** - 本地开发配置
- **[API文档](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/docs/api.md)** - 详细API参考
- **[贡献指南](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CONTRIBUTING.md)** - 如何贡献

## 🧪 测试

本项目通过**1126个测试**维护高代码质量。

```bash
# 运行测试
pytest tests/ -v

# 运行覆盖率测试
pytest tests/ --cov=tree_sitter_analyzer
```

## 📄 许可证

MIT许可证 - 详见[LICENSE](LICENSE)文件。

## 🤝 贡献

我们欢迎贡献！请查看我们的[贡献指南](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CONTRIBUTING.md)了解详情。

### 🤖 AI/LLM协作

本项目支持AI辅助开发，具有专门的质量控制：

```bash
# 面向AI系统 - 生成代码前运行
python check_quality.py --new-code-only
python llm_code_checker.py --check-all

# 面向AI生成代码审查
python llm_code_checker.py path/to/new_file.py
```

📖 **查看我们的[AI协作指南](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/AI_COLLABORATION_GUIDE.md)和[LLM编码指南](https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/LLM_CODING_GUIDELINES.md)了解与AI系统协作的详细说明。**

---

**为处理大型代码库和AI助手的开发者用❤️制作。**
