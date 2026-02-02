# V2 日常使用行动计划 - 让它成为最喜爱的工具

## 🎯 核心目标

**让 tree-sitter-analyzer v2 成为我们日常开发中不可或缺的工具**

通过实际使用驱动开发，而不是盲目补全功能。每次使用 v2 都是在验证其实用性，发现改进点，并逐步完善。

---

## 📋 立即可用的 V2 功能

### 1. Java 项目分析 (✅ 生产就绪)
```bash
# 场景：分析 Java 代码结构
cd v2
uv run python -m tree_sitter_analyzer_v2.cli.main analyze ../examples/BigService.java --format markdown

# 场景：构建 Java 项目调用图
uv run python -c "
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
builder = CodeGraphBuilder(language='java')
graph = builder.build_from_directory('tests/fixtures/java_project/src/main/java', pattern='**/*.java', cross_file=True)
print(f'Nodes: {graph.number_of_nodes()}, Edges: {graph.number_of_edges()}')
"
```

**实用价值**:
- ✅ 理解大型 Java 类的结构
- ✅ 追踪跨文件方法调用
- ✅ 分析代码依赖关系

### 2. Python 项目分析 (✅ 完全支持)
```bash
# 场景：分析 Python 模块
uv run python -m tree_sitter_analyzer_v2.cli.main analyze tree_sitter_analyzer_v2/core/parser.py --format markdown

# 场景：构建 Python 项目调用图
uv run python -c "
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
builder = CodeGraphBuilder(language='python')
graph = builder.build_from_directory('tree_sitter_analyzer_v2', pattern='**/*.py', cross_file=True)
print(f'Nodes: {graph.number_of_nodes()}, Edges: {graph.number_of_edges()}')
"
```

**实用价值**:
- ✅ 理解 v2 自身的代码结构
- ✅ 重构时分析影响范围
- ✅ 学习新 Python 项目

### 3. TypeScript 项目分析 (✅ 完全支持)
```bash
# 场景：分析 TypeScript 文件
uv run python -m tree_sitter_analyzer_v2.cli.main analyze ../examples/sample.ts --format markdown

# 场景：构建 TypeScript 项目调用图
uv run python -c "
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
builder = CodeGraphBuilder(language='typescript')
graph = builder.build_from_directory('path/to/ts/project', pattern='**/*.ts', cross_file=True)
print(f'Nodes: {graph.number_of_nodes()}, Edges: {graph.number_of_edges()}')
"
```

**实用价值**:
- ✅ 分析前端 TypeScript 代码
- ✅ 理解 React/Vue/Angular 组件结构
- ✅ 追踪 API 调用链

### 4. MCP 集成 (✅ 生产就绪)
```bash
# 场景：通过 Claude Desktop 使用
# 配置文件：%APPDATA%\Claude\claude_desktop_config.json
{
  "mcpServers": {
    "tree-sitter-analyzer-v2": {
      "command": "python",
      "args": ["-m", "tree_sitter_analyzer_v2.mcp.server"],
      "env": {
        "PYTHONPATH": "C:\\git-private\\tree-sitter-analyzer\\v2"
      }
    }
  }
}
```

**实用价值**:
- ✅ 在 Claude Code 中直接分析代码
- ✅ AI 辅助代码审查
- ✅ 自动化代码理解

---

## 🚀 每日使用计划

### Morning Routine (早晨启动)

#### 1. 使用 V2 分析今天要修改的代码
```bash
# 示例：今天要重构 symbols.py
cd v2
uv run python -m tree_sitter_analyzer_v2.cli.main analyze tree_sitter_analyzer_v2/graph/symbols.py --format markdown > /tmp/symbols_analysis.md

# 查看分析结果
cat /tmp/symbols_analysis.md
```

**收益**: 在修改前理解代码结构，避免破坏性修改

#### 2. 构建相关文件的调用图
```bash
# 构建 graph 模块的调用图
uv run python -c "
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
from tree_sitter_analyzer_v2.graph.export import export_to_mermaid

builder = CodeGraphBuilder(language='python')
graph = builder.build_from_directory('tree_sitter_analyzer_v2/graph', pattern='**/*.py', cross_file=True)

# 导出为 Mermaid
mermaid_code = export_to_mermaid(graph, max_nodes=50)
print(mermaid_code)
" > /tmp/graph_module_diagram.mmd
```

**收益**: 可视化理解模块间依赖，发现潜在问题

### During Development (开发中)

#### 3. 快速查找方法调用
```bash
# 场景：想知道 lookup_qualified 方法被哪些地方调用
uv run python -c "
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder

builder = CodeGraphBuilder(language='python')
graph = builder.build_from_directory('tree_sitter_analyzer_v2', pattern='**/*.py', cross_file=True)

# 查找所有调用 lookup_qualified 的地方
for source, target, data in graph.edges(data=True):
    if data.get('type') == 'CALLS':
        target_node = graph.nodes.get(target, {})
        if target_node.get('name') == 'lookup_qualified':
            source_node = graph.nodes[source]
            print(f'{source_node.get(\"name\")} -> lookup_qualified')
"
```

