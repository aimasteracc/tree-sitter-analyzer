# 系统知识注入

## wiki: ts-analyzer-autonomous-dev-design.md
8步全自动开发流程 + 7种失败模式防御 + 5层自主架构。
wiki灵感→竞品否决→功能评分→TDD实现→质量门禁→commit→回到wiki

## wiki: tree-sitter-analyzer-test-mastery.md
测试质量门禁系统 + test_mastery_scan.py 模式。
必须满足: property test ≥10%, oversized files ≤0, skip rate ≤5%,
assertion density ≥1.5, test:source ≤3.0

## wiki: tree-sitter-analyzer-autonomous-dev-capability.md
5层架构: 感知层→决策层→自主执行层→反思层→记忆层
8步执行顺序, 1-in-1-out规则, Self-Hosting Gate,
3-Agent GAN: Planner→Generator→Evaluator

## wiki: tree-sitter-analyzer-24x7-autonomous-dev-monitoring.md
监控手册: 进程存活/Git状态/提交频率/测试通过率/覆盖率趋势/异常告警

## wiki: tree-sitter-performance.md
增量解析(GLRAnalyzer+ParsingTable), SubtreePool, GLR策略,
节点重用条件: 不可变的left_children+stable_state nodes,
keyword extraction, external scanner优化

## 竞品否决检查
ESLint/Ruff/SonarQube: 已覆盖, 跳过
CodeFlow: 浏览器端正则→精确度不如AST, 跳过
GitNexus: 知识图谱+爆炸半径→可作为Phase 7灵感参考

## 质量基线
- test_mastery_scan.py gate: Property test 10.2% ✓
- 23 oversized files (待Phase 8拆分)
- 79 low assertion density files (待增强)
- Skip rate 2.8% ✓
- 覆盖率: tree_sitter_compat 66%→目标>70%

### 2026-05-18 Tick 观察

- `test_engine.py` 是高优先目标文件（D 级，1700+ 行）。首次动作已完成一次 mixin 拆分。
- 按 CLAUDE/MCP 建议，`refactoring_suggestions` 给出的切片顺序可继续执行；建议本轮持续沿 `TestUnifiedAnalysisEngine*` 分组拆出混杂职责。
- 风险低：`TestUnifiedAnalysisEnginePluginManagement` 再次收口后完成验证
  - `uv run pytest tests/unit/core/test_engine.py -q`（85 passed, 1 skipped）
  - `uv run pytest -q`（10401 passed, 32 skipped）
  - `uv run python -m tree_sitter_analyzer --file-health tests/unit/core/test_engine.py`（`D(69.0)`，`oversized_file` 与 `deep_nesting` 仍为关键异味）
  - `uv run python -m tree_sitter_analyzer --change-impact --format json`（低风险队列，推荐 `uv run pytest -q` 进行队列验收）
- 下一步：继续按同一顺序切片 `TestUnifiedAnalysisEngineCacheManagement` / `TestUnifiedAnalysisEngineLanguageDetection`，优先保持每次单批次的测试反馈闭环。

- 2026-05-18 Tick: `test_engine.py` 继续切片成功收口 2 个类
  - 完成动作：将 `TestUnifiedAnalysisEngineCacheManagement` 与 `TestUnifiedAnalysisEngineLanguageDetection` 的测试迁移到 `tests/unit/core/_test_engine_test_mixin.py`。
  - 验证链路：
    - `uv run pytest tests/unit/core/test_engine.py -q`（78 passed, 1 skipped）
    - `uv run python -m tree_sitter_analyzer --file-health tests/unit/core/test_engine.py --format json`（`D(69.2)`，剩余 `oversized_file` 与 `deep_nesting`）
    - `uv run python -m tree_sitter_analyzer --change-impact --format json`（low risk, affected 1 file）
    - `uv run pytest -q`（10426 passed, 32 skipped）
  - 下一步优先级：继续 `TestUnifiedAnalysisEngineAnalysis`、`Security`、`Queries` 等职责分离方向，优先保持每次 1 个小批次可回归闭环。

- 2026-05-18 Tick: `TestUnifiedAnalysisEngineAnalysis` 迁入 mixin
  - 触发理由：沿现有 `refactoring_suggestions` 顺序，优先继续剥离 `TestUnifiedAnalysisEngine*` 责任块。
  - 执行结果：
    - 抽离 10 个 analysis 相关测试到 `TestUnifiedAnalysisEngineAnalysisTestMixin`（`tests/unit/core/_test_engine_test_mixin.py`）；
    - `TestUnifiedAnalysisEngineAnalysis` 保留清理钩子并继承 mixin（`tests/unit/core/test_engine.py`）。
  - 验证结果：
    - `uv run pytest tests/unit/core/test_engine.py -q`（69 passed, 1 skipped）
    - `uv run python -m tree_sitter_analyzer tests/unit/core/test_engine.py --file-health --format json`（`C(74.3)`；关键点仍是 `oversized_file` + `deep_nesting`）
    - `uv run python -m tree_sitter_analyzer --change-impact --format json`（低风险：主变更集中在 2 个文件）
    - `uv run pytest -q`（10385 passed, 32 skipped）
  - 结论：高优先异味已持续下降，下一步继续拆分 `Security` / `Queries`，保持单批次回归闭环。

