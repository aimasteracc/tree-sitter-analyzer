# Python 自索引验证报告 — Dogfood 结果

**日期**: 2026-08-15 ｜ **范围**: `tree_sitter_analyzer/**/*.py` 共 865 个文件 ｜ **索引器**: AST cache extractor v14 (SQLite) ｜ **Python**: 3.10.20

> 方法：用**标准库 ast 解析器**作为独立 ground truth，按 cache 提取规则（`cache/_symbol_walker.py`、`synapse_resolver/_imports.py`）推导每个文件**应该**被索引成什么，再与全新构建的 SQLite 索引（`/tmp/tsa-dogfood/index.db`，865 文件全量索引，synapse 已 backfill）**实际**内容逐项比对。

## 总体结论

| 检查项 | 预期 | 实际 | 一致率 | 判定 |
|---|---|---|---|---|
| 符号（function/method/class/constant，含行号） | 10755 | 10755（另 5248 行 kind=import） | **100%** | 零缺失、零行号偏差 |
| 导入绑定（ast_imports 行） | 7836 | 7327 | 93.5% | 509 条缺失（见 F1/F2） |
| CONTAINS 边（类→方法） | 3533 | 3533 | 100% | 完全一致 |
| EXTENDS 边（类→基类） | 328（建模口径） | 536 | 163%（重复） | 见 F4 |
| 跨文件调用边（可验证口径） | 1830 | 一致 1802 | 98.5% | 28 条错/漏解析（见 F3） |
| symbols_json ≡ ast_symbol_rows ≡ FTS5 | — | — | 100% | 865/865 文件三表一致 |

**正面结论**：符号层（名字、类型、行号）与独立解析器 100% 一致，行号零偏差；CONTAINS 边、三表一致性全部正确。索引的核心（AST 符号投影）可信。

**发现的问题**（详见第 4 节）：

1. **F1 — `from __future__ import annotations` 100% 丢失**：新语法节点 `future_import_statement` 不在 `_IMPORT_LIKE` 中，488/488 个含未来导入的文件在索引中完全无痕（symbols_json、ast_imports 都没有）。
2. **F2 — 括号多行导入带行内注释时整条语句丢失**：`from x import (  # noqa: F401` 这类写法在 `synapse_resolver/_imports.py` 正则里先按 `#` 切分导致 names 子句被截断为空白 → 该语句**所有别名**都不进 `ast_imports`（5 个文件、22 条绑定）。
3. **F3 — 跨文件调用解析忽略 import 绑定**：裸名解析器在“全项目多个文件定义同名函数”时挑错文件（24 条错指 + 8 条漏解析），例如 `cache/_symbol_declarations.py` 调用 `_node_text`（import 自 `cache/_symbol_syntax.py`）却被解析到 `_uml_state_helpers.py`；`search_content_cli.py` 的 `add_output_options` 被指到 `find_and_grep_cli_helpers.py`。
4. **F4 — EXTENDS 边重复**：146 个文件每条基类边生成 2 条（通用 `class:X` 节点 + synapse 解析后的文件符号节点），预期 328 条、实际 536 条；解析后的目标本身正确。
5. **F5 — ast_imports 丢失行号**：7327 行全部 `line=0`（写路径用字符串形式导入原文，`_parse_import_raw` 丢弃行号）。

## 1. 代码分类总览

按 `tree_sitter_analyzer/` 一级子目录分类（PackageRoot = 包根目录 116 个文件）：

