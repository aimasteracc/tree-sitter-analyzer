# Proposal: Apply v1.6.1.x Specification Changes to v1.9.3

## ⚠️ Architecture-Aware Approach

**CRITICAL**: This proposal has been updated to preserve v1.9.3's improved architecture.

**Guiding Principles**:
1. ✅ Apply **specification changes only**, not old implementation code
2. ✅ Respect v1.9.3's modular structure (`utils/`, plugins, formatters)
3. ✅ Avoid architecture regression (v1.6.1.1 logging already integrated)
4. ✅ Add new features using v1.9.3 patterns

**Updated Scope**: 
- v1.6.1.1: ❌ **Excluded** (already integrated in `utils/logging.py`)
- v1.6.1.3: ✅ **Include** (OutputFormatValidator - new class only)
- v1.6.1.4: ✅ **Include** (Streaming - new function + internal optimization)

See `ARCHITECTURE_COMPATIBILITY.md` for detailed analysis.

## Overview

This proposal outlines the integration of two critical improvements from v1.6.1.3 and v1.6.1.4 releases into the current v1.9.3 codebase: **Streaming File Reading** for 150x performance improvement and **OutputFormatValidator** for enhanced LLM interactions with multilingual support.

**Architecture Note**: v1.6.1.1 logging features are already present in v1.9.3's `tree_sitter_analyzer/utils/logging.py`.

## User Value

### For End Users
1. **Drastically Faster Code Extraction**: Large file operations reduced from 30 seconds to <200ms
2. **Lower Memory Usage**: Streaming approach prevents memory exhaustion on large files
3. **Better Error Messages**: Multilingual support (English/Japanese) for output format conflicts
4. **Improved Reliability**: No more out-of-memory errors on large codebases

### For LLM Interactions
1. **Clear Guidance**: Token efficiency information for each output format
2. **Conflict Prevention**: Automatic detection of mutually exclusive parameters
3. **Optimized Token Usage**: Helps LLMs choose the most efficient format
4. **Consistent Experience**: Uniform error messages across all MCP tools

## Change Summary

### 1. Streaming File Reading (v1.6.1.4)
**Impact**: HIGH - Performance Critical  
**Complexity**: MEDIUM  
**Risk**: LOW

**Changes**:
- Add `read_file_safe_streaming()` context manager to `encoding_utils.py`
- Refactor `read_file_partial()` in `file_handler.py` to use streaming
- Port performance tests from v1.6.1.4

**Backward Compatibility**: 100% - Same function signatures, internal optimization only

### 2. Output Format Validator (v1.6.1.3)
**Impact**: MEDIUM - UX Enhancement  
**Complexity**: LOW  
**Risk**: LOW

**Changes**:
- Create new `tree_sitter_analyzer/mcp/tools/output_format_validator.py`
- Integrate validator into `search_content_tool.py`
- Add multilingual error messages (English/Japanese)
- Port LLM guidance tests

**Backward Compatibility**: 100% - Additive only, no breaking changes

## Technical Approach

### Phase 1: Streaming File Reading

#### 1.1 Add `read_file_safe_streaming()` to `encoding_utils.py`
```python
@contextlib.contextmanager
def read_file_safe_streaming(file_path: str | Path):
    """
    Context manager for streaming file reading with automatic encoding detection.
    
    Memory-efficient for large files as it doesn't load entire content.
    """
    file_path = Path(file_path)
    
    # Detect encoding from first 8KB
    with open(file_path, "rb") as f:
        sample_data = f.read(8192)
    
    detected_encoding = EncodingManager.detect_encoding(sample_data, str(file_path))
    
    # Open for streaming with detected encoding
    @contextlib.contextmanager
    def _file_context():
        with open(file_path, "r", encoding=detected_encoding, errors="replace") as f:
            yield f
    
    return _file_context()
```

#### 1.2 Refactor `read_file_partial()` in `file_handler.py`
**Before** (Current v1.9.3):
```python
# Read whole file safely
content, detected_encoding = read_file_safe(file_path)
lines = content.splitlines(keepends=True)
```

**After** (v1.6.1.4 approach):
```python
# Use streaming approach for memory efficiency
with read_file_safe_streaming(file_path) as f:
    # Use itertools.islice for efficient line selection
    if end_idx is not None:
        selected_lines_iter = itertools.islice(f, start_idx, end_idx + 1)
    else:
        selected_lines_iter = itertools.islice(f, start_idx, None)
    
    selected_lines = list(selected_lines_iter)
```

#### 1.3 Import Required Modules
Add to `file_handler.py`:
```python
import itertools
from .encoding_utils import read_file_safe, read_file_safe_streaming
```

### Phase 2: Output Format Validator

#### 2.1 Create `output_format_validator.py`
New file: `tree_sitter_analyzer/mcp/tools/output_format_validator.py`

**Key Components**:
- `OutputFormatValidator` class
- `OUTPUT_FORMAT_PARAMS` set (5 mutually exclusive params)
- `FORMAT_EFFICIENCY_GUIDE` dict (token estimates)
- `_detect_language()` method (LANG env var + locale)
- `_get_error_message()` method (English/Japanese)
- `validate_and_get_guidance()` method (main API)

#### 2.2 Integrate with `search_content_tool.py`
Modify `SearchContentTool.validate_arguments()`:
```python
def validate_arguments(self, arguments: dict[str, Any]) -> bool:
    """Validate tool arguments including output format conflicts."""
    
    # Existing validation...
    
    # Add output format validation
    from .output_format_validator import OutputFormatValidator
    
    validator = OutputFormatValidator()
    is_valid, message = validator.validate_and_get_guidance(arguments)
    
    if not is_valid:
        raise ValueError(message)
    
    if message:  # Guidance message
        logger.debug(message)
    
    return True
```

