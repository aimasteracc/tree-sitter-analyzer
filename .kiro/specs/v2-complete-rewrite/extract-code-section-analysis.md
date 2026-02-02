# Extract Code Section Tool - Analysis Document

**Date**: 2026-02-01
**Task**: T7.4 - extract_code_section MCP Tool
**Status**: Analysis Phase

## Overview

Analyze v1's `read_partial_tool.py` to understand partial file reading functionality and identify implementation requirements for v2.

## V1 Implementation Analysis

### File Location
`tree_sitter_analyzer/mcp/tools/read_partial_tool.py` (861 lines)

### Core Functionality

**1. Single File Extraction (Basic Mode)**
```python
{
  "file_path": "src/main.py",
  "start_line": 10,
  "end_line": 20,
  "start_column": 0,  # optional
  "end_column": 50    # optional
}
```
- Line-based extraction (1-indexed)
- Optional column-based extraction (0-indexed)
- Reads from start_line to end_line (inclusive)
- If end_line omitted, reads to end of file

**2. Batch Mode (Advanced)**
```python
{
  "requests": [
    {
      "file_path": "src/main.py",
      "sections": [
        {"start_line": 10, "end_line": 20, "label": "main function"},
        {"start_line": 50, "end_line": 60, "label": "helper"}
      ]
    },
    {
      "file_path": "src/utils.py",
      "sections": [
        {"start_line": 1, "end_line": 30, "label": "imports and setup"}
      ]
    }
  ]
}
```
- Extract multiple sections from multiple files in one call
- Each section has optional label for identification
- Mutually exclusive with single-mode parameters

**3. Output Formats**

| Format | Description | Use Case |
|--------|-------------|----------|
| `text` (default) | CLI-compatible with headers | Human-readable output |
| `json` | Structured JSON with metadata | Programmatic access |
| `raw` | Plain code content only | Direct code extraction |

**4. Output Destinations**

- **Direct output**: Returns content in response
- **File output**: Saves to file with `output_file` parameter
- **Suppress output**: `suppress_output=true` to save tokens when saving to file

**5. TOON Format Support**

```python
"output_format": "toon"  # default, 50-70% token reduction
"output_format": "json"  # full JSON output
```

### Safety Limits (Batch Mode)

```python
_BATCH_LIMITS = {
    "max_files": 20,                    # Max files per batch
    "max_sections_per_file": 50,        # Max sections per file
    "max_sections_total": 200,          # Total sections across all files
    "max_total_bytes": 1024 * 1024,     # 1 MiB total content
    "max_total_lines": 5000,            # Total lines across all sections
    "max_file_size_bytes": 5 * 1024 * 1024  # 5 MiB per file
}
```

**Enforcement Strategies**:
- `fail_fast=true`: Stop on first error
- `allow_truncate=true`: Truncate results to fit limits (otherwise fail)

### Key Features

✅ **Single & Batch Modes**: Flexible extraction from one or many files
✅ **Line/Column Precision**: Character-level extraction support
✅ **Multiple Output Formats**: text, json, raw
✅ **File Output**: Save to file with auto-extension detection
✅ **Token Optimization**: TOON format + suppress_output
✅ **Security Validation**: PathResolver integration
✅ **Performance Monitoring**: Detailed metrics
✅ **Error Handling**: Partial success in batch mode
✅ **Encoding Support**: Uses v1's EncodingManager (implicit via read_file_partial)

### Dependencies (V1)

```python
from ...file_handler import read_file_partial  # Core reading logic
from ..utils.file_output_manager import FileOutputManager  # File saving
from ..utils.format_helper import apply_toon_format_to_response, format_for_file_output  # Formatting
from .base_tool import BaseMCPTool  # Base class
```

### Response Format (Single Mode)

```python
{
  "success": true,
  "file_path": "src/main.py",
  "range": {
    "start_line": 10,
    "end_line": 20,
    "start_column": null,
    "end_column": null
  },
  "content_length": 256,
  "lines_extracted": 11,
  "partial_content_result": "...",  # Content in specified format
  "output_file_path": "/path/to/saved/file.txt",  # If output_file specified
  "file_saved": true
}
```

### Response Format (Batch Mode)

```python
{
  "success": true,
  "count_files": 2,
  "count_sections": 3,
  "truncated": false,
  "limits": { ... },
  "errors_summary": {"errors": 0},
  "results": [
    {
      "file_path": "src/main.py",
      "resolved_path": "/abs/path/src/main.py",
      "sections": [
        {
          "label": "main function",
          "range": {"start_line": 10, "end_line": 20},
          "content_length": 256,
          "content": "..."  # In TOON mode, this may be omitted
        }
      ],
      "errors": []
    }
  ]
}
```

## V2 Implementation Requirements

### Must Have (MVP)

1. **Single File Extraction** ✅
   - Line range: start_line → end_line
   - Read to EOF if end_line omitted
   - Return content + metadata

2. **Output Format Support** ✅
   - TOON (default)
   - Markdown (instead of JSON - v2 standard)

3. **Encoding Detection** ✅
   - Use v2's EncodingDetector for multi-encoding support
   - Handles Japanese, Chinese files

4. **Security Validation** ✅
   - Project boundary enforcement
   - Path resolution and validation

### Should Have (Phase 2)

5. **Batch Mode** (optional, can defer)
   - Multiple sections from multiple files
   - Safety limits enforcement

6. **File Output** (optional, can defer)
   - Save to file functionality
   - suppress_output option

### Won't Have (Out of Scope)

- Column-level extraction (start_column, end_column)
- Performance monitoring integration (v2 doesn't have this yet)
- FileOutputManager (v2 doesn't have this yet)

## V2 Simplifications

Compared to v1's 861 lines, v2 can be much simpler:

1. **No FileOutputManager**: Skip file output functionality for MVP
2. **No Column Extraction**: Line-based only (simpler)
3. **Simpler Limits**: Only for batch mode, which is optional
4. **TOON + Markdown Only**: No "raw" or "text" formats (use TOON/Markdown instead)
5. **Simplified Batch**: Can be Phase 2 feature

## Estimated Complexity

| Component | V1 Lines | V2 Estimate | Notes |
|-----------|----------|-------------|-------|
| Schema | 100 | 50 | Simpler schema (no columns, file output) |
| Single Mode | 250 | 100 | Core extraction logic |
| Batch Mode | 300 | 150 | Optional Phase 2 |
| Validation | 100 | 50 | Reuse v2 patterns |
| File Output | 100 | 0 | Skip for MVP |
| **Total** | **850** | **200-350** | 75% simpler |

## Implementation Strategy

### Phase 1: MVP (Single Mode) - 1h
- Tool schema definition
- Single file extraction (start_line → end_line)
- TOON/Markdown output
- Encoding detection integration
- 10-15 tests

### Phase 2: Advanced Features - 1h (optional)
- Batch mode with limits
- File output functionality
- Column-level extraction
- 10-15 additional tests

## Key Design Decisions

1. **Use EncodingDetector**: Leverage v2's encoding detection for multi-language support
2. **TOON as Default**: Consistent with v2 philosophy (token optimization)
3. **Markdown over JSON**: v2 uses Markdown format instead of JSON
4. **Defer Batch Mode**: Can be added later if needed
5. **Line-Based Only**: Skip column extraction for simplicity

## Next Steps

1. Create design document (T7.4 design)
2. Write failing tests (RED phase)
3. Implement ExtractCodeSectionTool (GREEN phase)
4. Refactor and optimize (REFACTOR phase)

---

**Status**: ✅ Analysis Complete
**Next**: Design Phase
