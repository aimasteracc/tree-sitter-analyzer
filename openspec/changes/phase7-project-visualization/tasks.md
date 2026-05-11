# Phase 7 Tasks — 项目级可视化

## 切片 1: DependencyGraph（依赖图核心）
- [x] 1.1 创建 `tree_sitter_analyzer/project_graph.py` 模块骨架
- [x] 1.2 实现 ImportExtractor：提取 Python/JS/TS/Java 的 import 语句
- [x] 1.3 实现 DependencyGraph 构建（文件→imports 映射）
- [x] 1.4 实现循环依赖检测
- [x] 1.5 实现 BlastRadius 分析（正向/反向依赖遍历）
- [x] 1.6 实现缓存层（mtime + content hash）

## 切片 2: HealthScorer（健康评分）
- [x] 2.1 创建 `tree_sitter_analyzer/health_scorer.py`
- [x] 2.2 实现行数评分（SLOC-based）
- [x] 2.3 实现复杂度评分（AST 节点数 / 深度）
- [x] 2.4 实现依赖深度评分（依赖图集成）
- [x] 2.5 实现注释率评分
- [x] 2.6 实现综合加权评分（0-100 分制）

## 切片 3: 测试（TDD）
- [x] 3.1 先写 `tests/unit/test_project_graph.py` 所有测试用例
- [x] 3.2 先写 `tests/unit/test_health_scorer.py` 所有测试用例
- [x] 3.3 创建测试 fixtures（多语言示例项目）
- [x] 3.4 补完实现使所有测试通过（30/30）

## 切片 4: API 集成
- [x] 4.1 `api.py` 新增 `analyze_project_deps()` 函数
- [x] 4.2 `api.py` 新增 `analyze_health()` 函数
- [x] 4.3 `api.py` 新增 `analyze_blast_radius()` 函数
- [ ] 4.4 MCP server 注册新工具（可选，后续）

## 切片 5: 质量门禁
- [x] 5.1 ruff check 通过
- [x] 5.2 pytest -q 所有测试通过（30/30）
- [x] 5.3 test_mastery_scan.py --gates 通过（无新违规）
- [x] 5.4 净代码 ≥ 50 行确认（~700 行净代码）
