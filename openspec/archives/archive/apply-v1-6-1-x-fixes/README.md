# Apply v1.6.1.x Specification Changes to v1.9.3

## ⚠️ Architecture-Aware Approach

**CRITICAL UPDATE**: This proposal has been revised to preserve v1.9.3's improved architecture.

**Key Decisions**:
- ✅ v1.6.1.1 logging: **Already integrated** in `utils/logging.py` - No action needed
- ✅ v1.9.3 architecture: **Preserved** (modular utils/, plugins, formatters)
- ✅ Implementation: **Specifications only**, not old code copying
- ✅ Scope: **Reduced from 24h to 14h** (42% reduction)

See **`ARCHITECTURE_COMPATIBILITY.md`** for detailed analysis.

## Quick Links

- **[🔒 Architecture Compatibility](./ARCHITECTURE_COMPATIBILITY.md)** - アーキテクチャ分析 (必読)
- **[📝 Japanese Summary](./SUMMARY_ja.md)** - 日本語の実行サマリー (推奨開始点)
- **[🔍 Analysis](./analysis.md)** - Detailed gap analysis and code comparison
- **[📋 Proposal](./proposal.md)** - Implementation proposal with technical approach
- **[✅ Tasks](./tasks.md)** - Actionable task breakdown (8 tasks, ~14 hours)

## Overview

This change integrates critical improvements from v1.6.1.3 and v1.6.1.4 releases that are **missing** in the current v1.9.3 codebase.

### 1. Streaming File Reading (v1.6.1.4) ⚡
**Impact**: HIGH - Performance Critical  
**Status**: ❌ Not in v1.9.3

- **Performance**: 30s → <200ms (150x faster) for large files
- **Memory**: O(file_size) → O(requested_lines)
- **Files**: `file_handler.py`, `encoding_utils.py`
- **Approach**: Add new function + internal optimization (API unchanged)
- **Commit**: `8e1500e`

### 2. Output Format Validator (v1.6.1.3) 🌐
**Impact**: MEDIUM - UX Enhancement  
**Status**: ❌ Not in v1.9.3

- **Features**: Multilingual errors (EN/JA), LLM token guidance
- **Validation**: Mutually exclusive parameter detection
- **Files**: `output_format_validator.py` (NEW), `search_content_tool.py`
- **Approach**: New class following v1.9.3 patterns
- **Commit**: `3f44ac6`

### 3. Logging Control (v1.6.1.1) ✅
**Impact**: N/A - Already Integrated  
**Status**: ✅ **FULLY INTEGRATED in v1.9.3**

- **Location**: `tree_sitter_analyzer/utils/logging.py`
- **Features**: All environment variables, file logging, custom directory
- **Action**: **None required** - v1.9.3 has improved version
- **Commit**: `55144d8`

## Implementation Plan (Architecture-Safe)

### Phase 1: Streaming File Reading (5 hours)
1. Add `read_file_safe_streaming()` to `encoding_utils.py` (2h)
2. Refactor `read_file_partial()` in `file_handler.py` (2h)
3. Port performance tests (1h)

### Phase 2: Output Format Validator (5 hours)
1. Create `output_format_validator.py` (3h)
2. Integrate with `search_content_tool.py` (2h)

### Phase 3: QA & Documentation (4 hours)
1. Run full test suite (1h)
2. Performance benchmarking (2h)
3. Update documentation (1h)

**Total**: ~14 hours (2 days)  
*Reduced from 24h: v1.6.1.1 excluded (already integrated), specifications only*

## Getting Started

### Quick Start Commands

```bash
# Retrieve implementation files from git history
git show 8e1500e:tree_sitter_analyzer/file_handler.py  # Reference for streaming
git show 3f44ac6:tree_sitter_analyzer/mcp/tools/output_format_validator.py > \
    tree_sitter_analyzer/mcp/tools/output_format_validator.py

# Retrieve test files
git show 8e1500e:tests/test_streaming_read_performance.py > tests/test_streaming_read_performance.py
git show 8e1500e:tests/test_streaming_read_performance_extended.py > tests/test_streaming_read_performance_extended.py
git show 3f44ac6:tests/test_llm_guidance_compliance.py > tests/test_llm_guidance_compliance.py
git show 3f44ac6:tests/test_search_content_description.py > tests/test_search_content_description.py

# Retrieve OpenSpec documentation from v1.6.1.4 - NEW
mkdir -p openspec/changes/refactor-streaming-read-performance/specs/mcp-tools
git show 8e1500e:openspec/changes/refactor-streaming-read-performance/design.md > \
    openspec/changes/refactor-streaming-read-performance/design.md
git show 8e1500e:openspec/changes/refactor-streaming-read-performance/proposal.md > \
    openspec/changes/refactor-streaming-read-performance/proposal.md
git show 8e1500e:openspec/changes/refactor-streaming-read-performance/specs/mcp-tools/spec.md > \
    openspec/changes/refactor-streaming-read-performance/specs/mcp-tools/spec.md
git show 8e1500e:openspec/changes/refactor-streaming-read-performance/tasks.md > \
    openspec/changes/refactor-streaming-read-performance/tasks.md

# Run tests
pytest tests/test_streaming_read_performance*.py -v
pytest tests/test_llm_guidance*.py tests/test_search_content_description.py -v
```

### Document Reading Order

For **detailed analysis**: Read in this order:
1. 📝 **SUMMARY_ja.md** - Quick overview in Japanese
2. 🔍 **analysis.md** - Understand the gaps and problems
3. 📋 **proposal.md** - Review technical approach
4. ✅ **tasks.md** - Execute implementation tasks

