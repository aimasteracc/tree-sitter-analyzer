# V2 使用痛点跟踪 - 持续改进

## 📋 痛点列表

### ✅ 已解决

#### 痛点 #1: 编码检测缺失
**发现时间**: 2026-02-02
**严重程度**: 🔴 Critical
**问题**: CLI 在读取文件时没有使用 EncodingDetector，Windows 上默认用 cp932 导致 UnicodeDecodeError

**解决方案**:
```python
# 修改前
content = file_path.read_text()  # ❌ 使用系统默认编码

# 修改后
encoding_detector = EncodingDetector()
content = encoding_detector.read_file_safe(file_path)  # ✅ 自动检测编码
```

**文件**: `tree_sitter_analyzer_v2/cli/main.py`
**状态**: ✅ 已修复
**验证**: 成功分析 symbols.py

---

### ⚠️ 待解决

#### 痛点 #2: CLI 命令过长
**发现时间**: 2026-02-02
**严重程度**: 🟡 Medium
**问题**:
```bash
# 当前命令太长
uv run python -m tree_sitter_analyzer_v2.cli.main analyze file.py --format markdown
```

**期望**:
```bash
# 应该简化为
tsa analyze file.py --format markdown
```

**优先级**: 🔥 High
**预计工作量**: 2 小时
**改进方案**:
1. 在 `pyproject.toml` 中添加 `[project.scripts]`
2. 创建 `tsa` 入口点
3. 测试安装后的命令

**状态**: 🔄 计划中

---

#### 痛点 #3: Markdown 输出格式混乱
**发现时间**: 2026-02-02
**严重程度**: 🟡 Medium
**问题**: Markdown 表格嵌套在表格里，methods 列包含另一个表格，难以阅读

**示例**:
```markdown
| Name | Methods | ... |
| --- | --- | --- |
| SymbolTable | | Name | Parameters | ... |
| --- | --- | --- |
| add | self, entry | ... | | ... |
```

**改进方案**:
1. 为 methods/attributes 使用列表而非嵌套表格
2. 或者拆分为多个表格（Classes 一个表，Methods 另一个表）
3. 添加 `--compact` 模式只显示核心信息

**优先级**: 🔥 High
**预计工作量**: 3 小时
**状态**: 🔄 计划中

---

#### 痛点 #4: 缺少 --summary 快速模式
**发现时间**: 2026-02-02
**严重程度**: 🟡 Medium
**问题**: 当前只有详细输出，想快速查看文件概览时信息过载

**期望输出**:
```
File: symbols.py
Lines: 357 (Code: 280, Comments: 50, Blank: 27)
Classes: 3 (SymbolEntry, SymbolTable, SymbolTableBuilder)
Methods: 6
Complexity: 2.5 avg
```

**改进方案**:
```python
# 在 CLI 中添加 --summary flag
parser.add_argument("--summary", action="store_true", help="Show quick summary only")

# 实现 summary formatter
def format_summary(result):
    return f"""
File: {result.file_path}
Lines: {result.total_lines} (Code: {result.code_lines}, Comments: {result.comment_lines})
Classes: {len(result.classes)} ({', '.join(c.name for c in result.classes[:3])})
Methods: {len(result.methods)}
"""
```

**优先级**: 🔥 High
**预计工作量**: 2 小时
**状态**: 🔄 计划中

---

#### 痛点 #5: Windows 控制台 Emoji 不支持
**发现时间**: 2026-02-02
**严重程度**: 🟢 Low
**问题**: Python 脚本中的 emoji 字符导致 UnicodeEncodeError (cp932)

**临时方案**: 不使用 emoji
**长期方案**:
1. 检测控制台编码能力
2. 自动降级为 ASCII 输出
3. 或者使用 `colorama` 库处理 Windows 控制台

**优先级**: 🟢 Low
**预计工作量**: 1 小时
**状态**: 🔄 计划中

---