- 2026-05-18 Tick: `TestUnifiedAnalysisEngineSecurity` 与 `TestUnifiedAnalysisEngineQueries` 迁入 mixin
  - 触发理由：继续沿 `TestUnifiedAnalysisEngine*` 列表收缩 oversized test file，并优先处理安全/查询分组。
  - 执行结果：
    - 新增 `TestUnifiedAnalysisEngineSecurityTestMixin` 与 `TestUnifiedAnalysisEngineQueriesTestMixin`（`tests/unit/core/_test_engine_test_mixin.py`）；
    - `TestUnifiedAnalysisEngineSecurity` 与 `TestUnifiedAnalysisEngineQueries` 在 `tests/unit/core/test_engine.py` 改为继承对应 mixin。
  - 验证结果：
    - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
    - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
    - `uv run pytest tests/unit/core/test_engine.py -q`（64 passed, 1 skipped）
    - `uv run python -m tree_sitter_analyzer tests/unit/core/test_engine.py --file-health --format json`（`C(75.1)`；剩余 `oversized_file` + `deep_nesting`）
    - `uv run python -m tree_sitter_analyzer --change-impact --format json`（低风险：2 文件变更，1 文件受影响）
    - `uv run pytest -q`（10380 passed, 32 skipped）
  - 结论：`Security` 与 `Queries` 责任已成功抽离；文件健康仍由 `oversized_file` 主导，下一步建议继续迁移 `TestUnifiedAnalysisEnginePerformance` 与 `Properties`。

- 2026-05-18 Tick: `TestUnifiedAnalysisEnginePerformance` 与 `TestUnifiedAnalysisEngineProperties` 迁入 mixin
  - 触发理由：沿 `refactoring_suggestions` 顺序继续收口 `TestUnifiedAnalysisEngine*` 组，优先缩短大文件主职责。
  - 执行结果：
    - 新增 `TestUnifiedAnalysisEnginePerformanceTestMixin` 与 `TestUnifiedAnalysisEnginePropertiesTestMixin`；
    - 在 `tests/unit/core/test_engine.py` 中将 `TestUnifiedAnalysisEnginePerformance` 与 `TestUnifiedAnalysisEngineProperties` 改为继承对应 mixin。
  - 验证结果：
    - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
    - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
    - `uv run pytest tests/unit/core/test_engine.py -q`（60 passed, 1 skipped）
    - `uv run pytest -q`（10376 passed, 32 skipped）
    - `uv run python -m tree_sitter_analyzer tests/unit/core/test_engine.py --file-health --format json`（`C(75.0)`；`oversized_file` + `deep_nesting`）
    - `uv run python -m tree_sitter_analyzer --change-impact --format json`（低风险：2 文件变更）
  - 结论：`Performance` 与 `Properties` 已迁移，`test_engine.py` 异味主因仍为 `oversized_file`，下一步建议继续处理 `TestUnifiedAnalysisEngineCleanup` 与深度嵌套位置。

- 2026-05-18 Tick: `TestMockLanguagePlugin` 迁入 mixin（继续切片）
  - 目标：延续 `test_engine.py` 责任拆分，抽离 `TestMockLanguagePlugin`。
  - 执行结果：
    - 新增 `TestMockLanguagePluginTestMixin`（`tests/unit/core/_test_engine_test_mixin.py`）。
    - `TestMockLanguagePlugin` 在 `tests/unit/core/test_engine.py` 改为继承 mixin。
  - 验证链路：
    - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
    - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
    - `uv run pytest tests/unit/core/test_engine.py -q`（55 passed, 1 skipped）
    - `uv run pytest -q`（10371 passed, 32 skipped）
    - `uv run python -m tree_sitter_analyzer tests/unit/core/test_engine.py --file-health --format json`（`C(75.1)`，`oversized_file` + `deep_nesting`）
    - `uv run python -m tree_sitter_analyzer --change-impact --format json`（低风险：2 文件变更，1 文件受影响）
  - 结论：本次切片完成且回归通过，队列继续推进到 `TestUnifiedAnalysisEngineCleanup` 或下一类 `*Comprehensive` 责任块。

- 2026-05-18 Tick: `TestUnifiedAnalysisEngineCleanup` 迁入 mixin
  - 目标：继续收口 `TestUnifiedAnalysisEngine*` 组并继续压缩 `test_engine.py`。
  - 执行结果：
    - 新增 `TestUnifiedAnalysisEngineCleanupTestMixin`（`tests/unit/core/_test_engine_test_mixin.py`）；
    - `TestUnifiedAnalysisEngineCleanup` 在 `tests/unit/core/test_engine.py` 改为继承该 mixin，仅保留 `teardown_class`。
  - 验证链路：
    - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
    - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
    - `uv run pytest tests/unit/core/test_engine.py -q`

- 2026-05-19 Tick: unification 测试组迁入 mixin
  - 触发理由：`safe-to-edit` 判定 `tests/unit/core/test_engine.py` 可直接聚焦编辑；`file-health` 显示主要弱点仍是 `oversized_file`。
  - 执行结果：
    - 将 `TestUnifiedEngineSingleton`、`SyncAnalysis`、`AnalyzeCode`、`QueryExecution`、`NonexistentFile`、`CompatibilityProperties` 的测试体迁入 mixin；
    - 主测试文件保留类名和来源分组，降低单文件体积并保持 pytest 收集路径稳定。
  - 验证结果：
    - `uv run pytest tests/unit/core/test_engine.py -q`（32 passed）
    - `uv run pytest -q`（10348 passed, 31 skipped）
    - `uv run python -m tree_sitter_analyzer tests/unit/core/test_engine.py --file-health --format json`（`C(77.0)`；971 lines；剩余 `oversized_file` + `deep_nesting`）
    - `uv run python -m tree_sitter_analyzer --change-impact --format json`（low risk，推荐 default suite 已执行）
  - 结论：本轮闭环干净，可提交推送；下一轮继续同一队头，优先迁移 `TestAnalysisEnginePublicAPI`、`TestAnalysisEngineConcurrency` 或 `TestAnalysisEngineEdgeCases`。
