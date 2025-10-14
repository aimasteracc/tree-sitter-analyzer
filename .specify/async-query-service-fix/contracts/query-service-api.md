# Query Service API Contract

**Feature**: Async Query Service Fix  
**Date**: 2025-10-14  
**Version**: 1.0  

## Overview

非同期QueryServiceのAPIコントラクトを定義します。既存の同期APIから非同期APIへの移行における契約仕様を明確化し、後方互換性と型安全性を保証します。

## Core API Contract

### QueryService.execute_query()

**Before (Synchronous)**:
```python
def execute_query(
    self,
    file_path: str,
    language: str,
    query_key: str | None = None,
    query_string: str | None = None,
    filter_expression: str | None = None,
) -> list[dict[str, Any]] | None:
```

**After (Asynchronous)**:
```python
async def execute_query(
    self,
    file_path: str,
    language: str,
    query_key: str | None = None,
    query_string: str | None = None,
    filter_expression: str | None = None,
) -> list[dict[str, Any]] | None:
```

**Contract Changes**:
- ✅ **Method Signature**: `async def` キーワード追加
- ✅ **Parameters**: 変更なし（完全互換）
- ✅ **Return Type**: 変更なし（完全互換）
- ✅ **Exceptions**: 既存例外に加えて非同期例外対応

## Input Validation Contract

### Required Parameters

| Parameter | Type | Constraints | Validation Rules |
|-----------|------|-------------|------------------|
| `file_path` | `str` | 必須、非空 | セキュリティ検証、存在確認、読み取り権限 |
| `language` | `str` | 必須、非空 | サポート言語リスト、正規化 |

### Optional Parameters

| Parameter | Type | Default | Constraints |
|-----------|------|---------|-------------|
| `query_key` | `str \| None` | `None` | 利用可能クエリキー、相互排他（query_string） |
| `query_string` | `str \| None` | `None` | 有効なTree-sitter構文、相互排他（query_key） |
| `filter_expression` | `str \| None` | `None` | フィルター構文、安全性検証 |

### Validation Rules

```python
# Mutual exclusivity
if not query_key and not query_string:
    raise ValueError("Must provide either query_key or query_string")

if query_key and query_string:
    raise ValueError("Cannot provide both query_key and query_string")

# Security validation
is_valid, error_msg = security_validator.validate_file_path(file_path)
if not is_valid:
    raise ValueError(f"Invalid file path: {error_msg}")
```

## Output Contract

### Success Response

```python
# Type Definition
QueryResult = list[dict[str, Any]]

# Structure
[
    {
        "capture_name": str,      # Required: キャプチャ名
        "node_type": str,         # Required: ノードタイプ
        "start_line": int,        # Required: 開始行番号 (1-based)
        "end_line": int,          # Required: 終了行番号 (1-based)
        "content": str,           # Required: コード内容
    },
    # ... more results
]
```

### Empty Response

```python
# No matches found
[]  # Empty list, not None
```

### Error Response

```python
# Exceptions that may be raised
- ValueError: Invalid parameters
- FileNotFoundError: File does not exist
- PermissionError: File access denied
- AsyncTimeoutError: Operation timeout
- AsyncQueryError: Query execution failed
```

## Async Behavior Contract

### Execution Model

```python
# Caller Contract
async def caller_example():
    service = QueryService()
    
    # ✅ Correct usage
    results = await service.execute_query(
        file_path="example.py",
        language="python",
        query_key="function"
    )
    
    # ❌ Incorrect usage (will raise TypeError)
    # results = service.execute_query(...)  # Missing await
```

### Timeout Behavior

```python
# Default timeout: 30 seconds
async def execute_with_timeout():
    try:
        async with asyncio.timeout(30.0):
            results = await service.execute_query(...)
    except asyncio.TimeoutError:
        # Handle timeout
        pass
```

### Cancellation Support

```python
# Cancellation-aware execution
async def cancellable_execution():
    task = asyncio.create_task(
        service.execute_query(...)
    )
    
    try:
        results = await task
    except asyncio.CancelledError:
        # Cleanup resources
        pass
```

## Performance Contract

### Response Time Guarantees

| File Size | Expected Response Time | Maximum Response Time |
|-----------|----------------------|----------------------|
| < 1MB | < 100ms | < 500ms |
| 1-10MB | < 500ms | < 2s |
| 10-100MB | < 2s | < 10s |
| > 100MB | < 10s | < 30s |

### Memory Usage Contract

```python
# Memory efficiency guarantees
- Base memory overhead: < 10MB
- Per-file overhead: < file_size * 1.5
- Concurrent execution: Linear scaling
- Memory cleanup: Automatic after completion
```

### Concurrency Contract

