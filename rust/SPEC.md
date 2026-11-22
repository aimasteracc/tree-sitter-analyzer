# SPEC — tree-sitter-analyzer Rust 改写（Stage 0 规格）

- 基线：aimasteracc/tree-sitter-analyzer **v3.1.2**（commit `f95da6035a1191add763d254aa36313037dbabe3`，tag `v3.1.2`，`tree_sitter_analyzer/__init__.py` `__version__ == "3.1.2"`）
- 工具：aimasteracc/rust-anything @ `8ac2c1c8ab77bd1a20588f0c03f0a72ab99a046e`（= 上游 erkamyaman/rust-anything main，MIT；已通过第三方只读安检，见 `/workspace/oss-review/reports/rust-anything.md`）
- 分支：`feature/rust-anything-rewrite`（从 `origin/main` @ `f95da603` 开出）。**所有改写产物只放 `rust/` 目录**；不修改任何 Python 源码、`tests/`、`pyproject.toml`、`.github/`
- 本文每条契约均已在基线源码中核实；来源路径随条目标注

---

## 1. 目标、基线冻结与范围边界

### 1.1 目标

用 rust-anything 的「先录音、后改写、逐步对照」方法，把 tree-sitter-analyzer（以下简称 TSA）的核心对外行为改写为 Rust，并在每一个单元上以 **v3.1.2 真实输出的规范化 JSON** 为黄金对照关门。第一阶段只追求**行为兼容**，不改变发行形态：Python 3.1.x 仍是唯一正式 PyPI 包。

### 1.2 基线冻结

| 项 | 值 | 来源 |
|---|---|---|
| TSA 版本 / 提交 | 3.1.2 / `f95da603`（= tag `v3.1.2`） | `git log`、`pyproject.toml` |
| 工作分支 | `feature/rust-anything-rewrite`（自 `origin/main` 开出） | `git branch` |
| 黄金来源 | PyPI `tree-sitter-analyzer==3.1.2`（隔离 venv 安装，非本地源码运行） | 见 §5.1 |
| 依赖解析（PyPI v3.1.2 约束下） | `tree-sitter>=0.26.0` → **0.26.1**；`tree-sitter-python>=0.23.6,<0.25.0` → **0.23.6** | `pyproject.toml` L56/L62 + PyPI 版本表（0.23.6 为 <0.25.0 的最新版；tree-sitter PyPI 最新即 0.26.1） |
| rust-anything 侧 grammar | `tree-sitter` **0.27.2**、`tree-sitter-python` **0.25.0** | rust-anything `Cargo.lock` / `Cargo.toml` |

基线冻结后不再跟随 TSA 上游演进；若日后重定基线，必须重录全部 fixtures 并更新本规格。

### 1.3 第一批核心范围（只限这 3 块）

**(a) JSON envelope**
- MCP `ToolResponse` 契约与工厂：`mcp/tools/tool_response.py`、`mcp/tools/_response_builder.py`
- CLI envelope 契约：`tests/unit/cli/test_cli_envelope_contract.py` 的 `_CLI_ENVELOPE_KEYS`（只读引用，不改测试）
- 错误信封规范化：`mcp/server_utils/error_recovery.py`（error_type 分类、K12 路径回显归一化、M14 language 回显）

**(b) MCP facade 分发**
- `mcp/facade_map.py`：`FACADE_NAMES`（8）、`SET_PROJECT_PATH_TOOL_NAME`、`REMOVED_TOOL_NAMES`（5）、`LEGACY_TOOL_MAP`（62）、`NEW_ACTION_PARITY`（21）
- `mcp/_tool_registry.py`：facade 注册顺序（`_FACADE_REGISTRATIONS`，search/index 接受 lifecycle_manager）
- `mcp/tools/facade_tool.py`：`FacadeTool.execute` 分发序、参数校验/投影（F4）、符号别名（R3）、`action=help`、difflib 拼写建议、`INVALID_ARGUMENT` 错误信封

**(c) Python 单语言插件**
- `languages/python_plugin/plugin.py`（PythonPlugin）+ `extractor.py`（PythonElementExtractor 及各 mixin）
- 对照 `tests/golden/corpus_python.py` + `tests/golden/corpus_python_expected.json` 的 AST 节点计数与元素抽取

