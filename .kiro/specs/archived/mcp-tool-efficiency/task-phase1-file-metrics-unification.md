# Task 计划（Phase 1 / 要件3）：文件 Metrics 计算的统一与缓存

> 设计依据：`design-phase1-file-metrics-unification.md`

## 交付物（Deliverables）

- **D1**：新增统一模块 `tree_sitter_analyzer/mcp/utils/file_metrics.py`
- **D2**：移除 `server.py` 与 `analyze_scale_tool.py` 内部重复 metrics 计算实现，全部改用统一模块
- **D3**：实现基于 **content_hash** 的 metrics 缓存与失效（内容变化必失效）
- **D4**：新增/更新测试，覆盖“命中缓存 / 内容变化失效 / 输出字段齐全”

## 范围内文件（预计改动）

- 新增：`tree_sitter_analyzer/mcp/utils/file_metrics.py`
- 修改：
  - `tree_sitter_analyzer/mcp/server.py`
  - `tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py`
  - `tree_sitter_analyzer/mcp/utils/shared_cache.py`（如需扩展 metrics cache key 规则/辅助 API）
- 测试：`tests/` 下新增或扩展相应用例

## 任务拆解（Work Breakdown）

### T1：定义统一 metrics API 与返回结构

- **目标**：确定统一模块的函数签名与返回 dict 的字段名（以要件字段为准）。
- **建议接口**（实现时可调整命名，但语义要一致）：
  - `compute_file_metrics(file_path: str, language: str | None = None) -> dict[str, Any]`
  - 返回必须包含：
    - `total_lines/code_lines/comment_lines/blank_lines/estimated_tokens/file_size_bytes`
    - 可选：`content_hash`

**验收点**：
- 满足要件3的字段清单
- 统一输出字段命名，不再出现 server/tool 各自命名漂移

### T2：实现 content_hash 指纹 + 缓存

- **目标**：同一文件多次请求时复用缓存；内容变化时必失效。
- **实现要点**：
  - 读取文件内容一次即可同时：
    - 计算 `file_size_bytes`
    - 计算 `estimated_tokens`
    - 计算 `content_hash`（例如 SHA256）
    - 计算行分类指标
  - 缓存 key 至少包含：
    - `project_root`
    - `resolved_path`
    - `content_hash`

**验收点**：
- 同一内容重复调用命中缓存
- 修改文件内容后 cache miss 并重新计算

### T3：替换 `server.py` 的重复实现

- **目标**：删除/替换 `server.py::_calculate_file_metrics` 的内部逻辑，改调用统一模块。
- **实现要点**：
  - 保持 server 对外输出结构（如需 `lines_*` 的字段映射，在组装响应处做薄转换）
  - 不重复读文件/不重复算 metrics

**验收点**：
- server 路径不再维护独立 metrics 算法
- 输出包含所需字段（或可映射得到）

### T4：替换 `AnalyzeScaleTool` 的重复实现

- **目标**：删除/替换 `AnalyzeScaleTool::_calculate_file_metrics`，改调用统一模块。
- **实现要点**：
  - token 估算策略保持一致（统一模块内实现）
  - 仍保持原有返回结构与 TOON/JSON 输出兼容

**验收点**：
- AnalyzeScaleTool 输出仍包含要件字段
- 注释/空行统计与 server 一致（同一算法）

### T5：测试补齐（必做）

- **目标**：防止统一后出现字段缺失、缓存误命中、或行为不一致。
- **建议用例**：
  - **字段完整性**：返回 dict 必须包含要件字段
  - **缓存命中**：同一文件两次调用 metrics，只计算一次（用 spy/monkeypatch 统计底层读取或 compute 次数）
  - **内容变化失效**：写入不同内容后，应触发重新计算
  - **跨入口一致**：同一文件分别从 server 路径与 analyze_scale_tool 路径获取 metrics，关键字段一致

**验收点**：
- 新增测试通过
- 全量 pytest 通过

## 风险与决策点（默认选择）

- **R1：hash 算法**  
  - 默认：SHA256（稳定且实现简单）
- **R2：缓存容量**  
  - 默认：Phase 1 先不引入 LRU，上层后续 Phase 2 再做容量治理（文档已有风险提示）

## Definition of Done

- 仅保留**单一** metrics 计算实现
- 满足要件3四条受け入れ基準
- 测试覆盖缓存命中与内容变化失效


