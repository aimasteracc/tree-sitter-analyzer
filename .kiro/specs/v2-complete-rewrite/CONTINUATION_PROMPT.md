# V2 Daily Use Continuation Prompt

Copy this prompt to start a new session continuing V2 improvements:

---

## Context

我正在开发 **tree-sitter-analyzer v2** (企业级代码分析工具)，采用**使用驱动开发**的方法：每天使用 V2，发现痛点，立即修复，持续改进。

**项目位置**: `C:\git-private\tree-sitter-analyzer\v2`
**当前分支**: `v2-rewrite`
**最新提交**: `fec62ad` - Daily use improvements

---

## V2 Current Status (2026-02-02)

### ✅ 已完成 (Production Ready)
1. **Java Language Support** - 完整支持 + Code Graph (26/26 tasks, 71 tests passing)
2. **Python Language Support** - 完整支持 + Code Graph
3. **TypeScript Language Support** - 完整支持 + Code Graph
4. **Code Graph System** - 跨文件调用图、依赖分析、Mermaid可视化 (V1没有的杀手级功能)
5. **MCP Integration** - 7个工具 (analyze, extract, query, scale, find_and_grep, search, code_graph)
6. **Encoding Detection** - ✅ 已修复 (CLI集成EncodingDetector)
7. **CLI Short Alias** - ✅ 已添加 (`tsa` 命令)

