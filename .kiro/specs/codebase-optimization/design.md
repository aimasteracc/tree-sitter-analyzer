# Design - Codebase Optimization Patterns

## Overview

This document defines the optimization patterns and rules extracted from commits 9a11878..HEAD that must be applied to all remaining unoptimized files in the tree-sitter-analyzer codebase.

## Technology Choices

### Python Standards
- **PEP 484**: Type Hints (100% coverage required)
- **PEP 257**: Docstring Conventions (English-only)
- **PEP 8**: Style Guide (enforced via ruff)
- **Python Version**: 3.10+ (maintain backward compatibility where possible)

### Type Checking
- **Runtime**: TYPE_CHECKING conditional imports
- **Static**: mypy compliance (strict mode)
- **Protocols**: Python 3.8+ compatibility pattern

### Performance Tools
- **Caching**: functools.lru_cache + custom LRU with threading.RLock
- **Monitoring**: time.perf_counter() for execution timing
- **Hashing**: hashlib.sha256 for cache keys

### Documentation
- **Language**: English-only (no mixed languages)
- **Format**: Google/NumPy style docstrings
- **Version**: Synchronized across all files (1.10.5)

## Architectural Design

### Pattern Categories

The optimization follows a layered pattern approach:

```
┌─────────────────────────────────────────────┐
│ 1. Module Docstring (Standardized Header)  │
├─────────────────────────────────────────────┤
│ 2. Import Organization (TYPE_CHECKING)     │
├─────────────────────────────────────────────┤
│ 3. Logging Configuration                   │
├─────────────────────────────────────────────┤
│ 4. Type Definitions (Protocols, Enums)     │
├─────────────────────────────────────────────┤
│ 5. Custom Exceptions (Hierarchy)           │
├─────────────────────────────────────────────┤
│ 6. Data Classes (Immutable Models)         │
├─────────────────────────────────────────────┤
│ 7. Main Implementation (with Caching)      │
├─────────────────────────────────────────────┤
│ 8. Convenience Functions (Singletons)      │
├─────────────────────────────────────────────┤
│ 9. Module Exports (__all__)                │
└─────────────────────────────────────────────┘
```

## Implementation Details

### 1. Module Docstring Pattern

**Template:**
```python
#!/usr/bin/env python3
"""
[Title] - [Component Type] for [Purpose]

This module provides [detailed description of functionality].

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling and recovery
- LRU caching for performance
- [Component-specific optimizations]
- Detailed documentation

Features:
- [Feature 1]
- [Feature 2]
- [Feature 3]
- Type-safe operations (PEP 484)

Architecture:
- Layered design with clear separation of concerns
- Performance optimization with LRU caching
- Thread-safe operations where applicable
- Integration with [related components]

Usage:
    >>> from tree_sitter_analyzer.[path] import [Class]
    >>> [usage example]

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""
```

**Rules:**
- Always start with shebang `#!/usr/bin/env python3`
- Title format: `[Component Name] - [Type] for [Domain]`
- Include all sections: Description, Optimized with, Features, Architecture, Usage
- Metadata: Author, Version (1.10.5), Date (2026-01-28)
- English-only, no mixed languages

### 2. Import Organization Pattern

**Standard Structure:**
```python
# Standard library imports (alphabetical, grouped by category)
import hashlib
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache, wraps
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any, Optional, List, Dict, Tuple, Union, Callable, Type, NamedTuple, Set

# Type checking setup
if TYPE_CHECKING:
    # Type-checking imports (heavy dependencies, circular imports)
    from tree_sitter import Tree, Language, Node
    from ..core.cache_service import CacheService
    from ..utils.logging import log_debug, log_info, log_warning, log_error, log_performance
else:
    # Runtime imports (lightweight fallbacks)
    Tree = Any
    Language = Any
    Node = Any

    # Critical runtime dependencies
    from ..utils.logging import log_debug, log_info, log_warning, log_error, log_performance

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
```

**Rules:**
- **Group 1**: Standard library (alphabetical within groups)
- **Group 2**: TYPE_CHECKING conditional block
- **Group 3**: Logging configuration (after imports)
- Use `TYPE_CHECKING` for all heavy/circular dependencies
- Always provide `Any` fallbacks for type-only imports
- Import utility functions from `..utils.logging`

### 3. Type Hint Patterns

**Protocol Backward Compatibility:**
```python
if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    Protocol = object

class ComponentProtocol(Protocol):
    """Interface for component implementations."""

    def method(self, arg: str) -> Optional[Any]:
        """
        Method documentation.

        Args:
            arg: Argument description

        Returns:
            Return value description
        """
        ...
```

