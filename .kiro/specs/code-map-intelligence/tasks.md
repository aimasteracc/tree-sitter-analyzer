# Code Map Intelligence - Tasks

## Phase 1: trace_call_flow — 双向调用链追踪

| Task | Status | Files |
|------|--------|-------|
| T1.1: 定义 CallFlowResult 数据类 | completed | `core/code_map.py` |
| T1.2: 实现 _build_call_index (源码扫描) | completed | `core/code_map.py` |
| T1.3: 实现 trace_call_flow BFS 遍历 | completed | `core/code_map.py` |
| T1.4: 编写 6 个核心测试 | completed | `tests/unit/test_code_map_intelligence.py` |
| T1.5: 修复 _build_call_index (body→源码行) | completed | `core/code_map.py` |
| T1.6: Ruff + Mypy 通过 | completed | `core/code_map.py` |

## Phase 2: impact_analysis — 修改影响分析

| Task | Status | Files |
|------|--------|-------|
| T2.1: 定义 ImpactResult 数据类 | completed | `core/code_map.py` |
| T2.2: 实现传递闭包 BFS + risk_level | completed | `core/code_map.py` |
| T2.3: 编写 7 个核心测试 | completed | `tests/unit/test_code_map_intelligence.py` |

## Phase 3: gather_context — LLM 上下文捕获

| Task | Status | Files |
|------|--------|-------|
| T3.1: 定义 ContextResult + CodeSection | completed | `core/code_map.py` |
| T3.2: 实现 gather_context (符号+调用者+代码) | completed | `core/code_map.py` |
| T3.3: 编写 7 个核心测试 | completed | `tests/unit/test_code_map_intelligence.py` |

## QA Edge Cases

| Task | Status | Files |
|------|--------|-------|
| T4.1: trace_call_flow 4 个边界测试 | completed | `tests/unit/test_code_map_intelligence.py` |
| T4.2: impact_analysis 4 个边界测试 | completed | `tests/unit/test_code_map_intelligence.py` |
| T4.3: gather_context 4 个边界测试 | completed | `tests/unit/test_code_map_intelligence.py` |

## Phase 4: Decorator/Framework Awareness — Dead Code Precision

| Task | Status | Files |
|------|--------|-------|
| T4.1: Add `decorated_entries` to `ModuleInfo` | completed | `core/code_map.py` |
| T4.2: Define `_FRAMEWORK_DECORATORS` pattern set | completed | `core/code_map.py` |
| T4.3: Implement `_extract_decorated_entries` (parser metadata + AST) | completed | `core/code_map.py` |
| T4.4: Wire into `_parse_file` | completed | `core/code_map.py` |
| T4.5: Update `_detect_dead_code` to skip decorated | completed | `core/code_map.py` |
| T4.6: Track decorator-usage (decorator factories alive) | completed | `core/code_map.py` |
| T4.7: Add depth limit to AST recursion | completed | `core/code_map.py` |
| T4.8: TDD tests (8 core + 4 QA edge cases) | completed | `tests/unit/test_code_map_intelligence.py` |
| T4.9: Decorator fixture | completed | `tests/fixtures/cross_file_project/decorated.py` |

## Phase 5: MCP Tool Exposure — code_intelligence

| Task | Status | Files |
|------|--------|-------|
| T5.1: Create `CodeIntelligenceTool` class | completed | `mcp/tools/intelligence.py` |
| T5.2: Register in server + __init__ | completed | `mcp/server.py`, `mcp/tools/__init__.py` |
| T5.3: Integration tests (18 tests) | completed | `tests/integration/test_intelligence_tool.py` |
| T5.4: Critic P0: fix double-scan | completed | `mcp/tools/intelligence.py` |
| T5.5: Critic P1: path validation | completed | `mcp/tools/intelligence.py` |
| T5.6: Critic P1: local var caching | completed | `mcp/tools/intelligence.py` |
| T5.7: Update tool count in existing tests | completed | `test_mcp_server.py`, `test_mcp_server_registration.py` |

## Verification

| Check | Status |
|-------|--------|
| All 61 intelligence tests pass | completed |
| All 18 MCP tool tests pass | completed |
| Ruff: 0 errors | completed |
| Mypy: 0 errors | completed |
| Full test suite: pending DevOps | in_progress |
