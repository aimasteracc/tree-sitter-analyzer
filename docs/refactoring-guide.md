# Plugin Refactoring Guide

## Overview

This guide explains how to refactor existing language plugins to use the new base classes and mixins, reducing code duplication and improving maintainability.

## New Infrastructure

### Base Classes

1. **ElementExtractorBase** - Comprehensive base class combining all mixins
2. **CacheManagementMixin** - Cache initialization and reset functionality
3. **NodeTraversalMixin** - AST traversal with batch processing
4. **NodeTextExtractionMixin** - Optimized text extraction with caching

## Migration Example

### Before (Current Implementation)

```python
class JavaElementExtractor(ElementExtractor):
    def __init__(self) -> None:
        self.current_package: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        
        # Duplicated cache initialization
        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[int] = set()
        self._element_cache: dict[tuple[int, str], Any] = {}
        # ... more initialization
    
    def _reset_caches(self) -> None:
        """Reset performance caches"""
        self._node_text_cache.clear()
        self._processed_nodes.clear()
        self._element_cache.clear()
        # ... more cache clearing
    
    def _traverse_and_extract_iterative(
        self, root_node, extractors, results, element_type
    ) -> None:
        """Duplicated traversal logic"""
        # ... 100+ lines of traversal code
```

### After (Using Base Classes)

```python
from tree_sitter_analyzer.plugins import ElementExtractorBase

class JavaElementExtractor(ElementExtractorBase):
    def __init__(self) -> None:
        super().__init__()  # Initializes all caches automatically
        self.current_package: str = ""
        self.current_file: str = ""
        # No need to duplicate cache initialization!
    
    # _reset_caches() is inherited from ElementExtractorBase
    # _traverse_and_extract_iterative() is inherited from NodeTraversalMixin
    # _get_node_text_optimized() is inherited from NodeTextExtractionMixin
    
    def extract_functions(self, tree, source_code):
        self.source_code = source_code
        self.content_lines = source_code.split("\n")
        self._reset_caches()  # Inherited method
        
        functions: list[Function] = []
        extractors = {
            "method_declaration": self._extract_method_optimized,
            "constructor_declaration": self._extract_method_optimized,
        }
        
        # Use inherited traversal method
        self._traverse_and_extract_iterative(
            tree.root_node, extractors, functions, "method"
        )
        
        return functions
```

## Benefits

### Code Reduction
- **Java plugin**: ~200 lines of duplicated code eliminated
- **Python plugin**: ~180 lines eliminated  
- **SQL plugin**: ~220 lines eliminated
- **Total estimated reduction**: ~1500+ lines across all plugins

### Consistency
- All plugins use the same caching strategy
- Same traversal algorithm ensures predictable behavior
- Easier to maintain and debug

### Performance
- Optimized caching is implemented once
- Batch processing for fields is standardized
- Position-based cache keys prevent collisions

## Step-by-Step Migration

1. **Update imports**
   ```python
   from tree_sitter_analyzer.plugins import ElementExtractorBase
   ```

2. **Update class declaration**
   ```python
   class MyLanguageExtractor(ElementExtractorBase):
       # Instead of ElementExtractor
   ```

3. **Remove duplicated initialization**
   ```python
   def __init__(self):
       super().__init__()  # This handles cache initialization
       # Keep only language-specific state
   ```

4. **Remove duplicated methods**
   - Delete `_reset_caches()` (inherited)
   - Delete `_traverse_and_extract_iterative()` (inherited)
   - Delete `_get_node_text_optimized()` (inherited)
   - Delete `_fallback_text_extraction()` (inherited)

5. **Update method calls**
   - Replace any custom traversal with `self._traverse_and_extract_iterative()`
   - Use `self._get_node_text_optimized()` for text extraction

6. **Run tests**
   ```bash
   pytest tests/unit/languages/test_<language>_plugin.py -v
   ```

## Testing

New tests are available in `tests/unit/plugins/test_extractor_mixin.py`:

```bash
pytest tests/unit/plugins/test_extractor_mixin.py -v
```

These tests verify:
- Cache initialization and reset
- AST traversal functionality
- Text extraction with caching
- Integration with language plugins

## Estimated Impact

| Plugin | Lines Before | Lines After | Reduction |
|--------|--------------|-------------|-----------|
| SQL | 2462 | ~2240 | ~9% |
| Markdown | 1973 | ~1790 | ~9% |
| TypeScript | 1893 | ~1710 | ~10% |
| Python | 1640 | ~1460 | ~11% |
| JavaScript | 1619 | ~1440 | ~11% |
| Java | 1292 | ~1090 | ~16% |

**Total codebase reduction**: ~1000-1500 lines
**Maintenance improvement**: Significant (common bugs fixed once)
**Performance**: Consistent across all plugins

## Next Steps

1. Migrate one plugin as a pilot (recommend: Java plugin)
2. Verify all tests pass
3. Document any language-specific adjustments needed
4. Migrate remaining plugins
5. Remove deprecated code patterns

## Questions?

Refer to:
- `tree_sitter_analyzer/plugins/extractor_mixin.py` - Implementation
- `tests/unit/plugins/test_extractor_mixin.py` - Test examples
- This document - Migration guide