### 1.4 明确排除出第一批

- embeddings 全部路径（含 **OpenAI** 出网花钱路径）；本地 HuggingFace 路径也不进第一批
- 其余 **21 个语言插件**（TSA 共 22 个插件 entry points；第一批只做 Python）
- `call_graph` / `health` / `edit` 的**执行体**（facade 分发层要能路由它们的名字与 action，但不实现其内部逻辑）
- 任何 **PyPI 替换 / 双发**：不改 `pyproject.toml`、不动 `upload_to_pypi.py`、不新建 Rust 包发布
- index / 缓存 / 文件监视 / LSP / knowledge graph / CLI 全部子命令的 Rust 实现（CLI 只锁定 envelope 形状）

---

## 2. 兼容契约细则

### 2.1 JSON envelope

**Canonical verdicts（8 个，`frozenset`，两处定义必须一致）**
来源：`tool_response.py` `CANONICAL_VERDICTS` 与 `_response_builder.py` `CANONICAL_VERDICTS`（后者刻意不 import 前者以保持 leaf 地位）

```
SAFE, REVIEW, CAUTION, UNSAFE, INFO, WARN, ERROR, NOT_FOUND
```

**工厂函数**（`_response_builder.py`；全部 keyword-only，返回 JSON 可序列化 dict）

| 函数 | 签名要点 | 输出形状 |
|---|---|---|
| `build_response` | `(*, verdict, success=True, warnings=None, **fields)`；verdict 不在 canonical 集合立即 raise `InvalidVerdictError(ValueError)`，消息含非法值与 `sorted(CANONICAL_VERDICTS)` | `{"success", "verdict", **fields}` + 非空时追加 `"warnings"`（拷贝为 list） |
| `build_error` | `(*, error, verdict="ERROR", **fields)` | `{"success": False, "verdict", "error", **fields}` |
| `build_error_response` | `(tool_name, error, verdict="ERROR", **fields)` | 同上 + `"tool": tool_name` |
| `build_success_response` | `(tool_name, data, verdict="INFO", duration_ms=None, **fields)` | `{"success": True, "verdict", "tool", **data, **fields}` + 非空时 `"duration_ms"` |
| `build_agent_summary` | `(verdict, message, recommendations=None, **fields)` | `{"success": True, "verdict", "message", **fields}` + 非空时 `"recommendations"` |

`InvalidVerdictError` 继承 `ValueError`（`except ValueError` 的调用方能捕获）。

**`validate_tool_response` / `envelope_violations`（`tool_response.py`）**
- `validate_tool_response(payload, tool_name)`：payload 必须 dict；`success` 必须存在且为 bool；`success=False` 时必须有无 `error: str`；`verdict` 存在时必须是 canonical。违规 raise `AssertionError`（仅 pytest 合法调用）
- `envelope_violations(payload, tool_name)`：返回 `(rule, message)` 列表，**不抛异常**；空列表 = 合规

**ENVELOPE_RULES（11 条规则名，`frozenset`）**

| # | 规则 | 判据 |
|---|---|---|
| 1 | `base` | `validate_tool_response` 通过 |
| 2 | `agent-summary-shape` | `agent_summary` 存在时必须是 dict |
| 3 | `verdict-canonical` | `agent_summary.verdict`（剔除 `"n/a"`/空）必须在 canonical 集合 |
| 4 | `verdict-mirror` | 顶层 `verdict` 与 `agent_summary.verdict` 同设时必须相等 |
| 5 | `failure-verdict` | `success=False` 时有效 verdict 必须 ∈ `FAILURE_VERDICTS = {ERROR, NOT_FOUND}` |
| 6 | `success-verdict` | `success=True` 时有效 verdict 不得为 `ERROR` |
| 7 | `error-code` | `success=False` 时必须有非空 str 的 `error_code` 或 `error_type` |
| 8 | `completeness-status` | `completeness` ∈ `COMPLETENESS_STATUSES = {complete, incomplete, unknown}` |
| 9 | `completeness-reasons` | `complete` 不得带 reasons；非 `complete` 必须至少 1 个 reason；`completeness_reason` 存在时必须等于 `completeness_reasons[0]` |
| 10 | `completeness-reason-code` | reason code 必须来自已知闭集（`COMPLETENESS_REASONS | UQL_REASONS | INDEX_COMPLETENESS_REASONS`；UQL 允许 `<stage>:<CODE>` 前缀，取 `:` 后段校验） |
| 11 | `truncation` | `truncated` / `skipped_files_truncated` 存在时必须 bool；`TRUNCATION_COUNT_PAIRS = (total_count, returned_count), (total_matches, returned_matches), (caller_count, callers_listed)`：listed ≤ total，且 listed < total 时不得 `truncated: False` |

