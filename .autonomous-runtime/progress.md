# progress.md — 开发进度日志

> 每条记录一个 Sprint 的操作和结果

## 2026-05-11: 初始设置（手动）

- 安装 Matt Pocock 13 Skills + gstack
- unittest.TestCase → pytest 迁移（148/148）
- TODO items: Ruby visibility + JS exports
- 死代码: compat.py 删除
- 28 补充测试 + 4 slow markers
- pytest.ini 移除 -n auto + --cov
- 增量解析 + test_mastery_scan.py
- ruff 全面清理
- 8194 测试, 0 errors, 100% 源模块覆盖

## 2026-05-11: DeepSeek TUI 自动化设置

- loop.sh + status.sh（对标 Claude Code 版本）
- ds-automation.yaml（DS TUI 原生每小时 schedule）
- task_plan.md + findings.md + progress.md
- 7 Phase 中 6 个已完成, 2 个待开发

## 2026-05-11: Phase 7 完成 — 项目级可视化

- project_graph.py: DependencyGraph + BlastRadius（依赖图+爆炸半径分析）
- health_scorer.py: HealthScorer（5维加权健康评分 0-100分制）
- api.py: analyze_project_deps() / analyze_health() / analyze_blast_radius()
- 测试: 30/30 通过（test_project_graph.py + test_health_scorer.py）
- 零新依赖，全部基于现有 tree-sitter parser
- 质量门禁: ruff 通过, pytest 全部通过, mastery scan 无新违规

## 2026-05-12: Phase 8 Slice 1 — MCP 测试文件拆分

- 拆分 test_mcp_fd_rg_tools.py (5633行) → 9 个文件，按源模块分组
  (fd_rg_utils, list_files_p1-p4, search_content_p1-p2, find_and_grep_p1-p2)
- 拆分 test_fd_rg_utils.py (1480行) → 2 个文件，按类边界拆分
- 删除 2 个 oversized 文件，新增 11 个聚焦文件
- ruff --fix: 消除 29 个未使用导入
- 验证: 246 个拆分测试全部通过
- mastery scan: oversized 22 → 20
- Git commit: 357cec3

## 2026-05-12: Phase 8 Slice 2 — 低密度测试修复

- 5 个低断言密度文件全部修复至 density ≥ 1.0:
  - test_javascript_plugin_coverage_boost.py: 删除空文件
  - test_conftest_query.py: +7 测试函数 → density 2.00
  - test_tree_sitter_compat_coverage_boost.py: +2 断言 → density 1.00
  - test_logging.py: +11 断言 → density 1.00
  - test_logging_coverage.py: +16 断言 → density 1.00
- 修复 2 个预存 ruff B017 违规
- 质量门禁: ruff ✓, pytest 141 passed ✓, mastery scan ALL GATES PASSED
- low-density violation: 5 → 0
- Git commit: e6a6785 (+115 -3, 112 行净代码)

---

## 下一步

Phase 8 Slice 3+: 拆分 11 个 oversized 测试文件（> 1200 lines）

## 2026-05-18: 自主运行层 tick 入口修复

- 新增 `.autonomous-runtime/tick.sh`，作为 5 分钟 heartbeat 的幂等入口:
  检查 loop、尝试启动、sleep 1 复核、写 `last-tick.json`、输出单行状态。
- 修正 `status.sh` 的健康语义: Codex heartbeat 是真正 24/7 开发引擎，
  `loop.sh` 只作为辅助探针，避免后台进程被桌面执行器清理时误报系统已停。
- 更新 `ds-automation.yaml`，要求自动化只调用 tick 入口，不再手写 nohup。
- 验证: `bash -n` 通过，`tick.sh` 真实运行可写 tick 状态，
  `status.sh` 显示最近 heartbeat 在线。

## 2026-05-18: 自主状态 JSON 输出

- 为 `.autonomous-runtime/status.sh` 增加 `--json` 模式，输出 loop 探针、
  Codex heartbeat、OpenSpec 待办、最近 Python 变更和机器可读结论。
- 保留默认人类可读输出，方便人工检查；心跳可用 JSON 模式决定是否通知用户。
- 验证: `bash -n` 通过，`status.sh --json | uv run python -m json.tool` 通过。

## 2026-05-18: YAML 元数据测试结构化重构

