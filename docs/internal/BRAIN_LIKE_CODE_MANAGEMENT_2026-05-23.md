# 能不能像大脑神经/血液那样管理代码?

> 实操答案: **substrate 已经搭了 70%, 但 4 个关键 bio-property 还差着。**
>
> 这文档不画饼,把我们现状跟大脑/血液系统逐项对照,告诉你哪些已有、哪些
> 差,以及差的那些每一项要做多少工作。

实验日期: 2026-05-23

---

## 当前你的项目作为"神经网络"的真实快照

(全部从 ``ast_call_edges`` + ``ast_symbol_rows`` 直接查出来,没虚构)

| 神经科学概念 | 对应代码层 | 当前数字 | 状态 |
|---|---|---|---|
| neurons (神经元) | functions | **22,554** | ✅ |
| neuron clusters (神经核团) | classes | **3,717** | ✅ |
| synapses (突触) | call edges | **89,982** | ✅ |
| hub regions | 高入度 functions | top1 `len` 被调 2478× | ✅ |
| sensory neurons (入口) | 0 入度 functions | 18,527 | ⚠ 数太多,真入口被淹没 |
| pruned neurons (退化) | 0 进 + 0 出 | 974 dead | ✅ (有 dead_code_tool) |
| cross-region pathways | cross-file edges | **0 (0%)** 🚨 | **🚨 这是最大的 bio gap** |
| Hebbian co-fire | git co-changes | 已有 `score_git_hotspot` | ✅ |

---

## 🚨 最大的 bio-property gap: cross-file 突触 = 0

大脑里大约 **1/3 的突触跨脑区** (corpus callosum / association fibers)。
我们的 89,982 条 call edges,**100% 是 intra-file** — 因为 callee 存的是字符串
名 (`Path`, `len`, `tool.execute`),没解析到具体的 (file, line, function_id)。

具体例子: `health_scorer.score_file` 调用 `Path(...)`,我们记的是:
```
caller=score_file  caller_file=health_scorer.py
callee=Path  (字符串,没说是 pathlib.Path 还是项目里某个 Path)
```

后果: agent 问 "改 X 函数会影响谁?" 时,我们只能 grep 字符串 — 不能精确告诉
他 "你改的 Path 是 pathlib 的,所以本项目的 800 个 Path 调用其实都不受影响"。

**这是大脑能做、我们暂时不能的核心区别。**

---

## 跟大脑/血液系统的逐项对照

### A. 已有 / 等价 (10 项)

| Bio 特性 | 我们怎么做 | 工具/字段 |
|---|---|---|
| neuron (节点) | functions/classes | `ast_symbol_rows` |
| dendritic input | 入度 | `codegraph_callers` |
| axonal output | 出度 | `codegraph_callees` |
| pruning (突触修剪) | dead code detection | `codegraph_dead_code` |
| inhibition (抑制) | safe_to_edit / change_impact guard | verdict=CAUTION/UNSAFE |
| activation strength | call frequency (静态) | edge count |
| hub regions | high in-degree | `codegraph_overview.hub_functions` |
| Hebbian "fire together" | git co-change | `health_scorer.score_git_hotspot` |
| plasticity (重塑) | incremental re-index | `ast_cache --mode index` |
| myelination (高速通道) | hot path caching | `_health_score_cache` + ast_cache |

### B. 部分 — 差距明确,可补 (4 项)

| Bio 特性 | 现状 | 要做啥 | 估时 |
|---|---|---|---|
| **cross-region synapses** | callee 只存字符串 | callee resolution: 写边时 join 到 ast_symbol_rows.id;加 `callee_symbol_id` 列;import 路径 + scope chain 解析 | **5-7 天** (核心改进) |
| **temporal activation** (神经元最近被激活的频率) | 只有静态边 | 加 runtime instrumentation hook;或者从 git log 派生 "function modified frequency" | 3 天 (静态版) / 1 周 (运行时) |
| **inhibitory edges** (X 必须不调 Y) | 没有 | 加 architectural-constraint DSL:`forbid: tree_sitter_analyzer → tests/`;违反时 verdict=UNSAFE | 2 天 |
| **homeostasis loop** (自动纠偏) | 没有 | 一个 daemon:periodic 跑 health,grade 下降到阈值就 fire 通知 / 提建议;类似 `--watch` 但目标是健康度 | 4 天 |

### C. 没必要做的 bio 类比 (3 项)

| Bio 特性 | 为什么不做 |
|---|---|
| neurogenesis (新增神经元) | 等价于"自动生成代码",这是 LLM 的工作,不是 analyzer 的 |
| 血脑屏障 (blood-brain barrier) | 等价于 module 边界保护,Python 的 `__all__` + import system 已经覆盖 |
| 神经递质多样性 (GABA/dopamine/serotonin) | edge_type 区分 (calls/imports/extends) 已经够用,过度细分增加 schema 复杂度 |

