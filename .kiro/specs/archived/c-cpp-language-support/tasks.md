# Implementation Plan

## Phase 1: Plugin Implementation

- [x] 1.1 Create `c_plugin.py` with `CPlugin` and `CElementExtractor`
- [x] 1.2 Create `cpp_plugin.py` with `CppPlugin` and `CppElementExtractor`
- [x] 1.3 Implement `analyze_file()` for reading files, parsing syntax trees, and aggregating elements with node counts
- [x] 1.4 Implement `get_tree_sitter_language()` with graceful import/wrapper failure handling
- [x] 1.5 Use BFS (breadth-first search) for `_find_identifier()` to ensure correct name extraction
- [x] 1.6 Filter out local variables and type references (only extract top-level definitions)
- [x] 1.7 Checkpoint - Verify plugin loads correctly

## Phase 2: Entry Points and Dependencies

- [x] 2.1 Register `c` and `cpp` in `pyproject.toml` `[project.entry-points."tree_sitter_analyzer.plugins"]`
- [x] 2.2 Add `tree-sitter-c` to core dependencies (not just optional)
- [x] 2.3 Add `tree_sitter_c` to mypy ignore list for missing imports
- [x] 2.4 Checkpoint - Verify entry points work

## Phase 3: Query Modules

- [x] 3.1 Create `queries/c.py` with C-specific tree-sitter queries
- [x] 3.2 Create `queries/cpp.py` with C++-specific tree-sitter queries
- [x] 3.3 Include common query aliases for cross-language compatibility (`functions`, `classes`, `variables`, `imports`)
- [x] 3.4 Checkpoint - Verify queries are accessible

## Phase 4: Sample Files

- [x] 4.1 Create comprehensive `examples/sample.c` covering:
  - Preprocessor directives (#include, #define, #ifdef)
  - Enums, structs, unions
  - Typedefs and function pointers
  - Global, static, const, extern variables
  - Function definitions and declarations
  - Arrays and pointers
- [x] 4.2 Create comprehensive `examples/sample.cpp` covering:
  - Namespaces and using declarations
  - Classes with public/private/protected sections
  - Structs with member functions
  - Enums and enum classes
  - Templates (functions and classes)
  - Inheritance and virtual functions
  - Operator overloading
  - Friend functions
  - Type aliases (typedef and using)
  - Lambda expressions
  - Smart pointers
- [x] 4.3 Checkpoint - Verify samples parse correctly

## Phase 5: Unit Tests

- [x] 5.1 Create `tests/test_c/test_c_plugin.py` with:
  - Plugin metadata test (language name, extensions)
  - Extractor coverage test (all element types)
  - analyze_file execution test
- [x] 5.2 Create `tests/test_cpp/test_cpp_plugin.py` with:
  - Plugin metadata test (language name, extensions)
  - Extractor coverage test (all element types)
  - analyze_file execution test
- [x] 5.3 Checkpoint - Ensure unit tests pass

## Phase 6: Golden Master Tests

- [x] 6.1 Generate Golden Master files for C (full/compact/csv formats)
- [x] 6.2 Generate Golden Master files for C++ (full/compact/csv formats)
- [x] 6.3 Add C/C++ tests to `test_golden_master_regression.py`
- [x] 6.4 Checkpoint - Verify all Golden Master tests pass

## Phase 7: Validation

- [x] 7.1 Run import and initialization verification
- [x] 7.2 Verify graceful degradation when tree-sitter-c/cpp unavailable
- [x] 7.3 Confirm plugin doesn't affect other language plugins on failure
- [x] 7.4 Run full test suite multiple times to verify stability
- [x] 7.5 Final checkpoint - All tests pass consistently

