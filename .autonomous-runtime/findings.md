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

- 2026-05-19 Tick: `TestAnalysisEnginePublicAPI` / `Concurrency` / `EdgeCases` 迁入 mixin
  - 触发理由：队头继续是 `tests/unit/core/test_engine.py` 的 oversized 结构异味，且这些类可直接作为独立 mixin 切片收口。
  - 执行结果：
    - 新增并迁移测试至 `tests/unit/core/_test_engine_test_mixin.py`：
      `TestAnalysisEnginePublicAPITestMixin`（2 条测试）、
      `TestAnalysisEngineConcurrencyTestMixin`（2 条并发测试）、
      `TestAnalysisEngineEdgeCasesTestMixin`（边界/异常/编码类测试）。
    - `tests/unit/core/test_engine.py` 的 `TestAnalysisEnginePublicAPI`、`TestAnalysisEngineConcurrency`、`TestAnalysisEngineEdgeCases` 改为纯继承层级。
    - 补齐 `CLAUDE.md` 契约字段以满足 change-impact 验证要求（`verification_command`、`pytest_required`、`--change-impact --format json`）。
  - 验证结果：
    - `uv run ruff check --fix ...` / `uv run ruff check ...`（通过）
    - `uv run pytest tests/unit/core/test_engine.py -q`（20 passed）
    - `uv run pytest <focused-performance-set> -q`（84 passed, 3 skipped）
    - `uv run pytest -q`（10336 passed, 31 skipped）
    - `uv run pytest tests/unit/test_agent_contracts.py::test_agent_docs_require_change_impact_verification_command -q`（通过）
- 结论：本批切片干净通过，`test_engine.py` 异常负担继续下降；队列可继续处理下一组分析/公共 API 边界测试。

- 2026-05-19 Tick: `TestAnalysisEngineConfiguration` / `TestAnalysisEnginePerformanceExtended` 迁入 mixin
  - 目标：继续切分 `tests/unit/core/test_engine.py`，把初始化配置与扩展性能场景抽出到 mixin。
  - 执行：
    - 新建 `TestAnalysisEngineConfigurationTestMixin`、`TestAnalysisEnginePerformanceExtendedTestMixin`。
    - 将 `TestAnalysisEngineConfiguration`、`TestAnalysisEnginePerformanceExtended` 改为纯继承层。
    - 保持行为一致，仅做测试组织重构。
  - 验证结果：
    - `uv run ruff check --fix tests/unit/core/test_engine.py`（通过）
    - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
    - `uv run pytest tests/unit/core/test_engine.py -q`（14 passed）
    - `uv run pytest tests/unit/core/test_engine.py tests/benchmarks/test_large_file_performance.py tests/benchmarks/test_query_performance.py tests/integration/test_phase7_performance_integration.py tests/unit/core/test_performance.py tests/unit/performance/test_async_performance.py tests/unit/performance/test_mcp_performance.py -q`（78 passed, 3 skipped）
- 结论：本批次切片通过；未发现功能回归。继续下一队头任务（`TestAnalysisEngine*` 其余职责）。

- 2026-05-19 Tick: `test_engine.py` mixin 派生类收集问题修复
  - 触发理由：最近一次大规模 mixin 迁移后出现 `pytest` 0 tests collected，根因在于 `mixin` 类保留 `__test__ = False`，子类沿用该标记导致主文件测试全部被过滤。
  - 处理过程：
    - 检查 `tests/unit/core/test_engine.py` 所有 `Test*` 派生类是否需要覆盖 `__test__` 标记。
    - 为 `TestAnalysisEngine`、`TestUnified*`、`TestMockLanguagePlugin`、`TestAnalysisEngine*`、`TestAnalysisEnginePerformanceExtended`、`TestEngineManager*`、`TestEngineSecurityRegression` 全部补齐 `__test__ = True`。
    - 不更改测试实现与断言，仅修复可收集性元数据，保持功能无变更。
  - 验证链路：
    - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
    - `uv run pytest tests/unit/core/test_engine.py -q`（101 passed, 1 skipped）
    - `uv run pytest -q`（10417 passed, 32 skipped）
  - 结论：收集问题闭环处理完毕，队列可直接进入下一组 mixin 收敛（`test_engine.py` 剩余类边界整合），风险较低。

- 2026-05-19 Tick: test_engine 管理器职责切片迁移到独立文件
  - 目标: 继续 `test_engine.py` 队头收敛，按职责边界将 `test_engine_manager` 相关测试从主文件独立出来，降低单文件认知负担。
  - 动作:
    - 在 `tests/unit/core/test_engine_manager.py` 新建 `TestEngineManagerGetInstance`、`TestEngineManagerThreadSafety`、`TestEngineManagerResetInstances`、`TestEngineManagerEdgeCases`、`TestEngineSecurityRegression` 5 个类。
    - 各类继续继承既有 `tests/unit/core/_test_engine_test_mixin.py` 中的对应 mixin，不变更测试实现与断言。
    - 从 `tests/unit/core/test_engine.py` 移除上述管理器/安全回归壳类，剥离出专属文件并清理多余导入。
  - 验证:
    - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/test_engine_manager.py tests/unit/core/_test_engine_test_mixin.py`（通过）
    - `uv run pytest tests/unit/core/test_engine.py tests/unit/core/test_engine_manager.py -q`（101 passed, 1 skipped）
    - `uv run python -m tree_sitter_analyzer --file-health tests/unit/core/test_engine.py --format json`（`A(96.4)`，`test_engine.py` 无 `oversized_file` 异味）
    - `uv run python -m tree_sitter_analyzer --change-impact --format json`（低风险）
    - `uv run pytest -q`（10417 passed, 32 skipped）
  - 结果:
    - `test_engine.py` 已从单文件承载中移出 `EngineManager` 相关边界，健康分回升到 `A(96.4)`，风险下降。
    - 当前队列建议：继续检查是否有剩余的 `test_engine.py` 相关类可进一步按文件边界拆分；如无明显动作，则在下一步评估是否回到其他 top-5 oversized 文件。
