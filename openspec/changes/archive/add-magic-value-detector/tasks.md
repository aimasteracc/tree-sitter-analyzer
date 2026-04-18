# Magic Value Detector

## Goal

检测代码中的硬编码魔法值（数字、字符串、URL、文件路径），帮助开发者识别应该抽取为常量或配置的值。

一句话定义: "找出代码中不该硬编码的值"

## MVP Scope

### Sprint 1: Core Detection Engine (Python)

**文件**:
- `tree_sitter_analyzer/analysis/magic_values.py` (~400 lines)

**功能**:
- `MagicValueReference` dataclass: value, file_path, line, col, value_type, context, category
- `MagicValueUsage` dataclass: value, references, file_count, total_refs, category
- `MagicValueResult` dataclass: aggregated results
- `MagicValueDetector` class:
  - `detect(file_path)` → detect in single file
  - `detect_directory(dir_path)` → detect in directory
  - `group_by_value()` → group identical values
  - `filter_by_category(categories)` → filter results
- 5 种值类型检测:
  - hardcoded numbers (非 0, 1, -1)
  - hardcoded strings (非空, 非 format)
  - URLs (http/https/ftp)
  - file paths (/xxx, ./xxx)
  - color codes (#RGB, #RRGGBB)
- 智能过滤:
  - 忽略常见安全值 (0, 1, "", True, False, None)
  - 忽略 enum 成员赋值
  - 忽略类型注解中的字符串
  - 忽略 docstring
- 分类: magic_number, magic_string, hardcoded_url, hardcoded_path, hardcoded_color

**测试**: 15+ tests

### Sprint 2: Multi-Language Support (JS/TS, Java, Go)

**功能**:
- JavaScript/TypeScript: numeric/string/template literals, regex literals
- Java: numeric/string literals, annotations
- Go: numeric/string/rune literals, struct tags
- TypeScript `language_typescript` / `language_tsx` function name override

**测试**: 12+ multilang tests

### Sprint 3: MCP Tool Integration

**文件**:
- `tree_sitter_analyzer/mcp/tools/magic_values_tool.py` (~200 lines)

**功能**:
- MCP tool: `magic_values` (analysis toolset)
- 参数: file_path, project_root, min_occurrences, categories, format
- 输出: TOON + JSON
- 注册到 analysis toolset

**测试**: 10 MCP tool tests

## Technical Approach

- 使用 `TreeSitterQueryCompat` 兼容层执行 tree-sitter 查询
- 匹配 `number` 和 `string` 节点类型
- 通过上下文过滤（跳过 enum、docstring、type annotation）
- URL/path 检测通过正则匹配字符串内容
- 与 env_tracker/import_sanitizer 架构模式一致