- 目标: 继续 Phase 8 Slice 3，降低测试可维护性风险，优先处理 `test_yaml_element_metadata_properties.py`。
- 动作:
  - 新增 `tests/unit/languages/_test_yaml_element_metadata_properties_helpers.py`，提取 `test_property_4_element_metadata_line_numbers` 的公共解析/断言逻辑；主测试改为调用 helper。
  - 本次继续重构：
    - 将 `test_property_4_element_metadata_mixed_structures` 改为结构化 helper 检查；
    - 将 `test_property_4_element_metadata_raw_text_accuracy` 改为共享 helper 检查；
    - 新增 `assert_raw_text_fields`、`assert_raw_text_matches_source`、`assert_mapping_raw_text_contains_key`、`assert_scalar_raw_text_non_empty`。
- 验证: 
  - `uv run pytest tests/unit/languages/test_yaml_element_metadata_properties.py -q`（6 passed）
  - `uv run python -m tree_sitter_analyzer tests/unit/languages/test_yaml_element_metadata_properties.py --file-health --format json`
- 结果:
  - 全量回归: `10417 passed, 32 skipped`（上游记录）
  - 本文件健康评分: 从 `C(73.8, 5 warnings)` 提升到 `B(81.7, 3 warnings)`；
    - 剩余主要 smell: `deep_nesting`（line 77）与两个长方法（with_comments、consistency）。

## 2026-05-18: YAML 元数据测试结构化重构（收口）

- 目标: 继续清理 `tests/unit/languages/test_yaml_element_metadata_properties.py` 的最后一类结构异味。
- 动作:
  - 在 helper 模块补齐 `assert_sequence_metadata`，将 sequence 断言从主测试中抽离。
  - 继续降低策略复杂度，新增 `_yaml_scalar_value` 降低 `deep_nesting`。
  - 通过 `ruff check --fix` + import reorder 校验。
- 验证:
  - `uv run pytest tests/unit/languages/test_yaml_element_metadata_properties.py -q`（6 passed）
  - `uv run python -m tree_sitter_analyzer tests/unit/languages/test_yaml_element_metadata_properties.py --file-health --format json`
  - `uv run pytest -q`（10417 passed, 32 skipped）
- 结果:
  - 文件级健康评分回到 `A(90.9)`，`code_smells = 0`。
  - 变更文件:
    - `tests/unit/languages/_test_yaml_element_metadata_properties_helpers.py`
    - `tests/unit/languages/test_yaml_element_metadata_properties.py`

## 2026-05-18: test_engine.py 可维护性切片（持续）

- 目标: 继续 Phase 8 Slice 3，降低 `tests/unit/core/test_engine.py` 的文件异味（`D 68.2`）。
- 动作:
  - 新增 `tests/unit/core/_test_engine_test_mixin.py`，抽离 `TestAnalysisEngine` 中的 8 个测试为 mixin。
  - `tests/unit/core/test_engine.py` 的 `TestAnalysisEngine` 继承该 mixin，行数从 1707 降至 1605，单次改动集中在初始化/文件分析相关测试块。
- 验证:
  - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run pytest tests/unit/core/test_engine.py -q`（93 passed, 1 skipped）
  - `uv run pytest -q`（10409 passed, 32 skipped）
- 结果:
  - `test_engine.py` 文件健康仍为 `D(68.7)`，但已稳定：拆分后的 mixin 文件健康 `A(96.7)`，无新增警告。
  - 风险保持低，后续下一步可继续按建议继续迁移 `TestUnifiedAnalysisEngine*` 责任片段。

## 2026-05-18: test_engine.py 可维护性切片（继续）

- 目标: 继续 `TestUnifiedAnalysisEngineInit` 责任拆分，降低类内测试混杂。
- 动作:
  - 在 `tests/unit/core/_test_engine_test_mixin.py` 新增 `TestUnifiedAnalysisEngineInitTestMixin`，抽离 5 个 `TestUnifiedAnalysisEngineInit` 测试。
  - 修改 `tests/unit/core/test_engine.py`，让 `TestUnifiedAnalysisEngineInit` 继承该 mixin，并保留生命周期清理钩子。
- 验证:
  - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run pytest tests/unit/core/test_engine.py -q`（88 passed, 1 skipped）
  - `uv run pytest -q`（10404 passed, 32 skipped）
  - `uv run python -m tree_sitter_analyzer --file-health --format json tests/unit/core/test_engine.py`（`D(68.9)`；`oversized_file` 与 `deep_nesting` 仍在，继续切片）
- 结果:
  - `test_engine.py` 行数继续下降到约 1573 行；
  - `TestUnifiedAnalysisEngineInit` 抽离成功，下一步继续沿 `refactor` 建议处理 `PluginManagement`、`CacheManagement`、`LanguageDetection`。

