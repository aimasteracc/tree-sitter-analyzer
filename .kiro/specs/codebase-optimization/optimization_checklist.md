# Optimization Checklist - Language Plugins

This checklist ensures complete and consistent optimization of all language plugin files.

## 🎯 Optimization Levels

- **Level 1** (Basic): Documentation and structure
- **Level 2** (Standard): Type hints and error handling  
- **Level 3** (Advanced): Performance and thread safety

---

## ✅ Complete Checklist

### Level 1: Documentation & Structure (DONE for Batch 1)

- [x] **Module Docstring** - Structured with all sections
  - Title: `[Language] Language Plugin - Enhanced [Language] Code Analysis`
  - Description paragraph
  - "Optimized with:" section (5+ items)
  - "Features:" section (6+ items)
  - "Architecture:" section (4+ items)
  - "Usage:" section with example
  - Metadata: Author, Version 1.10.5, Date 2026-01-28

- [x] **Import Organization**
  - Standard library imports (grouped and commented)
  - Third-party imports (if any)
  - TYPE_CHECKING block (basic)
  - Internal imports (grouped)
  - Logging configuration

- [x] **Module Exports**
  - `__all__: list[str]` at end of file
  - List extractor classes
  - List plugin classes

### Level 2: Type Safety & Error Handling (TODO)

- [ ] **Enhanced TYPE_CHECKING Block**
  ```python
  if TYPE_CHECKING:
      import tree_sitter
      from ..core.analysis_engine import AnalysisRequest
      from ..models import AnalysisResult
  else:
      # Runtime fallback
      tree_sitter = Any  # type: ignore[misc,assignment]
  ```

- [ ] **Custom Exception Hierarchy** (if plugin-specific errors needed)
  ```python
  class [Language]PluginError(Exception):
      """Base exception for [Language] plugin errors."""
      def __init__(self, message: str, exit_code: int = 1):
          super().__init__(message)
          self.exit_code = exit_code
  
  class [Language]ParseError([Language]PluginError):
      """Exception raised when parsing fails."""
      pass
  ```

- [ ] **Complete Type Hints**
  - All method parameters have type hints
  - All return values have type hints
  - Class attributes have type hints
  - No `Any` types except where necessary

- [ ] **Comprehensive Method Docstrings**
  - Brief one-line summary
  - Extended description
  - Args: section with all parameters
  - Returns: section with return type description
  - Raises: section with exceptions
  - Note: section for implementation details
  - Example: section (where helpful)

### Level 3: Performance & Thread Safety (TODO)

- [ ] **Performance Monitoring**
  - Import `from time import perf_counter`
  - Add timing to key methods:
    ```python
    start_time = perf_counter()
    try:
        # operation
        result = ...
        end_time = perf_counter()
        log_performance(f"Operation completed in {end_time - start_time:.4f}s")
        return result
    except Exception as e:
        end_time = perf_counter()
        log_error(f"Operation failed after {end_time - start_time:.4f}s: {e}")
        raise
    ```

- [ ] **LRU Caching** (where applicable)
  - Add `from functools import lru_cache` to imports
  - Apply `@lru_cache(maxsize=128)` to expensive pure functions
  - Example: language loading, query compilation

- [ ] **Thread Safety** (where needed)
  - Import `import threading`
  - Add locks for shared state:
    ```python
    _cache_lock: threading.RLock = threading.RLock()
    
    def _get_cached_result(self, key: str) -> Optional[ResultType]:
        with self._cache_lock:
            return self._cache.get(key)
    ```

- [ ] **Statistics Tracking** (for critical operations)
  ```python
  _stats: Dict[str, Any] = {
      "total_operations": 0,
      "cache_hits": 0,
      "cache_misses": 0,
      "errors": 0,
      "execution_times": [],
  }
  ```

---

## 📊 Plugin-Specific Considerations

### Language Plugins Don't Need (Inherited from Base):
- ❌ Complex caching systems (base class handles this)
- ❌ Thread locks (unless plugin has shared state)
- ❌ Custom protocols (base class defines interfaces)

### Language Plugins DO Need:
- ✅ Clear TYPE_CHECKING imports
- ✅ Performance monitoring for analyze_file()
- ✅ Comprehensive docstrings
- ✅ Plugin-specific exception classes (if custom errors)
- ✅ Complete type hints

---

## 🎯 Priority Assessment

### High Priority (Apply to all):
1. Enhanced TYPE_CHECKING block (better imports)
2. Complete method docstrings
3. Performance monitoring in analyze_file()

### Medium Priority (Apply where beneficial):
4. LRU caching for get_tree_sitter_language()
5. Plugin-specific exceptions (only if needed)

### Low Priority (Apply sparingly):
6. Thread locks (only if shared mutable state)
7. Statistics tracking (only for critical plugins)

---

## 📝 Current Status

### Batch 1 Plugins (7 files):
- **Level 1**: ✅ 100% Complete
- **Level 2**: ⏳ 0% Complete  
- **Level 3**: ⏳ 0% Complete

### What's Done:
- Module docstrings with metadata
- Basic import organization
- __all__ exports
- Files compile without errors

### What's Missing:
- Enhanced TYPE_CHECKING with fallbacks
- Complete method docstrings (many are basic)
- Performance monitoring
- LRU caching on expensive operations
- Plugin-specific exceptions (where needed)

---

## 🚀 Action Plan

### Phase A: Enhance TYPE_CHECKING (Quick Win)
- Update TYPE_CHECKING blocks in all 7 Batch 1 files
- Add proper runtime fallbacks
- Estimated time: 30 minutes

### Phase B: Method Documentation (High Value)
- Add comprehensive docstrings to all public methods
- Focus on analyze_file(), extract_elements(), get_extractor()
- Estimated time: 1-2 hours

### Phase C: Performance Monitoring (Critical Path)
- Add perf_counter() timing to analyze_file()
- Add LRU cache to get_tree_sitter_language()
- Estimated time: 45 minutes

### Phase D: Exception Handling (Optional)
- Add plugin-specific exceptions only where needed
- Most plugins can use base class exceptions
- Estimated time: 30 minutes (selective)

---

## 🔍 Verification Checklist

After optimization, verify:
- [ ] File compiles: `python -m py_compile <file>`
- [ ] Type checking: `mypy <file>` (when utils/__init__.py fixed)
- [ ] Imports work: `python -c "from tree_sitter_analyzer.languages import <Plugin>"`
- [ ] All public methods documented
- [ ] Performance logging present
- [ ] __all__ exports complete

---

## 📚 Reference Files

**Fully Optimized Examples:**
- `tree_sitter_analyzer/core/parser.py` - Complete Level 1-3 optimization
- `tree_sitter_analyzer/core/query.py` - Exception handling patterns
- `tree_sitter_analyzer/models/element.py` - Data class patterns

**Current State:**
- `tree_sitter_analyzer/languages/*_plugin.py` - Level 1 complete, Level 2-3 needed
