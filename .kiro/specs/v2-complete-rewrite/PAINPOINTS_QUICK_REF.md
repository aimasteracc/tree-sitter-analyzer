# V2 痛点快速参考 (Quick Reference)

**最后更新**: 2026-02-03

---

## 🚨 Critical (必须立即修复)

| ID | 痛点 | 状态 | 工作量 | 文件 |
|----|------|------|--------|------|
| #10 | search_content API 返回 0 结果（应该返回 11） | 🔄 新发现 | 2h | `search.py` |
| #11 | search_content 后台线程 UnicodeDecodeError (cp932) | 🔄 新发现 | 1h | `search.py` |

**总计**: 3 小时

---

## 🔥 High Priority (本周必做)

| ID | 痛点 | 状态 | 工作量 | 文件 |
|----|------|------|--------|------|
| #3 | Markdown 表格嵌套混乱 | 🔄 计划中 | 3h | `formatters/markdown_formatter.py` |
| #4 | 缺少 --summary 快速模式 | 🔄 计划中 | 2h | `cli/main.py` |
| #6 | Code Graph 输出节点太多 | 🔄 计划中 | 2h | `graph/export.py` |
| #14 | Code Graph 缺少查询和过滤能力 | 🔄 新发现 | 4h | `graph/` (新建 query.py) |

**总计**: 11 小时

---

## 🟡 Medium Priority (下周实现)

| ID | 痛点 | 状态 | 工作量 | 文件 |
|----|------|------|--------|------|
| #8 | 缺少文件搜索集成测试 | 🔄 计划中 | 2h | `tests/` |
| #9 | API 文档与实现不一致 (extract_code_section) | 🔄 新发现 | 1h | `api/interface.py` or docs |
| #13 | 缺少批量分析功能 | 🔄 新发现 | 3h | `cli/main.py`, `api/interface.py` |

**总计**: 6 小时

---

## 🟢 Low Priority (长期优化)

| ID | 痛点 | 状态 | 工作量 | 文件 |
|----|------|------|--------|------|
| #5 | Windows 控制台 emoji 不支持 | 🔄 计划中 | 1h | `cli/main.py` |
| #7 | 缺少增量分析 | 🔄 计划中 | 8h | `graph/incremental.py` |
| #12 | MCP 服务器类名不一致 | 🔄 新发现 | 0.5h | `mcp/server.py` or docs |

**总计**: 9.5 小时

---

## ✅ 已解决

| ID | 痛点 | 解决时间 | 文件 |
|----|------|----------|------|
| #1 | 编码检测缺失 | 2026-02-02 | `cli/main.py` |
| #2 | CLI 命令过长 | 2026-02-02 | `pyproject.toml` |

---

## 📊 工作量统计

| 优先级 | 任务数 | 总工作量 |
|--------|--------|----------|
| 🚨 Critical | 2 | 3h |
| 🔥 High | 4 | 11h |
| 🟡 Medium | 3 | 6h |
| 🟢 Low | 3 | 9.5h |
| **总计** | **12** | **29.5h** |

---

## 🎯 本周计划 (Week 1)

### 今日必做 (2-3h)
1. [ ] #10: 修复 search_content API (2h)
2. [ ] #11: 修复编码错误 (1h)

### 本周剩余 (6-8h)
3. [ ] #4: 实现 --summary 模式 (2h)
4. [ ] #3: 优化 Markdown 格式 (3h)
5. [ ] #14: Code Graph 查询能力 (4h) - 部分实现

**本周总计**: 9-11 小时

---

## 🚀 下周计划 (Week 2)

### 必做任务 (8-10h)
1. [ ] #14: 完成 Code Graph 查询能力 (剩余部分)
2. [ ] #6: Code Graph 过滤功能 (2h)
3. [ ] #13: 批量分析功能 (3h)
4. [ ] #9: API 文档一致性 (1h)
5. [ ] #8: 文件搜索测试 (2h)

**下周总计**: 8-10 小时

---

## 📋 快速查找索引

### 按文件分组

#### `cli/main.py`
- #4: --summary 模式
- #5: emoji 支持
- #13: 批量分析

#### `api/interface.py`
- #9: extract_code_section
- #13: analyze_files() 方法

#### `search.py`
- #10: search_content 返回 0 结果
- #11: UnicodeDecodeError

#### `formatters/markdown_formatter.py`
- #3: 表格嵌套问题

#### `graph/export.py`
- #6: 节点过滤

#### `graph/` (新建 query.py)
- #14: 查询和过滤 API

#### `mcp/server.py`
- #12: 类名统一

#### `tests/`
- #8: 文件搜索测试

---

## 🔍 痛点详情链接

完整描述见: `.kiro/specs/v2-complete-rewrite/PAINPOINTS_TRACKER.md`

会话记录见: `.kiro/specs/v2-complete-rewrite/SESSION_20_REAL_USE_DISCOVERY.md`

---

## 📈 修复进度追踪

```
总痛点: 14 个
已解决: 2 个 (14%)
进行中: 0 个
待处理: 12 个 (86%)

Critical: 2 个 (需立即修复)
High: 4 个 (本周必做)
Medium: 3 个 (下周实现)
Low: 3 个 (长期优化)
```

---

## 🎯 成功指标

### 本周目标
- [ ] 所有 Critical 问题解决 (2/2)
- [ ] 至少 2 个 High 问题解决 (2/4)
- [ ] V2 日常使用无阻碍

### 本月目标
- [ ] 所有 High 问题解决 (4/4)
- [ ] 所有 Medium 问题解决 (3/3)
- [ ] 痛点总数 < 5 个

### 长期目标
- [ ] 所有已知痛点解决
- [ ] 使用 V2 成为日常习惯
- [ ] 每周发现 < 1 个新痛点

---

**使用方法**:
- 开始工作前：查看"本周计划"
- 修复痛点后：更新状态为 ✅
- 发现新痛点：添加到 PAINPOINTS_TRACKER.md，然后更新此文件
- 每周回顾：检查进度，调整优先级