**收益**: 重构时快速评估影响范围

#### 4. 提取代码片段 (通过 Python API)
```python
# 场景：只需要查看某个方法的实现
from tree_sitter_analyzer_v2.api.interface import extract_code_section

result = extract_code_section(
    file_path="tree_sitter_analyzer_v2/graph/symbols.py",
    start_line=212,
    end_line=289,
    output_format="markdown"
)
print(result)
```

**收益**: 专注于特定代码段，避免信息过载

### Code Review (代码审查)

#### 5. 分析 PR 中的变更
```bash
# 场景：审查别人的 PR，快速理解改动的文件
git diff main --name-only | grep "\.py$" | while read file; do
    echo "=== $file ==="
    uv run python -m tree_sitter_analyzer_v2.cli.main analyze "$file" --format markdown | head -50
done
```

**收益**: 快速了解 PR 改动的代码结构

#### 6. 检查跨文件影响
```bash
# 场景：PR 修改了 symbols.py，想知道影响了哪些文件
uv run python -c "
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
import networkx as nx

builder = CodeGraphBuilder(language='python')
graph = builder.build_from_directory('tree_sitter_analyzer_v2', pattern='**/*.py', cross_file=True)

# 找出所有依赖 symbols.py 的文件
symbols_nodes = [n for n, d in graph.nodes(data=True) if d.get('file_path') == 'symbols.py']
affected_files = set()
for node in symbols_nodes:
    # 找出所有调用这个节点的地方
    for source in graph.predecessors(node):
        source_file = graph.nodes[source].get('file_path')
        if source_file != 'symbols.py':
            affected_files.add(source_file)

print('Affected files:')
for f in sorted(affected_files):
    print(f'  - {f}')
"
```

**收益**: 确保修改不会破坏其他模块

### Evening Review (晚间回顾)

#### 7. 分析今天的改动
```bash
# 场景：回顾今天修改了哪些代码
git diff HEAD~1 --name-only | grep "\.py$" | while read file; do
    echo "=== Changes in $file ==="
    uv run python -m tree_sitter_analyzer_v2.cli.main analyze "$file" --format toon
    echo ""
done
```

**收益**: 快速回顾今天的工作，发现潜在问题

---

## 📊 使用中发现问题 → 改进 V2

### 记录使用痛点

每次使用 V2 时，记录以下问题：

#### 痛点 1: CLI 命令太长
**问题**:
```bash
uv run python -m tree_sitter_analyzer_v2.cli.main analyze file.py --format markdown
```
太冗长

**改进方向**:
- [ ] 创建 shell alias: `alias tsa='uv run python -m tree_sitter_analyzer_v2.cli.main'`
- [ ] 打包为独立可执行文件
- [ ] 添加到 PATH

#### 痛点 2: 缺少 --summary 快速模式
**问题**: 想快速查看文件概览，但只有详细模式

**改进方向**:
- [ ] 添加 `--summary` flag
- [ ] 输出格式: `Classes: X, Methods: Y, Lines: Z`

#### 痛点 3: Code Graph 输出太多
**问题**: 大项目的调用图包含太多节点，难以阅读

**改进方向**:
- [ ] 添加 `--max-nodes` 参数
- [ ] 支持按模块过滤
- [ ] 支持按深度限制

#### 痛点 4: 缺少文件搜索功能
**问题**: 想找特定类型的文件，但 CLI 不支持

**改进方向**:
- [ ] 添加 `search-files` 子命令
- [ ] 集成 fd 工具
- [ ] 支持 glob pattern

---

## 🛠️ 快速改进优先级

### 本周必做 (Week 1)

#### 改进 1: 简化 CLI 使用
```bash
# 目标：从这个
uv run python -m tree_sitter_analyzer_v2.cli.main analyze file.py

# 变成这个
tsa analyze file.py
```

**实现步骤**:
1. 在 `pyproject.toml` 中添加 `scripts` 入口
2. 创建 `tsa` 命令别名
3. 测试安装后的命令

#### 改进 2: 添加 --summary 模式
```python
# 实现简要输出模式
def format_summary(result):
    return f"""
    File: {result.file_path}
    Lines: {result.total_lines} (Code: {result.code_lines}, Comments: {result.comment_lines})
    Classes: {len(result.classes)}
    Methods: {len(result.methods)}
    Complexity: {result.avg_complexity:.2f}
    """
```

#### 改进 3: Code Graph 可视化优化
```python
# 添加节点过滤
def export_to_mermaid(graph, max_nodes=50, include_only=None, exclude=None):
    # 支持按文件、模块、类型过滤
    pass
```

