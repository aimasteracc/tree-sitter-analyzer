# TODOS

## Core — Analysis Sessions & Daemon

### **Priority:** P0
**Fix multi-instance daemon race condition**
- **What:** Add `fcntl.flock()` to PID file for atomic daemon startup
- **Why:** 两个 `tsa daemon start` 同时执行会导致第二个实例崩溃（未捕获异常）
- **Pros:** 保证单一 daemon 实例，避免生产环境崩溃
- **Cons:** 增加 5-10 行代码复杂度
- **Context:** 当前 plan 仅用 PID file 检测，无原子锁。Daemon startup 在 `daemon_server.py::start()` 中实现
- **Depends on:** Daemon Architecture 实现
- **Effort:** S (human: ~1h / CC: ~10min)

### **Priority:** P0
**Handle IndexManager LRU eviction failure**
- **What:** eviction 失败时降级到 read-only 模式，停止索引新文件
- **Why:** 内存超 2GB 且 LRU 无法释放（文件锁定）会导致 OOM crash
- **Pros:** daemon 继续服务已有索引，避免崩溃
- **Cons:** 降级模式需要向用户显示状态
- **Context:** IndexManager 在 `daemon/index_manager.py` 中维护 2GB cap。LRU eviction 逻辑未处理失败场景
- **Depends on:** Daemon Architecture 实现
- **Effort:** S (human: ~2h / CC: ~15min)

### **Priority:** P0
**Handle empty output in parse_analysis_result()**
- **What:** 空输出返回空 StructuredResult（functions=[], classes=[]），而非抛出异常
- **Why:** 分析空文件时测试会崩溃或静默跳过
- **Pros:** 测试稳定性提升，边缘情况覆盖完整
- **Cons:** 需要区分"空文件"和"解析失败"
- **Context:** Semantic golden master 的 `parse_analysis_result()` 辅助函数。在 `tests/integration/core/test_golden_master_regression.py` 中使用
- **Depends on:** Semantic Golden Master Tests 实现
- **Effort:** S (human: ~30min / CC: ~5min)

### **Priority:** P0
~~**Fix golden master test infrastructure before Grammar Coverage implementation**~~
**Completed:** v1.10.6 (2026-04-04)

---

## Core — Edge Cases & Error Handling

~~**Initialize session directory on first use**~~
**Completed:** Already implemented — `save_to_audit_log()` uses `mkdir(parents=True, exist_ok=True)`

~~**Prevent session ID collisions**~~
**Completed:** Already implemented — session_id format is `{YYYYMMDD-HHMMSS}-{uuid4}`

### **Priority:** P1
**Handle replay of deleted files**
- **What:** 文件已删除时，显示清晰错误：\"File {path} was deleted (use --checkout-commit to restore)\"
- **Why:** 当前 plan 仅处理文件变化，未处理文件删除
- **Pros:** 用户体验提升，错误信息可操作
- **Cons:** 需要区分"不存在"和"从未存在"
- **Context:** `tsa replay` CLI 命令，在 Session replay 逻辑中检查 file_hashes
- **Depends on:** Analysis Sessions 实现
- **Effort:** S (human: ~1h / CC: ~10min)

### **Priority:** P1
**Support multi-format parsing in parse_analysis_result()**
- **What:** 根据输出格式自动选择解析器（TOON / JSON / CSV）
- **Why:** Semantic tests 需要支持所有 3 种输出格式
- **Pros:** 测试覆盖完整，不依赖单一格式
- **Cons:** 增加解析复杂度（需要 3 个解析逻辑）
- **Context:** `parse_analysis_result()` 在 semantic golden master 辅助模块中。当前 plan 未明确格式检测逻辑
- **Depends on:** Semantic Golden Master Tests 实现
- **Effort:** M (human: ~3h / CC: ~20min)

### **Priority:** P2
**Handle parameter order semantic equivalence**
- **What:** 判断 `f(a, b)` vs `f(b, a)` 在有默认参数时的语义等价性
- **Why:** 参数重排序不应破坏 semantic golden master tests
- **Pros:** 测试更健壮，容忍良性变化
- **Cons:** 需要深度静态分析（复杂）
- **Context:** StructuredResult.get_params() 比较逻辑。CEO plan 已 defer 到 Phase 1-2-3 迁移完成后
- **Depends on:** Semantic Golden Master Tests Phase 3 完成
- **Effort:** M (human: ~1 day / CC: ~1h)

### **Priority:** P2
**Add file watcher debounce mechanism**
- **What:** 300ms debounce window，收集连续文件变化事件，批量更新索引
- **Why:** 编译/test watch 场景会产生高频事件，导致 daemon 抖动
- **Pros:** 性能提升，减少无效索引更新
- **Cons:** 增加事件队列管理复杂度
- **Context:** `file_watcher.py` 的事件处理循环。Plan 提及降级到轮询但未明确 debounce
- **Depends on:** Daemon Architecture 实现
- **Effort:** S (human: ~2h / CC: ~15min)