## 2026-05-18: test_engine.py 可维护性切片（继续）

- 目标: 继续 `TestUnifiedAnalysisEngine*` 的拆分，降低 `test_engine.py` 的维护负担。
- 动作:
  - 在 `tests/unit/core/_test_engine_test_mixin.py` 新增 `TestUnifiedAnalysisEnginePluginManagementTestMixin`，抽离 3 个 `TestUnifiedAnalysisEnginePluginManagement` 测试。
  - 将 `tests/unit/core/test_engine.py` 的 `TestUnifiedAnalysisEnginePluginManagement` 改造为继承该 mixin。
- 验证:
  - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run pytest tests/unit/core/test_engine.py -q`（85 passed, 1 skipped）
  - `uv run pytest -q`（10401 passed, 32 skipped）
  - `uv run python -m tree_sitter_analyzer --file-health tests/unit/core/test_engine.py`（`D(69.0)`，`oversized_file` 与 `deep_nesting` 仍在）
  - `uv run python -m tree_sitter_analyzer --change-impact --format json`（变更影响仅在上述两个文件，默认队列级验证仍为 `uv run pytest -q`）
- 结果:
  - `test_engine.py` 约 1554 行，较前已继续收缩。
  - `TestUnifiedAnalysisEnginePluginManagement` 的职责更内聚，未引入新风险。
  - 下一步建议继续迁移 `TestUnifiedAnalysisEngineCacheManagement` 与 `TestUnifiedAnalysisEngineLanguageDetection`。

## 2026-05-18: test_engine.py 可维护性切片（继续）

- 目标: 继续 `TestUnifiedAnalysisEngine*` 的切片，完成 `CacheManagement` 与 `LanguageDetection` 的抽离。
- 动作:
  - 在 `tests/unit/core/_test_engine_test_mixin.py` 新增 `TestUnifiedAnalysisEngineCacheManagementTestMixin` 与 `TestUnifiedAnalysisEngineLanguageDetectionTestMixin`，将对应 8 个测试抽出到 mixin。
  - `tests/unit/core/test_engine.py` 的 `TestUnifiedAnalysisEngineCacheManagement` 与 `TestUnifiedAnalysisEngineLanguageDetection` 改为继承各自 mixin，仅保留清理钩子。
- 验证:
  - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过，1 个自动修复）
  - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run pytest tests/unit/core/test_engine.py -q`（78 passed, 1 skipped）
  - `uv run python -m tree_sitter_analyzer --file-health tests/unit/core/test_engine.py --format json`（`D(69.2)`, `oversized_file` + `deep_nesting`）
  - `uv run python -m tree_sitter_analyzer --change-impact --format json`（低风险，集中影响 2 个更改文件）
  - `uv run pytest -q`（10426 passed, 32 skipped）
- 结果:
  - 两组测试从主文件成功抽离，`test_engine.py` 继续收缩至约 1505 行。
  - 风险继续受控：变更未触发回归，继续沿 `refactoring_suggestions` 逐步拆解 `oversized_file`。

## 2026-05-18: test_engine.py 可维护性切片（继续）

- 目标: 继续 `TestUnifiedAnalysisEngine*` 责任拆分，抽离 `TestUnifiedAnalysisEngineAnalysis`。
- 动作:
  - 新增 `TestUnifiedAnalysisEngineAnalysisTestMixin`，将 10 个 `TestUnifiedAnalysisEngineAnalysis` 测试迁移到 mixin 文件。
  - `tests/unit/core/test_engine.py` 的 `TestUnifiedAnalysisEngineAnalysis` 改为继承 mixin，仅保留 `teardown_class`。
