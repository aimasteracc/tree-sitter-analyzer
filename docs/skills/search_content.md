# search_content — AI Agent 使用指南

## 何时使用

跨项目搜索特定模式、关键词或正则表达式。找到**所有**包含特定代码模式的文件。

## SMART 工作流中的位置

```
Set → Map → **Analyze** (本工具) → Retrieve → Trace
               ↑
          在这里查找
```

## Intent Alias

此工具有两个 intent-based alias：

```python
# 这三个调用完全相同：
await mcp.call_tool("search_content", {"roots": [...], "query": "..."})
await mcp.call_tool("locate_usage", {"roots": [...], "query": "..."})
await mcp.call_tool("find_usage", {"roots": [...], "query": "..."})
```

## 典型调用模式

### 示例 1：找到某个类的所有使用位置

```python
# 问题：UserService 在哪里被使用？
result = await mcp.call_tool("locate_usage", {
    "roots": ["/path/to/project"],
    "query": "UserService",
    "output_format": "json"
})

# 响应：
# {
#   "success": true,
#   "count": 15,
#   "results": [
#     {"file": "src/controllers/AuthController.java", "line": 23, "match": "private UserService userService;"},
#     {"file": "src/services/PaymentService.java", "line": 45, "match": "this.userService.findById(userId)"},
#     ...
#   ]
# }
```

### 示例 2：正则表达式搜索

```python
# 问题：找到所有 public static final 常量定义
result = await mcp.call_tool("search_content", {
    "roots": ["/path/to/project"],
    "query": "public\\s+static\\s+final\\s+\\w+\\s+\\w+\\s*=",  # 正则表达式
    "include_globs": ["*.java"],
    "case": "sensitive"
})
```

## 参数

```json
{
  "query": "必需 - 搜索模式（支持正则表达式）",
  "roots": "可选 - 搜索根目录列表（也可用 files 指定具体文件）",
  "files": "可选 - 具体文件路径列表（替代 roots）",
  "include_globs": "可选 - 包含的文件模式列表（例如 ['*.java', '*.py']）",
  "exclude_globs": "可选 - 排除的 glob 模式列表",
  "case": "可选 - 'sensitive', 'insensitive' 或 'smart'（默认: smart）",
  "fixed_strings": "可选 - 是否使用固定字符串而非正则（默认: false）",
  "word": "可选 - 是否仅匹配整词（默认: false）",
  "output_format": "可选 - 'json' 或 'toon'（默认: toon）"
}
```

## 与其他工具的组合

### 与 get_code_outline 配合

```python
# 步骤 1: 找到所有使用 processPayment 的文件
locations = await mcp.call_tool("locate_usage", {
    "roots": ["/project"],
    "query": "processPayment"
})

# 步骤 2: 对每个文件获取大纲以理解上下文
for location in locations["results"]:
    outline = await mcp.call_tool("get_code_outline", {
        "file_path": location["file"]
    })
```

### 与 find_and_grep 配合

```python
# find_and_grep: 先找文件，再搜索内容（两步）
# search_content: 直接搜索内容（一步，更快）

# 使用 search_content 当你知道要搜索什么时：
result = await mcp.call_tool("search_content", {
    "roots": ["/project"],
    "query": "UserService"
})
```

## 最佳实践

1. ✅ **使用 include_globs 缩小搜索范围**
   ```python
   # 仅搜索 Java 文件
   result = await mcp.call_tool("search_content", {
       "roots": ["/project"],
       "query": "processPayment",
       "include_globs": ["*.java"]
   })
   ```

2. ✅ **使用 exclude 排除无关目录**
   ```python
   result = await mcp.call_tool("search_content", {
       "roots": ["/project"],
       "query": "TODO",
       "exclude": ["node_modules", "vendor", ".git"]
   })
   ```

3. ✅ **区分大小写敏感和不敏感**
   ```python
   # 查找精确匹配（例如类名）
   result = await mcp.call_tool("search_content", {
       "roots": ["/project"],
       "query": "UserService",
       "case": "sensitive"
   })

   # 查找所有变体（例如注释中的提及）
   result = await mcp.call_tool("search_content", {
       "roots": ["/project"],
       "query": "user service",
       "case": "insensitive"
   })
   ```

4. ❌ **不要在大型仓库中不加过滤地搜索**
   ```python
   # 不好：在整个仓库中搜索 "a"
   result = await mcp.call_tool("search_content", {
       "roots": ["/huge-monorepo"],
       "query": "a"  # 太宽泛！
   })

   # 好：缩小范围
   result = await mcp.call_tool("search_content", {
       "roots": ["/huge-monorepo/services"],
       "query": "authenticateUser",
       "include_globs": ["*.java"]
   })
   ```

## 示例用例

### 用例 1：影响分析

```python
# 问题：如果我修改 processPayment 方法，哪些地方会受影响？
affected = await mcp.call_tool("locate_usage", {
    "roots": ["/project"],
    "query": "processPayment",
    "include_globs": ["*.java"],
    "case": "sensitive"
})

# 响应显示所有调用 processPayment 的位置
# 现在你知道需要测试哪些文件
```

### 用例 2：安全审计

```python
# 问题：代码库中是否有硬编码的密码或密钥？
secrets = await mcp.call_tool("search_content", {
    "roots": ["/project"],
    "query": "(password|secret|api_key)\\s*=\\s*['\\\"]\\w+['\\\"]",
    "exclude": [".env", ".git", "node_modules"]
})
```

### 用例 3：代码迁移

```python
# 问题：需要将所有 @Deprecated 方法迁移到新 API
deprecated = await mcp.call_tool("search_content", {
    "roots": ["/project"],
    "query": "@Deprecated",
    "include_globs": ["*.java"]
})

# 现在你有一个需要更新的所有文件的清单
```

## 性能特征

- **引擎**：基于 ripgrep（非常快速）
- **大型仓库**：可以在几秒钟内搜索数百万行代码
- **内存**：高效（不将整个仓库加载到内存中）
- **并发**：自动并行化搜索

## 支持的搜索模式

- **字面量文本**：`"UserService"`
- **正则表达式**：`"class\\s+\\w+Service"`
- **单词边界**：`"\\btest\\b"`（匹配 "test" 但不匹配 "testing"）
- **多行模式**：使用 `(?s)` 标志

## 相关工具

| 工具 | 何时使用 |
|------|---------|
| `search_content` | 你知道要搜索什么（模式、关键词） |
| `find_and_grep` | 你需要先找文件，然后在其中搜索（两步） |
| `list_files` | 你只需要文件列表，不需要内容搜索 |

## 版本历史

- **v1.10.5** (2026-03-28): 添加 intent aliases `locate_usage` 和 `find_usage`
- **v1.9.0** (2025-01-10): 初始版本

---

**🎯 记住：快速找到代码，无论它在哪里。这是你的代码库搜索引擎。**
