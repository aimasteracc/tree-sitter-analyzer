# Extract Code Section Tool - Design Document

**Date**: 2026-02-01
**Task**: T7.4 - extract_code_section MCP Tool
**Status**: Design Phase

## Overview

Design v2's extract_code_section tool based on v1 analysis, with simplified implementation focused on core functionality.

## Architecture

### Tool Structure

```
v2/tree_sitter_analyzer_v2/
├── mcp/tools/
│   └── extract.py              # NEW: ExtractCodeSectionTool (~200 lines)
└── tests/integration/
    └── test_extract_tool.py    # NEW: Integration tests (~300 lines)
```

### Class Design

```python
class ExtractCodeSectionTool(BaseTool):
    """
    MCP tool for extracting code sections by line range.

    Simplified version of v1's ReadPartialTool:
    - Line-based extraction only (no columns)
    - TOON/Markdown output only
    - Single mode only (no batch for MVP)
    - Encoding detection support
    """

    def __init__(self):
        """Initialize with encoding detector."""
        self._encoding_detector = EncodingDetector()

    def get_name(self) -> str:
        return "extract_code_section"

    def get_description(self) -> str:
        return (
            "Extract specific code sections by line range. "
            "Returns partial file content with automatic encoding detection "
            "for multi-language files (Japanese, Chinese, etc.)."
        )

    def get_schema(self) -> dict[str, Any]:
        """Return JSON schema for arguments."""

    def get_tool_definition(self) -> dict[str, Any]:
        """Return MCP tool definition."""

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute code section extraction."""
```

## API Design

### Input Schema

```python
{
    "type": "object",
    "properties": {
        "file_path": {
            "type": "string",
            "description": "Path to the code file to read"
        },
        "start_line": {
            "type": "integer",
            "description": "Starting line number (1-based)",
            "minimum": 1
        },
        "end_line": {
            "type": "integer",
            "description": "Ending line number (1-based, optional - reads to end if not specified)",
            "minimum": 1
        },
        "output_format": {
            "type": "string",
            "enum": ["toon", "markdown"],
            "description": "Output format: 'toon' (default, token-optimized) or 'markdown' (human-readable)",
            "default": "toon"
        }
    },
    "required": ["file_path", "start_line"]
}
```

### Output Format

**TOON Format (Default)**:
```
file_path: src/main.py
range: {start_line:10, end_line:20}
lines_extracted: 11
content_length: 256
content: |
  def main():
      print("Hello")
      return 0
```

**Markdown Format**:
```markdown
# Code Section Extract

**File**: `src/main.py`
**Range**: Line 10-20
**Lines**: 11
**Size**: 256 characters

```python
def main():
    print("Hello")
    return 0
```
```

## Implementation Details

### Extraction Algorithm

```python
def _extract_lines(self, file_path: Path, start_line: int, end_line: Optional[int]) -> str:
    """
    Extract lines from file using encoding detection.

    Strategy:
    1. Detect encoding using EncodingDetector
    2. Read file with detected encoding
    3. Split into lines
    4. Extract specified range (1-indexed)
    5. Join and return

    Memory: O(n) where n = file size (loads entire file)
    For large files (>10MB), could use streaming in future.
    """
    # Detect encoding
    encoding = self._encoding_detector.detect_encoding(file_path)

    # Read file with detected encoding
    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
        lines = f.readlines()

    # Validate range
    total_lines = len(lines)
    if start_line > total_lines:
        raise ValueError(f"start_line {start_line} exceeds file length {total_lines}")

    # Extract range (convert to 0-indexed)
    start_idx = start_line - 1
    end_idx = end_line if end_line else total_lines

    extracted = lines[start_idx:end_idx]
    return ''.join(extracted)
```

### Error Handling

| Error Condition | Response |
|-----------------|----------|
| File not found | `{"success": false, "error": "File not found: <path>"}` |
| start_line < 1 | `{"success": false, "error": "start_line must be >= 1"}` |
| end_line < start_line | `{"success": false, "error": "end_line must be >= start_line"}` |
| start_line > total_lines | `{"success": false, "error": "start_line exceeds file length"}` |
| Encoding error | Use 'replace' error handling (no failure) |
| Security violation | `{"success": false, "error": "Path outside project root"}` |

### Security Validation

```python
def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
    file_path = arguments["file_path"]

    # Validate path is within project boundaries
    # (v2 doesn't have PathResolver, so basic validation)
    file_path_obj = Path(file_path).resolve()

    # Check file exists
    if not file_path_obj.exists():
        return {"success": False, "error": f"File not found: {file_path}"}

    # Check file is readable
    if not file_path_obj.is_file():
        return {"success": False, "error": f"Not a file: {file_path}"}
```