### 下周必做 (Week 2)

#### 改进 4: 添加 C/C++ 支持
**原因**: 日常工作中经常遇到 C/C++ 代码

**实现**:
1. 参考 v1 的 C/C++ parser
2. 实现基础的 function/struct 提取
3. 添加 Code Graph 支持

#### 改进 5: 性能基准测试
**原因**: 确保 v2 不比 v1 慢

**实现**:
1. 创建 benchmark 测试套件
2. 对比 v1/v2 在同一文件上的速度
3. 优化瓶颈

---

## 📈 使用驱动开发循环

```
使用 V2 → 发现痛点 → 记录问题 → 快速修复 → 再次使用 → 验证改进
    ↑                                                              ↓
    └──────────────────────────────────────────────────────────────┘
                            持续改进
```

### 每周回顾

#### Week 1 回顾清单
- [ ] V2 使用次数: ___次
- [ ] 发现的痛点: ___个
- [ ] 已修复的痛点: ___个
- [ ] 新增功能: ___个
- [ ] 性能提升: ___%

#### 成功指标
- **使用频率**: 从每周 0 次 → 每天 5+ 次
- **CLI 命令长度**: 从 50 字符 → 20 字符
- **分析速度**: 从 5 秒 → 1 秒
- **功能完整性**: 从 20% → 50%

---

## 🎯 1 个月后的目标

### 功能目标
- [ ] 支持 Java, Python, TypeScript, C, C++, Go, Rust (7 种语言)
- [ ] CLI 命令简洁易用 (tsa analyze, tsa search, tsa graph)
- [ ] Code Graph 可视化优化 (支持过滤、限制节点数)
- [ ] 性能 ≥ V1 (缓存命中率 > 90%)

### 使用目标
- [ ] 每天使用 V2 至少 5 次
- [ ] 用 V2 审查所有 PR
- [ ] 用 V2 学习新项目
- [ ] 用 V2 重构代码

### 质量目标
- [ ] 测试覆盖率 > 85%
- [ ] 发现 0 critical bugs
- [ ] 文档完整覆盖所有功能
- [ ] 示例项目丰富多样

---

## 💡 实用技巧

### 技巧 1: 创建 Shell 函数
```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
tsa() {
    cd /path/to/tree-sitter-analyzer/v2
    uv run python -m tree_sitter_analyzer_v2.cli.main "$@"
}

tsa-graph() {
    cd /path/to/tree-sitter-analyzer/v2
    uv run python -c "
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
from tree_sitter_analyzer_v2.graph.export import export_to_mermaid
builder = CodeGraphBuilder(language='$1')
graph = builder.build_from_directory('$2', pattern='**/*.$1', cross_file=True)
print(export_to_mermaid(graph, max_nodes=50))
"
}
```

### 技巧 2: 集成到 VS Code
```json
// .vscode/tasks.json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "Analyze Current File",
      "type": "shell",
      "command": "tsa analyze ${file} --format markdown",
      "group": "build"
    },
    {
      "label": "Build Code Graph",
      "type": "shell",
      "command": "tsa-graph python ${fileDirname}",
      "group": "build"
    }
  ]
}
```

### 技巧 3: Pre-commit Hook
```bash
# .git/hooks/pre-commit
#!/bin/bash
# 分析即将提交的文件
git diff --cached --name-only | grep "\.py$" | while read file; do
    tsa analyze "$file" --format summary
done
```

---

## 🎓 学习计划

### Week 1: 熟悉 V2 功能
- [ ] 阅读 V2 所有文档
- [ ] 运行所有测试用例
- [ ] 分析 V2 自身代码

### Week 2: 深度使用
- [ ] 用 V2 分析真实项目
- [ ] 发现至少 10 个改进点
- [ ] 实现至少 3 个改进

### Week 3: 扩展功能
- [ ] 添加 1-2 种新语言支持
- [ ] 优化性能瓶颈
- [ ] 编写使用指南

### Week 4: 分享与推广
- [ ] 创建示例项目
- [ ] 录制使用视频
- [ ] 编写最佳实践文档

---

## ✅ 行动清单

### 今天就做 (Day 1)
- [ ] 创建 `tsa` shell 别名
- [ ] 用 V2 分析 1 个真实文件
- [ ] 记录 1 个痛点

### 本周完成 (Week 1)
- [ ] 每天使用 V2 至少 1 次
- [ ] 修复 3 个痛点
- [ ] 添加 --summary 模式

### 本月完成 (Month 1)
- [ ] V2 成为日常工具
- [ ] 支持 7 种语言
- [ ] 性能优化完成

---

**结论**: 让 V2 成为喜爱的工具的关键是**真实使用**。通过每天使用、发现问题、快速改进的循环，V2 会逐步成为不可或缺的开发工具。不要等所有功能都完成才开始使用，而是在使用中驱动开发！