#### 痛点 #6: Code Graph 输出太多
**发现时间**: 2026-02-02
**严重程度**: 🟡 Medium
**问题**: 大项目的 Code Graph 包含太多节点 (92个)，Mermaid 图难以阅读

**改进方案**:
1. 添加 `--filter` 参数按模块/类/文件过滤
2. 添加 `--depth` 参数限制调用深度
3. 添加 `--focus` 参数聚焦特定函数的上下游
4. 智能节点聚合（将相似节点合并）

**示例**:
```bash
# 只显示 SymbolTable 相关的调用链
tsa graph --focus SymbolTable --depth 2

# 只显示 CALLS 边（隐藏 CONTAINS）
tsa graph --edge-types CALLS

# 只显示特定模块
tsa graph --modules symbols,cross_file
```

**优先级**: 🔥 High
**预计工作量**: 4 小时
**状态**: 🔄 计划中

---

#### 痛点 #7: 缺少增量分析
**发现时间**: 2026-02-02 (预见性痛点)
**严重程度**: 🟡 Medium
**问题**: 每次分析都重新解析所有文件，大项目很慢

**改进方案**:
1. 实现文件级缓存（基于 mtime）
2. 只重新分析改动的文件
3. 增量更新 Code Graph

**优先级**: 🟢 Medium
**预计工作量**: 8 小时
**状态**: 🔄 计划中

---

#### 痛点 #8: 缺少文件搜索集成
**发现时间**: 2026-02-02 (预见性痛点)
**严重程度**: 🟡 Medium
**问题**: 想找特定类型的文件时需要手动用 find 命令

**期望**:
```bash
# 查找所有 Python 文件
tsa search-files --type py --pattern "*test*"

# 查找内容
tsa search-content --query "SymbolTable" --type py
```

**改进方案**: CLI 已有 `search-files` 和 `search-content` 子命令，但需要测试和文档

**优先级**: 🟢 Medium
**预计工作量**: 2 小时
**状态**: 🔄 计划中

---

## 📈 改进优先级排序

### 本周必做 (Week 1)
1. **痛点 #2**: CLI 命令简化 (2h) - 直接影响日常使用
2. **痛点 #4**: 添加 --summary 模式 (2h) - 高频需求
3. **痛点 #3**: Markdown 格式优化 (3h) - 可读性关键

**总计**: 7 小时

### 下周实现 (Week 2)
4. **痛点 #6**: Code Graph 过滤功能 (4h) - 大项目必需
5. **痛点 #8**: 文件搜索集成测试 (2h) - 补全功能
6. **痛点 #5**: Windows 控制台 emoji (1h) - 用户体验

**总计**: 7 小时

### 长期优化 (Week 3+)
7. **痛点 #7**: 增量分析 (8h) - 性能优化

---

## 🎯 成功指标

### 本周目标
- [ ] CLI 命令从 50+ 字符缩短到 20 字符
- [ ] --summary 模式实现并通过测试
- [ ] Markdown 输出可读性评分 > 8/10

### 本月目标
- [ ] 所有 High 优先级痛点解决
- [ ] 每天使用 V2 至少 5 次
- [ ] 发现至少 10 个新痛点并记录

---

## 📝 痛点反馈模板

```markdown
#### 痛点 #X: [简短描述]
**发现时间**: YYYY-MM-DD
**严重程度**: 🔴 Critical / 🟡 Medium / 🟢 Low
**问题**: [详细描述问题]

**当前行为**:
[代码示例或命令示例]

**期望行为**:
[代码示例或命令示例]

**改进方案**:
1. [方案 1]
2. [方案 2]

**优先级**: 🔥 High / 🟢 Medium / 🟢 Low
**预计工作量**: X 小时
**状态**: 🔄 计划中 / ✅ 已修复 / ❌ 已放弃
```

---

#### 痛点 #9: API 文档与实际实现不一致
**发现时间**: 2026-02-03
**严重程度**: 🟡 Medium
**问题**: `V2_DAILY_USE_ACTION_PLAN.md` 文档提到 `extract_code_section` API，但实际 `api/interface.py` 中不存在

