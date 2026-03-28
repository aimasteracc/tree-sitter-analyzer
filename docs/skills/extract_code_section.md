# extract_code_section — AI Agent 使用指南

## 何时使用

在使用 `get_code_outline` **之后**使用此工具。先调用 outline 了解文件结构，然后仅提取你需要的方法体或代码段。

## SMART 工作流中的位置

```
Set → Map → Analyze → **Retrieve** (本工具) → Trace
                        ↑
                    在这里提取
```

## 典型调用模式

### 示例 1：提取单个方法体

```python
# 步骤 1: 先用 get_code_outline 找到方法位置
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "src/services/PaymentService.java",
    "output_format": "toon"
})

# 响应显示 processPayment 方法在 93-125 行

# 步骤 2: 仅提取该方法
code = await mcp.call_tool("extract_code_section", {
    "file_path": "src/services/PaymentService.java",
    "start_line": 93,
    "end_line": 125
})

# 响应：
# {
#   "success": true,
#   "partial_content_result": {
#     "file_path": "src/services/PaymentService.java",
#     "start_line": 93,
#     "end_line": 125,
#     "total_lines": 33,
#     "content": "public PaymentResult processPayment(...) { ... }",
#     "format": "text"
#   }
# }
```

### 示例 2：精确列提取（提取单个表达式）

```python
# 问题：只需要某一行的特定部分，不需要整行
code = await mcp.call_tool("extract_code_section", {
    "file_path": "config/database.yml",
    "start_line": 12,
    "end_line": 12,
    "start_column": 10,  # 0ベース（第11个字符开始）
    "end_column": 35     # 0ベース（到第36个字符结束）
})

# 响应：只返回指定列范围的文本片段
```

### 示例 3：JSON 格式导出（用于程序化处理）

```python
# 问题：需要程序化处理提取的代码
result = await mcp.call_tool("extract_code_section", {
    "file_path": "src/controllers/UserController.java",
    "start_line": 45,
    "end_line": 78,
    "format": "json"  # 返回结构化 JSON
})

# 响应：
# {
#   "success": true,
#   "partial_content_result": {
#     "file_path": "src/controllers/UserController.java",
#     "start_line": 45,
#     "end_line": 78,
#     "total_lines": 34,
#     "content": "...",
#     "format": "json"
#   }
# }
```

### 示例 4：保存到文件（节省 token）

```python
# 问题：提取的代码很长，不想在响应中返回全部内容
result = await mcp.call_tool("extract_code_section", {
    "file_path": "src/legacy/MonolithService.java",
    "start_line": 200,
    "end_line": 450,
    "output_file": "extracted_legacy_code.txt",
    "suppress_output": true  # 不返回内容，只保存到文件（节省 90%+ token）
})

# 响应：
# {
#   "success": true,
#   "output_file_path": "/output/extracted_legacy_code.txt"
# }
```

## 参数

```json
{
  "file_path": "必需 - 源文件路径",
  "start_line": "必需 - 开始行号（1ベース）",
  "end_line": "可选 - 结束行号（1ベース，默认：文件末尾）",
  "start_column": "可选 - 开始列号（0ベース）",
  "end_column": "可选 - 结束列号（0ベース）",
  "format": "可选 - 'text'（默认）/'json'/'raw'",
  "output_file": "可选 - 输出文件名",
  "suppress_output": "可选 - 抑制响应输出，仅保存到文件（默认: false）"
}
```

## Token 优化策略

### 适合小代码段（< 100 行）
```python
# 直接获取内容
result = await mcp.call_tool("extract_code_section", {
    "file_path": "Service.java",
    "start_line": 50,
    "end_line": 100,
    "format": "text"  # 简洁格式
})
```

### 适合大代码段（100+ 行）
```python
# 保存到文件，不返回内容
result = await mcp.call_tool("extract_code_section", {
    "file_path": "LegacyService.java",
    "start_line": 100,
    "end_line": 500,
    "output_file": "legacy_code.txt",
    "suppress_output": true  # 节省 90%+ token
})

# 然后读取文件或分段处理
```

## 与其他工具的组合

### 与 get_code_outline 配合（推荐）

```python
# 1. 获取大纲 → 找到感兴趣的方法
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "BigService.java",
    "output_format": "toon"  # 54-56% token 节省
})

# 2. 提取特定方法（从大纲中看到的行号）
code = await mcp.call_tool("extract_code_section", {
    "file_path": "BigService.java",
    "start_line": 93,
    "end_line": 125
})
```

### 与 search_content 配合

```python
# 1. 搜索代码找到位置
search_result = await mcp.call_tool("search_content", {
    "roots": ["/project"],
    "query": "processPayment",
    "include_globs": ["*.java"]
})

# 响应显示匹配在 PaymentService.java 第 95 行

# 2. 提取该方法的完整代码（假设方法约 30 行）
code = await mcp.call_tool("extract_code_section", {
    "file_path": "src/services/PaymentService.java",
    "start_line": 93,
    "end_line": 125
})
```

### 与 analyze_code_structure 配合

```python
# analyze_code_structure: 所有方法的完整表格
full_table = await mcp.call_tool("analyze_code_structure", {
    "file_path": "Service.java",
    "format_type": "compact"  # 紧凑格式，减少 token
})

# 从表格中找到感兴趣的方法行号

# extract_code_section: 提取该方法的实际代码
code = await mcp.call_tool("extract_code_section", {
    "file_path": "Service.java",
    "start_line": 150,
    "end_line": 180
})
```

## 编码处理

自动编码检测和 UTF-8 转换：
- 支持 UTF-8、UTF-16、Shift-JIS、EUC-JP、ISO-8859-1 等常见编码
- 自动检测文件编码
- 输出统一为 UTF-8
- 无需手动指定编码

