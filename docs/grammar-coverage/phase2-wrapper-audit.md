# Phase 2 Wrapper Node Audit Report

**Date:** 2025-02-28
**Agent:** Agent 3 (Phase 2 Preliminary Investigation)
**Scope:** 7 high-risk languages with wrapper nodes (decorators, attributes, modifiers)

## Executive Summary

Audited 7 languages for wrapper node handling. Found **4 languages with missing wrapper support** and **3 languages with proper handling**. Total estimated fix effort: **3-4 hours**.

## Detailed Audit Results

### 1. TypeScript - ❌ MISSING WRAPPER SUPPORT

**Wrapper nodes:** `decorator`, `decorator_call_expression`

**Plugin status:** ❌ NOT HANDLED
- `container_node_types` (line 212-229) does NOT include `decorator` or `decorator_call_expression`
- Traversal will skip decorated functions/classes if decorator is the parent node

**Corpus examples:**
- Line 389: `@sealed` decorator on class
- Line 391: `@required` decorator on property
- Line 394: `@log` decorator on method

**Fix required:** Add decorator nodes to `container_node_types`

**Estimated effort:** 30 minutes

**Fix location:** `tree_sitter_analyzer/languages/typescript_plugin.py:212-229`

```python
# Add these to container_node_types:
"decorator",
"decorator_call_expression",
```

---

### 2. Rust - ✅ PROPERLY HANDLED

**Wrapper nodes:** `attribute_item`, `inner_attribute_item`

**Plugin status:** ✅ HANDLED
- Rust plugin uses `_traverse_and_extract()` recursive traversal (line 358-371)
- No `container_node_types` whitelist, so ALL nodes are traversed
- Attributes are explicitly extracted via `extract_attributes()` method (line 168-190)

**Corpus examples:**
- Line 59: `#[derive(Debug, Clone)]` on struct
- Line 67: `#[derive(Debug)]` on enum
- Line 74: `#[derive(Debug, Clone)]` on struct
- Line 90: `#[derive(Debug, Clone, PartialEq)]` on enum
- Line 98: `#[derive(Debug)]` on type

**Fix required:** None

**Estimated effort:** 0

---

### 3. Ruby - ❌ MISSING WRAPPER SUPPORT

**Wrapper nodes:** `visibility_modifier` (private, protected, public keywords)

**Plugin status:** ❌ PARTIALLY HANDLED
- Ruby uses iterative traversal without container node filtering (line 214-244)
- Visibility modifiers are parsed but NOT explicitly extracted as standalone elements
- Methods after `private`/`protected` lines should inherit visibility but this logic is missing

**Corpus examples:**
- Line 126: `private` modifier affecting subsequent methods
- Line 133: `protected` modifier affecting subsequent methods
- Line 181: `private_class_method :new`

**Fix required:**
1. Add visibility state tracking during traversal
2. Apply visibility to methods parsed after modifier declaration
3. Optionally extract visibility modifier nodes as Expression elements

**Estimated effort:** 1-2 hours (complex state tracking required)

**Fix location:** `tree_sitter_analyzer/languages/ruby_plugin.py:196-245`

---

### 4. Scala - ❌ MISSING WRAPPER SUPPORT

**Wrapper nodes:** `annotation` (e.g., `@tailrec`, `@deprecated`)

**Plugin status:** ❌ NOT HANDLED
- Scala plugin uses recursive `_traverse_and_extract()` (line 183-196)
- No annotation extraction logic
- Annotations attached to functions/classes are ignored

**Corpus examples:**
- Line 225: `@scala.annotation.tailrec` on function

**Fix required:** Add annotation extraction similar to Rust attributes

**Estimated effort:** 30-45 minutes

**Fix location:** `tree_sitter_analyzer/languages/scala_plugin.py:183-196`

```python
# Add extractor for annotations
def extract_annotations(self, tree, source_code) -> list[Expression]:
    extractors = {"annotation": self._extract_annotation}
    # ... implementation
```

---

### 5. C# - ❌ MISSING WRAPPER SUPPORT

**Wrapper nodes:** `attribute_list` (e.g., `[HttpGet]`, `[Authorize]`)

**Plugin status:** ⚠️ PARTIALLY HANDLED
- Plugin HAS `_extract_attributes()` method (line 157-192)
- Attributes are extracted and attached to elements via `annotations` field
- BUT: Attributes are only extracted for immediate parent elements
- If attribute is on a wrapper node that wraps the declaration, it might be missed

**Corpus examples:** No C# golden corpus exists yet

**Fix required:**
1. Verify attribute extraction works with all nesting scenarios
2. Optionally extract attribute_list as standalone Expression elements
3. Add `attribute_list` to container traversal if using whitelist

**Estimated effort:** 30 minutes (verification + optional extraction)

**Fix location:** `tree_sitter_analyzer/languages/csharp_plugin.py:157-192, 232-249`

---

### 6. Kotlin - ✅ PROPERLY HANDLED

**Wrapper nodes:** `annotation` (e.g., `@JvmStatic`, `@Deprecated`)

**Plugin status:** ✅ HANDLED
- Plugin has `extract_annotated_expressions()` method (line 581-627)
- Extracts `annotated_expression` nodes as Expression elements
- Recursive traversal with no container whitelist (line 161-174)