### **Priority:** P2
**Update tool descriptions for intent-based naming**
- **What:** 为 6 个 MCP 工具更新 description 字段，强调意图而非实现
- **Why:** AI 代理依赖描述匹配工具，意图导向提升选择准确率
- **Pros:** 用户 prompt 更简洁，工具发现能力提升
- **Cons:** 需要重写 6 个工具的描述文案
- **Context:** `server.py` 中每个工具的 `get_tool_definition()` 方法。CEO plan 建议但未强制
- **Depends on:** Intent-Based Tool Aliases 实现
- **Effort:** S (human: ~1h / CC: ~10min)

---

## Performance Optimizations

### **Priority:** P2
**Async SHA256 hash calculation for sessions**
- **What:** 使用 ThreadPoolExecutor 批量并行计算文件 hash
- **Why:** 100 个文件 × 10ms = 1 秒阻塞主线程
- **Pros:** session 保存速度提升 10x
- **Cons:** 增加异步复杂度（需要 await）
- **Context:** `AnalysisSession.save_to_audit_log()` 中对每个 input_files 计算 SHA256。Section 4 Performance Review 发现 N+1 pattern
- **Depends on:** Analysis Sessions 实现
- **Effort:** S (human: ~1h / CC: ~10min)

### **Priority:** P2
**Cache file hash by mtime**
- **What:** 维护 {file_path: (mtime, hash)} 缓存，mtime 未变则复用 hash
- **Why:** 重复分析同一文件时避免重新计算 hash
- **Pros:** session 创建速度提升（同一工作流内多个 session）
- **Cons:** 需要缓存失效逻辑
- **Context:** Hash 计算在 `AnalysisSession.__init__()` 和 replay 流程中。Section 4 推荐缓存
- **Depends on:** Analysis Sessions 实现
- **Effort:** S (human: ~1.5h / CC: ~12min)

~~**Cache git commit hash for 5 seconds**~~
**Completed:** v1.10.6 (2026-04-05) — module-level `_git_commit_cache` with 5s TTL

### **Priority:** P2
**Optimize parse_analysis_result() with tree-sitter**
- **What:** 复用现有 tree-sitter 解析器一次性解析整个输出，而非逐函数字符串解析
- **Why:** 50 个函数 × 字符串解析 = N+1 pattern
- **Pros:** 解析速度提升 5-10x
- **Cons:** 需要为 TOON/JSON/CSV 编写 tree-sitter query
- **Context:** `parse_analysis_result()` 在 semantic golden master 辅助模块中。Section 4 Performance Review 发现 N+1
- **Depends on:** Semantic Golden Master Tests 实现
- **Effort:** M (human: ~4h / CC: ~25min)

### **Priority:** P2
**Benchmark universal traversal performance vs whitelist**
- **What:** For each of 6 plugins migrated to universal traversal, benchmark large file parsing (1000+ LOC) and compare to whitelist baseline
- **Why:** CEO plan target: <10% performance regression. Must verify this holds in practice.
- **Pros:** Prevents shipping performance regressions, validates architectural assumption
- **Cons:** Adds benchmark infrastructure (15-20 min per language)
- **Context:** Universal traversal visits ALL nodes vs whitelist visiting only container nodes. Could be slower for deeply nested files. Grammar Coverage plan Phase 4 migration (python_plugin.py, javascript_plugin.py, typescript_plugin.py, java_plugin.py, c_plugin.py, cpp_plugin.py)
- **Depends on:** Phase 4 universal traversal migration (Grammar Coverage MECE)
- **Effort:** M (human: ~1 day / CC: ~2h) — 6 plugins × 20 min each
- **Blocking:** Phase 4 completion (Grammar Coverage)

---

## Phase 2 Items (Deferred from CEO Plan)

### **Priority:** P2
**Call Graph + Impact Analysis**
- **What:** 方法级别的调用图分析，回答"改了 method X，哪些地方会受影响？"
- **Why:** GitNexus 有此功能，TSA 缺失。用户需求验证后再实现
- **Pros:** 与 GitNexus 功能对齐，AI context engine 的 table-stakes 能力
- **Cons:** 工作量过大（>1 月），偏离 TSA 差异化（企业安全 + 审计）
- **Context:** CEO plan 明确 defer。Phase 2 重访标准：≥50 个企业用户要求 OR 竞品压力 OR GitNexus API 集成路径成熟
- **Depends on:** Phase 1（Analysis Sessions + Daemon）完成 + 市场反馈
- **Effort:** XL (human: >1 month / CC: ~1 week)
- **Phase 2 trigger conditions:**
  1. ≥50 个企业用户在访谈中明确要求 call graph 功能
  2. 竞品分析显示 call graph 成为 AI context engine 的 table-stakes 能力
  3. GitNexus 提供稳定的 API 集成路径，TSA 可以作为客户端调用

