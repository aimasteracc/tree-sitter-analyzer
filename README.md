# Tree-sitter Analyzer

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-1268%20passed-brightgreen.svg)](#测试)

An extensible multi-language code analyzer framework using Tree-sitter with dynamic plugin architecture, designed to solve the problem of large code files exceeding LLM single-pass token limits.

**Available as both CLI tool and MCP server.**

## Core Features

1. **Code Scale Analysis** - Get overall structure without reading complete files
2. **Targeted Code Extraction** - Extract specific line ranges efficiently  
3. **Code Position Information** - Get detailed position data for precise extraction

## Installation

### Prerequisites

First, install uv (a fast Python package manager):

```bash
# On macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or using pip
pip install uv
```

### Install from GitHub

```bash
# Basic installation with Java support
# Clone and install the project
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer

# Install with Java support
uv sync
uv add tree-sitter-java

# With popular languages (Java, Python, JavaScript, TypeScript)
uv sync --extra popular

# With MCP server support
uv sync --extra mcp

# Full installation with all features
uv sync --extra all --extra mcp
```

### Alternative: Using pip

```bash
# After the project is published to PyPI
pip install "tree-sitter-analyzer[java]"
```

## Usage

### CLI Commands

```bash
# Code scale analysis
python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text

# Partial code extraction
python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86

# Position information table
python -m tree_sitter_analyzer examples/Sample.java --table=full
```

#### CLI Output Examples

**Code Scale Analysis (`--advanced --output-format=text`):**
```
PS C:\git-public\tree-sitter-analyzer> python -m tree_sitter_analyzer examples/Sample.java --advanced --output-format=text
2025-07-30 16:57:47,827 - tree_sitter_analyzer - INFO - Successfully loaded 3 language plugins: java, javascript, python
2025-07-30 16:57:47,916 - tree_sitter_analyzer - INFO - CacheService initialized: L1=100, L2=1000, L3=10000, TTL=3600s
2025-07-30 16:57:47,917 - tree_sitter_analyzer - INFO - Loading plugins...
2025-07-30 16:57:47,920 - tree_sitter_analyzer - INFO - Plugin registered for language: java
2025-07-30 16:57:47,920 - tree_sitter_analyzer - INFO - Plugin registered for language: javascript
2025-07-30 16:57:47,922 - tree_sitter_analyzer - INFO - Plugin registered for language: python
2025-07-30 16:57:47,922 - tree_sitter_analyzer - INFO - Successfully loaded 3 language plugins: java, javascript, python     
2025-07-30 16:57:47,923 - tree_sitter_analyzer - INFO - UnifiedAnalysisEngine initialized
INFO: 拡張子から言語を自動判定しました: java
2025-07-30 16:57:47,925 - tree_sitter_analyzer - INFO - Starting analysis for examples/Sample.java
2025-07-30 16:57:47,945 - tree_sitter_analyzer.core.parser - INFO - Parser initialized successfully
2025-07-30 16:57:47,951 - PERF - analyze_java: 0.0253s - Operation completed
2025-07-30 16:57:47,951 - tree_sitter_analyzer.performance - INFO - analyze_java: 0.0253s - Operation completed
2025-07-30 16:57:47,958 - PERF - unified_analysis: 0.0253s - Analyzed examples/Sample.java (java)
2025-07-30 16:57:47,958 - tree_sitter_analyzer.performance - INFO - unified_analysis: 0.0253s - Analyzed examples/Sample.java (java)

--- 高度な解析結果 ---
"ファイル: examples/Sample.java"
"パッケージ: (default)"
"行数: 178"
"\nクラス数: 8"
"メソッド数: 24"
"フィールド数: 5"
"インポート数: 2"
"アノテーション数: 0"
```

**Partial Code Extraction (`--partial-read`):**
```
PS C:\git-public\tree-sitter-analyzer> python -m tree_sitter_analyzer examples/Sample.java --partial-read --start-line 84 --end-line 86
2025-07-30 16:58:22,948 - tree_sitter_analyzer - INFO - Successfully loaded 3 language plugins: java, javascript, python
2025-07-30 16:58:23,056 - tree_sitter_analyzer - INFO - Successfully read partial file examples/Sample.java: lines 84-86
{
  "file_path": "examples/Sample.java",
  "range": {
    "start_line": 84,
    "end_line": 86,
    "start_column": null,
    "end_column": null
  },
  "content": "        public void innerMethod() {\n            System.out.println(\"Inner class method, value: \" + value);\n        }\n",
  "content_length": 117
}
```

**Table Format Analysis (`--table=full`):**

The `--table=full` command produces detailed analysis tables:


# Sample.java

## Imports
```java
java.util.List
java.util.ArrayList
```

## Classes
| Class | Type | Visibility | Lines | Methods | Fields |
|-------|------|------------|-------|---------|--------|
| AbstractParentClass | class | public | 7-15 | 2 | 0 |
| ParentClass | class | public | 18-45 | 4 | 2 |
| TestInterface | class | public | 48-64 | 3 | 0 |
| AnotherInterface | class | public | 67-69 | 1 | 0 |
| Test | class | public | 72-159 | 14 | 3 |
| InnerClass | class | public | 83-87 | 1 | 0 |
| StaticNestedClass | class | public | 90-94 | 1 | 0 |
| TestEnum | class | public | 162-178 | 0 | 0 |

## Fields
| Name | Type | Vis | Modifiers | Line | Doc |
|------|------|-----|-----------|------|-----|
| CONSTANT | String | ~ | static,final | 20 | - |
| parentField | String | # | protected | 23 | - |
| value | int | - | private | 74 | - |
| staticValue | int | + | public,static | 77 | - |
| finalField | String | - | private,final | 80 | - |

## Constructor
| Method | Signature | Vis | Lines | Cols | Cx | Doc |
|--------|-----------|-----|-------|------|----|----|
| ParentClass | ():void | + | 26-28 | 5-6 | 1 | - |
| Test | (value:int):void | + | 97-100 | 5-6 | 1 | - |
| Test | ():void | + | 103-105 | 5-6 | 1 | - |

## Public Methods
| Method | Signature | Vis | Lines | Cols | Cx | Doc |
|--------|-----------|-----|-------|------|----|----|
| innerMethod | ():void | + | 84-86 | 5-6 | 1 | - |
| nestedMethod | ():void | + | 91-93 | 5-6 | 1 | - |
| getValue | ():String | + | 108-110 | 5-6 | 1 | - |
| staticMethod | ():void [static] | + | 128-130 | 5-6 | 1 | - |
| finalMethod | ():void | + | 133-135 | 5-6 | 1 | - |
| doSomething | ():void | + | 138-141 | 5-6 | 1 | - |
| anotherMethod | ():void | + | 143-146 | 5-6 | 1 | - |
| genericMethod | (input:T):void | + | 149-151 | 5-6 | 1 | - |
| createList | (item:T):List<T> | + | 154-158 | 5-6 | 1 | - |

## Private Methods
| Method | Signature | Vis | Lines | Cols | Cx | Doc |
|--------|-----------|-----|-------|------|----|----|
| privateMethod | ():void | - | 123-125 | 5-6 | 1 | - |


### MCP Server

The Tree-sitter Analyzer provides an MCP (Model Context Protocol) server that enables AI assistants to analyze code files directly.

```bash
# Start MCP server
python -m tree_sitter_analyzer.mcp.server
```



### MCP Configuration

Add to your Claude Desktop config file:

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

#### Available MCP Tools

1. **analyze_code_scale** - Get code scale and complexity metrics
2. **format_table** - Generate table-formatted analysis (equivalent to CLI `--table=full`)
3. **read_code_partial** - Extract specific line ranges from files
4. **get_code_positions** - Get precise position information for code elements
5. **analyze_code_universal** - Universal code analysis with automatic language detection

#### MCP Usage Examples

**Code Scale Analysis:**
```json
{
  "tool": "analyze_code_scale",
  "arguments": {
    "file_path": "examples/Sample.java",
    "include_complexity": true,
    "include_details": true
  }
}
```

**Table Format Analysis:**
```json
{
  "tool": "format_table",
  "arguments": {
    "file_path": "examples/Sample.java",
    "format_type": "full"
  }
}
```

**Partial Code Reading:**
```json
{
  "tool": "read_code_partial",
  "arguments": {
    "file_path": "examples/Sample.java",
    "start_line": 84,
    "end_line": 86
  }
}
```

**Get Code Positions:**
```json
{
  "tool": "get_code_positions",
  "arguments": {
    "file_path": "examples/Sample.java",
    "element_types": ["methods", "classes"],
    "include_details": true
  }
}
```

## Development

For developers and contributors:

```bash
# Clone the repository
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer

# Install development dependencies
uv sync

# Run tests
pytest tests/ -v
```

## License

MIT License