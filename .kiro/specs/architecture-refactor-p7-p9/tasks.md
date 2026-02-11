# Architecture Refactor P7-P9 — Tasks

| Task | Phase | Status | Files | Acceptance |
|------|-------|--------|-------|------------|
| T1: 创建 constants.py | P7 | completed | `core/code_map/constants.py` | `FRAMEWORK_DECORATORS` 唯一定义 ✅ |
| T2: 创建 formatters.py | P7 | completed | `core/code_map/formatters.py` | `format_toon` + `format_mermaid` ✅ |
| T3: 创建 call_index.py | P7 | completed | `core/code_map/call_index.py` | 调用索引构建逻辑 ✅ |
| T4: 创建 result.py | P7 | completed | `core/code_map/result.py` | `CodeMapResult` 完整数据类 ✅ |
| T5: 创建 parallel.py | P7 | completed | `core/code_map/parallel.py` | 并行解析 + 线程安全 ✅ |
| T6: 创建 scanner.py | P7 | completed | `core/code_map/scanner.py` | `ProjectCodeMap` 扫描引擎 ✅ |
| T7: 瘦身 __init__.py | P7 | completed | `core/code_map/__init__.py` | 48 行 (< 50 目标) ✅ |
| T8: 回归验证 P7 | P7 | completed | `tests/` | 全量 0 failures, 4 skips ✅ |
| T9: DIP 修复 _get_thread_parsers | P8 | completed | `parallel.py` | 从 registry 获取 parser ✅ |
| T10: DIP 修复 call extractor | P8 | completed | `parallel.py` | graph.extractors 仅在运行时导入 ✅ |
| T11: 删除 _lazy_import_parsers | P8 | completed | 全部文件 | 零处引用 ✅ |
| T12: 异常处理净化 | P9 | completed | 6 处 except | 全部 `as e` + logger ✅ |
| T13: 回归验证 P8+P9 | P9 | completed | `tests/` | 全量 0 failures ✅ |
