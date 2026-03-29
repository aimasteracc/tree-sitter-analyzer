# analyze_code_universal — AI 使用指南

## 工具别名（Intent Aliases）

- **analyze_file** — 分析文件
- **universal_analyze** — 通用分析
- **multi_language_analyze** — 多语言分析

## 何时使用

当需要对单个代码文件进行全面分析时使用。支持 17 种编程语言的自动检测和分析。

**analyze_code_universal vs 其他工具：**
- **analyze_code_universal** — 单文件全面分析（basic/detailed/structure/metrics）
- **analyze_code_structure** — 结构化表格分析（Table 格式）
- **check_code_scale** — 规模和复杂度评估（附带 LLM 指导）
- **get_code_outline** — 大纲导航（TOON 格式，token 优化）

## SMART Workflow 位置

Set → Map → **Analyze**（本工具）→ Retrieve → Trace

在 SMART workflow 的 **Analyze** 步骤使用 `analyze_code_universal`：
1. **Set**：明确分析目标
2. **Map**：了解文件规模
3. **Analyze**（本工具）：深入分析文件内容
4. **Retrieve**：提取特定代码段
5. **Trace**：追踪依赖和影响

## 典型调用模式

### 模式 1：基础分析（快速理解文件）

```python
# 基础分析：快速了解文件的主要组成部分
basic = await mcp.call_tool("analyze_code_universal", {
    "file_path": "src/services/UserService.java",
    "analysis_type": "basic"  # 基础分析
})

# 响应示例（TOON 格式）：
# analysis
#   file: src/services/UserService.java
#   language: java
#   type: basic
#   summary
#     classes: 1
#     methods: 12
#     imports: 8
#     total_lines: 234
#   elements
#     - type: class
#       name: UserService
#       line: 10
#     - type: method
#       name: getUserById
#       line: 23
#     - type: method
#       name: createUser
#       line: 37
#     # ... 更多元素（仅关键信息）
```

### 模式 2：详细分析（包含代码内容）

```python
# 详细分析：包含每个元素的完整代码内容
detailed = await mcp.call_tool("analyze_code_universal", {
    "file_path": "src/utils/StringHelper.java",
    "analysis_type": "detailed"  # 详细分析
})

# 响应示例（TOON 格式）：
# analysis
#   file: src/utils/StringHelper.java
#   language: java
#   type: detailed
#   elements
#     - type: class
#       name: StringHelper
#       line: 10-234
#       code: |
#         public class StringHelper {
#           // ... 完整代码
#         }
#     - type: method
#       name: isEmpty
#       line: 15-23
#       code: |
#         public static boolean isEmpty(String str) {
#           return str == null || str.trim().isEmpty();
#         }
#     # ... 每个元素都包含完整代码
```

### 模式 3：结构分析（层级关系）

```python
# 结构分析：重点关注层级关系和组织结构
structure = await mcp.call_tool("analyze_code_universal", {
    "file_path": "src/controllers/UserController.java",
    "analysis_type": "structure"  # 结构分析
})

# 响应示例（TOON 格式）：
# analysis
#   file: src/controllers/UserController.java
#   language: java
#   type: structure
#   structure
#     package: com.example.controllers
#     imports: 15
#     classes
#       - name: UserController
#         line: 20
#         type: class
#         methods
#           - name: getUser
#             line: 34
#             type: public method
#           - name: createUser
#             line: 56
#             type: public method
#           - name: updateUser
#             line: 78
#             type: public method
#           - name: deleteUser
#             line: 98
#             type: public method
#           - name: validateUser (private helper)
#             line: 112
#             type: private method
```

### 模式 4：指标分析（metrics only）

```python
# 指标分析：仅计算指标，不返回代码内容
metrics = await mcp.call_tool("analyze_code_universal", {
    "file_path": "src/services/PaymentService.java",
    "analysis_type": "metrics"  # 仅指标
})

# 响应示例（TOON 格式）：
# analysis
#   file: src/services/PaymentService.java
#   language: java
#   type: metrics
#   metrics
#     total_lines: 567
#     code_lines: 423
#     blank_lines: 89
#     comment_lines: 55
#     complexity_score: 67
#     class_count: 2
#     method_count: 23
#     function_count: 0
#     import_count: 12
#     file_size_kb: 18.5
```

### 模式 5：与其他工具的集成