### Phase 3: Testing

#### 3.1 Port Streaming Performance Tests
Files from v1.6.1.4:
- `tests/test_streaming_read_performance.py` (163 lines)
- `tests/test_streaming_read_performance_extended.py` (232 lines)

**Test Coverage**:
- Large file performance (100MB+)
- Memory usage validation
- Line range selection accuracy
- Column range handling
- Encoding detection correctness
- Edge cases (empty files, beyond EOF)

#### 3.2 Port LLM Guidance Tests
Files from v1.6.1.3:
- `tests/test_llm_guidance_compliance.py` (170 lines)
- `tests/test_search_content_description.py` (217 lines)

**Test Coverage**:
- Mutual exclusivity detection
- Multilingual error messages
- Locale detection (English/Japanese)
- Token efficiency guidance
- Integration with search_content tool

## Acceptance Criteria

### Streaming File Reading
- [ ] `read_file_safe_streaming()` added to `encoding_utils.py`
- [ ] `read_file_partial()` refactored to use streaming
- [ ] All existing tests pass (3,370+ tests)
- [ ] Performance tests show <200ms for 100MB files
- [ ] Memory usage tests show O(requested_lines) not O(file_size)
- [ ] Backward compatibility verified (same function signatures)

### Output Format Validator
- [ ] `output_format_validator.py` created with complete implementation
- [ ] Integration with `search_content_tool.py` completed
- [ ] English and Japanese error messages working
- [ ] Locale detection functioning correctly
- [ ] LLM guidance tests passing
- [ ] No breaking changes to existing MCP tool interfaces

### Overall Quality
- [ ] Test coverage maintained at >80%
- [ ] No new pylint/mypy errors
- [ ] Documentation updated (if needed)
- [ ] Performance benchmarks documented
- [ ] Change log updated with improvements

## Implementation Timeline

### Day 1: Streaming File Reading
- Morning: Implement `read_file_safe_streaming()` in `encoding_utils.py`
- Afternoon: Refactor `read_file_partial()` in `file_handler.py`
- Evening: Port and run performance tests

### Day 2: Output Format Validator
- Morning: Create `output_format_validator.py` with multilingual support
- Afternoon: Integrate with `search_content_tool.py`
- Evening: Port and run LLM guidance tests

### Day 3: Testing & Validation
- Morning: Run full test suite, fix any issues
- Afternoon: Performance benchmarking and documentation
- Evening: Code review and final adjustments

## Risks & Mitigation

### Risk 1: Streaming Breaks Edge Cases
**Likelihood**: LOW  
**Impact**: MEDIUM  
**Mitigation**: 
- Comprehensive test coverage from v1.6.1.4
- Keep old implementation as fallback (feature flag)
- Staged rollout with monitoring

### Risk 2: Locale Detection Fails in Some Environments
**Likelihood**: MEDIUM  
**Impact**: LOW  
**Mitigation**:
- Graceful fallback to English if locale detection fails
- Default to 'en' if LANG env var not set
- Try/except around locale module imports

### Risk 3: Performance Regression on Small Files
**Likelihood**: LOW  
**Impact**: LOW  
**Mitigation**:
- Benchmark small files (<1MB) to ensure no overhead
- Encoding detection caching already implemented
- Use adaptive strategy if needed (streaming vs. full read based on size)

## Dependencies

### Internal
- Existing `EncodingManager` in `encoding_utils.py` ✅
- Existing `read_file_safe()` function ✅
- Existing `search_content_tool.py` structure ✅

### External
- `itertools` (standard library) ✅
- `contextlib` (standard library) ✅
- `locale` (standard library) ✅
- No new third-party dependencies required

## Success Metrics

### Performance Metrics
- **Large File Read Time**: 30s → <200ms (150x improvement)
- **Memory Usage**: File size → Requested lines only
- **Small File Overhead**: <10ms additional latency

### Quality Metrics
- **Test Coverage**: Maintain >80% coverage
- **Test Pass Rate**: 100% (3,370+ tests)
- **Error Rate**: No new errors in production MCP interactions

### UX Metrics
- **LLM Error Clarity**: 100% clear error messages for format conflicts
- **Token Optimization**: Measurable reduction in unnecessary verbose outputs
- **Multilingual Support**: Verified Japanese locale detection

## Alternative Approaches Considered

### Alternative 1: Lazy Loading Instead of Streaming
**Rejected**: More complex, same memory usage, worse performance for sequential reads

### Alternative 2: Async/Await for File Operations
**Rejected**: Adds complexity, minimal benefit for current use case, breaking changes

### Alternative 3: Basic Validator Without Multilingual Support
**Rejected**: Incomplete port from v1.6.1.3, loses valuable UX improvement

### Alternative 4: Separate Tool for Format Validation
**Rejected**: Increases complexity, harder for LLMs to discover and use

## References

- **v1.6.1.3 Implementation**: Git commit `3f44ac6`
- **v1.6.1.4 Implementation**: Git commit `8e1500e`
- **Analysis Document**: `analysis.md` in this directory
- **Original OpenSpec (v1.6.1.4)**: `openspec/changes/refactor-streaming-read-performance/`

---

**Proposal Version**: 1.0  
**Status**: Draft  
**Created**: 2025-01-XX  
**Approval Required**: Technical Lead, Product Owner
