# find_and_grep — AI Agent 使用指南

## 何时使用

2 段階統合検索——先找文件（fd），再搜索内容（ripgrep）。适合"在特定类型的文件中查找特定模式"的场景。

## SMART 工作流中的位置

```
Set → **Map** (本工具，阶段 1) → **Analyze** (本工具，阶段 2) → Retrieve → Trace
       ↑                              ↑
   先找文件                        再搜内容
```

## 典型调用模式

### 示例 1：找到所有 Java 文件中的 processPayment 调用

```python
# 问题：processPayment 方法在哪些地方被调用？
result = await mcp.call_tool("find_and_grep", {
    "roots": ["/path/to/project"],
    "query": "processPayment",
    "extensions": ["java"]  # 阶段 1: 只看 .java 文件
})

# 响应：
# {
#   "success": true,
#   "total_matches": 15,
#   "total_files": 8,
#   "results": [
#     {
#       "file": "src/controllers/PaymentController.java",
#       "line": 45,
#       "match": "this.service.processPayment(order, amount);"
#     },
#     {
#       "file": "src/services/OrderService.java",
#       "line": 123,
#       "match": "paymentService.processPayment(orderId, total);"
#     },
#     ...
#   ]
# }
```

### 示例 2：查找最近修改的配置文件中的 API 密钥

```python
# 问题：最近修改的配置文件中是否有硬编码的 API 密钥？
result = await mcp.call_tool("find_and_grep", {
    "roots": ["/project"],
    "pattern": "*.{yaml,yml,json,env}",  # 阶段 1: 配置文件
    "glob": true,
    "changed_within": "7d",  # 阶段 1: 最近 7 天修改的文件
    "query": "(api_key|secret|token)\\s*[=:]\\s*['\"]\\w+['\"]"  # 阶段 2: 正则查找密钥
})
```

### 示例 3：大规模搜索（Token 优化）

```python
# 问题：整个代码库中有多少处使用了 TODO 注释？
result = await mcp.call_tool("find_and_grep", {
    "roots": ["/huge-project"],
    "query": "TODO:",
    "extensions": ["java", "py", "ts", "js"],
    "total_only": true  # 只返回总数，不返回匹配详情（最大 token 节省）
})

# 响应：
# {
#   "success": true,
#   "total_matches": 342,
#   "total_files": 156
# }
```

### 示例 4：多条件文件查找 + 内容搜索

```python
# 问题：在最近修改的、大于 100KB 的 Python 文件中查找 deprecated 函数
result = await mcp.call_tool("find_and_grep", {
    "roots": ["/project"],
    "extensions": ["py"],           # 阶段 1: 只看 Python 文件
    "size": ["+100k"],               # 阶段 1: 大于 100KB
    "changed_within": "30d",         # 阶段 1: 最近 30 天修改
    "query": "@deprecated",          # 阶段 2: 查找 @deprecated 装饰器
    "group_by_file": true            # Token 优化: 按文件分组
})
```

## 参数

### 阶段 1: 文件查找参数（fd）

```json
{
  "roots": "必需 - 搜索根目录列表",
  "pattern": "可选 - 文件名模式",
  "glob": "可选 - 将 pattern 作为 glob 处理（默认: false）",
  "types": "可选 - 文件类型（例如 ['python', 'java']）",
  "extensions": "可选 - 文件扩展名（例如 ['py', 'java']）",
  "exclude": "可选 - 排除模式列表",
  "depth": "可选 - 最大搜索深度",
  "follow_symlinks": "可选 - 跟随符号链接（默认: false）",
  "hidden": "可选 - 包含隐藏文件（默认: false）",
  "no_ignore": "可选 - 忽略 .gitignore（默认: false）",
  "size": "可选 - 文件大小过滤器（例如 ['+100k', '-1M']）",
  "changed_within": "可选 - 修改时间过滤器（例如 '7d', '2w', '1M'）",
  "changed_before": "可选 - 修改前时间过滤器",
  "full_path_match": "可选 - 全路径匹配（默认: false）",
  "file_limit": "可选 - 最大文件数",
  "sort": "可选 - 排序方式（'path'/'mtime'/'size'）"
}
```

### 阶段 2: 内容搜索参数（ripgrep）

```json
{
  "query": "必需 - 搜索查询（支持正则表达式）",
  "case": "可选 - 大小写敏感（'smart'/'insensitive'/'sensitive'，默认: smart）",
  "fixed_strings": "可选 - 字面量字符串搜索（默认: false）",
  "word": "可选 - 单词边界匹配（默认: false）",
  "multiline": "可选 - 允许多行匹配（默认: false）",
  "include_globs": "可选 - 包含的文件模式",
  "exclude_globs": "可选 - 排除的文件模式",
  "max_filesize": "可选 - 最大文件大小",
  "context_before": "可选 - 匹配前的上下文行数",
  "context_after": "可选 - 匹配后的上下文行数",
  "encoding": "可选 - 文件编码",
  "max_count": "可选 - 每个文件的最大匹配数",
  "timeout_ms": "可选 - 超时（毫秒）"
}
```

