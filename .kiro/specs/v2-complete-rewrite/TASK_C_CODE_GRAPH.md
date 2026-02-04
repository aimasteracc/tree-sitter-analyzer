# Task C: Code Graph 查询增强

**Status**: In Progress
**Priority**: High (本周必做)
**Estimated**: 4h
**Pain Point**: #14

## Problem Statement

当前 Code Graph 功能基础，缺少高级查询能力：
- 无法快速查询某个类的所有方法
- 无法查找函数的调用者（反向查询）
- 无法追踪调用链路径
- 无法灵活过滤和聚焦节点

**用户痛点**：
```python
# 当前：需要手动遍历整个图
graph = build_code_graph("project/")
# ❌ 很难找到 "UserService.login" 被谁调用了
# ❌ 很难找到 A -> B -> C 的调用路径
```

## Goals

实现 5 个高级查询 API：

1. **query_methods(class_name)**: 查询类的所有方法
2. **find_callers(target)**: 查找调用者（反向依赖）
3. **find_call_chain(from, to)**: 查找调用链路径
4. **filter(types, pattern)**: 过滤节点
5. **focus(node_id, depth)**: 聚焦子图

## Design

### Option A: 扩展现有 CodeGraph 类（推荐）
```python
# 在 graph/queries.py 中实现
class CodeGraphQueries:
    """High-level query APIs for code graphs."""

    def __init__(self, graph: CodeGraph):
        self.graph = graph

    def query_methods(self, class_name: str) -> list[dict]:
        """Query all methods of a class."""

    def find_callers(self, target: str) -> list[dict]:
        """Find all callers of a function/method."""

    def find_call_chain(self, from_node: str, to_node: str) -> list[list[str]]:
        """Find call paths from one node to another."""

    def filter(self, node_types: list[str], file_pattern: str = None) -> dict:
        """Filter graph by node types and file pattern."""

    def focus(self, node_id: str, depth: int = 1) -> dict:
        """Extract subgraph focused on a node."""
```

### Option B: 独立查询模块
在 `graph/advanced_queries.py` 中实现，但这会增加模块复杂度。

**选择**: Option A - 扩展 `graph/queries.py`

## Implementation Plan

### Step 0: 分析现有代码
- [x] 了解 graph/builder.py 的结构
- [x] 了解 graph/queries.py 当前实现
- [x] 了解节点和边的数据结构

### Step 1: 编写测试 (TDD - RED)
- [ ] 创建 tests/unit/test_code_graph_queries.py
- [ ] 编写 query_methods() 测试（5个测试用例）
- [ ] 编写 find_callers() 测试（5个测试用例）
- [ ] 编写 find_call_chain() 测试（3个测试用例）
- [ ] 编写 filter() 测试（3个测试用例）
- [ ] 编写 focus() 测试（3个测试用例）
- [ ] 运行测试 - 应该全部失败 ❌

### Step 2: 实现功能 (TDD - GREEN)
- [ ] 实现 query_methods()
- [ ] 实现 find_callers()
- [ ] 实现 find_call_chain()（使用 BFS/DFS）
- [ ] 实现 filter()
- [ ] 实现 focus()
- [ ] 运行测试 - 应该全部通过 ✅

### Step 3: 集成和优化 (TDD - REFACTOR)
- [ ] 添加性能优化（缓存、索引）
- [ ] 添加错误处理
- [ ] 更新文档字符串
- [ ] 检查覆盖率（目标 >80%）

### Step 4: 集成测试
- [ ] 创建 tests/integration/test_graph_queries.py
- [ ] 测试真实项目的查询
- [ ] 验证性能（大型项目）

### Step 5: 提交
- [ ] 更新 PAINPOINTS_TRACKER.md
- [ ] 提交代码
- [ ] 推送到远程

## Files to Create/Modify

**修改**:
1. `v2/tree_sitter_analyzer_v2/graph/queries.py` - 添加新方法

**创建**:
1. `v2/tests/unit/test_code_graph_queries.py` - 单元测试
2. `v2/tests/integration/test_graph_queries.py` - 集成测试（可选）

## API 设计详细说明

### 1. query_methods(class_name: str)
```python
def query_methods(self, class_name: str) -> list[dict]:
    """
    Query all methods of a class.

    Args:
        class_name: Full class name (e.g., "UserService")

    Returns:
        List of method dicts with keys: name, visibility, parameters, return_type

    Example:
        >>> queries.query_methods("Calculator")
        [
            {"name": "add", "visibility": "public", "parameters": ["a", "b"]},
            {"name": "subtract", "visibility": "public", "parameters": ["a", "b"]}
        ]
    """
```

