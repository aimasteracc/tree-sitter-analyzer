# Phase 3 Auto-Discovery: Quick Reference

**Status**: ✅ **FEASIBLE - Proceed with implementation**
**Date**: 2026-03-31
**Full Report**: [phase3-feasibility-report.md](./phase3-feasibility-report.md)

---

## TL;DR

**Question**: Can we auto-discover all grammar elements without manually maintaining wrapper lists?

**Answer**: **YES** - Using tree-sitter's Language API + structural analysis

---

## Key Findings

### 1. Grammar Access: ✅ No grammar.json needed

```python
import tree_sitter
import tree_sitter_python

lang = tree_sitter.Language(tree_sitter_python.language())

# All metadata accessible via API:
lang.node_kind_count        # 275 types (Python)
lang.node_kind_for_id(i)    # Get type name
lang.field_count            # 31 fields (Python)
lang.field_name_for_id(i)   # Get field name
```

**Advantage**: Automatically synced with tree-sitter versions

---

### 2. Wrapper Detection: ⚠️ Needs structural analysis

**Heuristic alone (names)**: Insufficient
```python
# Only finds 4 candidates, includes false positives
wrapper_patterns = ["decorated_", "with_clause", "annotated_"]
```

**Structural analysis**: Effective
```python
# Multi-feature scoring:
score = 0
score += 30 if has_definition_field else 0
score += 30 if has_decorator_field else 0
score += 20 if len(child_types) >= 2 else 0
score += 10 if avg_children >= 2 else 0
score += 10 if matches_name_pattern else 0

# Example: decorated_definition gets 70/100
```

**Validation on Python**: decorated_definition correctly identified
```
Child types:
  - decorator: 5 occurrences (wrapper metadata)
  - function_definition: 3 (wrapped content)
  - class_definition: 1 (wrapped content)

Field usage:
  - definition: 4 times (points to wrapped node)
```

---

### 3. Path Enumeration: ✅ Code sample-based

```python
def enumerate_paths(lang, code_samples, max_depth=3):
    # Parse samples, traverse AST, record (node_type, parent_path)
    # Result: All syntactic paths up to depth 3
```

**Example output** (Python, 189 bytes of code):
```
21 unique paths including:
  module > decorated_definition > function_definition
  module > decorated_definition > class_definition
  module > with_statement > with_clause
```

**Limitation**: Coverage depends on sample quality
**Solution**: Use existing golden corpus

---

### 4. Performance: ✅ Fast enough for CI

| Operation | Time | Memory |
|-----------|------|--------|
| Per language | < 10ms | < 5MB |
| 17 languages | < 200ms | < 50MB |

---

## Recommended Approach

### Phase 3 Strategy: Hybrid Analysis

1. **Runtime Introspection** (Language API)
   - Enumerate all node types
   - Get field definitions
   - No external grammar files needed

2. **Structural Analysis** (Code samples)
   - Parse golden corpus files
   - Analyze AST structure
   - Score wrapper candidates

3. **Heuristic Filtering** (Name patterns)
   - Supplement structural analysis
   - Filter obvious non-wrappers

4. **Golden Corpus Validation**
   - Verify against expected.json
   - Compare with existing plugins
   - Human review final list

---

## Implementation Plan

### Phase 3.1: Core Engine (Week 1)
- Extend `GrammarIntrospector` with structural analysis
- Implement `AutoDiscoveryEngine` class
- Unit tests on Python

### Phase 3.2: Multi-Language Validation (Week 2)
- Test on Python/Go/Java/C/C++ (already validated in Phase 2.5)
- Compare auto-discovery vs manual plugin configs
- Tune scoring thresholds

### Phase 3.3: Full Rollout (Week 3)
- Extend to remaining 12 languages
- CI integration
- Grammar change monitoring

---

## Success Metrics

- [ ] Auto-discovery success rate > 90% (17 languages)
- [ ] Wrapper identification accuracy > 85%
- [ ] New coverage gaps found > 20
- [ ] Manual config work reduced > 70%

---

## Prototype Scripts

### Run Prototypes

```bash
# Basic introspection (node types, fields, heuristic wrappers)
uv run python scripts/grammar_introspection_prototype.py

# Structural analysis (multi-feature scoring, validation)
uv run python scripts/grammar_structural_analysis.py
```

### Output Locations
- `scripts/grammar_introspection_prototype.py` - Language API exploration
- `scripts/grammar_structural_analysis.py` - Wrapper detection validation
- `docs/grammar-coverage/phase3-feasibility-report.md` - Full analysis

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Wrapper detection accuracy | Golden corpus validation + human review |
| Cross-language generalization | Incremental rollout (5 → 17 languages) |
| Grammar changes breaking detection | CI monitoring + version tracking |
| Sample coverage gaps | Expand golden corpus as needed |

---

## Decision: ✅ GO

**Confidence Level**: High (8/10)

**Rationale**:
- Technical feasibility proven
- Performance acceptable
- Integrates with existing infrastructure
- Clear success criteria
- Low-risk incremental approach

**Next Action**: Begin **Phase 3.1 implementation**

---

**For detailed analysis, see**: [phase3-feasibility-report.md](./phase3-feasibility-report.md)
