# V1 测试架构分析与 V2 指导改进

## 1. 架构问题摘要

### 1.1 冗余与重复

| 问题 | 现状 (V1) | V2 参考 |
|------|------------|---------|
| **output_format 重复** | 50+ 处手写 `"output_format": "json"`，断言依赖完整 dict 的测试分散在多文件 | 单一 conftest 或 fixture 提供“要完整 JSON 返回”的约定，测试只声明需求 |
| **同模块多文件重复** | `unit/test_validator.py` 与 `unit/security/test_validator.py`；`test_regex_checker`、`test_boundary_manager` 同理 | 按领域单一入口：security 相关集中到 `unit/security/` |
| **universal_analyze 测试分散** | `unit/cli/test_universal_analyze_tool_*.py` 与 `unit/mcp/test_universal_analyze_tool.py` 存在重叠 | 按层级划分：unit 测工具逻辑，cli 测命令行入口，避免同一行为多处断言 |
| **temp_project_dir 与 sample 文件** | conftest 内大段内联创建 src/java/js/README | V2 使用 `tests/fixtures/` 目录 + 短小 fixture（如 `sample_python_code()`），减少重复与体积 |

### 1.2 结构与分层

| 问题 | 现状 (V1) | V2 参考 |
|------|------------|---------|
| **conftest 体积** | 单文件 487+ 行，大量 autouse 与 reset 逻辑 | 精简 conftest，按目录 conftest 分层（根 conftest 仅路径/通用 fixture） |
| **fixture 命名与复用** | `temp_project_dir`、`temp_test_file`、`temp_test_dir` 分散，无统一“MCP 工具默认参数” | 明确命名：`project_root`、`fixtures_dir`、`mcp_tool_json_args`（需要完整 JSON 时合并） |
| **测试目录与代码对应** | unit/cli、unit/core、unit/mcp、unit/security、unit/languages 等混用 | V2：unit/ 按模块与 integration/ 分离，fixtures 独立目录 |

### 1.3 可维护性

| 问题 | 建议 |
|------|------|
| 默认 toon 与断言不一致 | 凡断言 `result["file_path"]`、`result["analysis_type"]` 等，统一通过 fixture 或 helper 传入 `output_format="json"`，避免每处手写 |
| 单例 reset 重复 | reset_global_singletons 内 try/except 块重复两次（yield 前后），可抽成 _reset_singletons() 调用 |
| 测试与实现耦合 | 工具返回形状变更时，仅改 conftest/fixture 或一层 helper，而不是改 50+ 个测试 |

---

## 2. V2 指导的改进项（按优先级）

1. **共享 MCP 工具“要 JSON 返回”的约定**  
   在 conftest 中提供 `mcp_tool_json_args()`（返回 `{"output_format": "json"}`），需要完整 dict 的测试合并使用。  
   → 减少重复，便于日后统一改为环境变量或 mark 控制。

2. **合并重复的 security/validator 等单元测试**  
   保留 `unit/security/` 下入口，逐步将 `unit/test_validator.py` 等迁移或改为引用，避免同一行为两处维护。

3. **conftest 精简**  
   抽离 reset 逻辑为函数；考虑将 `cleanup_test_databases`、`verify_test_isolation` 等按需使用而非 autouse。

4. **fixtures 与 test_data**  
   长期可引入 `tests/fixtures/` 或 `tests/test_data/`，与 V2 对齐，减少内联大段内容。

---

## 3. 本次实施（TDD）

- 在根 conftest 中新增 `mcp_tool_json_args` fixture。
- 在 `test_universal_analyze_tool_coverage.py` 中改用该 fixture 合并 args，运行现有测试全部通过后提交。
