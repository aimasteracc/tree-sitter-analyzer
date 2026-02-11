# Code Map Intelligence - Design

## 架构：统一到 CodeMapResult

不创建新模块，而是增强现有 `CodeMapResult` + 在 `code_map.py` 中添加方法。

```
ProjectCodeMap.scan() → CodeMapResult
  ├── .trace_call_flow(name) → CallFlowResult
  ├── .impact_analysis(name) → ImpactResult  
  └── .gather_context(query, max_tokens) → ContextResult
```

## 数据流

```
Source Files → Tree-sitter Parse → Symbol Index + Call Graph
                                        ↓
                              trace_call_flow()   ← 双向 BFS
                              impact_analysis()   ← 逆向传递闭包
                              gather_context()    ← 符号匹配 + 图遍历 + 代码提取
```

## Phase 1: trace_call_flow

在 CodeMapResult 中利用已有的 graph/builder 构建的调用图，新增方法：

```python
@dataclass
class CallFlowResult:
    target: SymbolInfo
    callers: list[list[SymbolInfo]]   # 上游调用链（多条路径）
    callees: list[list[SymbolInfo]]   # 下游调用链（多条路径）
    
    def to_toon(self) -> str: ...
```

## Phase 2: impact_analysis

```python
@dataclass  
class ImpactResult:
    target: SymbolInfo
    affected_symbols: list[SymbolInfo]  # 所有受影响的符号
    affected_files: list[str]           # 受影响的文件
    blast_radius: int                   # 爆炸半径（受影响符号数）
    depth: int                          # 最大传递深度
    risk_level: str                     # "high" / "medium" / "low"
    
    def to_toon(self) -> str: ...
```

## Phase 3: gather_context

```python
@dataclass
class ContextResult:
    query: str
    matched_symbols: list[SymbolInfo]
    code_sections: list[CodeSection]    # 提取的代码段
    total_tokens: int
    
    def to_toon(self) -> str: ...

@dataclass
class CodeSection:
    file_path: str
    start_line: int
    end_line: int
    content: str
    relevance: str   # "definition" / "caller" / "callee" / "import"
```

## 实现策略
- 复用 graph/builder + graph/queries 的现有能力
- 在 code_map.py 中添加新方法和数据类
- TDD：先写测试，再实现