### Token 优化参数

```json
{
  "count_only_matches": "可选 - 仅返回匹配数（默认: false）",
  "summary_only": "可选 - 仅返回摘要（默认: false）",
  "group_by_file": "可选 - 按文件分组（默认: false）",
  "total_only": "可选 - 仅返回总数（默认: false）",
  "output_file": "可选 - 输出文件名",
  "suppress_output": "可选 - 抑制响应输出（默认: false）"
}
```

## Token 优化策略

### 适合小规模搜索（< 100 个匹配）
```python
# 直接获取完整结果
result = await mcp.call_tool("find_and_grep", {
    "roots": ["/project"],
    "query": "processPayment",
    "extensions": ["java"]
})
```

### 适合中等规模搜索（100-500 个匹配）
```python
# 按文件分组，减少重复路径
result = await mcp.call_tool("find_and_grep", {
    "roots": ["/project"],
    "query": "TODO",
    "extensions": ["java", "py"],
    "group_by_file": true  # 节省 30-40% token
})
```

### 适合大规模搜索（500+ 个匹配）
```python
# 只返回总数和摘要
result = await mcp.call_tool("find_and_grep", {
    "roots": ["/huge-project"],
    "query": "deprecated",
    "total_only": true  # 节省 90%+ token
})

# 或保存到文件
result = await mcp.call_tool("find_and_grep", {
    "roots": ["/huge-project"],
    "query": "deprecated",
    "output_file": "search_results.txt",
    "suppress_output": true  # 节省 90%+ token
})
```

## 与其他工具的组合

### 与 list_files 配合

```python
# list_files: 只找文件
files = await mcp.call_tool("list_files", {
    "roots": ["/project"],
    "pattern": "*.java",
    "glob": true
})

# find_and_grep: 找文件 + 搜索内容（二合一）
result = await mcp.call_tool("find_and_grep", {
    "roots": ["/project"],
    "pattern": "*.java",
    "glob": true,
    "query": "processPayment"
})
```

**何时用哪个？**
- `list_files` → 只需要文件列表
- `find_and_grep` → 需要文件列表 + 内容匹配

### 与 search_content 配合

```python
# search_content: 直接搜索内容（一步）
result = await mcp.call_tool("search_content", {
    "roots": ["/project"],
    "query": "processPayment"
})

# find_and_grep: 先找文件，再搜内容（二步，更精确）
result = await mcp.call_tool("find_and_grep", {
    "roots": ["/project"],
    "pattern": "*Service.java",  # 阶段 1: 只在 Service 文件中搜索
    "glob": true,
    "query": "processPayment"     # 阶段 2: 查找方法调用
})
```

**何时用哪个？**
- `search_content` → 简单搜索，不需要文件过滤
- `find_and_grep` → 复杂搜索，需要按文件类型/大小/时间过滤

### 与 get_code_outline 配合

```python
# 1. 找到所有包含 processPayment 的文件
matches = await mcp.call_tool("find_and_grep", {
    "roots": ["/project"],
    "query": "processPayment",
    "extensions": ["java"],
    "group_by_file": true
})

# 2. 对每个匹配的文件获取大纲
for file in matches["files"]:
    outline = await mcp.call_tool("get_code_outline", {
        "file_path": file["path"],
        "output_format": "toon"
    })
```

## 文件查找模式

### Glob 模式（阶段 1）

```python
# 基本 glob
"*.java"              # 当前目录中的所有 .java 文件
"**/*.java"           # 所有目录中的所有 .java 文件（递归）
"src/**/*Test.java"   # src 下所有 Test.java 文件

# 多个扩展名
"*.{java,py,ts}"      # .java、.py 或 .ts 文件

# 排除模式
exclude: ["target", "build", ".git"]
```

### 文件大小过滤（阶段 1）

```python
size: ["+100k"]       # 大于 100KB
size: ["-1M"]         # 小于 1MB
size: ["+100k", "-1M"]  # 100KB 到 1MB 之间
```

### 时间过滤（阶段 1）

```python
changed_within: "7d"   # 最近 7 天修改
changed_within: "2w"   # 最近 2 周修改
changed_within: "1M"   # 最近 1 个月修改
changed_before: "30d"  # 30 天前修改
```

## 内容搜索模式

### 正则表达式（阶段 2）

```python
# 基本正则
query: "processPayment"                        # 字面量匹配
query: "process.*Payment"                      # 模式匹配
query: "\\btest\\b"                            # 单词边界
query: "(api_key|secret)\\s*=\\s*['\"]\\w+['\"]"  # 复杂模式

# 多行匹配
query: "class.*\\{[\\s\\S]*?processPayment"
multiline: true
```

### 大小写敏感（阶段 2）

```python
case: "smart"        # 智能：查询全小写时不区分大小写，否则区分
case: "insensitive"  # 不区分大小写
case: "sensitive"    # 区分大小写
```