**CLI envelope 契约**（`tests/unit/cli/test_cli_envelope_contract.py`，5th permanent CI gate）
- `_CLI_ENVELOPE_KEYS = {"success", "summary_line", "verdict", "agent_summary"}`（4 键）；`_AGENT_SUMMARY_KEYS = {"summary_line", "verdict"}`
- happy path：`success is True`；`summary_line` 非空 str；`verdict` 非空 str；`agent_summary` 为 dict 且含 2 键；**顶层 `verdict` 必须镜像 `agent_summary.verdict`**（verdict-mirror 扩展到 CLI）
- 历史教训锁定：不得输出 `None` 字段、bare LIST、plain text

**error_recovery 规范化**（`mcp/server_utils/error_recovery.py`）
- 错误信封 canonical 键：`success(False)`, `error`, `error_type`, `verdict("ERROR")`, `agent_summary{summary_line, next_step, verdict}`, `summary_line`（顶层镜像）；兼容别名 `error_category = error_type`、`recovery_hint`；可选 `suggested_tool`；从 arguments 镜像标识字段（优先序 `file_path → symbol → query → roots[0] → mode`）
- `error_type` 分类（`_classify`，**消息文本优先于异常类**）：
  - 子串规则 15 条（按序首中即停）：`not found`/`no such file`→`file_not_found`；`unsupported language`→`language_unsupported`；`project root`→`project_not_set`（suggested_tool=`set_project_path`）；`outside project boundary`→`security_violation`；`blast_radius mode`→`validation`（须排在通用 `required` 前）；`required`/`must be`/`valid values:`→`validation`；`memory`→`resource_exhausted`；`timed out`→`timeout`；`regex parse error`→`subprocess`；`cache is empty`→`index_not_ready`（suggested_tool=`index`）；`syntax error`→`validation`；`permission denied`→`permission_denied`
  - 异常类回退表 `_EXC_CLASS_TO_TYPE`：`FileNotFoundError`/`NotADirectoryError`→`file_not_found`；`IsADirectoryError`/`ValueError`/`TypeError`/`KeyError`/`IndexError`→`validation`；`PermissionError`→`permission_denied`；`TimeoutError`→`timeout`；`AnalysisError`/`MCPError`/`RuntimeError`/`OSError`/`AttributeError`→`internal`
  - 最终兜底：`internal`
