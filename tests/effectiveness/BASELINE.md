# RFC-0017 Phase 1 — Mutation Baseline

**Date**: 2026-06-14
**Tool**: mutmut 3.6.0
**Runner**: macOS (arm64, Python 3.14.3)
**Config**: `[tool.mutmut]` in `pyproject.toml`; per-mutant test selection narrows to module-specific tests
**Run command (per module)**: see `scripts/run_mutation_baseline.py`

> This file records the **curated baseline** from the first phase-1 run.
> Per-run cache files (`.mutmut-cache`, `mutants/`) are NOT committed — see `.gitignore`.
> Refresh this file deliberately (not on every CI run) when the baseline improves.

---

## 2026-09-07 校正：九月更新未验证，达标结论撤回

**当前没有可信复跑支持 2026-09 的高分或达标结论。** 下方保留原始发布表供审计，
不是当前实测成绩，也不是验收依据。九月更新中的 `422 / 246 / 510` 总数来自只计
顶层 `def` 的统计，遗漏类方法，不能作为完整变异分母，更不能据此用差值推断 killed。
`semantic_change_classifier` 的九月更新也未经过可信复跑，同样标记为未验证。
所有依赖这些数字的分数、合计、改善幅度及“剩余多为等价变异”结论均撤回。
六月历史解释和 `toon_encoder` 历史行保留，但未在本轮复核，不能代表当前代码。

## 原始发布表（封存；2026-09 更新数字全部未验证）

| Module | Total mutants | Killed | Survived | No-test | Score | Surviving = bugs suite misses |
|---|---|---|---|---|---|---|
| `ast_diff.py` | 422 | 358 | **64** | 0 | **84.8%** | 64 deliberate bugs the suite does not catch (2026-09-05 v1.29.2 hardening: was 238 surviving / 59.0% score; see dated note below) |
| `semantic_change_classifier.py` | 330 | 318 | **12** | 0 | **96.4%** | 12 deliberate bugs the suite does not catch (v1.29.3: 71→10; v1.29.4 module grew via `_is_test_path` fix) |
| `mcp/tools/facade_tool.py` | 246 | 229 | **17** | 0 | **93.1%** | 17 deliberate bugs the suite does not catch (2026-09-05 v1.29.3 hardening: was 65 surviving / 70.3%; tests narrowed to facade-specific files fixing the sandbox baseline failure) |
| `mcp/tools/query_symbol_search.py` | 510 | 420 | **90** | 0 | **82.4%** | 90 deliberate bugs the suite does not catch (2026-09-05 v1.29.4 hardening: was 360 surviving / 37.2%; selection narrowed, denominator stabilized) |
| `formatters/toon_encoder.py` | 464 | 141 | **140** | 183 | **30.4%** | 140 deliberate bugs the suite does not catch |
| **TOTAL (5 modules)** | **1 972** | **1 466** | **323** | 183 | **74.3%** | **323 surviving mutants = 323 deliberate bugs the current suite cannot catch** |

**原合计结论已撤回：** 323 surviving、1 972 total、1 466 killed、74.3% 均为上述
混合口径表的未验证合计，不能据此量化当前测试有效性。存活变异也不自动等于真实缺陷；
是否等价必须逐项提供证据。

> **历史原文，已撤回其测量与等价性结论（2026-09-07）**：
> **2026-09-05 更新（v1.29.2 热修）**：`ast_diff.py` 完成场景化加固——
> 新增 `tests/unit/test_ast_diff_scenarios.py`（65 个场景测试，断言对齐真实语义），
> 存活变异 238 → 64、杀死率 59.0% → 84.8%。同轮修复了测量脚本
> `scripts/run_mutation_baseline.py` 的沙盒回归：2026-07 大重构后
> `ast_diff` 引入包内依赖（`.core.parser`、`.project_graph`）而 mutmut
> 沙盒未随之拷贝，导致 6 月之后的基线复跑全部失败（`also_copy` 修复）。
> ast_diff 的 Total 由 580 变为 422 系测量口径随沙盒修复而稳定，
> 前后对比以「存活数」为准（238 → 64）。剩余 64 个存活多为等价变异
> （如 `errors="replace"` 语义、字符串字面量差），清单存于热修 PR。.

---

## Interpretation per module（六月历史记录，非当前验证结论）

### `ast_diff.py` — 238 surviving / 59.0%

The highest absolute surviving count. The `_diff_matched_nodes`, `_sig_diff`, and
`diff_strings`/`diff_files` method bodies have the most survivors. Tests check that
hunks are produced and classify correctly; they do not assert on fine-grained field
values within hunks (which fields changed, by exactly how much, etc.). This module
produced the real defect that triggered the RFC: 155 KB output for a small diff —
the output-size invariant was missing.

### `semantic_change_classifier.py` — 71 surviving / 77.4%

Best score of the five. The classifier has property-based test coverage (Hypothesis)
which kills mutants that purely structural tests would not. Still 71 surviving; most
are in edge-case branches and the scoring arithmetic.

