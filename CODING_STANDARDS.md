# Tree-sitter Analyzer - Coding Standards

**Version**: 1.10.5  
**Last Updated**: 2026-01-31  
**Status**: ✅ Active (182/182 files optimized)

---

## 📖 Purpose

This document defines the unified coding standards for the tree-sitter-analyzer project. All code MUST follow these standards to ensure consistency, maintainability, and quality across the 182+ Python files in the codebase.

**For AI/LLM Agents**: Follow these standards strictly when generating, modifying, or reviewing code.

---

## 🎯 Core Principles

1. **Type Safety First** - 100% PEP 484 type hint coverage
2. **English Only** - All comments, docstrings, and documentation in English
3. **Performance Aware** - Use LRU caching and performance monitoring
4. **Thread Safe** - Use locks for shared resources
5. **Error Explicit** - Custom exception hierarchy with clear messages
6. **Backward Compatible** - Maintain API compatibility with aliases

---

## 📁 File Structure Template

```python
#!/usr/bin/env python3
"""
Module Title - Brief Description

Detailed description of module functionality, architecture, and key features.

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling and recovery
- Performance optimization (LRU caching, timing)
- Thread-safe operations
- Detailed documentation

Features:
- Feature 1: Description
- Feature 2: Description
- Feature 3: Description

Architecture:
- Component 1: Role
- Component 2: Role
- Integration points

Usage:
    >>> from tree_sitter_analyzer.module import Class
    >>> obj = Class(param="value")
    >>> result = obj.method()

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""

# ============================================================================
# Imports - Standard Library
# ============================================================================

import os
import sys
import threading
import time
from pathlib import Path

# ============================================================================
# Imports - Third Party
# ============================================================================

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

# ============================================================================
# Imports - Type Checking (Conditional)
# ============================================================================

if TYPE_CHECKING:
    # Import for type hints only (avoid circular imports)
    from tree_sitter import Tree, Node, Language
    from .other_module import SomeClass

# ============================================================================
# Imports - Performance & Utilities
# ============================================================================

from functools import lru_cache, wraps
from time import perf_counter
from dataclasses import dataclass, field

# ============================================================================
# Imports - Internal Modules
# ============================================================================

from ..utils import log_error, log_info
from .base import BaseClass

# ============================================================================
# Logging Configuration
# ============================================================================

import logging
logger = logging.getLogger(__name__)

# ============================================================================
# Public API Exports
# ============================================================================

__all__: List[str] = [
    # Main classes
    "MainClass",
    
    # Helper functions
    "helper_function",
    
    # Constants
    "CONSTANT_VALUE",
]

# ============================================================================
# Constants and Configuration
# ============================================================================

MAX_CACHE_SIZE: int = 1024
DEFAULT_TIMEOUT: float = 30.0
SUPPORTED_LANGUAGES: List[str] = ["python", "javascript", "java"]

# ============================================================================
# Exception Hierarchy
# ============================================================================

class ModuleError(Exception):
    """Base exception for this module."""
    pass

class InitializationError(ModuleError):
    """Raised when initialization fails."""
    pass

class ValidationError(ModuleError):
    """Raised when validation fails."""
    pass

# ============================================================================
# Data Classes and Type Definitions
# ============================================================================

@dataclass(frozen=True, slots=True)
class ConfigClass:
    """Configuration data class."""
    param1: str
    param2: int = 10
    param3: Optional[str] = None

# ============================================================================
# Main Implementation
# ============================================================================

class MainClass:
    """
    Main class description.
    
    This class provides functionality for...
    
    Attributes:
        _cache: Internal cache dictionary
        _lock: Thread lock for synchronization
        _stats: Performance statistics
    
    Example:
        >>> obj = MainClass(param="value")
        >>> result = obj.process(data)
    """
    
    def __init__(self, param: str, config: Optional[ConfigClass] = None) -> None:
        """
        Initialize the class.
        
        Args:
            param: Required parameter description
            config: Optional configuration object
        
        Raises:
            InitializationError: If initialization fails
        """
        self._param = param
        self._config = config or ConfigClass(param1="default")
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._stats = {"calls": 0, "total_time": 0.0}
    
    def process(self, data: str) -> Dict[str, Any]:
        """
        Process data and return results.
        
        Args:
            data: Input data to process
        
        Returns:
            Dictionary containing processing results
        
        Raises:
            ValidationError: If data is invalid
        
        Example:
            >>> result = obj.process("test data")
            >>> print(result["success"])
            True
        """
        start_time = perf_counter()
        
        try:
            # Implementation
            result = self._internal_process(data)
            return result
        finally:
            elapsed = perf_counter() - start_time
            with self._lock:
                self._stats["calls"] += 1
                self._stats["total_time"] += elapsed
    
    def _internal_process(self, data: str) -> Dict[str, Any]:
        """Internal processing method (private)."""
        if not data:
            raise ValidationError("Data cannot be empty")
        return {"success": True, "data": data}

# ============================================================================
# Helper Functions
# ============================================================================

@lru_cache(maxsize=128)
def helper_function(key: str, value: int) -> str:
    """
    Helper function with LRU caching.
    
    Args:
        key: String key
        value: Integer value
    
    Returns:
        Formatted string result
    
    Example:
        >>> result = helper_function("test", 42)
        >>> print(result)
        'test:42'
    """
    return f"{key}:{value}"

# ============================================================================
# Module-level Exports (Backward Compatibility)
# ============================================================================

def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.
    
    Args:
        name: Name of the attribute to import
    
    Returns:
        The requested attribute
    
    Raises:
        AttributeError: If attribute not found
    """
    # CRITICAL: Skip Python internal attributes
    if name.startswith("_"):
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    
    # Handle specific imports
    if name == "MainClass":
        return MainClass
    
    # Handle backward compatibility aliases
    if name == "OldClassName":
        return MainClass  # Redirect to new name
    
    # Not found
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```