### ❌ V1 vs V2 Gap
- **Languages**: 17 (V1) vs 3 (V2) = **缺少14种** (C/C++, C#, Go, Rust, Kotlin, PHP, Ruby, SQL, HTML, CSS, YAML, Markdown)
- **Tests**: 8405 (V1) vs ~150 (V2) = **56倍差距**
- **CLI Features**: V1功能更全 (--summary, --table full, --show-languages)

### 🎯 V2 Unique Advantages
- ✅ **Code Graph** - V1完全没有 (跨文件调用图、依赖分析、可视化)
- ✅ **Architecture** - 插件系统、100% Type Safety、双层缓存
- ✅ **Performance** - 懒加载、增量构建

---

## Quick Start Commands

### Basic Usage
```bash
cd C:\git-private\tree-sitter-analyzer\v2

# Analyze file (now works with any encoding!)
uv run tsa analyze tree_sitter_analyzer_v2/graph/symbols.py --format toon
uv run tsa analyze tree_sitter_analyzer_v2/graph/symbols.py --format markdown

# Build Code Graph
uv run python -c "
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
from tree_sitter_analyzer_v2.graph.export import export_to_mermaid

builder = CodeGraphBuilder(language='python')
graph = builder.build_from_directory('tree_sitter_analyzer_v2/graph', pattern='**/*.py', cross_file=True)

print(f'Nodes: {graph.number_of_nodes()}, Edges: {graph.number_of_edges()}')
print(export_to_mermaid(graph, max_nodes=30))
"

# Run tests
uv run pytest tests/ -v
```

---

## Key Documents to Read

### Planning & Progress
1. **`.kiro/specs/v2-complete-rewrite/V1_VS_V2_GAP_ANALYSIS.md`**
   - 完整的V1/V2功能对比
   - 实施路线图 (8-12周达到功能对齐)
   - 成功指标

2. **`.kiro/specs/v2-complete-rewrite/V2_DAILY_USE_ACTION_PLAN.md`**
   - 每日使用场景和命令
   - Shell函数和VS Code集成
   - 每周学习计划

3. **`.kiro/specs/v2-complete-rewrite/PAINPOINTS_TRACKER.md`** ⭐ **最重要**
   - 8个已发现的痛点 (2个已修复, 6个待解决)
   - 优先级排序 (本周必做 vs 下周 vs 长期)
   - 每个痛点的详细改进方案

4. **`.kiro/specs/v2-complete-rewrite/E5_JAVA_PROGRESS.md`**
   - Java支持完成度: 100% (26/26 tasks)
   - 71 tests passing (106% of target)

5. **`.kiro/specs/v2-complete-rewrite/CODE_GRAPH_PROGRESS.md`**
   - Code Graph 5个增强全部完成
   - E1-E5详细文档

---

## 本周必做 (Week 1 - 7 hours total)

根据 `PAINPOINTS_TRACKER.md`，**本周优先级最高的改进**:

### 1️⃣ 实现 --summary 快速模式 (2小时)
**痛点 #4** - 当前只有详细输出，想快速查看文件概览时信息过载

**期望输出**:
```bash
uv run tsa analyze symbols.py --summary
# File: symbols.py
# Lines: 357 (Code: 280, Comments: 50, Blank: 27)
# Classes: 3 (SymbolEntry, SymbolTable, SymbolTableBuilder)
# Methods: 6
# Complexity: 2.5 avg
```

**实现位置**:
- `tree_sitter_analyzer_v2/cli/main.py` - 添加 `--summary` flag
- `tree_sitter_analyzer_v2/formatters/` - 创建 `summary_formatter.py`

### 2️⃣ 优化 Markdown 输出格式 (3小时)
**痛点 #3** - Markdown表格嵌套在表格里，难以阅读

**改进方向**:
- 为 methods/attributes 使用列表而非嵌套表格
- 或者拆分为多个表格 (Classes一个表, Methods另一个表)
- 添加 `--compact` 模式

**实现位置**: `tree_sitter_analyzer_v2/formatters/markdown_formatter.py`

### 3️⃣ 添加 Code Graph 过滤 (2小时)
**痛点 #6** - 大项目的Code Graph包含太多节点，难以阅读

**期望功能**:
```bash
# 聚焦特定函数的上下游
uv run tsa graph --focus SymbolTable --depth 2

# 只显示CALLS边
uv run tsa graph --edge-types CALLS

# 只显示特定模块
uv run tsa graph --modules symbols,cross_file
```

**实现位置**:
- `tree_sitter_analyzer_v2/graph/export.py` - 增强 `export_to_mermaid()`
- `tree_sitter_analyzer_v2/cli/main.py` - 添加 `graph` 子命令

---

## 使用驱动开发循环

### Daily Routine (每天重复)

#### Morning (早晨)
1. **用V2分析今天要修改的代码**
   ```bash
   uv run tsa analyze <file_to_modify> --format toon
   ```

2. **构建相关模块的调用图**
   ```bash
   uv run python -c "
   from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
   builder = CodeGraphBuilder(language='python')
   graph = builder.build_from_directory('path/to/module', pattern='**/*.py', cross_file=True)
   print(f'Nodes: {graph.number_of_nodes()}, Edges: {graph.number_of_edges()}')
   "
   ```

#### During Development (开发中)
3. **发现痛点 → 立即记录**
   - 打开 `PAINPOINTS_TRACKER.md`
   - 使用模板添加新痛点
   - 评估优先级和工作量

4. **快速修复 Critical 痛点**
   - 影响使用的问题立即修复
   - 其他问题记录到本周/下周计划

#### Evening (晚间)
5. **回顾今天的改动**
   ```bash
   git diff HEAD~1 --name-only | grep "\.py$" | while read file; do
       uv run tsa analyze "$file" --format toon
   done
   ```

6. **更新PAINPOINTS_TRACKER.md**
   - 标记已解决的痛点为 ✅
   - 添加新发现的痛点
   - 调整下周优先级

---

## Success Metrics (成功指标)

### This Week Goals
- [ ] V2使用频率: 从3次/天 → 5+次/天
- [ ] 痛点 #3, #4, #6 全部解决
- [ ] CLI命令简化 50% (已完成 ✅)
- [ ] 发现并记录至少 3 个新痛点

### This Month Goals
- [ ] 支持 7 种语言 (Java/Python/TS/C/C++/Go/Rust)
- [ ] 测试数量 > 500
- [ ] 所有High优先级痛点解决
- [ ] V2成为日常首选工具

---

## Next Actions (立即开始)

### Option A: 继续使用V2 (推荐)
**目标**: 发现更多痛点，验证已有功能

**行动**:
1. 用V2分析一个真实项目 (比如V2自己的代码)
2. 尝试所有可用功能 (analyze, code graph, mermaid)
3. 记录遇到的所有问题到 `PAINPOINTS_TRACKER.md`

**示例任务**:
- 分析 `tree_sitter_analyzer_v2/languages/` 模块
- 构建整个v2项目的Code Graph
- 生成Mermaid可视化并保存为文件

### Option B: 实现本周必做改进
**目标**: 解决已知的高优先级痛点

**行动**:
1. 实现 `--summary` 快速模式 (2h)
2. 优化 Markdown 输出格式 (3h)
3. 添加 Code Graph 过滤功能 (2h)

### Option C: 补全核心语言
**目标**: 缩小与V1的差距

**行动**:
1. 实现 C/C++ Parser (参考 v1 的实现)
2. 实现 Go Parser
3. 为每种语言添加 Code Graph 支持

---

## Important Notes

### 1. 不要重复造轮子
- V1 已经实现了 17 种语言，可以参考 `tree_sitter_analyzer/` 目录
- 复制 V1 的 parser 逻辑，适配 V2 的架构
- 重点是集成 Code Graph 功能 (这是V2的优势)

### 2. TDD 开发流程
- 先写测试 (参考 `v2/tests/unit/test_java_parser.py`)
- 再实现功能
- 确保覆盖率 > 80%

### 3. 文档优先
- 每个新功能都要更新 `PAINPOINTS_TRACKER.md`
- 每次使用都要记录发现的问题
- 保持文档与代码同步

### 4. 小步快跑
- 优先解决影响使用的Critical痛点
- 每个改进 < 4 小时
- 频繁提交，保持进度可见

---

## Example Prompt to Start

你可以用这样的prompt开始新对话：

```
我正在继续开发 tree-sitter-analyzer v2，采用"使用驱动开发"方法。

当前状态:
- ✅ Java/Python/TypeScript 支持完成
- ✅ Code Graph 系统完成
- ✅ CLI 编码问题已修复
- ✅ tsa 短命令已添加

本周待做 (PAINPOINTS_TRACKER.md):
1. 实现 --summary 快速模式 (2h)
2. 优化 Markdown 输出格式 (3h)
3. 添加 Code Graph 过滤 (2h)

请帮我: [选择 A/B/C]
A. 继续使用V2分析真实项目，发现新痛点
B. 实现本周必做的改进 (从痛点#4开始)
C. 补全C/C++语言支持

项目位置: C:\git-private\tree-sitter-analyzer\v2
关键文档: .kiro/specs/v2-complete-rewrite/PAINPOINTS_TRACKER.md
```

---

**核心理念**: 不要等所有功能都完成才使用！每天使用V2，在使用中发现问题并修复，让真实需求驱动开发优先级！
