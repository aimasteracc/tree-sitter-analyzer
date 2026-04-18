# Import Dependency Sanitizer

## Goal

检测未使用的 import、循环 import、以及 import 顺序合规性。跨语言支持（Python, JS/TS, Java, Go）。

一句话定义: "告诉你哪些 import 是多余的、哪些文件之间存在循环依赖"

## MVP Scope

### Sprint 1: Core Detection Engine (Python) ✅

**文件**:
- `tree_sitter_analyzer/analysis/import_sanitizer.py` (~400 lines)

**完成内容**:
- `ImportInfo` dataclass: 导入名、模块、行号、列号、别名
- `SymbolRef` dataclass: 符号名、行号、列号、上下文
- `SortViolation` dataclass: 排序违规信息
- `ImportAnalysisResult` dataclass: 聚合结果
- `ImportSanitizer` class:
  - `analyze_file(file_path)` → 检测单文件
  - `analyze_directory(dir_path)` → 检测目录
  - `detect_unused_imports()` → 检测未使用的导入
  - `detect_circular_imports()` → 检测循环依赖
  - `check_sort_compliance()` → 检查导入排序合规性
- Python 导入模式支持:
  - `import os`
  - `import os.path`
  - `from os import path`
  - `from os import path as ospath`
  - `from os import *` (标记为不可静态验证)

**测试**: 20+ tests

### Sprint 2: Multi-Language Support

**文件**:
- `tree_sitter_analyzer/analysis/import_sanitizer.py` (扩展)

**完成内容**:
- JavaScript/TypeScript: `import { x } from 'y'`, `import x from 'y'`, `import 'y'`
- Java: `import com.example.Foo`, `import static com.example.Bar.method`
- Go: `import "fmt"`, `import ( "fmt" "os" )`
- 每种语言的排序合规性规则

**测试**: 15+ tests

### Sprint 3: MCP Tool Integration

**文件**:
- `tree_sitter_analyzer/mcp/tools/import_sanitizer_tool.py` (~250 lines)
- `tree_sitter_analyzer/mcp/registry.py` (added import_sanitizer)
- `tree_sitter_analyzer/mcp/tool_registration.py` (registered import_sanitizer)

**完成内容**:
- MCP tool: `import_sanitizer` (analysis toolset)
- 参数: file_path, project_root, check_unused, check_circular, check_sort, format
- 输出: TOON + JSON
- 工具注册到 ToolRegistry

**测试**: 15+ tests

## Technical Approach

- 使用 tree-sitter 查询解析 import 语句（与 env_tracker 模式一致）
- 符号引用分析：提取文件中所有标识符引用，与导入符号匹配
- 循环检测：构建 import 图，使用 Tarjan SCC 算法
- 排序合规性：每语言配置排序规则（PEP 8, Google Java Style, Go conventions）
- 单文件分析独立于项目级分析
