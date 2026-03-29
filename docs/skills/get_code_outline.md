# get_code_outline — AI Agent 使用指南

## 何时使用

在提取代码内容（`extract_code_section`）**之前**使用此工具。先调用此工具了解文件结构，然后仅获取你需要的方法体。

## SMART 工作流中的位置

```
Set → **Map** (本工具) → Analyze → Retrieve → Trace
       ↑
    首先在这里
```

## 典型调用模式

```python
# 1. get_code_outline(file_path="BigService.java") → 获取层级结构
# 2. extract_code_section(file_path=..., start_line=N, end_line=M) → 获取方法体
```

### 示例：分析大型 Java 文件

```python
# 步骤 1: 获取大纲（TOON 格式，54-56% token 节省）
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "src/main/java/BigService.java",
    "output_format": "toon"  # 默认值
})

# 响应示例（TOON 格式）:
# success: true
# outline:
#   file_path: src/main/java/BigService.java
#   language: java
#   total_lines: 1419
#   package: com.example.service
#   statistics:
#     class_count: 1
#     method_count: 66
#   classes:
#     - name: BigService
#       type: class
#       lines: 14-1419
#       methods:
#         [66]{name,returns,params,vis,static,lines}:
#           processPayment,PaymentResult,"orderId:String,amount:BigDecimal",public,false,93-125
#           validateOrder,boolean,"order:Order",private,false,127-156
#           ...

# 步骤 2: 现在你知道 processPayment 在 93-125 行，只提取那部分
code = await mcp.call_tool("extract_code_section", {
    "file_path": "src/main/java/BigService.java",
    "start_line": 93,
    "end_line": 125
})
```

## Token 指导

- **默认 `output_format="toon"`**：与 JSON 相比节省 54-56% token
- **仅在下游工具需要结构化数据时使用 `"json"`**

### Token 节省示例

| 文件大小 | JSON Token | TOON Token | 节省率 |
|---------|-----------|-----------|--------|
| 小文件 (335 行, 1 类 10 方法) | ~800 | ~350 | 56% |
| 中文件 (786 行, 3 类 31 方法) | ~2400 | ~1100 | 54% |
| 大文件 (1420 行, 1 类 66 方法) | ~5200 | ~2300 | 56% |

## 参数

```json
{
  "file_path": "必需 - 源文件路径",
  "language": "可选 - 编程语言（未提供时自动检测）",
  "include_fields": "可选 - 包含类/结构字段（默认: false）",
  "include_imports": "可选 - 包含导入语句（默认: false）",
  "output_format": "可选 - 'toon'（推荐）或 'json'（默认: toon）"
}
```

## 何时包含字段和导入

```python
# 分析数据模型 → 包含字段
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "models/User.java",
    "include_fields": True  # 查看所有字段：id, name, email, createdAt...
})

# 跟踪依赖关系 → 包含导入
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "services/PaymentService.java",
    "include_imports": True  # 查看依赖：Stripe API, database, etc.
})
```

## Intent Alias

此工具也可通过 intent-based alias 调用：

```python
# 这两个调用完全相同：
await mcp.call_tool("get_code_outline", {"file_path": "..."})
await mcp.call_tool("navigate_structure", {"file_path": "..."})
```

## 与其他工具的组合

### 与 extract_code_section 配合

```python
# 1. 获取大纲 → 找到感兴趣的方法
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "BigService.java"
})

# 2. 提取特定方法
code = await mcp.call_tool("extract_code_section", {
    "file_path": "BigService.java",
    "start_line": 93,
    "end_line": 125
})
```

### 与 analyze_code_structure 配合

```python
# get_code_outline: 快速大纲，无方法体
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "Service.java"
})

# analyze_code_structure: 完整分析，包括复杂度、依赖关系
analysis = await mcp.call_tool("analyze_code_structure", {
    "file_path": "Service.java"
})
```

## 支持的语言

17 种语言：Java, Python, TypeScript, JavaScript, C, C++, C#, SQL, HTML, CSS, Go, Rust, Kotlin, PHP, Ruby, YAML, Markdown