---

## 🔧 Type Hints (PEP 484) - MANDATORY

### ✅ Function Signatures

```python
# Good - Complete type hints
def process_file(
    file_path: str,
    max_size: Optional[int] = None,
    options: Dict[str, Any] = None,
    *,
    strict: bool = False
) -> Tuple[bool, str, Dict[str, Any]]:
    """Process a file and return results."""
    pass

# Bad - No type hints
def process_file(file_path, max_size=None, options=None, strict=False):
    pass
```

### ✅ Class Attributes

```python
# Good
class Parser:
    """Parser class."""
    
    def __init__(self) -> None:
        self._cache: Dict[str, Tree] = {}
        self._lock: threading.Lock = threading.Lock()
        self._count: int = 0

# Bad
class Parser:
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()
        self._count = 0
```

### ✅ Complex Types

```python
from typing import (
    TYPE_CHECKING, Any, Callable, Dict, List, 
    Optional, Tuple, Union, TypeVar, Generic
)

# Type aliases
NodeList = List['Node']
ResultDict = Dict[str, Any]
CallbackFunc = Callable[[str], bool]

# Generic types
T = TypeVar('T')

class Container(Generic[T]):
    def __init__(self) -> None:
        self._items: List[T] = []
    
    def add(self, item: T) -> None:
        self._items.append(item)
    
    def get(self, index: int) -> T:
        return self._items[index]
```

---

## 📝 Documentation Standards

### ✅ Module Docstrings

```python
"""
Module Title - One Line Summary

Multi-paragraph detailed description explaining:
- What this module does
- Why it exists
- How it fits into the larger architecture

Optimized with:
- Complete type hints (PEP 484)
- Comprehensive error handling
- Performance optimization (LRU caching)
- Thread-safe operations

Features:
- Feature 1 with explanation
- Feature 2 with explanation

Architecture:
- Component description
- Integration points

Usage:
    >>> from module import Class
    >>> obj = Class()
    >>> result = obj.method()

Author: aisheng.yu
Version: 1.10.5
Date: 2026-01-28
"""
```

### ✅ Function/Method Docstrings

