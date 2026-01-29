# Design - Test Quality Audit and Improvement

## Audit Strategy

### 1. Identify "Constant Checks"
Use `ast-grep` or `grep` to find test files that primarily use `assert "key" in DICT` or `assert isinstance(x, dict)`. These are candidates for consolidation into a single test per module.

### 2. Dependency Analysis
Identify test modules that cover the same source file.
- Example: `tests/unit/core/test_exceptions.py` vs `tests/unit/core/test_exceptions_comprehensive.py`.
- Action: Merge into a single, high-quality test file and delete the redundant ones.

### 3. Coverage Gap Mapping
Specifically target files with < 40% coverage:
- `tree_sitter_analyzer/core/analysis_engine.py` (33%)
- `tree_sitter_analyzer/core/cache_service.py` (25%)
- `tree_sitter_analyzer/core/parser.py` (26%)
- `tree_sitter_analyzer/cli/commands/*` (10-20%)

### 4. Functional "Path Testing"
Instead of testing if a dictionary has 50 keys, create one integration test that runs the full analysis pipeline for that language and asserts the **output content** against a baseline.

## Action Plan

### Phase 1: Pruning
- **Step 1**: Consolidate language query tests. Instead of 100 tests checking for 100 query keys, use one test that iterates through the dictionary.
- **Step 2**: Remove redundant exception tests.
- **Step 3**: Identify "shallow mocks" where `AnalyzeScaleTool` is tested with every single component mocked out. These tests don't verify if the tool actually works with real components.

### Phase 2: Targeted Coverage Boost
- **Step 1**: Implement real integration tests for `UnifiedAnalysisEngine` using the `examples/` directory.
- **Step 2**: Add tests for the `SecurityValidator` logic (currently 11% coverage).
- **Step 3**: Test the cache persistence logic in `CacheService`.

## Tools to be used
- `pytest --cov --cov-report=term-missing`
- `scripts/monitor_coverage.py`
- Manual AST inspection