- **K12**：回显的 `file_path` / `source_file` 归一化 —— `\` → `/`，循环剥掉前导 `./`，使 `./X` 与 `X` 字节一致（`_normalize_path_string`）
- **M14**：单文件响应必须回显 `language: <detected>`（`detect_language_from_file`）；已非空则不覆盖；无 `file_path` 可探测则跳过；检测结果为 `unknown`/失败则不写键（保持 `language is None` 可分支）
- 三个入口：`build_agent_friendly_error(tool_name, error, arguments=…)`（工具抛异常时）、`ensure_canonical_error_envelope`（工具返回 `{success: False}` dict 时补全）、`ensure_canonical_success_envelope`（成功路径补 K12/M10/summary；M10 = verdict 顶层与 agent_summary 镜像，最终兜底 `agent_summary.verdict = "n/a"`）

### 2.2 MCP facade 分发

来源：`facade_map.py`、`_tool_registry.py`、`tools/facade_tool.py`

**公共表面 = 8 facades + 1 独立工具**

```python
SET_PROJECT_PATH_TOOL_NAME = "set_project_path"   # 非 facade、不进 LEGACY_TOOL_MAP（改 server 级状态）
FACADE_NAMES = ("search", "nav", "structure", "health", "edit", "project", "index", "viz")  # 顺序即 tools/list 注册序
```

注册序补充（`_tool_registry._FACADE_REGISTRATIONS`）：`search` 与 `index` 构造时接受 `lifecycle_manager`（`takes_lifecycle_manager=True`），其余 6 个不接受。

**REMOVED_TOOL_NAMES（5 个，无任何路由；破坏性删除，来源 CHANGELOG 1.30.0 / RFC-0033）**

```
search_content, find_and_grep, batch_search, list_files, check_tools
```

**LEGACY_TOOL_MAP（62 个旧名 → `(facade, action)`；按 facade 分组计数：search 3 / nav 13 / structure 8 / health 12 / edit 8 / project 9 / index 6 / viz 3）**

关键条目（Rust 侧必须逐一锁定）：
- `codegraph_call_graph → ("nav", "callers")`：R4 约定 —— call-graph 能力经 `nav.callers`/`nav.callees` 的 **`scope=graph`** 分支到达；legacy shim 转发到 callers scope=graph（`mode=callers` 是历史默认）
- `query_code → ("search", "query")`（tree-sitter .scm DSL）与 `codegraph_symbol_search → ("search", "symbol")`（BM25 FTS）是 **DISTINCT** actions，不得合并（F3 LOCKED）
- `get_project_summary → ("project", "card")`（RFC-0027 §L7 修复的无路由遗留名）

**NEW_ACTION_PARITY（21 个 `(facade, action, cli_flag)` 三元组；无 v1.x 遗留名、不触发弃用信封）**

`nav_test_map, nav_co_change, nav_pulse, nav_pulse_batch, edit_verify, edit_rename, edit_plan_rename, edit_mutation_probe, health_unreachable, health_middleware, health_self, health_refactor_queue, structure_signatures, index_knowledge, index_schema, viz_knowledge, search_tql_schema, search_tql_execute, search_semantic, search_text, search_uql`

**FacadeTool.execute 7 步分发序**（顺序不可变；响应永不重包装 verdict/agent_summary）

1. **action 校验**：`arguments["action"]` 缺失或非 str → `_action_error("missing required parameter 'action'")`
2. **`action == "help"`**：`build_help_response(facade_name, available_actions, full_description, action_map, bespoke_actions, arguments, target_action, bespoke_schemas)` —— 无 `target_action` 返回精简核心工作流（`agent-core/v1` 5 步：search.symbol → structure.outline → nav.pulse → edit.impact → edit.verify）；指定时从真实 inner schema 生成精确调用契约
3. **`output_format` 值校验**：已知 action 且传了 `output_format != "json"` → `_argument_value_error(action, "output_format", value, ["json"])`（`error_code: INVALID_ARGUMENT`）
4. **action-scoped 参数校验**：`_action_scoped_params` 中某参数出现但当前 action 不在其允许集 → inner 路由时 `_argument_error(..., supported_actions=…)`；否则 `_action_error("parameter 'X' applies only to action(s): …")`
5. **bespoke 路由（F5）**：`action in bespoke_map` → `_clean_bespoke_args`（剥 `action` 控制键 + R3 双向别名复制）→ 计时执行 handler；返回值**原样透传**（dict 或裸 int exit code，不附 provenance）
6. **inner 路由**：`action in action_map` →
   a. `_invalid_arguments` 非空（会被投影静默丢弃的参数）→ `_argument_error`（`error_code: INVALID_ARGUMENT`，`invalid_arguments`/`allowed_arguments`/`suggestions`，difflib cutoff 0.6 建议）
   b. `_project_args` 投影：剥控制键 `action` → **R3 归一**（`symbol` ↔ `function_name` 双向互补、`symbol → class_name` 单向，均在白名单过滤**之前**）→ 按 inner `inputSchema.properties` 白名单过滤（F4 strict-param projection）
   c. 计时窗口内 answer-cache：仅 allowlist 只读动作有 key；命中 → `_with_provenance(payload, key, "cache")`；未命中 → `inner.execute(projected)` + store + `_with_provenance(result, key, "computed")`。`provenance` 块键：`served_from, tool, action, normalized_args, generation, producer_version, extra_inputs`
7. **未知 action**：`_closest_action`（`difflib.get_close_matches(n=1, cutoff=0.6)`）→ `_action_error("unknown action 'X'; valid actions are: …", suggestion)`；`_action_error` 信封含 `success:False, verdict:"ERROR", error_type:"validation", error, facade, available_actions`（排序后）`, suggestion, summary_line, agent_summary{verdict, summary_line, next_step}`；有 suggestion 时 error 前缀 `did you mean: <s>? `

**INVALID_ARGUMENT 错误信封**（`_argument_error` / `_argument_value_error` 共有形状）：`success:False, verdict:"ERROR", error_type:"validation", error_code:"INVALID_ARGUMENT", error(=summary_line), facade, action, invalid_arguments, allowed_arguments, suggestions, summary_line, agent_summary{verdict:"ERROR", summary_line, next_step}`；值错误额外带 `invalid_values`/`allowed_values`。

**公共 inputSchema**（Wave D 精简形）：`required: ["action"]`（enum = 全部动作 + `help`）、`_CORE_FACADE_PARAMS`（scope/mode/file_path/symbol/function_name/query/language/limit/output_format/target_action）、`additionalProperties: True`（inner 严格校验由投影保证）。

### 2.3 Python 语言插件

来源：`languages/python_plugin/plugin.py`、`extractor.py`、`_python_complexity.py`、`models/result.py`、`tests/golden/corpus_python_expected.json`

**PythonPlugin**
- `language = "python"`；`extensions = [".py", ".pyw", ".pyi"]`；`is_applicable` 大小写不敏感后缀匹配
- `get_supported_queries()` 返回 **16** 个：`function, class, variable, import, async_function, method, decorator, exception, comprehension, lambda, context_manager, type_hint, docstring, django_model, flask_route, fastapi_endpoint`
- `get_element_categories()`：单/复数别名 → tree-sitter 节点类型，如 `function(s)/async_function(s)/method(s) → function_definition`、`class(es) → class_definition`、`import(s) → import_statement + import_from_statement`、`from_import(s) → import_from_statement`、`variable(s) → assignment`、`decorator(s) → decorator`、`exception(s) → raise_statement + except_clause`、`comprehension(s) → list/set/dictionary_comprehension + generator_expression`、`context_manager(s) → with_statement`、`type_hint(s) → type`、`docstring(s) → string`、`django_model(s) → class_definition`、`flask_route(s) → decorator`、`fastapi_endpoint(s) → function_definition`、`all_elements → 上述 16 种节点类型全集`
- `analyze_file(file_path, request)`：`tree_sitter.Parser` + `tree_sitter_python` capsule 解析 → `extract_functions/classes/variables/imports` → `node_count = count_nodes_iterative(root)` → `AnalysisResult(file_path, language="python", success=True, elements, line_count=len(source.splitlines()), node_count)`；`tree_sitter` 不可用或 grammar 加载失败时返回 `success=False` + `error_message`（不抛异常）
- `extract_elements(tree, source_code) → {"functions": […], "classes": […], "variables": […], "imports": […]}`（抽取异常时 log 后返回四个空列表，键仍在）

**AnalysisResult 序列化**（`models/result.py`）
- `to_dict()`：`file_path, line_count, package({name} | None), imports[], classes[], methods[], fields[], annotations[], analysis_time, success, error_message`
- `to_mcp_format()`：`{file_path, structure{package, imports, classes, methods, fields, annotations}, metadata{…counts, line_count, analysis_time, success, error_message}}`
- `get_summary()`：`file_path, line_count, class_count, method_count, field_count, import_count, annotation_count, success, analysis_time`

**Cyclomatic complexity 公式**（`_python_complexity.python_cyclomatic_complexity`）
`复杂度 = 1 + 决策节点数`，决策节点 frozenset（10 种）：`if_statement, elif_clause, for_statement, while_statement, except_clause, conditional_expression, match_statement, boolean_operator, for_in_clause, if_clause`。注意：`match_statement` 整体计 1（不逐 case）；`else`/`with` 不计；`and`/`or` 逐个计。

**corpus_python_expected.json 精确计数（锁定目标，9 种 node_types）**

```json
{"language": "python", "node_types": {
  "function_definition": 28, "class_definition": 8, "decorated_definition": 7,
  "lambda": 5, "list_comprehension": 1, "dictionary_comprehension": 1,
  "set_comprehension": 1, "generator_expression": 2, "yield": 3}}
