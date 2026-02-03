# Session 20: V2 真实使用与痛点发现

**日期**: 2026-02-03
**会话类型**: 真实使用驱动开发 (Usage-Driven Development)
**目标**: 通过实际使用 V2 的各种功能，发现并记录新的痛点

---

## 📋 测试场景清单

### ✅ 场景 1: 分析 Python 核心模块
**命令**:
```bash
cd v2
uv run tsa analyze tree_sitter_analyzer_v2/core/parser.py --format markdown
uv run tsa analyze tree_sitter_analyzer_v2/core/parser.py --format toon
```

**结果**:
- ✅ Markdown 格式正常输出
- ✅ TOON 格式正常输出
- ⚠️ 发现 Markdown 表格嵌套问题（已知痛点 #3）

---

### ❌ 场景 2: 快速查看文件概览
**命令**:
```bash
uv run tsa analyze tree_sitter_analyzer_v2/core/parser.py --summary
```

**结果**:
- ❌ 参数 `--summary` 不存在
- 验证了已知痛点 #4

---

### ✅ 场景 3: 分析较大 Python 文件
**命令**:
```bash
uv run tsa analyze tree_sitter_analyzer_v2/graph/symbols.py --format markdown
```

**结果**:
- ✅ 成功分析 357 行文件
- ✅ 正确识别 3 个类 (SymbolEntry, SymbolTable, SymbolTableBuilder)
- ⚠️ Markdown 表格嵌套严重（Methods 列中嵌套参数表格）

---

### ✅ 场景 4: 构建 Code Graph
**命令**:
```python
from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder
from tree_sitter_analyzer_v2.graph.export import export_to_mermaid

builder = CodeGraphBuilder(language='python')
graph = builder.build_from_directory('tree_sitter_analyzer_v2/graph', pattern='**/*.py', cross_file=True)
```

**结果**:
- ✅ 成功构建 Code Graph
- ✅ Nodes: 92, Edges: 131
- ✅ 生成 Mermaid 图
- ⚠️ 发现痛点 #6: 92 个节点太多，难以阅读
- ⚠️ 发现痛点 #14: 缺少查询和过滤能力

---

### ❌ 场景 5: 使用 Python API 提取代码片段
**命令**:
```python
from tree_sitter_analyzer_v2.api.interface import extract_code_section

result = extract_code_section(
    file_path='tree_sitter_analyzer_v2/graph/symbols.py',
    start_line=212,
    end_line=289,
    output_format='markdown'
)
```

**结果**:
- ❌ ImportError: cannot import name 'extract_code_section'
- 🆕 发现痛点 #9: API 文档与实际实现不一致

---

### ✅ 场景 6: 搜索 Python 文件
**命令**:
```bash
uv run tsa search-files tree_sitter_analyzer_v2 "*.py"
```

**结果**:
- ✅ 成功找到 127 个 Python 文件
- ✅ 输出格式清晰

---

### ⚠️ 场景 7: 搜索文件内容
**命令**:
```bash
uv run tsa search-content tree_sitter_analyzer_v2 "CodeGraphBuilder"
```

**结果**:
- ✅ CLI 正常工作，找到 11 个匹配
- ❌ Python API 返回 0 个匹配
- 🆕 发现痛点 #10: search_content API 返回错误结果
- 🆕 发现痛点 #11: 后台线程 UnicodeDecodeError (cp932)

---

### ⚠️ 场景 8: 测试 Python API
**命令**:
```python
from tree_sitter_analyzer_v2.api.interface import TreeSitterAnalyzerAPI

api = TreeSitterAnalyzerAPI()
result1 = api.analyze_file('tree_sitter_analyzer_v2/core/parser.py', output_format='toon')
result2 = api.search_files('.', pattern='*.py', file_type='py')
result3 = api.search_content('.', pattern='CodeGraphBuilder', file_type='py')
```