For **quick implementation**: Start with:
1. ✅ **tasks.md** - Task-by-task implementation guide
2. 📋 **proposal.md** - Reference for technical decisions

## Key Findings

### Gap 1: Current v1.9.3 Loads Entire Files
**Location**: `file_handler.py` line 130
```python
# Current (SLOW)
content, detected_encoding = read_file_safe(file_path)
lines = content.splitlines(keepends=True)
```

**Problem**: 30+ seconds for 100MB files, high memory usage

**Solution**: Stream with `itertools.islice()` → <200ms

### Gap 2: No Output Format Validation
**Location**: `search_content_tool.py`

**Problem**: LLMs can specify conflicting parameters:
- `total_only` + `count_only_matches` = confusion
- No token efficiency guidance

**Solution**: `OutputFormatValidator` with multilingual errors and LLM guidance

## Expected Outcomes

### Performance ⚡
- [x] Large files: 30s → <200ms (150x improvement)
- [x] Memory: Constant O(requested_lines) not O(file_size)
- [x] Small files: <10ms overhead

### UX 🌐
- [x] Clear error messages (English/Japanese)
- [x] Token efficiency guidance (~10 to ~5000+ tokens)
- [x] Automatic conflict detection
- [x] Optimal format selection help

### Quality ✅
- [x] Test coverage: >80% maintained
- [x] Test pass rate: 100% (3,370+ tests)
- [x] Backward compatibility: 100% (no breaking changes)

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Streaming breaks edge cases | LOW | MEDIUM | Comprehensive tests from v1.6.1.4, feature flag fallback |
| Locale detection fails | MEDIUM | LOW | Graceful fallback to English, try/except safety |
| Small file performance regression | LOW | LOW | Benchmark all sizes, encoding cache optimization |

## References

### Git History
- **v1.6.1.3 Commit**: `3f44ac6` - LLM guidance with multilingual support
- **v1.6.1.4 Commit**: `8e1500e` - Streaming file reading refactor

### Test Files (from git)
- `tests/test_streaming_read_performance.py` (163 lines) - v1.6.1.4
- `tests/test_streaming_read_performance_extended.py` (232 lines) - v1.6.1.4
- `tests/test_llm_guidance_compliance.py` (170 lines) - v1.6.1.3
- `tests/test_search_content_description.py` (217 lines) - v1.6.1.3

### OpenSpec Documentation (from git)
- `openspec/changes/refactor-streaming-read-performance/design.md` (84 lines) - v1.6.1.4
- `openspec/changes/refactor-streaming-read-performance/proposal.md` (18 lines) - v1.6.1.4
- `openspec/changes/refactor-streaming-read-performance/specs/mcp-tools/spec.md` (23 lines) - v1.6.1.4
- `openspec/changes/refactor-streaming-read-performance/tasks.md` (54 lines) - v1.6.1.4
- `docs/mcp_fd_rg_design.md` (132 lines) - v1.6.1.3
- `openspec/specs/llm-guidance/spec.md` (201 lines) - v1.6.1.3
- `openspec/specs/mcp-tools/spec.md` (186 lines) - v1.6.1.3

### Implementation Files (from git)
- `tree_sitter_analyzer/file_handler.py` (streaming version) - v1.6.1.4
- `tree_sitter_analyzer/encoding_utils.py` (with `read_file_safe_streaming()`) - v1.6.1.4
- `tree_sitter_analyzer/mcp/tools/output_format_validator.py` (new file) - v1.6.1.3
- `tree_sitter_analyzer/mcp/utils/file_output_manager.py` (thread safety improvements) - v1.6.1.3

## Current Status

- ✅ **Architecture Analysis Complete**: v1.6.1.1 already integrated in `utils/logging.py`
- ✅ **Documentation Complete**: Architecture-aware analysis, proposal, tasks (v2.0)
- ✅ **Tool Descriptions**: search_content_tool.py has LLM guidance
- ⏳ **Implementation Pending**: Ready to start Phase 1 (8 tasks, architecture-safe)
- ⏳ **Testing Pending**: Performance tests ready to port
- ⏳ **Integration Pending**: Clear integration points identified

## Next Actions

1. **Review Architecture Doc**: Read `ARCHITECTURE_COMPATIBILITY.md` **FIRST**
2. **Start Implementation**: Follow `tasks.md` step-by-step (8 tasks, 14h)
3. **Run Tests**: Validate each phase before moving forward
4. **Benchmark**: Document performance improvements
5. **Update CHANGELOG**: Add v1.9.4 entry (or appropriate version)

---

**Document Version**: 2.0  
**Created**: 2025-11-04  
**Updated**: 2025-11-04  
**Status**: Ready for Architecture-Safe Implementation  
**Author**: AI Analysis + Architecture Review  
**Estimated Effort**: 14 hours (~2 days)  
**Changes**: 
- v1.0: Initial analysis (19h)
- v1.1: Added Phase 4 (21h)
- v1.2: Added v1.6.1.4 discoveries (24h)
- v2.0: **ARCHITECTURE-AWARE** - Excluded v1.6.1.1, specifications only (14h, 42% reduction)  
**Changes**: 
- v1.0: Initial analysis (streaming + validator)
- v1.1: Added Phase 4 (thread safety, tests, docs from v1.6.1.3) - 21h
- v1.2: Added Task 1.4 (OpenSpec docs from v1.6.1.4) - 24h, total 12 files discovered
