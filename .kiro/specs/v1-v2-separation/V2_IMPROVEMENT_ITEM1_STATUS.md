# V2 改进项 1 检查结果与待提高项

**检查日期**: 2026-02-05  
**检查方式**: 使用 MCP (tree-sitter-analyzer) 的 `search_content` 在 V1 的 `tests/` 下检索 `mcp_tool_json_args` 与 `"output_format": "json"`。  
**结论**: 改进项 1 **部分完成**；MCP 能完成本次检查（无需人工逐文件查），说明 V2 工具能力在此场景可用。

---

## 改进项 1：共享 MCP 工具「要 JSON 返回」的约定

### 已达成

- **conftest**：根 conftest 已提供 `mcp_tool_json_args` fixture（返回 `{"output_format": "json"}`）。
- **部分测试已迁移**：`unit/mcp/test_mcp_fd_rg_tools.py` 等已统一使用 `{**mcp_tool_json_args, ...}`，未手写 `"output_format": "json"`。

### 已迁移（2026-02-05 全自动执行）

以下模块已改为注入 `mcp_tool_json_args` 并合并参数，不再手写 `"output_format": "json"`：

- **unit/mcp**：`test_mcp_rg_phase1_basic.py`、`test_list_files_tool.py`、`test_analyze_code_structure_tool.py`、`test_find_and_grep_tool.py`、`test_mcp_async_integration.py`
- **unit/performance**：`test_mcp_performance.py`
- **unit/core**：`test_tree_sitter_integration.py`
- **integration**：`test_phase7_end_to_end.py`、`test_user_story_1_integration.py`、`test_user_story_2_integration.py`、`test_user_story_3_integration.py`、`test_user_story_4_integration.py`、`test_mcp_integration.py`、`test_integration.py`
- **integration/mcp/test_tools**：`test_analyze_scale_tool.py`
- **benchmarks**：`test_large_file_performance.py`

### 待提高（仍手写 `"output_format": "json"` 的模块）

以下文件仍内联 `"output_format": "json"`，需按同一方式改为注入 `mcp_tool_json_args` 并合并参数。

| 层级 | 文件 | 约处数 |
|------|------|--------|
| **integration/mcp/test_tools** | `test_table_format_tool.py` | 5 |
| **integration/formatters** | `test_real_integration.py` | 4 |
| | `format_contract_tests.py` | 11 |
| **integration/core** | `test_analyze_scale_tool_file_output.py` | 8 |
| | `test_analyze_scale_tool_batch_metrics.py` | 1 |
| **integration/cli** | `test_read_partial_tool_file_output.py` | 10 |
| | `test_read_partial_tool_extended.py` | 7 |
| | `test_read_partial_tool_batch.py` | 1 |
| | `test_cli_query_filter_integration.py` | 4 |

**说明**：`tests/conftest.py` 内唯一一处 `"output_format": "json"` 为 fixture 定义本身，保留；`ARCHITECTURE_AND_V2_GUIDANCE.md` 中为文档说明，不纳入迁移。

### 建议执行顺序

1. **unit/mcp**：`test_mcp_rg_phase1_basic.py` → `test_list_files_tool.py` → `test_analyze_code_structure_tool.py` → `test_find_and_grep_tool.py` → `test_mcp_async_integration.py`。
2. **unit/** 其余：`test_mcp_performance.py`、`test_tree_sitter_integration.py`。
3. **integration/**：按上表从 user_story、tools、formatters、core、cli 分批改。
4. **benchmarks**：最后统一改为使用 `mcp_tool_json_args`（若 fixture 在 benchmark 中可用）或保留并加注释说明原因。

---

## MCP 检查能力说明

- **search_content**：可精确检索 `mcp_tool_json_args` 与 `"output_format": "json"`，能区分“已用 fixture”与“仍手写”的文件与行号。
- 本次未使用但可用于后续的：`find_and_grep`（先按 pattern 筛文件再搜内容）、`analyze_code_structure`（理解 conftest 结构）等。

若后续有“MCP 做不到”的检查项，可在此目录下新增文档记录，并标注为「需提高：V2 工具/能力」。
