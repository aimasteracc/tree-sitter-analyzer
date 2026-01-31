---
inclusion: always
---

# 🤖 AI 助手编码行为指令

**执行级别**: MANDATORY - 所有代码生成/修改操作必须遵循

## 核心原则

### 1. 质量优先原则（CRITICAL）

**在编写或修改任何 Python 代码前，必须：**

1. **自动检查质量基准**
   ```bash
   python .kiro/optimization_work/check_optimization_quality.py <target_file>
   ```

2. **确认最低标准**
   - 现有代码 < 90分：必须优化到 >= 90
   - 新代码：必须直接达到 >= 90
   - 禁止提交任何 < 90 分的代码

3. **完整性检查**
   - ✅ 模块头：11个必需章节
   - ✅ 异常类：3个标准类（Base + 2 Specific）
   - ✅ 公共方法：Args/Returns/Note 100%覆盖
   - ✅ 私有方法：Args/Returns/Note 简化版
   - ✅ 性能监控：5-8个 perf_counter 监控点
   - ✅ 统计追踪：_stats + get_statistics()
   - ✅ 导出列表：__all__ 包含异常类

### 2. 一致性原则（MANDATORY）

**同一文件内所有方法必须统一：**

- 文档格式完全一致（章节顺序、缩进、标点）
- 异常类格式一致（pass 单独成行）
- 类型注解风格一致（PEP 484）
- 命名约定一致（snake_case for functions）

**禁止出现**:
```python
# ❌ 错误：格式不一致
def method1(arg: str) -> int:
    """Brief.
    
    Args: arg description
    Returns: int description
    """

def method2(x: str) -> bool:
    """Brief description.
    
    Args:
        x: description
        
    Returns:
        bool: description
    """
```

**正确做法**:
```python
# ✅ 正确：完全统一
def method1(arg: str) -> int:
    """Brief description.
    
    Args:
        arg: Description of arg
        
    Returns:
        int: Description of return value
        
    Note:
        Important behavior
    """

def method2(x: str) -> bool:
    """Brief description.
    
    Args:
        x: Description of x
        
    Returns:
        bool: Description of return value
        
    Note:
        Important behavior
    """
```

### 3. 自动化原则（CRITICAL）

**不要等用户要求，主动执行：**

1. **代码修改前**:
   - 自动读取 `.kiro/steering/coding_checklist.md`
   - 自动运行质量检查
   - 自动识别不符合项

2. **代码修改中**:
   - 自动应用所有标准模式
   - 自动补充缺失的文档章节
   - 自动添加性能监控和统计追踪

3. **代码修改后**:
   - 自动再次运行质量检查
   - 自动确认分数 >= 90
   - 自动报告优化结果

### 4. 完整性原则（MANDATORY）

**永远不要留下半成品：**

- ❌ 禁止：只优化部分方法
- ❌ 禁止：跳过某些文档章节
- ❌ 禁止：遗漏性能监控
- ✅ 要求：一次性完成所有优化
- ✅ 要求：确保所有方法格式统一
- ✅ 要求：确保质量检查通过

## 编码工作流（强制执行）

### 阶段 1: 准备阶段（自动）

```python
# 伪代码：AI 内部逻辑
if task.involves_python_code():
    # 1. 加载编码标准
    load_file(".kiro/steering/coding_checklist.md")
    load_file("CODING_STANDARDS.md", section="Level 2-3")
    
    # 2. 如果是修改现有文件
    if target_file.exists():
        baseline_score = run_quality_check(target_file)
        identify_issues(baseline_score)
    
    # 3. 规划优化策略
    if baseline_score < 90:
        plan_optimization_phases()
```

### 阶段 2: 执行阶段（按顺序）

**Phase 1: 模块头优化**
```python
# 确保包含11个必需章节
required_sections = [
    "Brief description",
    "Detailed description", 
    "Features",
    "Architecture",
    "Usage",
    "Performance Characteristics",
    "Thread Safety",
    "Dependencies",
    "Error Handling",
    "Note",
    "Example"
]
```

**Phase 2: 异常类优化**
```python
# 必须定义3个异常类
class ModuleBaseException(Exception):
    """Base exception."""
    pass  # 单独成行

class SpecificError1(ModuleBaseException):
    """Specific error 1."""
    pass

class SpecificError2(ModuleBaseException):
    """Specific error 2."""
    pass
```

**Phase 3-4: 方法文档优化**
```python
# 公共方法：Args/Returns/Note + 4个推荐章节
# 私有方法：Args/Returns/Note

# 无参数方法必须明确
def method(self) -> dict:
    """Brief.
    
    Args:
        None (instance method with no parameters)
```

**Phase 5-6: 性能和统计**
```python
# 5-8个 perf_counter 监控点
# _stats + get_statistics() 实现
```

