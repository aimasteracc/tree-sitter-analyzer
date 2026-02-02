# Encoding Detection and Large File Optimization - Design Document

**Status**: In Progress
**Phase**: Design
**Created**: 2026-02-01

## 1. Architecture Overview

### 1.1 New Module Structure

```
v2/tree_sitter_analyzer_v2/
├── utils/
│   └── encoding.py          # NEW: Encoding detection module (~300 lines)
├── mcp/tools/
│   ├── find_and_grep.py     # MODIFY: Use encoding detection
│   ├── scale.py             # MODIFY: Use encoding detection
│   └── analyze.py           # MODIFY: Use encoding detection
└── tests/
    ├── unit/
    │   └── test_encoding.py          # NEW: Encoding tests
    └── fixtures/
        ├── encoding_fixtures/        # NEW: Multi-encoding test files
        │   ├── japanese_shift_jis.txt
        │   ├── chinese_gbk.txt
        │   ├── utf16_bom.txt
        │   └── large_file_500mb.txt
```

### 1.2 Core Components

1. **EncodingDetector**: Main encoding detection and file reading class
2. **EncodingCache**: LRU cache for encoding detection results
3. **Integration Layer**: Modify existing tools to use encoding detection

---

## 2. EncodingDetector Class Design

### 2.1 Class Structure

```python
from pathlib import Path
from typing import Generator, Optional, Iterator
import chardet

class EncodingDetector:
    """Detect file encoding and provide safe file reading."""

    # Class-level cache (shared across instances)
    _cache: Optional['EncodingCache'] = None

    # Fallback encodings in priority order
    FALLBACK_ENCODINGS = [
        "utf-8",
        "shift_jis",      # Japanese
        "euc-jp",         # Japanese
        "gbk",            # Chinese (Simplified)
        "gb2312",         # Chinese (older)
        "big5",           # Chinese (Traditional)
        "cp1252",         # Windows Western European
        "iso-8859-1",     # Latin-1
        "cp949",          # Korean
        "utf-16",
        "utf-16-le",
        "utf-16-be",
    ]

    # BOM (Byte Order Mark) signatures
    BOM_SIGNATURES = {
        b'\xef\xbb\xbf': 'utf-8',
        b'\xff\xfe': 'utf-16-le',
        b'\xfe\xff': 'utf-16-be',
        b'\xff\xfe\x00\x00': 'utf-32-le',
        b'\x00\x00\xfe\xff': 'utf-32-be',
    }

    def __init__(self, enable_cache: bool = True):
        """Initialize encoding detector."""
        if enable_cache and EncodingDetector._cache is None:
            EncodingDetector._cache = EncodingCache(max_size=500)
        self._enable_cache = enable_cache

    def detect_encoding(
        self,
        file_path: str | Path,
        sample_size: int = 32768  # 32KB sample
    ) -> str:
        """
        Detect file encoding.

        Detection strategy:
        1. Check cache (if enabled)
        2. Detect BOM (Byte Order Mark)
        3. Try UTF-8 decode
        4. Use chardet library (if available)
        5. Fallback to encodings list

        Returns:
            Encoding name (e.g., 'utf-8', 'shift_jis')
        """

    def read_file_safe(
        self,
        file_path: str | Path,
        fallback_encoding: str = "utf-8",
        errors: str = "replace"
    ) -> str:
        """
        Read entire file with automatic encoding detection.

        For files < 10MB. For larger files, use read_file_streaming().

        Returns:
            File content as string
        """

    def read_file_streaming(
        self,
        file_path: str | Path,
        chunk_size: int = 8192
    ) -> Generator[str, None, None]:
        """
        Stream file content line by line (memory-efficient).

        For files > 10MB. Memory usage: O(1) regardless of file size.

        Yields:
            Lines from file
        """

    def _detect_bom(self, data: bytes) -> Optional[str]:
        """Detect BOM signature."""

    def _try_decode(self, data: bytes, encoding: str) -> bool:
        """Try to decode sample data with given encoding."""

    def _use_chardet(self, data: bytes) -> Optional[str]:
        """Use chardet library for detection (if available)."""
```

### 2.2 Detection Flow

```
┌─────────────────────────────┐
│ detect_encoding(file_path)  │
└──────────┬──────────────────┘
           │
           ▼
    ┌──────────────┐
    │ Check Cache? │──Yes──▶ Return cached encoding
    └──────┬───────┘
           │ No
           ▼
    ┌──────────────┐
    │ Read 32KB    │
    │ sample       │
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │ Detect BOM?  │──Yes──▶ Return BOM encoding
    └──────┬───────┘
           │ No
           ▼
    ┌──────────────┐
    │ Try UTF-8?   │──Success──▶ Return 'utf-8'
    └──────┬───────┘
           │ Fail
           ▼
    ┌──────────────┐
    │ Use chardet? │──Available──▶ Return detected encoding
    └──────┬───────┘
           │ Not available
           ▼
    ┌──────────────────┐
    │ Try fallbacks:   │
    │ 1. shift_jis     │
    │ 2. gbk           │
    │ 3. cp1252        │
    │ ...              │
    └──────┬───────────┘
           │
           ▼
    Return first successful encoding or 'utf-8' as last resort
```