## 性能特征

- **阶段 1 (fd)**：基于 fd，极快的文件发现（数百万文件，几秒钟）
- **阶段 2 (ripgrep)**：基于 ripgrep，极快的内容搜索
- **内存**：高效（不将整个仓库加载到内存中）
- **并发**：自动并行化搜索

## 最佳实践

1. ✅ **使用文件过滤缩小阶段 2 的搜索范围**
   ```python
   # 好：只在相关文件中搜索
   result = await mcp.call_tool("find_and_grep", {
       "roots": ["/project"],
       "extensions": ["java"],  # 阶段 1: 只看 Java 文件
       "query": "processPayment"
   })

   # 不好：在所有文件中搜索（包括二进制文件、日志等）
   result = await mcp.call_tool("find_and_grep", {
       "roots": ["/project"],
       "query": "processPayment"  # 搜索所有文件，浪费时间
   })
   ```

2. ✅ **使用 exclude 排除无关目录**
   ```python
   result = await mcp.call_tool("find_and_grep", {
       "roots": ["/project"],
       "query": "TODO",
       "exclude": ["node_modules", "vendor", ".git", "target", "build"]
   })
   ```

3. ✅ **对大规模搜索使用 token 优化**
   ```python
   # 中等规模：按文件分组
   result = await mcp.call_tool("find_and_grep", {
       "roots": ["/project"],
       "query": "deprecated",
       "group_by_file": true
   })

   # 大规模：只返回总数
   result = await mcp.call_tool("find_and_grep", {
       "roots": ["/huge-project"],
       "query": "TODO",
       "total_only": true
   })
   ```

4. ❌ **不要在大型仓库中不加过滤地搜索**
   ```python
   # 不好：搜索整个 monorepo 中的 "a"
   result = await mcp.call_tool("find_and_grep", {
       "roots": ["/huge-monorepo"],
       "query": "a"  # 太宽泛！
   })

   # 好：缩小范围
   result = await mcp.call_tool("find_and_grep", {
       "roots": ["/huge-monorepo/services/payment"],
       "extensions": ["java"],
       "query": "authenticateUser"
   })
   ```

## 示例用例

### 用例 1：安全审计

```python
# 问题：代码库中是否有硬编码的密码或密钥？
secrets = await mcp.call_tool("find_and_grep", {
    "roots": ["/project"],
    "pattern": "*.{java,py,js,ts,yml,yaml,json}",
    "glob": true,
    "exclude": [".env", ".git", "node_modules", "test"],
    "query": "(password|secret|api_key|token)\\s*[=:]\\s*['\"]\\w+['\"]"
})
```

### 用例 2：代码迁移

```python
# 问题：需要将所有 @Deprecated 方法迁移到新 API
deprecated = await mcp.call_tool("find_and_grep", {
    "roots": ["/project"],
    "extensions": ["java"],
    "query": "@Deprecated",
    "context_after": 1  # 显示注解后的方法签名
})
```

### 用例 3：最近修改的代码审查

```python
# 问题：最近一周修改的文件中是否有 console.log（调试代码忘记删除）
debug_code = await mcp.call_tool("find_and_grep", {
    "roots": ["/project/src"],
    "extensions": ["js", "ts"],
    "changed_within": "7d",  # 阶段 1: 最近一周修改的文件
    "query": "console\\.log",   # 阶段 2: 查找 console.log
    "group_by_file": true
})
```

### 用例 4：大文件搜索

```python
# 问题：大于 500KB 的文件中是否有性能问题（嵌套循环）
large_files_issues = await mcp.call_tool("find_and_grep", {
    "roots": ["/project"],
    "extensions": ["java", "py"],
    "size": ["+500k"],  # 阶段 1: 只看大文件
    "query": "for.*for.*for",  # 阶段 2: 查找三重嵌套循环
    "multiline": true
})
```

## 支持的语言

17 种语言：Java, Python, TypeScript, JavaScript, C, C++, C#, SQL, HTML, CSS, Go, Rust, Kotlin, PHP, Ruby, YAML, Markdown

## 技术细节

- **实现**：fd（阶段 1）+ ripgrep（阶段 2）
- **并发**：自动并行化搜索
- **内存**：高效（流式处理）
- **缓存**：支持 .gitignore 缓存

## 相关工具

| 工具 | 何时使用 |
|------|---------
| `find_and_grep` | 你需要先找文件，然后在其中搜索（二步） |
| `search_content` | 你知道要搜索什么（模式、关键词），一步直达 |
| `list_files` | 你只需要文件列表，不需要内容搜索 |
| `get_code_outline` | 你需要文件的**结构**（类、方法），不是内容搜索 |

## 版本历史

- **v1.10.4** (2025-02-15): 初始版本，支持 fd + ripgrep 集成

---

**🎯 记住：先找对文件，再搜对内容。这是你的精准狙击工具。**