- 验证:
  - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run pytest tests/unit/core/test_engine.py -q`（69 passed, 1 skipped）
  - `uv run python -m tree_sitter_analyzer tests/unit/core/test_engine.py --file-health --format json`（`C(74.3)`，`oversized_file` 与 `deep_nesting`）
  - `uv run python -m tree_sitter_analyzer --change-impact --format json`（低风险，变更仅在 2 个目标文件）
  - `uv run pytest -q`（10385 passed, 32 skipped）
- 结果:
  - 文件长度继续下降至约 1362 行，`test_engine.py` 文件健康提升到 `C(74.3)`。
  - 下一步继续按同一队列拆 `TestUnifiedAnalysisEngineSecurity` 与 `TestUnifiedAnalysisEngineQueries`。

## 2026-05-18: test_engine.py 可维护性切片（继续）

- 目标: 继续 `TestUnifiedAnalysisEngine*` 责任拆分，抽离 `TestUnifiedAnalysisEngineSecurity` 与 `TestUnifiedAnalysisEngineQueries`。
- 动作:
  - 在 `tests/unit/core/_test_engine_test_mixin.py` 新增 `TestUnifiedAnalysisEngineSecurityTestMixin` 与 `TestUnifiedAnalysisEngineQueriesTestMixin`。
  - 将 `TestUnifiedAnalysisEngineSecurity` 与 `TestUnifiedAnalysisEngineQueries` 在 `tests/unit/core/test_engine.py` 改为继承对应 mixin。
- 验证:
  - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
  - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
  - `uv run pytest tests/unit/core/test_engine.py -q`（64 passed, 1 skipped）
  - `uv run python -m tree_sitter_analyzer tests/unit/core/test_engine.py --file-health --format json`（`C(75.1)`，仍有 `oversized_file` + `deep_nesting`）
  - `uv run python -m tree_sitter_analyzer --change-impact --format json`（低风险，影响文件 1 个 + 2 个改动）
  - `uv run pytest -q`（10380 passed, 32 skipped）
- 结果:
  - `test_engine.py` 进一步收缩并降低维护复杂度，`Security`/`Queries` 责任分离完成。
  - `test_engine.py` 味道仍是 oversized_file，属于可继续执行的下一步（`TestUnifiedAnalysisEnginePerformance`、`Properties` 等组）。

## 2026-05-18: test_engine.py 可维护性切片（继续）

- 目标: 继续 `TestUnifiedAnalysisEngine*` 责任拆分，抽离 `TestUnifiedAnalysisEnginePerformance` 与 `TestUnifiedAnalysisEngineProperties`。
- 动作:
  - 在 `tests/unit/core/_test_engine_test_mixin.py` 新增
    `TestUnifiedAnalysisEnginePerformanceTestMixin` 与 `TestUnifiedAnalysisEnginePropertiesTestMixin`。
  - 将 `TestUnifiedAnalysisEnginePerformance` 与 `TestUnifiedAnalysisEngineProperties`
    在 `tests/unit/core/test_engine.py` 改为继承对应 mixin，仅保留 `teardown_class`。
- 验证:
  - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run pytest tests/unit/core/test_engine.py -q`（60 passed, 1 skipped）
  - `uv run pytest -q`（10376 passed, 32 skipped）
  - `uv run python -m tree_sitter_analyzer tests/unit/core/test_engine.py --file-health --format json`（`C(75.0)`，仍有 `oversized_file` 与 `deep_nesting`）
  - `uv run python -m tree_sitter_analyzer --change-impact --format json`（低风险，变更 2 个文件）
- 结果:
- `test_engine.py` 继续收缩并保持低风险；当前主异味仍是 `oversized_file`，下一步建议优先处理 `TestUnifiedAnalysisEngineCleanup` 与深度嵌套点。

## 2026-05-18: test_engine.py 可维护性切片（继续）

- 目标: 继续 `tests/unit/core/test_engine.py` 的责任切片，收敛 `TestMockLanguagePlugin`。
- 动作:
  - 新增 `TestMockLanguagePluginTestMixin` 到 `tests/unit/core/_test_engine_test_mixin.py`，抽离 `TestMockLanguagePlugin` 的 5 个用例（初始化、语言名、扩展名、extractor、analyze_file）。
  - `tests/unit/core/test_engine.py` 的 `TestMockLanguagePlugin` 改为继承 `TestMockLanguagePluginTestMixin`。
- 验证:
  - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
  - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
  - `uv run pytest tests/unit/core/test_engine.py -q`
  - `uv run python -m tree_sitter_analyzer tests/unit/core/test_engine.py --file-health --format json`
  - `uv run python -m tree_sitter_analyzer --change-impact --format json`
- 结果:
  - 继续保持低风险：`test_engine.py` 行数略降，类边界更清晰。
  - `test_engine.py` 仍为 `oversized_file`，但持续朝切片方向推进。

## 2026-05-18: test_engine.py 可维护性切片（继续）

- 目标: 继续 `TestUnifiedAnalysisEngine*` 的责任切片，处理 `TestUnifiedAnalysisEngineCleanup`。
- 动作:
  - 新增 `TestUnifiedAnalysisEngineCleanupTestMixin`，将 `test_cleanup` 从 `TestUnifiedAnalysisEngineCleanup` 迁出到 mixin。
  - `tests/unit/core/test_engine.py` 的 `TestUnifiedAnalysisEngineCleanup` 改为继承 `TestUnifiedAnalysisEngineCleanupTestMixin`，仅保留 `teardown_class`。
