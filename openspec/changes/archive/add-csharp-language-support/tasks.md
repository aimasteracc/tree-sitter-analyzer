# Tasks: Add C# Language Support

**Change ID:** `add-csharp-language-support`  
**Status:** Draft

---

## Task Breakdown

### Phase 1: Foundation Setup (Day 1)

#### Task 1.1: Verify tree-sitter-c-sharp Availability
**Priority:** Critical  
**Estimated Time:** 1 hour

- [x] Verify `tree-sitter-c-sharp` package exists on PyPI
- [x] Check compatibility with `tree-sitter>=0.25.0`
- [x] Test basic installation: `pip install tree-sitter-c-sharp`
- [x] Verify language loading works with current tree-sitter version
- [x] Document any version constraints

**Validation:**
- Package installs successfully
- Language object can be created
- No version conflicts with existing dependencies

**Dependencies:** None

---

#### Task 1.2: Update pyproject.toml
**Priority:** Critical  
**Estimated Time:** 30 minutes

- [x] Add `tree-sitter-c-sharp` to optional dependencies
- [x] Add C# to language bundles (e.g., `all-languages`)
- [x] Update project description to mention C# support
- [x] Verify dependency resolution with `uv lock`

**Files to Modify:**
- `pyproject.toml`

**Validation:**
- `uv lock` succeeds
- `uv sync --extra csharp` installs correctly
- No dependency conflicts

**Dependencies:** Task 1.1

---

### Phase 2: Core Implementation (Day 2-3)

#### Task 2.1: Create C# Plugin Structure
**Priority:** Critical  
**Estimated Time:** 2 hours

- [x] Create `tree_sitter_analyzer/languages/csharp_plugin.py`
- [x] Implement `CSharpPlugin` class extending `LanguagePlugin`
- [x] Implement `get_language_name()` → "csharp"
- [x] Implement `get_file_extensions()` → [".cs"]
- [x] Implement `get_tree_sitter_language()` with caching
- [x] Implement `create_extractor()` → CSharpElementExtractor()
- [x] Add proper type hints for mypy compliance
- [x] Add docstrings for all public methods

**Files to Create:**
- `tree_sitter_analyzer/languages/csharp_plugin.py`

**Validation:**
- Plugin class instantiates successfully
- All interface methods implemented
- Mypy passes with zero errors
- Ruff passes with zero errors

**Dependencies:** Task 1.2

---

#### Task 2.2: Implement C# Element Extractor Base
**Priority:** Critical  
**Estimated Time:** 3 hours

- [x] Implement `CSharpElementExtractor` class extending `ElementExtractor`
- [x] Initialize caches and state variables
- [x] Implement `_reset_caches()` method
- [x] Implement `_get_node_text_optimized()` method (similar to Java plugin)
- [x] Implement `_extract_namespace()` method
- [x] Implement `_extract_modifiers()` method
- [x] Implement `_determine_visibility()` method
- [x] Add performance optimization caches

**Files to Modify:**
- `tree_sitter_analyzer/languages/csharp_plugin.py`

**Validation:**
- Extractor instantiates successfully
- Helper methods work correctly
- No memory leaks in caches

**Dependencies:** Task 2.1

---

#### Task 2.3: Implement Class Extraction
**Priority:** Critical  
**Estimated Time:** 4 hours