```python
def analyze_code(
    source: str,
    language: str,
    config: Optional[AnalysisConfig] = None
) -> AnalysisResult:
    """
    Analyze source code and return structured results.
    
    This function performs comprehensive code analysis including
    syntax validation, structure extraction, and metrics calculation.
    
    Args:
        source: Source code string to analyze. Must not be empty.
        language: Programming language identifier (e.g., 'python', 'java').
                 Must be supported by the analyzer.
        config: Optional analysis configuration. If None, uses default
               configuration with all features enabled.
    
    Returns:
        AnalysisResult object containing:
        - success: Boolean indicating if analysis succeeded
        - elements: List of extracted code elements
        - metrics: Dictionary of code metrics
        - errors: List of any errors encountered
    
    Raises:
        ValueError: If source is empty or language is not supported
        AnalysisError: If analysis fails due to internal error
        TimeoutError: If analysis exceeds configured timeout
    
    Example:
        >>> result = analyze_code(
        ...     source="def hello(): pass",
        ...     language="python"
        ... )
        >>> print(result.success)
        True
        >>> print(len(result.elements))
        1
    
    Note:
        This function is thread-safe and can be called concurrently.
        Results are cached based on source code hash.
    """
```

### ✅ Class Docstrings

```python
class AnalysisEngine:
    """
    Main orchestrator for code analysis operations.
    
    The AnalysisEngine coordinates between parsers, query executors,
    and formatters to provide a unified interface for code analysis.
    
    Thread Safety:
        All public methods are thread-safe. Internal state is protected
        by locks and uses thread-safe data structures.
    
    Performance:
        Uses LRU caching for parsed trees and query results. Cache size
        is configurable via AnalysisEngineConfig.
    
    Attributes:
        _parser: Tree-sitter parser instance
        _executor: Query executor for running queries
        _cache: LRU cache for parsed syntax trees
        _lock: Thread lock for synchronization
        _stats: Performance statistics dictionary
    
    Example:
        >>> engine = AnalysisEngine(project_root=".")
        >>> result = engine.analyze_file("main.py")
        >>> print(result.success)
        True
    """
```

---

## 📦 Import Organization - 5 Groups

```python
# ============================================================================
# Group 1: Standard Library (alphabetical)
# ============================================================================

import hashlib
import logging
import os
import sys
import threading
import time
from pathlib import Path

# ============================================================================
# Group 2: Third-Party Libraries (alphabetical)
# ============================================================================

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

# ============================================================================
# Group 3: TYPE_CHECKING Conditional Imports
# ============================================================================

if TYPE_CHECKING:
    # Import expensive or circular dependencies for type checking only
    from tree_sitter import Tree, Node, Language, Parser as TreeParser
    from ..encoding_utils import EncodingManager
    from .other_module import ComplexClass

# ============================================================================
# Group 4: Performance & Utility Tools
# ============================================================================

from functools import lru_cache, wraps
from time import perf_counter
from dataclasses import dataclass, field
from enum import Enum

# ============================================================================
# Group 5: Internal Project Imports (relative imports last)
# ============================================================================

from ..utils import log_error, log_info, log_warning
from ..exceptions import BaseError
from .base import BaseClass
```

**CRITICAL Rules:**
1. **Always import `sys`** if you use `sys.version_info`
2. **Use TYPE_CHECKING** for type-only imports to avoid circular dependencies
3. **Separate groups** with comment headers
4. **Alphabetical order** within each group

---

## ⚠️ Exception Handling

### ✅ Custom Exception Hierarchy

```python
# Base exception for the module/package
class AnalysisEngineError(Exception):
    """Base exception for analysis engine operations."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

# Specific exceptions
class InitializationError(AnalysisEngineError):
    """Raised when engine initialization fails."""
    pass

class ValidationError(AnalysisEngineError):
    """Raised when input validation fails."""
    pass

class TimeoutError(AnalysisEngineError):
    """Raised when operation exceeds timeout."""
    pass
```

### ✅ Exception Usage

```python
def initialize(config: Config) -> None:
    """Initialize with proper error handling."""
    try:
        _setup_parser()
        _load_language(config.language)
    except FileNotFoundError as e:
        raise InitializationError(
            f"Failed to load language file: {config.language}",
            details={"language": config.language, "error": str(e)}
        ) from e
    except Exception as e:
        raise InitializationError(
            f"Unexpected initialization error: {e}"
        ) from e
```

---

## 🚀 Performance Optimization

### ✅ LRU Caching

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def parse_query(query_string: str) -> Query:
    """
    Parse query string with LRU caching.
    
    Cache size: 128 most recent queries
    Thread-safe: Yes (functools.lru_cache is thread-safe)
    """
    return Query(query_string)

