# GitHub Copilot Coding Standards

## 🎯 Mandatory Quality Standards

**Before writing or modifying any Python code, ensure:**

### Quality Requirements (CRITICAL)
- **Minimum Score**: >= 90/100
- **Check Tool**: `python scripts/check_code_quality.py <file>`
- **Forbidden**: Submit any code scoring < 90

### Module Header (11 Required Sections)
```python
"""Brief one-line description.

Detailed description.

Features:
    - Feature 1
    - Feature 2

Architecture:
    - Component 1: Purpose

Usage:
    Example code

Performance Characteristics:
    - Time: O(n)
    - Space: O(1)

Thread Safety:
    - Thread-safe: Yes/No

Dependencies:
    - External: list
    - Internal: list

Error Handling:
    - 3 custom exceptions

Note:
    Important notes

Example:
    ```python
    code_example()
    ```
"""
```

### Exception Classes (Must Have 3)
```python
class ModuleBaseException(Exception):
    """Base exception."""
    pass


class SpecificError1(ModuleBaseException):
    """Specific error 1."""
    pass


class SpecificError2(ModuleBaseException):
    """Specific error 2."""
    pass
```

**Forbidden**: `pass` on same line as class definition

### Method Documentation (100% Coverage)

**Public Methods** (Required: Args/Returns/Note):
```python
def method(self, arg: str) -> dict[str, Any]:
    """Brief description.
    
    Args:
        arg: Description
        
    Returns:
        dict[str, Any]: Description
        
    Note:
        Important behavior
    """
```

**No-parameter methods must be explicit**:
```python
def get_statistics(self) -> dict:
    """Get statistics.
    
    Args:
        None (instance method with no parameters)
```

**Private Methods** (Simplified: Args/Returns/Note)

### Performance Monitoring (5-8 monitoring points)
```python
from time import perf_counter

def __init__(self):
    self._stats = {
        'total_calls': 0,
        'total_time': 0.0,
        'errors': 0
    }

def operation(self):
    start = perf_counter()
    try:
        self._stats['total_calls'] += 1
        # operation
    finally:
        self._stats['total_time'] += perf_counter() - start
```

### Statistics Method (Must Implement)
```python
def get_statistics(self) -> dict[str, Any]:
    """Get statistics.
    
    Args:
        None (instance method with no parameters)
        
    Returns:
        dict[str, Any]: Statistics with derived metrics
    """
    total = max(1, self._stats['total_calls'])
    return {
        **self._stats,
        'avg_time': self._stats['total_time'] / total
    }
```

### Export List (__all__)
```python
__all__ = [
    'PublicClass',
    'public_function',
    # Exceptions must be exported
    'ModuleBaseException',
    'SpecificError1',
    'SpecificError2'
]
```

## 🚫 Forbidden Practices

1. Skip quality checks
2. Simplify documentation format
3. Inconsistent method formats within same file
4. Less than 3 exception classes
5. Missing performance monitoring
6. Missing statistics tracking

## ✅ Standard Workflow

```
1. Read target file
2. Run quality check (baseline)
3. Identify non-compliant items
4. Fix all issues
5. Re-run quality check
6. Confirm >= 90/100
```

## 📚 Complete Documentation

- **Quality Checker**: `scripts/check_code_quality.py`
- **Compliance Checker**: `scripts/check_code_compliance.py`
- **Coding Standards**: `CODING_STANDARDS.md`

---

**Enforcement**: Must follow for every code operation
**Last Updated**: 2026-01-31