**结果**:
- ✅ analyze_file 正常工作
- ✅ search_files 正常工作 (127 files)
- ❌ search_content 返回 0 matches (应该是 11)
- ❌ 后台线程编码错误

---

### ✅ 场景 9: 分析 Java 代码
**命令**:
```bash
uv run tsa analyze ../examples/BigService.java --format markdown
```

**结果**:
- ✅ 成功分析大型 Java 文件
- ✅ 正确提取所有方法和复杂度
- ⚠️ Markdown 表格嵌套问题依然存在

---

### ✅ 场景 10: 分析 TypeScript 代码
**命令**:
```bash
uv run tsa analyze tests/fixtures/analyze_fixtures/sample.ts --format toon
```

**结果**:
- ✅ 成功分析 TypeScript 文件
- ✅ 正确识别 interfaces, classes, functions
- ✅ TOON 格式输出清晰

---

### ✅ 场景 11: 性能测试 - Code Graph 构建
**命令**:
```python
import time
builder = CodeGraphBuilder(language='python')
start = time.time()
graph = builder.build_from_directory('tree_sitter_analyzer_v2', pattern='**/*.py', cross_file=True)
elapsed = time.time() - start
```

**结果**:
- ✅ 构建时间: 5.99秒
- ✅ 410 nodes, 644 edges
- ✅ 性能: 68.4 nodes/sec
- 👍 性能表现良好

---

### ❌ 场景 12: 检查 MCP 服务器
**命令**:
```python
from tree_sitter_analyzer_v2.mcp.server import TreeSitterAnalyzerMCPServer
```

**结果**:
- ❌ ImportError: cannot import name 'TreeSitterAnalyzerMCPServer'
- 🆕 发现痛点 #12: MCP 服务器类名不一致（实际是 `MCPServer`）

---

## 📊 发现的新痛点总结

### 🔴 Critical (需立即修复)
1. **痛点 #10**: search_content Python API 返回错误结果 (0 vs 11)
2. **痛点 #11**: search_content 后台线程编码错误 (UnicodeDecodeError)

### 🟡 Medium (本周修复)
3. **痛点 #9**: API 文档与实际实现不一致 (extract_code_section 不存在)
4. **痛点 #13**: 缺少批量分析功能
5. **痛点 #14**: Code Graph 缺少过滤和查询能力

### 🟢 Low (下周修复)
6. **痛点 #12**: MCP 服务器类名不一致

---

## ✅ 验证的功能正常性

### 核心功能 ✅
- ✅ tsa analyze (Python) - 正常工作
- ✅ tsa analyze (Java) - 正常工作
- ✅ tsa analyze (TypeScript) - 正常工作
- ✅ tsa search-files - 正常工作
- ✅ Code Graph 构建 - 性能良好 (68 nodes/sec)
- ✅ Mermaid 可视化 - 正常输出

### API 功能 ⚠️
- ✅ api.analyze_file() - 正常工作
- ✅ api.search_files() - 正常工作
- ❌ api.search_content() - 返回错误结果
- ❌ extract_code_section() - 不存在

---

## 🎯 修复优先级建议

### 今日必做 (2-3 小时)
1. **修复痛点 #10**: search_content API 返回 0 结果
   - 检查 SearchEngine.search_content() 实现
   - 对比 CLI 和 API 调用差异
   - 添加测试验证修复

2. **修复痛点 #11**: 编码错误
   - 在 subprocess 调用中显式指定 UTF-8
   - 测试 Windows 兼容性

### 本周必做 (5-6 小时)
3. **实现痛点 #4**: --summary 快速模式
4. **优化痛点 #3**: Markdown 格式（去除表格嵌套）
5. **修复痛点 #9**: 添加 extract_code_section API 或更新文档

### 下周必做 (7-8 小时)
6. **增强痛点 #14**: Code Graph 查询能力
7. **实现痛点 #13**: 批量分析功能
8. **优化痛点 #6**: Code Graph 过滤功能

