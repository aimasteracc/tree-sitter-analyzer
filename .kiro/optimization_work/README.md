# Level 2-3 Optimization 工作流程

这个目录包含用于执行和验证 Level 2-3 优化的工具和文档。

## 📚 文档

### 1. python_plugin_optimization_pattern.md
完整的优化模式文档，包含：
- Before/After 对比
- 6 个优化模式（异常、文档、性能监控等）
- 8 阶段实施步骤
- 质量检查清单
- ROI 分析

**用途**: 作为优化的参考指南和模板

## 🛠️ 工具

### 1. check_optimization_quality.py
自动化质量检查工具，确保文件符合 Level 2-3 标准。

**检查项目**:
- ✅ 模块文档头格式（11个必需部分）
- ✅ 自定义异常类（3个）
- ✅ 公共方法文档完整性（Args/Returns/Raises/Performance/Thread Safety/Note/Example）
- ✅ 私有方法文档（Args/Returns/Note）
- ✅ 性能监控（perf_counter）
- ✅ 统计追踪（_stats + get_statistics()）
- ✅ __all__ 导出列表

**使用方法**:
```bash
# 检查单个文件
python .kiro/optimization_work/check_optimization_quality.py <file_path>

# 示例
python .kiro/optimization_work/check_optimization_quality.py tree_sitter_analyzer/formatters/python_formatter.py
```

**输出示例**:
```
🔍 Checking: python_formatter.py
======================================================================

📄 Module Header:
  ✓ All required sections present

🚨 Exception Classes:
  ✓ Found 3 exception classes

📚 Public Methods:
  Required sections: 100.0%
  All sections: 88.6%

🔒 Private Methods:
  ✓ All 15 methods documented

⚡ Performance Monitoring:
  ✓ perf_counter imported
  ✓ Found 2 monitoring points

📊 Statistics Tracking:
  ✓ _stats dictionary found
  ✓ get_statistics() method found

📦 Exports:
  ✓ __all__ list present

🎯 Overall Score: 100/100
✅ PASS - Meets Level 2-3 standards
```

**评分标准**:
- 90-100: ✅ PASS - 符合 Level 2-3 标准
- 70-89: ⚠️ PARTIAL - 需要改进
- 0-69: ❌ FAIL - 不符合标准

**退出码**:
- 0: PASS
- 1: PARTIAL
- 2: FAIL

## 🔄 标准化工作流程

### 步骤 1: 选择文件
从 Phase 2/3 计划中选择下一个要优化的文件。

### 步骤 2: 基线检查
```bash
python .kiro/optimization_work/check_optimization_quality.py <file_path>
```
记录初始分数和问题列表。

### 步骤 3: 执行优化
按照 8 阶段模式进行优化：

1. **阶段 1-2**: 自定义异常类
   ```python
   class ModuleNameError(Exception):
       """Base exception for module operations."""
       pass
   
   class ExtractionError(ModuleNameError):
       """Raised when extraction fails."""
       pass
   
   class ValidationError(ModuleNameError):
       """Raised when validation fails."""
       pass
   ```

2. **阶段 3**: 增强类文档
   - Features (7-10 项)
   - Architecture (4-5 行)
   - Performance (具体数字)
   - Thread Safety (明确说明)
   - Attributes (列出所有属性)
   - Example (使用示例)

3. **阶段 4**: 优化 `__init__()`
   ```python
   def __init__(self) -> None:
       """Initialize with caching and statistics.
       
       Args:
           None (or list specific parameters)
       
       Raises:
           ModuleError: If initialization fails
       
       Note:
           Thread-safe, each instance independent.
       """
       self._cache = {}
       self._lock = threading.RLock()
       self._stats = {
           "operations": 0,
           "total_time_ms": 0.0,
       }
   ```

4. **阶段 5**: 添加性能监控
   ```python
   def method(self, data: Any) -> Any:
       """Method description.
       
       Args:
           data: Input data
       
       Returns:
           Processed result
       
       Raises:
           ExtractionError: If processing fails
       
       Performance:
           Typical: 2-5ms, Cache hit: ~1ms
       
       Thread Safety:
           Thread-safe through locking
       
       Note:
           Additional notes
       
       Example:
           >>> obj.method(data)
       """
       start_time = perf_counter()
       try:
           result = self._process(data)
           with self._lock:
               self._stats["operations"] += 1
           return result
       except Exception as e:
           raise ExtractionError(f"Failed: {e}") from e
       finally:
           elapsed_ms = (perf_counter() - start_time) * 1000
           with self._lock:
               self._stats["total_time_ms"] += elapsed_ms
           if elapsed_ms > 10:
               logger.warning(f"Slow: {elapsed_ms:.2f}ms")
   ```

5. **阶段 6**: 增强方法文档
   - 公共方法: 完整 Level 2-3 文档
   - 私有方法: Args/Returns/Note

