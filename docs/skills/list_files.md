# list_files — AI Agent 使用指南

## 何时使用

发现项目结构 - 找到匹配特定模式的所有文件。在搜索**内容**之前先映射项目的**结构**。

## SMART 工作流中的位置

```
Set → **Map** (本工具) → Analyze → Retrieve → Trace
       ↑
   首先在这里
```

## Intent Alias

此工具有两个 intent-based alias：

```python
# 这三个调用完全相同：
await mcp.call_tool("list_files", {"roots": [...], "pattern": "*.java"})
await mcp.call_tool("map_structure", {"roots": [...], "pattern": "*.java"})
await mcp.call_tool("discover_files", {"roots": [...], "pattern": "*.java"})
```

## 典型调用模式

### 示例 1：找到所有 Java 文件

```python
# 问题：这个项目有哪些 Java 文件？
result = await mcp.call_tool("map_structure", {
    "roots": ["/path/to/project"],
    "pattern": "*.java",
    "glob": True,
    "output_format": "json"
})

# 响应：
# {
#   "success": true,
#   "count": 342,
#   "results": [
#     {"path": "src/main/java/com/example/UserService.java", "size": 15234},
#     {"path": "src/main/java/com/example/PaymentService.java", "size": 23456},
#     ...
#   ]
# }
```

### 示例 2：按目录层级过滤

```python
# 问题：只找 services 目录下的文件，不包括子目录
result = await mcp.call_tool("list_files", {
    "roots": ["/project/src"],
    "pattern": "services/*.java",  # 仅顶层
    "max_depth": 1,
    "glob": True
})
```

### 示例 3：多模式匹配

```python
# 问题：找到所有配置文件
result = await mcp.call_tool("discover_files", {
    "roots": ["/project"],
    "pattern": "*.{yaml,yml,json,toml}",  # 多个扩展名
    "glob": True
})
```

## 参数

```json
{
  "roots": "必需 - 搜索根目录列表",
  "pattern": "必需 - 文件模式（glob 或正则表达式）",
  "glob": "可选 - true 使用 glob 语法，false 使用正则（默认: true）",
  "max_depth": "可选 - 最大目录深度（默认: 无限制）",
  "exclude": "可选 - 排除的模式列表",
  "output_format": "可选 - 'json' 或 'toon'（默认: json）"
}
```

## 与其他工具的组合

### 与 get_code_outline 配合

```python
# 步骤 1: 找到所有 Service 文件
files = await mcp.call_tool("map_structure", {
    "roots": ["/project"],
    "pattern": "*Service.java",
    "glob": True
})

# 步骤 2: 对每个文件获取大纲
for file in files["results"]:
    outline = await mcp.call_tool("get_code_outline", {
        "file_path": file["path"]
    })
```

### 与 search_content 配合

```python
# 步骤 1: 找到所有可能的文件
files = await mcp.call_tool("list_files", {
    "roots": ["/project"],
    "pattern": "*.java",
    "glob": True
})

# 步骤 2: 在这些文件中搜索特定模式
result = await mcp.call_tool("search_content", {
    "roots": ["/project"],
    "query": "processPayment",
    "include_globs": ["*.java"]
})
```

## Glob 模式语法

```python
# 基本通配符
"*.java"              # 当前目录中的所有 .java 文件
"**/*.java"           # 所有目录中的所有 .java 文件（递归）
"src/**/*.java"       # src 下所有目录中的 .java 文件

# 多个扩展名
"*.{java,py,ts}"      # .java、.py 或 .ts 文件

# 字符范围
"test[0-9].java"      # test0.java 到 test9.java

# 否定
"!*Test.java"         # 排除以 Test.java 结尾的文件（与 exclude 参数一起使用）
```

## 最佳实践

1. ✅ **使用 max_depth 限制深度**
   ```python
   # 避免在深度嵌套的 node_modules 中搜索
   result = await mcp.call_tool("list_files", {
       "roots": ["/project"],
       "pattern": "*.js",
       "max_depth": 5,
       "glob": True
   })
   ```

2. ✅ **使用 exclude 排除无关目录**
   ```python
   result = await mcp.call_tool("list_files", {
       "roots": ["/project"],
       "pattern": "*.java",
       "exclude": ["target", "build", ".git"],
       "glob": True
   })
   ```

3. ✅ **先映射，后搜索**
   ```python
   # 首先了解项目结构
   files = await mcp.call_tool("map_structure", {
       "roots": ["/project"],
       "pattern": "**/*.java",
       "glob": True
   })

   # 然后决定在哪里搜索
   result = await mcp.call_tool("search_content", {
       "roots": ["/project/src/services"],
       "query": "processPayment"
   })
   ```

4. ❌ **不要在没有模式的情况下列出所有文件**
   ```python
   # 不好：列出项目中的所有文件
   result = await mcp.call_tool("list_files", {
       "roots": ["/huge-project"],
       "pattern": "*",  # 太宽泛！
       "glob": True
   })

   # 好：指定你要查找的内容
   result = await mcp.call_tool("list_files", {
       "roots": ["/huge-project"],
       "pattern": "**/*Service.java",
       "glob": True
   })
   ```

## 示例用例

### 用例 1：项目审计

```python
# 问题：项目有多少个测试文件？
test_files = await mcp.call_tool("discover_files", {
    "roots": ["/project"],
    "pattern": "**/*Test.{java,py,ts}",
    "glob": True
})

print(f"找到 {test_files['count']} 个测试文件")
```

### 用例 2：遗留代码发现

```python
# 问题：项目中还有哪些 JSP 文件（遗留代码）？
jsp_files = await mcp.call_tool("list_files", {
    "roots": ["/project"],
    "pattern": "**/*.jsp",
    "glob": True
})

# 现在你知道需要迁移哪些文件
```

### 用例 3：依赖映射

```python
# 问题：项目有哪些配置文件？
config_files = await mcp.call_tool("map_structure", {
    "roots": ["/project"],
    "pattern": "*.{yaml,yml,properties,xml}",
    "exclude": ["target", "build"],
    "glob": True
})
```

## 性能特征

- **引擎**：基于 fd（极快的文件发现）
- **大型仓库**：可以在几秒钟内扫描数百万个文件
- **内存**：高效（不读取文件内容）
- **并发**：自动并行化搜索

## 与 find 命令的对比

| 功能 | list_files | find 命令 |
|------|-----------|----------|
| 速度 | 非常快（基于 fd） | 较慢（递归遍历） |
| Glob 支持 | 原生支持 | 需要 -name 标志 |
| Git 集成 | 自动排除 .gitignore | 需要手动排除 |
| 跨平台 | 一致行为 | 平台差异 |

## 相关工具

| 工具 | 何时使用 |
|------|---------|
| `list_files` | 你只需要文件列表 |
| `search_content` | 你需要在文件**内**搜索 |
| `find_and_grep` | 你需要两者：先找文件，再搜索内容 |
| `get_code_outline` | 你需要文件的**结构**（类、方法） |

## 版本历史

- **v1.10.5** (2026-03-28): 添加 intent aliases `map_structure` 和 `discover_files`
- **v1.9.0** (2025-01-10): 初始版本

---

**🎯 记住：在搜索内容之前先映射结构。这是你的项目地图。**
