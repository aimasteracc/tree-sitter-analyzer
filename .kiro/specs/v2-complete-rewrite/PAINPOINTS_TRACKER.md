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

## 🔄 更新日志

### 2026-02-02
- ✅ 解决痛点 #1: 编码检测缺失
- 📝 记录痛点 #2-8
- 🎯 制定本周改进计划