---

## 3. EncodingCache Class Design

### 3.1 Class Structure

```python
from collections import OrderedDict
from pathlib import Path
from typing import Optional
import threading

class EncodingCache:
    """
    Thread-safe LRU cache for encoding detection results.

    Simplified version of v1's cache (no TTL for v2).
    """

    def __init__(self, max_size: int = 500):
        """Initialize cache with maximum size."""
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, file_path: str | Path) -> Optional[str]:
        """
        Get cached encoding for file.

        Returns None if not cached or file was modified.
        Uses file path + mtime as cache key.
        """

    def set(self, file_path: str | Path, encoding: str) -> None:
        """
        Cache encoding for file.

        Implements LRU eviction when cache is full.
        """

    def clear(self) -> None:
        """Clear all cached entries."""

    def _get_cache_key(self, file_path: str | Path) -> str:
        """Generate cache key: path + mtime."""
        path = Path(file_path).resolve()
        mtime = path.stat().st_mtime
        return f"{path}:{mtime}"
```

### 3.2 Cache Key Strategy

```
Cache Key Format: "{absolute_path}:{mtime}"

Example:
  /path/to/file.py:1738425600.123456

Benefits:
- Automatic invalidation when file is modified (mtime changes)
- No need for TTL mechanism
- Simple and effective
```

---

## 4. Integration with Existing Tools

### 4.1 find_and_grep.py Changes

**Current Code (Line 171-174)**:
```python
# Read file content
with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
```

**New Code**:
```python
from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

# In __init__:
self._encoding_detector = EncodingDetector()

# In execute():
try:
    # Read file with automatic encoding detection
    content = self._encoding_detector.read_file_safe(file_path)
except Exception:
    # Skip files that can't be read
    continue
```

### 4.2 scale.py Changes

**Current Code (Line 151-153)**:
```python
def _calculate_file_metrics(self, file_path: Path) -> dict[str, Any]:
    content = file_path.read_text(encoding="utf-8")
```

**New Code**:
```python
from tree_sitter_analyzer_v2.utils.encoding import EncodingDetector

# In __init__:
self._encoding_detector = EncodingDetector()

# In _calculate_file_metrics():
content = self._encoding_detector.read_file_safe(file_path)
```

### 4.3 analyze.py Changes

Similar pattern - replace all `read_text(encoding='utf-8')` with `read_file_safe()`.

### 4.4 Large File Handling Strategy

For files > 10MB, switch to streaming:

```python
file_size = Path(file_path).stat().st_size
LARGE_FILE_THRESHOLD = 10 * 1024 * 1024  # 10MB

if file_size > LARGE_FILE_THRESHOLD:
    # Use streaming for large files
    line_count = 0
    for line in self._encoding_detector.read_file_streaming(file_path):
        line_count += 1
        # Process line by line
else:
    # Read entire file for small files
    content = self._encoding_detector.read_file_safe(file_path)
```

---

## 5. Error Handling Strategy

### 5.1 Encoding Detection Failures

```python
def detect_encoding(self, file_path: str | Path) -> str:
    """
    Always returns a valid encoding name.

    Fallback chain:
    1. Cache hit → return cached
    2. BOM detection → return BOM encoding
    3. UTF-8 try → return 'utf-8'
    4. chardet → return detected (if confidence > 0.7)
    5. Fallback list → return first successful
    6. Last resort → return 'utf-8'
    """
```

### 5.2 File Reading Failures

```python
def read_file_safe(self, file_path: str | Path, errors: str = "replace") -> str:
    """
    Uses 'replace' error handling by default.

    - Invalid bytes → replaced with U+FFFD (�)
    - Ensures file can always be read
    - No exceptions raised for encoding issues
    """
```

---

## 6. Dependencies

### 6.1 Required Dependencies

```toml
# pyproject.toml
[project.optional-dependencies]
encoding = [
    "chardet>=5.0.0",  # Encoding detection library
]
```

### 6.2 Graceful Degradation

```python
try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False

def _use_chardet(self, data: bytes) -> Optional[str]:
    """Use chardet if available, else return None."""
    if not HAS_CHARDET:
        return None

    result = chardet.detect(data)
    if result['confidence'] > 0.7:
        return result['encoding']
    return None
```

---

## 7. Performance Considerations

### 7.1 Sample Size Strategy

