# 错误模式记录 (Error Patterns Registry)

> 本文档记录在开发过程中发现的常见错误模式，用于指导LLM和开发者避免重复犯错。
> 每次发现新的错误模式时，应在此文档中添加记录。

---

## 1. Stub代码问题 (Stub Code Anti-Pattern)

### 问题描述
创建只包含 `pass` 或 `raise NotImplementedError` 的占位代码，给人"功能完整"的假象。

### 错误示例
```python
# BAD: 空壳代码
class SecurityScanner:
    def __init__(self):
        pass  # TODO: Initialize
    
    def execute(self, *args, **kwargs):
        raise NotImplementedError("Feature needs implementation")
```

### 正确做法
- 不要创建空壳代码，要么完整实现，要么不创建
- 如果功能未实现，在README中明确标注为"计划中"
- 使用 `@abstractmethod` 定义接口时必须有实现类

### 检测方法
```bash
# 查找空pass语句
grep -r "pass\s*$" --include="*.py" src/
# 查找NotImplementedError
grep -r "NotImplementedError" --include="*.py" src/
```

---

## 2. 重复实现问题 (Duplicate Implementation Anti-Pattern)

### 问题描述
同一功能在多处实现，使用不同技术（如tree-sitter vs 正则），导致行为不一致和维护困难。

### 错误示例
```python
# 文件1: languages/typescript_parser.py - 使用tree-sitter
class TypeScriptParser:
    def parse(self, content, file_path):
        # 使用tree-sitter解析
        ...

# 文件2: features/multilang_support.py - 使用正则
class TypeScriptParser:  # 同名类！
    def parse(self, content, file_path):
        # 使用简单正则匹配
        func_match = re.search(r'function\s+(\w+)', line)
        ...
```

### 正确做法
- 每个功能只有一个权威实现
- 使用依赖注入而非重复实现
- 如需简化版本，应复用核心实现而非重写

### 检测方法
```bash
# 查找同名类
grep -r "class TypeScriptParser" --include="*.py" src/
```

---

## 3. 文件过大问题 (Large File Anti-Pattern)

### 问题描述
单个文件超过300行限制，违反项目约定的模块化原则。

### 项目规定
- **硬性限制**: 300行
- **目标**: 100-200行
- **超限处理**: 拆分为多个模块

### 错误示例
```
features/instant_understanding.py - 936行 (超限3倍!)
```

### 正确做法
- 按职责拆分：dataclasses、engine、helpers、output
- 使用子包组织相关模块
- 每个文件单一职责

### 检测方法
```bash
# 查找超过300行的Python文件
find . -name "*.py" -exec wc -l {} \; | awk '$1 > 300'
```

---

## 4. 文档与代码不同步 (Documentation Drift Anti-Pattern)

### 问题描述
README中的声明与实际代码不符，误导使用者。

### 错误示例
```markdown
# README.md 声称:
- 38 tests passing    # 实际: 1300+ tests
- 86% code coverage   # 实际: 90%
- 17 language support # 实际: 只实现了4种
```

### 正确做法
- README中的数据应动态生成或定期更新
- 未实现的功能标注为"计划中"
- 使用CI/CD自动更新覆盖率徽章

### 检测方法
```bash
# 实际测试数量
pytest --collect-only | grep "test session starts" -A 1
# 实际覆盖率
pytest --cov=src --cov-report=term | grep TOTAL
```

---

## 5. 测试覆盖率虚高 (False Coverage Anti-Pattern)

### 问题描述
测试只验证stub代码会抛出NotImplementedError，不是真正的功能测试。

### 错误示例
```python
# BAD: 假测试 - 只验证stub行为
def test_execute_not_implemented(self):
    scanner = SecurityScanner()
    with pytest.raises(NotImplementedError):
        scanner.execute()  # 这不是真正的测试!
```

### 正确做法
- 测试应验证实际功能行为
- 如果功能未实现，不要写测试
- 覆盖率应反映真实的功能测试

---

## 6. 一致性问题 (Inconsistency Anti-Pattern)

### 问题描述
项目中使用多种不同的方式处理同类问题。

### 错误示例
```python
# 错误处理不一致
def func1():
    return {"success": False, "error": "message"}  # 返回dict

def func2():
    raise ValueError("message")  # 抛出异常

# 语言不一致
class SecurityScanner:
    """安全扫描器"""  # 中文docstring
    
class Parser:
    """Parser for source code."""  # 英文docstring
```

### 正确做法
- 统一错误处理方式（选择一种并坚持）
- 统一文档语言（推荐英文）
- 建立并遵循编码规范

---

## 错误模式检查清单 (Pre-Commit Checklist)

在提交代码前，检查以下内容：

- [ ] 没有空的 `pass` 语句
- [ ] 没有 `NotImplementedError`（除非是抽象方法）
- [ ] 没有重复的类名
- [ ] 所有文件 < 300 行
- [ ] README与实际代码一致
- [ ] 新测试验证真实功能（非stub）
- [ ] 错误处理方式一致
- [ ] 文档语言一致

---

## 更新记录

| 日期 | 添加者 | 内容 |
|------|--------|------|
| 2026-02-06 | Claude | 初始版本，记录6种常见错误模式 |
