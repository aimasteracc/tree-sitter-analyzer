# Design: Fix Java Plugin Annotation Extraction

**Change ID**: `fix-java-plugin-annotation-extraction`

---

## Design Decisions

### Decision 1: Separate cache lifecycle from business state lifecycle

**Problem**: `_reset_caches()` clears both performance caches and business state
(`self.annotations`, `self.current_package`). These have different lifecycles:

- **Performance caches**: Should reset before each `extract_*()` call (per-element-type scope)
- **Business state**: Should persist across `extract_*()` calls within one file analysis

**Decision**: Remove business state resets from `_reset_caches()`. Business state is
initialized in `__init__` and written by `extract_annotations()` / `extract_packages()`.

### Decision 2: Pre-extract shared state before element extraction

**Problem**: `extract_functions()` and `extract_classes()` call
`_find_annotations_for_line_cached()` which reads `self.annotations`. This data
must exist before those methods run.

**Decision**: In `extract_elements()`, call `extract_annotations()` and
`extract_packages()` first. Their results populate `self.annotations` and
`self.current_package`, which are then available to subsequent extractors.

### Decision 3: Align with GoPlugin's self.extractor sync pattern

**Problem**: `GoPlugin` syncs language-specific metadata back to `self.extractor`
after analysis (goroutines, channels, defers). `JavaPlugin` creates `self.extractor`
in `__init__` but never updates it, making it stale.

**Decision**: Sync `annotations`, `current_package`, and `imports` back to
`self.extractor` at the end of `extract_elements()`, consistent with `GoPlugin`.

---

## Affected Files

| File | Change |
|------|--------|
| `tree_sitter_analyzer/languages/java_plugin.py` | 3 targeted changes |
| `tests/unit/languages/test_java_plugin.py` | Add `TestResetCachesPreservesState` class |
| `tests/integration/languages/test_java_integration.py` | New file, 3 integration tests |

---

## Non-changes

- `extract_classes()` guard (`if not self.current_package: self._extract_package_from_tree(tree)`)
  is kept as a safety net for standalone calls.
- `_annotation_cache` continues to be cleared by `_reset_caches()` — it's a lookup
  cache derived from `self.annotations` and must be rebuilt when caches are reset.
- No changes to public method signatures.
