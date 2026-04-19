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
