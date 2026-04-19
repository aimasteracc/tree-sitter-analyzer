# Findings — Product & Architecture Discussion Log

## 产品讨论记录 - Len-Comparison Anti-pattern - 2026-04-20

**调用**: /steve-jobs-perspective (office-hours)

**输入**: 3 candidates for next feature — Singleton Comparison, Star Import, Empty Sequence Comparison

**分析**:
1. Singleton Comparison → DON'T — already covered by `literal_boolean_comparison.py` (eq_true, eq_false, eq_none, ne_none)
2. Star Import → DON'T — already covered by `import_sanitizer.py` (wildcard_import detection at line 291)
3. Len-Comparison Anti-pattern → DO — genuine gap, not covered by any existing analyzer

**Len-Comparison Anti-pattern Analysis**:
- **聚焦即说不**: Solves real PEP 8 violation (Pylint C1801). `len(x) == 0` instead of `not x` is a common anti-pattern.
- **减法思维**: Minimal version is simple AST pattern matching on comparison_operator + len() call.
- **一句话定义**: Detect explicit `len()` comparisons where truthiness is more Pythonic/idiomatic.

**结论**: DO
**理由**: Fills a genuine gap, not covered, clean AST pattern, multi-language potential (Python len(), JS .length, Java .size(), Go len())

**功能评分** (>= 8/12 门槛):
- 独特性: 3 (无重叠)
- 需求度: 3 (PEP 8, Pylint C1801)
- 架构适配: 3 (标准 BaseAnalyzer)
- 实现成本: 3 (单 Sprint)
- **总分: 12/12** ✅

## 技术架构讨论记录 - Len-Comparison Anti-pattern - 2026-04-20

**调用**: /plan-eng-review

**输入**: Len-Comparison Anti-pattern Detector

**推荐方案**: 独立模块 (标准 BaseAnalyzer 模式)
- 检测模式: comparison_operator 包含 len() 调用
- 比较类型: `== 0`, `!= 0`, `> 0`, `>= 1`, `< 1`, `== 0`
- 语言支持: Python (len), JS/TS (.length), Java (.size()), Go (len)
- 修复建议: 使用 truthiness (`if x`, `if not x`)

**风险**: 低
**依赖**: 无新依赖

## 产品讨论记录 - Constant Boolean Operand Detector - 2026-04-20

**调用**: /steve-jobs-perspective (direct analysis)

**输入**: Boolean expression with constant non-boolean operands

**分析**:
- **聚焦即说不**: Solves real bugs. `if x == "a" or "b":` is always True because "b" is truthy. Classic Python pitfall (Pylint R0916/R1729).
- **减法思维**: Detect `or`/`and` operands that are non-boolean constants (strings, numbers, lists, dicts). Single AST pass.
- **一句话定义**: Detect non-boolean constant operands in boolean expressions that make conditions always true/false.

**结论**: DO
**理由**: Catches real bugs, no overlap with tautological_condition (which detects x==x), multi-language potential

**功能评分** (>= 8/12 门槛):
- 独特性: 3 (no overlap with tautological_condition which handles x==x)
- 需求度: 3 (Pylint R0916, real bugs, classic Python pitfall)
- 架构适配: 3 (standard BaseAnalyzer)
- 实现成本: 3 (single Sprint, Python-only MVP)
- **总分: 12/12** ✅

**调用**: /steve-jobs-perspective (office-hours)

**输入**: 3 candidates — Subprocess Security, YAML Unsafe Load, Redundant Super Call

**分析**:
1. Subprocess Security → DON'T — already covered by `security_scan.py` (line 229-237: subprocess shell=True detection)
2. YAML Unsafe Load → DON'T — already covered by `security_scan.py` (line 254-262: yaml.load without SafeLoader)
3. Redundant Super Call → DO — genuine gap, not covered by any existing analyzer

**Redundant Super Call Analysis**:
- **聚焦即说不**: Solves real code noise. `super().__init__()` in Python 3 when parent has no custom `__init__` is unnecessary ceremony.
- **减法思维**: Minimal version detects __init__ methods whose body is a single `super().__init__()` call (or `super().__init__(*args, **kwargs)`). Multi-language: Python super(), Java super(), JS super().
- **一句话定义**: Detect unnecessary super() calls that add no value beyond boilerplate.

**结论**: DO
**理由**: Fills a genuine gap, not covered, clear AST pattern, multi-language potential (Python super(), Java super(), JS super())

**功能评分** (>= 8/12 门槛):
- 独特性: 3 (无重叠, checked all 142 analyzers)
- 需求度: 2 (style issue, Pylint W0235, not a bug)
- 架构适配: 3 (标准 BaseAnalyzer)
- 实现成本: 3 (单 Sprint)
- **总分: 11/12** ✅

## 技术架构讨论记录 - Redundant Super Call Detector - 2026-04-20

**调用**: /plan-eng-review (architect agent)

**输入**: Redundant Super Call Detector

**推荐方案**: 独立模块 (标准 BaseAnalyzer 模式)

**两种检测类型**:
1. `redundant_super_init` (severity: low) — Constructor body contains ONLY super() call with zero additional statements
2. `passthrough_super_init` (severity: info) — Constructor params passed through to super() without transformation

**技术方案**:
- 新文件: `tree_sitter_analyzer/analysis/redundant_super.py`
- 新工具: `tree_sitter_analyzer/mcp/tools/redundant_super_tool.py`
- 模板: `missing_break.py` (cleanest template)
- Category: `correctness`
- 语言支持: Python (super()), Java (super()), JS/TS (super())

**AST patterns**:
- Python: `call_expression` → `attribute(__init__)` → `call_expression(super)`
- Java: `explicit_constructor_invocation` (super not this)
- JS/TS: `call_expression` → `identifier(super)`

**重叠**: `inheritance_quality.py` 已有 `empty_override` 检测, 但不专门针对构造函数

**风险**: 低
**依赖**: 无新依赖