**Comprehensive Type Annotations:**
```python
# All function signatures must include type hints
def process_file(
    self,
    file_path: Union[str, Path],
    options: Optional[Dict[str, Any]] = None,
    *,
    cache: bool = True,
    timeout: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Process file with options.

    Args:
        file_path: Path to file (string or Path object)
        options: Optional configuration dictionary
        cache: Enable caching (keyword-only)
        timeout: Timeout in seconds (keyword-only)

    Returns:
        Tuple of (success flag, error message or None)
    """
    ...
```

**Rules:**
- **100% coverage**: All parameters, return values, class attributes
- Use `Union[Type1, Type2]` for multiple types (or `Type1 | Type2` in Python 3.10+)
- Use `Optional[Type]` for nullable values
- Generic types must be fully parameterized: `Dict[str, Any]`, `List[str]`
- Keyword-only args use `*` separator

### 4. Exception Handling Pattern

**Custom Exception Hierarchy:**
```python
# ============================================================================
# Custom Exceptions
# ============================================================================

class [Component]Error(Exception):
    """Base exception for [component] errors."""

    def __init__(self, message: str, exit_code: int = 1):
        """
        Initialize exception.

        Args:
            message: Error message
            exit_code: Exit code for CLI (default: 1)
        """
        super().__init__(message)
        self.exit_code = exit_code


class InitializationError([Component]Error):
    """Exception raised when [component] initialization fails."""
    pass


class ExecutionError([Component]Error):
    """Exception raised when execution fails."""
    pass


class ValidationError([Component]Error):
    """Exception raised when validation fails."""
    pass


class CacheError([Component]Error):
    """Exception raised when caching fails."""
    pass
```

**Exception Handling in Methods:**
```python
def method(self, arg: str) -> ResultType:
    """Method documentation."""
    try:
        # Operation
        result = self._perform_operation(arg)
        return result
    except SpecificError as e:
        log_error(f"Operation failed for {arg}: {e}")
        raise CustomError(f"Failed to process {arg}: {e}") from e
    except Exception as e:
        log_error(f"Unexpected error in method: {e}")
        raise CustomError(f"Unexpected error: {e}") from e
```

**Rules:**
- Base exception includes `exit_code` for CLI integration
- Specific exception types before generic `Exception`
- Always log errors before raising
- Preserve stack traces with `from e`
- Error messages should be informative with context

### 5. Performance Optimization Pattern

**LRU Caching with Thread Safety:**
```python
class Component:
    """Component with caching."""

    # Class-level cache (shared across instances)
    _cache: Dict[str, ResultType] = {}
    _lock: threading.RLock = threading.RLock()
    _stats: Dict[str, Any] = {
        "total_operations": 0,
        "successful_operations": 0,
        "failed_operations": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "execution_times": [],
    }

    def _generate_cache_key(self, *args: Any, **kwargs: Any) -> str:
        """
        Generate deterministic cache key with file metadata.

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            SHA-256 hash of key components
        """
        key_components = [str(arg) for arg in args]
        key_components.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))

        # Include file metadata for cache invalidation
        if "file_path" in kwargs and os.path.exists(kwargs["file_path"]):
            stat = os.stat(kwargs["file_path"])
            key_components.extend([str(int(stat.st_mtime)), str(stat.st_size)])

        key_str = ":".join(key_components)
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()

    def _get_cached_result(self, key: str) -> Optional[ResultType]:
        """
        Thread-safe cache retrieval.

        Args:
            key: Cache key

        Returns:
            Cached result or None
        """
        with self._lock:
            if key in self._cache:
                self._stats["cache_hits"] += 1
                log_debug(f"Cache hit for key: {key}")
                return self._cache[key]
            self._stats["cache_misses"] += 1
            log_debug(f"Cache miss for key: {key}")
            return None

    def _set_cached_result(self, key: str, value: ResultType) -> None:
        """
        Thread-safe cache storage with LRU eviction.

        Args:
            key: Cache key
            value: Value to cache
        """
        with self._lock:
            # Evict oldest entries if cache is full
            if len(self._cache) >= self._config.cache_max_size:
                keys_to_remove = list(self._cache.keys())[:1]
                for k in keys_to_remove:
                    del self._cache[k]
                log_debug(f"Evicted {len(keys_to_remove)} cache entries")
            self._cache[key] = value
```

