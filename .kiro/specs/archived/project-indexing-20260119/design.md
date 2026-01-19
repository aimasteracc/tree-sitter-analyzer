# Design - Project indexing with TOON

## Technology Choices
- **Analysis Engine**: `tree-sitter-analyzer` (itself).
- **Format**: TOON (Token-Optimized Output Notation).
- **Storage**: Persistent file `.kiro/project_map.toon`.

## Implementation Strategy
1. **File Discovery**: Use `glob` to find all `.py` files in `tree_sitter_analyzer/`.
2. **Batch Analysis**: Run `tree-sitter-analyzer --table toon` on each file.
3. **Stream Redirection**: Append the output of each analysis to the aggregate map file.
4. **Header Addition**: Prefix each entry with the relative file path for clear indexing.

## Data Flow
`Source Code (.py)` -> `Tree-sitter Analyzer` -> `TOON String` -> `project_map.toon`