**当前行为**:
```python
from tree_sitter_analyzer_v2.api.interface import extract_code_section
# ImportError: cannot import name 'extract_code_section'
```

**期望行为**:
```python
# 应该可以这样使用
result = extract_code_section(
    file_path="symbols.py",
    start_line=212,
    end_line=289,
    output_format="markdown"
)
```

**改进方案**:
1. 在 `api/interface.py` 中添加 `extract_code_section` 函数
2. 或者更新文档，说明应该使用 MCP 工具而不是 Python API
3. 检查所有文档，确保 API 示例与实际实现一致

**优先级**: 🟢 Medium
**预计工作量**: 1 小时
**状态**: 🔄 新发现

---

#### 痛点 #10: search_content Python API 返回错误结果
**发现时间**: 2026-02-03
**严重程度**: 🔴 Critical
**问题**: `api.search_content()` 找到 0 个匹配，但 CLI 的 `tsa search-content` 找到了 11 个匹配

**当前行为**:
```python
result = api.search_content('.', pattern='CodeGraphBuilder', file_type='py')
# result['count'] = 0，但应该是 11
```

**期望行为**:
```python
result = api.search_content('.', pattern='CodeGraphBuilder', file_type='py')
# result['count'] = 11
# result['matches'] = [...11 个匹配...]
```

**改进方案**:
1. 检查 `search_engine.search_content()` 的实现
2. 对比 CLI 和 API 的调用差异
3. 修复参数传递或 ripgrep 命令构造问题
4. 添加测试确保 API 与 CLI 行为一致

**优先级**: 🔥 High
**预计工作量**: 2 小时
**状态**: 🔄 新发现

---

#### 痛点 #11: search_content 后台线程编码错误
**发现时间**: 2026-02-03
**严重程度**: 🟡 Medium
**问题**: `search_content` 执行后，后台线程抛出 `UnicodeDecodeError: 'cp932'`

**错误信息**:
```
Exception in thread Thread-3 (_readerthread):
UnicodeDecodeError: 'cp932' codec can't decode byte 0x92 in position 9373
```

**根本原因**:
- subprocess 读取 ripgrep 输出时使用系统默认编码 (Windows cp932)
- ripgrep 输出是 UTF-8，导致解码失败

**改进方案**:
1. 在 `SearchEngine.search_content()` 中显式指定 UTF-8 编码
2. 使用 `subprocess.run(..., encoding='utf-8', errors='replace')`
3. 添加 Windows 编码兼容性测试

**优先级**: 🔥 High
**预计工作量**: 1 小时
**状态**: 🔄 新发现

---

#### 痛点 #12: MCP 服务器类名不一致
**发现时间**: 2026-02-03
**严重程度**: 🟢 Low
**问题**: 文档和代码注释提到 `TreeSitterAnalyzerMCPServer`，但实际类名是 `MCPServer`

**当前行为**:
```python
from tree_sitter_analyzer_v2.mcp.server import TreeSitterAnalyzerMCPServer
# ImportError
```

**实际类名**:
```python
from tree_sitter_analyzer_v2.mcp.server import MCPServer  # 正确
```

**改进方案**:
1. 统一类名：要么改代码为 `TreeSitterAnalyzerMCPServer`
2. 或者更新所有文档使用 `MCPServer`
3. 添加类型别名确保向后兼容

**优先级**: 🟢 Low
**预计工作量**: 0.5 小时
**状态**: 🔄 新发现

---

#### 痛点 #13: 缺少批量分析功能
**发现时间**: 2026-02-03
**严重程度**: 🟡 Medium
**问题**: 想分析多个文件时，需要写循环手动调用，缺少批量分析 API

**当前行为**:
```bash
# 需要手动循环
git diff --name-only | grep "\.py$" | while read file; do
    tsa analyze "$file" --format markdown
done
```

**期望行为**:
```python
# API 支持批量分析
api = TreeSitterAnalyzerAPI()
results = api.analyze_files(
    files=["file1.py", "file2.py", "file3.py"],
    output_format="toon"
)
```

