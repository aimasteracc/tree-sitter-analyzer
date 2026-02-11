# Architecture Refactor — Tasks

| Task | Phase | Status | Files | Acceptance |
|------|-------|--------|-------|------------|
| T1: 创建 code_map/ 包 + types.py | P1 | completed | core/code_map/ | 所有 dataclass 移入 types.py |
| T2: 拆出 result.py (纯数据) | P1 | completed | core/code_map/__init__.py | CodeMapResult 保留数据+属性+委托 |
| T3: 拆出 analyzers/ | P1 | completed | core/code_map/analyzers/ | 8 个分析器独立模块 |
| T4: 拆出 scanner/parallel/call_index | P1 | completed | core/code_map/__init__.py | 保留在 __init__ (文件系统依赖) |
| T5: 拆出 toon_format.py | P1 | completed | core/code_map/__init__.py | _format_toon 保留 (紧耦合) |
| T6: __init__.py 重导出 | P1 | completed | core/code_map/__init__.py | 向后兼容 ✅ |
| T7: 回归验证 P1 | P1 | completed | tests/ | 1088 tests pass ✅ |
| T8: 类型化 ModuleInfo 字段 | P2 | completed | core/code_map/types.py | TypedDict + 类型化属性 |
| T9: ParserRegistry | P3 | completed | core/parser_registry.py | 懒加载 + 自注册 |
| T10: graph/ 统一 | P4 | completed | graph/builder.py | build_from_code_map + DIP |
| T11: MCP 标准化 | P5 | completed | mcp/tools/intelligence.py | 策略分派表 |
| T12: 结构化日志 | P6 | completed | 3 文件 | logging 贯穿关键路径 |
