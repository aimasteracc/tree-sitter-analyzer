# Phase 7: 项目级可视化

## 动机
tree-sitter-analyzer 目前在单文件分析上表现优秀（17 语言 AST 解析 + 查询），但缺少项目级别的代码上下文可视化能力。AI 工具需要理解"哪些文件互相依赖"、"这个改动会影响什么"才能做出更好的重构建议。

## 变更概要

新增三个项目级分析模块，全部基于现有 parser + query engine：

1. **DependencyGraph** — 跨文件依赖图生成（import/require/include 关系）
2. **HealthScorer** — 文件级健康评分（复杂度、依赖深度、测试覆盖率加权）
3. **BlastRadius** — 变更影响范围分析（给定文件改动，计算受影响文件集合）

## 设计决策

- 零新依赖：纯 Python stdlib + 现有 tree-sitter parser
- 懒加载：仅在调用时构建，不增加启动开销
- 增量友好：依赖图缓存基于文件 mtime + content hash
- 格式兼容：输出 JSON/TOON/YAML，与 OutputManager 统一

## 范围

### In Scope
- `tree_sitter_analyzer/project_graph.py` — DependencyGraph + BlastRadius
- `tree_sitter_analyzer/health_scorer.py` — HealthScorer
- `tests/unit/test_project_graph.py` — 依赖图单元测试
- `tests/unit/test_health_scorer.py` — 健康评分单元测试
- API 暴露：`api.py` 新增 `analyze_project_deps()` / `analyze_health()` / `analyze_blast_radius()`

### Out of Scope
- 可视化渲染（graphviz/D3）— 只输出结构化数据
- Git 历史分析 — 仅静态 AST 级别
- 循环依赖自动修复

## 竞品参考
- GitNexus: 知识图谱 + 爆炸半径（灵感来源，AST 精度更高）
- CodeFlow: 浏览器端正则 → 精确度不如 AST

## 质量目标
- 测试覆盖率 ≥ 90%
- 依赖图构建 < 2s for 100-file project
- 健康评分 5 个维度（行数、复杂度、依赖数、测试覆盖率、注释率）
