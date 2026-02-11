# Architecture Refactor — Design

## Phase 1: 消灭上帝对象

将 `code_map.py` 拆为 `core/code_map/` 包：

```
core/code_map/
  __init__.py          # 重导出所有公开名，保持向后兼容
  types.py             # 所有 dataclass (SymbolInfo, ModuleInfo, ...)
  result.py            # CodeMapResult (纯数据 + 属性 + find_symbol)
  scanner.py           # ProjectCodeMap (扫描引擎)
  parallel.py          # _parse_file_standalone, _get_thread_parsers
  call_index.py        # _build_call_index, _build_cross_file_calls
  toon_format.py       # _format_toon, _format_mermaid
  analyzers/
    __init__.py
    call_flow.py       # trace_call_flow
    impact.py          # impact_analysis
    context.py         # gather_context
    inheritance.py     # trace_inheritance, find_implementations
    refactoring.py     # suggest_refactorings
    smell.py           # detect_code_smells
    risk.py            # assess_change_risk
    test_audit.py      # audit_test_architecture
    snapshot.py        # token_economics, project_snapshot, symbol_index
    mermaid.py         # to_mermaid
```

### 关键设计决策

1. **CodeMapResult 只保留**：数据字段 + 计算属性 + find_symbol 系列
2. **每个分析器**：接收 `CodeMapResult` 作为参数的纯函数/类
3. **CodeMapResult 上保留委托方法**：调用分析器，保持 API 兼容
4. **__init__.py 重导出一切**：`from .types import *; from .result import *; ...`

## Phase 2: 类型化 IR

定义 `ParsedFunction`, `ParsedClass`, `ParsedImport`, `ParsedModule` 替代 `dict[str, Any]`。
语言解析器 `.parse()` 返回值不变（仍是 dict），但 `ModuleInfo` 字段改为类型化。
渐进式：先在 code_map 消费端做类型化包装，不动解析器返回值。

## Phase 3: 依赖反转

创建 `core/parser_registry.py`，语言解析器自注册。
`ProjectCodeMap` 从 registry 获取解析器，不直接 import languages/。

## Phase 4: 统一分析引擎

`graph/builder.py` 改为从 `CodeMapResult` 构建 NetworkX 图，而非重新解析文件。

## Phase 5: MCP API 标准化

统一返回格式 + 策略模式替换 if-elif 链。

## Phase 6: 结构化日志

`logging.getLogger(__name__)` 贯穿关键路径。
