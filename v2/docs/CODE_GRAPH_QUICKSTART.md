# Code Graph - 5 分钟快速上手

## 最常用的 3 个命令

### 1️⃣ 快速浏览文件结构

```bash
uv run python scripts/analyze_code_graph.py <file.py>
```

**示例**:
```bash
uv run python scripts/analyze_code_graph.py tree_sitter_analyzer_v2/graph/builder.py
```

**输出**:
```
MODULES: 1
CLASSES: 1
FUNCTIONS: 3

MODULE: builder
  CLASS: CodeGraphBuilder
    FUNC: build_from_file
      CALLS: _extract_module_node, ...
```

---

### 2️⃣ 查找函数调用者

```bash
uv run python scripts/analyze_code_graph.py <file.py> --find-callers <函数名>
```

**示例**:
```bash
uv run python scripts/analyze_code_graph.py tree_sitter_analyzer_v2/graph/builder.py --find-callers build_from_file
```

**用途**: 重构前检查影响范围

---

### 3️⃣ 分析整个目录

```bash
uv run python scripts/analyze_code_graph.py <directory> --all
```

**示例**:
```bash
uv run python scripts/analyze_code_graph.py tree_sitter_analyzer_v2/graph --all
```

**输出**: 整个模块的结构概览

---

## Python API (最简单)

```python
from tree_sitter_analyzer_v2.graph import CodeGraphBuilder, export_for_llm

# 一行构建
builder = CodeGraphBuilder()
graph = builder.build_from_file('your_file.py')

# 一行导出
print(export_for_llm(graph))
```

---

## 实际使用场景

### 场景 1: 理解陌生代码

```bash
# 快速浏览整个模块
uv run python scripts/analyze_code_graph.py src/new_module --all
```

### 场景 2: 重构安全检查

```bash
# 找出谁在用这个函数
uv run python scripts/analyze_code_graph.py src/utils.py --find-callers old_function
```

### 场景 3: 为 Claude 准备上下文

```bash
# 生成 token 优化的概览
uv run python scripts/analyze_code_graph.py src --all > overview.txt
# 将 overview.txt 发给 Claude
```

---

## 高级选项

```bash
# 详细模式（包含参数和返回类型）
--detailed

# 包含私有函数
--include-private
```

---

## 完整文档

👉 查看 [CODE_GRAPH_USAGE.md](./CODE_GRAPH_USAGE.md) 了解所有功能

---

**最后更新**: 2026-02-01
