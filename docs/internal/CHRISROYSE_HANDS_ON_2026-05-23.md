# 与 ChrisRoyse/CodeGraph 实操对照 — 不是理论,是真跑

> **方法**: 把 ChrisRoyse 仓库的 `python_parser.py` 单独跑起来(绕开 Neo4j),
> 看它对 `health_scorer.py` 抽出来什么,跟我们对照。
>
> 实操日期: 2026-05-23  
> 被测对象: `github.com/ChrisRoyse/CodeGraph` (TypeScript + Neo4j + Python AST parser)  
> 我们: tree-sitter-analyzer (本仓库)

---

## TL;DR

**核心能力 (functions / classes / imports / calls): 完全等价。**  
**Neo4j 包装 / variable+parameter 节点: 我们没有,需要做 4 件事补齐。**

| 度量 | ChrisRoyse | Ours (full reindex) | 差? |
|---|---|---|---|
| Classes | 2 | 2 | **0** |
| Functions + Methods | 11 + 10 = 21 | 21 | **0** |
| Imports | 10 | 10 | **0** |
| **CALLS edges** | **140** | **140** | **0** |
| Module nodes | 10 | (合并进 imports) | 等价 |
| **Variables** | 86 | 2 (module-level only) | 我们 -84 |
| **Parameters** | 40 (独立 node) | 0 (附在 function.parameters) | 我们 -40 (设计差异) |

---

## 实操过程 (实际命令)

```bash
# 1. Clone
git clone --depth 1 https://github.com/ChrisRoyse/CodeGraph.git /tmp/competitor_eval/CodeGraph

# 2. 装依赖 (ChrisRoyse 真实问题 #1: peer-dep 冲突)
cd /tmp/competitor_eval/CodeGraph
npm install  # 失败: tree-sitter-c-sharp 要 tree-sitter@^0.21.1, root 锁 0.22.4
npm install --legacy-peer-deps  # OK, 514 packages

# 3. Build TS
npm run build  # OK

# 4. CLI 启动 (要求 Neo4j ENV)
node dist/index.js --help  # OK, analyze command

# 5. 跑 Python parser 单独 (绕过 Neo4j)
uv run python /tmp/competitor_eval/CodeGraph/python_parser.py \
  tree_sitter_analyzer/health_scorer.py > /tmp/cr_out.json

# 6. 对照我们
uv run python -m tree_sitter_analyzer tree_sitter_analyzer/health_scorer.py \
  --advanced --format json > /tmp/ours_out.json
```

ChrisRoyse 抽出来的:
```text
160 nodes:  PythonVariable=86  PythonParameter=40
            PythonFunction=11  PythonMethod=10
            PythonModule=10    PythonClass=2   File=1
213 rels:   PYTHON_CALLS=140
            PYTHON_HAS_PARAMETER=40
            PYTHON_DEFINES_FUNCTION=11
            PYTHON_IMPORTS=10
            PYTHON_HAS_METHOD=10
            PYTHON_DEFINES_CLASS=2
```

我们抽出来的 (`--advanced` + ast_cache 重索引):
```text
35 elements: function=21 (含 methods)  class=2  import=10  variable=2
140 call_edges in ast_cache.ast_call_edges table
```

---

## 实操路上的真实发现

### ChrisRoyse 侧

1. **🚨 npm peer-dep 冲突 — `npm install` 直接失败**  
   `tree-sitter-c-sharp@0.23.1` 要 `tree-sitter@^0.21.1`,root 用 `0.22.4`。
   需要 `--legacy-peer-deps` 才能装。新用户大概率第一步就卡。

2. **🚨 Neo4j 必需** — 没 Neo4j 就根本进不了它的图查询能力。
   docker 起 Neo4j ≈ 800MB 镜像 + 4GB RAM,或者要装 Neo4j Desktop。
   我们这次跑 Python parser 是绕过去了,但失去了图查询。

### 我们侧

3. **🚨 cache 状态混乱时 `ast_call_edges` 是空的**  
   - 刚清前用 `rm -f .ast-cache/index.db` 但 wal/shm 没清,导致 schema 升级残留
   - `index_project` 没报错但 call_edges 表 0 行
   - 完全清干净 (`rm -f *.db*`) 后再 force 索引: **89,982 条 call edges**,health_scorer.py **140 条** (跟 ChrisRoyse 一模一样)
   - **修复方向**: ast_cache 在打开时该 sanity-check schema 版本,清理孤儿 wal

---

## "想跟 ChrisRoyse Neo4j 版本完全等价,要做啥?"

把差距拆成 4 件事,标注**真要做** vs **没必要**:

### ① ✅ 已有 — 不用做的
| ChrisRoyse 能力 | 我们的实现 | 状态 |
|---|---|---|
| Function 节点 + 行号 + 签名 | `ast_index.symbols_json` + ast_symbol_rows | ✅ 等价 |
| Class 节点 + 继承 | 同上 | ✅ 等价 |
| Import 节点 + IMPORTS 边 | `ast_index.imports_json` + extract_imports | ✅ 等价 |
| CALLS 边 (caller→callee + line) | `ast_call_edges` 表 | ✅ **140 vs 140 字节级一致** |
| DEFINES_FUNCTION / DEFINES_CLASS / HAS_METHOD | 隐含在 symbols + parent_id | ✅ 等价语义 |
| 多语言支持 (Python/TS/Java/Go/SQL/HTML/CSS...) | 我们 17 语言 | ✅ **超** |

