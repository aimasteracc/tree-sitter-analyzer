# Design: Phase 4 — Decorator/Framework Entry Recognition

## Problem
v1 analysis shows 827 dead code symbols. Many are false positives because:
- `@click.command` / `@app.route` decorated functions are called by frameworks via reflection
- AST call extraction only sees `call_expression` nodes, not decorator-based registration
- Result: every Flask route, every Click CLI command, every pytest fixture is "dead code"

## Solution: Decorator-Aware Dead Code Detection

### Architecture

```
_parse_file()
    └── NEW: _extract_decorated_entries(parsed, language)
            └── Scan AST for decorator nodes
            └── Match against known framework patterns
            └── Return set of {function_name} that are framework-registered

_detect_dead_code()
    └── NEW: Skip symbols whose names are in decorator_entries set
```

### Key Design Decisions

1. **Decorator pattern matching (not hardcoded)**:
   - `_FRAMEWORK_DECORATOR_PATTERNS`: configurable set of decorator name patterns
   - Covers: `@app.*`, `@click.*`, `@pytest.*`, `@staticmethod`, `@classmethod`,
     `@property`, `@override`, `@abstractmethod`, `@dataclass`, etc.

2. **ModuleInfo extension**: Add `decorated_entries: set[str]` field
   - Populated during `_parse_file` via AST decorator scanning
   - Consumed by `_detect_dead_code` to exempt decorated functions

3. **Language-agnostic AST approach**:
   - Python: scan for `decorator` nodes in AST
   - Java: scan for `annotation` nodes (same concept)
   - TypeScript: scan for `decorator` nodes

4. **Two categories**:
   - **Framework entries**: `@app.route`, `@click.command`, `@pytest.fixture` — always exempt
   - **Structural decorators**: `@property`, `@staticmethod`, `@classmethod` — exempt from dead code

### Decorator Patterns

```python
_FRAMEWORK_DECORATOR_PATTERNS = {
    # Web frameworks
    "route", "get", "post", "put", "delete", "patch",
    "app", "api", "router", "blueprint",
    # CLI frameworks
    "command", "group", "option", "argument",
    "click", "typer",
    # Testing
    "fixture", "parametrize", "mark",
    "pytest", "test",
    # Python builtins
    "property", "staticmethod", "classmethod",
    "abstractmethod", "override",
    "dataclass", "dataclasses",
    # Event/Signal
    "on", "listener", "handler", "receiver",
    "subscribe", "callback",
    # DI/Registration
    "register", "inject", "provider",
    "singleton", "service",
}
```

### Impact on Existing Tests
- `TestDeadCodeAccuracy` tests in `cross_file_project` fixture don't use decorators → no change
- New tests needed for decorator recognition

## Task Breakdown

| Task | Description | Files |
|------|-------------|-------|
| T4.1 | Add `decorated_entries` to `ModuleInfo` | `code_map.py` |
| T4.2 | Implement `_extract_decorated_entries` (Python AST) | `code_map.py` |
| T4.3 | Wire into `_parse_file` | `code_map.py` |
| T4.4 | Update `_detect_dead_code` to check decorated | `code_map.py` |
| T4.5 | Add decorator fixture + tests (TDD) | fixture + tests |
| T4.6 | Extend to Java annotations (bonus) | `code_map.py` |