6. **阶段 7**: 添加统计方法
   ```python
   def get_statistics(self) -> dict[str, Any]:
       """Get performance statistics.
       
       Args:
           None (instance method)
       
       Returns:
           Dictionary with operations, total_time_ms, avg_time_ms
       
       Thread Safety:
           Returns copy, safe for concurrent access
       
       Performance:
           O(1), <1ms
       """
       with self._lock:
           stats = self._stats.copy()
           if stats["operations"] > 0:
               stats["avg_time_ms"] = stats["total_time_ms"] / stats["operations"]
           return stats
   ```

7. **阶段 8**: 更新 __all__
   ```python
   __all__ = [
       # Exception classes
       "ModuleError",
       "ExtractionError", 
       "ValidationError",
       # Main classes
       "MainClass",
   ]
   ```

### 步骤 4: 代码质量检查
```bash
# Ruff 检查和修复
uv run ruff check <file_path> --fix --unsafe-fixes

# 测试运行
uv run pytest tests/ -k <module_name> -v --no-cov
```

### 步骤 5: 质量验证
```bash
python .kiro/optimization_work/check_optimization_quality.py <file_path>
```

**目标**: Score >= 90 (PASS)

### 步骤 6: 生成完成报告
使用 PowerShell 脚本生成详细报告（参考 python_plugin.py 完成报告）。

### 步骤 7: 更新进度
```python
manage_todo_list([
    {"id": 1, "status": "completed", "title": "..."},
    {"id": 2, "status": "in-progress", "title": "..."},
    ...
])
```

## 📊 质量标准

### Level 2-3 优化必须满足:

**模块级别**:
- ✅ 完整的模块文档头（11个部分）
- ✅ 3 个自定义异常类
- ✅ 清晰的导入分组

**类级别**:
- ✅ 增强的类文档（Features/Architecture/Performance/Thread Safety/Attributes/Example）
- ✅ __init__() 完整文档
- ✅ 统计追踪基础设施（_stats + _lock）

**方法级别**:
- ✅ 公共方法: Args/Returns/Raises/Performance/Thread Safety/Note/Example (至少前3个)
- ✅ 私有方法: Args/Returns/Note
- ✅ 性能监控: 5-8个关键点
- ✅ 异常处理: 自定义异常 + 错误链

**导出**:
- ✅ __all__ 包含所有公共 API（异常类 + 主类）

### 文档覆盖率目标:
- Args: 100%（所有公共方法）
- Returns: 100%（所有公共方法）
- Raises: 70%+（关键方法）
- Performance: 70%+（性能敏感方法）
- Thread Safety: 60%+（有并发的方法）
- Note: 80%+
- Example: 40%+

## 🎯 使用场景

### 1. 开始新文件优化前
```bash
# 检查基线
python .kiro/optimization_work/check_optimization_quality.py <next_file>
```

### 2. 优化过程中
```bash
# 定期检查（每完成2-3个阶段）
python .kiro/optimization_work/check_optimization_quality.py <current_file>
```

### 3. 完成优化后
```bash
# 最终验证
python .kiro/optimization_work/check_optimization_quality.py <completed_file>

# 必须达到 Score >= 90
```

### 4. CI/CD 集成
```bash
# 在 CI 中运行
for file in $(find tree_sitter_analyzer -name "*.py"); do
    python .kiro/optimization_work/check_optimization_quality.py $file || exit 1
done
```

## 📈 进度跟踪

### Phase 2 (Sample Deep Dive - 5 files):
- [x] python_plugin.py (Score: TBD - needs recheck)
- [x] python_formatter.py (Score: 100/100 ✅)
- [ ] analyze_scale_tool.py
- [ ] cache_service.py
- [ ] default_command.py

### Phase 3 (Full Project - 182 files):
目标: 所有文件 Score >= 90

## 🔧 故障排除

### 常见问题

**Q: 为什么 get_statistics() 需要 Args: 部分？**
A: 即使方法没有参数，也需要明确说明 `Args: None (instance method)` 以保持一致性。

**Q: 私有方法需要完整文档吗？**
A: 不需要。私有方法只需要 Args/Returns/Note 三部分，保持简洁。

**Q: 性能监控点数量建议？**
A: 5-8个关键方法。不需要监控所有方法，聚焦在：
- 主要入口方法（analyze, format, extract）
- 复杂算法
- 缓存操作
- 外部调用

**Q: Thread Safety 何时需要？**
A: 当方法使用共享状态（如 _cache, _stats）或可能并发调用时。

## 📝 下一步

1. 使用质量检查工具重新验证 python_plugin.py
2. 修复发现的问题
3. 继续优化 analyze_scale_tool.py（下一个文件）
4. 建立自动化批量检查脚本

---

**维护者**: aisheng.yu  
**最后更新**: 2026-01-31  
**版本**: 1.0