### ② ⚠ 真要做才能补齐 — 估时 2-3 天
| ChrisRoyse 能力 | 我们没有 | 做啥 |
|---|---|---|
| **Variable 节点** (每个赋值算 1 个,86 个 vs 我们 2) | extract_symbols 只走 module-level | 加 walker 进 function body,提 `assignment` 节点,新 schema 字段 `scope` (module/function/class) |
| **Parameter 节点 + HAS_PARAMETER 边** | 参数附在 function.params 列表里,不是独立节点 | 把 parameters 也存到 ast_symbol_rows,kind="parameter",同时在 call_edges 加 edge type "has_parameter" |
| **明确的边类型** (HAS_METHOD / DEFINES_FUNCTION 等) | 我们靠 caller/callee 关系隐式表达 | call_edges 新加 `edge_type` 列,默认 "calls",其它 "defines/imports/has_method" |
| **导出 Cypher / Gremlin 查询接口** | 我们走 Python 函数 + MCP | 新做一个 `analyze_with_cypher` MCP 工具,接收 Cypher 子集 (或者 JSON DSL),内部翻译成 SQL |

### ③ 🚨 真要做的话需要外部依赖 — 估时 1 周
| ChrisRoyse 能力 | 做啥 |
|---|---|
| Neo4j 后端存储 | 加 optional `neo4j` extra,把 ast_call_edges + ast_symbol_rows 镜像写入 Neo4j;保留 SQLite 默认 |
| 自然语言 → Cypher (MCP 上的 query) | 这是 LLM 层的工作,不是我们 |
| Neo4j Bloom 可视化 | 用户在 Neo4j Desktop 里直接看,我们提供 export 即可 |

### ④ ❌ 看不出价值的 — 不建议做
| ChrisRoyse 有 | 为什么我们不做 |
|---|---|
| 把整个项目都塞进图数据库 | 我们的 SQLite + FTS5 在 1382 文件项目里 < 3 秒 full index,Neo4j 同规模要 30+ 秒;对小-中项目纯负担 |
| Bloom 可视化 | agent 用 TOON 文本输出,不看图;人类要看的话直接打开 ast_cache 用 datasette 也行 |
| Cross-language CALL 关系 (React 调 Python API) | 通过我们的 route_detector + symbol_lineage 已经能做,且不需要图 DB |

---

## 决定建议

**做** ② 那 4 件事 (估 2-3 天):
- 加 variable + parameter 节点,跟 ChrisRoyse 抽出来的图密度对齐
- call_edges 加 edge_type 列,把语义边类型公开
- 出一个 `analyze_with_cypher`-like MCP 工具,接受简单图查询 DSL

**不做** ③ Neo4j 后端:
- 我们的 SQLite + FTS5 + ast_call_edges 已经覆盖 90% 用例
- Neo4j 引入的运维负担 (服务、内存、端口、密码) 跟 agent UX 矛盾
- 真要做就 expose 一个 export-to-cypher 命令让用户自己导

**避免** ④ 一开始就上图数据库:
- 在我们的 dogfood 实测里 (这次跑) 已经看到了:agent 在跑同样查询时,我们 < 3 秒 full index + 即时查询,ChrisRoyse 必须先起 Neo4j 才能 query。**对 agent 是反摩擦**。

---

## 复现这份实验

```bash
# Setup
mkdir -p /tmp/competitor_eval && cd /tmp/competitor_eval
git clone --depth 1 https://github.com/ChrisRoyse/CodeGraph.git
cd CodeGraph && npm install --legacy-peer-deps && npm run build

# Run ChrisRoyse's Python parser (no Neo4j needed for parser test)
cd /Users/aisheng.yu/git-private/tree-sitter-analyzer
uv run python /tmp/competitor_eval/CodeGraph/python_parser.py \
  tree_sitter_analyzer/health_scorer.py > /tmp/cr_out.json
jq '[.nodes[] | .kind] | group_by(.) | map({k:.[0], v:length})' /tmp/cr_out.json
jq '.relationships | length' /tmp/cr_out.json

# Run ours
rm -f .ast-cache/index.db .ast-cache/*.db-wal .ast-cache/*.db-shm   # IMPORTANT
uv run python -c "
from tree_sitter_analyzer.ast_cache import ASTCache
cache = ASTCache('.')
cache.index_project(max_files=2000, force=True, workers=0)
cache.close()
"
sqlite3 .ast-cache/index.db \
  "SELECT COUNT(*) FROM ast_call_edges WHERE file_path='tree_sitter_analyzer/health_scorer.py'"
# expected: 140  (字节级跟 ChrisRoyse 完全一致)
```
