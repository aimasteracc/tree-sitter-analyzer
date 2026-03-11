# 规格说明：output_manager.py 死代码清理

## 问题描述

`tree_sitter_analyzer/output_manager.py` 中存在三个**确认的死代码**模块级函数，
无任何外部引用（经全代码库 grep 验证）：

| 函数 | 定义位置 | 外部引用数 |
|------|----------|-----------|
| `output_success` | output_manager.py | 0 |
| `output_languages` | output_manager.py | 0 |
| `output_queries` | output_manager.py | 0 |

这三个函数是对 `OutputManager` 实例方法的无用包装，
从未被任何 CLI、MCP 工具或测试调用。

## 修复方案

从 `tree_sitter_analyzer/output_manager.py` 删除：
- `def output_success(...)`
- `def output_languages(...)`
- `def output_queries(...)`

## 验收标准

| ID | 条件 | 期望结果 |
|----|------|----------|
| AC-OM-001 | `from tree_sitter_analyzer.output_manager import output_success` | 抛 `ImportError` |
| AC-OM-002 | `from tree_sitter_analyzer.output_manager import output_languages` | 抛 `ImportError` |
| AC-OM-003 | `from tree_sitter_analyzer.output_manager import output_queries` | 抛 `ImportError` |
| AC-OM-004 | `output_manager` 模块正常 import | 成功，不受影响 |
| AC-OM-005 | 全量测试 `uv run pytest -q` | 全绿（无测试依赖这 3 个函数） |

## 范围外（不做）

- `OutputManager` 类本身的方法重构（风险高，单独立项）
- `output_info`、`output_warning`、`output_error` 等其他模块级函数（仍有使用，不删除）