```python
# Small files (< 100KB): Read entire file
# Medium files (100KB - 10MB): Read 32KB sample
# Large files (> 10MB): Read 32KB sample + use streaming
```

### 7.2 Cache Hit Ratio

Expected cache hit ratio: **80-90%** for typical workflows.

Benefits:
- Avoid redundant chardet calls (expensive)
- Reduce file I/O
- Speed up repeated file access

### 7.3 Memory Usage

| Operation | Memory Usage | Notes |
|-----------|-------------|-------|
| detect_encoding() | O(1) | Only reads 32KB sample |
| read_file_safe() | O(n) | Loads entire file |
| read_file_streaming() | O(1) | Line-by-line iteration |

For 500MB file:
- Old approach (read_text): **500MB+ memory**
- New approach (streaming): **~8KB memory**

---

## 8. Testing Strategy

### 8.1 Test Files Required

Create `tests/fixtures/encoding_fixtures/`:

1. **japanese_shift_jis.txt** (Shift_JIS encoding)
   ```
   こんにちは世界
   日本語のテストファイル
   ```

2. **chinese_gbk.txt** (GBK encoding)
   ```
   你好世界
   中文测试文件
   ```

3. **utf16_bom.txt** (UTF-16 with BOM)
   ```
   UTF-16 encoded file with BOM
   ```

4. **mixed_encoding.txt** (Edge case - try UTF-8 first)

5. **large_file_mock.txt** (For streaming tests - can be generated)

### 8.2 Test Cases

**Unit Tests** (~15 tests):
1. test_detect_utf8
2. test_detect_shift_jis
3. test_detect_gbk
4. test_detect_utf16_bom
5. test_detect_with_cache
6. test_cache_invalidation_on_mtime_change
7. test_read_file_safe_utf8
8. test_read_file_safe_shift_jis
9. test_read_file_safe_with_errors
10. test_read_file_streaming
11. test_cache_lru_eviction
12. test_graceful_degradation_without_chardet
13. test_fallback_encodings
14. test_thread_safety
15. test_large_file_threshold

**Integration Tests** (~5 tests):
1. test_find_and_grep_with_japanese_files
2. test_find_and_grep_with_chinese_files
3. test_scale_with_large_file
4. test_analyze_with_mixed_encodings
5. test_end_to_end_encoding_detection

---

## 9. Migration Plan

### Phase 1: Core Implementation (TDD)
1. Create `utils/encoding.py`
2. Implement EncodingCache (5 tests)
3. Implement EncodingDetector.detect_encoding() (5 tests)
4. Implement read_file_safe() (3 tests)
5. Implement read_file_streaming() (2 tests)

### Phase 2: Integration
1. Modify find_and_grep.py (2 tests)
2. Modify scale.py (2 tests)
3. Modify analyze.py (1 test)

### Phase 3: Validation
1. Test with real Japanese files
2. Test with real Chinese files
3. Benchmark performance with 500MB+ files
4. Verify memory usage with streaming

---

## 10. Success Criteria

✅ **Functional Requirements**:
- Detect UTF-8, Shift_JIS, GBK, UTF-16, and other major encodings
- Handle files with BOM correctly
- Support streaming for files > 10MB
- Graceful fallback when chardet not available

✅ **Performance Requirements**:
- Cache hit ratio > 80%
- 500MB file processing: < 1GB memory usage
- No performance regression for small files (< 1MB)

✅ **Quality Requirements**:
- All tests passing (403 → ~423 tests)
- Test coverage > 85% for encoding module
- No hardcoded 'utf-8' in tool files
- Thread-safe cache implementation

---

## 11. Implementation Timeline

| Phase | Duration | Tests | Status |
|-------|----------|-------|--------|
| Phase 1: EncodingCache | 15min | 5 | Pending |
| Phase 1: detect_encoding() | 20min | 5 | Pending |
| Phase 1: read_file_safe() | 15min | 3 | Pending |
| Phase 1: read_file_streaming() | 15min | 2 | Pending |
| Phase 2: Integration | 20min | 5 | Pending |
| Phase 3: Validation | 15min | 3 | Pending |
| **Total** | **1.5-2h** | **23** | Pending |

---

## 12. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| chardet not installed | Medium | Graceful degradation to fallback encodings |
| Unknown encodings | Low | Always fallback to UTF-8 with 'replace' |
| Cache memory usage | Low | LRU eviction at 500 entries (~50KB) |
| Thread safety issues | Medium | Use threading.Lock for cache operations |
| Performance regression | Low | Benchmark before/after |

---

## Next Steps

1. **Begin TDD Phase 1**: Create encoding module with tests
2. **Validate with real files**: Test Japanese and Chinese content
3. **Benchmark**: Compare memory usage before/after for large files
4. **Document**: Update CHANGELOG.md with new feature