**Phase 7: 导出列表**
```python
__all__ = [
    'PublicClass',
    'public_function',
    'ModuleBaseException',  # 必须导出
    'SpecificError1',
    'SpecificError2'
]
```

### 阶段 3: 验证阶段（强制）

```python
# 伪代码：AI 内部逻辑
final_score = run_quality_check(target_file)

if final_score >= 90:
    report_success(final_score)
else:
    # 不应该发生！必须修复
    identify_remaining_issues()
    fix_issues()
    rerun_validation()
```

## 常见错误及自动修正

### 错误 1: 遗漏 Args 章节（无参数方法）

```python
# ❌ 错误
def get_stats(self) -> dict:
    """Get statistics.
    
    Returns:
        dict: Statistics
    """

# ✅ 修正
def get_statistics(self) -> dict[str, Any]:
    """Get statistics.
    
    Args:
        None (instance method with no parameters)
        
    Returns:
        dict[str, Any]: Statistics
    """
```

### 错误 2: pass 语句格式错误

```python
# ❌ 错误
class MyException(Exception):
    """Exception.""" pass

# ✅ 修正
class MyException(Exception):
    """Exception."""
    pass
```

### 错误 3: 遗漏 Note 章节

```python
# ❌ 错误：只有 Args/Returns
def method(self, x: int) -> str:
    """Brief.
    
    Args:
        x: Description
        
    Returns:
        str: Result
    """

# ✅ 修正：必须有 Note
def method(self, x: int) -> str:
    """Brief.
    
    Args:
        x: Description
        
    Returns:
        str: Result
        
    Note:
        Important behavior or limitation
    """
```

### 错误 4: 性能监控缺失

```python
# ❌ 错误：没有性能监控
def process(self, data):
    result = self._do_work(data)
    return result

# ✅ 修正：添加监控
def process(self, data):
    start = perf_counter()
    try:
        result = self._do_work(data)
        self._stats['success_count'] += 1
        return result
    finally:
        self._stats['total_time'] += perf_counter() - start
```

## 用户交互模式

### 模式 1: 主动报告（推荐）

```
用户: "优化 python_plugin.py"

AI: [自动执行]
1. 读取文件
2. 运行质量检查（baseline: 0/100）
3. 识别15个问题
4. 一次性修复所有问题
5. 再次运行质量检查（97/100 PASS）
6. 报告结果

输出: "✅ python_plugin.py 已优化到 97/100 (PASS)
- 13个公共方法已补充完整文档
- 所有方法现在都有 Args/Returns/Note"
```

### 模式 2: 预防性检查（自动）

```
用户: "修改 formatter.py 的 format_result() 方法"

AI: [自动执行]
1. 读取文件当前状态
2. 运行质量检查（baseline: 80/100 PARTIAL）
3. 修改 format_result()
4. 同时修复其他低分项
5. 确保最终 >= 90

输出: "✅ 已修改 format_result() 并优化整个文件到 100/100"
```

### 模式 3: 新文件创建（强制标准）

```
用户: "创建一个新的 analyzer.py"

AI: [自动应用所有标准]
1. 生成11章节模块头
2. 定义3个异常类
3. 所有方法包含完整文档
4. 添加性能监控
5. 实现统计追踪
6. 定义 __all__
7. 运行质量检查（目标: 100/100）

输出: "✅ 已创建 analyzer.py (100/100 PASS)"
```

## 关键提醒（始终显示）

**在执行任何Python代码操作时，必须在心中默念：**

1. ✅ 我已检查 `.kiro/steering/coding_checklist.md`
2. ✅ 我已运行质量检查获取 baseline
3. ✅ 我将确保所有方法格式统一
4. ✅ 我将确保最终分数 >= 90/100
5. ✅ 我将主动完成所有优化，不等用户催促

## 工具快捷方式

```bash
# 质量检查
alias qc='python .kiro/optimization_work/check_optimization_quality.py'

# 使用
qc tree_sitter_analyzer/languages/python_plugin.py

# 批量检查
find tree_sitter_analyzer -name "*.py" -exec python .kiro/optimization_work/check_optimization_quality.py {} \;
```

## 参考资料（优先级排序）

1. **CRITICAL**: `.kiro/steering/coding_checklist.md` - 强制检查清单
2. **CRITICAL**: `.kiro/optimization_work/check_optimization_quality.py` - 自动检查工具
3. **HIGH**: `.kiro/optimization_work/README.md` - 完整工作流指南（850行）
4. **HIGH**: `CODING_STANDARDS.md` - Level 2-3 章节
5. **MEDIUM**: `.kiro/steering/tech.md` - Level 2-3 最適化プロセス

---

**最后更新**: 2026-01-31 (Session 14)
**强制执行**: 每次代码操作前自动加载
**监督机制**: 质量检查分数 < 90 = 操作失败
