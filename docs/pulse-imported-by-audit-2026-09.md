# Pulse `imported_by` 链路审计报告（2026-09-11）

> 审计方式：全部结论基于对以下文件的逐行亲读（本会话），非摘要转述。
> 覆盖：解析 → 索引 → SQL → API → 裁剪 → 序列化 → MCP 全链路。
> 关联文档：根目录 `VALUE_AUDIT.md`（2026-09-05 价值体检）。

## 总裁决

链路本身一致、无阻断性缺陷：`imported_by` 在每一层的语义稳定为
「导入目标符号所在文件的模块路径列表」（文件级反向依赖），测试覆盖了核心语义
（named/parent/multi-importer/JS→TS 交叉导入/防假边）。

但审计发现 **6 个此前未记录的真问题**（含 1 个产品级语义缺口、1 个失败粒度
设计问题）和 **4 个低风险异味**。问题按严重度排列如下。

---

## 问题清单

### P1-1 `imported_by` 语言覆盖不一致，且无失败信号

- **位置**：`tree_sitter_analyzer/synapse_resolver/languages/`（交叉验证）、
  `tree_sitter_analyzer/api/_pulse_sql.py:49-58`
- **证据**：synapse 侧只有 Python（`_imports.py`）和 TS/JS
  （`_typescript_imports.py`）产生 `kind='imports'` 边；Go/Rust/Java/C# 等
  语言的 resolver 只做调用解析（返回 `(symbol_id, resolution, resolved_file)`
  级联），不产出 import 边。
- **失败模式**：这些语言的 Pulse `imported_by` 恒为空元组（静默）。而同一
  MCP 服务器里 `smart_context` 的 `imported_by_count/sample` 来自
  `project_graph.DependencyGraph`（`smart_context_tool.py:19`），后者支持
  go/rust/c/cpp/java。两个工具对「谁依赖这个文件」给出不同答案，agent 无从
  分辨「没人导入」与「该语言不支持」。
- **对比**：`call_graph` 对不支持语言有 `call_graph_available=false` +
  `call_graph_reason` 显式标记（`pulse.py:219-222`）；`imported_by` 没有对应
  机制。
- **建议**：为 `imported_by` 增加等价的可用性标记（如
  `imports_graph_available`），或在 `get_project_schema` 的
  `available_pulse_fields` 中按语言声明差异。

### P1-2 大型 Python 仓库中整个 Pulse 端点失败（失败粒度问题）

- **位置**：`tree_sitter_analyzer/api/pulse.py:294-295`
- **证据**：Python 符号查询时，若索引文件数 >10000 或 import 绑定 >20000，
  `raise ValueError("PULSE_IMPORT_RESOURCE_LIMIT")`。
- **失败模式**：异常被 `pulse_tool.py` 的 `except Exception` 捕获，整个请求
  返回 `success: False`——**一个可选字段（imported_by 的 Python 富化）拖死
  全部上下文**（callers/callees/git_heat 等本可正常返回）。
- **备注**：`tests/unit/api/test_pulse.py:761`
  （`test_query_pulse_import_capacity_is_an_error`）固化了该行为，说明是
  有意的资源守卫；争议点在失败粒度，不在守卫本身。
- **建议**：超限时降级为「跳过 Python 富化 + `truncated_fields` 记录
  `imported_by`」，而非整体报错。

### P2-1 `_estimate_tokens` 异常捕获过窄，且测试名与覆盖不符

- **位置**：`tree_sitter_analyzer/api/pulse.py:360-368`；
  `tests/unit/api/test_pulse.py:289-313`
- **证据**：只捕获 `ImportError`。tiktoken 已安装但 BPE 缓存冷 + 无网络时，
  `tiktoken.get_encoding("cl100k_base")` 抛网络异常（非 ImportError）→ 整个
  pulse 崩溃。tiktoken 是可选依赖（`pyproject.toml:475` 附近，
  mypy optional overrides），常见安装走 ImportError 回退，触发窗口窄但存在。
- **测试缺口**：`test_budget_uses_optional_tokenizer_without_network` 名字含
  "without_network"，实际只注入了**正常工作的**假 tiktoken
  （`monkeypatch.setitem(sys.modules, "tiktoken", SimpleNamespace(...))`），
  恰恰没有覆盖「tiktoken 在但初始化失败」分支——测试名与测试内容不符。
- **建议**：`except ImportError` 改为同时捕获初始化异常（或预检编码可用性），
  并补一个「tiktoken 抛运行时异常 → 回退字符估算」的测试。

### P2-2 每次 Python Pulse 查询全量拉取约 30k 行，无缓存

- **位置**：`tree_sitter_analyzer/api/pulse.py:286-293`
- **证据**：每次 `query_pulse` 都执行两条 SELECT（≤10001 文件 + ≤20001 绑定），
  在 Python 侧 O(N) 解析模块映射，无连接级缓存。