| 分类 | 文件数 | 符号 预期→实际 | 导入 预期→实际 | 跨文件调用边(模型可验证) | 有问题的文件 |
|---|---|---|---|---|---|
| MCP | 221 | 3015 → 4576 | 2148 → 1985 | 609/614 | 219 |
| Languages | 149 | 2010 → 3101 | 1658 → 1587 | 354/359 | 148 |
| PackageRoot | 116 | 1832 → 2760 | 1268 → 1172 | 280/281 | 116 |
| Formatters | 87 | 1030 → 1333 | 526 → 505 | 141/146 | 87 |
| CLI | 59 | 533 → 923 | 585 → 539 | 116/120 | 59 |
| Synapse | 37 | 309 → 417 | 185 → 148 | 25/26 | 37 |
| Cache | 24 | 287 → 477 | 345 → 322 | 52/56 | 24 |
| GrammarCoverage | 24 | 110 → 163 | 105 → 101 | 5/6 | 10 |
| Core | 21 | 203 → 327 | 151 → 149 | 30/31 | 20 |
| Queries | 19 | 192 → 205 | 17 → 16 | 11/11 | 13 |
| ImportExtractors | 9 | 47 → 72 | 49 → 49 | 18/18 | 9 |
| KnowledgeGraph | 9 | 156 → 226 | 108 → 100 | 39/40 | 9 |
| PlatformCompat | 9 | 88 → 132 | 61 → 61 | 6/6 | 9 |
| Constraints | 8 | 33 → 62 | 47 → 39 | 8/8 | 8 |
| Exceptions | 8 | 64 → 95 | 61 → 61 | 3/3 | 8 |
| Registry | 8 | 91 → 133 | 49 → 43 | 0/0 | 8 |
| Utils | 8 | 91 → 124 | 66 → 64 | 19/19 | 7 |
| Models | 7 | 75 → 106 | 111 → 111 | 20/20 | 7 |
| Task | 7 | 120 → 146 | 56 → 49 | 9/9 | 7 |
| Hyphae | 5 | 54 → 67 | 34 → 29 | 11/11 | 5 |
| Plugins | 5 | 138 → 189 | 75 → 75 | 14/14 | 5 |
| Security | 5 | 97 → 129 | 39 → 38 | 2/2 | 5 |
| Encoding | 4 | 15 → 25 | 12 → 12 | 0/0 | 4 |
| Internal_Api | 4 | 22 → 35 | 13 → 13 | 1/1 | 4 |
| Route_Detector | 4 | 84 → 104 | 38 → 35 | 29/29 | 4 |
| Serialization | 4 | 10 → 16 | 9 → 6 | 0/0 | 4 |
| Graph | 2 | 47 → 54 | 15 → 14 | 0/0 | 2 |
| Services | 1 | 1 → 4 | 4 → 3 | 0/0 | 1 |
| Skills | 1 | 1 → 2 | 1 → 1 | 0/0 | 1 |

说明：符号“实际”含 kind=import 行（导入语句原文），故通常大于预期；导入差异集中在 F1/F2。

## 2. 逐文件验证（示例：预期 vs 实际）

### 示例 A — 有问题的文件：`tree_sitter_analyzer/ast_cache.py`

| 项 | 预期（stdlib ast） | 实际（SQLite） | 差异 |
|---|---|---|---|
| 符号 | 16 函数 + 1 类 + 5 常量 | 完全一致（含行号） | 0 |
| 导入绑定 | 21 | 13 | 缺 8：`.cache.extraction`x4、`.cache.helpers`x2、`.cache.maintenance`x1、`__future__`x1 |
| 原因 | — | — | `from .cache.extraction import (  # noqa: F401` 行内注释（F2）+ future 导入（F1） |

### 示例 B — 干净文件：`tree_sitter_analyzer/core/request.py`

| 项 | 预期 | 实际 | 差异 |
|---|---|---|---|
| 符号 | 2 | 4（含 2 行 import 原文） | 0 缺失、行号全对 |
| 导入绑定 | 2 | 2 | 0 |
| 跨文件调用（模型口径） | 0 | 一致 0 | 0 错漏 |
| CONTAINS / EXTENDS | 1/0 | 1/0 | 一致 / 一致 |

### 示例 C — 插件文件：`tree_sitter_analyzer/languages/python_plugin/extractor.py`

