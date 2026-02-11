# Code Map Intelligence - Requirements

## Vision
让 LLM 瞬间理解整个项目的代码地图，比 Neo4j 等工具更快、更准确。

## 现状分析
已有组件：
- `core/code_map.py`: ProjectCodeMap - 符号索引、依赖图、死代码检测、热点分析
- `graph/builder.py`: CodeGraphBuilder - NetworkX 图构建（CONTAINS + CALLS）
- `graph/queries.py`: get_callers, get_call_chain, find_definition, filter_nodes, focus_subgraph
- `graph/cross_file.py`: 跨文件调用解析
- `graph/export.py`: TOON/Mermaid 导出、call_flow 导出
- `graph/incremental.py`: mtime 增量更新

## 缺失的核心能力

### 1. 双向调用链追踪 (trace_call_flow)
- 输入一个函数名 → 输出完整的上下游调用树
- 上游：谁调用了我（递归到入口点）
- 下游：我调用了谁（递归到叶子节点）
- TOON 格式输出，LLM 一眼看懂

### 2. 修改影响分析 (impact_analysis)  
- 输入一个符号 → 输出所有受影响的文件和函数
- 传递性分析：A→B→C，改 C 则 A 和 B 都受影响
- 爆炸半径估算：受影响符号数、文件数、深度
- 风险分级：高/中/低

### 3. LLM 上下文捕获引擎 (gather_context)
- 输入一个查询（函数名/类名/关键词）→ 输出所有相关代码
- 智能收集：定义 + 调用者 + 被调用者 + import 关系
- Token 预算：在指定 token 限制内打包最相关的代码
- 防幻觉：确保 LLM 看到所有相关上下文

## 验收标准
- trace_call_flow: 输入函数名 → 1 秒内返回完整调用树
- impact_analysis: 输入符号名 → 列出所有受影响文件+函数+风险级别  
- gather_context: 输入查询 → 在 token 预算内返回最相关代码段
- 所有功能覆盖率 > 85%
- TOON 输出 < 原始代码 50% token