- **失败模式**：`pulse_batch`（`pulse_tool.py:263-334`）逐符号调用 →
  大仓库上是 N × 30k 行的重复工作；快照内做纯只读计算，本可复用。
- **建议**：模块表/绑定表按连接缓存（invalidate on reindex），或把 Python
  富化下沉到索引期（与 TS 的 `callee_resolved_file` 策略对齐——TS 正是索引
  期解析、查询期零成本）。

### P3-1 `COMPACT_LEGEND` 缺 `at` 键的映射

- **位置**：`tree_sitter_analyzer/api/serialization.py:14-20`（legend）vs
  `:72`（compact 输出含 `"at": gh.at`）
- **失败模式**：legend 是注入 MCP 工具描述的唯一键名文档，agent 在输出中
  看到 `at` 无从知道它是 Unix 时间戳（秒）。
- **建议**：legend 补 `at=timestamp_seconds`。

### P3-2 数量预裁剪对下游不可见

- **位置**：`tree_sitter_analyzer/api/pulse.py:396-403`（`_FIELD_TOP_N`）、
  `api/_pulse_sql.py:57`（`LIMIT 20` 硬编码）、`pulse.py:311`（Python 路径
  `[:20]`）
- **失败模式**：`apply_budget` 先把 `imported_by` 20→5，SQL 再 LIMIT 20，但
  `truncated_fields` 只记录**整字段删除**。下游无法区分「本来就 5 个导入者」
  与「被裁到 5 个」——对用 imported_by 做影响面判断的 agent 是隐患。
- **建议**：字段内数量截断也写入 `truncated_fields`（如
  `imported_by[5/20]`），或输出原始计数。

### P3-3 死代码：`_FIELD_BUDGETS`

- **位置**：`tree_sitter_analyzer/api/pulse.py:386-394`
- **证据**：全仓 grep 仅此一处定义，零引用（apply_budget 只用
  `_FIELD_TOP_N` 和 `_PRIORITY_ORDER`）。
- **建议**：删除，或真正用于 per-field 预算控制（现名不符实）。

### P3-4 compact 视图缺 `call_graph_reason`

- **位置**：`tree_sitter_analyzer/api/serialization.py:86`（compact 无）vs
  `:141`（verbose 有）
- **失败模式**：`cg: false` 时默认视图（compact 是 MCP 默认 format）消费者
  看不到原因，只有 verbose 有。
- **建议**：compact 在 `call_graph_available=false` 时附带 `cg_reason` 短键。

---

## 架构观察：三套并行的 import 解析引擎

| 引擎 | 规模 | 语言 | 消费方 | 特点 |
|---|---|---|---|---|
| `import_graph.ImportGraph` | 502 行 | PY/JS | MCP `codegraph_import_graph` | 正则；支持 `require()`；只匹配相对路径 |
| `project_graph.DependencyGraph` | 803 行 | PY/JS/Go/Rust/C/C++/Java… | `smart_context`、项目级分析 | 每语言 resolver 注册表 |
| synapse + Pulse `imported_by` | 分散 | PY/TS-JS | MCP `pulse` | 索引期解析（TS）/查询期富化（PY）；edges 表 |

三套各自维护后缀解析顺序、相对路径语义、require 支持与否（差异均有
docstring 说明理由，属有意设计）。**这不是紧急问题**，但任何一处修改解析
语义（如新增后缀、支持 `exports` 字段）都需要同步三处，是长期的漂移风险
来源。收敛候选：以 `project_graph` 的注册表为唯一事实，其余两处复用。

## 已验证无恙的部分

- SQL `imported_by` CTE 的语言中立分支（`callee_resolved_file`）与 Python
  专属分支（`target_node_id = :module_node`）语义正确，防假边测试覆盖充分
  （bare specifier 不绑定项目文件、自导入不报告、无关导入者不报告）。
- `apply_budget` 裁剪顺序与 MCP 工具描述**逐字一致**
  （comments→siblings→imported_by→imports→git_heat→callees→callers）。
- `pulse_tool` 走 `certified_pulse_connection`（源码证据认证）→
  `query_pulse` → `apply_budget` → `serialize`，与 API 层无漂移。
- 测试回归：66 passed（resolver 2 文件 + imported_by API 1 文件，
  2026-09-11 实测）。

## 测试覆盖缺口

1. tiktoken 安装但初始化失败 → 回退路径（见 P2-1）。
2. 超资源上限时的**降级**语义（现在只测了报错，见 P1-2）。
3. 非 PY/TS-JS语言的 `imported_by` 空值契约（现在无测试声明这是预期行为，
   见 P1-1）。
4. `truncated_fields` 对字段内截断的可见性（见 P3-2）。

## 处置建议

- 本文档记录问题清单；P1-1 / P1-2 建议开 GitHub issue 跟踪（含本文档链接）。
- 修复优先级：P1-2（改动最小、收益直接）→ P1-1（需设计标记机制）→
  P2-1/P2-2 → P3 系列（可顺手修）。
- 三引擎收敛为独立重构议题，不与本轮修复混合。