| 项 | 预期 | 实际 | 差异 |
|---|---|---|---|
| 符号 | 3 | 12（含 9 行 import 原文） | 0 缺失 |
| 导入绑定 | 21 | 21 | 0 |
| 跨文件调用（模型口径） | 0 | 一致 0 | 0 错漏 |

## 3. 全局问题清单（可执行证据）

### F2 明细 — 括号导入 + 行内注释 → 整条丢失（5 文件 22 条绑定）

| 文件 | 丢失的绑定 |
|---|---|
| `tree_sitter_analyzer/ast_cache.py` | _content_hash、_extract_symbols、_has_fts5、_node_text、_build_function_entry、_commit_index_results、_reclaim_storage_after_full_rebuild |
| `tree_sitter_analyzer/cli/commands/mcp_commands/__init__.py` | CodeGraphCalleeTreeTool、CodeGraphCallerTreeTool |
| `tree_sitter_analyzer/mcp/tools/_graph_cache_fingerprint.py` | GraphFingerprint、_EXCLUDE_DIRS、_SOURCE_EXTS、compute_graph_fingerprint、is_ast_index_stale |
| `tree_sitter_analyzer/mcp/tools/fd_rg_utils.py` | create_file_summary_from_count_data、extract_file_list_from_count_data、group_matches_by_file、optimize_match_paths、parse_rg_json_lines_to_matches、summarize_search_results |
| `tree_sitter_analyzer/mcp/utils/shared_cache.py` | SharedCache、get_shared_cache |

### F3 明细 — 跨文件调用错解析/漏解析