```python
# 场景：新项目入门 - 快速理解核心文件

# 步骤 1: 先评估规模
scale = await mcp.call_tool("check_code_scale", {
    "file_path": "src/core/Application.java"
})

# 步骤 2: 根据规模选择分析深度
if scale["metrics"]["total_lines"] < 300:
    # 小文件：详细分析
    analysis = await mcp.call_tool("analyze_code_universal", {
        "file_path": "src/core/Application.java",
        "analysis_type": "detailed"  # 包含代码
    })
elif scale["metrics"]["total_lines"] < 800:
    # 中等文件：结构分析
    analysis = await mcp.call_tool("analyze_code_universal", {
        "file_path": "src/core/Application.java",
        "analysis_type": "structure"  # 重点关注结构
    })
else:
    # 大文件：先获取 outline
    outline = await mcp.call_tool("get_code_outline", {
        "file_path": "src/core/Application.java",
        "output_format": "toon"
    })
    # 然后按需提取特定方法

# 步骤 3: 查找关键方法
methods = await mcp.call_tool("query_code", {
    "file_path": "src/core/Application.java",
    "query_key": "methods",
    "filter": "public=true"  # 仅 public 方法（API surface）
})

# 步骤 4: 提取关键方法代码
main_method = methods["query_result"]["matches"][0]
code = await mcp.call_tool("extract_code_section", {
    "file_path": "src/core/Application.java",
    "start_line": main_method["start_line"],
    "end_line": main_method["end_line"]
})
```

## 分析类型（Analysis Types）

| 类型 | 描述 | Token 消耗 | 适用场景 |
|------|------|-----------|---------|
| **basic** | 基础分析：元素列表 + 基本信息 | 低 | 快速理解文件组成 |
| **detailed** | 详细分析：包含完整代码内容 | 高 | 需要阅读代码实现 |
| **structure** | 结构分析：层级关系 + 组织结构 | 中 | 理解代码组织架构 |
| **metrics** | 指标分析：仅计算指标，无代码 | 极低 | 评估文件规模和复杂度 |

## 输出格式

### 默认：TOON 格式（50-70% Token 缩减）

```
analysis
  file: src/UserService.java
  language: java
  type: basic
  summary
    classes: 1
    methods: 12
    imports: 8
  elements
    - type: class
      name: UserService
      line: 10
    - type: method
      name: getUserById
      line: 23
```

### JSON 格式（详细但 token 消耗更高）

```python
result = await mcp.call_tool("analyze_code_universal", {
    "file_path": "Service.java",
    "analysis_type": "basic",
    "output_format": "json"  # 明确指定 JSON
})

# 响应：
# {
#   "success": true,
#   "analysis": {
#     "file_path": "src/UserService.java",
#     "language": "java",
#     "type": "basic",
#     "summary": {
#       "classes": 1,
#       "methods": 12,
#       "imports": 8
#     },
#     "elements": [
#       {
#         "type": "class",
#         "name": "UserService",
#         "line": 10
#       },
#       // ...
#     ]
#   }
# }
```

## Token 优化策略

### 适合小文件（< 300 行）

```python
# 小文件可以直接详细分析
detailed = await mcp.call_tool("analyze_code_universal", {
    "file_path": "SmallUtil.java",
    "analysis_type": "detailed"  # 包含代码
})
# Token 消耗：~1000-3000 tokens
```

### 适合中等文件（300-800 行）

```python
# 中等文件用结构分析
structure = await mcp.call_tool("analyze_code_universal", {
    "file_path": "MediumService.java",
    "analysis_type": "structure"  # 仅结构，无代码
})
# Token 消耗：~500-1500 tokens
```

### 适合大文件（> 800 行）

```python
# 大文件：先用 metrics 评估，再用 outline 导航
metrics = await mcp.call_tool("analyze_code_universal", {
    "file_path": "LargeService.java",
    "analysis_type": "metrics"  # 仅指标
})
# Token 消耗：~100-300 tokens

# 然后用 get_code_outline
outline = await mcp.call_tool("get_code_outline", {
    "file_path": "LargeService.java",
    "output_format": "toon"
})
# 最后按需提取特定方法
```

### TOON vs JSON 格式

```python
# TOON 格式（推荐）：节省 50-70% token
result_toon = await mcp.call_tool("analyze_code_universal", {
    "file_path": "Service.java",
    "analysis_type": "basic",
    "output_format": "toon"  # 默认，可省略
})

# JSON 格式：详细但 token 消耗高
result_json = await mcp.call_tool("analyze_code_universal", {
    "file_path": "Service.java",
    "analysis_type": "basic",
    "output_format": "json"
})
```

## 参数说明

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | string | 是 | - | 要分析的文件路径 |
| `language` | string | 否 | 自动检测 | 编程语言 |
| `analysis_type` | string | 否 | "basic" | 分析类型："basic", "detailed", "structure", "metrics" |
| `output_format` | string | 否 | "toon" | 输出格式："toon" 或 "json" |

## 最佳实践

### ✅ DO（推荐做法）

1. **根据文件规模选择分析类型**
   ```python
   # 先评估规模
   scale = await mcp.call_tool("check_code_scale", {"file_path": "File.java"})

   # 根据规模选择分析类型
   if scale["metrics"]["total_lines"] < 300:
       analysis_type = "detailed"  # 小文件：详细分析
   elif scale["metrics"]["total_lines"] < 800:
       analysis_type = "structure"  # 中等文件：结构分析
   else:
       analysis_type = "metrics"  # 大文件：仅指标
   ```

