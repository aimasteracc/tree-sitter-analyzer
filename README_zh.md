# 🌳 Tree-sitter Analyzer

**[English](README.md)** | **[日本語](README_ja.md)** | **简体中文**

[![Python版本](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![许可证](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![测试](https://img.shields.io/badge/tests-3370%20passed-brightgreen.svg)](#质量保证)
[![覆盖率](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)
[![质量](https://img.shields.io/badge/quality-enterprise%20grade-blue.svg)](#质量保证)
[![PyPI](https://img.shields.io/pypi/v/tree-sitter-analyzer.svg)](https://pypi.org/project/tree-sitter-analyzer/)
[![版本](https://img.shields.io/badge/version-1.9.2-blue.svg)](https://github.com/aimasteracc/tree-sitter-analyzer/releases)
[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuOTYxNTYgMS42MDAxSDIuMjQxNTZDMS44ODgxIDEuNjAwMSAxLjYwMTU2IDEuODg2NjQgMS42MDE1NiAyLjI0MDFWNC45NjAxQzEuNjAxNTYgNS4zMTM1NiAxLjg4ODEgNS42MDAxIDIuMjQxNTYgNS42MDAxSDQuOTYxNTZDNS4zMTUwMiA1LjYwMDEgNS42MDE1NiA1LjMxMzU2IDUuNjAxNTYgNC45NjAxVjIuMjQwMUM1LjYwMTU2IDEuODg2NjQgNS4zMTUwMiAxLjYwMDEgNC45NjE1NiAxLjYwMDFaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00Ljk2MTU2IDEwLjM5OTlIMi4yNDE1NkMxLjg4ODEgMTAuMzk5OSAxLjYwMTU2IDEwLjY4NjQgMS42MDE1NiAxMS4wMzk5VjEzLjc1OTlDMS42MDE1NiAxNC4xMTM0IDEuODg4MSAxNC4zOTk5IDIuMjQxNTYgMTQuMzk5OUg0Ljk2MTU2QzUuMzE1MDIgMTQuMzk5OSA1LjYwMTU2IDE0LjExMzQgNS42MDE1NiAxMy43NTk5VjExLjAzOTlDNS42MDE1NiAxMC42ODY0IDUuMzE1MDIgMTAuMzk5OSA0Ljk2MTU2IDEwLjM5OTlaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik0xMy43NTg0IDEuNjAwMUgxMS4wMzg0QzEwLjY4NSAxLjYwMDEgMTAuMzk4NCAxLjg4NjY0IDEwLjM5ODQgMi4yNDAxVjQuOTYwMUMxMC4zOTg0IDUuMzEzNTYgMTAuNjg1IDUuNjAwMSAxMS4wMzg0IDUuNjAwMUgxMy43NTg0QzE0LjExMTkgNS42MDAxIDE0LjM5ODQgNS4zMTM1NiAxNC4zOTg0IDQuOTYwMVYyLjI0MDFDMTQuMzk4NCAxLjg4NjY0IDE0LjExMTkgMS42MDAxIDEzLjc1ODQgMS42MDAxWiIgZmlsbD0iI2ZmZiIvPgo8cGF0aCBkPSJNNCAxMkwxMiA0TDQgMTJaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00IDEyTDEyIDQiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgo8L3N2Zz4K&logoColor=ffffff)](https://zread.ai/aimasteracc/tree-sitter-analyzer)
[![GitHub Stars](https://img.shields.io/github/stars/aimasteracc/tree-sitter-analyzer.svg?style=social)](https://github.com/aimasteracc/tree-sitter-analyzer)


## 🚀 AI时代的企业级代码分析工具

> **深度集成AI助手 · 强大文件搜索 · 多语言支持 · 智能代码分析**

## 📋 目录

- [1. 💡 项目特色](#1--项目特色)
- [2. 📋 前置准备（所有用户必读）](#2--前置准备所有用户必读)
- [3. 🚀 快速开始](#3--快速开始)
  - [3.1 🤖 AI使用者（Claude Desktop、Cursor等）](#31--ai使用者claude-desktopcursor等)
  - [3.2 💻 CLI使用者（命令行工具）](#32--cli使用者命令行工具)
  - [3.3 👨‍💻 开发者（源码开发）](#33--开发者源码开发)
- [4. 📖 使用流程与示例](#4--使用流程与示例)
  - [4.1 🔄 AI助手SMART工作流程](#41--ai助手smart工作流程)
- [5. 🤖 MCP工具完整列表](#5--mcp工具完整列表)
- [6. ⚡ CLI命令大全](#6--cli命令大全)
- [7. 🛠️ 核心功能特性](#7-️-核心功能特性)
- [8. 🏆 质量保证](#8--质量保证)
- [9. 📚 文档与支持](#9--文档与支持)
- [10. 🤝 贡献与许可证](#10--贡献与许可证)

---

## 1. 💡 项目特色

Tree-sitter Analyzer 是一个为AI时代设计的企业级代码分析工具，提供：

| 功能类别 | 核心能力 | 主要优势 |
|---------|---------|---------|
| **🤖 深度AI集成** | • MCP协议支持<br>• SMART工作流程<br>• 突破token限制<br>• 自然语言交互 | 原生支持Claude Desktop、Cursor、Roo Code<br>系统化的AI辅助代码分析方法<br>让AI理解任意大小的代码文件<br>用自然语言完成复杂分析任务 |
| **🔍 强大的搜索能力** | • 智能文件发现<br>• 内容精确搜索<br>• 两阶段搜索<br>• 项目边界保护 | 基于fd的高性能文件搜索<br>基于ripgrep的正则表达式搜索<br>先找文件再搜内容的组合工作流<br>自动检测和尊重项目边界 |
| **📊 智能代码分析** | • 快速结构分析<br>• 精确代码提取<br>• 复杂度分析<br>• 统一元素系统 | 无需读取完整文件即可理解架构<br>支持指定行范围的代码片段提取<br>循环复杂度计算和质量指标<br>革命性的统一代码元素管理 |

### 🌍 企业级多语言支持

| 编程语言 | 支持级别 | 主要特性 |
|---------|---------|---------|
| **Java** | 完整支持 | Spring框架、JPA、企业级特性 |
| **Python** | 完整支持 | 类型注解、装饰器、现代Python特性 |
| **JavaScript** | 完整支持 | ES6+、React/Vue/Angular、JSX |
| **TypeScript** | 完整支持 | 接口、类型、装饰器、TSX/JSX、框架检测 |
| **HTML** | 🆕 完整支持 | DOM结构分析、元素分类、属性提取、层次关系 |
| **CSS** | 🆕 完整支持 | 选择器分析、属性分类、样式规则提取、智能分类 |
| **Markdown** | 完整支持 | 标题、代码块、链接、图片、表格、任务列表、引用 |
| **C/C++** | 基础支持 | 基本语法解析 |
| **Rust** | 基础支持 | 基本语法解析 |
| **Go** | 基础支持 | 基本语法解析 |

### 🏆 生产就绪
- **3,370个测试** - 100%通过率，企业级质量保证
- **高覆盖率** - 全面的测试覆盖
- **跨平台支持** - Windows、macOS、Linux全平台兼容
- **持续维护** - 活跃的开发和社区支持

---

## 2. 📋 前置准备（所有用户必读）

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

| 操作系统 | 包管理器 | 安装命令 | 备注 |
|---------|---------|---------|------|
| **macOS** | Homebrew | `brew install fd@10.3.0 ripgrep@14.1.1` | 推荐方式 |
| **Windows** | winget | `winget install sharkdp.fd --version 10.3.0` <br> `winget install BurntSushi.ripgrep.MSVC --version 14.1.1` | 推荐方式 |
| | Chocolatey | `choco install fd --version 10.3.0` <br> `choco install ripgrep --version 14.1.1` | 替代方式 |
| | Scoop | `scoop install fd@10.3.0 ripgrep@14.1.1` | 替代方式 |
| **Ubuntu/Debian** | apt | `sudo apt install fd-find=10.3.0* ripgrep=14.1.1*` | 官方仓库 |
| **CentOS/RHEL/Fedora** | dnf | `sudo dnf install fd-find-10.3.0 ripgrep-14.1.1` | 官方仓库 |
| **Arch Linux** | pacman | `sudo pacman -S fd=10.3.0 ripgrep=14.1.1` | 官方仓库 |

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

## 3. 🚀 快速开始

### 3.1 🤖 AI使用者（Claude Desktop、Cursor等）

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

### 3.2 💻 CLI使用者（命令行工具）

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

# 🆕 新架构HTML/CSS分析
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.html --table=html --output-format=text
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.css --advanced --output-format=text
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.html --structure --language html

# 精确代码提取
uv run python -m tree_sitter_analyzer examples/BigService.java --partial-read --start-line 93 --end-line 106
```

---

### 3.3 👨‍💻 开发者（源码开发）

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

## 4. 📖 使用流程与示例

### 4.1 🔄 AI助手SMART工作流程

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

**AI 将会调用** `find_and_grep` 工具，并返回显示在 BigService.java 中有 8 处匹配的结果。

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

**AI会调用** `extract_code_section` 工具，返回checkMemoryUsage方法的代码。

---

#### **T - 追踪依赖关系（理解代码关联）**

**场景1：查找认证相关的所有方法**
```
在 examples/BigService.java 中查找所有与认证（auth）相关的方法
```

**AI会调用查询过滤**，返回authenticateUser方法的（141-172行）代码。

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

**HTML/CSS分析示例：**
```
我想分析index.html的HTML结构：
1. 存在哪些HTML元素，它们是如何组织的？
2. 定义了哪些CSS规则，设置了哪些属性？
3. 元素是如何分类的（结构、媒体、表单）？
```

AI会自动：
1. 提取包含标签名、属性和分类的HTML元素
2. 通过智能分类分析CSS选择器和属性
3. 生成显示DOM层次结构和样式规则的结构化表格

---

## 5. 🤖 MCP工具完整列表

Tree-sitter Analyzer提供了丰富的MCP工具集，专为AI助手设计：

| 工具类别 | 工具名称 | 主要功能 | 核心特性 |
|---------|---------|---------|---------|
| **📊 代码分析** | `check_code_scale` | 快速分析代码文件规模 | 文件大小统计、行数统计、复杂度分析、性能指标 |
| | `analyze_code_structure` | 分析代码结构和生成表格 | 🆕 suppress_output参数、多种格式(full/compact/csv/json/html)、自动语言检测 |
| | `extract_code_section` | 精确提取代码片段 | 指定行范围提取、大文件高效处理、保持原始格式 |
| **🔍 智能搜索** | `list_files` | 高性能文件发现 | 基于fd、glob模式、文件类型过滤、时间范围控制 |
| | `search_content` | 正则表达式内容搜索 | 基于ripgrep、多种输出格式、上下文控制、编码处理、🆕 并行处理引擎、统一`set_project_path`支持 |
| | `find_and_grep` | 两阶段搜索 | 先找文件再搜内容、组合fd+ripgrep、智能缓存优化、🆕 统一`set_project_path`支持 |
| **🔧 高级查询** | `query_code` | tree-sitter查询 | 预定义查询键、自定义查询字符串、过滤表达式支持 |
| **⚙️ 系统管理** | `set_project_path` | 设置项目根路径 | 安全边界控制、自动路径验证、🆕 全MCP工具统一 |
| **📁 资源访问** | 代码文件资源 | URI访问代码文件 | 通过URI标识访问文件内容 |
| | 项目统计资源 | 访问项目统计数据 | 项目分析数据和统计信息 |

### 🆕 v1.9.0新特性：并行处理引擎

革命性的并行处理功能，显著提升搜索性能：

- **🔄 并行处理引擎**: search_content MCP工具现在支持多目录并行搜索
- **⚡ 性能提升**: 大型代码库搜索速度提升最高4倍
- **🛡️ 类型安全改进**: mypy错误减少7%（341个→318个）
- **✨ 代码风格统一**: ruff违规大幅减少
- **🏗️ 技术债务解决**: 全面的代码质量改进
- **🚀 测试执行时间**: 保持83%缩短（215秒→37秒）

#### 🔄 并行处理功能详情
- **自动并行执行**: 多个roots目录自动并行处理
- **可配置控制**: `enable_parallel`选项控制（默认: True）
- **可扩展性能**: 性能提升随目录数量扩展
- **内存高效**: 信号量控制并发执行限制

### 🆕 v1.8.4新特性：可配置文件日志功能

革命性的环境变量控制文件日志系统：

- **🔧 环境变量控制**：通过环境变量灵活控制文件日志行为
  - `TREE_SITTER_ANALYZER_ENABLE_FILE_LOG`: 启用/禁用文件日志
  - `TREE_SITTER_ANALYZER_LOG_DIR`: 自定义日志目录路径
  - `TREE_SITTER_ANALYZER_FILE_LOG_LEVEL`: 控制文件日志级别
- **🛡️ 默认行为改进**：默认禁用文件日志，防止用户项目污染
- **📁 智能目录选择**：启用时使用系统临时目录，保持项目清洁
- **🔄 向后兼容性**：完全保持现有功能不变
- **📚 完整文档支持**：包含调试指南和故障排除文档

### 🆕 v1.8.3新特性：MCP工具设计一致性增强

全面的MCP工具统一和设计一致性改进：

- **🔧 统一`set_project_path`实现**：SearchContentTool和FindAndGrepTool现在具有一致的`set_project_path`方法实现
- **🏗️ 全MCP工具设计一致性**：全部4个MCP工具（QueryTool、TableFormatTool、SearchContentTool、FindAndGrepTool）现在具有统一的接口设计
- **📁 FileOutputManager集成**：统一的FileOutputManager工厂模式用于一致的文件输出管理
- **🔄 动态项目路径变更**：所有MCP工具现在通过统一接口支持动态项目路径变更
- **🛡️ 增强的安全边界**：所有MCP工具具有一致的安全边界保护
- **📋 改进的开发者体验**：统一接口使MCP工具开发和使用更加一致

### 🆕 v1.8.2新特性：CLI安全性和参数验证增强

全面的CLI安全性改进和参数验证优化：

- **🔒 CLI安全边界修复**：修复了CLI模式下的安全边界错误，确保文件访问的安全性
- **✅ 正确的CLI参数验证**：实现了完整的CLI参数验证系统，防止无效参数组合
- **🚫 排他参数控制**：`--table`和`--query-key`参数现在正确实现排他控制
- **🔍 增强的过滤支持**：`--query-key`与`--filter`的组合使用得到完整支持
- **⚠️ 清晰的错误消息**：提供详细的错误信息，帮助用户正确使用命令
- **🛡️ 安全功能增强**：测试环境下的临时目录访问许可和项目边界保护
- **📋 改进的用户体验**：更直观的命令行界面和错误处理

### 🆕 v1.8.0新特性：HTML/CSS语言支持

具有专用数据模型和格式化的革命性HTML和CSS分析功能：

- **🏗️ HTML DOM分析**：包含标签名、属性和层次结构的完整HTML元素提取
- **🎨 CSS规则分析**：通过智能分类进行CSS选择器和属性的全面分析
- **📊 元素分类系统**：HTML元素（结构、标题、文本、列表、媒体、表单、表格、元数据）和CSS属性（布局、盒模型、排版、背景、过渡、交互性）的智能分类
- **🔧 专用数据模型**：用于精确Web技术分析的新`MarkupElement`和`StyleElement`类
- **📋 增强的格式化器**：具有结构化表格输出的新HTML格式化器，用于Web开发工作流
- **🔄 可扩展架构**：具有`FormatterRegistry`的插件式系统，用于动态格式管理
- **🆕 依赖关系**：添加了`tree-sitter-html>=0.23.0,<0.25.0`和`tree-sitter-css>=0.23.0,<0.25.0`以支持原生解析

### 🆕 v1.7.3特性：Markdown完整支持

全新的Markdown语言支持，为文档分析和AI助手提供强大功能：

- **📝 完整Markdown解析**：支持ATX标题、Setext标题、代码块、链接、图片、表格等所有主要元素
- **🔍 智能元素提取**：自动识别和提取标题层级、代码语言、链接URL、图片信息等
- **📊 结构化分析**：将Markdown文档转换为结构化数据，便于AI理解和处理
- **🎯 任务列表支持**：完整支持GitHub风格的任务列表（复选框）
- **🔧 查询系统集成**：支持所有现有的查询和过滤功能
- **📁 多扩展名支持**：支持.md、.markdown、.mdown、.mkd、.mkdn、.mdx等格式

### 🆕 v1.7.2特性：文件输出优化功能

MCP搜索工具新增的文件输出优化功能是一个革命性的token节省解决方案：

- **🎯 文件输出优化**：`find_and_grep`、`list_files`、`search_content`工具新增`suppress_output`和`output_file`参数
- **🔄 自动格式检测**：智能选择文件格式（JSON/Markdown），基于内容类型自动决定
- **💾 大幅节省Token**：将大型搜索结果保存到文件时，响应大小减少高达99%
- **📚 ROO规则文档**：新增完整的tree-sitter-analyzer MCP优化使用指南
- **🔧 向后兼容**：可选功能，不影响现有功能的使用

### 🆕 v1.7.0特性：suppress_output功能

`analyze_code_structure`工具的`suppress_output`参数：

- **问题解决**：当分析结果过大时，传统方式会返回完整的表格数据，消耗大量token
- **智能优化**：设置`suppress_output=true`且指定`output_file`时，仅返回基本元数据
- **效果显著**：可减少响应大小高达99%，大幅节省AI对话的token消耗
- **使用场景**：特别适合大型代码文件的结构分析和批量处理场景

---

## 6. ⚡ CLI命令大全

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

# 🆕 新架构HTML/CSS分析
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.html --table=full --output-format=text
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.css --table=full --output-format=text
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.html --advanced --output-format=text
uv run python -m tree_sitter_analyzer examples/comprehensive_sample.css --advanced --output-format=text

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

# 🆕 v1.8.2 正确的使用方法
# 正确：使用 --query-key 与 --filter 组合
uv run python -m tree_sitter_analyzer examples/BigService.java --query-key methods --filter "name=main"

# 正确：生成完整结构表格
uv run python -m tree_sitter_analyzer examples/BigService.java --table full

# 🚫 v1.8.2 错误的使用方法（会显示错误）
# 错误：同时使用 --table 和 --query-key（排他参数）
# uv run python -m tree_sitter_analyzer examples/BigService.java --table full --query-key methods
# 错误信息: "--table and --query-key cannot be used together. Use --query-key with --filter instead."

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

#### 🔒 安全功能说明

v1.8.2版本增强了安全功能，确保文件访问的安全性：

```bash
# ✅ 安全的项目边界保护
# 工具会自动检测和尊重项目边界，防止访问项目外的敏感文件

# ✅ 测试环境临时目录访问
# 在测试环境下，允许访问临时目录以支持测试用例

# ✅ 正确的CLI参数验证
# 系统会验证参数组合的有效性，防止无效的命令执行

# 示例：安全的文件分析
uv run python -m tree_sitter_analyzer examples/BigService.java --advanced
# ✅ 允许：文件在项目目录内

# uv run python -m tree_sitter_analyzer /etc/passwd --advanced
# ❌ 拒绝：文件在项目边界外（安全保护）
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


## 7. 🛠️ 核心功能特性

| 功能类别 | 功能名称 | 核心特性 | 技术优势 |
|---------|---------|---------|---------|
| **📊 代码结构分析** | 智能解析引擎 | 类、方法、字段统计<br>包信息和导入依赖<br>复杂度指标（循环复杂度）<br>精确行号定位 | 基于tree-sitter的高精度解析<br>支持大型企业级代码库<br>实时性能优化 |
| **✂️ 智能代码提取** | 精确提取工具 | 精确按行范围提取<br>保持原始格式和缩进<br>包含位置元数据<br>支持大文件高效处理 | 零损失格式保持<br>内存优化算法<br>流式处理支持 |
| **🔍 高级查询过滤** | 多维度过滤器 | **精确匹配**: `--filter "name=main"`<br>**模式匹配**: `--filter "name=~auth*"`<br>**参数过滤**: `--filter "params=2"`<br>**修饰符过滤**: `--filter "static=true,public=true"`<br>**复合条件**: 组合多个条件进行精确查询 | 灵活的查询语法<br>高性能索引<br>智能缓存机制 |
| **🔗 AI助手集成** | MCP协议支持 | **Claude Desktop** - 完整MCP支持<br>**Cursor IDE** - 内置MCP集成<br>**Roo Code** - MCP协议支持<br>**其他MCP兼容工具** - 通用MCP服务器 | 标准MCP协议<br>即插即用设计<br>跨平台兼容 |
| **🌍 多语言支持** | 企业级语言引擎 | **Java** - 完整支持，包括Spring、JPA框架<br>**Python** - 完整支持，包括类型注解、装饰器<br>**JavaScript** - 企业级支持，包括ES6+、React/Vue/Angular、JSX<br>**TypeScript** - **完整支持**，包括接口、类型、装饰器、TSX/JSX、框架检测<br>**HTML** - **🆕 完整支持**，包括DOM结构、元素分类、属性提取<br>**CSS** - **🆕 完整支持**，包括选择器分析、属性分类、样式规则<br>**Markdown** - **完整支持**，包括标题、代码块、链接、图片、表格、任务列表、引用<br>**C/C++、Rust、Go** - 基础支持 | 框架感知解析<br>语法扩展支持<br>持续语言更新 |
| **📁 高级文件搜索** | fd+ripgrep集成 | **ListFilesTool** - 智能文件发现，支持多种过滤条件<br>**SearchContentTool** - 智能内容搜索，支持正则表达式<br>**FindAndGrepTool** - 组合发现与搜索，两阶段工作流 | 基于Rust的高性能工具<br>并行处理能力<br>智能缓存优化 |
| **🏗️ 统一元素系统** | 革命性架构设计 | **单一元素列表** - 所有代码元素（类、方法、字段、导入、包）统一管理<br>**一致的元素类型** - 每个元素都有`element_type`属性<br>**简化的API** - 更清晰的接口和降低的复杂度<br>**更好的可维护性** - 所有代码元素的单一真实来源 | 统一数据模型<br>类型安全保证<br>扩展性设计 |

---

## 8. 🏆 质量保证

### 📊 质量指标
- **3,370个测试** - 100%通过率 ✅
- **高代码覆盖率** - 全面测试套件
- **零测试失败** - 生产就绪
- **跨平台支持** - Windows、macOS、Linux

### ⚡ 最新质量成就（v1.8.3）
- ✅ **🔒 CLI安全性增强** - 修复CLI模式下的安全边界错误，确保文件访问安全
- ✅ **✅ 参数验证完善** - 实现完整的CLI参数验证系统，防止无效参数组合
- ✅ **🚫 排他参数控制** - `--table`和`--query-key`参数正确实现排他控制
- ✅ **🔍 过滤功能增强** - `--query-key`与`--filter`组合使用得到完整支持
- ✅ **⚠️ 错误消息优化** - 提供清晰详细的错误信息，改善用户体验
- ✅ **🛡️ 项目边界保护** - 自动检测和尊重项目边界，防止访问敏感文件
- ✅ **🧪 测试环境支持** - 测试环境下的临时目录访问许可
- ✅ **📋 用户体验改进** - 更直观的命令行界面和错误处理机制

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

项目维护高质量的测试覆盖率，详细的模块覆盖率信息请查看：

[![覆盖率详情](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer/branch/main/graph/badge.svg)](https://codecov.io/gh/aimasteracc/tree-sitter-analyzer)

**点击上方徽章查看：**
- 📊 **模块别覆盖率** - 每个模块的详细覆盖率统计
- 📈 **覆盖率趋势** - 历史覆盖率变化趋势
- 🔍 **未覆盖代码行** - 具体的未测试代码位置
- 📋 **详细报告** - 完整的覆盖率分析报告

### ✅ 文档验证状态

**本README中的所有内容都已验证：**
- ✅ **所有命令已测试** - 每个CLI命令都在真实环境中运行验证
- ✅ **所有数据真实** - 覆盖率、测试数量等数据直接来自测试报告
- ✅ **SMART流程真实** - 基于实际的BigService.java (1419行) 演示
- ✅ **跨平台验证** - Windows、macOS、Linux环境测试通过

**验证环境：**
- 操作系统：Windows 10、macOS、Linux
- Python版本：3.10+
- 项目版本：tree-sitter-analyzer v1.8.2
- 测试文件：BigService.java (1419行)、sample.py (256行)、MultiClass.java (54行)
- 新增验证：CLI参数验证、安全边界保护、排他参数控制

---

## 9. 📚 文档与支持

### 📖 完整文档
本项目提供完整的文档支持，包括：

- **快速开始指南** - 参见本README的[快速开始](#3--快速开始)部分
- **MCP配置指南** - 参见[AI使用者配置](#31--ai使用者claude-desktopcursor等)部分
- **CLI使用指南** - 参见[CLI命令大全](#6--cli命令大全)部分
- **核心功能说明** - 参见[核心功能特性](#7-️-核心功能特性)部分

### 🤖 AI协作支持
本项目支持AI辅助开发，具有专门的质量控制：

```bash
# AI系统代码生成前检查
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all
```

### 💝 赞助商与致谢

**[@o93](https://github.com/o93)** - *主要赞助商与支持者*
- 🚀 **MCP工具增强**: 赞助了全面的MCP fd/ripgrep工具开发
- 🧪 **测试基础设施**: 实现了企业级测试覆盖率（50+全面测试用例）
- 🔧 **质量保证**: 支持了bug修复和性能改进
- 💡 **创新支持**: 使高级文件搜索和内容分析功能得以早期发布

**[💖 赞助这个项目](https://github.com/sponsors/aimasteracc)** 帮助我们继续为开发者社区构建出色的工具！

---

## 10. 🤝 贡献与许可证

### 🤝 贡献指南

我们欢迎各种形式的贡献！包括：

- **🐛 Bug报告** - 发现问题请提交Issue
- **💡 功能建议** - 新功能想法欢迎讨论
- **📝 文档改进** - 帮助完善文档
- **🔧 代码贡献** - 提交Pull Request
- **🧪 测试用例** - 增加测试覆盖率

### ⭐ 给我们一个Star！

如果这个项目对您有帮助，请在GitHub上给我们一个⭐ - 这是对我们最大的支持！

### 📄 许可证

MIT许可证 - 详见[LICENSE](LICENSE)文件。

---

**🎯 为处理大型代码库和AI助手的开发者而构建**

*让每一行代码都被AI理解，让每个项目都突破token限制*