### **Priority:** P3
**Windows Daemon Support (Named Pipe IPC)**
- **What:** 实现 Windows 上的 daemon 通信（named pipe 替代 Unix socket）
- **Why:** Windows 用户无法使用 daemon 性能提升（当前 fallback 到直接模式）
- **Pros:** Windows 用户获得 10-20x 性能提升
- **Cons:** Named pipe 需要不同 API（IOCP/threading model），额外 2-3 周工作量
- **Context:** CEO plan Phase 1 仅支持 Unix/Linux/macOS。Windows 自动降级但功能正常
- **Depends on:** Unix daemon 稳定运行 + Windows 用户反馈性能问题
- **Effort:** L (human: 2-3 weeks / CC: ~3-4 days)

### **Priority:** P3
**Session File Encryption**
- **What:** 加密 `~/.tsa/sessions/*.json` 文件（AES-256）
- **Why:** 企业客户可能要求审计数据加密
- **Pros:** 满足企业合规要求
- **Cons:** 增加密钥管理复杂度，MVP 不需要
- **Context:** Session 文件仅含元数据（文件路径、hash、timestamp），无敏感代码内容。CEO plan defer 到企业客户明确要求
- **Depends on:** Analysis Sessions MVP 稳定 + 企业客户反馈
- **Effort:** S (human: 1-2 days / CC: ~2-3h)

### **Priority:** P3
**Daemon Auto-Restart on Crash (systemd/launchd)**
- **What:** 提供 systemd service file（Linux）和 launchd plist（macOS）用于 daemon 自动重启
- **Why:** 生产环境 daemon 崩溃后需要手动重启
- **Pros:** 提升可用性，减少运维负担
- **Cons:** 增加安装复杂度（需要用户配置 systemd/launchd）
- **Context:** MVP 假设用户手动 `tsa daemon start`。CEO plan defer 到用户反馈稳定性问题
- **Depends on:** Daemon 稳定性数据 + 用户反馈崩溃频率
- **Effort:** M (human: 2-3 days / CC: ~3-4h)

---

## P2: Refactoring & Tech Debt

### **Priority:** P2
**Split python_plugin.py into Multiple Modules**
- **What:** Refactor `python_plugin.py` (~1800 LOC) into multiple focused modules:
  - `python_plugin.py` — Main plugin class, public API
  - `python_extractor.py` — Core extraction logic (functions, classes, variables)
  - `python_expressions.py` — Expression extraction (lambdas, comprehensions, expressions)
  - `python_utils.py` — Helper utilities (signature parsing, text extraction)
- **Why:** Current file violates 800 LOC guideline from CLAUDE.md after Python coverage fix implementation (Wave 2: added 12 expression node types)
- **Pros:** Improved maintainability, follows file size conventions, better code organization
- **Cons:** Requires updating imports in ~30 test files
- **Context:** Python plugin achieved 100% grammar coverage (57/57 node types) after Wave 2 implementation (lambdas, comprehensions, expressions). File size grew from ~1200 to ~1800 LOC. Code is well-tested with 90%+ coverage.
- **Depends on:** Python coverage fix completion (Wave 2 — COMPLETED)
- **Effort:** M (human: 2-3h / CC: ~30min)
- **Risk:** Low (well-tested code, pure refactor, no logic changes)

---

---

## Completed

~~**Fix golden master test infrastructure before Grammar Coverage implementation**~~
**Completed:** v1.10.6 (2026-04-04)

~~**Fix validator O(N×M) matching loop — CI timeout risk**~~
**Completed:** v1.10.6 (2026-04-05) — O(N) line_index build + O(M) lookup

~~**Fix wrapper detection false positives — `body` field in `_WRAPPER_FIELDS`**~~
**Completed:** v1.10.6 (2026-04-05) — removed `body`, decorated_definition now scores correctly

~~**Fix coverage inflation from single-line construct matching**~~
**Completed:** v1.10.6 (2026-04-05) — first-match + skip root nodes

~~**Fix Go plugin double-counting imports**~~
**Completed:** v1.10.6 (2026-04-05) — removed synthetic outer import_declaration

~~**Investigate Python decorated function `start_line` semantics**~~
**Completed:** v1.10.6 (2026-04-05) — start_line=def line, decorator_start_line field added

~~**Fix Rust/Scala/Kotlin recursive traversal stack overflow**~~
**Completed:** v1.10.6 (2026-04-05) — converted to iterative DFS

~~**Split python_plugin.py into Multiple Modules**~~
**Completed:** v1.10.6 (2026-04-05) — python_extractor.py (1599L) + python_plugin.py (386L)

~~**Update tool descriptions for intent-based naming**~~
**Completed:** v1.10.6 (2026-04-05) — 4 MCP tools updated
