# Grammar Coverage Validator

Grammar Coverage Validator 用于验证 tree-sitter 语言插件对语法节点的覆盖度，确保插件能够提取所有可能的节点类型（MECE 原则：互斥且完全穷尽）。

## 概述

Grammar Coverage MECE 项目旨在确保 tree-sitter-analyzer 的 17 个语言插件能够 100% 覆盖所有语法节点类型。Validator 模块通过以下方式验证覆盖度：

1. 解析 golden corpus 文件（使用 tree-sitter 直接解析）
2. 提取所有 named node types 作为"全集"
3. 运行插件提取，收集被提取的 node types
4. 计算覆盖率：`covered_types / total_types * 100%`
5. 列出未覆盖的 node types

## 核心功能

### 1. `validate_plugin_coverage(language: str) -> CoverageReport`

验证指定语言插件的 grammar coverage。

**示例：**
```python
from tree_sitter_analyzer.grammar_coverage import validate_plugin_coverage_sync

report = validate_plugin_coverage_sync("python")
print(f"Coverage: {report.coverage_percentage:.1f}%")
print(f"Uncovered types: {report.uncovered_types}")
```

### 2. `generate_coverage_report(report: CoverageReport) -> str`

生成人类可读的覆盖度报告。

**输出格式：**
```
Python: 95.7% (44/46 node types covered)

Uncovered node types (2):
- async_for_statement
- match_statement

Corpus file: /path/to/corpus_python.py
```

### 3. `check_coverage_threshold(coverage_pct: float, threshold: float = 100.0) -> bool`

检查覆盖率是否达到阈值（用于 CI 集成）。

**示例：**
```python
from tree_sitter_analyzer.grammar_coverage import (
    check_coverage_threshold,
    validate_plugin_coverage_sync,
)

report = validate_plugin_coverage_sync("javascript")
if not check_coverage_threshold(report.coverage_percentage):
    print(f"Coverage below 100%: {report.coverage_percentage:.1f}%")
    exit(1)
```

## 数据结构

### `CoverageReport`

```python
@dataclass
class CoverageReport:
    language: str                          # 语言名称（如 "python"）
    total_node_types: int                  # 语法中的总节点类型数
    covered_node_types: int                # 插件覆盖的节点类型数
    coverage_percentage: float             # 覆盖率百分比（0-100）
    uncovered_types: list[str]             # 未覆盖的节点类型列表
    corpus_file: str                       # 使用的 corpus 文件路径
    expected_node_types: dict[str, int]    # 预期的节点类型及其计数
    actual_node_types: dict[str, int]      # 实际解析到的节点类型及其计数
```

## CI 集成

### GitHub Actions 示例

```yaml
- name: Check Grammar Coverage
  run: |
    uv run python -c "
    from tree_sitter_analyzer.grammar_coverage import (
        validate_plugin_coverage_sync,
        check_coverage_threshold,
    )

    languages = ['python', 'javascript', 'go']
    failed = []

    for lang in languages:
        report = validate_plugin_coverage_sync(lang)
        if not check_coverage_threshold(report.coverage_percentage):
            failed.append((lang, report.coverage_percentage))

    if failed:
        for lang, pct in failed:
            print(f'FAIL: {lang} - {pct:.1f}%')
        exit(1)
    "
```

### 本地 CI 检查脚本

```bash
#!/bin/bash
# check_grammar_coverage.sh

set -e

echo "Checking grammar coverage for all languages..."

uv run python -m tree_sitter_analyzer.grammar_coverage.example_usage

if [ $? -eq 0 ]; then
    echo "✓ All languages meet 100% coverage threshold"
    exit 0
else
    echo "✗ Some languages are below 100% coverage threshold"
    exit 1
fi
```

## 使用示例

### 命令行使用

```bash
# 运行示例脚本
python -m tree_sitter_analyzer.grammar_coverage.example_usage
```

### Python API 使用

```python
from tree_sitter_analyzer.grammar_coverage import (
    validate_plugin_coverage_sync,
    generate_coverage_report,
    check_coverage_threshold,
)

# 验证 Python 插件
report = validate_plugin_coverage_sync("python")

# 打印报告
print(generate_coverage_report(report))

# CI 检查
if not check_coverage_threshold(report.coverage_percentage, threshold=100.0):
    print(f"ERROR: Python plugin coverage below 100%")
    exit(1)
```

## 设计决策

### 1. 100% 覆盖阈值（无例外）

所有语言插件必须达到 100% 覆盖率，无例外。这确保了：
- 没有遗漏的语法节点
- 完整的代码分析能力
- 一致的跨语言体验

### 2. 使用 Golden Corpus 而非 Grammar 定义

我们使用 golden corpus 文件而不是解析 grammar.json，因为：
- Golden corpus 是真实的、可执行的代码
- 避免复杂的 grammar.json 解析逻辑
- Corpus 文件更易于维护和验证

### 3. 异步 API

`validate_plugin_coverage` 是异步函数，与 `analyze_file` 保持一致。同步包装器 `validate_plugin_coverage_sync` 用于测试和 CLI。

## 依赖关系

### Phase 1.1 (当前)
- ✓ 解析 golden corpus 文件
- ✓ 提取所有 node types（全集）
- ✓ 生成覆盖度报告
- ✓ CI 阈值检查

### Phase 1.2 (待实现)
- ⏳ Grammar introspection 系统集成
- ⏳ 插件覆盖度检测（`_get_covered_node_types_from_plugin`）
- ⏳ 实时覆盖率计算

当前 `_get_covered_node_types_from_plugin` 返回空集，等待 Phase 1.2 grammar introspection 系统就绪后实现。

## 测试

```bash
# 运行所有 validator 测试
uv run pytest tests/unit/grammar_coverage/test_validator.py -v

# 检查代码风格
uv run ruff check tree_sitter_analyzer/grammar_coverage/validator.py

# 检查类型
uv run mypy tree_sitter_analyzer/grammar_coverage/validator.py --strict
```

测试覆盖率：98.11% (26 tests passed)

## 相关文档

- [Golden Corpus README](../../../tests/golden/README.md) - Golden corpus 文件规范
- [Grammar Coverage MECE](../../../docs/grammar-coverage-mece.md) - 项目总体计划
- [AI Coding Rules](../../../docs/ai-coding-rules.md) - CI 质量检查规则

## 贡献指南

添加新语言支持：

1. 在 `_get_tree_sitter_module` 中添加语言模块映射
2. 在 `_get_language_extension` 中添加文件扩展名映射
3. 创建 `corpus_<language>.<ext>` 文件（参考 [Golden Corpus README](../../../tests/golden/README.md)）
4. 创建 `corpus_<language>_expected.json` 文件
5. 运行验证：`validate_plugin_coverage_sync("<language>")`

## License

See project root LICENSE file.
