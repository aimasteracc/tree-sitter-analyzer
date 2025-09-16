# Tree-sitter Analyzer

[![Python版本](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![许可证](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![测试](https://img.shields.io/badge/tests-1699%20passed-brightgreen.svg)](#质量保证)
[![覆盖率](https://img.shields.io/badge/coverage-74.42%25-green.svg)](#质量保证)
[![质量](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#质量保证)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![版本](https://img.shields.io/badge/version-1.3.5-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

## 🚀 突破LLM token限制，让AI理解任意大小的代码文件

> **为AI时代设计的革命性代码分析工具**

## 📋 目录

- [🚀 突破LLM token限制](#-突破llm-token限制让ai理解任意大小的代码文件)
- [📋 目录](#-目录)
- [💡 独特之处](#-独特之处)
- [📊 实时演示和结果](#-实时演示和结果)
- [🚀 30秒快速开始](#-30秒快速开始)
  - [🤖 AI用户（Claude Desktop、Cursor等）](#-ai用户claude-desktopcursor等)
  - [💻 开发者（CLI）](#-开发者cli)
- [❓ 为什么选择Tree-sitter Analyzer](#-为什么选择tree-sitter-analyzer)
- [📖 实际使用示例](#-实际使用示例)
- [🛠️ 核心功能](#️-核心功能)
- [📦 安装指南](#-安装指南)
- [🔒 安全和配置](#-安全和配置)
- [🏆 质量保证](#-质量保证)
- [🤖 AI协作支持](#-ai协作支持)
- [📚 文档](#-文档)
- [🤝 贡献](#-贡献)
- [📄 许可证](#-许可证)

## 💡 独特之处

想象一下：你有一个1400多行的Java服务类，Claude或ChatGPT因为token限制无法分析。现在，Tree-sitter Analyzer让AI助手能够：

- ⚡ **3秒获得完整代码结构概览**
- 🎯 **精确提取**任意行范围的代码片段
- 📍 **智能定位**类、方法、字段的确切位置
- 🔗 **无缝集成**Claude Desktop、Cursor、Roo Code等AI IDE
- 🏗️ **统一元素管理** - 所有代码元素（类、方法、字段、导入）在一个统一的系统中

**再也不用因为大文件而让AI束手无策！**

## 📊 实时演示和结果

### ⚡ **闪电般的分析速度**
```bash
# 1419行大型Java服务类分析结果（< 1秒）
Lines: 1419 | Classes: 1 | Methods: 66 | Fields: 9 | Imports: 8 | Packages: 1
Total Elements: 85 | Complexity: 348 (avg: 5.27, max: 15)
```

### 📊 **精确的结构表格**
| 类名 | 类型 | 可见性 | 行范围 | 方法数 | 字段数 |
|------|------|--------|--------|---------|--------|
| BigService | class | public | 17-1419 | 66 | 9 |

### 🔄 **AI助手SMART工作流程**
- **S**: `set_project_path` - 设置项目根目录
- **M**: `list_files`, `search_content`, `find_and_grep` - 精确映射目标文件
- **A**: `analyze_code_structure` - 分析核心结构与统一元素
- **R**: `extract_code_section` - 按需检索关键代码片段
- **T**: 高级依赖追踪（需要时）

---

## 🚀 30秒快速开始

### 🤖 AI用户（Claude Desktop、Cursor等）

**📋 0. 前提要求（高级MCP工具）**
要使用高级文件搜索和内容分析功能，请先安装这些工具：
```bash
# 安装fd和ripgrep（详细说明请参阅前提要求部分）
# macOS
brew install fd ripgrep

# Windows（使用winget - 推荐）
winget install sharkdp.fd BurntSushi.ripgrep.MSVC

# Windows（其他方式）
# choco install fd ripgrep
# scoop install fd ripgrep

# Ubuntu/Debian
sudo apt install fd-find ripgrep
```

**📦 1. 一键安装**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**⚙️ 2. 配置AI客户端**

**Claude Desktop配置：**

将以下内容添加到您的配置文件：
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

**其他AI客户端：**
- **Cursor**: 内置MCP支持，参考Cursor文档进行配置
- **Roo Code**: 支持MCP协议，查看相应配置指南
- **其他MCP兼容客户端**: 使用相同的服务器配置

**⚠️ 配置注意事项：**
- **基础配置**: 工具将自动检测项目根目录（推荐）
- **高级配置**: 如需指定特定目录，请用绝对路径替换`/absolute/path/to/your/project`
- **避免使用**: `${workspaceFolder}`等变量在某些客户端中可能不受支持

**🎉 3. 重启AI客户端，开始分析大型代码文件！**

### 💻 开发者（CLI）

```bash
# 安装
uv add "tree-sitter-analyzer[popular]"

# 检查文件规模（1419行大型服务类，瞬间完成）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 生成结构表格（1个类，66个方法，清晰展示）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 精确代码提取
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105
```

---

## ❓ 为什么选择Tree-sitter Analyzer

### 🎯 解决真实痛点

**传统方法的困境：**
- ❌ 大文件超出LLM token限制
- ❌ AI无法理解代码结构
- ❌ 需要手动分割文件
- ❌ 上下文丢失导致分析不准确

**Tree-sitter Analyzer的突破：**
- ✅ **智能分析**: 不读取完整文件即可理解结构
- ✅ **精确定位**: 准确的逐行代码提取
- ✅ **AI原生**: 针对LLM工作流优化
- ✅ **多语言支持**: Java、Python、JavaScript/TypeScript等

## 📖 实际使用示例

### 💬 AI IDE 提示词（SMART分析工作流程）

> **✅ 测试验证状态：** 以下所有提示词都已在真实环境中测试验证，确保100%可用
>
> **🎯 SMART分析工作流程：**
> - **S** - 设置项目 (set_project_path)
> - **M** - 映射目标文件 (精确模式匹配)
> - **A** - 分析核心结构 (analyze_code_structure)
> - **R** - 检索关键代码 (extract_code_section)
> - **T** - 追踪依赖关系 (需要时)
>
> **⚠️ 重要提示：**
> - 遵循SMART工作流程顺序以获得最佳结果
> - 对于项目内的文件，使用**相对路径**（例如：`examples/BigService.java`）
> - 对于项目外的文件，使用**绝对路径**（例如：`C:\git-public\tree-sitter-analyzer\examples\BigService.java`）
> - 所有工具都支持Windows和Unix风格的路径
> - 项目路径应该指向您的代码仓库根目录

#### 🔧 **S - 设置项目（必需的第一步）**

**选项1：在MCP设置中配置**
```json
{
  "mcpServers": {
    "tree-sitter-analyzer": {
      "command": "uv",
      "args": ["run", "python", "-m", "tree_sitter_analyzer.mcp.server"],
      "env": {
        "TREE_SITTER_PROJECT_ROOT": "/path/to/your/project"
      }
    }
  }
}
```

**选项2：直接告诉AI（推荐，更自然）**

**方式1：明确请求设置**
```
请帮我设置项目根目录，路径是：C:\git-public\tree-sitter-analyzer
```

**方式2：提供项目信息**
```
我的项目在：C:\git-public\tree-sitter-analyzer
请设置这个路径作为项目根目录
```

**方式3：简单说明**
```
项目路径：C:\git-public\tree-sitter-analyzer
```

**AI会自动调用相应的工具来设置路径，无需记住复杂的命令格式**

#### 🗺️ **M - 映射目标文件（精确模式匹配）**

> **📋 前提要求：** 此步骤需要安装`fd`和`ripgrep`工具。请参阅[前提要求](#前提要求)部分的安装说明。

**智能文件发现：**
```
查找项目中的所有Python文件
```

```
列出大于10KB的所有Java文件
```

```
查找项目中的配置文件（*.json, *.yaml, *.toml）
```

**智能内容搜索：**
```
在所有Python文件中搜索"def authenticate"并显示上下文
```

```
在源文件中查找所有TODO注释
```

```
在所有文件中搜索"class.*Service"模式，不区分大小写
```

**组合发现与搜索：**
```
查找所有Python文件并搜索"async def"函数
```

```
在所有源文件中搜索"class.*Service"
```

**返回格式：**
```json
{
  "success": true,
  "results": [
    {
      "file": "tree_sitter_analyzer/core/query_service.py",
      "line": 20,
      "text": "class QueryService:",
      "matches": [[0, 18]]
    }
  ],
  "count": 25,
  "meta": {
    "searched_file_count": 256,
    "truncated": false,
    "fd_elapsed_ms": 225,
    "rg_elapsed_ms": 2969
  }
}
```

#### 🔍 **A - 分析核心结构**

**方式1：明确请求分析**
```
请帮我分析这个文件：examples/BigService.java
```

**方式2：描述分析需求**
```
我想了解这个Java文件的规模和结构：examples/BigService.java
```

**方式3：简单请求**
```
分析这个文件：examples/BigService.java
```

**使用绝对路径的替代方案：**
```
请分析这个文件：C:\git-public\tree-sitter-analyzer\examples\BigService.java
```

**返回格式：**
```json
{
  "file_path": "examples/BigService.java",
  "language": "java",
  "metrics": {
    "lines_total": 1419,
    "lines_code": 907,
    "lines_comment": 246,
    "lines_blank": 267,
    "elements": {
      "classes": 1,
      "methods": 66,
      "fields": 9,
      "imports": 8,
      "packages": 1,
      "total": 85
    },
    "complexity": {
      "total": 348,
      "average": 5.27,
      "max": 15
    }
  }
}
```

#### 📊 **R - 检索关键代码**

**方式1：明确请求表格**
```
请生成这个文件的详细结构表格：examples/BigService.java
```

**方式2：描述表格需求**
```
我想看这个Java文件的完整结构，包括所有类、方法和字段：examples/BigService.java
```

**方式3：简单请求**
```
生成结构表格：examples/BigService.java
```

**使用绝对路径的替代方案：**
```
请生成详细结构表格：C:\git-public\tree-sitter-analyzer\examples\BigService.java
```

**返回格式：**
- 完整的Markdown表格
- 包括类信息、方法列表（带行号）、字段列表
- 方法签名、可见性、行范围、复杂度等详细信息

#### ✂️ **精确代码提取**

**方式1：明确请求提取**
```
请提取这个文件的第93-105行代码：examples/BigService.java
```

**方式2：描述提取需求**
```
我想看这个Java文件第93行到105行的代码内容：examples/BigService.java
```

**方式3：简单请求**
```
提取第93-105行代码：examples/BigService.java
```

**使用绝对路径的替代方案：**
```
请提取代码片段：C:\git-public\tree-sitter-analyzer\examples\BigService.java，第93-105行
```

**返回格式：**
```json
{
  "file_path": "examples/BigService.java",
  "range": {
    "start_line": 93,
    "end_line": 105,
    "start_column": null,
    "end_column": null
  },
  "content": "    private void checkMemoryUsage() {\n        Runtime runtime = Runtime.getRuntime();\n        long totalMemory = runtime.totalMemory();\n        long freeMemory = runtime.freeMemory();\n        long usedMemory = totalMemory - freeMemory;\n\n        System.out.println(\"Total Memory: \" + totalMemory);\n        System.out.println(\"Free Memory: \" + freeMemory);\n        System.out.println(\"Used Memory: \" + usedMemory);\n\n        if (usedMemory > totalMemory * 0.8) {\n            System.out.println(\"WARNING: High memory usage detected!\");\n        }\n",
  "content_length": 542
}
```

#### 🔗 **T - 追踪依赖关系（高级分析）**

**错误处理增强（v0.9.7）：**
- 改进了`@handle_mcp_errors`装饰器，增加了工具名称识别
- 更好的错误上下文，便于调试和故障排除
- 增强了文件路径的安全验证

**查找特定方法：**
```
请帮我查找这个文件中的main方法：examples/BigService.java
```

**查找认证相关方法：**
```
我想找到所有认证相关的方法：examples/BigService.java
```

**查找无参数的公共方法：**
```
请帮我找到所有无参数的公共getter方法：examples/BigService.java
```

**返回格式：**
```json
{
  "success": true,
  "results": [
    {
      "capture_name": "method",
      "node_type": "method_declaration",
      "start_line": 1385,
      "end_line": 1418,
      "content": "public static void main(String[] args) {\n        System.out.println(\"BigService Demo Application\");\n        System.out.println(\"==========================\");\n\n        BigService service = new BigService();\n\n        // Test basic functions\n        System.out.println(\"\\n--- Testing Basic Functions ---\");\n        service.authenticateUser(\"testuser\", \"password123\");\n        service.createSession(\"testuser\");\n\n        // Test customer management\n        System.out.println(\"\\n--- Testing Customer Management ---\");\n        service.updateCustomerName(\"CUST001\", \"New Customer Name\");\n        Map<String, Object> customerInfo = service.getCustomerInfo(\"CUST001\");\n\n        // Test report generation\n        System.out.println(\"\\n--- Testing Report Generation ---\");\n        Map<String, Object> reportParams = new HashMap<>();\n        reportParams.put(\"start_date\", \"2024-01-01\");\n        reportParams.put(\"end_date\", \"2024-12-31\");\n        service.generateReport(\"sales\", reportParams);\n\n        // Test performance monitoring\n        System.out.println(\"\\n--- Testing Performance Monitoring ---\");\n        service.monitorPerformance();\n\n        // Test security check\n        System.out.println(\"\\n--- Testing Security Check ---\");\n        service.performSecurityCheck();\n\n        System.out.println(\"\\n--- Demo Completed ---\");\n        System.out.println(\"BigService demo application finished successfully.\");\n    }"
    }
  ],
  "count": 1,
  "file_path": "examples/BigService.java",
  "language": "java",
  "query": "methods"
}
```

#### 💡 **SMART工作流程最佳实践**
- **自然语言**: 直接用自然语言告诉AI您想要什么，无需记住复杂的参数格式
- **顺序流程**: 遵循S→M→A→R→T顺序以获得最佳分析结果
- **路径处理**: 设置项目路径后，相对路径自动解析到项目根目录
- **安全保护**: 工具自动执行项目边界检查，确保安全
- **智能理解**: AI会自动理解您的需求，调用相应的工具
- **性能优化**: 所有MCP工具都经过速度优化，内置超时和结果限制
- **依赖追踪**: 仅在需要理解代码元素间复杂关系时使用T步骤

### 🛠️ CLI命令示例

```bash
# 快速分析（1419行大文件，瞬间完成）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 详细结构表格（66个方法清晰展示）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 精确代码提取（内存使用监控代码片段）
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 100 --end-line 105

# 多语言支持测试（Python文件）
uv run python -m tree_sitter_analyzer examples/sample.py --table=full

# 小文件快速分析（54行Java文件）
uv run python -m tree_sitter_analyzer examples/MultiClass.java --advanced

# 静默模式（仅显示结果）
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full --quiet

# 🔍 查询过滤示例（v0.9.6+）
# 查找特定方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# 查找认证相关方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~auth*"

# 查找无参数的公开方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=0,public=true"

# 查找静态方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "static=true"

# 查看过滤语法帮助
uv run python -m tree_sitter_analyzer --filter-help
```

---

## 🏗️ 架构改进（v1.2.0+）

### 🔄 **统一元素管理系统**

Tree-sitter Analyzer现在具有革命性的统一架构，将所有代码元素整合到一个统一的系统中：

#### **之前（传统架构）：**
- 类、方法、字段、导入的独立集合
- 不同分析模式下的数据结构不一致
- 复杂的维护和潜在的不一致性

#### **之后（统一架构）：**
- **单一`elements`列表**: 所有代码元素（类、方法、字段、导入、包）统一
- **一致的元素类型**: 每个元素都有`element_type`属性，便于识别
- **简化的API**: 更清晰的接口和降低的复杂度
- **更好的可维护性**: 所有代码元素的单一真实来源

#### **优势：**
- ✅ **一致性**: 所有分析模式下的统一数据结构
- ✅ **简单性**: 更容易使用和理解
- ✅ **可扩展性**: 易于添加新的元素类型
- ✅ **性能**: 优化的内存使用和处理
- ✅ **向后兼容性**: 现有API继续无缝工作

#### **支持的元素类型：**
- `class` - 类和接口
- `function` - 方法和函数
- `variable` - 字段和变量
- `import` - 导入语句
- `package` - 包声明

---

## 🛠️ 核心功能

### 📊 **代码结构分析**
无需读取完整文件即可获得洞察：
- 类、方法、字段统计
- 包信息和导入依赖
- 复杂度指标
- 精确行号定位

### ✂️ **智能代码提取**
- 精确按行范围提取
- 保持原始格式和缩进
- 包含位置元数据
- 支持大文件高效处理

### 🔍 **高级查询过滤**
强大的代码元素查询和过滤系统：
- **精确匹配**: `--filter "name=main"` 查找特定方法
- **模式匹配**: `--filter "name=~auth*"` 查找认证相关方法
- **参数过滤**: `--filter "params=2"` 查找特定参数数量的方法
- **修饰符过滤**: `--filter "static=true,public=true"` 查找静态公开方法
- **复合条件**: `--filter "name=~get*,params=0,public=true"` 组合多个条件
- **CLI/MCP一致**: 命令行和AI助手中使用相同的过滤语法

### 🔗 **AI助手集成**
通过MCP协议深度集成：
- Claude Desktop
- Cursor IDE
- Roo Code
- 其他支持MCP的AI工具

### 🔍 **高级文件搜索与内容分析 (v1.2.4+)**
基于fd和ripgrep的强大文件发现和内容搜索功能：

#### **📋 前提要求**
要使用高级MCP工具（ListFilesTool、SearchContentTool、FindAndGrepTool），您需要安装以下命令行工具：

**安装fd（快速文件查找器）：**
```bash
# macOS（使用Homebrew）
brew install fd

# Windows（使用winget - 推荐）
winget install sharkdp.fd

# Windows（使用Chocolatey）
choco install fd

# Windows（使用Scoop）
scoop install fd

# Ubuntu/Debian
sudo apt install fd-find

# CentOS/RHEL/Fedora
sudo dnf install fd-find

# Arch Linux
sudo pacman -S fd
```

**安装ripgrep（快速文本搜索）：**
```bash
# macOS（使用Homebrew）
brew install ripgrep

# Windows（使用winget - 推荐）
winget install BurntSushi.ripgrep.MSVC

# Windows（使用Chocolatey）
choco install ripgrep

# Windows（使用Scoop）
scoop install ripgrep

# Ubuntu/Debian
sudo apt install ripgrep

# CentOS/RHEL/Fedora
sudo dnf install ripgrep

# Arch Linux
sudo pacman -S ripgrep
```

**验证安装：**
```bash
# 检查fd安装
fd --version

# 检查ripgrep安装
rg --version
```

> **⚠️ 重要提示：** 如果没有安装这些工具，高级MCP文件搜索和内容分析功能将无法工作。基本MCP工具（analyze_code_structure、extract_code_section等）将继续正常工作。

#### **🗂️ ListFilesTool - 智能文件发现**
- **高级过滤**: 文件类型、大小、修改时间、扩展名过滤
- **模式匹配**: 灵活文件发现的Glob模式和正则表达式支持
- **元数据丰富**: 文件大小、修改时间、目录状态和扩展名信息
- **性能优化**: 基于fd的闪电般快速文件系统遍历

#### **🔎 SearchContentTool - 智能内容搜索**
- **正则表达式和字面搜索**: 包含大小写敏感控制的灵活模式匹配
- **上下文感知结果**: 可配置的前后上下文行以便更好理解
- **多种输出格式**: 标准结果、仅计数、摘要和按文件分组
- **编码支持**: 处理不同文本编码的文件
- **性能限制**: 内置超时和结果限制以确保响应性操作

#### **🎯 FindAndGrepTool - 组合发现与搜索**
- **两阶段工作流**: 首先用fd发现文件，然后用ripgrep搜索内容
- **全面过滤**: 结合文件发现过滤器和内容搜索模式
- **高级选项**: 多行模式、单词边界、固定字符串和大小写控制
- **丰富元数据**: 文件发现计时、搜索计时和结果统计
- **Token优化**: 路径优化和结果分组以最小化AI token使用

#### **✨ 主要优势:**
- 🚀 **企业级可靠性**: 50+全面测试用例确保稳定性
- 🎯 **Token高效**: 为AI助手交互优化的多种输出格式
- 🔧 **高度可配置**: 精确控制的广泛参数支持
- 📊 **性能监控**: 内置计时和结果统计
- 🛡️ **错误弹性**: 全面的错误处理和验证

### 🌍 **多语言支持**
- **Java** - 完整支持，包括Spring、JPA框架
- **Python** - 完整支持，包括类型注解、装饰器
- **JavaScript/TypeScript** - 完整支持，包括ES6+特性
- **C/C++、Rust、Go** - 基础支持

---

## 📦 安装指南

### 👤 **终端用户**
```bash
# 基础安装
uv add tree-sitter-analyzer

# 热门语言包（推荐）
uv add "tree-sitter-analyzer[popular]"

# MCP服务器支持
uv add "tree-sitter-analyzer[mcp]"

# 完整安装
uv add "tree-sitter-analyzer[all,mcp]"
```

### 👨‍💻 **开发者**
```bash
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer
uv sync --extra all --extra mcp
```

---

## 🔒 安全和配置

### 🛡️ **项目边界保护**

Tree-sitter Analyzer自动检测和保护项目边界：

- **自动检测**: 基于`.git`、`pyproject.toml`、`package.json`等
- **CLI控制**: `--project-root /path/to/project`
- **MCP集成**: `TREE_SITTER_PROJECT_ROOT=/path/to/project`或使用自动检测
- **安全保证**: 仅分析项目边界内的文件

**推荐的MCP配置：**

**选项1: 自动检测（推荐）**
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

**选项2: 手动指定项目根目录**
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

## 🏆 质量保证

### 📊 **质量指标**
- **1,599个测试** - 100%通过率 ✅
- **74.24%代码覆盖率** - 行业领先水平
- **零测试失败** - 完全CI/CD就绪
- **跨平台兼容** - Windows、macOS、Linux

### ⚡ **最新质量成就（v1.3.5）**
- ✅ **跨平台路径兼容性** - 修复Windows短路径名称和macOS符号链接差异
- ✅ **Windows环境** - 使用Windows API实现稳健的路径标准化
- ✅ **macOS环境** - 修复`/var`与`/private/var`符号链接差异
- ✅ **全面测试覆盖** - 1699个测试，74.42%覆盖率
- ✅ **GitFlow实现** - 专业的开发/发布分支策略。详见[GitFlow文档](GITFLOW_zh.md)。

### ⚙️ **运行测试**
```bash
# 运行所有测试
uv run pytest tests/ -v

# 生成覆盖率报告
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html --cov-report=term-missing

# 运行特定测试
uv run pytest tests/test_mcp_server_initialization.py -v
```

### 📈 **覆盖率亮点**
- **语言检测器**: 98.41%（优秀）
- **CLI主入口**: 94.36%（优秀）
- **查询过滤系统**: 96.06%（优秀）
- **查询服务**: 86.25%（良好）
- **错误处理**: 82.76%（良好）

---

## 🤖 AI协作支持

### ⚡ **针对AI开发优化**

本项目支持AI辅助开发，具有专门的质量控制：

```bash
# AI系统代码生成前检查
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all

# AI生成代码审查
uv run python llm_code_checker.py path/to/new_file.py
```

📖 **详细指南**:
- [AI协作指南](AI_COLLABORATION_GUIDE.md)
- [LLM编码准则](LLM_CODING_GUIDELINES.md)

---

## 📚 文档

- **[用户MCP设置指南](MCP_SETUP_USERS.md)** - 简单配置指南
- **[开发者MCP设置指南](MCP_SETUP_DEVELOPERS.md)** - 本地开发配置
- **[项目根目录配置](PROJECT_ROOT_CONFIG.md)** - 完整配置参考
- **[API文档](docs/api.md)** - 详细API参考
- **[贡献指南](CONTRIBUTING.md)** - 如何贡献
 - **[接管与训练指南](training/README.md)** - 为新成员/维护者准备的系统上手资料

---

## 💝 赞助商与致谢

我们感谢使这个项目成为可能的赞助商们：

### 🌟 **特别感谢**

**[@o93](https://github.com/o93)** - *主要赞助商与支持者*
- 🚀 **MCP工具增强**: 赞助了全面的MCP fd/ripgrep工具开发
- 🧪 **测试基础设施**: 实现了企业级测试覆盖率（50+全面测试用例）
- 🔧 **质量保证**: 支持了bug修复和性能改进
- 💡 **创新支持**: 使高级文件搜索和内容分析功能得以早期发布

*"感谢@o93的慷慨支持，我们能够提供革命性的强大MCP工具，改变了AI助手与代码库交互的方式。这项赞助直接促成了ListFilesTool、SearchContentTool和FindAndGrepTool的全面测试覆盖开发。"*

### 🤝 **成为赞助商**

您的支持帮助我们：
- 🔬 开发新功能和工具
- 🧪 维护全面的测试覆盖率
- 📚 创建更好的文档
- 🚀 加速开发周期

**[💖 赞助这个项目](https://github.com/sponsors/aimasteracc)** 帮助我们继续为开发者社区构建出色的工具！

---

## 🤝 贡献

我们欢迎各种形式的贡献！请查看[贡献指南](CONTRIBUTING.md)了解详情。

### ⭐ **给我们一个Star！**

如果这个项目对您有帮助，请在GitHub上给我们一个⭐ - 这是对我们最大的支持！

---

## 📄 许可证

MIT许可证 - 详见[LICENSE](LICENSE)文件。

---

**🎯 为处理大型代码库和AI助手的开发者而构建**

*让每一行代码都被AI理解，让每个项目都突破token限制*

---

## ✅ 提示词测试验证

本文档中的所有AI提示词都已在真实环境中进行过完整测试，确保：

- **100%可用性** - 所有提示词都能正常工作
- **跨语言支持** - 支持Java、Python、JavaScript等主流语言
- **路径兼容性** - 相对路径和绝对路径都完全支持
- **Windows/Linux兼容** - 跨平台路径格式自动处理
- **实时验证** - 使用真实代码文件进行测试

**测试环境：**
- 操作系统：Windows 10
- 项目：tree-sitter-analyzer v1.3.5
- 测试文件：BigService.java (1419行)、sample.py (256行)、MultiClass.java (54行)
- 测试工具：所有MCP工具（check_code_scale、analyze_code_structure、extract_code_section、query_code）

**🚀 现在开始** → [30秒快速开始](#-30秒快速开始)