# For methods, use manual caching with lock
class Parser:
    def __init__(self) -> None:
        self._cache: Dict[str, Tree] = {}
        self._lock = threading.Lock()
    
    def parse(self, code: str, filename: str) -> Tree:
        cache_key = f"{filename}:{hash(code)}"
        
        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
        
        tree = self._parse_impl(code)
        
        with self._lock:
            self._cache[cache_key] = tree
        
        return tree
```

### ✅ Performance Monitoring

```python
from time import perf_counter

def analyze(self, data: str) -> Result:
    """Analyze with performance tracking."""
    start_time = perf_counter()
    
    try:
        result = self._process(data)
        return result
    finally:
        elapsed = perf_counter() - start_time
        
        # Update statistics
        with self._lock:
            self._stats['total_calls'] += 1
            self._stats['total_time'] += elapsed
            self._stats['avg_time'] = (
                self._stats['total_time'] / self._stats['total_calls']
            )
        
        # Log slow operations
        if elapsed > 1.0:
            logger.warning(
                f"Slow analysis: {elapsed:.2f}s for {len(data)} bytes"
            )
```

---

## 🔒 Thread Safety

### ✅ Using Locks

```python
import threading

class CacheService:
    """Thread-safe cache service."""
    
    def __init__(self) -> None:
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()  # One lock for all operations
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache (thread-safe)."""
        with self._lock:
            return self._cache.get(key)
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache (thread-safe)."""
        with self._lock:
            self._cache[key] = value
    
    def clear(self) -> None:
        """Clear cache (thread-safe)."""
        with self._lock:
            self._cache.clear()
```

### ✅ Thread-Safe Collections

```python
from queue import Queue
from threading import Lock

class WorkQueue:
    def __init__(self) -> None:
        # Queue is already thread-safe
        self._queue: Queue[Task] = Queue()
        
        # But statistics need a lock
        self._stats_lock = Lock()
        self._processed = 0
    
    def add(self, task: Task) -> None:
        """Add task (thread-safe via Queue)."""
        self._queue.put(task)
    
    def get(self) -> Task:
        """Get task (thread-safe via Queue)."""
        task = self._queue.get()
        
        with self._stats_lock:
            self._processed += 1
        
        return task
```

---

## 🎭 __getattr__ Pattern - CRITICAL

```python
def __getattr__(name: str) -> Any:
    """
    Fallback for dynamic imports and backward compatibility.
    
    CRITICAL: Must skip Python internal attributes to avoid
    capturing __path__, __spec__, etc.
    
    Args:
        name: Attribute name to retrieve
    
    Returns:
        The requested attribute
    
    Raises:
        AttributeError: If attribute not found
    """
    # ⚠️ CRITICAL: Skip Python internal attributes
    if name.startswith("_"):
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    
    # Handle specific imports (use globals() for module-level items)
    if name in ["MainClass", "helper_function"]:
        return globals()[name]
    
    # Handle backward compatibility aliases
    if name == "OldClassName":
        return globals()["NewClassName"]
    
    if name == "CacheError":
        # Redirect to new name
        return globals()["CacheServiceError"]
    
    # Not found
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```

**Why This Matters:**
- Without `if name.startswith("_")` check, `__getattr__` catches `__path__`, `__spec__`, etc.
- This causes `ImportError` and breaks module loading
- **18 files were fixed** in Session 12 for this issue

---

## 🏷️ Naming Conventions

| Type | Convention | Example |
|------|------------|---------|
| **Classes** | PascalCase | `AnalysisEngine`, `ParseResult` |
| **Functions** | snake_case | `parse_file`, `get_language` |
| **Variables** | snake_case | `file_path`, `max_retries` |
| **Constants** | UPPER_SNAKE_CASE | `MAX_SIZE`, `DEFAULT_TIMEOUT` |
| **Private members** | _leading_underscore | `_cache`, `_internal_method` |
| **Type variables** | Single uppercase or PascalCase | `T`, `KT`, `ResultType` |
| **Type aliases** | PascalCase | `NodeList`, `ResultDict` |

### ✅ Examples

```python
# Constants
MAX_CACHE_SIZE: int = 1024
DEFAULT_ENCODING: str = "utf-8"
SUPPORTED_LANGUAGES: List[str] = ["python", "java"]

