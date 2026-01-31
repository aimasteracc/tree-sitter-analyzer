# Task 计划（Phase 1 / 要件1）：重複セキュリティ検証の排除

> 设计依据：`design-phase1-security-validation-cache.md`  
> 目标：减少同一请求/同一进程会话内对同一文件路径的重复安全校验与重复 resolve，同时不降低安全性。

## 交付物（Deliverables）

- **D1**：实现“安全校验缓存 + original→resolved 映射缓存”，并在 project root 变化时失效。
- **D2**：移除/合并重复校验路径：至少覆盖 `server.py` + `AnalyzeScaleTool` 的重复点。
- **D3**：新增/更新测试用例，验证“缓存命中/失效/不回退安全性”。
- **D4**：可观测性（最低限度）：日志或计数能证明 `validate_file_path` 调用次数下降（可选但推荐）。

## 范围内文件（预计改动）

- `tree_sitter_analyzer/mcp/utils/shared_cache.py`
- `tree_sitter_analyzer/mcp/tools/base_tool.py`
- `tree_sitter_analyzer/mcp/server.py`
- `tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py`
- （测试目录：按仓库现有测试结构决定，后续实现阶段确定具体路径）

## 任务拆解（Work Breakdown）

### T1：明确缓存 key 规则并在 `SharedCache` 落地

- **目标**：支持复合 key，至少包含 `project_root`，避免跨项目污染。
- **实现要点**：
  - 约定 key 编码：`"{project_root}::{kind}::{path}"`（示例；最终以实现为准）
  - 缓存项：
    - `resolved_paths[(project_root, original)] -> resolved`
    - `security_cache[(project_root, resolved)] -> (is_valid, error_msg)`
  - 保留 `SharedCache.clear()` 作为统一失效入口

**验收点**：
- 缓存写入/读取对同一路径可稳定命中
- 不同 `project_root` 下同一路径字符串不会互相命中

### T2：在 `BaseMCPTool` 提供统一 helper（推荐）

- **目标**：让工具侧尽量只调用一个 helper，避免散落式 resolve/validate。
- **实现要点**：
  - 新增 helper（命名不强制）：`resolve_and_validate_file_path(file_path: str) -> str`
  - helper 内部：
    - 查询/写入 original→resolved 缓存
    - 查询/写入 security 校验缓存（以 resolved 为主）
  - `set_project_path()` 被调用时清空 shared cache（或调用外部统一清空）

**验收点**：
- 任意 tool 使用 helper 后，不再需要重复调用 `SecurityValidator.validate_file_path` 两次

### T3：Server 层去重（`server.py`）

- **目标**：避免 server + tool 双重校验造成的重复；推动“单一入口”。
- **实现要点（Phase 1 最小可行）**：
  - server 在 `handle_call_tool` 对 `file_path` 的校验应复用缓存（或改为使用 Base 的统一逻辑）
  - 规范化传参：将 `arguments["file_path"]` 规范化为 resolved（或新增 `resolved_file_path`，但要保证兼容）
  - `set_project_path` 执行时触发缓存失效

**验收点（建议用日式句式，便于对齐 requirements）**：
- ファイルパスを検証した場合、システムは同一プロセス内の後続リクエストのために検証結果をキャッシュしなければならない
- プロジェクトパスが変更された場合、システムはキャッシュされた検証結果をすべて無効化しなければならない

### T4：Tool 层去重（`AnalyzeScaleTool`）

- **目标**：移除 `AnalyzeScaleTool.execute()` 中对同一路径的重复校验与重复 resolve。
- **实现要点**：
  - 使用 Base helper（T2）后：
    - 不再对 original 与 resolved 各做一次完整校验
    - 只保留必要的“文件存在性检查”等业务校验

**验收点**：
- `AnalyzeScaleTool.execute()` 对同一 `file_path` 不再触发 2 次 `validate_file_path`

### T5：测试与回归验证

- **目标**：证明优化有效且不引入安全回退。
- **建议测试维度**：
  - **缓存命中**：同一 `project_root + file_path` 连续调用，第二次不再走完整校验（可用 monkeypatch/spy 统计调用次数）
  - **失效**：调用 `set_project_path` 后，缓存必须清空，下一次调用必须重新校验
  - **安全不回退**：非法路径（越界/穿越）仍然失败；合法路径仍然成功

**验收点**：
- 测试覆盖上述三类场景
- 现有测试套件不回归失败

## 风险与决策点（需要你在实现前确认的默认选择）

- **R1：是否引入新的“轻量校验”API**  
  - 默认：Phase 1 先不新增 API（走“最小改动”路径：缓存封装现有 `validate_file_path`），避免影响面过大。
  - 如果你希望更严格按“分层校验”落地，我们再在实现阶段把它升级为新增 API。

- **R2：失败结果是否加 TTL**  
  - 默认：Phase 1 不做 TTL；仅做 project root 变更失效。

## 完成定义（Definition of Done）

- 关键路径重复校验被消除（至少 server + analyze_scale）
- project root 变化可可靠清空缓存
- 有测试覆盖缓存命中与失效
- 代码风格与现有约定一致


