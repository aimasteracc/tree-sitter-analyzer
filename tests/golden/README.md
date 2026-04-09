# Golden Corpus Files

## 概述

Golden corpus 文件是 Grammar Coverage MECE 项目的一部分，用于验证 tree-sitter 解析器对各语言的 node types 覆盖度。

每个语言有两个文件：
1. `corpus_<language>.py` - 包含所有关键语法节点的示例代码
2. `corpus_<language>_expected.json` - 预期的解析结果（node type 统计）

## 文件结构

### Corpus 文件 (corpus_*.py/js/go/etc.)

- 必须是**可执行的合法代码**（语法正确）
- 必须覆盖该语言的**所有关键 node types**
- 代码注释使用汉语，但 log/变量名用英文
- 遵守项目的 Ruff/MyPy 规范（可使用 `# ruff: noqa` 忽略必要的警告）

### Expected JSON (corpus_*_expected.json)

```json
{
  "language": "python",
  "description": "语言描述",
  "corpus_file": "corpus_python.py",
  "node_types": {
    "function_definition": 69,
    "class_definition": 13,
    ...
  },
  "statistics": {
    "total_named_nodes": 2716,
    "unique_node_types": 74
  },
  "critical_node_types": {
    "function_definition": 69,
    "class_definition": 13,
    "decorated_definition": 20,
    ...
  },
  "notes": [
    "说明文字"
  ]
}
```

## Python Corpus 特性

`corpus_python.py` 覆盖以下关键 node types：

### 函数类型 (69 个)
- Regular functions
- Async functions
- Nested functions
- Class methods (`__init__`, `__post_init__`)
- Generators (with `yield`)
- Async generators

### 类类型 (13 个)
- Regular classes
- Abstract base classes (ABC)
- Nested classes
- Data classes (`@dataclass`)

### 装饰器 (20 个 decorated_definition)
- **关键**: 这是 Issue #112 的 regression test
- 函数装饰器 (`@simple_decorator`)
- 类装饰器 (`@dataclass`)
- 参数化装饰器
- 多重装饰器

### 方法类型
- `@staticmethod` (静态方法)
- `@classmethod` (类方法)
- `@property` (属性装饰器)

### Lambda 和推导式 (8 + 9)
- Lambda 表达式
- List comprehension
- Dict comprehension
- Set comprehension
- Generator expression

## 验证工具

### validate_corpus.py

验证 corpus 文件是否与 expected.json 匹配。

```bash
# 在 tests/golden 目录运行
uv run python validate_corpus.py
```

输出示例：
```
PASS: Validation PASSED for corpus_python.py
   Total node types: 74
   Total named nodes: 2716

   Critical node types:
   OK function_definition            69
   OK class_definition               13
   OK decorated_definition           20
   ...
```

## 添加新语言

1. 创建 `corpus_<language>.<ext>` 文件
   - 覆盖该语言的所有关键 node types
   - 确保代码可执行

2. 使用 tree-sitter 解析并生成 expected.json
   ```python
   from tree_sitter import Language, Parser
   import tree_sitter_<language>

   # 解析 corpus 文件并统计 node types
   # 生成 expected.json
   ```

3. 更新 `validate_corpus.py` 支持新语言

4. 在 `corpus_<language>.<ext>` 头部注释中列出覆盖的 node types

## CI/CD 集成

Golden corpus 文件将在 CI 中自动验证：
- 语法检查 (Ruff/ESLint/etc.)
- 解析验证 (tree-sitter parser)
- 覆盖度检查 (与 expected.json 对比)

## 注意事项

1. **immutable 原则**: corpus 文件应该展示最佳实践，但语法覆盖度优先于编码规范
2. **Windows 编码**: 避免在 print/log 中使用中文字符（会导致 Windows 控制台 UnicodeEncodeError）
3. **Issue #112**: `decorated_definition` 是关键 - 必须包含足够的装饰器示例
4. **Ruff 警告**: Lambda 表达式等会触发 Ruff 警告，这是预期的（使用 `# ruff: noqa` 忽略）

## 相关文档

- [docs/grammar-coverage-mece.md](../../docs/grammar-coverage-mece.md) - Grammar Coverage MECE 项目计划
- [docs/ai-coding-rules.md](../../docs/ai-coding-rules.md) - AI 编码规范
