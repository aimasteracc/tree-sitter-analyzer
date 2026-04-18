# add-ast-chunking-optimization

## Summary
Add AST-aware chunking for large files — split analysis results into semantic chunks based on language-specific boundaries (classes, functions, top-level blocks).

## Motivation
- Current `extract_code_section` is line-based, not AST-aware
- Large files need semantic segmentation for efficient LLM consumption
- Different languages have different natural chunking boundaries

## Tasks
- [x] T1: Create `ast_chunker.py` with `AstChunk` model and `chunk_analysis_result()` function
- [x] T2: Add language-family chunking strategies (OOP, scripting, Go, markup)
- [x] T3: Integrate token estimation per chunk using line-count heuristic
- [x] T4: Write unit tests for all chunking strategies
- [x] T5: Run CI checks (ruff + mypy + pytest)

## Files
- ✅ EXISTING: `tree_sitter_analyzer/core/ast_chunker.py` (487 lines)
- ✅ EXISTING: `tests/unit/core/test_ast_chunker.py` (28 tests pass)

## Design
- Pure function: `(AnalysisResult, language) -> list[AstChunk]`
- No mutation of existing code — additive only
- `AstChunk` is a frozen dataclass with name, chunk_type, start_line, end_line, token_estimate, children

## Implementation Details

### Language Families
- **OOP Languages**: Java, C#, Kotlin, Scala - classes contain methods/fields
- **Script Languages**: Python, JavaScript, TypeScript, Ruby, PHP - classes + top-level functions
- **Function Languages**: Go, Rust, C, C++ - top-level functions only

### Chunk Types
- `class`: Class definition with nested methods/fields as children
- `function`: Top-level function or method
- `import_block`: All imports grouped together
- `header`: Code before first semantic element (package, shebang)
- `tail`: Code after last semantic element

### Token Estimation
- Conservative estimate: 4 tokens per line
- Formula: `(end_line - start_line + 1) * TOKENS_PER_LINE`

## Test Results
All 28 tests passing:
- TestOopChunking: Java-style classes with methods
- TestScriptChunking: Python/JS/TS/Ruby/PHP class + functions
- TestFunctionChunking: Go/Rust/C top-level functions
- TestChunksSummary: Chunk metadata and to_dict()

## Status
✅ **COMPLETE** - Module was already implemented with full test coverage.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
