# Tasks: Add C# Language Support

## Status: IMPLEMENTED (language) + BUG FIX (annotation extraction)

### Phase 1 — Language support (pre-existing, complete)
- [x] `csharp_plugin.py` + `csharp_helpers.py` implemented
- [x] `tree-sitter-c-sharp` dependency installed
- [x] Registered in `language_loader.py` as `csharp` / `cs`
- [x] Query module `queries/csharp.py` in place
- [x] Sample files: `examples/Sample.cs`, `SampleAdvanced.cs`, `SampleASPNET.cs`

### Phase 2 — Bug fix: attribute extraction (2026-05-28)
- [x] **Bug**: `extract_attributes()` in `csharp_helpers.py` walked `node.prev_sibling`
  to find attribute lists. In the tree-sitter-c-sharp grammar, `attribute_list`
  nodes are **direct children** of declaration nodes (at index 0, 1, …), not siblings.
  `prev_sibling` always returned `None` → `annotations=[]` on all classes and methods.
- [x] **Fix**: iterate `node.children`, collect `attribute_list` until first non-attribute
  child, extract name from `attribute → identifier` subtree.
- [x] **TDD tests added**:
  - `test_class_attribute_names_extracted`: `[Serializable]` on BaseEntity, `[Obsolete]` on Order
  - `test_method_attribute_names_extracted`: `[HttpGet]`, `[Authorize]` on GetAll
  - `TestExtractAttributes` in `_test_csharp_helpers_primitives.py` updated to new API
- [x] 18 006 tests pass, 0 regressions

### Verified via MCP (post-fix)
- `SampleASPNET.cs`: `UsersController` annotations = `[ApiController, Route, Authorize]`
- `GetAll` method annotations = `[HttpGet, ProducesResponseType]`
