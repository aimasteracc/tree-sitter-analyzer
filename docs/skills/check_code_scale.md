# check_code_scale — AI 使用指南

## 工具别名（Intent Aliases）

- **assess_scale** — 评估代码规模
- **measure_complexity** — 测量复杂度
- **analyze_metrics** — 分析指标

## 何时使用

在决定分析策略之前调用此工具。**先测量，后决策** — `check_code_scale` 帮助 AI 代理判断：
- 文件是否过大，需要分段处理
- 复杂度是否过高，需要outline-first导航
- 是否适合直接全文分析

## SMART Workflow 位置

**Set** → **Map** (本工具) → Analyze → Retrieve → Trace

在 SMART workflow 的 **Map** 步骤使用 `check_code_scale`：
1. **Set**：明确分析目标
2. **Map**（本工具）：测量文件规模和复杂度
3. **Analyze**：根据 scale 指导选择分析策略
4. **Retrieve**：提取具体代码内容
5. **Trace**：追踪影响范围

## 典型调用模式

### 模式 1：单文件规模评估 + 策略指导

```python
# 步骤 1: 评估文件规模
scale = await mcp.call_tool("check_code_scale", {
    "file_path": "src/services/BigService.java"
})

# 响应示例（TOON 格式）：
# scale_analysis
#   file: src/services/BigService.java
#   language: java
#   metrics
#     total_lines: 1245
#     code_lines: 982
#     complexity_score: 127
#     class_count: 3
#     method_count: 48
#   guidance  # LLM 分析指导
#     recommendation: "large_file"
#     strategy: "Use get_code_outline first, then extract_code_section for specific methods"
#     token_estimate: "~18000 tokens if analyzed in full"
#     分段建议: "Split into 3 segments: lines 1-400, 401-800, 801-1245"

# 步骤 2: 根据指导选择策略
if "large_file" in scale["guidance"]["recommendation"]:
    # 大文件：先 outline，再提取
    outline = await mcp.call_tool("get_code_outline", {
        "file_path": "src/services/BigService.java",
        "output_format": "toon"
    })
    # 然后提取感兴趣的方法
    code = await mcp.call_tool("extract_code_section", {
        "file_path": "src/services/BigService.java",
        "start_line": 234,
        "end_line": 298
    })
else:
    # 小文件：直接全文分析
    analysis = await mcp.call_tool("analyze_code_structure", {
        "file_path": "src/services/BigService.java"
    })
```

### 模式 2：批量文件指标（快速扫描多个文件）

```python
# 批量模式：仅计算指标，不做结构分析
batch_metrics = await mcp.call_tool("check_code_scale", {
    "file_paths": [
        "src/services/UserService.java",
        "src/services/OrderService.java",
        "src/services/PaymentService.java",
        "src/services/NotificationService.java"
    ],
    "metrics_only": true  # 只要 metrics，不要结构分析
})

# 响应示例（TOON 格式）：
# batch_metrics
#   total_files: 4
#   files
#     - file: src/services/UserService.java
#       total_lines: 456
#       code_lines: 342
#       complexity_score: 32
#     - file: src/services/OrderService.java
#       total_lines: 789
#       code_lines: 601
#       complexity_score: 67
#     - file: src/services/PaymentService.java
#       total_lines: 1123
#       code_lines: 891
#       complexity_score: 104
#     - file: src/services/NotificationService.java
#       total_lines: 234
#       code_lines: 178
#       complexity_score: 18

# 步骤 2: 根据批量结果优先处理高复杂度文件
high_complexity_files = [
    f for f in batch_metrics["files"]
    if f["complexity_score"] > 80
]
# PaymentService.java 的复杂度最高，优先分析
```

### 模式 3：详细分析模式（包含结构信息）

```python
# 详细模式：包含类、方法、函数等结构信息
detailed = await mcp.call_tool("check_code_scale", {
    "file_path": "src/utils/StringUtils.java",
    "include_details": true,   # 包含详细元素信息
    "include_complexity": true, # 包含复杂度指标
    "include_guidance": true    # 包含 LLM 指导（默认 true）
})

# 响应示例（TOON 格式）：
# scale_analysis
#   file: src/utils/StringUtils.java
#   language: java
#   metrics
#     total_lines: 234
#     code_lines: 178
#     complexity_score: 24
#     class_count: 1
#     method_count: 12
#   structure  # 包含详细结构信息
#     classes
#       - name: StringUtils
#         line: 10
#         method_count: 12
#     methods
#       - name: isEmpty
#         line: 15
#         complexity: 1
#       - name: join
#         line: 23
#         complexity: 3
#       - name: split
#         line: 45
#         complexity: 5
#   guidance
#     recommendation: "medium_file"
#     strategy: "Can analyze in full or use structure-first approach"
#     token_estimate: "~3500 tokens if analyzed in full"
```

