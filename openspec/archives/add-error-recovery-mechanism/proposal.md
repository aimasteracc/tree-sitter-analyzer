# Add Error Recovery Mechanism

## Overview

Add a resilience layer that wraps analysis operations with graceful degradation.
When a parse error, encoding error, or timeout occurs, the system returns partial
results instead of failing completely.

## Design

### ErrorRecovery class

```python
class ErrorRecovery:
    def analyze_with_recovery(file_path, operations):
        results = {}
        for op in operations:
            try:
                results[op] = execute(op)
            except ParseError:
                results[op] = fallback_parse(file_path)  # line-count + regex
            except EncodingError:
                results[op] = {"error": "encoding", "lines": count_raw_lines()}
            except TimeoutError:
                results[op] = {"error": "timeout", "partial": True}
        return results
```

### Fallback Strategies

| Error Type | Fallback |
|------------|----------|
| Parse error | Regex-based extraction (class/method names via pattern) |
| Encoding error | Raw line count + binary detection |
| Timeout | Return cached partial result if available |
| Missing language | Generic text analysis (line count, word count) |

### Integration Point

Wrap `analyze_code_structure_tool.py` execute() with ErrorRecovery.
When tree-sitter fails, return partial results with `recovery_mode: true`.

## Success Criteria

1. Corrupted Java file → returns partial results (class names via regex)
2. Binary file → returns encoding error, not crash
3. Timeout → returns partial results with `recovery_mode: true`
4. 5+ TDD tests
5. All existing tests pass
