# Design - Project Self-Optimization

## Technology Choices
- **Analysis Tool**: `tree-sitter-analyzer` (Dogfooding)
- **Reporting Format**: Markdown (within `.kiro` structure)
- **Refactoring Strategy**: Functional decomposition and logic isolation.

## Analysis Results (Findings)
Based on the self-scan and manual inspection of `tree_sitter_analyzer/core/`, the following functions have been identified as candidates for optimization due to high logical complexity and length:

### 1. `UnifiedAnalysisEngine.analyze` (analysis_engine.py:117-172)
- **Complexity Source**: Orchestrates security validation, language detection, cache checks, parsing, and query execution in a single flow.
- **Issues**:
    - Too many responsibilities (Violation of SRP).
    - Complex conditional logic for language handling and cache management.
    - Direct dependency on multiple internal components.

### 2. `QueryExecutor.execute_query` (query.py:41-138)
- **Complexity Source**: Handles multi-layered input validation, language name normalization, compatibility checks, and multi-stage error handling.
- **Issues**:
    - Deeply nested `try-except` blocks.
    - Repetitive logic for result creation.
    - Manual language attribute probing (e.g., `getattr(language, "name", ...)`).

### 3. `UnifiedAnalysisEngine.analyze_file` (analysis_engine.py:174-237)
- **Complexity Source**: Serves as a massive compatibility bridge with many optional parameters.
- **Issues**:
    - High number of parameters.
    - Complex manual construction of `AnalysisRequest` from individual args.
    - Redundant logic for parameter overriding.

## Proposed Optimization Plan

### Task A: Refactor `UnifiedAnalysisEngine.analyze`
- **Action**: Extract sub-operations into dedicated private methods:
    - `_validate_request(request)`
    - `_handle_cache(request)`
    - `_get_plugin_and_parse(request)`
- **Goal**: Reduce `analyze` to a clean high-level orchestrator.

### Task B: Simplify `QueryExecutor.execute_query`
- **Action**: 
    - Create a `_normalize_language_name(language)` helper.
    - Unified the error response creation.
    - Flatten the `try-except` structure.

### Task C: Decouple `analyze_file` Parameter Mapping
- **Action**: Extract the logic for converting legacy parameters to `AnalysisRequest` into a dedicated builder method or helper function.

## Verification Plan
- **Step 1**: Implement changes one by one.
- **Step 2**: Run `uv run pytest tests/unit/` after each refactor.
- **Step 3**: Re-run the self-analysis scan to confirm complexity reduction.
- **Step 4**: Perform benchmark tests to ensure no performance regression.