```python
# Concurrent execution support
async def concurrent_queries():
    tasks = [
        service.execute_query(file1, "python", "function"),
        service.execute_query(file2, "javascript", "class"),
        service.execute_query(file3, "typescript", "method"),
    ]
    
    # All queries execute concurrently
    results = await asyncio.gather(*tasks)
    
    # Performance guarantee: 
    # Concurrent execution should be 2-3x faster than sequential
```

## Error Handling Contract

### Exception Hierarchy

```python
class AsyncQueryError(Exception):
    """Base exception for async query operations"""
    
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        super().__init__(message)
        self.context = context or {}

class AsyncFileReadError(AsyncQueryError):
    """File reading operation failed"""
    pass

class AsyncTimeoutError(AsyncQueryError):
    """Operation exceeded timeout limit"""
    pass

class AsyncValidationError(AsyncQueryError):
    """Input validation failed"""
    pass
```

### Error Context

```python
# Error context information
{
    "operation": "execute_query",
    "file_path": "/path/to/file.py",
    "language": "python",
    "query_type": "function",
    "start_time": "2025-10-14T02:30:00Z",
    "duration": 1.234,
    "error_type": "AsyncFileReadError",
    "error_message": "File not found"
}
```

## Backward Compatibility Contract

### Migration Path

```python
# Phase 1: Async-only (Current target)
class QueryService:
    async def execute_query(self, ...):
        # New async implementation
        pass

# Phase 2: Dual interface (If needed)
class QueryService:
    async def execute_query(self, ...):
        # Async implementation
        pass
    
    def execute_query_sync(self, ...):
        # Sync wrapper for backward compatibility
        return asyncio.run(self.execute_query(...))
```

### Breaking Changes

**None** - This is a non-breaking change because:
1. Callers already use `await` (QueryCommand, QueryTool)
2. Method signature remains identical except for `async` keyword
3. Return types and exceptions remain the same
4. No public API changes

## Testing Contract

### Unit Test Requirements

```python
@pytest.mark.asyncio
async def test_execute_query_basic():
    """Basic async query execution test"""
    service = QueryService()
    results = await service.execute_query(
        file_path="test.py",
        language="python",
        query_key="function"
    )
    assert isinstance(results, list)

@pytest.mark.asyncio
async def test_execute_query_concurrent():
    """Concurrent execution test"""
    service = QueryService()
    tasks = [
        service.execute_query("test1.py", "python", "function"),
        service.execute_query("test2.py", "python", "class"),
    ]
    results = await asyncio.gather(*tasks)
    assert len(results) == 2
```

### Integration Test Requirements

```python
@pytest.mark.asyncio
async def test_cli_integration():
    """CLI command integration test"""
    command = QueryCommand(mock_args)
    exit_code = await command.execute_async("python")
    assert exit_code == 0

@pytest.mark.asyncio
async def test_mcp_integration():
    """MCP tool integration test"""
    tool = QueryTool()
    result = await tool.execute({
        "file_path": "test.py",
        "query_key": "function"
    })
    assert result["success"] is True
```

### Performance Test Requirements

```python
@pytest.mark.asyncio
async def test_performance_baseline():
    """Performance baseline test"""
    service = QueryService()
    start_time = time.time()
    
    results = await service.execute_query(
        file_path="large_file.py",
        language="python",
        query_key="function"
    )
    
    duration = time.time() - start_time
    assert duration < 5.0  # 5 second limit
    assert len(results) > 0
```

## Security Contract

### Input Sanitization

```python
# File path validation
- Path traversal protection (../, ..\)
- Symlink resolution and validation
- Project boundary enforcement
- Permission verification

# Query validation
- Tree-sitter syntax validation
- Injection attack prevention
- Resource limit enforcement
```

### Resource Protection

```python
# Resource limits
- Maximum file size: 100MB
- Maximum execution time: 30s
- Maximum memory usage: 500MB
- Maximum concurrent operations: 10
```

## Monitoring Contract

### Metrics Collection

```python
# Performance metrics
- execution_time: float
- memory_usage: int (bytes)
- file_size: int (bytes)
- result_count: int

# Error metrics
- error_rate: float (0.0-1.0)
- timeout_rate: float (0.0-1.0)
- retry_count: int

# Usage metrics
- query_type_distribution: dict[str, int]
- language_distribution: dict[str, int]
- concurrent_operations: int
```

### Health Checks

```python
async def health_check():
    """Service health verification"""
    try:
        # Quick test query
        results = await service.execute_query(
            "test_file.py", "python", "function"
        )
        return {"status": "healthy", "response_time": duration}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

---

**Created**: 2025-10-14  
**Version**: 1.0  
**Status**: Final  
**Compliance**: Tree-sitter Analyzer Constitution v1.0.1