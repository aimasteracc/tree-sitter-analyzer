# Function Cognitive Complexity Scorer

## Goal

计算每个函数的认知复杂度（Cognitive Complexity，SonarSource 规范），识别"最让人头疼的函数"并给出具体改进建议。

一句话定义: "告诉开发者哪些函数最难理解，为什么，以及如何简化"

## MVP Scope

### Sprint 1: Core Detection Engine (Python) — 目标 ~500 lines

**文件**:
- `tree_sitter_analyzer/analysis/cognitive_complexity.py` (~500 lines)

**完成内容**:
- `ComplexityIncrement` dataclass: 增量类型、行号、增量值、描述
- `FunctionComplexity` dataclass: 函数名、起始行、结束行、总复杂度、增量明细、评级
- `CognitiveComplexityResult` dataclass: 聚合结果
- `CognitiveComplexityAnalyzer` class:
  - `analyze_file(file_path)` → 检测单文件认知复杂度
  - `analyze_code(source_code, language)` → 检测代码片段
  - 内部维护 `nesting_level` 计数器
  - 识别函数边界 (function_definition, lambda)

**SonarSource 认知复杂度规则**:
- 基础增量 (+1): if, elif, else if, conditional operator (? :), switch, for, while, do while, catch, goto
- 嵌套增量 (+nesting_level): 嵌套的控制结构
- 不增加: else, 括号 (纯结构)
- 逻辑运算符序列: &&, || 序列只 +1（同一序列不重复计）

**测试**: `tests/unit/analysis/test_cognitive_complexity.py` (30+ tests)

### Sprint 2: Multi-Language Support (JS/TS, Java, Go) — 目标 ~300 lines

**文件**: 扩展 `cognitive_complexity.py`

**支持语言**:
- JavaScript/TypeScript: if, else if, switch, for, while, do, catch, try, ternary (? :), &&, ||
- Java: 同 JS/TS + assert 语句
- Go: if, else if, switch, select, for, range, defer/recover（Go 无 while）

**每种语言的 AST node mapping**:
```python
_LANGUAGE_NODES = {
    "python": {"if": "if_statement", "for": "for_statement", ...},
    "javascript": {"if": "if_statement", "for": "for_statement", ...},
    ...
}
```

**测试**: 扩展测试文件 (15+ tests per language)

### Sprint 3: MCP Tool Integration — 目标 ~200 lines

**文件**:
- `tree_sitter_analyzer/mcp/tools/cognitive_complexity_tool.py` (~200 lines)

**MCP Tool**:
- 名称: `cognitive_complexity`
- Toolset: analysis
- 输入: file_path, threshold (default 15), format (json/toon)
- 输出: 函数列表 + 复杂度分数 + 增量明细 + 改进建议

**测试**: `tests/unit/mcp/test_tools/test_cognitive_complexity_tool.py` (10+ tests)

## Technical Approach

**算法核心**: 嵌套深度计数器 (nesting_level)

```
walk_ast(node, nesting_level=0):
    if node is function/method:
        create new FunctionComplexity
        walk children with nesting_level=0
    if node is control_flow (if/for/while/switch/catch):
        add increment (+1 + nesting_level)
        walk children with nesting_level += 1
    if node is else/elif:
        add increment (+1, no nesting change)
        walk children with same nesting_level
    if node is logical_operator_sequence:
        add increment (+1, no nesting change)
```

**评级标准** (SonarSource 推荐):
- 1-5: 简单 (Simple)
- 6-10: 中等 (Moderate)
- 11-20: 复杂 (Complex)
- 21-50: 非常复杂 (Very Complex)
- 50+: 极端复杂 (Extreme)

**依赖模块**: tree-sitter language modules (已有)
