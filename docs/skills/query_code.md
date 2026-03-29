# query_code — AI 使用指南

## 工具别名（Intent Aliases）

- **extract_pattern** — 提取代码模式
- **find_elements** — 查找代码元素
- **query_syntax** — 查询语法树

## 何时使用

当需要提取特定类型的代码元素（方法、类、函数、导入等）或使用 tree-sitter query 语法查找自定义模式时使用。

**query_code vs 其他工具：**
- **query_code** — 提取特定类型的代码元素（使用 tree-sitter query）
- **search_content** — 全文本搜索（ripgrep，基于文本）
- **find_and_grep** — 文件查找 + 内容搜索组合
- **get_code_outline** — 获取完整的层级大纲

## SMART Workflow 位置

Set → Map → **Analyze**（本工具）→ Retrieve → Trace

在 SMART workflow 的 **Analyze** 步骤使用 `query_code`：
1. **Set**：明确查询目标
2. **Map**：了解项目结构
3. **Analyze**（本工具）：提取特定代码元素
4. **Retrieve**：获取详细代码内容
5. **Trace**：追踪依赖和影响

## 典型调用模式

### 模式 1：预定义查询（最常用）

```python
# 查询所有方法
methods = await mcp.call_tool("query_code", {
    "file_path": "src/services/UserService.java",
    "query_key": "methods"  # 预定义查询
})

# 响应示例：
# {
#   "success": true,
#   "query_result": {
#     "file_path": "src/services/UserService.java",
#     "language": "java",
#     "query_type": "methods",
#     "total_matches": 12,
#     "matches": [
#       {
#         "name": "getUserById",
#         "type": "method",
#         "start_line": 23,
#         "end_line": 35,
#         "start_column": 4,
#         "end_column": 5
#       },
#       {
#         "name": "createUser",
#         "type": "method",
#         "start_line": 37,
#         "end_line": 52,
#         "start_column": 4,
#         "end_column": 5
#       },
#       // ... 更多方法
#     ]
#   }
# }

# 可用的预定义查询：
# - "methods" — 所有方法
# - "classes" — 所有类
# - "functions" — 所有函数
# - "imports" — 所有导入语句
# - "variables" — 所有变量
# - "comments" — 所有注释
```

### 模式 2：自定义 Tree-sitter Query（高级）

```python
# 使用自定义 tree-sitter query 语法
custom_query = await mcp.call_tool("query_code", {
    "file_path": "src/api/Controller.java",
    "query_string": """
        (method_declaration
          (modifiers
            (annotation
              name: (identifier) @annotation_name))
          name: (identifier) @method_name)
    """
})

# 这个查询会找到所有带注解的方法（如 @GetMapping, @PostMapping 等）

# 响应示例：
# {
#   "query_result": {
#     "total_matches": 8,
#     "matches": [
#       {
#         "name": "getUser",  # 从 @method_name 捕获
#         "type": "method_declaration",
#         "start_line": 45,
#         "end_line": 58
#       },
#       // ...
#     ]
#   }
# }
```

### 模式 3：结合过滤表达式（精确查询）

```python
# 查询所有方法，但只要以 "get" 开头的
getters = await mcp.call_tool("query_code", {
    "file_path": "src/model/User.java",
    "query_key": "methods",
    "filter": "name=~get*"  # 过滤：名称匹配 get*
})

# 更复杂的过滤：
# - "name=main" — 精确匹配名称
# - "name=~get*" — 通配符匹配
# - "name=~get*,public=true" — 多条件（逗号分隔）
# - "start_line>100" — 按行号过滤

# 响应仅包含匹配的方法：
# {
#   "query_result": {
#     "total_matches": 5,
#     "matches": [
#       {"name": "getUserId", ...},
#       {"name": "getUserName", ...},
#       {"name": "getUserEmail", ...},
#       // ...
#     ]
#   }
# }
```

### 模式 4：输出到文件（大结果集）

```python
# 查询大文件的所有类和方法，保存到文件
result = await mcp.call_tool("query_code", {
    "file_path": "src/services/LegacyService.java",
    "query_key": "methods",
    "output_file": "legacy_methods.json",  # 保存到文件
    "suppress_output": true  # 不返回内容（节省 token）
})

# 响应：
# {
#   "success": true,
#   "output_file_path": "/tmp/legacy_methods.json",
#   "message": "Query results saved to file"
# }
# 然后可以读取文件或分段处理
```

### 模式 5：与其他工具的集成

