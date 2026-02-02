# Cross-File Call Resolution Test Project

This is a test project for validating cross-file call resolution in the Tree-sitter Analyzer.

## Project Structure

```
cross_file_project/
├── README.md                    # This file
├── main.py                      # Entry point, imports from utils
├── utils.py                     # Utility functions
├── config.py                    # Configuration module
├── services/
│   ├── __init__.py
│   ├── auth.py                  # Authentication service
│   └── data.py                  # Data processing service
└── processors/
    ├── __init__.py
    ├── text_processor.py        # Text processing utilities
    └── validator.py             # Validation utilities
```

## Known Cross-File Calls

This project contains the following documented cross-file function calls:

### Absolute Imports

1. **main.py → utils.py**
   - `main()` calls `helper()`
   - `main()` calls `validate()`

2. **main.py → config.py**
   - `main()` calls `get_config()`

3. **services/auth.py → utils.py**
   - `authenticate()` calls `validate()`

4. **services/data.py → utils.py**
   - `process()` calls `helper()`

5. **services/data.py → processors/text_processor.py**
   - `process()` calls `clean_text()`

### Relative Imports

6. **services/auth.py → services/data.py**
   - `authenticate()` calls `fetch_user_data()` (from .data)

7. **processors/text_processor.py → processors/validator.py**
   - `clean_text()` calls `is_valid_text()` (from .validator)

### Same-File Calls (Control Group)

8. **main.py**
   - `local_func()` calls `main()`

9. **utils.py**
   - `helper()` calls `process_data()`

10. **processors/text_processor.py**
    - `clean_text()` calls `_sanitize()` (private function)

## Import Types

- **Absolute imports**: `from utils import helper`
- **Relative imports (sibling)**: `from . import data`
- **Relative imports (nested)**: `from ..utils import validate`

## Expected Test Results

When analyzing this project with `cross_file=True`, the analyzer should:

1. Detect **7 cross-file calls** (excluding same-file calls)
2. Correctly resolve absolute imports to file paths
3. Correctly resolve relative imports within packages
4. Build a complete call graph showing all relationships
5. Mark cross-file edges with `cross_file=True` attribute

## Usage in Tests

```python
from pathlib import Path
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

FIXTURE_DIR = Path(__file__).parent / "cross_file_project"

# Build graph with cross-file resolution
builder = CodeGraphBuilder()
graph = builder.build_from_directory(
    str(FIXTURE_DIR),
    cross_file=True
)

# Count cross-file calls
cross_file_calls = [
    (u, v) for u, v, d in graph.edges(data=True)
    if d.get('type') == 'CALLS' and d.get('cross_file') is True
]

assert len(cross_file_calls) >= 7
```

## File Contents Summary

- **main.py**: Entry point with calls to utils and config
- **utils.py**: Shared utilities (helper, validate, process_data)
- **config.py**: Configuration getter
- **services/auth.py**: Authentication with calls to utils and data service
- **services/data.py**: Data processing with calls to utils and text_processor
- **processors/text_processor.py**: Text cleaning with validator calls
- **processors/validator.py**: Text validation utilities

## Test Scenarios

1. **Absolute import resolution**: main.py → utils.py
2. **Relative sibling import**: services/auth.py → services/data.py
3. **Relative nested import**: processors/text_processor.py → processors/validator.py
4. **Multi-hop call chain**: main → auth → data → text_processor
5. **Ambiguous names**: Multiple files may define similar function names (handled conservatively)
