# 规格说明：Intelligence Graph 多语言索引支持

## 问题描述

`ProjectIndexer` 当前只扫描 `.py` 文件，手动走读 Python AST 节点，
与各语言插件（`java_plugin`、`cpp_plugin` 等）的功能重叠。

### 现有可用资源

| 资源 | 状态 |
|------|------|
| `SymbolIndex` 数据模型 | ✅ 语言无关，直接可用 |
| `SymbolDefinition`、`SymbolReference` | ✅ 语言无关，直接可用 |
| `LanguageDetector` | ✅ 可从文件扩展名识别语言 |
| `PluginManager` | ✅ 按语言名称获取插件 |
| 各语言插件 | ✅ 返回标准化 Class/Function 对象 |

### 正确设计

```
_index_single_file(java_file)
  → LanguageDetector.detect_language() → "java"
  → PluginManager.get_plugin("java") → JavaPlugin
  → plugin.create_extractor()
  → extractor.extract_classes(tree, source) → [Class, ...]
  → extractor.extract_functions(tree, source) → [Function, ...]
  → 转换为 SymbolDefinition，加入 SymbolIndex
```

## 修复方案

### 改动点

#### 1. `project_indexer.py`

- `_discover_python_files()` → 新增 `_discover_files(extensions)` 方法，
  接受文件扩展名集合（默认 `.py`，扩展后加入 `.java`、`.cpp`、`.h`、`.hpp` 等）
- `_index_single_file()` 增加分支：
  - Python 文件：保持现有逻辑（已有完善的导入解析）
  - 非 Python 文件：调用 `_index_file_via_plugin()` 新方法

#### 2. 新方法 `_index_file_via_plugin()`

```python
def _index_file_via_plugin(
    self, file_path: str, rel_path: str, language: str, source_code: str
) -> None:
    """通过语言插件提取符号，写入 SymbolIndex。"""
    plugin = self._plugin_manager.get_plugin(language)
    if plugin is None:
        return

    parser = self._get_language_parser(language)
    if parser is None:
        return

    tree = parser.parse(source_code.encode("utf-8"))
    extractor = plugin.create_extractor()

    # 提取类
    for cls in extractor.extract_classes(tree, source_code):
        self._symbol_index.add_definition(SymbolDefinition(
            name=cls.name,
            file_path=rel_path,
            line=cls.start_line,
            end_line=cls.end_line,
            symbol_type="class",
            modifiers=cls.modifiers or [],
            docstring=cls.docstring,
        ))

    # 提取函数/方法
    for func in extractor.extract_functions(tree, source_code):
        self._symbol_index.add_definition(SymbolDefinition(
            name=func.name,
            file_path=rel_path,
            line=func.start_line,
            end_line=func.end_line,
            symbol_type="method" if func.is_method else "function",
            parameters=func.parameters or [],
            return_type=func.return_type,
            modifiers=func.modifiers or [],
            docstring=func.docstring,
        ))
```

#### 3. 新方法 `_get_language_parser()`

按语言名称动态导入对应的 `tree_sitter_xxx` 包，
创建并缓存解析器实例（避免重复创建）。

支持的语言：`python`（已有）、`java`、`cpp`

### 不修改

- Python 文件的导入解析（`PythonImportResolver`）保持不变
- `CallGraphBuilder` 保持 Python-only（非 Python 调用图超出本次范围）
- `SymbolIndex`、`DependencyGraphBuilder` 无需改动

---

## 验收标准

| ID | 条件 | 期望结果 |
|----|------|----------|
| AC-ML-001 | 对含 `.java` 文件的目录运行 `ensure_indexed()` | Java 类出现在 `symbol_index.lookup_definition()` 中 |
| AC-ML-002 | Java 文件中的方法 | 方法出现在 `symbol_index.lookup_definition()` 中，symbol_type="method" 或 "function" |
| AC-ML-003 | 对含 `.cpp` 文件的目录运行 `ensure_indexed()` | C++ 类出现在 `symbol_index` 中 |
| AC-ML-004 | Python 文件索引行为 | 与修改前完全一致（回归） |
| AC-ML-005 | Python + Java 混合项目 | 两种语言文件均被正确索引 |
| AC-ML-006 | `tree_sitter_java` 未安装时 | 不崩溃，仅跳过 Java 文件 |

## 范围外（不做）

- Java 导入解析（`JavaImportResolver`）
- C++ 符号调用图
- Kotlin、Go 等其他语言（架构相同，单独按需添加）