```python
# 场景：重构 - 找到所有 public 方法，然后检查每个方法的调用情况

# 步骤 1: 查询所有 public 方法
methods = await mcp.call_tool("query_code", {
    "file_path": "src/api/UserController.java",
    "query_key": "methods",
    "filter": "public=true"  # 仅 public 方法
})

# 步骤 2: 对每个方法追踪调用情况
for method in methods["query_result"]["matches"]:
    impact = await mcp.call_tool("trace_impact", {
        "symbol": method["name"],
        "file_path": "src/api/UserController.java",
        "project_root": "/path/to/project"
    })
    # 分析每个 public 方法的调用情况

# 步骤 3: 提取需要重构的方法代码
target_method = methods["query_result"]["matches"][0]
code = await mcp.call_tool("extract_code_section", {
    "file_path": "src/api/UserController.java",
    "start_line": target_method["start_line"],
    "end_line": target_method["end_line"]
})
```

## 预定义查询（Query Keys）

| Query Key | 描述 | 适用语言 |
|-----------|------|---------|
| `methods` | 所有方法（包括 public/private/protected） | Java, JavaScript, TypeScript, Python, Go, Rust, C++, C#, PHP, Ruby, Kotlin |
| `classes` | 所有类定义 | Java, JavaScript, TypeScript, Python, C++, C#, PHP, Ruby, Kotlin |
| `functions` | 所有函数（非方法） | JavaScript, TypeScript, Python, Go, Rust, C, C++ |
| `imports` | 所有导入语句 | Java, JavaScript, TypeScript, Python, Go, Rust |
| `variables` | 所有变量声明 | 所有语言 |
| `comments` | 所有注释 | 所有语言 |

## 过滤表达式语法

| 表达式 | 说明 | 示例 |
|--------|------|------|
| `name=VALUE` | 精确匹配名称 | `name=main` |
| `name=~PATTERN` | 通配符匹配 | `name=~get*`（以 get 开头） |
| `name=~PATTERN*` | 前缀匹配 | `name=~test*` |
| `name=~*PATTERN` | 后缀匹配 | `name=~*Util` |
| `public=true` | 只要 public | `public=true` |
| `start_line>N` | 行号大于 N | `start_line>100` |
| `start_line<N` | 行号小于 N | `start_line<500` |
| `EXPR1,EXPR2` | 多条件（AND） | `name=~get*,public=true` |

## 输出格式

### 默认：JSON 格式（详细）

```json
{
  "success": true,
  "query_result": {
    "file_path": "src/services/UserService.java",
    "language": "java",
    "query_type": "methods",
    "total_matches": 12,
    "matches": [
      {
        "name": "getUserById",
        "type": "method",
        "start_line": 23,
        "end_line": 35,
        "start_column": 4,
        "end_column": 5
      }
    ]
  }
}
```

### Summary 格式（简洁）

```python
result = await mcp.call_tool("query_code", {
    "file_path": "Service.java",
    "query_key": "methods",
    "result_format": "summary"  # 简洁格式
})

# 响应示例：
# {
#   "success": true,
#   "summary": "Found 12 methods: getUserById(23-35), createUser(37-52), ..."
# }
```

## Token 优化策略

### 适合小结果集（< 50 个匹配）

```python
# 直接获取结果
methods = await mcp.call_tool("query_code", {
    "file_path": "SmallService.java",
    "query_key": "methods"
})
# Token 消耗：~200-500 tokens
```

### 适合大结果集（50+ 个匹配）

```python
# 保存到文件，不返回内容
result = await mcp.call_tool("query_code", {
    "file_path": "HugeService.java",
    "query_key": "methods",
    "output_file": "methods.json",
    "suppress_output": true  # 节省 90%+ token
})
# Token 消耗：~10 tokens（仅状态消息）

# 然后读取文件或分段处理
```

### 使用过滤减少结果

```python
# 不要查询所有方法然后在客户端过滤
# BAD:
all_methods = await mcp.call_tool("query_code", {
    "file_path": "Service.java",
    "query_key": "methods"
})
# 然后在客户端过滤 → 浪费 token

# GOOD：在服务端过滤
getters = await mcp.call_tool("query_code", {
    "file_path": "Service.java",
    "query_key": "methods",
    "filter": "name=~get*"  # 服务端过滤
})
# 只返回匹配的结果，节省 token
```

## 参数说明

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | string | 是 | - | 要查询的文件路径 |
| `language` | string | 否 | 自动检测 | 编程语言 |
| `query_key` | string | query_key 或 query_string 之一必需 | - | 预定义查询（methods/classes/functions等） |
| `query_string` | string | query_key 或 query_string 之一必需 | - | 自定义 tree-sitter query 字符串 |
| `filter` | string | 否 | - | 过滤表达式（name=main, name=~get*等） |
| `result_format` | string | 否 | "json" | 输出格式："json" 或 "summary" |
| `output_file` | string | 否 | - | 输出文件路径（可选） |
| `suppress_output` | boolean | 否 | false | 是否抑制响应输出（与 output_file 配合使用） |