### `mcp/tools/facade_tool.py` — 65 surviving / 70.3%

15 mutants had no test associations (untouched code paths in targeted test set).
65 survive: the routing logic, the action-dispatch switch, and optional-parameter
handling are under-asserted. Tests confirm the facade routes and returns something;
they do not pin the dispatch invariants.

### `mcp/tools/query_symbol_search.py` — 360 surviving / 37.2%

Worst score. 122 mutants had no test associations — large uncovered surface in the
targeted test set. The 360 survivors concentrate in SQL-building helpers and result
post-processing. Tests assert on result shape (keys present), not on values or SQL
correctness.

### `formatters/toon_encoder.py` — 140 surviving / 30.4%

183 "no-test" mutants: the targeted test set (`test_output_cost_invariants.py`,
`test_toon_compact_only.py`, `test_toon_losslessness_637.py`) does not exercise
many encoder branches. The 140 survivors are in low-level formatting helpers.
The cost-invariant test is the only value test here; it kills the most mutants
per test line in the targeted set.

---

## Mutation score emoji legend（历史记录，不用于统计）

图标含义随版本变化；以下保留原文。报告必须按对应版本的元数据状态解释，不按图标或源码计数。

- 🎉 = killed (test caught the bug)
- 🫥 = survived (test missed the bug) — THE NUMBER
- ⏰ = timeout
- 🙁 = killed by another exit code (still killed)
- 🔇 = no tests
- 🧙 = caught by type checker

---

## Notes on "no-test" mutants

Exit code 33 from mutmut means the targeted test set has no association with
that mutant's function. This is a real signal: it means those code paths have
**zero targeted test coverage**. For `toon_encoder.py` (183 no-test / 40%) and
`query_symbol_search.py` (122 no-test / 16%), expanding the targeted test set
would likely reveal additional survivors.

---

## How to re-run

以下命令是未来复测入口，本轮未执行长变异任务。`toon_encoder` 已删除，历史命令不可
直接作为当前复跑任务；应先核对源文件及测试选择。

```bash
# Per-module run (see scripts/run_mutation_baseline.py):
uv run python scripts/run_mutation_baseline.py ast_diff
uv run python scripts/run_mutation_baseline.py semantic_change_classifier
uv run python scripts/run_mutation_baseline.py facade_tool
uv run python scripts/run_mutation_baseline.py query_symbol_search
uv run python scripts/run_mutation_baseline.py toon_encoder

# Or use the CI workflow (ubuntu-latest only; mutmut needs os.fork):
# .github/workflows/mutation-baseline.yml (manual trigger / on-label)
```

### 可信复测与轻量读取要求

1. 保存前后 source revision、测试 revision、精确源文件和测试选择、mutmut/Python 版本、
   完整配置与命令、退出码及原始元数据。前后必须采用相同源范围、相同测试选择和统计规则；
   若测试内容是被评估的变量，应记录其差异。若源代码或变异集合变化，先建立可比集合或重建基线，
   不直接比较总存活数来宣称改善。
2. 使用 mutmut 完整元数据中的全部 mutant key（包括类方法）逐项统计全部状态。
   单列 killed、survived、no tests、not checked、timeout、skipped、suspicious、
   interrupted、segfault、type-check caught 及未知状态；不能把非 survived 状态都算 killed。
   明确分母和 killed 的定义，核对全状态之和与完整变异集合；未知、缺失、未完成结果必须披露。
3. `run` 和结果读取均成功只是必要条件，不证明元数据完整、缓存新鲜或成绩达标。
   使用隔离的运行目录保留每次证据，不把旧缓存混入新测试选择的成绩。
4. 本机 2026-09-07 查验为 **mutmut 3.7.0**，`uv run mutmut results --help` 显示
   `--all BOOLEAN`。其实现从 `SourceFileMutationData.exit_code_by_key` 读取状态，默认隐藏 killed。
   在已有完整缓存、且配置与生成缓存时一致的隔离运行目录中，可轻量执行
   `uv run mutmut results --all true` 查看所有已记录状态；该命令不启动变异测试。
   runner 恢复原 `pyproject.toml` 后不能假定其配置仍与该次运行一致。
5. 本工作区没有 `mutants/`，未获得可核验的历史元数据；上述方法只验证了本机版本的
   CLI 及实现，不保证 3.6.0 或未来版本兼容。空输出不等于零变异，已有输出也不证明没有遗漏。
   本轮不发布任何替代成绩。

---

## Phase-2 plan (separate PR)

可信基线重建之前，不启用基于上述未验证分数的达标或退化判断。
Once the ratchet is configured with a verified baseline, a PR may not lower any module's mutation score.
Surviving mutants are triaged: kill (add the missing assertion) or annotate
(equivalent mutant, document why behavior-preserving). The `query_symbol_search.py`
score (37.2%) and `toon_encoder.py` score (30.4%) are the highest-priority targets.