## 支持的语言

17 种语言：Java, Python, TypeScript, JavaScript, C, C++, C#, SQL, HTML, CSS, Go, Rust, Kotlin, PHP, Ruby, YAML, Markdown

## 错误处理

```python
# 文件不存在
response = await mcp.call_tool("extract_code_section", {
    "file_path": "does_not_exist.java",
    "start_line": 10
})
# → {"success": false, "error": "File not found: does_not_exist.java"}

# 行号超出范围
response = await mcp.call_tool("extract_code_section", {
    "file_path": "small_file.py",
    "start_line": 1000  # 文件只有 50 行
})
# → {"success": false, "error": "Line number out of range"}

# start_line > end_line
response = await mcp.call_tool("extract_code_section", {
    "file_path": "file.java",
    "start_line": 100,
    "end_line": 50  # 错误：结束行小于开始行
})
# → {"success": false, "error": "Invalid line range"}
```

## 性能特征

- **速度**：< 3 秒（对于大多数文件）
- **编码**：自动检测和 UTF-8 转换
- **内存**：高效分段读取，不加载整个文件
- **Token 优化**：`suppress_output=true` + `output_file` 节省 90%+ token

## 格式类型对比

| 格式 | 返回格式 | Token 消耗 | 何时使用 |
|------|---------|-----------|------------|
| `text` | 纯文本字符串 | 低 | 人类阅读，直接展示 |
| `json` | 结构化 JSON | 中 | 程序化处理，元数据需求 |
| `raw` | 原始字节流 | 低 | 二进制文件，特殊格式 |

## 最佳实践

1. ✅ **总是先用 get_code_outline，后用 extract_code_section**
   ```python
   # 好：先看大纲，再精确提取
   outline = await mcp.call_tool("get_code_outline", {"file_path": "BigFile.java"})
   code = await mcp.call_tool("extract_code_section", {
       "file_path": "BigFile.java",
       "start_line": 93,
       "end_line": 125
   })

   # 不好：盲目提取整个文件
   code = await mcp.call_tool("extract_code_section", {
       "file_path": "BigFile.java",
       "start_line": 1,
       "end_line": 5000
   })
   ```

2. ✅ **对大段代码使用 output_file + suppress_output**
   ```python
   # 大段代码（100+ 行）不要直接返回
   result = await mcp.call_tool("extract_code_section", {
       "file_path": "HugeFile.java",
       "start_line": 100,
       "end_line": 500,
       "output_file": "extracted.txt",
       "suppress_output": true
   })
   ```

3. ✅ **使用精确列提取减少噪音**
   ```python
   # 只需要某一行的特定部分
   result = await mcp.call_tool("extract_code_section", {
       "file_path": "config.yml",
       "start_line": 12,
       "end_line": 12,
       "start_column": 10,
       "end_column": 35
   })
   ```

4. ❌ **不要提取不需要的上下文**
   ```python
   # 不好：提取整个类（包含 10 个方法），只需要其中 1 个
   code = await mcp.call_tool("extract_code_section", {
       "file_path": "Service.java",
       "start_line": 1,
       "end_line": 500
   })

   # 好：只提取需要的方法
   code = await mcp.call_tool("extract_code_section", {
       "file_path": "Service.java",
       "start_line": 93,
       "end_line": 125
   })
   ```

## 示例用例

### 用例 1：理解遗留代码

```python
# 问题：2000 行的遗留文件，只需要看一个核心方法
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "legacy/MonolithService.java",
    "output_format": "toon"
})

# 从大纲中找到 processCriticalBusinessLogic 在 450-520 行

code = await mcp.call_tool("extract_code_section", {
    "file_path": "legacy/MonolithService.java",
    "start_line": 450,
    "end_line": 520
})

# 现在你只看到关键业务逻辑，token 消耗从 5000+ 降到 200-
```

### 用例 2：代码审查准备

```python
# 问题：审查 PR 中修改的特定方法
diff = await mcp.call_tool("search_content", {
    "roots": ["/project"],
    "query": "validateUserInput",
    "include_globs": ["*.java"]
})

# 找到该方法在 UserController.java 第 78 行

code = await mcp.call_tool("extract_code_section", {
    "file_path": "src/controllers/UserController.java",
    "start_line": 75,
    "end_line": 95
})

# 快速审查该方法，而不需要加载整个控制器
```

### 用例 3：多方法提取

```python
# 问题：需要同时看 3 个相关方法
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "PaymentService.java"
})

# 从大纲看到：
# - processPayment: 93-125 行
# - validateOrder: 127-156 行
# - calculateTax: 158-180 行

# 提取整个支付流程（3 个方法）
code = await mcp.call_tool("extract_code_section", {
    "file_path": "PaymentService.java",
    "start_line": 93,
    "end_line": 180
})

# 现在你看到完整的支付流程，不包含其他无关方法
```

## 技术细节

- **实现**：基于文件系统的高效分段读取
- **编码**：自动检测（支持 10+ 种编码）
- **线程安全**：是（异步）
- **缓存**：无（每次调用都重新读取，适用于频繁变化的文件）

## 相关工具

| 工具 | 何时使用 |
|------|---------
| `get_code_outline` | 首先使用 - 获取文件结构地图 |
| `extract_code_section` | 之后使用 - 仅获取你需要的代码部分 |
| `analyze_code_structure` | 深度分析 - 完整表格视图，所有方法细节 |
| `search_content` | 跨项目搜索 - 找到包含特定模式的所有文件 |
| `list_files` | 项目发现 - 找到所有匹配特定模式的文件 |

## 版本历史

- **v1.10.4** (2025-02-15): 初始版本，支持行/列提取，自动编码检测

---

**🎯 记住：Map first, then retrieve. 此工具是你的精准提取器。**
