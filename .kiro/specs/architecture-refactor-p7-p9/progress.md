# Architecture Refactor P7-P9 — Progress

## Session 2026-02-11

### Phase 7: 彻底拆分 __init__.py ✅

- `__init__.py` 1486 行 → 48 行 (**96.8% 减少**)
- 创建 6 个新模块:
  - `constants.py` (37 行): FRAMEWORK_DECORATORS + PUBLIC_API_PATTERNS 唯一定义
  - `formatters.py` (123 行): TOON + Mermaid 格式化
  - `call_index.py` (257 行): 调用索引构建 + 共享 call-site 提取
  - `result.py` (349 行): CodeMapResult 数据类 + 全部方法
  - `parallel.py` (126 行): 线程安全并行解析
  - `scanner.py` (489 行): ProjectCodeMap 扫描引擎
- **结果**: 全量测试 0 failures

### Phase 8: DIP 完成 ✅

- `_lazy_import_parsers()` 完全删除 (零引用)
- `get_thread_parsers()` 从 `ParserRegistry.get_all_parsers()` 获取 parser
- 每线程通过 `type(parser)()` 创建独立实例 (失败时 skip 而非 fallback)
- `_get_call_extractor()` 删除，统一到 `call_index.extract_call_sites()`
- `graph.extractors` 的 import 仅存在于 `call_index.py` 一处（单一入口）
- **结果**: 零处直接 import languages/

### Phase 9: 异常处理净化 ✅

- 所有 `except Exception` 改为 `except Exception as e` + `logger.warning/debug`
- 包括 `analyzers/test_audit.py` 遗漏项
- 零处裸 `except Exception:`

### 10 Expert Panel Review

#### Round 1: 5 条指摘
| ID | 专家 | 严重度 | 问题 | 修复 |
|----|------|--------|------|------|
| U-1 | Uncle Bob | High | scanner._get_call_extractor 直接 import graph | 统一到 call_index.extract_call_sites() |
| B-1 | Burns | High | call site 提取重复 (parallel+scanner) | 删除重复，共享函数 |
| U-2 | Uncle Bob | Medium | parallel fallback 到共享实例 | 改为 skip |
| K-1 | Kerr | Medium | 两处同功能不同签名 | 统一删除重复 |
| T-1 | Torvalds | Medium | FRAMEWORK_DECORATORS 引用不一致 | 统一直接引用 constants |

#### Round 2: 0 条指摘 → ✅ 全员通过!

## Metrics

| 指标 | Before (P1-P6) | After (P7-P9) | 改善 |
|------|----------------|---------------|------|
| `__init__.py` 行数 | 1486 | 48 | **-96.8%** |
| 裸 `except Exception:` | 5+ | 0 | **-100%** |
| `_lazy_import_parsers` 引用 | 2 | 0 | **-100%** |
| `graph.extractors` 入口 | 3+ | 1 | **-67%** |
| call-site 提取重复 | 2 处 | 1 处 (共享) | **-50%** |
| `_FRAMEWORK_DECORATORS` 定义 | 2 处 | 1 处 (constants.py) | **-50%** |
| 模块数 | 3 (init+types+analyzers/) | 9 | 职责清晰拆分 |
| 测试通过 | 1088+ | 1088+ | **零回归** |
| 专家评审轮数 | — | 2 轮 (5→0 指摘) | ✅ |

## Issues Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| 测试运行极慢 | 1 | 发现 coverage 收集导致，用 --no-cov 后 107s 完成 |
| StrReplace 匹配失败 | 1 | docstring 中带换行的内容匹配不上，改用更精确的上下文 |