**Corpus examples:** Kotlin corpus exists (line references available in code audit)

**Fix required:** None

**Estimated effort:** 0

---

### 7. Swift - ✅ PROPERLY HANDLED

**Wrapper nodes:** `modifiers` (e.g., `@available`, `@objc`, access control)

**Plugin status:** ✅ HANDLED
- Plugin has `_extract_modifiers()` method (line 616-625)
- Modifiers are extracted and attached to functions/classes/properties
- Recursive traversal with no container whitelist (line 159-175)

**Corpus examples:** Swift corpus exists with modifiers on classes/functions

**Fix required:** None

**Estimated effort:** 0

---

## Summary Table

| Language   | Status | Wrapper Nodes | Golden Corpus | Fix Effort | Priority |
|------------|--------|---------------|---------------|------------|----------|
| TypeScript | ❌ MISSING | decorator, decorator_call_expression | ✅ Examples found | 30 min | HIGH |
| Rust       | ✅ OK | attribute_item | ✅ Examples found | 0 | N/A |
| Ruby       | ❌ MISSING | visibility_modifier | ✅ Examples found | 1-2h | HIGH |
| Scala      | ❌ MISSING | annotation | ✅ Examples found | 45 min | MEDIUM |
| C#         | ⚠️ PARTIAL | attribute_list | ❌ No corpus | 30 min | MEDIUM |
| Kotlin     | ✅ OK | annotation | ✅ Corpus exists | 0 | N/A |
| Swift      | ✅ OK | modifiers | ✅ Corpus exists | 0 | N/A |

**Total languages with issues:** 4 (TypeScript, Ruby, Scala, C#)
**Total fix effort:** 3-4 hours
**Recommended approach:** Fix TypeScript first (quick win), then Ruby (most complex), then Scala and C#

---

## Implementation Plan

### Phase 2.1: Quick Wins (TypeScript + Scala)
**Effort:** 1-1.5 hours
**Impact:** 2 languages fixed

1. **TypeScript:** Add decorator nodes to container_node_types
2. **Scala:** Add annotation extraction method
3. Verify with golden corpus tests

### Phase 2.2: Complex Fix (Ruby)
**Effort:** 1-2 hours
**Impact:** 1 language fixed

1. Add visibility state machine during traversal
2. Update `_extract_method_element()` to use inherited visibility
3. Test with corpus_ruby.rb lines 126-136

### Phase 2.3: Verification (C#)
**Effort:** 30 minutes
**Impact:** 1 language verified/fixed

1. Create C# golden corpus with attributes
2. Verify attribute extraction works in all nesting scenarios
3. Add attribute_list to container nodes if needed

---

## Validation Strategy

For each fixed language:

1. **Unit test:** Create test with wrapper node wrapping target element
2. **Golden corpus:** Verify existing corpus examples are now extracted
3. **Grammar coverage:** Run coverage validator to confirm wrapper nodes are green
4. **Regression:** Run full test suite to ensure no breakage

---

## Next Steps

1. Proceed to Phase 2 implementation
2. Start with TypeScript (easiest fix)
3. Create wrapper node test fixtures for each language
4. Update grammar coverage validation after fixes

---

## Technical Notes

### Container Node Pattern

**Problem:** Iterative traversal with `container_node_types` whitelist can skip wrapper nodes if they're not in the whitelist.

**Example:**
```
decorator (@Component)  ← wrapper node NOT in container_node_types
  └─ class_declaration (MyClass)  ← target node, SKIPPED because parent not in whitelist
```

**Solution:** Add wrapper nodes to `container_node_types`:
```python
container_node_types = {
    "program",
    "class_body",
    "decorator",  # ← ADD WRAPPER NODES
    "attribute_item",
    # ...
}
```

### Recursive vs Iterative Traversal

**Recursive:** Visits ALL nodes (Rust, Kotlin, Swift, Scala)
- ✅ No container whitelist needed
- ✅ Naturally handles wrapper nodes
- ❌ Stack overflow risk on deep ASTs

**Iterative with whitelist:** Skips non-container nodes (TypeScript, Go)
- ✅ Safe for deep ASTs
- ✅ Performance optimization
- ❌ Must explicitly list all wrapper/container nodes

**Recommendation:** Prefer recursive traversal for new plugins; add wrapper nodes to whitelist for existing iterative plugins.

---

## References

- TypeScript plugin: `tree_sitter_analyzer/languages/typescript_plugin.py`
- Rust plugin: `tree_sitter_analyzer/languages/rust_plugin.py`
- Ruby plugin: `tree_sitter_analyzer/languages/ruby_plugin.py`
- Scala plugin: `tree_sitter_analyzer/languages/scala_plugin.py`
- C# plugin: `tree_sitter_analyzer/languages/csharp_plugin.py`
- Kotlin plugin: `tree_sitter_analyzer/languages/kotlin_plugin.py`
- Swift plugin: `tree_sitter_analyzer/languages/swift_plugin.py`
- Golden corpora: `tests/golden/corpus_*.{ts,rs,rb,scala,kt,swift}`
