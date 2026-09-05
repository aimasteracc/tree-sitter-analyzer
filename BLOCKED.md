# 待裁决清单（v1.29.2 热修随附）

1. 松断言棘轮的 PR-diff 检测存在误报：tests/unit/mcp/test_read_partial_tool_coverage.py
   与 tests/unit/test_patch_coverage_check.py 的 4 条断言与 origin/main 逐字节相同，
   却被报为「PR 新增」。本次以官方豁免通道（# ratchet: 注释）放行并留痕；
   检测逻辑本身（check_loose_assertions.py 的 diff 基准）待独立修复。
2. ast_diff 剩余 64 个存活变异的逐个等价性论证未完成（目标 ≤20% 已达成，
   存活率 15.2%）；多为 errors="replace" 语义与字符串字面量类近等价变异，
   完整清单可由 `uv run mutmut results` 复现。

# 追加（v1.29.3 轮次二）

3. [已修复 v1.29.4] _is_test_path 相对路径漏判——已修复并补齐正反用例。