### 模式 4：与其他工具的集成

```python
# 使用场景：重构前评估影响范围

# 步骤 1: 评估目标文件规模
scale = await mcp.call_tool("check_code_scale", {
    "file_path": "src/api/UserController.java"
})

# 步骤 2: 如果文件很大，先获取 outline
if scale["metrics"]["total_lines"] > 500:
    outline = await mcp.call_tool("get_code_outline", {
        "file_path": "src/api/UserController.java",
        "output_format": "toon"
    })
    # 从 outline 中找到要重构的方法（如 getUserById 在 89-123 行）

# 步骤 3: 提取要重构的方法
method_code = await mcp.call_tool("extract_code_section", {
    "file_path": "src/api/UserController.java",
    "start_line": 89,
    "end_line": 123
})

# 步骤 4: 追踪影响范围
impact = await mcp.call_tool("trace_impact", {
    "symbol": "getUserById",
    "file_path": "src/api/UserController.java",
    "project_root": "/path/to/project"
})
# 分析所有调用 getUserById 的地方，评估重构影响
```

## 输出格式（Output Format）

### 默认：TOON 格式（50-70% Token 缩减）

```
scale_analysis
  file: src/BigService.java
  language: java
  metrics
    total_lines: 1245
    code_lines: 982
    blank_lines: 145
    comment_lines: 118
    file_size_kb: 45.2
    complexity_score: 127
    class_count: 3
    method_count: 48
    function_count: 0
    import_count: 23
  guidance
    recommendation: "large_file"
    strategy: "Use get_code_outline + extract_code_section"
    token_estimate: "~18000 tokens"
    分段建议: "Split into 3 segments"
```

### JSON 格式（详细但 token 消耗更高）

```json
{
  "success": true,
  "analysis": {
    "file_path": "src/BigService.java",
    "language": "java",
    "metrics": {
      "total_lines": 1245,
      "code_lines": 982,
      "blank_lines": 145,
      "comment_lines": 118,
      "file_size_kb": 45.2,
      "complexity_score": 127,
      "class_count": 3,
      "method_count": 48,
      "function_count": 0,
      "import_count": 23
    },
    "guidance": {
      "recommendation": "large_file",
      "strategy": "Use get_code_outline + extract_code_section",
      "token_estimate": "~18000 tokens",
      "分段建议": "Split into 3 segments"
    }
  }
}
```

## Token 优化策略

### 批量模式（最优：仅 metrics，节省 80%+ token）

```python
# 批量扫描项目中的所有服务类
batch = await mcp.call_tool("check_code_scale", {
    "file_paths": [
        "src/services/ServiceA.java",
        "src/services/ServiceB.java",
        "src/services/ServiceC.java",
        # ... 可以有数百个文件
    ],
    "metrics_only": true  # 仅计算指标，不返回结构信息
})
# 返回：每个文件的简要 metrics（行数、复杂度等）
# Token 消耗：~10 tokens/文件（而不是 200+ tokens/文件）
```

### TOON 格式（推荐：节省 50-70% token）

```python
scale = await mcp.call_tool("check_code_scale", {
    "file_path": "BigService.java",
    "output_format": "toon"  # 默认，无需显式指定
})
# TOON 格式压缩冗余字段名和嵌套结构
```

### 最小化 details（适合快速评估）

```python
scale = await mcp.call_tool("check_code_scale", {
    "file_path": "BigService.java",
    "include_details": false,   # 不包含详细元素列表
    "include_complexity": true,
    "include_guidance": true    # 保留 guidance（关键）
})
# 仅返回 metrics + guidance，省略 structure 部分
```

## 参数说明

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | string | 是（单文件模式） | - | 要分析的文件路径 |
| `file_paths` | array | 是（批量模式） | - | 批量分析的文件路径列表 |
| `metrics_only` | boolean | 否 | false | 批量模式：仅计算指标，不做结构分析 |
| `language` | string | 否 | 自动检测 | 编程语言（java, python, javascript 等） |
| `include_complexity` | boolean | 否 | true | 是否包含复杂度指标 |
| `include_details` | boolean | 否 | false | 是否包含详细元素信息（类、方法列表） |
| `include_guidance` | boolean | 否 | true | 是否包含 LLM 分析指导 |
| `output_format` | string | 否 | "toon" | 输出格式："toon" 或 "json" |

## 最佳实践

### ✅ DO（推荐做法）

