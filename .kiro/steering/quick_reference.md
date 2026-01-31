---
inclusion: always
---

# ⚡ 编码标准速查卡

**用途**: AI助手每次代码操作时的快速参考

---

## 🎯 核心要求（3秒检查）

| 项目 | 要求 | 检查命令 |
|------|------|----------|
| **质量分数** | >= 90/100 | `python .kiro/optimization_work/check_optimization_quality.py <file>` |
| **模块头** | 11章节 | 包含Features/Architecture/Usage/Performance/... |
| **异常类** | 3个类 | Base + 2 Specific, pass单独成行 |
| **公共方法** | Args/Returns/Note | 100%覆盖，无参数写"None" |
| **私有方法** | Args/Returns/Note | 简化版 |
| **性能监控** | 5-8点 | perf_counter + _stats |
| **统计方法** | get_statistics() | 包含派生指标 |
| **导出列表** | __all__ | 包含异常类 |

---

## 📝 标准模板（30秒复制）

### 模块头模板
```python
"""Brief one-line description.

Detailed multi-line description.

Features:
    - Feature 1: Description
    - Feature 2: Description

Architecture:
    - Component: Purpose

Usage:
    ```python
    example_code()
    ```

Performance Characteristics:
    - Time: O(n)
    - Space: O(1)

Thread Safety:
    - Thread-safe: Yes/No
    - Lock: RLock/None

Dependencies:
    - External: list
    - Internal: list

Error Handling:
    - Exceptions: 3 custom classes
    - Recovery: Description

Note:
    Important limitations

Example:
    ```python
    concrete_example()
    ```
"""
```

### 异常类模板
```python
class ModuleBaseException(Exception):
    """Base exception for this module."""
    pass


class SpecificError1(ModuleBaseException):
    """First specific error."""
    pass


class SpecificError2(ModuleBaseException):
    """Second specific error."""
    pass
```

### 公共方法模板
```python
def public_method(self, arg1: str, arg2: int = 10) -> dict[str, Any]:
    """Brief description.
    
    Args:
        arg1: Description
        arg2: Description (default: 10)
        
    Returns:
        dict[str, Any]: Description
        
    Raises:
        SpecificError1: When condition
        
    Performance:
        Time: O(n)
        
    Thread Safety:
        Thread-safe with lock
        
    Note:
        Important behavior
        
    Example:
        ```python
        result = obj.public_method("test", 20)
        ```
    """
    start = perf_counter()
    try:
        self._stats['total_calls'] += 1
        # implementation
        result = {"key": "value"}
        return result
    except Exception as e:
        self._stats['errors'] += 1
        raise SpecificError1(f"Failed: {e}") from e
    finally:
        self._stats['total_time'] += perf_counter() - start
```

### 无参数方法模板
```python
def get_statistics(self) -> dict[str, Any]:
    """Get statistics.
    
    Args:
        None (instance method with no parameters)
        
    Returns:
        dict[str, Any]: Statistics with derived metrics
        
    Note:
        Includes hit_rate and avg_time
    """
    total = max(1, self._stats['total_calls'])
    return {
        **self._stats,
        'hit_rate': self._stats.get('hits', 0) / total,
        'avg_time': self._stats.get('total_time', 0.0) / total
    }
```

### 私有方法模板
```python
def _private_helper(self, data: list[str]) -> str:
    """Brief description.
    
    Args:
        data: Input data list
        
    Returns:
        str: Processed result
        
    Note:
        Internal helper, not for external use
    """
    return "".join(data)
```

### 统计初始化模板
```python
def __init__(self):
    self._stats = {
        'total_calls': 0,
        'total_time': 0.0,
        'cache_hits': 0,
        'errors': 0,
        'success_count': 0
    }
    self._lock = RLock()  # 如果需要线程安全
```

### __all__ 模板
```python
__all__ = [
    # Public classes
    'MainClass',
    'HelperClass',
    # Public functions  
    'main_function',
    # Exceptions (必须导出)
    'ModuleBaseException',
    'SpecificError1',
    'SpecificError2'
]
```

---

## 🚫 常见错误（10秒避免）

| 错误 | 正确 |
|------|------|
| `class E(Exception): """Doc.""" pass` | `"""Doc."""`<br>`pass` (单独成行) |
| 方法缺少 `Note:` | 必须有 `Note:` 章节 |
| 无参数方法没写 `Args:` | `Args: None (instance method...)` |
| `__all__ = ['Class']` (遗漏异常) | 必须包含3个异常类 |
| 没有性能监控 | 添加 `perf_counter` + `_stats` |
| 没有 `get_statistics()` | 必须实现此方法 |

---

## ⚡ 工作流（1分钟执行）

```
1. 读取目标文件
   ↓
2. 运行: python .kiro/optimization_work/check_optimization_quality.py <file>
   ↓
3. 查看 baseline 分数
   ↓
4. 如果 < 90: 识别缺失项
   ↓
5. 应用对应模板修复
   ↓
6. 再次运行质量检查
   ↓
7. 确认 >= 90/100
   ↓
8. 报告结果
```

---

## 📊 分数计算（理解扣分）

| 问题类型 | 扣分 | 示例 |
|---------|------|------|
| 模块头缺少章节 | -10 | 少了 Performance Characteristics |
| 异常类不足 | -10 | 只定义了2个，需要3个 |
| 异常类格式错误 | -10 | pass 和类定义在同一行 |
| 公共方法缺文档 | -10 | 没有 Args/Returns/Note |
| __all__ 缺失 | -10 | 没有定义导出列表 |
| 私有方法缺文档 | -3 | 警告级别 |
| 性能监控缺失 | -3 | 没有 perf_counter |
| 统计追踪缺失 | -3 | 没有 get_statistics() |

**目标**: 100分 (完美)
**及格线**: 90分 (PASS)
**警告线**: 70分 (PARTIAL)
**失败线**: < 70分 (FAIL)

---

## 🎯 优先级（紧急度排序）

**P0 - 阻塞性（-10分/个）**:
1. 模块头11章节
2. 3个异常类（格式正确）
3. 公共方法 Args/Returns/Note
4. __all__ 导出列表

**P1 - 警告性（-3分/个）**:
1. 私有方法文档
2. 性能监控点
3. 统计追踪方法

**推荐（不扣分但建议添加）**:
1. 公共方法的 Raises/Performance/Thread Safety/Example
2. 更详细的 Note 说明
3. 更多性能监控点（超过5个）

---

## 🔗 完整文档链接

| 文档 | 用途 | 优先级 |
|------|------|--------|
| `.kiro/steering/coding_checklist.md` | 完整检查清单 | ⭐⭐⭐⭐⭐ |
| `.kiro/steering/ai_instructions.md` | AI行为指令 | ⭐⭐⭐⭐⭐ |
| `.kiro/optimization_work/README.md` | 850行完整指南 | ⭐⭐⭐⭐ |
| `CODING_STANDARDS.md` | 官方编码标准 | ⭐⭐⭐⭐ |
| `.kiro/steering/tech.md` | 技术栈和流程 | ⭐⭐⭐ |

---

**最后更新**: 2026-01-31
**用途**: AI助手每次代码操作的必读速查
**原则**: 看到Python代码 = 自动应用这些标准