2. **优先使用 TOON 格式**
   ```python
   # GOOD：TOON 格式（默认）
   result = await mcp.call_tool("analyze_code_universal", {
       "file_path": "Service.java",
       "analysis_type": "basic"
       # output_format: "toon" — 默认，无需显式指定
   })
   ```

3. **分阶段分析**
   ```python
   # GOOD：先浅后深
   # 第 1 阶段：metrics（了解规模）
   metrics = await mcp.call_tool("analyze_code_universal", {
       "file_path": "Service.java",
       "analysis_type": "metrics"
   })

   # 第 2 阶段：structure（了解组织）
   if metrics_indicate_interesting:
       structure = await mcp.call_tool("analyze_code_universal", {
           "file_path": "Service.java",
           "analysis_type": "structure"
       })

   # 第 3 阶段：detailed（深入理解）
   if structure_shows_target_method:
       detailed = await mcp.call_tool("analyze_code_universal", {
           "file_path": "Service.java",
           "analysis_type": "detailed"
       })
   ```

### ❌ DON'T（避免做法）

1. **不要对大文件使用 detailed 分析**
   ```python
   # BAD：大文件（1200 行）用 detailed
   detailed = await mcp.call_tool("analyze_code_universal", {
       "file_path": "HugeService.java",
       "analysis_type": "detailed"  # 可能 token 溢出
   })

   # GOOD：大文件用 outline + extract
   outline = await mcp.call_tool("get_code_outline", {
       "file_path": "HugeService.java"
   })
   # 然后按需提取
   ```

2. **不要忽略 analysis_type 参数**
   ```python
   # BAD：不指定分析类型（默认 basic，可能不满足需求）
   result = await mcp.call_tool("analyze_code_universal", {
       "file_path": "Service.java"
   })

   # GOOD：明确指定分析类型
   result = await mcp.call_tool("analyze_code_universal", {
       "file_path": "Service.java",
       "analysis_type": "structure"  # 明确需求
   })
   ```

3. **不要重复分析**
   ```python
   # BAD：多次分析同一个文件
   basic = await mcp.call_tool("analyze_code_universal", {
       "file_path": "Service.java",
       "analysis_type": "basic"
   })
   structure = await mcp.call_tool("analyze_code_universal", {
       "file_path": "Service.java",
       "analysis_type": "structure"
   })
   detailed = await mcp.call_tool("analyze_code_universal", {
       "file_path": "Service.java",
       "analysis_type": "detailed"
   })

   # GOOD：根据需求选择一种分析类型
   analysis = await mcp.call_tool("analyze_code_universal", {
       "file_path": "Service.java",
       "analysis_type": "structure"  # 选择最合适的
   })
   ```

## 支持的语言

Java, JavaScript, TypeScript, Python, Go, Rust, C, C++, C#, PHP, Ruby, Kotlin, Markdown, HTML, CSS, YAML, SQL (共 17 种语言)

所有语言支持自动检测，无需手动指定 `language` 参数。

## 性能指标

- **基础分析（basic）**：< 2 秒
- **详细分析（detailed）**：< 5 秒（取决于文件大小）
- **结构分析（structure）**：< 3 秒
- **指标分析（metrics）**：< 1 秒
- **Token 缩减**：
  - TOON vs JSON：50-70% 缩减
  - metrics vs detailed：80%+ 缩减

## 与其他工具的配合

| 场景 | 工具链 |
|------|--------|
| **新项目入门** | check_code_scale → analyze_code_universal (structure) → extract_code_section |
| **代码审查** | analyze_code_universal (basic) → query_code (find patterns) → trace_impact |
| **重构准备** | analyze_code_universal (structure) → trace_impact → extract_code_section |
| **文档生成** | analyze_code_universal (detailed) → 提取注释和签名 |
| **依赖分析** | analyze_code_universal (structure) → search_content (find usages) |

## 常见问题

**Q: analyze_code_universal vs analyze_code_structure 的区别？**
A:
- **analyze_code_universal** — 灵活的多模式分析（basic/detailed/structure/metrics），TOON 或 JSON 格式
- **analyze_code_structure** — 固定的表格格式分析，输出 Markdown 表格

选择建议：
- AI 代理处理 → 用 `analyze_code_universal`（结构化数据）
- 人类阅读 → 用 `analyze_code_structure`（可读性强的表格）

**Q: 何时使用 metrics vs check_code_scale?**
A:
- **analyze_code_universal (metrics)** — 简单的指标计算
- **check_code_scale** — 指标 + LLM 分析指导 + 分段建议

选择建议：
- 仅需要指标数据 → 用 `analyze_code_universal (metrics)`
- 需要分析策略指导 → 用 `check_code_scale`

**Q: 如何处理不支持的语言?**
A:
工具会返回错误提示 `"Unsupported language"`。目前支持 17 种主流语言。如需支持更多语言，请提交 issue。

**Q: detailed 分析会返回完整代码吗?**
A:
是的，`detailed` 模式会返回每个元素（类、方法、函数等）的完整代码内容。对于大文件（> 500 行），建议使用 `structure` 或 `outline + extract` 策略。