1. **大规模项目扫描时使用批量模式**
   ```python
   # 快速扫描整个 services 目录
   all_services = glob.glob("src/services/**/*.java")
   batch = await mcp.call_tool("check_code_scale", {
       "file_paths": all_services,
       "metrics_only": true
   })
   # 根据复杂度排序，优先分析高复杂度文件
   ```

2. **在详细分析前先评估规模**
   ```python
   # 先评估
   scale = await mcp.call_tool("check_code_scale", {"file_path": "BigFile.java"})

   # 根据 guidance 选择策略
   if "large_file" in scale["guidance"]["recommendation"]:
       # 使用 outline-first 策略
       outline = await mcp.call_tool("get_code_outline", {...})
   else:
       # 直接全文分析
       analysis = await mcp.call_tool("analyze_code_structure", {...})
   ```

3. **利用 guidance 字段**
   ```python
   scale = await mcp.call_tool("check_code_scale", {
       "file_path": "Service.java",
       "include_guidance": true  # 默认 true
   })
   # guidance 包含：
   # - recommendation: "small_file" / "medium_file" / "large_file"
   # - strategy: 推荐的分析策略
   # - token_estimate: 全文分析的 token 估算
   # - 分段建议: 大文件的分段建议
   ```

### ❌ DON'T（避免做法）

1. **不要对每个文件都用 include_details=true**
   ```python
   # BAD：每个文件都要详细信息
   for file in all_files:
       scale = await mcp.call_tool("check_code_scale", {
           "file_path": file,
           "include_details": true  # 浪费 token
       })

   # GOOD：先批量扫描，再针对性详细分析
   batch = await mcp.call_tool("check_code_scale", {
       "file_paths": all_files,
       "metrics_only": true
   })
   # 然后只对高复杂度文件做详细分析
   ```

2. **不要忽略 guidance 字段**
   ```python
   # BAD：忽略 guidance，直接全文分析大文件
   scale = await mcp.call_tool("check_code_scale", {"file_path": "HugeFile.java"})
   # ... 然后直接 analyze_code_structure（可能 token 溢出）

   # GOOD：根据 guidance 调整策略
   if scale["guidance"]["recommendation"] == "large_file":
       # 使用 outline + extract 策略
   ```

3. **不要在批量模式下使用 include_details**
   ```python
   # BAD：批量模式不支持 include_details
   batch = await mcp.call_tool("check_code_scale", {
       "file_paths": [...],
       "include_details": true  # 无效，批量模式只支持 metrics_only
   })

   # GOOD：批量模式只用 metrics_only
   batch = await mcp.call_tool("check_code_scale", {
       "file_paths": [...],
       "metrics_only": true
   })
   ```

## 性能指标

- **单文件分析**：< 1 秒
- **批量分析（metrics_only）**：< 0.1 秒/文件
- **支持的语言**：Java, JavaScript, TypeScript, Python, Go, Rust, C, C++, C#, PHP, Ruby, Kotlin, Markdown, HTML, CSS, YAML, SQL
- **Token 缩减**：
  - TOON vs JSON：50-70% 缩减
  - metrics_only vs detailed：80%+ 缩减
  - 批量模式 vs 逐个调用：90%+ 缩减

## 与其他工具的配合

| 场景 | 工具链 |
|------|--------|
| **大文件分析** | check_code_scale → get_code_outline → extract_code_section |
| **批量扫描 + 重点分析** | check_code_scale (批量) → analyze_code_structure (针对高复杂度) |
| **重构前评估** | check_code_scale → trace_impact → extract_code_section |
| **新项目理解** | list_files → check_code_scale (批量) → get_code_outline (重点文件) |
| **代码审查** | check_code_scale → analyze_code_structure → query_code (查找特定模式) |

## 常见问题

**Q: 何时使用 metrics_only vs include_details?**
A:
- **metrics_only=true**：批量扫描、快速评估、优先级排序
- **include_details=true**：单文件深入分析、需要了解类/方法结构

**Q: guidance 中的 recommendation 有哪些值?**
A:
- **small_file**：< 300 行，可以直接全文分析
- **medium_file**：300-800 行，建议先 outline 或直接分析
- **large_file**：> 800 行，必须先 outline 再分段提取

**Q: 批量模式最多支持多少文件?**
A: 理论上无限制，但建议单次 < 500 文件。超过时分批调用。

**Q: 如何根据 complexity_score 判断复杂度?**
A:
- **0-20**：简单文件（工具类、配置）
- **20-50**：中等复杂度（普通业务逻辑）
- **50-100**：较高复杂度（核心服务）
- **> 100**：高复杂度（需要重构或分段分析）
