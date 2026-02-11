# Architecture Refactor P7-P9 — Design

## Phase 7: 彻底拆分 `__init__.py` (1486 → <50 行)

### 拆分方案

当前 `__init__.py` 的逻辑分区：

| 行范围 | 内容 | 目标文件 |
|--------|------|---------|
| 1-97 | Imports + `__all__` + `_lazy_import_parsers` | `__init__.py` (瘦身) |
| 99-111 | `_FRAMEWORK_DECORATORS` (模块级) | 删除 (和类内版本合并) |
| 114-128 | `_get_thread_parsers()` | `parallel.py` |
| 131-228 | `_parse_file_standalone()` | `parallel.py` |
| 231-726 | `CodeMapResult` | `result.py` |
| 728-1372 | `ProjectCodeMap` | `scanner.py` |
| 1374-1454 | `_format_toon()` | `formatters.py` |
| 1457-1486 | `_format_mermaid()` | `formatters.py` |

### 新文件结构

```
core/code_map/
├── __init__.py        # <50 行: 只做 re-export
├── types.py           # 已存在: 所有 dataclass
├── result.py          # NEW: CodeMapResult 数据类 + 方法
├── scanner.py         # NEW: ProjectCodeMap 扫描引擎
├── parallel.py        # NEW: 并行解析基础设施
├── formatters.py      # NEW: TOON + Mermaid 格式化
├── call_index.py      # NEW: 调用索引构建 (从 result.py 中抽出)
├── constants.py       # NEW: _FRAMEWORK_DECORATORS (唯一定义)
└── analyzers/         # 已存在
```

### 依赖方向 (clean)

```
__init__.py → re-exports from all modules
scanner.py → result.py, parallel.py, constants.py, types.py
result.py → call_index.py, analyzers/, formatters.py, types.py
parallel.py → parser_registry, constants.py, types.py
call_index.py → types.py
formatters.py → types.py
constants.py → (无依赖)
```

## Phase 8: DIP 完成

### 问题
- `_get_thread_parsers()` 直接 `from languages.xxx import XxxParser`
- `_parse_file_standalone` 直接 `from graph.extractors import JavaCallExtractor`

### 方案
1. `_get_thread_parsers()` → 从 `ParserRegistry` 获取 parser 类，每线程实例化
2. `ParserRegistry` 新增 `get_parser_class(lang)` 返回类而非实例
3. `CallExtractor` 注册到 `ParserRegistry`，通过 `get_call_extractor(lang)` 获取

## Phase 9: 异常处理净化

### 5 处裸 `except Exception` 全部添加日志

| 位置 | 当前行为 | 修复方案 |
|------|---------|---------|
| `parallel.py` (原 L227) | `return None` | `logger.warning("Failed to parse %s: %s", file_path, e)` |
| `result.py` (原 L614) | `return` | `logger.warning("Regex scan failed for %s: %s", module.path, e)` |
| `result.py` (原 L724) | `return ""` | `logger.debug("Cannot read symbol code: %s", e)` |
| `scanner.py` (原 L883) | `pass` | `logger.warning("Parallel parse failed for %s: %s", rel_path, e)` |
| `scanner.py` (原 L951) | `return None` | `logger.warning("Failed to parse file %s: %s", file_path, e)` |
