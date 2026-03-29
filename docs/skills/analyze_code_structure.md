# analyze_code_structure — AI Agent 使用指南

## 何时使用

获取代码结构的详细表格输出，用于快速理解文件的全貌——类、方法、函数、字段的完整列表。

## SMART 工作流中的位置

```
Set → Map → **Analyze** (本工具) → Retrieve → Trace
               ↑
          在这里分析
```

## Intent Alias

此工具有一个 intent-based alias：

```python
# 这两个调用完全相同：
await mcp.call_tool("analyze_code_structure", {"file_path": "...", "format_type": "full"})
await mcp.call_tool("extract_structure", {"file_path": "...", "format_type": "full"})
```

## 典型调用模式

### 示例 1：全表格视图（适合大文件）

```python
# 问题：这个 2000 行的 Java 文件有什么？
result = await mcp.call_tool("extract_structure", {
    "file_path": "src/main/java/BigService.java",
    "format_type": "full",
    "output_format": "json"
})

# 响应：
# {
#   "success": true,
#   "analysis_result": {
#     "file_path": "src/main/java/BigService.java",
#     "language": "java",
#     "total_elements": 66,
#     "format_type": "full"
#   },
#   "table_output": "
#   ╭────────────────────────────────────────────────────────╮
#   │                    BigService.java                      │
#   ├─────────┬────────────┬──────────┬─────────┬────────────┤
#   │  Type   │    Name    │  Lines   │  Public │  Static    │
#   ├─────────┼────────────┼──────────┼─────────┼────────────┤
#   │ Method  │ processPayment │ 93-125 │   Yes   │    No     │
#   │ Method  │ validateOrder  │ 127-156│   No    │    No     │
#   ...
#   "
# }
```

### 示例 2：紧凑格式（适合 AI 上下文）

```python
# 问题：只需要快速概览，不需要所有细节
result = await mcp.call_tool("analyze_code_structure", {
    "file_path": "src/controllers/UserController.java",
    "format_type": "compact"
})

# 响应：更少的列，更紧凑的输出，减少 token 消耗
```

### 示例 3：CSV 导出（适合数据分析）

```python
# 问题：需要导出到 Excel 或数据分析工具
result = await mcp.call_tool("analyze_code_structure", {
    "file_path": "src/services/PaymentService.java",
    "format_type": "csv",
    "output_file": "payment_service_structure.csv",
    "suppress_output": true  # 不返回内容，只保存到文件（节省 token）
})

# 响应：
# {
#   "success": true,
#   "output_file_path": "/output/payment_service_structure.csv"
# }
```

## 参数

```json
{
  "file_path": "必需 - 分析对象ファイルのパス",
  "format_type": "可选 - 'full'（完整表格）/'compact'（紧凑）/'csv'（CSV 导出）（默认: full）",
  "language": "可选 - 编程语言（自动检测）",
  "output_file": "可选 - 输出文件名",
  "suppress_output": "可选 - 抑制响应输出，仅保存到文件（默认: false）"
}
```

## Token 优化策略

### 适合小到中等文件（< 1000 行）
```python
# 直接获取完整输出
result = await mcp.call_tool("analyze_code_structure", {
    "file_path": "MediumService.java",
    "format_type": "compact"  # 紧凑格式，减少 token
})
```

### 适合大文件（1000+ 行）
```python
# 保存到文件，不返回内容
result = await mcp.call_tool("analyze_code_structure", {
    "file_path": "HugeService.java",
    "format_type": "csv",
    "output_file": "structure.csv",
    "suppress_output": true  # 节省 90%+ token
})

# 然后读取文件或使用 query_code 获取特定元素
```

## 与其他工具的组合

### 与 get_code_outline 配合

```python
# get_code_outline: 快速大纲，层级结构，54-56% token 节省
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "BigService.java"
})

# analyze_code_structure: 详细表格，所有字段，适合数据分析
structure = await mcp.call_tool("analyze_code_structure", {
    "file_path": "BigService.java",
    "format_type": "full"
})
```

**何时用哪个？**
- `get_code_outline` → 快速理解层级结构，token 高效
- `analyze_code_structure` → 完整表格视图，适合数据分析和导出

### 与 extract_code_section 配合

```python
# 步骤 1: 分析结构，找到感兴趣的方法
structure = await mcp.call_tool("analyze_code_structure", {
    "file_path": "PaymentService.java",
    "format_type": "compact"
})

# 步骤 2: 提取特定方法的代码
code = await mcp.call_tool("extract_code_section", {
    "file_path": "PaymentService.java",
    "start_line": 93,
    "end_line": 125
})
```

### 与 query_code 配合

```python
# analyze_code_structure: 所有元素的完整表格
full_table = await mcp.call_tool("analyze_code_structure", {
    "file_path": "Service.java",
    "format_type": "full"
})

# query_code: 过滤特定元素（例如只要 public 方法）
public_methods = await mcp.call_tool("query_code", {
    "file_path": "Service.java",
    "query_key": "methods",
    "filter": "public=true"
})
```