# Classes
class AnalysisEngine:
    pass

class ParseResult(NamedTuple):
    success: bool
    tree: Tree

# Functions and methods
def parse_file(file_path: str) -> ParseResult:
    pass

def get_language_detector() -> LanguageDetector:
    pass

# Private methods (single underscore)
class Parser:
    def _internal_parse(self, code: str) -> Tree:
        pass
    
    def _validate_syntax(self, tree: Tree) -> bool:
        pass

# Variables
file_path: str = "main.py"
max_retries: int = 3
language_detector: LanguageDetector = get_language_detector()
```

---

## 📊 Data Classes

```python
from dataclasses import dataclass, field
from typing import List, Optional

# Immutable data class (preferred for DTOs)
@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """
    Result of code analysis operation.
    
    Attributes:
        success: Whether analysis succeeded
        elements: List of extracted code elements
        metrics: Performance and complexity metrics
        errors: List of errors encountered
    """
    success: bool
    elements: List[Element]
    metrics: Dict[str, float] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

# Mutable config class
@dataclass
class AnalysisConfig:
    """Configuration for analysis engine."""
    max_depth: int = 50
    timeout: float = 30.0
    include_stats: bool = True
    languages: List[str] = field(default_factory=lambda: ["python"])
```

---

## 🚫 Common Pitfalls - MUST AVOID

### ❌ Pitfall 1: Missing `import sys`

```python
# ❌ BAD - NameError: name 'sys' is not defined
if sys.version_info >= (3, 8):
    from typing import Protocol

# ✅ GOOD
import sys

if sys.version_info >= (3, 8):
    from typing import Protocol
```

**Fix Applied:** 11 files in Session 12

---

### ❌ Pitfall 6: Unused TYPE_CHECKING Imports

**Core Principle: TYPE_CHECKING is for avoiding circular imports, not for type aggregation.**

```python
# ❌ BAD - Importing symbols in TYPE_CHECKING but not using them
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .module import ClassA, ClassB, ClassC  # Only ClassA used!
    from .utils import func1, func2  # Neither used!

def process(obj: ClassA) -> None:  # Only ClassA is actually used
    pass

# ✅ GOOD - Only import what's actually used in type annotations
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .module import ClassA  # Precisely what's needed

def process(obj: ClassA) -> None:
    pass
```

**Pattern for modules with `__getattr__` dynamic imports:**

```python
# ✅ CORRECT - Dynamic imports re-import, so TYPE_CHECKING stays minimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only types used in THIS file's annotations
    from .loader import Loader

# Runtime imports for actual usage
from .commands import SomeCommand

def __getattr__(name: str) -> Any:
    """Dynamic import - re-imports at runtime."""
    if name.startswith("_"):
        raise AttributeError(f"module has no attribute '{name}'")
    
    if name == "SomeCommand":
        from .commands import SomeCommand  # Re-import here
        return SomeCommand
    
    raise AttributeError(f"module has no attribute '{name}'")
```

**Key Rules:**
1. **Default: Minimal TYPE_CHECKING** - Only what's used in annotations
2. **No exceptions** - Even `__getattr__` modules use minimal imports
3. **Rationale**: Python's `from __future__ import annotations` makes else blocks unnecessary
4. **Tool alignment**: Follow mypy, pyright, ruff consensus

**Why `# noqa: F401` is a code smell:**
- Indicates unused imports (technical debt)
- Makes code reviews harder
- Reduces refactoring safety
- Goes against tool ecosystem

**Verification Command:**
```bash
uv run ruff check tree_sitter_analyzer/ --select F401
# Should pass with ZERO warnings (no noqa needed)
```

**Why This Matters:**
- Follows Python stdlib conventions (check typing.py, collections.abc)
- Reduces cognitive load for team
- Improves type checker performance
- Enables safe automated refactoring

---

### ❌ Pitfall 2: Unsafe `__getattr__`