或者 CLI 支持:
```bash
tsa analyze --batch file1.py file2.py file3.py
tsa analyze --from-git-diff  # 分析 git diff 的所有文件
```

**改进方案**:
1. 在 Python API 添加 `analyze_files()` 方法
2. CLI 添加 `--batch` 参数支持多文件
3. CLI 添加 `--from-git-diff` 快捷方式
4. 支持并行分析提升性能

**优先级**: 🟢 Medium
**预计工作量**: 3 小时
**状态**: 🔄 新发现

---

#### 痛点 #14: Code Graph 缺少过滤和查询能力
**发现时间**: 2026-02-03
**严重程度**: 🟡 Medium
**问题**: 构建完 Code Graph (92 nodes, 131 edges) 后，无法方便地过滤和查询特定节点

**当前行为**:
```python
graph = builder.build_from_directory('tree_sitter_analyzer_v2/graph')
# 只能手动遍历所有节点
for node_id, data in graph.nodes(data=True):
    if 'SymbolTable' in node_id:
        print(node_id)
```

**期望行为**:
```python
# 方便的查询 API
graph = builder.build_from_directory('tree_sitter_analyzer_v2/graph')

# 查找特定类的所有方法
symbol_methods = graph.query_methods(class_name='SymbolTable')

# 查找调用链
call_chain = graph.find_call_chain(from_node='lookup', to_node='add')

# 过滤节点
filtered_graph = graph.filter(
    node_types=['METHOD'],
    file_pattern='symbols.py'
)
```

**改进方案**:
1. 在 `CodeGraph` 类添加查询方法 (query_methods, find_callers, etc.)
2. 实现 `filter()` 方法返回子图
3. 添加 `focus()` 方法聚焦特定节点的上下游
4. 在 CLI 添加 `tsa graph query` 子命令

**优先级**: 🔥 High (这是 V2 的杀手级功能，必须好用)
**预计工作量**: 4 小时
**状态**: 🔄 新发现

---

## 📈 改进优先级排序 (更新)

### 本周必做 (Week 1) - 修订
1. **痛点 #10**: 修复 search_content API (2h) - 🔴 Critical
2. **痛点 #11**: 修复编码错误 (1h) - 🔴 Critical
3. **痛点 #4**: 添加 --summary 模式 (2h) - 高频需求
4. **痛点 #3**: Markdown 格式优化 (3h) - 可读性关键

**总计**: 8 小时

### 下周实现 (Week 2) - 修订
5. **痛点 #14**: Code Graph 查询能力 (4h) - V2 核心竞争力
6. **痛点 #6**: Code Graph 过滤功能 (2h) - 大项目必需
7. **痛点 #13**: 批量分析功能 (3h) - 日常使用便利
8. **痛点 #9**: API 文档一致性 (1h) - 开发者体验

**总计**: 10 小时

### 长期优化 (Week 3+)
9. **痛点 #7**: 增量分析 (8h)
10. **痛点 #2**: CLI 命令简化 (已完成 ✅)
11. **痛点 #12**: MCP 类名统一 (0.5h)

---

## 🔄 更新日志

### 2026-02-03
- 🔍 执行真实使用测试，发现 6 个新痛点 (#9-#14)
- 🔴 发现 2 个 Critical 级别问题 (#10, #11) 需要立即修复
- 🎯 更新本周必做计划，优先修复 Critical 问题
- ✅ 验证核心功能：
  - ✅ tsa analyze (Python/Java/TypeScript) - 正常工作
  - ✅ tsa search-files - 正常工作
  - ❌ tsa search-content API - 返回错误结果
  - ✅ Code Graph 构建 - 性能良好 (68 nodes/sec)
  - ❌ API 文档 - 与实际实现不一致

### 2026-02-02
- ✅ 解决痛点 #1: 编码检测缺失
- ✅ 解决痛点 #2: CLI 命令简化 (tsa 短命令)
- 📝 记录痛点 #3-8
- 🎯 制定本周改进计划
