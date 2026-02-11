# Architecture Refactor P7-P9 — Requirements

## 背景

Phase 1-6 完成后，10 位全球顶级架构师联合评审发现 3 个 P0 Critical 问题：

### P0 #1: `__init__.py` 仍然 1485 行（Fowler 评分 5/10）
- `CodeMapResult` 带 15 个委托方法 + 200+ 行调用索引构建
- `ProjectCodeMap` 800+ 行扫描引擎
- `_format_toon` / `_format_mermaid` 格式化逻辑
- `_parse_file_standalone` + `_get_thread_parsers` 并行解析基础设施
- **本质上是把 2500 行改名为 1485 行，结构未变**

### P0 #2: DIP 被 `_lazy_import_parsers` 绕过（Uncle Bob 评分 4/10）
- `_get_thread_parsers()` 直接实例化 `PythonParser()`, `JavaParser()`, `TypeScriptParser()`
- 并行解析（最热路径）完全不走 `ParserRegistry`
- `_parse_file_standalone` 直接 import `graph.extractors`（依赖方向反了）
- **两套系统而非一套**

### P0 #3: 8+ 处裸 `except Exception` 静默吞错（Hightower 评分 3/10）
- `_parse_file_standalone` L227: `except Exception: return None`
- `_build_call_index_regex` L614: `except Exception: return`
- `_parse_files_parallel` L883: `except Exception: pass`
- `_parse_file` L951: `except Exception: return None`
- `_read_symbol_code` L724: `except Exception: return ""`
- 文件解析失败、编码错误、权限问题全部消失无踪

## 目标

| Phase | 目标 | 量化验收标准 |
|-------|------|-------------|
| P7 | 彻底拆分 `__init__.py` | `__init__.py` < 50 行，只做 re-export |
| P8 | DIP 完成 | 零处直接 import `languages/`，零处 `_lazy_import_parsers` |
| P9 | 异常处理净化 | 零处裸 `except Exception`，全部有 `logger.warning/error` |

## 非功能性要求

- 1088+ tests 全部通过（零回归）
- 向后兼容：所有 public API 保持不变
- 每个 Phase 独立可验证
