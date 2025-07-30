# Tree-sitter Analyzer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1268%20passed-brightgreen.svg)](#测试)

一个基于Tree-sitter的可扩展多语言代码分析框架，**既可以作为CLI工具使用，也可以作为MCP服务器使用**，专门设计用于解决大型代码文件超出LLM单次处理token限制的问题。

## 🎯 核心功能

本项目的三大核心功能专门用于处理大型代码文件，特别是Java文件：

### 1. 代码整体规模分析
获取代码文件的整体结构和复杂度信息，无需读取完整文件内容。

### 2. 指定位置代码提取
精确提取代码文件中指定行范围的内容，避免加载整个文件。

### 3. 代码位置信息获取
获取类、方法、字段等代码元素的详细位置信息，用于后续的精确提取。

## 🚀 使用方式

本项目提供两种使用方式：

### 方式一：CLI命令行工具
直接在命令行中使用，适合脚本自动化和开发调试。

### 方式二：MCP服务器
作为MCP服务器运行，与AI工具（如Claude Desktop、Cursor等）集成使用。

## 🚀 核心命令使用（CLI方式）

### 1. 代码整体规模分析命令

```bash
# 获取代码文件的整体规模和结构信息
python -m tree_sitter_analyzer.cli examples/Sample.java --advanced --output-format=text
```

**功能说明**：
- 分析代码文件的整体结构
- 统计类、方法、字段数量
- 计算代码复杂度
- 提供文件概览信息
- **不需要读取完整文件内容**

**输出示例**：
```
=== 代码规模分析 ===
文件: examples/Sample.java
语言: Java
总行数: 178
类数量: 4
方法数量: 12
字段数量: 8
复杂度评分: 中等
```

### 2. 指定位置代码提取命令

```bash
# 提取指定行范围的代码内容
python -m tree_sitter_analyzer.cli examples/Sample.java --partial-read --start-line 84 --end-line 86
```

**功能说明**：
- 精确提取指定行范围的代码
- 支持按行号范围提取
- 支持按列范围提取
- **内存高效，只读取需要的部分**

**输出示例**：
```json
{
  "file_path": "examples/Sample.java",
  "start_line": 84,
  "end_line": 86,
  "content": "    public void setValue(int value) {\n        this.value = value;\n    }",
  "line_count": 3
}
```

### 3. 代码位置信息获取命令

```bash
# 获取代码元素的详细位置信息表格
python -m tree_sitter_analyzer.cli examples/Sample.java --table=full
```

**功能说明**：
- 生成完整的代码元素位置表格
- 包含类、方法、字段的精确位置
- 提供可见性、类型等详细信息
- **为精确代码提取提供位置索引**

**输出示例**：
```
┌─────────────┬──────────────┬───────────┬──────────┬─────────────┬──────────────┐
│ 元素类型    │ 名称         │ 起始行    │ 结束行   │ 可见性      │ 类型/返回值  │
├─────────────┼──────────────┼───────────┼──────────┼─────────────┼──────────────┤
│ class       │ Test         │ 72        │ 159      │ public      │ -            │
│ field       │ value        │ 74        │ 74       │ private     │ int          │
│ field       │ staticValue  │ 77        │ 77       │ public      │ int          │
│ constructor │ Test         │ 97        │ 100      │ public      │ -            │
│ method      │ getValue     │ 108       │ 110      │ public      │ String       │
│ method      │ setValue     │ 113       │ 115      │ protected   │ void         │
└─────────────┴──────────────┴───────────┴──────────┴─────────────┴──────────────┘
```

## 💡 使用场景

### 大文件处理工作流

1. **首先获取文件概览**：
   ```bash
   python -m tree_sitter_analyzer.cli large_file.java --advanced --output-format=text
   ```

2. **获取详细位置信息**：
   ```bash
   python -m tree_sitter_analyzer.cli large_file.java --table=full
   ```

3. **根据需要提取特定代码段**：
   ```bash
   python -m tree_sitter_analyzer.cli large_file.java --partial-read --start-line 100 --end-line 150
   ```

### LLM集成优势

- **突破Token限制**：无需一次性加载整个大文件
- **精确定位**：通过位置表格快速找到目标代码
- **按需提取**：只提取需要分析的代码段
- **结构化信息**：提供代码的结构化元数据

## 📦 安装

### 使用uv安装（推荐）