```

Rust 侧对 `tests/golden/corpus_python.py` 的节点类型计数必须逐键相等（缺失键按 0 计，见 `tests/golden/validate_corpus.py` 语义）。

---

## 3. 非确定性与环境敏感字段归一化规则（Comparison Normalization）

对照（diff/录音回放）前对两侧 JSON 施加同一变换；只允许**删除或替换**下表字段，其余必须逐字节相等：

| 字段 | 出现位置 | 规则 |
|---|---|---|
| `analysis_time` | `AnalysisResult.to_dict()/to_mcp_format()/get_summary()` | 删除（或固定为 0 后再比） |
| `duration_ms` | `build_success_response(..., duration_ms=…)` | 删除 |
| `provenance.generation` | facade answer-cache 命中/新算响应 | 删除（源码树指纹的代数，环境敏感） |
| `provenance.producer_version` | 同上 | 删除（含版本号与实现标识） |
| `file_path` / `source_file` | 各响应回显 | **K12 同款归一化**：`\` → `/`，循环剥前导 `./`；对照时进一步把绝对路径改写为相对仓库根的相对路径 |
| 时间戳 / 缓存戳 / 绝对路径（任意键名） | 任何 fixture | 生成 fixtures 时即用相对路径与固定 cwd，避免引入；对照器对 `*_at`/`timestamp` 类键删除 |
| `node_count`、`node_types` 计数 | `analyze_file`、corpus 对照 | **不可归一化，只能对齐 grammar 版本**（见下） |

**node_count 与 grammar 版本差异风险**：PyPI v3.1.2 解析为 `tree-sitter 0.26.1` + `tree-sitter-python 0.23.6`（§1.2），而 rust-anything 依赖 `tree-sitter 0.27.2` + `tree-sitter-python 0.25.0`。两个 grammar 版本的节点命名/结构可能不同，直接影响 `node_count` 与 `node_types` 计数及抽取结果。策略：
1. `rust/tsa-core` 的 Python grammar crate **优先尝试钉到与 Python 侧一致的版本**；若 crates.io 无对应版本，则记录差异并在 fixtures 中为 Rust 侧单独生成一份「grammar 标注版」期望（文件名带 grammar 版本后缀），差异必须逐项列举、不得静默通过；
2. `corpus_python_expected.json` 的 9 键计数是**锁定验收目标**；若 Rust 侧 grammar 无法复现，视为该单元未完成，不得修改黄金文件；
3. 每份 fixture 在 `MANIFEST.json` 中记录生成侧的 `tree-sitter`/`tree-sitter-python`（或 Rust crate）版本。

---

## 4. rust-anything 单元映射与已知限制

### 4.1 整仓扫描结果（`rust-anything analyze . --whole-app`，schema `rust-anything/analyze@1`，language python；输出存 `/tmp/tsa-analyze-whole-app.json`）

| 指标 | 值 |
|---|---|
| packages / source_files / test_files / loc | 1 / 1267 / 1330 / 292497 |
| **units** | **82**（ready **30** / caution **42** / blocked **10** / keep 0） |
| parse_errors | **0** |

与第一批直接相关的单元：

| unit | files | LOC | status | readiness | 备注 |
|---|---|---|---|---|---|
| `tree_sitter_analyzer/languages/python_plugin/` | 16 | 2112 | caution | 0 | wave 4；外部依赖 anyio/tree-sitter/tree-sitter-python；direct_tests 15；exports 38 / bridgeable 26；主要风险 unordered-iteration(13)、string-offsets(12)、dynamic-typing(36)、async(5) |
| `tree_sitter_analyzer/mcp/` | 13 | 2104 | **blocked** | 0 | dynamic-code(2)；与 ~30 个单元存在 import cycle（notes 要求一起移植）；direct_tests 63 |
| `tree_sitter_analyzer/mcp/tools/` | 168 | 50035 | caution | 0 | exports 385 / bridgeable 253；direct_tests 365；fan_in 16；同样在巨型 import cycle 中；风险 unordered-iteration(407)、string-offsets(255)、dynamic-typing(709)、async(321) 等 |
| `tree_sitter_analyzer/mcp/resources/` | 5 | 834 | ready | 54 | 可早期单独 bridge |
| `tree_sitter_analyzer/mcp/utils/edge_extractors/` | 5 | 344 | ready | 73 | 同上 |

### 4.2 已知限制：目录粒度过粗

analyze 的默认单元切分是**目录级**：`mcp/tools/`（168 文件 / 50k LOC）与 `mcp/`（blocked，dynamic-code + 巨型 import cycle）无法作为单个 bridge 单元推进；整目录一次性移植会撞 rust-anything 的行数门禁与录制可行性。

**缓解策略**：
1. **阶段 2–3**：对目标**单文件 / 子模块**（如 `mcp/tools/_response_builder.py`、`mcp/tools/tool_response.py`、`mcp/tools/facade_tool.py`、`mcp/facade_map.py`）使用 `bridge --force` + PyO3，绕过目录级 readiness 评估，以本规格的契约测试为真门禁；
2. **或**先在 `rust/tsa-core` 建立**纯 Rust 契约与核心实现**（不接 Python import graph），行为对齐 fixtures 后，再决定是否/如何接 PyO3 桥回原包（过渡期默认不 `enable`）；
3. import cycle 的单元（`mcp/`、`mcp/tools/`）在纯 Rust 侧按本规格的边界（envelope → facade 分发 → 插件）重新切分，不复制 Python 侧的循环依赖结构。

### 4.3 Stage 0–1 产物布局（全部在 `rust/` 下）

```
rust/
├── SPEC.md                 # 本规格（Stage 0）
├── fixtures/               # Stage 1：PyPI v3.1.2 真实黄金输出（规范化后）
│   ├── MANIFEST.json       #   生成命令、venv freeze（grammar 版本）、归一化规则版本
│   ├── envelope/           #   build_response/build_error/… 与 envelope_violations 用例
│   ├── facade/             #   8 facades + set_project_path + 62 legacy + help + INVALID_ARGUMENT
│   ├── cli/                #   CLI envelope 黄金（corpus_python.py 等）
│   └── python_plugin/      #   corpus_python 节点计数 + extract_elements/AnalysisResult 输出
└── tsa-core/               # Stage 1：红灯契约测试 crate（todo!() 占位实现）
    ├── Cargo.toml
    ├── tests/              #   读 fixtures 的契约测试（红灯）
    └── src/                #   lib.rs + todo!() 模块