## Output Format Comparison

### TOON Format (Default)

```python
{
    "success": True,
    "file_path": "src/main.py",
    "range": {"start_line": 10, "end_line": 20},
    "lines_extracted": 11,
    "content_length": 256,
    "content": "def main():\n    print('Hello')\n    return 0\n"
}
```

**TOON Serialization**:
```
success: true
file_path: src/main.py
range: {start_line:10, end_line:20}
lines_extracted: 11
content_length: 256
content: |
  def main():
      print('Hello')
      return 0
```

### Markdown Format

```python
{
    "success": True,
    "content": """
# Code Section Extract

**File**: `src/main.py`
**Range**: Line 10-20
**Lines**: 11
**Size**: 256 characters

```python
def main():
    print('Hello')
    return 0
```
"""
}
```

## Testing Strategy

### Unit Tests (Not Needed)

ExtractCodeSectionTool is simple enough that integration tests are sufficient.

### Integration Tests (~12 tests)

**Created**: `v2/tests/integration/test_extract_tool.py`

1. **Basic Extraction Tests**
   - test_extract_basic_range
   - test_extract_to_end_of_file
   - test_extract_single_line
   - test_extract_first_line
   - test_extract_last_line

2. **Output Format Tests**
   - test_extract_toon_format
   - test_extract_markdown_format

3. **Encoding Tests**
   - test_extract_japanese_shift_jis
   - test_extract_chinese_gbk
   - test_extract_utf8_with_bom

4. **Error Handling Tests**
   - test_extract_file_not_found
   - test_extract_invalid_range
   - test_extract_start_line_exceeds_file

## Integration Points

### With EncodingDetector

```python
# In __init__
from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector
self._encoding_detector = EncodingDetector()

# In execute
encoding = self._encoding_detector.detect_encoding(file_path)
with open(file_path, 'r', encoding=encoding, errors='replace') as f:
    content = f.read()
```

### With MCP Server

```python
# In mcp/tools/__init__.py
from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

__all__ = [
    ...,
    "ExtractCodeSectionTool",
]
```

## Performance Considerations

| File Size | Memory Usage | Strategy |
|-----------|--------------|----------|
| < 1MB | O(n) | Load entire file |
| 1MB - 10MB | O(n) | Load entire file (acceptable) |
| > 10MB | O(n) | Future: Consider streaming |

**Note**: For MVP, loading entire file is acceptable. Can optimize later with streaming if needed.

## Comparison: V1 vs V2

| Feature | V1 | V2 MVP | V2 Future |
|---------|----|----|-----------|
| Line extraction | ✅ | ✅ | ✅ |
| Column extraction | ✅ | ❌ | ❓ |
| Batch mode | ✅ | ❌ | ❓ |
| File output | ✅ | ❌ | ❓ |
| TOON format | ✅ | ✅ | ✅ |
| Markdown format | ❌ | ✅ | ✅ |
| Encoding detection | ✅ (implicit) | ✅ (explicit) | ✅ |
| Safety limits | ✅ | ❌ | ❓ |
| Lines of code | ~850 | ~200 | ~400 |

## Success Criteria

✅ **Functional Requirements**:
- Extract code by line range (start_line → end_line)
- Read to EOF if end_line omitted
- Support TOON and Markdown output formats
- Handle multi-encoding files (Japanese, Chinese)
- Proper error handling

✅ **Quality Requirements**:
- All 12 tests passing
- Test coverage > 90%
- No hardcoded encodings
- Clear error messages

## Implementation Timeline

| Phase | Duration | Tests | Status |
|-------|----------|-------|--------|
| TDD Phase 1: Core | 30min | 5 basic tests | Pending |
| TDD Phase 2: Formats | 15min | 2 format tests | Pending |
| TDD Phase 3: Encoding | 15min | 3 encoding tests | Pending |
| TDD Phase 4: Errors | 10min | 3 error tests | Pending |
| Integration | 10min | 1 test | Pending |
| **Total** | **1-1.5h** | **~14 tests** | Pending |

## Next Steps

1. **Begin TDD Phase 1**: Create failing tests for basic extraction
2. **Implement Core Logic**: Line extraction with encoding detection
3. **Add Format Support**: TOON and Markdown output
4. **Validate**: Run full test suite

---

**Status**: ✅ Design Complete
**Next**: TDD Implementation