```python
# ❌ BAD - Catches Python internal attributes
def __getattr__(name: str) -> Any:
    if name == "MyClass":
        return MyClass
    raise AttributeError(f"Not found: {name}")

# ✅ GOOD - Skips internal attributes
def __getattr__(name: str) -> Any:
    # CRITICAL: Allow special attributes to raise AttributeError naturally
    if name.startswith("_"):
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```

**Why This Rule Exists:**
- Python's import system checks for `__path__`, `__file__`, etc.
- Without the guard, `__getattr__` intercepts these, causing `ImportError`
- Symptom: "ImportError: module __path__ not found"

---

### ❌ Pitfall 7: Empty TYPE_CHECKING Blocks

```python
# ❌ BAD - Empty TYPE_CHECKING blocks are code smell
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # Why is this here?

# ❌ BAD - Even with comments
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Future: Add type imports
    pass

# ✅ GOOD - Remove entirely if not needed
# (No TYPE_CHECKING import at all)

# ✅ GOOD - Only use when actually needed
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .module import ClassA  # Actually used below

def process(obj: ClassA) -> None:
    pass
```

**Key Rules:**
1. **Delete empty TYPE_CHECKING blocks** - They serve no purpose
2. **No "future planning" blocks** - Add TYPE_CHECKING only when needed
3. **Verification**: Run `ruff check` after removal to catch missing imports

**Project-Wide Cleanup (2026-01-28):**
- Removed 23 empty TYPE_CHECKING blocks across:
  - `mcp/` subsystem (12 files)
  - `testing/` (2 files)
  - `formatters/`, `plugins/`, `security/`, `platform_compat/`, `utils/`
- Pattern: `if TYPE_CHECKING:\n    pass` or with `else: pass`
- Result: Zero ruff errors, cleaner codebase

---

### ❌ Pitfall 2: Unsafe `__getattr__` (Original)
    if name.startswith("_"):
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    
    if name == "MyClass":
        return MyClass
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```

**Fix Applied:** 4 files in Session 12

---

### ❌ Pitfall 3: Class Name Mismatches

```python
# ❌ BAD - Class named ParserConfig, but imported as ParseConfig
from .parser import ParseConfig  # Class doesn't exist!

# ✅ GOOD - Import actual class name
from .parser import ParserConfig
```

**Fix Applied:** core/__init__.py in Session 12

---

### ❌ Pitfall 4: Missing TYPE_CHECKING Runtime Import

```python
# ❌ BAD - List not imported at runtime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List

__all__: List[str] = []  # NameError: name 'List' is not defined

# ✅ GOOD - Import List at runtime too
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .other import SomeClass

__all__: List[str] = []  # Works!
```

**Fix Applied:** core/__init__.py in Session 12

---

### ❌ Pitfall 5: No Backward Compatibility

```python
# ❌ BAD - Breaking change, old tests fail
class CacheServiceError(Exception):
    pass

# Old code tries: from module import CacheError
# Result: ImportError

# ✅ GOOD - Provide alias in __getattr__
def __getattr__(name: str) -> Any:
    if name.startswith("_"):
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
    
    # Backward compatibility alias
    if name == "CacheError":
        return CacheServiceError
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```

**Fix Applied:** cache_service.py in Session 12

---

## 📋 Pre-commit Checklist

Before submitting code, verify:

- [ ] **Type hints**: 100% coverage on all functions, methods, attributes
- [ ] **Docstrings**: All public APIs have comprehensive docstrings
- [ ] **English only**: No non-English text in code or docs
- [ ] **Import sys**: If using `sys.version_info`, `sys` is imported
- [ ] **__getattr__ safety**: Skips internal attributes (`_` prefix)
- [ ] **Class names**: Match between definition and imports
- [ ] **__all__ exports**: Defined and accurate
- [ ] **TYPE_CHECKING cleanup**: Only import types actually used in annotations
- [ ] **No unused imports**: Run `ruff check` to verify (F401)
- [ ] **Version sync**: 1.10.5, date 2026-01-28
- [ ] **Error handling**: Custom exceptions used appropriately
- [ ] **Thread safety**: Locks used for shared mutable state
- [ ] **Performance**: LRU caching and monitoring where beneficial
- [ ] **Tests pass**: `python -m py_compile <file>` succeeds
- [ ] **Import test**: `python -c "import module"` succeeds
- [ ] **Ruff clean**: `uv run ruff check <file>` passes

---

## 🧪 Verification Commands

```bash
# Compile check (syntax validation)
python -m py_compile tree_sitter_analyzer/module.py