## 最佳实践

### ✅ DO（推荐做法）

1. **优先使用预定义查询**
   ```python
   # GOOD：使用预定义查询（简单、可靠）
   methods = await mcp.call_tool("query_code", {
       "file_path": "Service.java",
       "query_key": "methods"
   })

   # 仅在特殊需求时使用自定义 query_string
   ```

2. **使用过滤减少结果集**
   ```python
   # GOOD：服务端过滤
   public_methods = await mcp.call_tool("query_code", {
       "file_path": "Service.java",
       "query_key": "methods",
       "filter": "public=true"  # 只返回 public 方法
   })
   ```

3. **大结果集保存到文件**
   ```python
   # GOOD：大文件查询保存到文件
   result = await mcp.call_tool("query_code", {
       "file_path": "LegacyCode.java",
       "query_key": "methods",
       "output_file": "methods.json",
       "suppress_output": true
   })
   # 然后读取文件或分段处理
   ```

### ❌ DON'T（避免做法）

1. **不要在客户端过滤**
   ```python
   # BAD：查询所有，然后在客户端过滤
   all = await mcp.call_tool("query_code", {
       "file_path": "Service.java",
       "query_key": "methods"
   })
   getters = [m for m in all if m["name"].startswith("get")]

   # GOOD：服务端过滤
   getters = await mcp.call_tool("query_code", {
       "file_path": "Service.java",
       "query_key": "methods",
       "filter": "name=~get*"
   })
   ```

2. **不要忽略 output_file 参数**
   ```python
   # BAD：大结果集直接返回（可能溢出 token）
   all_methods = await mcp.call_tool("query_code", {
       "file_path": "HugeService.java",
       "query_key": "methods"
   })

   # GOOD：保存到文件
   result = await mcp.call_tool("query_code", {
       "file_path": "HugeService.java",
       "query_key": "methods",
       "output_file": "methods.json",
       "suppress_output": true
   })
   ```

3. **不要混用 query_key 和 query_string**
   ```python
   # BAD：同时提供两个参数（会报错）
   result = await mcp.call_tool("query_code", {
       "file_path": "Service.java",
       "query_key": "methods",
       "query_string": "(method_declaration) @method"  # 冲突
   })

   # GOOD：只提供其中一个
   result = await mcp.call_tool("query_code", {
       "file_path": "Service.java",
       "query_key": "methods"
   })
   ```

## 性能指标

- **查询时间**：< 3 秒
- **支持的语言**：Java, JavaScript, TypeScript, Python, Markdown, HTML, CSS, Go, Rust, C, C++, C#, PHP, Ruby, Kotlin
- **结果数量限制**：默认无限制（建议使用 filter 或 output_file 处理大结果集）

## 与其他工具的配合

| 场景 | 工具链 |
|------|--------|
| **重构准备** | query_code (找方法) → trace_impact (查影响) → extract_code_section (提取代码) |
| **API 审计** | query_code (找 public 方法) → analyze_code_structure (详细分析) |
| **依赖分析** | query_code (找导入) → search_content (找使用) |
| **代码模式分析** | query_code (自定义 query) → 统计分析 |
| **文档生成** | query_code (找所有方法/类) → 生成文档 |

## 常见问题

**Q: query_code vs search_content 的区别？**
A:
- **query_code** — 基于语法树（AST）的精确查询，理解代码结构
- **search_content** — 基于文本的全文搜索（ripgrep），快速但不理解结构

示例：
- 找所有方法 → 用 `query_code`（结构化查询）
- 找所有包含 "TODO" 的地方 → 用 `search_content`（文本搜索）

**Q: 如何写自定义 query_string？**
A: 参考 tree-sitter query 文档：https://tree-sitter.github.io/tree-sitter/using-parsers#pattern-matching-with-queries

常用模式：
```scheme
# 查找所有函数声明
(function_declaration
  name: (identifier) @function_name) @function

# 查找所有 if 语句
(if_statement) @if

# 查找所有注解
(annotation
  name: (identifier) @annotation_name) @annotation
```

**Q: 过滤表达式支持正则吗？**
A: 支持通配符（`*`），不支持完整正则。
- `name=~get*` — 前缀匹配（支持）
- `name=~*Util` — 后缀匹配（支持）
- `name=~^get.*Id$` — 正则表达式（不支持）

**Q: 如何查询特定行号范围的元素？**
A:
```python
# 查询 100-500 行之间的所有方法
methods = await mcp.call_tool("query_code", {
    "file_path": "Service.java",
    "query_key": "methods",
    "filter": "start_line>100,end_line<500"
})
```
