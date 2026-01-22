# 测试失败修复任务计划

## 目标
修复 20 个失败的测试，主要涉及两类问题：
1. Mock 路径错误 - `fd_rg_utils` vs `fd_rg.utils`
2. 测试断言与 TOON 格式不匹配

## 问题分析

### 问题 1: Mock 路径错误 (10 个失败)
**文件**: `tests/unit/core/test_file_output_optimization.py`
**错误**: `AttributeError: 'module' object at tree_sitter_analyzer.mcp.tools.fd_rg_utils has no attribute 'run_command_capture'`
**原因**: 测试代码使用了错误的模块路径
- 错误: `tree_sitter_analyzer.mcp.tools.fd_rg_utils`
- 正确: `tree_sitter_analyzer.mcp.tools.fd_rg.utils`

### 问题 2: TOON 格式断言错误 (7 个失败)
**文件**: `tests/integration/mcp/tools/test_search_content_tool_integration.py`
**错误**: `assert 'matches' in result` 失败
**原因**: 
- 测试期望 JSON 格式的结果 (有 `matches` 键)
- 实际返回 TOON 格式 (数据在 `toon_content` 中)
- 需要在测试中指定 `output_format: "json"` 或更新断言逻辑

### 问题 3: 其他错误
- `KeyError: 'partial_content_result'` (2 个失败)
- `TypeError: RgCommandConfig.__init__() got an unexpected keyword argument 'files'` (1 个失败)
- `AssertionError: Expected AnalysisError for nonexistent file` (1 个失败)

## 执行阶段

### 阶段 1: 修复 Mock 路径错误 ✅
**状态**: `complete`
**文件**: `tests/unit/core/test_file_output_optimization.py`
**操作**: 将所有 `fd_rg_utils` 替换为 `fd_rg.utils`

### 阶段 2: 修复 TOON 格式断言错误 ✅
**状态**: `complete`
**文件**: `tests/integration/mcp/tools/test_search_content_tool_integration.py`
**操作**: 在测试中添加 `output_format: "json"` 参数
**修复**: 添加了 6 个 `output_format: "json"` 参数

### 阶段 3: 修复 partial_content_result 错误 ✅
**状态**: `complete`
**文件**: `tree_sitter_analyzer/mcp/tools/read_partial_tool.py`
**操作**: 修复条件逻辑错误
**修复**: 将 `if not suppress_output or not output_file:` 改为 `if not output_file or not suppress_output:`

### 阶段 4: 修复 RgCommandConfig 错误 ✅
**状态**: `complete`
**文件**: `tests/integration/mcp/tools/fd_rg/test_fd_rg_integration.py`
**操作**: 修复参数传递问题
**修复**: 将 `files=[...]` 改为 `roots=tuple(...)`

### 阶段 5: 修复错误处理断言
**状态**: `pending`
**文件**: `tests/integration/mcp/test_user_story_2_integration.py`
**操作**: 检查错误处理逻辑（可能需要修改测试期望）

## 错误记录
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| - | - | - |
