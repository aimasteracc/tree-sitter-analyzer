# Design - Fix Known Issues and Legacy Problems

## 技术选型 (Technology Choices)
- **Sorting**: 使用 Python 内置的 `sorted()` 函数配合 `os.path.getmtime` 或 `os.path.getsize` 等。
- **Query Processing**: 深入分析 `tree-sitter` 的 query API，优化 `UnifiedAnalysisEngine` 和 `QueryEngine` 的交互。

## 架构设计 (Architecture Design)

### 1. `list_files` 排序实现
在 `list_files_tool.py` 中，根据传入的 `sort` 参数（如 `name`, `modified`, `size`），在返回结果前对文件列表进行排序。

### 2. 查询引擎修复
- 检查 `ElementExtractor` 是否正确提取了字段信息。
- 检查 `Filter` 类在 `query.py` 中的应用逻辑。

## 边界情况处理 (Edge Cases)
- `sort` 参数为空或无效时的默认行为。
- `fields` 匹配不到任何结果时的处理。
- 过滤器正则表达式导致的性能问题或匹配错误。
