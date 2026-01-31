---
inclusion: always
---

# 🔒 编码强制检查清单

**重要性**: CRITICAL - 每次编码/优化前必须执行检查

## 📋 编码前自动检查

### 1. 质量评分基准（强制）

```bash
# 任何代码修改前必须运行
python .kiro/optimization_work/check_optimization_quality.py <target_file>

# 质量要求
✅ PASS: >= 90/100
⚠️  PARTIAL: 70-89/100  
❌ FAIL: 0-69/100
```

**禁止**: 提交任何 < 90 分的代码

### 2. 模块头结构（11个必需章节）

```python
"""Brief one-line description.

Detailed description explaining purpose, architecture, and key features.

Features:
    - Feature 1: Description
    - Feature 2: Description
    - Feature 3: Description

Architecture:
    - Component 1: Purpose
    - Component 2: Purpose

Usage:
    Basic usage example code

Performance Characteristics:
    - Time Complexity: O(n)
    - Memory Usage: Description
    - Optimization techniques used

Thread Safety:
    - Thread-safe operations: Description
    - Lock mechanisms: RLock for shared state

Dependencies:
    - External: List external dependencies
    - Internal: List internal imports

Error Handling:
    - Custom exceptions defined
    - Recovery strategies

Note:
    Important limitations or warnings

Example:
    ```python
    # Concrete usage example
    ```
"""
```

### 3. 异常类模式（强制3个）

```python
class ModuleBaseException(Exception):
    """Base exception for this module."""
    pass


class SpecificError1(ModuleBaseException):
    """First specific error condition."""
    pass


class SpecificError2(ModuleBaseException):
    """Second specific error condition."""
    pass
```

**禁止**: pass 语句与类定义在同一行

### 4. 公共方法文档（100%覆盖）

#### 必需章节（3个）
```python
def public_method(self, arg1: str, arg2: int = 10) -> dict[str, Any]:
    """Brief description.
    
    Args:
        arg1: Description of arg1
        arg2: Description of arg2 (default: 10)
        
    Returns:
        dict[str, Any]: Description of return value
        
    Note:
        Important behavior or limitations
    """
```

**无参数方法必须明确说明**:
```python
def get_statistics(self) -> dict[str, Any]:
    """Get statistics.
    
    Args:
        None (instance method with no parameters)
```

#### 推荐章节（4个）
- `Raises:` 列出所有可能抛出的异常
- `Performance:` 说明时间/空间复杂度
- `Thread Safety:` 说明线程安全保证
- `Example:` 提供使用示例

### 5. 私有方法文档（简化版）

```python
def _private_helper(self, data: list[str]) -> str:
    """Brief description.
    
    Args:
        data: Description
        
    Returns:
        str: Description
        
    Note:
        Implementation detail
    """
```

### 6. 性能监控（5-8个监控点）

```python
from time import perf_counter

def __init__(self):
    self._stats = {
        'total_calls': 0,
        'total_time': 0.0,
        'cache_hits': 0,
        'errors': 0
    }

def operation(self):
    start = perf_counter()
    try:
        self._stats['total_calls'] += 1
        # ... operation ...
    finally:
        self._stats['total_time'] += perf_counter() - start
```

### 7. 统计追踪（标准模式）

```python
def get_statistics(self) -> dict[str, Any]:
    """Get performance and usage statistics.
    
    Args:
        None (instance method with no parameters)
        
    Returns:
        dict[str, Any]: Statistics including:
            - total_calls: Total number of calls
            - hit_rate: Cache hit rate (derived)
            - avg_time: Average operation time (derived)
    """
    total = max(1, self._stats['total_calls'])
    return {
        **self._stats,
        'hit_rate': self._stats['cache_hits'] / total,
        'avg_time': self._stats['total_time'] / total
    }
```

### 8. 导出列表（__all__）

```python
__all__ = [
    # Public classes
    'MainClass',
    'HelperClass',
    # Public functions
    'public_function',
    # Exceptions (always export)
    'ModuleBaseException',
    'SpecificError1',
    'SpecificError2'
]
```

**类型注解支持**:
```python
__all__: list[str] = [...]  # ✅ 支持
```

## 🚫 禁止事项

1. **不得跳过质量检查**: 任何代码修改必须先运行 `check_optimization_quality.py`
2. **不得简化文档**: 公共方法必须包含 Args/Returns/Note
3. **不得混合风格**: 同一文件内所有方法必须统一格式
4. **不得省略异常**: 每个模块必须定义3个自定义异常类
5. **不得忽略性能**: 关键操作必须有 perf_counter 监控
6. **不得缺少统计**: 必须实现 `_stats` 字典和 `get_statistics()` 方法

## ✅ 编码后验证

### 完成代码后必须执行

```bash
# 1. 运行质量检查
python .kiro/optimization_work/check_optimization_quality.py <file>

# 2. 确认 PASS
# Expected: "Overall Score: XX/100" where XX >= 90

# 3. 查看详细报告
python .kiro/optimization_work/check_optimization_quality.py <file> > quality_report.txt

# 4. 运行单元测试（如果存在）
pytest tests/test_<module>.py -v

# 5. 运行类型检查
mypy <file>

# 6. 运行代码格式检查
ruff check <file>
```

## 📊 质量标准矩阵

| 检查项 | 权重 | 要求 |
|--------|------|------|
| 模块头 | -10/issue | 11个章节完整 |
| 异常类 | -10/issue | 3个类，格式正确 |
| 公共方法文档 | -10/issue | Args/Returns/Note 100% |
| 私有方法文档 | -3/warning | Args/Returns 推荐 |
| 性能监控 | -3/warning | 5-8个监控点 |
| 统计追踪 | -3/warning | _stats + get_statistics() |
| __all__ | -10/issue | 包含异常类 |

## 🔄 标准工作流

```
1. 读取目标文件
   ↓
2. 运行质量检查（baseline）
   ↓
3. 识别缺失项
   ↓
4. 按8个阶段优化
   ↓
5. 再次运行质量检查
   ↓
6. 确认 >= 90/100
   ↓
7. 提交更改
```

## 📚 参考资源

- **完整指南**: `.kiro/optimization_work/README.md` (850行)
- **代码模板**: 同上文件中的所有模板
- **质量检查器**: `.kiro/optimization_work/check_optimization_quality.py`
- **编码标准**: `CODING_STANDARDS.md` - Level 2-3 章节
- **技术栈**: `.kiro/steering/tech.md` - Level 2-3 最適化プロセス

## 🎯 当前项目状态

```
Level 2-3 优化进度: 2/182 (1.1%)

✅ python_formatter.py: 100/100 PASS
✅ python_plugin.py: 97/100 PASS
⏳ 剩余: 180 files

目标: 所有文件 >= 90/100
```

---

**最后更新**: 2026-01-31 (Session 14)
**强制执行**: 每次编码前必须阅读此检查清单