| 调用点（文件:caller） | callee | 应指向（按 import 绑定） | 实际指向 |
|---|---|---|---|
| `tree_sitter_analyzer/cache/_symbol_declarations.py` `_go_constant_symbol` | `_node_text` | `tree_sitter_analyzer/cache/_symbol_syntax.py` | `tree_sitter_analyzer/_uml_state_helpers.py` |
| `tree_sitter_analyzer/cache/_symbol_declarations.py` `_php_constants` | `_node_text` | `tree_sitter_analyzer/cache/_symbol_syntax.py` | `tree_sitter_analyzer/_uml_state_helpers.py` |
| `tree_sitter_analyzer/cache/_symbol_declarations.py` `_python_docstring` | `_node_text` | `tree_sitter_analyzer/cache/_symbol_syntax.py` | `tree_sitter_analyzer/_uml_state_helpers.py` |
| `tree_sitter_analyzer/cache/_symbol_declarations.py` `_python_module_constant` | `_node_text` | `tree_sitter_analyzer/cache/_symbol_syntax.py` | `tree_sitter_analyzer/_uml_state_helpers.py` |
| `tree_sitter_analyzer/cli/commands/base_command.py` `detect_language` | `is_language_supported` | `tree_sitter_analyzer/language_detector.py` | `tree_sitter_analyzer/api.py` |
| `tree_sitter_analyzer/cli/commands/mcp_commands/__init__.py` `handle_mcp_commands` | `_run_tool` | `tree_sitter_analyzer/cli/commands/mcp_commands/_helpers.py` | `tree_sitter_analyzer/cli/commands/constraint_check_command.py` |
| `tree_sitter_analyzer/cli/commands/search_content_cli.py` `_build_parser` | `add_output_options` | `tree_sitter_analyzer/cli/commands/search_content_cli_helpers.py` | `tree_sitter_analyzer/cli/commands/find_and_grep_cli_helpers.py` |
| `tree_sitter_analyzer/cli/commands/search_content_cli.py` `_build_parser` | `add_rg_options` | `tree_sitter_analyzer/cli/commands/search_content_cli_helpers.py` | `tree_sitter_analyzer/cli/commands/find_and_grep_cli_helpers.py` |
| `tree_sitter_analyzer/core/query.py` `_process_captures` | `process_captures` | `tree_sitter_analyzer/core/_query_results.py` | `（未解析）` |
| `tree_sitter_analyzer/formatters/_typescript_formatter_compact.py` `_method_row` | `create_compact_signature` | `tree_sitter_analyzer/formatters/_typescript_formatter_helpers.py` | `tree_sitter_analyzer/formatters/_python_formatter_signatures.py` |
| `tree_sitter_analyzer/formatters/_typescript_formatter_full.py` `_append_class_section` | `get_class_fields` | `tree_sitter_analyzer/formatters/_typescript_formatter_helpers.py` | `tree_sitter_analyzer/formatters/_java_formatter_class_mixin.py` |
| `tree_sitter_analyzer/formatters/_typescript_formatter_full.py` `_append_class_section` | `get_class_methods` | `tree_sitter_analyzer/formatters/_typescript_formatter_helpers.py` | `tree_sitter_analyzer/formatters/_java_formatter_class_mixin.py` |
| `tree_sitter_analyzer/formatters/_typescript_formatter_full.py` `_class_overview_row` | `get_class_fields` | `tree_sitter_analyzer/formatters/_typescript_formatter_helpers.py` | `tree_sitter_analyzer/formatters/_java_formatter_class_mixin.py` |
| `tree_sitter_analyzer/formatters/_typescript_formatter_full.py` `_class_overview_row` | `get_class_methods` | `tree_sitter_analyzer/formatters/_typescript_formatter_helpers.py` | `tree_sitter_analyzer/formatters/_java_formatter_class_mixin.py` |
| `tree_sitter_analyzer/grammar_coverage/auto_discovery.py` `get_all_node_types` | `get_all_node_types` | `tree_sitter_analyzer/grammar_coverage/introspector.py` | `（未解析）` |
| `tree_sitter_analyzer/incremental_sync.py` `get_changes` | `get_changes` | `tree_sitter_analyzer/incremental_sync_support.py` | `（未解析）` |
| `tree_sitter_analyzer/knowledge_graph/ladybug_query.py` `_edges_between` | `_edge_from_row` | `tree_sitter_analyzer/knowledge_graph/query.py` | `tree_sitter_analyzer/graph/edge_store.py` |
| `tree_sitter_analyzer/languages/_kotlin_class_helpers.py` `_kotlin_class_visibility` | `determine_visibility` | `tree_sitter_analyzer/languages/_kotlin_core_helpers.py` | `tree_sitter_analyzer/languages/_cpp_element.py` |
| `tree_sitter_analyzer/languages/go_plugin.py` `_extract_import_declaration` | `_extract_import_declaration` | `tree_sitter_analyzer/languages/_go_import.py` | `（未解析）` |
| `tree_sitter_analyzer/languages/sql_plugin/extractor.py` `_extract_function_metadata` | `_extract_function_metadata` | `tree_sitter_analyzer/languages/sql_plugin/function_extractor.py` | `（未解析）` |
| `tree_sitter_analyzer/languages/sql_plugin/extractor.py` `_parse_column_definition` | `_parse_column_definition` | `tree_sitter_analyzer/languages/sql_plugin/table_extractor.py` | `（未解析）` |
| `tree_sitter_analyzer/languages/sql_plugin/extractor.py` `_split_column_definitions` | `_split_column_definitions` | `tree_sitter_analyzer/languages/sql_plugin/table_extractor.py` | `（未解析）` |
| `tree_sitter_analyzer/mcp/tools/_codegraph_query_facets.py` `complexity_facet` | `_absolute_path` | `tree_sitter_analyzer/mcp/tools/_codegraph_query_symbols.py` | `tree_sitter_analyzer/frozen_git_settings.py` |
| `tree_sitter_analyzer/mcp/tools/_codegraph_query_facets.py` `health_facet` | `_absolute_path` | `tree_sitter_analyzer/mcp/tools/_codegraph_query_symbols.py` | `tree_sitter_analyzer/frozen_git_settings.py` |
| `tree_sitter_analyzer/mcp/tools/change_impact_tool.py` `_finalize_pr_result` | `_finalize_pr_result` | `tree_sitter_analyzer/mcp/tools/change_impact_support.py` | `（未解析）` |
| `tree_sitter_analyzer/mcp/utils/project_index/_filesystem.py` `compute_language_distribution` | `_is_language_count_excluded` | `tree_sitter_analyzer/mcp/utils/project_index/_readme.py` | `tree_sitter_analyzer/mcp/tools/project_overview_tool.py` |
| `tree_sitter_analyzer/mcp/utils/project_index/_manager.py` `render_toon` | `render_toon` | `tree_sitter_analyzer/mcp/utils/project_index/_toon.py` | `（未解析）` |
| `tree_sitter_analyzer/synapse_resolver/_context.py` `_build_resolver_context_uncached` | `ImportEntry` | `tree_sitter_analyzer/synapse_resolver/_imports.py` | `tree_sitter_analyzer/cross_file_resolver.py` |

