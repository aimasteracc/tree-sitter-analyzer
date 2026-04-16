# add-ast-chunking-optimization

## Summary
Add AST-aware chunking for large files — split analysis results into semantic chunks based on language-specific boundaries (classes, functions, top-level blocks).

## Motivation
- Current `extract_code_section` is line-based, not AST-aware
- Large files need semantic segmentation for efficient LLM consumption
- Different languages have different natural chunking boundaries

## Tasks
- [ ] T1: Create `ast_chunker.py` with `AstChunk` model and `chunk_analysis_result()` function
- [ ] T2: Add language-family chunking strategies (OOP, scripting, Go, markup)
- [ ] T3: Integrate token estimation per chunk using line-count heuristic
- [ ] T4: Write unit tests for all chunking strategies
- [ ] T5: Run CI checks (ruff + mypy + pytest)

## Files
- NEW: `tree_sitter_analyzer/core/ast_chunker.py`
- NEW: `tests/unit/core/test_ast_chunker.py`

## Design
- Pure function: `(AnalysisResult, language) -> list[AstChunk]`
- No mutation of existing code — additive only
- `AstChunk` is a frozen dataclass with name, chunk_type, start_line, end_line, token_estimate, children