### 2. find_callers(target: str)
```python
def find_callers(self, target: str) -> list[dict]:
    """
    Find all callers of a function/method.

    Args:
        target: Function/method name (e.g., "UserService.login")

    Returns:
        List of caller dicts with keys: caller, location, call_type

    Example:
        >>> queries.find_callers("UserService.login")
        [
            {"caller": "AuthController.authenticate", "location": "auth.py:45"},
            {"caller": "LoginView.post", "location": "views.py:123"}
        ]
    """
```

### 3. find_call_chain(from_node: str, to_node: str)
```python
def find_call_chain(self, from_node: str, to_node: str, max_depth: int = 5) -> list[list[str]]:
    """
    Find call chain paths between two nodes.

    Args:
        from_node: Starting node
        to_node: Target node
        max_depth: Maximum search depth (default 5)

    Returns:
        List of paths (each path is a list of node names)

    Example:
        >>> queries.find_call_chain("main", "save_user")
        [
            ["main", "process_request", "save_user"],
            ["main", "handle_user", "save_user"]
        ]
    """
```

### 4. filter(node_types: list[str], file_pattern: str = None)
```python
def filter(self, node_types: list[str] = None, file_pattern: str = None) -> dict:
    """
    Filter graph by node types and file pattern.

    Args:
        node_types: List of node types (e.g., ["class", "function"])
        file_pattern: File glob pattern (e.g., "src/**/*.py")

    Returns:
        Filtered graph dict

    Example:
        >>> queries.filter(node_types=["function"], file_pattern="src/core/*.py")
        {"nodes": [...], "edges": [...]}
    """
```

### 5. focus(node_id: str, depth: int = 1)
```python
def focus(self, node_id: str, depth: int = 1) -> dict:
    """
    Extract subgraph focused on a node and its neighbors.

    Args:
        node_id: Central node ID
        depth: Distance from central node (default 1)

    Returns:
        Subgraph dict with nodes within depth

    Example:
        >>> queries.focus("Calculator.add", depth=1)
        {
            "nodes": ["Calculator.add", "Calculator.subtract", "main"],
            "edges": [...]
        }
    """
```

## Acceptance Criteria

- [ ] 所有 5 个 API 实现完成
- [ ] 至少 19 个单元测试通过（每个 API 至少 3 个测试）
- [ ] 代码覆盖率 >80%
- [ ] 所有现有测试仍然通过
- [ ] 性能：1000 节点图查询 <100ms
- [ ] 文档字符串完整
- [ ] 类型注解完整

## Progress Log

### [2026-02-03 18:30] 开始 Task C
- 创建规划文档
- 准备分析现有代码结构

### [2026-02-03 18:35] 分析现有代码
- ✅ 分析了 graph/queries.py
- ✅ 分析了 graph/builder.py
- ✅ 了解了图的数据结构

**发现**：部分功能已实现！
- ✅ get_callers() - 已存在（对应 find_callers）
- ✅ get_call_chain() - 已存在（对应 find_call_chain）
- ✅ find_definition() - 已存在

**需要新增的功能**（修正后）：
1. query_methods(class_name) - 查询类的所有方法
2. filter_nodes(node_types, file_pattern) - 过滤节点
3. focus_subgraph(node_id, depth) - 聚焦子图

**节点数据结构**：
- MODULE: type, name, file_path, mtime, imports
- CLASS: type, name, module_id, start_line, end_line, methods (list of method names)
- FUNCTION: type, name, class_id, module_id, start_line, end_line, parameters

**边类型**：
- CONTAINS: 包含关系（Module→Class, Module→Function, Class→Method）
- CALLS: 调用关系

### [2026-02-03 18:45] TDD RED 阶段
- ✅ 添加了 11 个新测试到 test_code_graph_queries.py
  - TestQueryMethods: 4 个测试
  - TestFilterNodes: 3 个测试
  - TestFocusSubgraph: 4 个测试
- ✅ 运行测试确认失败（ImportError - 函数不存在）

### [2026-02-03 18:50] TDD GREEN 阶段
- ✅ 实现了 query_methods() - 67 行代码
- ✅ 实现了 filter_nodes() - 67 行代码
- ✅ 实现了 focus_subgraph() - 42 行代码
- ✅ 所有 11 个测试通过！
  - TestQueryMethods: 4/4 ✅
  - TestFilterNodes: 3/3 ✅
  - TestFocusSubgraph: 4/4 ✅

### [2026-02-03 18:55] 验证覆盖率
- 正在检查覆盖率...
