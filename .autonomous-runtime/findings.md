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
- 风险低：本轮再次收口后完成验证
  - `uv run pytest tests/unit/core/test_engine.py -q`（88 passed, 1 skipped）
  - `uv run pytest -q`（10404 passed, 32 skipped）
  - `--file-health` 仍为 `D(68.9)`，`oversized_file` 关键异味持续（1573 行），继续执行下一组切片：`TestUnifiedAnalysisEnginePluginManagement` / `CacheManagement` / `LanguageDetection`。