---

## 💡 使用体验反思

### 正面体验
1. ✅ **tsa 短命令很方便** - 已解决痛点 #2
2. ✅ **TOON 格式输出简洁清晰** - 比 Markdown 更适合 AI 消费
3. ✅ **Code Graph 构建速度快** - 68 nodes/sec，对中小项目足够
4. ✅ **TypeScript/Java/Python 支持完整** - 核心语言覆盖良好

### 负面体验
1. ❌ **search_content API 不可用** - Critical 问题，阻碍实际使用
2. ❌ **缺少 --summary 模式** - 每次都输出完整内容信息过载
3. ❌ **Code Graph 太大无法过滤** - 92 节点难以阅读和分析
4. ❌ **文档与实现不一致** - 浪费时间调试不存在的 API

### 改进方向
1. **立即修复 Critical 问题** - search_content 必须可用
2. **补全缺失功能** - --summary, extract_code_section
3. **增强 Code Graph** - 查询、过滤、聚焦功能
4. **完善文档** - 所有 API 示例必须可运行

---

## 🚀 下一步行动

### 立即行动 (今天)
1. [ ] 修复 search_content API (#10)
2. [ ] 修复编码错误 (#11)
3. [ ] 验证修复效果

### 本周行动
4. [ ] 实现 --summary 模式 (#4)
5. [ ] 优化 Markdown 格式 (#3)
6. [ ] 添加或文档化 extract_code_section (#9)

### 下周行动
7. [ ] 实现 Code Graph 查询 API (#14)
8. [ ] 实现批量分析功能 (#13)
9. [ ] 添加 Code Graph 过滤 (#6)

---

## 📈 V2 成熟度评估

### 功能完整性
- 基础分析: ⭐⭐⭐⭐⭐ (5/5) - 完全可用
- 文件搜索: ⭐⭐⭐⭐⭐ (5/5) - 完全可用
- 内容搜索 (CLI): ⭐⭐⭐⭐⭐ (5/5) - 完全可用
- 内容搜索 (API): ⭐☆☆☆☆ (1/5) - 严重问题
- Code Graph: ⭐⭐⭐⭐☆ (4/5) - 核心功能完整，缺少查询能力
- Python API: ⭐⭐⭐☆☆ (3/5) - 部分可用，有 bug

### 用户体验
- CLI 易用性: ⭐⭐⭐⭐☆ (4/5) - tsa 短命令很好，缺 --summary
- 输出格式: ⭐⭐⭐⭐☆ (4/5) - TOON 优秀，Markdown 有嵌套问题
- 错误信息: ⭐⭐⭐⭐☆ (4/5) - 清晰明确
- 性能: ⭐⭐⭐⭐⭐ (5/5) - 68 nodes/sec 很快

### 文档质量
- API 文档: ⭐⭐⭐☆☆ (3/5) - 有不一致问题
- 使用示例: ⭐⭐⭐⭐☆ (4/5) - 大部分可运行
- 错误排查: ⭐⭐⭐☆☆ (3/5) - 需要更多调试信息

### 总体评分: ⭐⭐⭐⭐☆ (4/5)
**结论**: V2 已经是一个**可用的工具**，核心功能稳定，但有 2 个 Critical bug (#10, #11) 需要立即修复才能日常使用。

---

## 📝 使用心得

1. **V2 的杀手级功能是 Code Graph** - 这是 V1 没有的，值得投入资源完善
2. **TOON 格式非常适合 AI 消费** - 应该作为默认格式
3. **search_content 是高频功能** - 必须优先修复 API 的 bug
4. **--summary 是刚需** - 不想每次都看完整输出
5. **文档必须可运行** - 示例代码必须经过测试

---

**下次使用计划**: 修复 Critical bugs 后，用 V2 分析一个真实的大型项目（如 Django 或 FastAPI），进一步验证性能和可用性。
