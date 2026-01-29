# Tasks - Fix Known Issues and Legacy Problems

## 任务拆解 (Work Breakdown Structure)

### Phase 1: list_files Sort Implementation
- **T1.1**: 阅读 `list_files_tool.py` 和 `fd_rg_utils.py` 现状 | Status: completed
- **T1.2**: 在 `fd_rg_utils.py` 中增加 `sort` 支持 | Status: completed
- **T1.3**: 在 `list_files_tool.py` 中暴露 `sort` 参数并应用 | Status: completed
- **T1.4**: 验证 `list_files` 排序功能 | Status: completed

### Phase 2: Query Engine Fix (Test 13-15)
- **T2.1**: 定位 Test 13-15 的具体失败原因 | Status: completed
- **T2.2**: 修复 `query.py` 或相关插件中的 fields/filter 处理 | Status: completed
- **T2.3**: 运行回归测试验证修复 | Status: completed

### Phase 3: Type Safety
- **T3.1**: 运行 `mypy` 并识别核心模块的主要错误 | Status: completed
- **T3.2**: 修复类型错误 | Status: completed

## 依赖关系 (Dependencies)
- 无

## 测试计划 (Testing Plan)
- 使用 `uv run pytest tests/regression/` 验证整体回归。
- 为 `list_files` 排序增加单元测试。