```bash
# 安装基础版本
uv add tree-sitter-analyzer

# 安装包含Java支持的版本
uv add "tree-sitter-analyzer[java]"

# 安装包含常用语言支持的版本
uv add "tree-sitter-analyzer[popular]"

# 安装MCP服务器支持
uv add "tree-sitter-analyzer[mcp]"
```

### 使用pip安装

```bash
# 基础安装
pip install tree-sitter-analyzer

# 安装Java支持
pip install "tree-sitter-analyzer[java]"

# 安装所有功能
pip install "tree-sitter-analyzer[all,mcp]"
```

## 🔧 MCP服务器集成

### 启动MCP服务器

```bash
# 启动MCP服务器
python -m tree_sitter_analyzer.mcp.server
```

### 可用的MCP工具

1. **analyze_code_scale**: 对应 `--advanced` 功能
   ```json
   {
     "file_path": "path/to/file.java",
     "include_complexity": true,
     "include_details": false
   }
   ```

2. **read_code_partial**: 对应 `--partial-read` 功能
   ```json
   {
     "file_path": "path/to/file.java",
     "start_line": 84,
     "end_line": 86
   }
   ```

3. **format_table**: 对应 `--table=full` 功能
   ```json
   {
     "file_path": "path/to/file.java",
     "format_type": "full"
   }
   ```

## 🏗️ 架构特点

### 高效内存使用
- **流式处理**：不需要将整个文件加载到内存
- **按需解析**：只解析需要的代码段
- **缓存优化**：智能缓存常用的分析结果

### 精确定位系统
- **Tree-sitter解析**：基于语法树的精确定位
- **多层次索引**：类、方法、字段的层次化位置信息
- **快速查找**：O(1)时间复杂度的位置查找

### 支持的语言

| 语言 | 扩展名 | 核心功能支持 |
|------|--------|-------------|
| Java | `.java` | ✅ 完整支持 |
| Python | `.py` | ✅ 完整支持 |
| JavaScript | `.js` | ✅ 完整支持 |
| TypeScript | `.ts` | ✅ 基础支持 |
| C/C++ | `.c`, `.cpp` | ✅ 基础支持 |

## 📖 详细参数说明

### --advanced 参数
- `--output-format=text|json|table`: 输出格式
- `--include-complexity`: 包含复杂度分析
- `--include-details`: 包含详细信息

### --partial-read 参数
- `--start-line N`: 起始行号（必需）
- `--end-line N`: 结束行号（可选，默认到文件末尾）
- `--start-column N`: 起始列号（可选）
- `--end-column N`: 结束列号（可选）
- `--format text|json`: 输出格式

### --table 参数
- `--table=full`: 完整表格格式
- `--table=compact`: 紧凑表格格式
- `--table=csv`: CSV格式输出

## 🧪 测试验证

```bash
# 测试核心功能
python -m tree_sitter_analyzer.cli examples/Sample.java --advanced --output-format=text
python -m tree_sitter_analyzer.cli examples/Sample.java --partial-read --start-line 1 --end-line 5
python -m tree_sitter_analyzer.cli examples/Sample.java --table=full

# 运行测试套件
pytest tests/ -v

# 运行特定功能测试
pytest tests/test_partial_reading.py -v
pytest tests/test_table_formatter.py -v
```

## 📊 性能基准

### 大文件处理性能

| 文件大小 | 全文件读取 | 部分读取 | 位置分析 |
|----------|------------|----------|----------|
| 1MB      | 2.3s       | 0.1s     | 0.5s     |
| 5MB      | 12.1s      | 0.1s     | 1.2s     |
| 10MB     | 25.8s      | 0.1s     | 2.1s     |
| 50MB     | 内存不足   | 0.1s     | 8.5s     |

### Token效率对比

| 方法 | 10MB Java文件 | Token使用量 | 处理时间 |
|------|---------------|-------------|----------|
| 全文件加载 | ❌ 超出限制 | 500K+ tokens | N/A |
| 结构化分析 | ✅ 成功 | 2K tokens | 2.1s |
| 按需提取 | ✅ 成功 | 500-5K tokens | 0.1s |

## 🔗 相关链接

- [GitHub仓库](https://github.com/tree-sitter-analyzer/tree-sitter-analyzer)
- [问题追踪](https://github.com/tree-sitter-analyzer/tree-sitter-analyzer/issues)
- [Tree-sitter官网](https://tree-sitter.github.io/)

## 📄 许可证

本项目采用MIT许可证。详见[LICENSE](LICENSE)文件。

---

**专为大型代码文件分析而设计，让LLM能够高效处理任意大小的代码文件。**