# Import test (runtime validation)
python -c "import tree_sitter_analyzer.module; print('OK')"

# Type checking (full project)
uv run mypy tree_sitter_analyzer/ --strict

# Code quality (linting and unused imports)
uv run ruff check tree_sitter_analyzer/

# Specific checks for unused imports
uv run ruff check tree_sitter_analyzer/ --select F401

# Specific checks for undefined names
uv run ruff check tree_sitter_analyzer/ --select F821

# Full test suite
uv run pytest tests/ -v --no-cov

# Quick compilation check for all files
uv run python -c "import tree_sitter_analyzer; print('✓ All imports OK')"
```

---

## 📊 Code Quality Metrics

After optimization (Session 12, 2026-01-31):

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| **Files Optimized** | 182 | 182 | ✅ 100% |
| **Compilation Success** | 100% | 100% | ✅ Pass |
| **Import Success** | 100% | 100% | ✅ Pass |
| **Type Hints Coverage** | 100% | ~98% | ⚠️ Good |
| **Unused Imports (F401)** | 0 | ~30 | ⚠️ Cleanup needed |
| **Undefined Names (F821)** | 0 | 0 | ✅ Pass |
| **Syntax Errors** | 0 | 0 | ✅ Pass |
| **English-only Docs** | 100% | 100% | ✅ Pass |

**Note:** F401 warnings are in TYPE_CHECKING blocks and don't affect runtime. These are marked for cleanup in Phase 6.

---

## 📚 Reference Examples

See these optimized files as reference implementations:

- **Core Module**: `tree_sitter_analyzer/core/analysis_engine.py` (843 lines)
- **Plugin System**: `tree_sitter_analyzer/plugins/manager.py` (1254 lines)
- **Language Plugin**: `tree_sitter_analyzer/languages/python_plugin.py` (1277 lines)
- **Formatter**: `tree_sitter_analyzer/formatters/python_formatter.py` (866 lines)
- **MCP Tool**: `tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py` (468 lines)

All 182 files follow these standards consistently.

---

## 🔄 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.10.5 | 2026-01-28 | Optimization complete: 182/182 files |
| 1.10.4 | 2026-01-27 | Phase 5 complete: Core & utilities |
| 1.10.3 | 2026-01-26 | Phase 4 complete: MCP tools |
| 1.10.2 | 2026-01-25 | Phase 3 complete: Formatters |
| 1.10.1 | 2026-01-24 | Phase 2 complete: Language plugins |

---

## 📞 Contact

**Maintainer**: aisheng.yu  
**Email**: aimasteracc@gmail.com  
**Project**: tree-sitter-analyzer v1.10.5

---

**Last Updated**: 2026-02-02 (Session 13)  
**Status**: ✅ Active - All 182 files compliant, 0 ruff errors

---

## 📊 Level 2-3 Optimization Standards (Added 2026-01-31)

**Quality Score Target**: >= 90/100  
**Automated Checker**: `scripts/check_code_quality.py`

### Current Status

| File | Score | Status |
|------|-------|--------|
| python_formatter.py | 100/100 | ✅ PASS |
| python_plugin.py | 97/100 | ✅ PASS |

### Quick Reference

**Check File Quality**:
``bash
python scripts/check_code_quality.py <file_path>
``

**Check Compliance**:
``bash
python scripts/check_code_compliance.py <file_path>
``

**Standards Documentation**: See `CODING_STANDARDS.md` for:
- 8-phase optimization workflow
- Documentation requirements (Args/Returns/Raises/Performance/Thread Safety/Note/Example)
- Exception class patterns (3 per module)
- Performance monitoring patterns
- Statistics tracking patterns
- Complete code templates

**Quality Criteria**:
- Module header: 11 required sections
- Custom exceptions: 3 classes
- Public methods: Args/Returns/Note (100% coverage)
- Performance monitoring: 5-8 points per file
- Statistics: _stats dict + get_statistics()
- Exports: __all__ with exceptions

---

**Standards Version**: 1.10.5 + Level 2-3  
**Last Updated**: 2026-01-31
