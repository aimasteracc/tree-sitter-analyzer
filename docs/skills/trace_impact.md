# trace_impact — AI Agent 使用指南

## 何时使用

在重构或修改代码前，找到某个符号（方法、类、函数）的**所有使用位置**，评估变更影响范围（blast radius）。

## SMART 工作流中的位置

```
Set → Map → Analyze → Retrieve → **Trace** (本工具)
                                     ↑
                              在这里追踪影响
```

## Intent Alias

此工具有一个 intent-based alias：

```python
# 这两个调用完全相同：
await mcp.call_tool("trace_impact", {"symbol": "processPayment", "file_path": "..."})
await mcp.call_tool("assess_blast_radius", {"symbol": "processPayment", "file_path": "..."})
```

## 典型调用模式

### 示例 1：重构前的影响分析

```python
# 问题：我要重构 processPayment 方法，哪些地方会受影响？
result = await mcp.call_tool("trace_impact", {
    "symbol": "processPayment",
    "file_path": "src/services/PaymentService.java",  # 源文件（自动过滤到 Java）
    "word_match": True  # 精确匹配整词
})

# 响应：
# {
#   "success": true,
#   "symbol": "processPayment",
#   "total_usages": 12,
#   "call_count": 12,
#   "filtered_language": "java",
#   "usages": [
#     {
#       "file": "src/controllers/CheckoutController.java",
#       "line": 45,
#       "context": "    result = paymentService.processPayment(order);"
#     },
#     {
#       "file": "src/services/SubscriptionService.java",
#       "line": 78,
#       "context": "    this.processPayment(subscription.getAmount());"
#     },
#     ...
#   ]
# }
```

### 示例 2：跨语言符号追踪

```python
# 问题：不限定语言，找到所有使用 UserService 的地方
result = await mcp.call_tool("trace_impact", {
    "symbol": "UserService",
    "word_match": True,
    "case_sensitive": True  # 区分大小写（类名通常需要）
})

# 注意：不提供 file_path 时，搜索所有语言
```

### 示例 3：API 弃用分析

```python
# 问题：我要弃用 legacyLogin 方法，有多少地方在用？
result = await mcp.call_tool("trace_impact", {
    "symbol": "legacyLogin",
    "file_path": "src/auth/AuthService.ts",  # TypeScript 文件
    "word_match": True
})

# 响应会告诉你需要迁移多少个调用点
# 可以根据 usages 列表逐个更新
```

## 参数

```json
{
  "symbol": "必需 - 要追踪的符号名（方法、类、函数或变量）",
  "file_path": "可选 - 符号定义的源文件路径（用于语言过滤）",
  "project_root": "可选 - 搜索根目录（默认使用工具配置的根目录）",
  "case_sensitive": "可选 - 是否区分大小写（默认: false，智能大小写）",
  "word_match": "可选 - 是否仅匹配整词（默认: true）",
  "max_results": "可选 - 最大返回结果数（默认: 1000）",
  "exclude_patterns": "可选 - 排除的 glob 模式数组（默认: node_modules, .git, vendor 等）"
}
```

## 与其他工具的组合

### 与 get_code_outline 配合

```python
# 步骤 1: 追踪符号的所有使用位置
usages = await mcp.call_tool("trace_impact", {
    "symbol": "calculateTotal",
    "file_path": "src/billing/Calculator.java"
})

# 步骤 2: 对每个使用位置的文件获取大纲，理解调用上下文
for usage in usages["usages"]:
    outline = await mcp.call_tool("get_code_outline", {
        "file_path": usage["file"]
    })
    # 现在你知道 calculateTotal 在每个文件中的哪个类/方法中被调用
```

### 与 extract_code_section 配合

```python
# 步骤 1: 找到所有使用位置
usages = await mcp.call_tool("trace_impact", {
    "symbol": "sendEmail",
    "file_path": "src/notifications/EmailService.java"
})

# 步骤 2: 提取每个调用点周围的代码，查看完整上下文
for usage in usages["usages"]:
    context = await mcp.call_tool("extract_code_section", {
        "file_path": usage["file"],
        "start_line": usage["line"] - 5,  # 前后各 5 行
        "end_line": usage["line"] + 5
    })
```

### 与 search_content 的区别

```python
# trace_impact: 专为影响分析设计，自动过滤到相同语言
# search_content: 通用内容搜索，灵活性更高

# 使用 trace_impact 当你要：
# - 评估重构的影响范围
# - 找到某个 API 的所有调用点
# - 分析弃用方法的使用情况

# 使用 search_content 当你要：
# - 搜索跨语言的模式
# - 查找注释、文档中的提及
# - 使用复杂正则表达式
```

## 最佳实践

1. ✅ **提供源文件路径以自动过滤语言**
   ```python
   # 好：自动仅搜索 Java 文件
   result = await mcp.call_tool("trace_impact", {
       "symbol": "UserService",
       "file_path": "src/services/UserService.java"  # 自动过滤到 .java
   })

   # 不好：搜索所有文件，可能有误报
   result = await mcp.call_tool("trace_impact", {
       "symbol": "UserService"  # 会在 .txt, .md 等文件中也找到
   })
   ```