## 支持的语言

17 种语言：Java, Python, TypeScript, JavaScript, C, C++, C#, SQL, HTML, CSS, Go, Rust, Kotlin, PHP, Ruby, YAML, Markdown

## 错误处理

```python
# 文件不存在
response = await mcp.call_tool("analyze_code_structure", {
    "file_path": "does_not_exist.java"
})
# → {"success": false, "error": "File not found: does_not_exist.java"}

# 语言不支持
response = await mcp.call_tool("analyze_code_structure", {
    "file_path": "file.xyz",
    "language": "unknown"
})
# → {"success": false, "error": "Language 'unknown' is not supported"}
```

## 性能特征

- **速度**：< 3 秒（对于大多数文件）
- **内存**：高效表格渲染
- **Token 优化**：`suppress_output=true` + `output_file` 节省 90%+ token

## 格式类型对比

| 格式 | 列数 | Token 消耗 | 何时使用 |
|------|------|-----------|----------|
| `full` | 所有列（类型、名称、行、可见性、静态、复杂度、参数、返回值） | 高 | 完整分析，详细视图 |
| `compact` | 核心列（类型、名称、行、可见性） | 中 | 快速理解，减少 token |
| `csv` | 所有列，CSV 格式 | 低（配合 suppress_output） | 导出到 Excel，数据分析 |

## 最佳实践

1. ✅ **对大文件使用 compact 或 csv + suppress_output**
   ```python
   # 大文件不要用 full 格式直接返回
   result = await mcp.call_tool("analyze_code_structure", {
       "file_path": "HugeFile.java",
       "format_type": "csv",
       "output_file": "structure.csv",
       "suppress_output": true
   })
   ```

2. ✅ **使用 output_file 保存结果以便后续分析**
   ```python
   # 保存到文件，可以多次引用而不重新解析
   result = await mcp.call_tool("analyze_code_structure", {
       "file_path": "Service.java",
       "format_type": "csv",
       "output_file": "service_structure.csv"
   })
   ```

3. ✅ **语言自动检测通常足够**
   ```python
   # 无需指定 language，会自动检测
   result = await mcp.call_tool("analyze_code_structure", {
       "file_path": "script.py"
   })
   ```

4. ❌ **不要对小文件使用 suppress_output**
   ```python
   # 不好：小文件浪费文件 I/O
   result = await mcp.call_tool("analyze_code_structure", {
       "file_path": "small_file.py",
       "suppress_output": true,
       "output_file": "output.csv"
   })

   # 好：小文件直接返回
   result = await mcp.call_tool("analyze_code_structure", {
       "file_path": "small_file.py",
       "format_type": "compact"
   })
   ```

## 示例用例

### 用例 1：理解遗留代码库

```python
# 问题：一个 3000 行的遗留 Java 文件，不知道从哪里开始
structure = await mcp.call_tool("analyze_code_structure", {
    "file_path": "legacy/MonolithService.java",
    "format_type": "full"
})

# 现在你知道：
# - 所有方法按字母顺序排列
# - 哪些是 public（API 入口点）
# - 哪些是 private（内部辅助方法）
# - 每个方法在哪一行
# - 复杂度指标
```

### 用例 2：代码审查准备

```python
# 问题：需要审查一个大文件，但不想加载整个文件
structure = await mcp.call_tool("analyze_code_structure", {
    "file_path": "PullRequest.java",
    "format_type": "compact"
})

# 快速扫描方法名和可见性，找到需要深入审查的部分
```

### 用例 3：代码库统计分析

```python
# 问题：需要分析整个代码库的方法数量、复杂度分布
files = await mcp.call_tool("list_files", {
    "roots": ["/project"],
    "pattern": "*.java",
    "glob": True
})

for file in files["results"]:
    await mcp.call_tool("analyze_code_structure", {
        "file_path": file["path"],
        "format_type": "csv",
        "output_file": f"stats/{file['name']}_structure.csv",
        "suppress_output": True
    })

# 现在所有结构数据都在 CSV 文件中，可以用 pandas 或 Excel 分析
```

## 技术细节

- **实现**：基于 tree-sitter AST 解析
- **格式**：Rich Table（full/compact）或 CSV
- **线程安全**：是（异步）
- **缓存**：无（每次调用都重新解析，适用于频繁变化的文件）

## 相关工具

| 工具 | 何时使用 |
|------|---------|
| `analyze_code_structure` | 完整表格视图，数据分析，代码审查 |
| `get_code_outline` | 快速大纲，层级结构，token 高效（54-56% 节省） |
| `extract_code_section` | 获取特定代码段的内容 |
| `query_code` | 过滤特定元素（例如只要 public 方法） |
| `list_files` | 项目发现 — 找到所有匹配特定模式的文件 |

## 版本历史

- **v1.10.5** (2026-03-28): 添加 intent alias `extract_structure`
- **v1.10.4** (2025-02-15): 初始版本，支持 full/compact/csv 格式

---

**🎯 记住：表格视图让大文件一目了然。这是你的代码结构浏览器。**