**Performance Monitoring:**
```python
def operation(self, arg: str) -> ResultType:
    """Operation with performance monitoring."""
    start_time = perf_counter()

    try:
        # Check cache
        cache_key = self._generate_cache_key(arg)
        cached = self._get_cached_result(cache_key)
        if cached is not None:
            return cached

        # Perform operation
        result = self._do_operation(arg)

        # Update cache
        self._set_cached_result(cache_key, result)

        # Update statistics
        end_time = perf_counter()
        execution_time = end_time - start_time
        self._stats["execution_times"].append(execution_time)
        self._stats["successful_operations"] += 1
        self._stats["total_operations"] += 1

        log_performance(f"Operation completed in {execution_time:.3f}s")

        return result

    except Exception as e:
        end_time = perf_counter()
        execution_time = end_time - start_time
        self._stats["failed_operations"] += 1
        self._stats["total_operations"] += 1
        log_error(f"Operation failed after {execution_time:.3f}s: {e}")
        raise
```

**Function-Level LRU Cache:**
```python
@lru_cache(maxsize=64, typed=True)
def get_instance(project_root: str = ".") -> Component:
    """
    Get singleton component instance with LRU caching.

    Args:
        project_root: Project root directory

    Returns:
        Component instance

    Note:
        - Cached instances are keyed by project_root
        - Maximum 64 instances cached
        - Type-sensitive caching enabled
    """
    config = ComponentConfig(project_root=project_root)
    return Component(config=config)
```

**Rules:**
- Use `threading.RLock` for thread safety
- SHA-256 hashing for cache keys
- Include file metadata (mtime, size) in cache keys
- LRU eviction when cache is full
- Track statistics: hits, misses, execution times
- Use `perf_counter()` for precise timing
- Log performance with `.3f` or `.4f` precision

### 6. Lazy Loading Pattern

```python
class Component:
    """Component with lazy initialization."""

    # Component initialized to None
    _heavy_component: Optional[HeavyType] = None
    _lock: threading.RLock = threading.RLock()

    def _ensure_heavy_component(self) -> HeavyType:
        """
        Lazy loading with thread safety.

        Returns:
            Initialized heavy component
        """
        with self._lock:
            if self._heavy_component is None:
                log_debug("Initializing heavy component")
                self._heavy_component = HeavyType()
                log_info("Heavy component initialized successfully")
        return self._heavy_component
```

### 7. Documentation Standards

**Method Docstring Template:**
```python
def method(
    self,
    arg1: str,
    arg2: int,
    *,
    option1: bool = True,
    option2: Optional[float] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Brief one-line description in imperative mood.

    Extended description providing more context about what this method
    does, how it works, and when to use it.

    Args:
        arg1: Description of arg1 with type information
        arg2: Description of arg2 with constraints (e.g., "must be positive")
        option1: Description of option1 (default: True)
        option2: Description of option2 (default: None)

    Returns:
        Tuple of (success flag, error message or None)

    Raises:
        ValidationError: When arg2 is negative
        ExecutionError: When operation fails

    Note:
        - Performance consideration: This method is cached
        - Thread-safe: Uses internal locking
        - File metadata (mtime, size) included in cache key

    Example:
        >>> component = Component()
        >>> success, error = component.method("test", 42)
        >>> if success:
        ...     print("Operation succeeded")
    """
```

**Rules:**
- First line: Brief summary (imperative mood, <80 chars)
- Blank line before extended description
- Args: One per line with type and constraints
- Returns: Describe structure and meaning
- Raises: Document all custom exceptions
- Note: Implementation details, performance, thread safety
- Example: Show typical usage (optional but recommended)
- English-only, no mixed languages

### 8. Logging Configuration

```python
# Configure logging (after imports)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Usage patterns
log_debug(f"Cache hit for key: {key}")
log_info(f"Component initialized successfully")
log_warning(f"Deprecated feature used: {feature}")
log_error(f"Operation failed: {error}")
log_performance(f"Parsed {file_path} in {time:.4f}s")
```

**Logging Categories:**
- **log_debug**: Cache hits/misses, internal state, detailed flow
- **log_info**: Initialization, major operations, success messages
- **log_warning**: Deprecations, non-critical issues, fallbacks
- **log_error**: All failures (logged before raising exceptions)
- **log_performance**: Timing metrics (use `.3f` or `.4f` format)

### 9. Data Class Pattern

