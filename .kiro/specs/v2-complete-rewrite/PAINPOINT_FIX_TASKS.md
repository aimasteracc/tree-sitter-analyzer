# 痛点修复任务清单

**创建时间**: 2026-02-03
**执行顺序**: #11 → #10 → #4 → #3 → #14

---

## 🔴 Today (Critical - 3h)

### Task 1: 修复 #11 编码错误 (1h)
**文件**: `tree_sitter_analyzer_v2/search.py`
**验收**: 无 UnicodeDecodeError，Windows 兼容

### Task 2: 修复 #10 search_content API (2h)
**文件**: `tree_sitter_analyzer_v2/search.py`
**验收**: API 返回结果与 CLI 一致

---

## 🔥 This Week (High - 9h)

### Task 3: 实现 #4 --summary 模式 (2h)
**文件**: `tree_sitter_analyzer_v2/cli/main.py`, `formatters/`
**验收**: CLI 支持 --summary，输出简洁

### Task 4: 优化 #3 Markdown 格式 (3h)
**文件**: `tree_sitter_analyzer_v2/formatters/markdown_formatter.py`
**验收**: 无嵌套表格，可读性 > 8/10

### Task 5: 增强 #14 Code Graph 查询 (4h)
**文件**: `tree_sitter_analyzer_v2/graph/queries.py` (新建)
**验收**: 实现 3+ 查询方法，测试覆盖 > 80%

---

## 📊 进度追踪

| Task | 状态 | 开始时间 | 完成时间 | 实际工作量 |
|------|------|----------|----------|------------|
| #11 编码错误 | ✅ 完成 | 2026-02-03 | 2026-02-03 | 0.5h |
| #10 search_content | ✅ 完成 | 2026-02-03 | 2026-02-03 | 0.5h |
| #4 --summary | ⏳ 待开始 | - | - | - |
| #3 Markdown | ⏳ 待开始 | - | - | - |
| #14 Code Graph | ⏳ 待开始 | - | - | - |

## ✅ 已完成修复总结

### 痛点 #11 & #10: 编码错误和 search_content API

**修复方式**: TDD 驱动修复
- 在 `subprocess.run()` 中添加 `encoding='utf-8'` 和 `errors='replace'`
- 修复文件: `tree_sitter_analyzer_v2/search.py` (L87, L168)
- 新增测试: `TestEncodingSupport` 类 (2 个测试)
- 测试覆盖率: search.py 从 55% → 85%
- 全部测试: 24/24 通过 ✅
