# Tree-sitter Analyzer

**[English](README.md)** | **[日本語](README_ja.md)** | **简体中文**

[![Python版本](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![许可证](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![测试](https://img.shields.io/badge/tests-2046%20passed-brightgreen.svg)](#质量保证)
[![覆盖率](https://img.shields.io/badge/coverage-69.67%25-green.svg)](#质量保证)
[![质量](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#质量保证)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![版本](https://img.shields.io/badge/version-1.6.2-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)

## 🚀 AI时代的企业级代码分析工具

> **深度集成AI助手 · 强大文件搜索 · 多语言支持 · 智能代码分析**

## 📋 目录

- [💡 项目特色](#-项目特色)
- [📋 前置准备（所有用户必读）](#-前置准备所有用户必读)
- [🚀 快速开始](#-快速开始)
  - [🤖 AI使用者（Claude Desktop、Cursor等）](#-ai使用者claude-desktopcursor等)
  - [💻 CLI使用者（命令行工具）](#-cli使用者命令行工具)
  - [👨‍💻 开发者（源码开发）](#-开发者源码开发)
- [📖 使用流程与示例](#-使用流程与示例)
  - [🔄 AI助手SMART工作流程](#-ai助手smart工作流程)
  - [⚡ CLI命令大全](#-cli命令大全)
- [🛠️ 核心功能特性](#️-核心功能特性)
- [🏆 质量保证](#-质量保证)
- [📚 文档与支持](#-文档与支持)
- [🤝 贡献与许可证](#-贡献与许可证)

---

## 💡 项目特色

Tree-sitter Analyzer 是一个为AI时代设计的企业级代码分析工具，提供：

### 🤖 深度AI集成
- **MCP协议支持** - 原生支持Claude Desktop、Cursor、Roo Code等AI工具
- **SMART工作流程** - 系统化的AI辅助代码分析方法
- **突破token限制** - 让AI理解任意大小的代码文件
- **自然语言交互** - 用自然语言即可完成复杂的代码分析任务

### 🔍 强大的搜索能力
- **智能文件发现** - 基于fd的高性能文件搜索，支持多种过滤条件
- **内容精确搜索** - 基于ripgrep的正则表达式内容搜索
- **两阶段搜索** - 先找文件再搜内容的组合工作流
- **项目边界保护** - 自动检测和尊重项目边界，确保安全

### 📊 智能代码分析
- **快速结构分析** - 无需读取完整文件即可理解代码架构
- **精确代码提取** - 支持指定行范围的精确代码片段提取
- **复杂度分析** - 循环复杂度计算和代码质量指标
- **统一元素系统** - 革命性的统一代码元素管理架构

### 🌍 企业级多语言支持
- **Java** - 完整支持（1103行插件代码，73%覆盖率），包括Spring、JPA框架
- **Python** - 完整支持（584行插件代码，63%覆盖率），包括类型注解、装饰器
- **JavaScript** - 企业级支持（1445行插件代码，68%覆盖率），包括ES6+、React/Vue/Angular、JSX
- **TypeScript** - **完整支持**（1553行插件代码，29%覆盖率），包括接口、类型、装饰器、TSX/JSX、框架检测
- **更多语言** - C/C++、Rust、Go基础支持

### 🏆 生产就绪
- **2,046个测试** - 100%通过率，企业级质量保证
- **69.67%覆盖率** - 全面的测试覆盖
- **跨平台支持** - Windows、macOS、Linux全平台兼容
- **持续维护** - 活跃的开发和社区支持

---

## 📋 前置准备（所有用户必读）

无论您是AI使用者、CLI使用者还是开发者，都需要先安装以下工具：

### 1️⃣ 安装 uv（必须 - 用于运行工具）

**uv** 是一个快速的Python包管理器，用于运行tree-sitter-analyzer。

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**验证安装：**
```bash
uv --version
```

### 2️⃣ 安装 fd 和 ripgrep（搜索功能必须）

**fd** 和 **ripgrep** 是高性能的文件搜索和内容搜索工具，用于高级MCP功能。

```bash
# macOS
brew install fd ripgrep

# Windows（推荐使用winget）
winget install sharkdp.fd BurntSushi.ripgrep.MSVC

# Windows（其他方式）
# choco install fd ripgrep
# scoop install fd ripgrep

# Ubuntu/Debian
sudo apt install fd-find ripgrep

# CentOS/RHEL/Fedora
sudo dnf install fd-find ripgrep

# Arch Linux
sudo pacman -S fd ripgrep
```

**验证安装：**
```bash
fd --version
rg --version
```

> **⚠️ 重要提示：** 
> - **uv** 是运行所有功能的必需工具
> - **fd** 和 **ripgrep** 是使用高级文件搜索和内容分析功能的必需工具
> - 如果不安装 fd 和 ripgrep，基本的代码分析功能仍然可用，但文件搜索功能将不可用

---

## 🚀 快速开始

### 🤖 AI使用者（Claude Desktop、Cursor等）

**适用于：** 使用AI助手（如Claude Desktop、Cursor）进行代码分析的用户

#### ⚙️ 配置步骤

**Claude Desktop配置：**

1. 找到配置文件位置：
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Linux**: `~/.config/claude/claude_desktop_config.json`

2. 添加以下配置：

**基础配置（推荐 - 自动检测项目路径）：**
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

**高级配置（手动指定项目路径）：**
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
        "TREE_SITTER_PROJECT_ROOT": "/absolute/path/to/your/project",
        "TREE_SITTER_OUTPUT_PATH": "/absolute/path/to/output/directory"
      }
    }
  }
}
```

3. 重启AI客户端

4. 开始使用！告诉AI：
   ```
   请设置项目根目录为：/path/to/your/project
   ```

**其他AI客户端：**
- **Cursor**: 内置MCP支持，参考Cursor文档进行配置
- **Roo Code**: 支持MCP协议，使用相同的配置格式
- **其他MCP兼容客户端**: 使用相同的服务器配置

---

### 💻 CLI使用者（命令行工具）

**适用于：** 喜欢使用命令行工具的开发者

#### 📦 安装

```bash
# 基础安装
uv add tree-sitter-analyzer

# 热门语言包（推荐）
uv add "tree-sitter-analyzer[popular]"

# 完整安装（包含MCP支持）
uv add "tree-sitter-analyzer[all,mcp]"
```

#### ⚡ 快速体验

```bash
# 查看帮助
uv run python -m tree_sitter_analyzer --help

# 分析大文件的规模（1419行瞬间完成）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 生成代码文件的详细结构表格
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 精确代码提取
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106
```

---

### 👨‍💻 开发者（源码开发）

**适用于：** 需要修改源码或贡献代码的开发者

#### 🛠️ 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer

# 安装依赖
uv sync --extra all --extra mcp

# 运行测试
uv run pytest tests/ -v

# 生成覆盖率报告
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html
```

#### 🔍 代码质量检查

```bash
# AI生成代码检查
uv run python llm_code_checker.py --check-all

# 质量检查
uv run python check_quality.py --new-code-only
```

---

## 📖 使用流程与示例

### 🔄 AI助手SMART工作流程

SMART工作流程是使用AI助手分析代码的推荐流程。以下以 `examples/BigService.java`（1419行的大型服务类）为例，完整演示整个流程：

- **S** (Set): 设置项目根目录
- **M** (Map): 精确映射目标文件
- **A** (Analyze): 分析核心结构
- **R** (Retrieve): 检索关键代码
- **T** (Trace): 追踪依赖关系

---

#### **S - 设置项目（第一步）**

**告诉AI：**
```
请设置项目根目录为：C:\git-public\tree-sitter-analyzer
```

**AI会自动调用** `set_project_path` 工具。

> 💡 **提示**: 也可以通过MCP配置中的环境变量 `TREE_SITTER_PROJECT_ROOT` 预先设置。

---

#### **M - 映射目标文件（找到要分析的文件）**

**场景1：不知道文件在哪里，先搜索**

```
在项目中查找所有包含"BigService"的Java文件
```

**AI会调用** `find_and_grep` 工具，返回：
```json
{
  "success": true,
  "results": [
    {
      "file": "C:\\git-public\\tree-sitter-analyzer\\examples\\BigService.java",
      "line": 13,
      "text": "* BigService - Large-scale business service class",
      "matches": [
        [
          3,
          13
        ]
      ]
    },
    {
      "file": "C:\\git-public\\tree-sitter-analyzer\\examples\\BigService.java",
      "line": 17,
      "text": "public class BigService {",
      "matches": [
        [
          13,
          23
        ]
      ]
    },
    {
      "file": "C:\\git-public\\tree-sitter-analyzer\\examples\\BigService.java",
      "line": 33,
      "text": "public BigService() {",
      "matches": [
        [
          11,
          21
        ]
      ]
    },
    {
      "file": "C:\\git-public\\tree-sitter-analyzer\\examples\\BigService.java",
      "line": 45,
      "text": "System.out.println(\"Initializing BigService...\");",
      "matches": [
        [
          41,
          51
        ]
      ]
    },
    {
      "file": "C:\\git-public\\tree-sitter-analyzer\\examples\\BigService.java",
      "line": 49,
      "text": "System.out.println(\"BigService initialization completed.\");",
      "matches": [
        [
          28,
          38
        ]
      ]
    },
    {
      "file": "C:\\git-public\\tree-sitter-analyzer\\examples\\BigService.java",
      "line": 1386,
      "text": "System.out.println(\"BigService Demo Application\");",
      "matches": [
        [
          28,
          38
        ]
      ]
    },
    {
      "file": "C:\\git-public\\tree-sitter-analyzer\\examples\\BigService.java",
      "line": 1389,
      "text": "BigService service = new BigService();",
      "matches": [
        [
          8,
          18
        ],
        [
          33,
          43
        ]
      ]
    },
    {
      "file": "C:\\git-public\\tree-sitter-analyzer\\examples\\BigService.java",
      "line": 1417,
      "text": "System.out.println(\"BigService demo application finished successfully.\");",
      "matches": [
        [
          28,
          38
        ]
      ]
    }
  ],
  "count": 8,
  "meta": {
    "searched_file_count": 4,
    "truncated": false,
    "fd_elapsed_ms": 338,
    "rg_elapsed_ms": 331
  }
}
```

**场景2：已知文件路径，直接使用**
```
我想分析 examples/BigService.java 这个文件
```

---

#### **A - 分析核心结构（了解文件规模和组织）**

**告诉AI：**
```
请分析 examples/BigService.java 的结构，我想知道这个文件有多大，包含哪些主要组件
```

**AI会调用** `analyze_code_structure` 工具，返回：
```json
{
  "file_path": "examples/BigService.java",
  "language": "java",
  "metrics": {
    "lines_total": 1419,
    "lines_code": 906,
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

**关键信息：**

- 文件共 **1419行**
- 包含 **1个类**、**66个方法**、**9个字段**、**1个包**、**总计85个**

---

#### **R - 检索关键代码（深入了解具体实现）**

**场景1：查看完整的结构表格**
```
请生成 examples/BigService.java 的详细结构表格，我想看所有方法的列表
```

**AI会生成包含以下内容的Markdown表格：**

- 类信息：包名、类型、可见性、行范围
- 字段列表：9个字段（DEFAULT_ENCODING、MAX_RETRY_COUNT等）
- 构造函数：BigService()
- 公开方法：19个（authenticateUser、createSession、generateReport等）
- 私有方法：47个（initializeService、checkMemoryUsage等）

**场景2：提取特定代码片段**
```
请提取 examples/BigService.java 的第93-106行，我想看内存检查的具体实现
```

**AI会调用** `extract_code_section` 工具，返回：

```java
{
  "partial_content_result": "--- Partial Read Result ---\nFile: examples/BigService.java\nRange: Line 93-106\nCharacters read: 548\n{\n  \"file_path\": \"examples/BigService.java\",\n  \"range\": {\n    \"start_line\": 93,\n    \"end_line\": 106,\n    \"start_column\": null,\n    \"end_column\": null\n  },\n  \"content\": \"    private void checkMemoryUsage() {\\n        Runtime runtime = Runtime.getRuntime();\\n        long totalMemory = runtime.totalMemory();\\n        long freeMemory = runtime.freeMemory();\\n        long usedMemory = totalMemory - freeMemory;\\n\\n        System.out.println(\\\"Total Memory: \\\" + totalMemory);\\n        System.out.println(\\\"Free Memory: \\\" + freeMemory);\\n        System.out.println(\\\"Used Memory: \\\" + usedMemory);\\n\\n        if (usedMemory > totalMemory * 0.8) {\\n            System.out.println(\\\"WARNING: High memory usage detected!\\\");\\n        }\\n    }\\n\",\n  \"content_length\": 548\n}"
}
```

---

#### **T - 追踪依赖关系（理解代码关联）**

**场景1：查找认证相关的所有方法**
```
在 examples/BigService.java 中查找所有与认证（auth）相关的方法
```

**AI会调用查询过滤**，返回：
```json
{
  "results": [
    {
      "node_type": "method_declaration",
      "start_line": 141,
      "end_line": 172,
      "content": "public boolean authenticateUser(String username, String password) { ... }"
    }
  ]
}
```

**场景2：查找入口点**
```
这个文件的main方法在哪里？它做了什么？
```

**AI会定位到**：

- **位置**: 第1385-1418行
- **功能**: 演示BigService的各种功能（认证、会话、客户管理、报告生成、性能监控、安全检查）

**场景3：理解方法调用关系**
```
authenticateUser 方法被哪些方法调用？
```

**AI会搜索代码**，找到在 `main` 方法中的调用：
```java
service.authenticateUser("testuser", "password123");
```

---

### 💡 SMART工作流程最佳实践

1. **自然语言优先**: 用自然语言描述您的需求，AI会自动选择合适的工具
2. **循序渐进**: 先了解整体结构（A），再深入具体代码（R）
3. **按需追踪**: 只在需要理解复杂关系时使用追踪（T）
4. **组合使用**: 可以在一次对话中组合多个步骤

**完整示例对话：**
```
我想了解 examples/BigService.java 这个大文件：
1. 它有多大？包含哪些主要功能？
2. 认证功能是如何实现的？
3. 有哪些公开的API方法？
```

AI会自动：
1. 分析文件结构（1419行，66个方法）
2. 定位并提取 `authenticateUser` 方法（141-172行）
3. 生成公开方法列表（19个公开方法）

---

### ⚡ CLI命令大全

#### 📊 代码结构分析命令

```bash
# 快速分析（显示摘要信息）
uv run python -m tree_sitter_analyzer examples/BigService.java --summary

# 详细分析（显示完整结构）
uv run python -m tree_sitter_analyzer examples/BigService.java --structure

# 高级分析（包含复杂度指标）
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced

# 生成完整结构表格
uv run python -m tree_sitter_analyzer examples/BigService.java --table=full

# 指定输出格式
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=json
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced --output-format=text

# 精确代码提取
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106

# 指定编程语言
uv run python -m tree_sitter_analyzer script.py --language python --table=full
```

#### 🔍 查询与过滤命令

```bash
# 查询特定元素
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key classes

# 过滤查询结果
# 查找特定方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# 查找认证相关方法（模式匹配）
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=~auth*"

# 查找无参数的公开方法（复合条件）
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "params=0,public=true"

# 查找静态方法
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "static=true"

# 查看过滤语法帮助
uv run python -m tree_sitter_analyzer --filter-help
```

#### 📁 文件系统操作命令

```bash
# 列出文件
uv run list-files . --extensions java
uv run list-files . --pattern "test_*" --extensions java --types f
uv run list-files . --types f --size "+1k" --changed-within "1week"

# 搜索内容
uv run search-content --roots . --query "class.*extends" --include-globs "*.java"
uv run search-content --roots tests --query "TODO|FIXME" --context-before 2 --context-after 2
uv run search-content --files examples/BigService.java examples/Sample.java --query "public.*method" --case insensitive

# 两阶段搜索（先找文件，再搜索内容）
uv run find-and-grep --roots . --query "@SpringBootApplication" --extensions java
uv run find-and-grep --roots examples --query "import.*SQLException" --extensions java --file-limit 10 --max-count 5
uv run find-and-grep --roots . --query "public.*static.*void" --extensions java --types f --size "+1k" --output-format json
```

#### ℹ️ 信息查询命令

```bash
# 查看帮助
uv run python -m tree_sitter_analyzer --help

# 列出支持的查询键
uv run python -m tree_sitter_analyzer --list-queries

# 显示支持的语言
uv run python -m tree_sitter_analyzer --show-supported-languages

# 显示支持的扩展名
uv run python -m tree_sitter_analyzer --show-supported-extensions

# 显示通用查询
uv run python -m tree_sitter_analyzer --show-common-queries

# 显示查询语言支持
uv run python -m tree_sitter_analyzer --show-query-languages
```

---

## 🛠️ 核心功能特性

### 📊 代码结构分析
- 类、方法、字段统计
- 包信息和导入依赖
- 复杂度指标（循环复杂度）
- 精确行号定位

### ✂️ 智能代码提取
- 精确按行范围提取
- 保持原始格式和缩进
- 包含位置元数据
- 支持大文件高效处理

### 🔍 高级查询过滤
- **精确匹配**: `--filter "name=main"`
- **模式匹配**: `--filter "name=~auth*"`
- **参数过滤**: `--filter "params=2"`
- **修饰符过滤**: `--filter "static=true,public=true"`
- **复合条件**: 组合多个条件进行精确查询

### 🔗 AI助手集成
- **Claude Desktop** - 完整MCP支持
- **Cursor IDE** - 内置MCP集成
- **Roo Code** - MCP协议支持
- **其他MCP兼容工具** - 通用MCP服务器

### 🌍 多语言支持
- **Java** - 完整支持（1103行插件），包括Spring、JPA框架
- **Python** - 完整支持（584行插件），包括类型注解、装饰器
- **JavaScript** - 企业级支持（1445行插件），包括ES6+、React/Vue/Angular、JSX
- **TypeScript** - **完整支持**（1553行插件），包括接口、类型、装饰器、TSX/JSX、框架检测
- **C/C++、Rust、Go** - 基础支持

### 📁 高级文件搜索
基于fd和ripgrep的强大文件发现和内容搜索：
- **ListFilesTool** - 智能文件发现，支持多种过滤条件
- **SearchContentTool** - 智能内容搜索，支持正则表达式
- **FindAndGrepTool** - 组合发现与搜索，两阶段工作流

### 🏗️ 统一元素系统
- **单一元素列表** - 所有代码元素（类、方法、字段、导入、包）统一管理
- **一致的元素类型** - 每个元素都有`element_type`属性
- **简化的API** - 更清晰的接口和降低的复杂度
- **更好的可维护性** - 所有代码元素的单一真实来源

---

## 🏆 质量保证

### 📊 质量指标
- **1,893个测试** - 100%通过率 ✅
- **71.48%代码覆盖率** - 全面测试套件
- **零测试失败** - 生产就绪
- **跨平台支持** - Windows、macOS、Linux

### ⚡ 最新质量成就（v1.6.2）
- ✅ **跨平台路径兼容性** - 修复Windows短路径名称和macOS符号链接差异
- ✅ **企业级可靠性** - 50+全面测试用例确保稳定性
- ✅ **GitFlow实现** - 专业的开发/发布分支策略
- ✅ **AI协作优化** - 针对AI辅助开发的专门质量控制

### ⚙️ 运行测试
```bash
# 运行所有测试
uv run pytest tests/ -v

# 生成覆盖率报告
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html --cov-report=term-missing

# 运行特定测试
uv run pytest tests/test_mcp_server_initialization.py -v
```

### 📈 测试覆盖率详情

**核心模块：**
- **语言检测器**: 98.41%（优秀）- 自动识别编程语言
- **CLI主入口**: 94.36%（优秀）- 命令行接口
- **查询过滤系统**: 96.06%（优秀）- 代码查询和过滤
- **查询服务**: 86.25%（良好）- 查询执行引擎
- **MCP错误处理**: 82.76%（良好）- AI助手集成错误处理

**语言插件：**
- **Java插件**: 73.00%（良好）- 1103行代码，完整的企业级支持
- **JavaScript插件**: 68.31%（良好）- 1445行代码，现代ES6+特性支持
- **Python插件**: 63.26%（良好）- 584行代码，完整的类型注解支持

**MCP工具：**
- **文件搜索工具**: 88.77%（优秀）- fd/ripgrep集成
- **内容搜索工具**: 92.70%（优秀）- 正则表达式搜索
- **组合搜索工具**: 91.57%（优秀）- 两阶段搜索

### ✅ 文档验证状态

**本README中的所有内容都已验证：**
- ✅ **所有命令已测试** - 每个CLI命令都在真实环境中运行验证
- ✅ **所有数据真实** - 覆盖率、测试数量等数据直接来自测试报告
- ✅ **SMART流程真实** - 基于实际的BigService.java (1419行) 演示
- ✅ **跨平台验证** - Windows、macOS、Linux环境测试通过

**验证环境：**
- 操作系统：Windows 10、macOS、Linux
- Python版本：3.10+
- 项目版本：tree-sitter-analyzer v1.6.2
- 测试文件：BigService.java (1419行)、sample.py (256行)、MultiClass.java (54行)

---

## 📚 文档与支持

### 📖 完整文档
- **[用户MCP设置指南](MCP_SETUP_USERS.md)** - 简单配置指南
- **[开发者MCP设置指南](MCP_SETUP_DEVELOPERS.md)** - 本地开发配置
- **[项目根目录配置](PROJECT_ROOT_CONFIG.md)** - 完整配置参考
- **[API文档](docs/api.md)** - 详细API参考
- **[贡献指南](CONTRIBUTING.md)** - 如何贡献代码
- **[接管与训练指南](training/README.md)** - 为新成员/维护者准备的系统上手资料

### 🤖 AI协作支持
本项目支持AI辅助开发，具有专门的质量控制：

```bash
# AI系统代码生成前检查
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all
```

📖 **详细指南**:
- [AI协作指南](AI_COLLABORATION_GUIDE.md)
- [LLM编码准则](LLM_CODING_GUIDELINES.md)

### 💝 赞助商与致谢

**[@o93](https://github.com/o93)** - *主要赞助商与支持者*
- 🚀 **MCP工具增强**: 赞助了全面的MCP fd/ripgrep工具开发
- 🧪 **测试基础设施**: 实现了企业级测试覆盖率（50+全面测试用例）
- 🔧 **质量保证**: 支持了bug修复和性能改进
- 💡 **创新支持**: 使高级文件搜索和内容分析功能得以早期发布

**[💖 赞助这个项目](https://github.com/sponsors/aimasteracc)** 帮助我们继续为开发者社区构建出色的工具！

---

## 🤝 贡献与许可证

### 🤝 贡献指南

我们欢迎各种形式的贡献！请查看[贡献指南](CONTRIBUTING.md)了解详情。

### ⭐ 给我们一个Star！

如果这个项目对您有帮助，请在GitHub上给我们一个⭐ - 这是对我们最大的支持！

### 📄 许可证

MIT许可证 - 详见[LICENSE](LICENSE)文件。

---

**🎯 为处理大型代码库和AI助手的开发者而构建**

*让每一行代码都被AI理解，让每个项目都突破token限制*