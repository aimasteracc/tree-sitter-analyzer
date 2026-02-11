# Architecture Refactor P1-P6 — Requirements

## 现状分析

十大架构师评审发现：
- `CodeMapResult` 有 33 个方法（God Object）
- `code_map.py` 有 2500+ 行（God File）
- `dict[str, Any]` 贯穿数据管道（无类型安全）
- core/ 直接 import languages/（依赖方向反转）
- graph/ 与 code_map 两套并行分析系统
- MCP 响应格式不统一
- 零可观测性

## 目标

将 v2 架构从"原型级"提升到"专家级"：
1. SRP：每个类/模块单一职责
2. DIP：core 不依赖 languages
3. 统一 IR：消除 dict[str, Any]
4. 统一引擎：消除双轨系统
5. API 标准化：MCP 响应一致
6. 可观测性：结构化日志

## 约束

- 所有 1088+ 现有测试必须继续通过
- 公开 API 向后兼容（`from tree_sitter_analyzer_v2.core.code_map import X` 不变）
- 每个 Phase 完成后独立可验证
