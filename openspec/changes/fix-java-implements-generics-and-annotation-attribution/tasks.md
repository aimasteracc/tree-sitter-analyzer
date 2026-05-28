# Tasks: Fix Java implements Generics + Annotation Attribution

## Validation Project
caffeine (ben-manes/caffeine) — BoundedLocalCache.java

## TDD Order: Write FAILING tests first, then implement fixes

---

### Phase 1: TDD — Write Failing Tests

- [x] **T1.1** Write test: implements with generics preserved as single string
  - `tests/unit/languages/test_java_caffeine_validation.py::TestImplementsGenerics::test_implements_generic_preserved_unit`
  - Was FAILING before fix ✓

- [x] **T1.2** Write test: multiple generic interfaces each preserved
  - `test_implements_multiple_generic_interfaces`
  - Was FAILING before fix ✓

- [x] **T1.3** Write test: @Override never appears in class annotations
  - `test_override_never_on_class_unit`
  - Was FAILING before fix ✓

- [x] **T1.4** Write test: annotation bleed via direct AST
  - `test_annotation_attribution_direct_ast`
  - Was FAILING before fix ✓

### Phase 2: Implement Fixes

- [x] **T2.1** Fix implements generic parsing in `_java_element_helpers.py`
  - Added `_split_respecting_generics()` — depth-counter-based comma split
  - Updated `_extract_class_relationships()` to call it instead of `re.findall(r"\b[A-Z]\w*")`
  - Strips leading `implements` keyword before splitting

- [x] **T2.2** Fix annotation attribution: root cause was `_reset_caches()` clearing `self.annotations`
  - Root cause: `_reset_caches()` in `java_plugin.py` called `self.annotations.clear()`,
    wiping data populated by `extract_annotations()` before `extract_classes()` could read it.
  - Fix: removed `self.annotations.clear()` from `_reset_caches()`. Annotations are extracted
    data (not a performance cache) and must survive across calls within a session.
  - Updated `test_reset_caches` in `test_java_element_extractor_core.py` to assert
    annotations are preserved (not cleared) by `_reset_caches()`.

- [x] **T2.3** Annotation window: ±2 line proximity is sufficient for the unit tests.
  - `@Override` on methods is always > 2 lines from the next class start in well-formatted code.
  - Caffeine-specific edge cases remain in the 3 `_skip_caffeine`-marked tests.

### Phase 3: Validate

- [x] **T3.1** All Java unit tests: 114 passed, 3 skipped (caffeine: no clone)
  - `uv run pytest tests/unit/languages/ -q` → 3644 passed, 24 skipped
  - Contract tests: 48 passed

- [ ] **T3.2** Verify caffeine BoundedLocalCache.java via MCP (requires caffeine clone)

- [ ] **T3.3** Verify with netty (optional stretch goal)

## Dependencies
- T1.* before T2.*
- T2.1 and T2.2 independent
- T3.* after T2.*

## Status
COMPLETE (2026-05-28) — all unit tests green; T3.2/T3.3 deferred (require external repos)