## 错误处理

```python
# 文件不存在
response = await mcp.call_tool("get_code_outline", {
    "file_path": "does_not_exist.java"
})
# → {"success": false, "error": "File not found: does_not_exist.java"}

# 语言不支持
response = await mcp.call_tool("get_code_outline", {
    "file_path": "file.xyz",
    "language": "unknown"
})
# → {"success": false, "error": "Language 'unknown' is not supported"}
```

## 性能特征

- **速度**：快速 AST 解析，无需完整编译
- **内存**：仅加载结构元数据，不加载方法体
- **Token 效率**：TOON 格式比 JSON 节省 54-56%

## 最佳实践

1. ✅ **总是先用 get_code_outline，后用 extract_code_section**
   - 避免盲目提取整个大文件
   - 仅获取你需要的代码部分

2. ✅ **对大文件使用 TOON 格式**
   - 默认 `output_format="toon"` 已优化 token 使用
   - 仅在需要程序化解析时使用 JSON

3. ✅ **仅在需要时包含字段和导入**
   - 默认情况下排除以减少 token 消耗
   - 分析数据模型时包含字段
   - 跟踪依赖关系时包含导入

4. ❌ **不要将此工具用于单个方法的小文件**
   - 直接使用 `extract_code_section` 或 `analyze_code_structure`
   - 此工具针对多类/多方法文件优化

## 示例用例

### 用例 1：理解遗留代码库

```python
# 问题：2000 行的 Java 服务，不知道从哪里开始
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "legacy/BigService.java",
    "include_imports": True
})

# 现在你知道：
# - 66 个方法（按名称排序）
# - 哪些是 public（API 入口点）
# - 哪些是 private（内部辅助方法）
# - 每个方法在哪一行
# - 依赖于哪些外部库
```

### 用例 2：跟踪业务逻辑

```python
# 问题：需要理解支付流程，但文件很大
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "PaymentController.java"
})

# 找到 processPayment 在 93-125 行，validateOrder 在 127-156 行
# 仅提取这两个方法：
payment_code = await mcp.call_tool("extract_code_section", {
    "file_path": "PaymentController.java",
    "start_line": 93,
    "end_line": 156
})
```

### 用例 3：准备 AI 上下文

```python
# 问题：AI 助手需要修改一个大文件中的方法，但完整文件太大无法放入上下文

# 步骤 1: 获取大纲（TOON 格式，~300 token）
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "BigService.java",
    "output_format": "toon"
})

# 步骤 2: AI 识别相关方法（例如 processPayment 在 93-125 行）

# 步骤 3: 仅提取该方法（~100 token）
code = await mcp.call_tool("extract_code_section", {
    "file_path": "BigService.java",
    "start_line": 93,
    "end_line": 125
})

# 总计：~400 token vs 加载整个文件的 ~5000 token（节省 92%）
```

## 技术细节

- **实现**：基于 tree-sitter AST 解析
- **格式**：TOON（Tree-Oriented Object Notation）用于紧凑表示
- **线程安全**：是（异步）
- **缓存**：无（每次调用都重新解析，适用于频繁变化的文件）

## 相关工具

| 工具 | 何时使用 |
|------|---------|
| `get_code_outline` | 首先使用 - 获取文件结构地图 |
| `extract_code_section` | 之后使用 - 仅获取你需要的代码部分 |
| `analyze_code_structure` | 深度分析 - 复杂度、依赖关系、指标 |
| `search_content` | 跨项目搜索 - 找到包含特定模式的所有文件 |
| `list_files` | 项目发现 - 找到所有匹配特定模式的文件 |

## 版本历史

- **v1.10.5** (2026-03-28): 引入 TOON 格式（54-56% token 节省），intent alias `navigate_structure`
- **v1.10.4** (2025-02-15): 初始版本，仅 JSON 输出

---

**🎯 记住：Map first, then retrieve. 此工具是你的地图。**