2. ✅ **类名和常量使用 case_sensitive**
   ```python
   # 查找类名（大小写敏感）
   result = await mcp.call_tool("trace_impact", {
       "symbol": "UserService",
       "case_sensitive": True  # UserService != userservice
   })

   # 查找方法名（智能大小写）
   result = await mcp.call_tool("trace_impact", {
       "symbol": "processPayment"  # 默认 false 即可
   })
   ```

3. ✅ **使用 word_match 避免子串误报**
   ```python
   # 好：仅匹配 "test" 整词
   result = await mcp.call_tool("trace_impact", {
       "symbol": "test",
       "word_match": True  # 不会匹配 "testing", "testable"
   })

   # 不好：会匹配所有包含 "test" 的地方
   result = await mcp.call_tool("trace_impact", {
       "symbol": "test",
       "word_match": False  # 误报率高
   })
   ```

4. ❌ **不要搜索过于通用的符号**
   ```python
   # 不好：符号太通用，结果过多
   result = await mcp.call_tool("trace_impact", {
       "symbol": "get"  # 太宽泛！
   })

   # 好：具体的符号名
   result = await mcp.call_tool("trace_impact", {
       "symbol": "getUserById",
       "file_path": "src/services/UserService.java"
   })
   ```

## 示例用例

### 用例 1：安全重构前的评估

```python
# 问题：我要将 legacyEncrypt 迁移到 secureEncrypt，有多少地方需要改？
impact = await mcp.call_tool("trace_impact", {
    "symbol": "legacyEncrypt",
    "file_path": "src/security/Encryption.java",
    "word_match": True
})

print(f"需要迁移 {impact['call_count']} 处调用")

# 现在你有一个完整的迁移清单
for usage in impact["usages"]:
    print(f"- {usage['file']}:{usage['line']}")
```

### 用例 2：API 弃用计划

```python
# 问题：我要弃用 v1 API，评估影响范围
v1_apis = ["getUserV1", "createOrderV1", "updateProfileV1"]

total_impact = 0
for api in v1_apis:
    result = await mcp.call_tool("trace_impact", {
        "symbol": api,
        "file_path": "src/api/v1/Controller.java",
        "word_match": True
    })
    total_impact += result["call_count"]
    print(f"{api}: {result['call_count']} 处调用")

print(f"总计需要迁移 {total_impact} 处调用")
```

### 用例 3：依赖分析

```python
# 问题：如果我删除 PaymentGateway 类，哪些服务会受影响？
impact = await mcp.call_tool("trace_impact", {
    "symbol": "PaymentGateway",
    "file_path": "src/gateways/PaymentGateway.java",
    "case_sensitive": True  # 类名，区分大小写
})

# 根据 usages 中的文件路径，识别受影响的模块
affected_modules = set()
for usage in impact["usages"]:
    module = usage["file"].split("/")[1]  # 例如 src/services/...
    affected_modules.add(module)

print(f"受影响的模块: {', '.join(affected_modules)}")
```

### 用例 4：性能优化优先级

```python
# 问题：我优化了 calculateShipping，值得推广到所有调用点吗？
impact = await mcp.call_tool("trace_impact", {
    "symbol": "calculateShipping",
    "file_path": "src/logistics/ShippingCalculator.java"
})

if impact["call_count"] > 10:
    print("高频调用，优化价值高！")
else:
    print("低频调用，优化收益有限。")
```

## 性能特征

- **引擎**：基于 ripgrep（极速）
- **大型仓库**：数百万行代码中搜索符号，通常 < 3 秒
- **语言过滤**：自动基于源文件扩展名过滤，减少噪音
- **内存**：高效（流式处理，不加载整个仓库）

## 与 GitNexus 的对比

| 特性 | GitNexus (图数据库) | trace_impact (ripgrep) |
|------|-------------------|----------------------|
| 调用图深度 | 支持多层调用链 | 仅 1 层（直接调用） |
| 速度 | 需要索引构建 | 零索引，即时搜索 |
| 准确性 | 高（语义理解） | 中（文本匹配） |
| 部署 | 需要 Neo4j | 零依赖 |
| 适用场景 | 深度影响分析 | 快速爆炸半径评估 |

**设计哲学**：tree-sitter-analyzer 的 `trace_impact` 提供 80% 价值（直接调用点），成本仅 20%（无需图数据库）。对于大多数重构场景，这已足够。

## 相关工具

| 工具 | 何时使用 |
|------|---------|
| `trace_impact` | 评估重构/删除的影响范围（单个符号） |
| `search_content` | 通用内容搜索（跨语言、正则、注释） |
| `find_and_grep` | 先找文件再搜索（两步流程） |

## 版本历史

- **v1.10.5** (2026-03-28): 初始版本，添加 intent alias `assess_blast_radius`
- **设计灵感**: GitNexus impact tool

---

**🎯 记住：在你动手改代码之前，先问"这会影响哪些地方？"这个工具给你答案。**