- [x] Implement `extract_classes()` method
- [x] Implement `_extract_csharp_classes()` for class declarations
- [x] Implement `_extract_interfaces()` for interface declarations
- [x] Implement `_extract_records()` for record declarations (C# 9+)
- [x] Implement `_extract_enums()` for enum declarations
- [x] Implement `_extract_structs()` for struct declarations
- [x] Extract class name, modifiers, visibility
- [x] Extract base class and interfaces
- [x] Extract attributes (C# annotations)
- [x] Extract generic type parameters
- [x] Generate fully qualified names with namespace

**Files to Modify:**
- `tree_sitter_analyzer/languages/csharp_plugin.py`

**Validation:**
- Classes extracted correctly
- Interfaces extracted correctly
- Records extracted correctly
- Enums extracted correctly
- Structs extracted correctly
- Attributes associated correctly

**Dependencies:** Task 2.2

---

#### Task 2.4: Implement Method Extraction
**Priority:** Critical  
**Estimated Time:** 4 hours

- [x] Implement `extract_functions()` method
- [x] Implement `_extract_methods()` for method declarations
- [x] Implement `_extract_constructors()` for constructor declarations
- [x] Extract method name, parameters, return type
- [x] Extract modifiers (public, private, static, async, etc.)
- [x] Extract attributes (HttpGet, Authorize, etc.)
- [x] Detect async methods
- [x] Detect extension methods
- [x] Detect operator overloads
- [x] Calculate complexity score
- [x] Extract XML documentation comments

**Files to Modify:**
- `tree_sitter_analyzer/languages/csharp_plugin.py`

**Validation:**
- Methods extracted correctly
- Constructors extracted correctly
- Async methods detected
- Attributes associated correctly
- Parameters extracted correctly

**Dependencies:** Task 2.2

---

#### Task 2.5: Implement Property Extraction
**Priority:** Critical  
**Estimated Time:** 3 hours

- [x] Implement `_extract_properties()` for property declarations
- [x] Detect auto-properties (`{ get; set; }`)
- [x] Detect computed properties (`=> expression`)
- [x] Detect properties with backing fields
- [x] Extract property type
- [x] Extract getter/setter presence
- [x] Extract init-only setters (C# 9+)
- [x] Extract attributes on properties
- [x] Map properties to Function elements with `is_property=True`

**Files to Modify:**
- `tree_sitter_analyzer/languages/csharp_plugin.py`

**Validation:**
- Auto-properties extracted correctly
- Computed properties extracted correctly
- Properties with backing fields extracted correctly
- Property types correct

**Dependencies:** Task 2.2

---

#### Task 2.6: Implement Field Extraction
**Priority:** High  
**Estimated Time:** 2 hours

- [x] Implement `extract_variables()` method
- [x] Implement `_extract_fields()` for field declarations
- [x] Extract field name, type, modifiers
- [x] Detect constants (`const`)
- [x] Detect readonly fields (`readonly`)
- [x] Detect events
- [x] Extract attributes on fields
- [x] Map fields to Variable elements

**Files to Modify:**
- `tree_sitter_analyzer/languages/csharp_plugin.py`

**Validation:**
- Fields extracted correctly
- Constants detected correctly
- Readonly fields detected correctly
- Events extracted correctly

**Dependencies:** Task 2.2

---

#### Task 2.7: Implement Import Extraction
**Priority:** High  
**Estimated Time:** 2 hours

- [x] Implement `extract_imports()` method
- [x] Implement `_extract_using_directives()` for using statements
- [x] Extract namespace imports
- [x] Extract static using directives
- [x] Extract using aliases
- [x] Map using directives to Import elements

**Files to Modify:**
- `tree_sitter_analyzer/languages/csharp_plugin.py`

**Validation:**
- Using directives extracted correctly
- Static using extracted correctly
- Using aliases extracted correctly

**Dependencies:** Task 2.2

---

#### Task 2.8: Implement analyze_file() Method
**Priority:** Critical  
**Estimated Time:** 2 hours

- [x] Implement `analyze_file()` async method
- [x] Load C# file with safe encoding detection
- [x] Parse file with tree-sitter-c-sharp
- [x] Extract all element types
- [x] Combine elements into AnalysisResult
- [x] Handle errors gracefully
- [x] Count AST nodes

**Files to Modify:**
- `tree_sitter_analyzer/languages/csharp_plugin.py`

**Validation:**
- File analysis works end-to-end
- All element types extracted
- Error handling works
- AnalysisResult structure correct

**Dependencies:** Tasks 2.3, 2.4, 2.5, 2.6, 2.7

---

### Phase 3: Testing (Day 4)

#### Task 3.1: Create Sample C# Files
**Priority:** Critical  
**Estimated Time:** 2 hours

- [x] Create `examples/Sample.cs` with basic C# features
  - Classes, methods, properties, fields
  - Using directives, namespaces
  - Basic attributes
- [x] Create `examples/SampleAdvanced.cs` with advanced features
  - Async/await methods
  - LINQ queries
  - Records, nullable reference types
  - Generic types
- [x] Create `examples/SampleASPNET.cs` with ASP.NET patterns
  - Controller class
  - HTTP attributes
  - Dependency injection

**Files to Create:**
- `examples/Sample.cs`
- `examples/SampleAdvanced.cs`
- `examples/SampleASPNET.cs`

**Validation:**
- Files contain valid C# syntax
- Files compile with `dotnet build` (if .NET SDK available)
- Files cover common C# patterns

**Dependencies:** None (can be done in parallel)

---

#### Task 3.2: Create Unit Tests
**Priority:** Critical  
**Estimated Time:** 4 hours

- [x] Create `tests/test_languages/test_csharp_plugin.py`
- [x] Test plugin instantiation
- [x] Test `get_language_name()`
- [x] Test `get_file_extensions()`
- [x] Test `get_tree_sitter_language()`
- [x] Test class extraction
- [x] Test method extraction
- [x] Test property extraction
- [x] Test field extraction
- [x] Test using directive extraction
- [x] Test attribute extraction
- [x] Test async method detection
- [x] Test record extraction
- [x] Test enum extraction
- [x] Test interface extraction
- [x] Test edge cases (empty files, invalid syntax)

**Files to Create:**
- `tests/test_languages/test_csharp_plugin.py`

**Validation:**
- All tests pass
- Test coverage >80%
- Tests cover all element types
- Tests cover edge cases

**Dependencies:** Tasks 2.8, 3.1

---

#### Task 3.3: Create Integration Tests
**Priority:** High  
**Estimated Time:** 2 hours

- [x] Test CLI analysis of C# files
- [x] Test format output (Full, Compact, CSV)
- [x] Test MCP tools with C# files
- [x] Test large C# file performance
- [x] Test partial class handling

**Files to Modify:**
- `tests/test_integration/` (add C# test cases)

**Validation:**
- CLI works with C# files
- Format output correct
- MCP tools work
- Performance acceptable

**Dependencies:** Task 3.2

---

#### Task 3.4: Create Golden Master Tests
**Priority:** Medium  
**Estimated Time:** 2 hours

- [x] Create golden master files for C# samples
- [x] Test full format output matches golden master
- [x] Test CSV format output matches golden master
- [x] Update golden master test suite

**Files to Create:**
- `tests/golden_masters/csharp_sample_full.txt`
- `tests/golden_masters/csharp_sample_csv.txt`

**Validation:**
- Golden master tests pass
- Output format consistent
- CSV format correct

**Dependencies:** Task 3.1, Task 3.2

---

### Phase 4: Documentation and Quality (Day 5)

#### Task 4.1: Update Documentation
**Priority:** High  
**Estimated Time:** 2 hours

- [x] Update `README.md` to include C# in supported languages
- [x] Update language support table
- [x] Add C# example to README
- [x] Update `CHANGELOG.md` with C# support
- [x] Update `docs/ja/user-guides/00_クイックスタートガイド.md`
- [x] Add C# to language count (8 → 9 languages)

**Files to Modify:**
- `README.md`
- `README_ja.md`
- `README_zh.md`
- `CHANGELOG.md`
- `docs/ja/user-guides/00_クイックスタートガイド.md`

**Validation:**
- Documentation accurate
- Examples work
- Language count correct

**Dependencies:** Task 3.2

---

#### Task 4.2: Run Quality Checks
**Priority:** Critical  
**Estimated Time:** 1 hour

- [x] Run `mypy` on C# plugin - must pass with zero errors
- [x] Run `ruff` on C# plugin - must pass with zero errors
- [x] Run `black` on C# plugin - must pass
- [x] Run `isort` on C# plugin - must pass
- [x] Run `pytest` - all tests must pass
- [x] Run `pytest --cov` - coverage must be >80%
- [x] Verify no regression in existing tests

**Validation:**
- All quality checks pass
- No linting errors
- No type errors
- Test coverage adequate
- No regression

**Dependencies:** Task 3.2

---

#### Task 4.3: Manual Testing
**Priority:** High  
**Estimated Time:** 2 hours

- [x] Test C# analysis via CLI
  - `uv run tree-sitter-analyzer examples/Sample.cs`
  - `uv run tree-sitter-analyzer examples/Sample.cs --format compact`
  - `uv run tree-sitter-analyzer examples/Sample.cs --format csv`
- [x] Test C# analysis via MCP
  - `mcp analyze_code_structure examples/Sample.cs`
- [x] Test with real-world C# projects
- [x] Verify output quality
- [x] Check performance

**Validation:**
- CLI works correctly
- MCP works correctly
- Output quality good
- Performance acceptable

**Dependencies:** Task 4.2

---

### Phase 5: Validation and Review (Day 5)

#### Task 5.1: Run OpenSpec Validation
**Priority:** Critical  
**Estimated Time:** 30 minutes

- [x] Run `uv run openspec validate add-csharp-language-support --strict`
- [x] Fix any validation errors
- [x] Ensure all specs are complete
- [x] Verify task completion

**Validation:**
- OpenSpec validation passes
- All specs complete
- All tasks marked complete

**Dependencies:** All previous tasks

---

#### Task 5.2: Final Review
**Priority:** Critical  
**Estimated Time:** 1 hour

- [x] Review all code changes
- [x] Verify no breaking changes
- [x] Verify isolation (no impact on other languages)
- [x] Check code quality
- [x] Check documentation completeness
- [x] Verify all success criteria met

**Validation:**
- Code review complete
- All success criteria met
- Ready for merge

**Dependencies:** Task 5.1

---

## Task Dependencies Graph

```
1.1 (Verify tree-sitter-c-sharp)
  └─> 1.2 (Update pyproject.toml)
        └─> 2.1 (Create C# Plugin Structure)
              └─> 2.2 (Implement Extractor Base)
                    ├─> 2.3 (Class Extraction)
                    ├─> 2.4 (Method Extraction)
                    ├─> 2.5 (Property Extraction)
                    ├─> 2.6 (Field Extraction)
                    └─> 2.7 (Import Extraction)
                          └─> 2.8 (analyze_file())
                                ├─> 3.2 (Unit Tests)
                                │     ├─> 3.3 (Integration Tests)
                                │     ├─> 3.4 (Golden Master Tests)
                                │     └─> 4.1 (Documentation)
                                │           └─> 4.2 (Quality Checks)
                                │                 └─> 4.3 (Manual Testing)
                                │                       └─> 5.1 (OpenSpec Validation)
                                │                             └─> 5.2 (Final Review)
                                └─> 3.1 (Sample Files) ────────┘

Parallel Tasks:
- 3.1 (Sample Files) can be done anytime
- 4.1 (Documentation) can start after 3.2
```

---

## Time Estimates

| Phase | Estimated Time |
|-------|----------------|
| Phase 1: Foundation Setup | 1.5 hours |
| Phase 2: Core Implementation | 20 hours |
| Phase 3: Testing | 10 hours |
| Phase 4: Documentation and Quality | 5 hours |
| Phase 5: Validation and Review | 1.5 hours |
| **Total** | **38 hours** (~5 days) |

---

## Success Criteria Checklist

- [x] C# plugin loads successfully via PluginManager
- [x] C# files (`.cs`) are recognized and processed
- [x] C# elements (classes, methods, properties, fields) are extracted correctly
- [x] C# analysis works through CLI, API, and MCP interfaces
- [x] Format output (Full, Compact, CSV) works for C# files
- [x] All tests pass (mypy, ruff, pytest)
- [x] Test coverage ≥80% for C# plugin
- [x] No regression in existing language plugins
- [x] Modern C# features are supported (records, nullable reference types)
- [x] C# attributes are extracted correctly

---

## Risk Mitigation

### Risk: tree-sitter-c-sharp not compatible
**Mitigation:** Verify compatibility in Task 1.1 before proceeding

### Risk: Complex C# syntax not parsing correctly
**Mitigation:** Create comprehensive sample files in Task 3.1, test edge cases

### Risk: Performance issues with large C# files
**Mitigation:** Use iterative traversal, optimize caching, test with large files

### Risk: Breaking existing functionality
**Mitigation:** Run full test suite, verify no regression, ensure isolation

---

## Notes

- Follow exact same pattern as SQL plugin (most recent addition)
- Refer to Java plugin for OOP language patterns
- C# has unique features (properties, attributes) requiring special handling
- Ensure complete isolation from other language plugins
- Maintain backward compatibility
- All code must pass mypy, ruff, and pytest