```

Stage 2+ 若使用 rust-anything bridge，其默认产物目录 `rust/<unit>-rs/` 同样落在本目录内。

---

## 5. 对照命令与 TDD 验收门禁

### 5.1 黄金生成（隔离 venv，PyPI v3.1.2；不使用本地源码）

```bash
python3 -m venv /tmp/tsa312
/tmp/tsa312/bin/pip install "tree-sitter-analyzer==3.1.2"
/tmp/tsa312/bin/pip freeze            # 记入 rust/fixtures/MANIFEST.json
                                      # 预期含 tree-sitter==0.26.1、tree-sitter-python==0.23.6

cd /workspace/tree-sitter-analyzer    # 仅作输入语料的读取位置；产物只写 rust/
# CLI envelope 黄金（--output-format json 为默认）
/tmp/tsa312/bin/tree-sitter-analyzer tests/golden/corpus_python.py \
    --output-format json > rust/fixtures/cli/corpus_python.cli.json
```

- MCP facade / envelope 黄金：经 `tree-sitter-analyzer-mcp`（stdio JSON-RPC `tools/call`）驱动，driver 脚本放 `rust/fixtures/tools/`（Stage 1 编写，只写 `rust/`）；逐个录制 8 facades 的代表性 action、`action=help`、`set_project_path`、62 个 legacy 名转发、未知 action / 非法参数错误信封
- corpus 节点计数黄金直接采用仓内 `tests/golden/corpus_python_expected.json`（基线冻结版本，只读复制进 `rust/fixtures/python_plugin/`）
- 每份产物落地前按 §3 规则归一化；`MANIFEST.json` 记录：生成日期、安装命令、`pip freeze`、归一化规则、TSA 版本/commit

### 5.2 Stage 1 红灯判据

```bash
cd rust/tsa-core && cargo test
```

红灯成立当且仅当：
1. `cargo test` **编译通过**（契约测试本身无语法/类型错误）；
2. **fixtures 解析通过**（所有 `rust/fixtures/**/*.json` 能被测试加载并断言非空——单独的 `fixtures_load` 测试组全绿）；
3. 行为测试**因未实现而失败**：被测函数体为 `todo!()`/`unimplemented!()`，失败信息可定位到对应契约条目（envelope / facade 分发 / python 插件）。

若编译失败或 fixtures 加载失败，不算合格红灯，先修测试本身。

### 5.3 Stage 3 绿灯及 gate 判据

- `cd rust/tsa-core && cargo test` 全绿；`cargo fmt --check`、`cargo clippy --all-targets -- -D warnings` 通过
- 归一化后的 Rust 输出与 fixtures **逐字节相等**（或差异清单逐项对应 §3 允许字段且为空以外的差异都有书面豁免）
- corpus_python：9 键 node_types 计数与 §2.3 锁定值完全一致
- 若该单元走了 rust-anything 流程：`build` → `diff`（归一化后 0 差异）→ `gate` 全过才算完成；通过后**默认不 `enable`**，保持 Python 原路径
- 每单元换人审查：对照日志、差异列表、gate 输出、未覆盖风险（规划/审查代理 ≠ 实现代理）

---

## 6. 禁止事项与发布/CI 安全护栏

### 6.1 禁止分支（TSA 仓库）

- **禁止使用/推送**：`main`、`develop`、`hotfix/*`、`release/v*`
- 依据：`hotfix-automation.yml` 与 `release-automation.yml` 在向 `hotfix/*`、`release/v*` push 时会调用 `reusable-publish.yml` 用 `secrets.PYPI_API_TOKEN` **自动发布 PyPI**（v3.1.2 即经此路径发布）；`develop-automation.yml` 会自动开 develop→main 的 PR。合并到 `main` 本身不发版，但仍在禁止之列
- 唯一允许的工作分支：`feature/rust-anything-rewrite`（已存在，基于 `origin/main` @ `f95da603`）

### 6.2 PR 规则

- **禁止直接 PR 到 `main`**：`.github/workflows/gitflow-guard.yml`（"Validate head→base per GITFLOW.md"）会拦截——PR 到 `main` 只允许 `release/v*` / `hotfix/*` 头分支
- 实验期如需 PR，目标为 **`develop`**，且仅在规格完成、内容值得评审时

### 6.3 禁止操作

- **禁止** 全局 `rust-anything setup`（会写 `~/.claude.json`、`~/.codex/config.toml`、`~/.cursor/mcp.json`、`~/.gemini/settings.json`、`~/.config/opencode/*` 并可能留下含 token 的 `.bak`）。如需 MCP，只在 TSA 实验分支的项目级 `.mcp.json` 手写 stdio 条目
- **禁止** `--agent claude` / `--agent codex`（默认 `acceptEdits` / `--full-auto` 无人值守，消耗付费额度；3 轮 × 30 分钟上限）。写 `port.rs` 由受控会话按 `TASK.md` 进行
- **禁止** `rust-anything enable`（会修改 Python 源文件）、`go` 带 `--agent` 自动批准、MCP 中自动批准 `go`/`enable`/`package`/`app_lift`
- **禁止** 修改 Python 源码、`tests/`、`pyproject.toml`、`.github/` 及任何 PyPI 发行文件（含 `upload_to_pypi.py`）；本阶段一切写入仅限 `rust/`
- **禁止** 在运行环境放置任何发布凭据（PyPI / crates.io / npm / Git push / SSH key / Claude / Codex 登录态）
- **禁止** 花钱：OpenAI embeddings 路径排除在范围外；不跑任何消耗付费额度的自动化
- 不删黄金文件、不改 `tests/golden/corpus_python_expected.json`（只读对照物）

### 6.4 基线不变式（ Stage 0 冻结，改动需重走规格评审）

- 对外 MCP 工具名 = 8 facades + `set_project_path`（+ β 期 62 legacy shim）
- JSON envelope：`success` + `verdict`（8 canonical）+ 工具载荷 + 可选 `warnings`/`agent_summary`；错误信封含 `error_type`/`agent_summary`/`summary_line`
- CLI 入口名与 CLI envelope（4 键 + verdict-mirror）不变
- Python 插件在 `corpus_python.py` 上的抽取与节点计数不变