**Immutable Models (frozen + slots):**
```python
@dataclass(frozen=True, slots=True)
class ImmutableModel:
    """
    Immutable model for [purpose].

    Attributes:
        field1: Description of field1
        field2: Description of field2
    """
    field1: str
    field2: int

    def __hash__(self) -> int:
        """Hash based on all fields."""
        return hash((self.field1, self.field2))
```

**Mutable Configuration:**
```python
@dataclass
class ConfigModel:
    """
    Configuration model for [purpose].

    Attributes:
        field1: Description of field1 (default: "default")
        field2: Description of field2 (default: 0)
    """
    field1: str = "default"
    field2: int = 0

    def validate(self) -> None:
        """
        Validate configuration.

        Raises:
            ValidationError: When validation fails
        """
        if self.field2 < 0:
            raise ValidationError(f"field2 must be non-negative, got {self.field2}")
```

**Rules:**
- Use `frozen=True, slots=True` for immutable models (performance)
- Provide default values for mutable configurations
- Include `__hash__` for frozen classes if used as dict keys
- Add `validate()` method for configurations

### 10. Module Exports Pattern

```python
__all__: List[str] = [
    # Data classes (alphabetical)
    "ConfigClass",
    "ModelClass",

    # Exceptions (alphabetical)
    "CustomError",
    "ValidationError",

    # Main class
    "MainClass",

    # Convenience functions
    "create_instance",
    "get_instance",
]

def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.

    Args:
        name: Attribute name

    Returns:
        Requested attribute

    Raises:
        ImportError: When attribute not found
    """
    if name == "MainClass":
        return MainClass
    elif name == "get_instance":
        return get_instance
    else:
        raise ImportError(f"Module {name} not found in {__name__}")
```

**Rules:**
- Define `__all__` with type hint `List[str]`
- Group exports by category with comments
- Sort alphabetically within each category
- Implement `__getattr__` for backward compatibility

## Edge Cases

### Circular Import Resolution
Use TYPE_CHECKING pattern to break circular dependencies:
```python
if TYPE_CHECKING:
    from ..circular_dependency import CircularClass
else:
    CircularClass = Any
```

### Python 3.8 Compatibility
Use backward-compatible Protocol pattern:
```python
if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    Protocol = object
```

### Heavy Dependency Management
Defer heavy imports to TYPE_CHECKING and use lazy loading:
```python
if TYPE_CHECKING:
    from heavy_library import HeavyClass
else:
    HeavyClass = Any

class Component:
    _heavy: Optional[HeavyClass] = None

    def _ensure_heavy(self) -> HeavyClass:
        if self._heavy is None:
            from heavy_library import HeavyClass
            self._heavy = HeavyClass()
        return self._heavy
```

### File Metadata in Cache Keys
Always include file modification time and size for cache invalidation:
```python
if os.path.exists(file_path):
    stat = os.stat(file_path)
    key_components.extend([str(int(stat.st_mtime)), str(stat.st_size)])
```

### Thread Safety Toggle
Make thread safety configurable for performance tuning:
```python
enable_thread_safety: bool = True
self._lock = threading.RLock() if enable_thread_safety else type(None)

# Usage
with self._lock:
    # Critical section
    pass
```

## Implementation Checklist

For each file to be optimized:

- [ ] Update module docstring (English-only, structured sections)
- [ ] Reorganize imports (TYPE_CHECKING pattern)
- [ ] Add logging configuration
- [ ] Define custom exception hierarchy
- [ ] Add comprehensive type hints (100% coverage)
- [ ] Implement LRU caching where applicable
- [ ] Add performance monitoring
- [ ] Add thread safety where needed
- [ ] Use lazy loading for heavy components
- [ ] Update method docstrings (Google/NumPy style)
- [ ] Define `__all__` exports
- [ ] Implement `__getattr__` for backward compatibility
- [ ] Verify mypy compliance (no errors)
- [ ] Verify all tests pass
- [ ] Update version to 1.10.5 and date to 2026-01-28

## Verification Criteria

After optimization, each file must:

1. **Pass mypy**: `uv run mypy tree_sitter_analyzer/path/to/file.py`
2. **Pass ruff**: `uv run ruff check tree_sitter_analyzer/path/to/file.py`
3. **Pass tests**: `uv run pytest tests/test_file.py -v`
4. **English-only**: No mixed language comments/docstrings
5. **Version sync**: Version 1.10.5, Date 2026-01-28
6. **Type coverage**: 100% type hint coverage
7. **Documentation**: All public APIs documented
8. **Performance**: Caching and monitoring where applicable
