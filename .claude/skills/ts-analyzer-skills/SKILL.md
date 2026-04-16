---
name: ts-analyzer-skills
description: |
  tree-sitter-analyzer 的自然语言 Skill 层。当用户用自然语言描述代码分析需求时，
  将其精准映射到底层 MCP 工具调用。支持中英文查询。
  触发词：「分析代码」「代码结构」「找到所有方法」「影响范围」「这个类有什么」
  「analyze code」「find methods」「trace impact」「code structure」
---

# Tree-sitter-analyzer — 自然语言 Skill 层

> **定位**：你是一个代码分析路由器。用户用自然语言描述需求，你精准选择 MCP 工具并构造参数。
> **原则**：先分流（triage），再精准调用。不要一次读整个文件，先了解结构。

## 查询路由表

当用户说... | 使用工具 | 关键参数
---|---|---
「这个文件的结构」「代码结构」「有什么类/方法」 | `analyze_code_structure` | `format_type: "compact"`
「这个文件的大纲」「层级结构」 | `get_code_outline` | （无额外参数）
「找到所有 X」「查出所有方法/类/函数」 | `query_code` | `query_key: "methods"/"classes"/"functions"`
「这个函数的实现」「第 X 行的代码」 | `extract_code_section` | `start_line`, `end_line`
「谁调用了 X」「影响范围」 | `trace_impact` | `symbol_name: "X"`
「搜索 YYY」「哪里用了 YYY」 | `search_content` | `pattern: "YYY"`
「找文件」「哪些文件」 | `list_files` | `pattern: "*.java"`
「文件多大」「复杂度」 | `check_code_scale` | （无额外参数）
「先给我看项目概览」 | `get_project_summary` | （无额外参数）
「修改安全吗」「能不能改」 | `modification_guard` | `file_path`, `symbol_name`
「找到 A 然后搜索 B」 | `find_and_grep` | `file_pattern`, `content_pattern`
「同时搜多个模式」 | `batch_search` | `patterns: ["A", "B"]`

## 智能工作流（SMART）

大多数分析任务遵循 SMART 五步法：

```
Set（设置）
  → set_project_path 或直接用绝对路径
  │
Map（映射）
  → check_code_scale：文件有多大？需不需要精简输出？
  → get_code_outline：快速了解层级
  │
Analyze（分析）
  → query_code：精准提取元素（按类型/过滤条件）
  → analyze_code_structure：详细表格视图
  │
Retrieve（提取）
  → extract_code_section：精准提取代码段
  │
Trace（追踪）
  → trace_impact：追踪影响范围
  → modification_guard：评估修改安全性
```

## 中英文查询映射

### 元素查找

| 自然语言 | query_key |
|---------|-----------|
| 「所有方法」「all methods」「方法的列表」 | `methods` |
| 「有哪些类」「classes」「类定义」 | `classes` |
| 「函数列表」「functions」「所有函数」 | `functions` |
| 「import 语句」「imports」「导入」 | `imports` |
| 「变量声明」「variables」「字段」 | `variables` |
| 「注释」「comments」 | `comments` |

### 结构分析

| 自然语言 | 工具 + 参数 |
|---------|-----------|
| 「这个文件的结构」 | `analyze_code_structure` + `format_type: "compact"` |
| 「详细结构」 | `analyze_code_structure` + `format_type: "full"` |
| 「快速大纲」 | `get_code_outline` |
| 「文件大小」「代码规模」 | `check_code_scale` |

### 影响追踪

| 自然语言 | 工具 + 参数 |
|---------|-----------|
| 「谁调用了 XXX」 | `trace_impact` + `symbol_name: "XXX"` |
| 「XXX 的引用」 | `trace_impact` + `symbol_name: "XXX"` |
| 「修改 XXX 安全吗」 | `modification_guard` + `symbol_name: "XXX"` |
| 「修改影响」 | `trace_impact` + `symbol_name` + `modification_guard` |

### 搜索

| 自然语言 | 工具 + 参数 |
|---------|-----------|
| 「搜索 XXX」 | `search_content` + `pattern: "XXX"` |
| 「找到 .java 文件中的 XXX」 | `find_and_grep` + `file_pattern: "*.java"` + `content_pattern: "XXX"` |
| 「同时搜 A 和 B」 | `batch_search` + `patterns: ["A", "B"]` |
| 「哪些文件匹配」 | `list_files` + `pattern: "*.xxx"` |

## Token 优化策略

| 场景 | 策略 | 节省 |
|------|------|------|
| 大文件（>500行） | 用 `format_type: "compact"` 或 TOON 输出 | 50-70% |
| 大量结果（>50条） | 用 `output_file` + `suppress_output` | 90%+ |
| 只需特定元素 | 用 `query_code` + `filter` 而非全量分析 | 80%+ |
| 项目级了解 | 用 `get_project_summary`（有缓存） | 95%+ |
| 不确定文件内容 | 先 `check_code_scale` 再决定策略 | N/A |

## 工具组合模式

### 模式 1：理解未知代码
```
check_code_scale → get_code_outline → query_code(methods) → extract_code_section
```

### 模式 2：修改前评估
```
trace_impact → modification_guard → analyze_code_structure
```

### 模式 3：精准查找
```
list_files → find_and_grep → extract_code_section
```

### 模式 4：批量分析
```
get_project_summary → list_files → batch_search → query_code
```

## 行为规则

1. **先分流再调用**：不要盲目调用工具，先判断用户需求属于哪个类别
2. **用 TOON 节省 token**：当用户不需要人类可读格式时，优先用 TOON 输出
3. **尊重 modification_guard**：修改代码前必须检查安全性
4. **用绝对路径**：所有 `file_path` 参数必须是绝对路径
5. **批量操作**：能用 `batch_search` 就不要多次 `search_content`
6. **缓存项目概览**：`get_project_summary` 有缓存，优先使用
7. **CJK 支持**：中英文查询等价处理，底层工具参数一律用英文

## 支持的语言

Java · Python · JavaScript · TypeScript · C · C++ · C# · Go · Rust · Kotlin · PHP · Ruby · SQL · HTML · CSS · YAML · Markdown