---

## 4 件事的具体实现路径

### ① cross-region 突触 (callee resolution) — 最重要

```python
# 当前 _extract_call_edges 写边时:
{
    "caller_name": "score_file",
    "callee_name": "Path",           # ← 字符串
    "callee_full": "",               # ← 空
}

# 目标:写边时加一步解析
{
    "caller_name": "score_file",
    "caller_symbol_id": 12834,       # ast_symbol_rows.id
    "callee_name": "Path",
    "callee_symbol_id": None,        # 解析不到时空,但 *尝试* 解析
    "callee_resolution": "pathlib.Path",  # stdlib / 项目内 / unknown
    "callee_file": "<stdlib:pathlib>",
}
```

**实现要点**:
- 用 imports 表 (我们已有) 反查 namespace
- 例如:`from pathlib import Path` → `Path` in this file = `pathlib.Path`
- `from ..health_scorer import HealthScorer` → caller 文件里 HealthScorer = 我们项目里某个 row
- stdlib 的边可以打 tag,不必入图

**触发收益**:
- agent 问 "改本项目的 Path 会影响谁" → 答案精确,不再 800 个误报
- cross-file `change_impact` 准确度大幅提升
- 满足 Hebbian "fire together wire together" 的真正语义

### ② temporal activation (静态版)

```sql
ALTER TABLE ast_symbol_rows ADD COLUMN last_modified_commit TEXT;
ALTER TABLE ast_symbol_rows ADD COLUMN modification_frequency INT DEFAULT 0;

-- index 时调 git log --follow file_path → 提取每个 symbol 涉及的 commit 数
```

最近 30 天被改 10 次 = "hot neuron",agent 在那一带的修改风险预判会更准。

### ③ inhibitory edges (架构约束)

```yaml
# architectural_constraints.yml
forbid:
  - from: tree_sitter_analyzer/mcp/
    to:   tree_sitter_analyzer/cli/
    reason: "MCP must not depend on CLI; reverse only"
  - from: tests/
    to:   /tmp/
    reason: "PR-trap fix 已经 lint 过的;持久化为图边"
```

在 ast_call_edges 旁边加 `ast_forbidden_edges`,`safe_to_edit` 看到违反就 verdict=UNSAFE。

### ④ homeostasis loop

```bash
tree-sitter-analyzer --watch-health \
  --threshold-grade C \
  --on-degradation 'echo "{file} grade dropped to {grade}: {recommendation}"'
```

Daemon 每 N 分钟跑一次 health,grade 下降就触发动作。我们已经有 `--watch` 给
ast_cache,把同样基建复用给 health。

---

## 如果只能做一件事,做哪个?

**做 ①** — callee resolution,5-7 天投入,价值最大:
- 解锁了真正的 "cross-region" 神经网络结构
- 改 1 个函数,精确知道项目内 [exact list] 个调用点会被影响
- 跟 Neo4j 派的工具能力对齐,但不需要 Neo4j 服务

② ③ ④ 都建立在 ① 之上,先把 ① 做了,后面是同一个 schema 的扩展。

---

## 复现 "项目的神经网络快照"

任何时候你都能跑这个看现状:

```bash
# Prereq: 索引干净
rm -f .ast-cache/*.db*
uv run python -c "
from tree_sitter_analyzer.ast_cache import ASTCache
c = ASTCache('.')
c.index_project(force=True, workers=0)
c.close()
"

# Snapshot
sqlite3 .ast-cache/index.db << 'SQL'
.headers on
.mode column
SELECT 'functions' AS metric, COUNT(*) AS n FROM ast_symbol_rows WHERE kind='function'
UNION ALL SELECT 'classes',         COUNT(*) FROM ast_symbol_rows WHERE kind='class'
UNION ALL SELECT 'call edges',      COUNT(*) FROM ast_call_edges
UNION ALL SELECT 'cross-file edges',COUNT(*) FROM ast_call_edges WHERE caller_file != file_path;
SQL

# Top 10 hub neurons
sqlite3 .ast-cache/index.db \
  "SELECT callee_name, COUNT(DISTINCT caller_name) AS in_degree
   FROM ast_call_edges GROUP BY callee_name
   ORDER BY in_degree DESC LIMIT 10"

# Dead neurons (potential)
sqlite3 .ast-cache/index.db \
  "SELECT COUNT(*) FROM ast_symbol_rows
   WHERE kind='function'
     AND name NOT IN (SELECT DISTINCT callee_name FROM ast_call_edges)
     AND name NOT IN (SELECT DISTINCT caller_name FROM ast_call_edges)"
```