### F1 统计 — future 导入

- 仓库内含 `from __future__ import` 的文件：**488**；`ast_imports`/`imports_json` 中出现的 future 导入：**0**（100% 丢弃）。

### F4 统计 — EXTENDS 重复

- 受影响文件：**146**；总边数 536（预期 328）。每条基类边 = 通用节点 + 解析后节点两条。

### F5 — ast_imports 行号

- **7327 / 7327** 行 `line=0`：写路径 `_parse_import_raw` 对字符串条目固定返回 0。

## 4. 根因定位

| # | 严重度 | 根因位置 | 建议 |
|---|---|---|---|
| F1 | P2 | `cache/_symbol_rules.py::_IMPORT_LIKE` 缺 `future_import_statement`（tree-sitter-python 新语法节点） | 加入该节点；或索引时显式跳过并在文档声明 |
| F2 | P1 | `synapse_resolver/_imports.py::_parse_python_imports`：`names_clause.split('#',1)[0]` 在去括号**之前**，括号内注释截断整条 | 先去括号/逐行去注释，再切分别名；补充括号+注释回归测试 |
| F3 | P1 | synapse 裸名解析按全项目同名定义匹配，未使用调用文件的 import 绑定消歧 | 解析时优先用本文件 `ast_imports` 绑定（module_path → 目标文件）过滤候选；重名时标记 ambiguous 而非硬选 |
| F4 | P3 | `cache/unresolved.py` 第二遍解析插入文件级 EXTENDS 边，但初写 `class:X` 通用边未删除 | 解析成功后替换/删除通用边，或查询端去重 |
| F5 | P3 | `cache/write.py::_parse_import_raw` 字符串条目丢弃行号（walker 其实有 line） | 提取时携带 line（dict 形式）写入 |

## 5. 复现

数据文件：`docs/dogfood/data/detail.jsonl.gz`（865 个文件每文件一行 JSON，含全部缺失/多余条目；`gunzip -c detail.jsonl.gz > detail.jsonl` 解压）、`docs/dogfood/data/totals.json`。

## 6. 本验证的口径与限制

- 符号/常量规则严格镜像 cache 提取器（`_python_module_constant`：模块级单目标赋值 + 大写/dunder/类型标注）；嵌套 def/类、`if TYPE_CHECKING` 内定义均计入（与 walker 一致）。
- 跨文件调用模型只接受**可证绑定**：模块级 `from X import y`（含别名）且目标文件确实定义该符号；属性调用（`a.b()`）、`import *`、`__init__` 再导出、函数内 import 不计入预期 —— 因此“额外”的 6187 条大部分是模型覆盖缺口，只有与预期目标冲突的才算错指（F3 表内为铁证）。
- `ast_imports.line` 恒为 0（F5）已在比对时排除行号维度。
- 抽取与索引写路径为 TSA 自身代码（dogfood 对象），ground truth 独立于 TSA。