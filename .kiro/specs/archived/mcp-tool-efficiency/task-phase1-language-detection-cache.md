# Task 计划（Phase 1 / 要件2）：语言检测缓存（Best Practice）

> 设计依据：`design-phase1-language-detection-cache.md`

## 交付物（Deliverables）

- **D1**：实现语言检测缓存：key 为 `(project_root, abs_path)`，value 为 `{language, mtime_ns}`
- **D2**：在 `language_detector.py` 的简单 API 层接入缓存（single entry point）
- **D3**：工具侧/Server 侧调用保持兼容，但避免重复检测
- **D4**：新增测试覆盖：缓存命中、mtime_ns 失效、unknown 缓存、文件不存在不缓存

## 范围内文件（预计改动）

- `tree_sitter_analyzer/language_detector.py`
- `tree_sitter_analyzer/mcp/utils/shared_cache.py`
- （可选）`tree_sitter_analyzer/mcp/tools/base_tool.py`（如果决定把 language 检测入口也放到 base helper）
- `tests/` 下新增/扩展用例

## 任务拆解（Work Breakdown）

### T1：扩展 SharedCache 以支持语言缓存元信息

**目标**：缓存中既能存 language，也能存 mtime_ns。

**实现建议（推荐）**：
- 新增专用结构（避免破坏现有 `get_language/set_language` 语义）：
  - `_language_meta_cache: dict[str, dict[str, Any]]`
  - `get_language_meta(abs_path, project_root) -> dict | None`
  - `set_language_meta(abs_path, meta, project_root) -> None`

**验收点**：
- 能按 `(project_root, abs_path)` 读写 `{language, mtime_ns}`

### T2：在 `language_detector.py` 接入缓存（single entry point）

**目标**：所有调用 `detect_language_from_file()` 的地方自动获得缓存收益。

**实现要点**：
- 对输入 `file_path`：
  - 规范化为 `abs_path`（优先使用已 resolved 的路径；如由 API 内 resolve，需要明确策略）
- 获取 `mtime_ns`：
  - 使用 `Path(abs_path).stat().st_mtime_ns`
  - 若文件不存在/无权限 stat：**不写缓存**，直接返回扩展名检测结果/unknown
- 缓存命中条件：
  - cache 存在且 `mtime_ns` 相同
- 未命中：
  - 执行检测（Phase 1 仍按扩展名为主）
  - 将 `{language, mtime_ns}` 写入缓存（包括 `unknown`）

**验收点**：
- 连续调用同一文件 2 次，第二次不再实际检测（命中缓存）

### T3：跨工具复用（验证点）

**目标**：多个 MCP 工具处理同一文件时，不重复 detect。

**实现要点**：
- 不要求立即改动所有 tool：只要它们都调用 `detect_language_from_file()`，缓存就会生效。
- 如某些工具绕开了该 API（手写扩展名判断），应统一回该 API（Phase 1 可只覆盖高频路径）。

**验收点**：
- 至少 2 个不同入口（例如 server 与某个 tool）对同一文件的语言检测能共享缓存

### T4：测试补齐

**建议用例**：
- **schema/行为**：
  - unknown 扩展名返回 `unknown` 且可缓存
- **缓存命中**：
  - monkeypatch 统计底层检测函数调用次数（第二次应为 0 增量）
- **失效**：
  - 修改文件内容（触发 mtime_ns 变化）后，必须重新检测并刷新缓存
- **不存在文件**：
  - 不应写入缓存（避免后续文件出现时误命中旧缓存）

**验收点**：
- 全量 pytest 通过

## 风险与决策点（默认选择）

- **R1：mtime 粒度**：默认使用 `st_mtime_ns`（纳秒级）
- **R2：缓存容量**：Phase 1 暂不加 LRU（后续 SharedToolCache 做容量治理）

## Definition of Done

- 满足要件2四条受け入れ基準
- 命中/失效/unknown/不存在文件路径行为均有测试覆盖