- 验证:
  - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
  - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
  - `uv run pytest tests/unit/core/test_engine.py -q`
- 结果:
  - `TestUnifiedAnalysisEngineCleanup` 已并入 mixin 体系，`test_engine.py` 继续沿切片目标前进。

## 2026-05-19: test_engine.py 可维护性切片（unification 组）

- 目标: 继续压缩 `tests/unit/core/test_engine.py`，处理 `test_engine_unification.py` 来源的同步 API/兼容性测试组。
- 动作:
  - 在 `tests/unit/core/_test_engine_test_mixin.py` 新增 6 个 unification mixin:
    - `TestUnifiedEngineSingletonTestMixin`
    - `TestUnifiedEngineSyncAnalysisTestMixin`
    - `TestUnifiedEngineAnalyzeCodeTestMixin`
    - `TestUnifiedEngineQueryExecutionTestMixin`
    - `TestUnifiedEngineNonexistentFileTestMixin`
    - `TestUnifiedEngineCompatibilityPropertiesTestMixin`
  - `tests/unit/core/test_engine.py` 中对应 6 个类改为继承 mixin，主文件仅保留类边界。
- 验证:
  - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过，自动修复导入）
  - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`（通过）
  - `uv run pytest tests/unit/core/test_engine.py -q`（32 passed）
  - `uv run python -m tree_sitter_analyzer tests/unit/core/test_engine.py --file-health --format json`（`C(77.0)`，971 lines，剩余 `oversized_file` 与 `deep_nesting`）
  - `uv run python -m tree_sitter_analyzer --change-impact --format json`（low risk，2 个变更文件，1 个受影响文件）
  - `uv run pytest -q`（10348 passed, 31 skipped，约 27s）
- 结果:
  - `test_engine.py` 从 1031 行降到 971 行，健康分从 `C(76.7)` 提升到 `C(77.0)`。
  - 队头仍是 `test_engine.py` oversized 文件，下一步继续迁移 `TestAnalysisEnginePublicAPI` / `Concurrency` / `EdgeCases` 等剩余主文件测试组。

## 2026-05-19: test_engine.py 可维护性切片（继续）

- 目标: 继续收口 `test_engine.py` 剩余职责组，降低主文件混合度。
- 动作:
  - 将 `TestAnalysisEnginePublicAPI`、`TestAnalysisEngineConcurrency`、`TestAnalysisEngineEdgeCases` 的 9 个测试体抽离到
    `tests/unit/core/_test_engine_test_mixin.py` 对应的 `TestAnalysisEnginePublicAPITestMixin`、`TestAnalysisEngineConcurrencyTestMixin`、`TestAnalysisEngineEdgeCasesTestMixin`。
  - `tests/unit/core/test_engine.py` 对应类改为继承 mixin（保留类边界，移除重复实现）。
  - 为满足变更契约，补充 `CLAUDE.md` 的验证元数据字段（`verification_command` / `pytest_required` / `--change-impact --format json`）。
- 验证:
  - `uv run ruff check --fix tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
  - `uv run ruff check tests/unit/core/test_engine.py tests/unit/core/_test_engine_test_mixin.py`
  - `uv run pytest tests/unit/core/test_engine.py -q`（20 passed）
  - `uv run pytest tests/unit/core/_test_engine_test_mixin.py -q`（若未单独运行则不影响队列，见下）
  - `uv run pytest tests/unit/core/test_engine.py tests/benchmarks/test_large_file_performance.py tests/benchmarks/test_query_performance.py tests/integration/test_phase7_performance_integration.py tests/unit/core/test_performance.py tests/unit/performance/test_async_performance.py tests/unit/performance/test_mcp_performance.py -q`（84 passed, 3 skipped）
  - `uv run pytest -q`（10336 passed, 31 skipped）
  - `uv run pytest tests/unit/test_agent_contracts.py::test_agent_docs_require_change_impact_verification_command -q`（通过）
  - `uv run python -m tree_sitter_analyzer --file-health tests/unit/core/test_engine.py --format json`
  - `uv run python -m tree_sitter_analyzer --change-impact --format json`
- 结果:
  - 本轮队头切片闭环完成，`test_engine.py` 对应职责面继续收敛且无测试回归。
  - 风险保持低，继续沿同一 queue 处理下一组职责（例如 `TestAnalysisEngineAnalyze*` / `TestAnalysisEngineProperties`）。
