# 待裁决清单（v1.29.2 热修随附）

1. 松断言棘轮的 PR-diff 检测存在误报：tests/unit/mcp/test_read_partial_tool_coverage.py
   与 tests/unit/test_patch_coverage_check.py 的 4 条断言与 origin/main 逐字节相同，
   却被报为「PR 新增」。本次以官方豁免通道（# ratchet: 注释）放行并留痕；
   检测逻辑本身（check_loose_assertions.py 的 diff 基准）待独立修复。
2. [2026-09-07 撤回达标结论，等待可信复测] ast_diff 的“64 存活、15.2% 存活率、
   目标 ≤20% 已达成”及“多为近等价变异”均未验证，不能继续作为实测结论。
   九月发布的 422/246/510 总数只统计顶层 def，遗漏类方法；不能据此推断 killed。
   `tests/effectiveness/BASELINE.md` 保留原始发布表并撤回九月分数、合计及改善结论。
   必须以 mutmut 完整元数据的全状态、相同源范围和测试选择重建前后可比测量，
   再逐项审查等价性。本机无 mutants/ 缓存，未复跑长变异任务，不提供替代成绩。
   mutmut 3.7.0 的 `results --all true` 可读取已有全状态记录，但须使用对应运行配置；
   默认 results 隐藏 killed，不能单独证明完整性或复现历史成绩。

# 追加（v1.29.3 轮次二）

3. [已修复 v1.29.4] _is_test_path 相对路径漏判——已修复并补齐正反用例。
