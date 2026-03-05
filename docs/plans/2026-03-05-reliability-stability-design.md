# 可靠性与稳定性改进设计文档

**日期:** 2026-03-05
**版本:** 1.0
**状态:** 待审批

---

## 1. 概述

### 1.1 背景

tree-sitter-analyzer 是一个成熟的企业级代码分析工具，支持17种语言、MCP服务器集成、8400+测试。通过4个专业Agent对代码库进行全面分析，发现89个可靠性问题需要解决。

### 1.2 分析方法

采用分层并行分析方法，4个Agent同时分析不同层面：
- **MCP层分析器**: 服务器、工具、错误处理
- **核心引擎分析器**: 解析器、查询、缓存服务
- **CLI层分析器**: 命令、参数验证
- **横切关注点分析器**: 异常、编码、格式化器

### 1.3 问题汇总

| 严重程度 | 数量 | 说明 |
|----------|------|------|
| 🔴 CRITICAL | 7 | 必须立即修复，可能导致崩溃或数据丢失 |
| 🟠 HIGH | 16 | 优先修复，影响系统稳定性 |
| 🟡 MEDIUM | 36 | 中期修复，降低系统健壮性 |
| 🟢 LOW | 30 | 长期改进，代码质量提升 |

---

## 2. 关键问题详情

### 2.1 CRITICAL 问题

#### C-1: 单例模式竞态条件
- **文件**: `tree_sitter_analyzer/core/analysis_engine.py:45-54`
- **问题**: `UnifiedAnalysisEngine` 的单例实现在多线程环境下存在竞态条件
- **影响**: 可能创建多个实例，导致状态不一致
- **修复方案**: 使用 `threading.Lock` 保护实例创建

```python
# 修复前
def __new__(cls, project_root: str | None = None):
    instance_key = project_root or "default"
    if instance_key not in cls._instances:
        with cls._lock:
            if instance_key not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[instance_key] = instance
                instance._initialized = False  # 在锁外设置
    return cls._instances[instance_key]

# 修复后
def __new__(cls, project_root: str | None = None):
    instance_key = project_root or "default"
    with cls._lock:
        if instance_key not in cls._instances:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instances[instance_key] = instance
    return cls._instances[instance_key]
```

#### C-2: 嵌套事件循环问题
- **文件**: `tree_sitter_analyzer/core/analysis_engine.py:298-320`
- **问题**: `analyze_code_sync` 在已有事件循环时使用 `ThreadPoolExecutor` 调用 `asyncio.run()`
- **影响**: 可能导致死锁或性能问题
- **修复方案**: 文档化异步优先，或使用 `nest_asyncio` 库

#### C-3: 非Java文件静默数据丢失
- **文件**: `tree_sitter_analyzer/mcp/tools/analyze_scale_tool.py:454`
- **问题**: 非Java文件分析返回 `None` 和空字典，静默丢失数据
- **影响**: 用户收到空结果，无错误提示
- **修复方案**: 实现通用分析或抛出明确错误

```python
# 修复前
analysis_result = None  # 占位符
structural_overview = {}  # 占位符

# 修复后
if language != "java":
    raise AnalysisError(
        f"Structural analysis not yet supported for {language}. "
        "Use analyze_code_structure tool instead.",
        operation="analyze_scale"
    )
```

#### C-4: 自定义contextlib遮蔽标准库
- **文件**: `tree_sitter_analyzer/mcp/tools/fd_rg_utils.py:124,631-645`
- **问题**: 文件定义了自己的 `contextlib` 类，遮蔽标准库
- **影响**: 潜在的导入问题和维护困难
- **修复方案**: 从标准库导入 `contextlib`

#### C-5: PartialReadCommand 缺少安全验证
- **文件**: `tree_sitter_analyzer/cli/commands/partial_read_command.py:34-50`
- **问题**: `validate_file()` 未执行路径遍历检查
- **影响**: 潜在的路径遍历攻击
- **修复方案**: 使用 `SecurityValidator` 进行安全检查

#### C-6: 批量操作退出码不一致
- **文件**: `tree_sitter_analyzer/cli_main.py:389,421`
- **问题**: 部分成功时也返回退出码1
- **影响**: 脚本可能误判执行结果
- **修复方案**: 根据失败比例或 `--fail-fast` 标志区分退出码

#### C-7: 顶层异常处理过于宽泛
- **文件**: `tree_sitter_analyzer/cli_main.py:647-649`
- **问题**: 捕获所有异常并隐藏详细信息
- **影响**: 调试困难
- **修复方案**: 记录完整堆栈跟踪到日志

---

### 2.2 HIGH 问题

#### H-1: 无文件大小限制
- **文件**: `tree_sitter_analyzer/core/parser.py:106-131`
- **修复**: 添加可配置的文件大小限制（默认10MB）

#### H-2: 类级别可变缓存共享
- **文件**: `tree_sitter_analyzer/core/parser.py:55`
- **修复**: 使缓存实例级别或添加线程同步

#### H-3: 无界递归遍历
- **文件**: `tree_sitter_analyzer/core/parser.py:280-298`, `query_service.py:262-271`
- **修复**: 转换为迭代遍历

#### H-4: SharedCache 单例竞态
- **文件**: `tree_sitter_analyzer/mcp/utils/shared_cache.py:12-18`
- **修复**: 使用 `@functools.cache` 或线程锁

#### H-5: 无界缓存增长
- **文件**: `tree_sitter_analyzer/mcp/utils/shared_cache.py`, `error_handler.py:154-156`
- **修复**: 实现LRU驱逐和TTL

---

## 3. 解决方案架构

### 3.1 分阶段实施

```
Phase 1: 关键修复 (第1周)
├── P1-1: 线程安全单例模式
├── P1-2: 修复静默数据丢失
├── P1-3: 安全验证增强
└── P1-4: 异常处理改进

Phase 2: 高优先级修复 (第2周)
├── P2-1: 内存安全（文件大小限制）
├── P2-2: 递归转迭代
├── P2-3: 事件循环处理
└── P2-4: 缓存大小限制

Phase 3: 中优先级修复 (第3周)
├── P3-1: 输入验证标准化
├── P3-2: 错误消息格式统一
├── P3-3: 缓存失效策略
└── P3-4: 资源清理
```

### 3.2 组件交互

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Layer                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ CLI Main    │  │ Commands    │  │ Argument Validator  │  │
│  │ (exit codes)│  │ (security)  │  │ (comprehensive)     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      MCP Layer                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Server      │  │ Tools       │  │ SharedCache         │  │
│  │ (error resp)│  │ (validation)│  │ (thread-safe, LRU)  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Core Engine                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Analysis    │  │ Parser      │  │ Cache Service       │  │
│  │ Engine      │  │ (size limit)│  │ (invalidation)      │  │
│  │ (singleton) │  │ (iterative) │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Cross-Cutting                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Exceptions  │  │ Encoding    │  │ Formatters          │  │
│  │ (hierarchy) │  │ (cache TTL) │  │ (explicit init)     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 测试策略

### 4.1 TDD 工作流

每个修复遵循严格的 TDD 流程：

```
1. RED: 编写失败的测试
   └── 测试应验证问题存在

2. GREEN: 实现最小修复
   └── 只修改使测试通过的代码

3. REFACTOR: 重构改进
   └── 在测试保护下优化代码

4. VERIFY: 验证覆盖率
   └── 确保新增代码有80%+覆盖率
```

### 4.2 测试类型

| 类型 | 目标 | 工具 |
|------|------|------|
| 单元测试 | 单个函数/类 | pytest |
| 集成测试 | 组件交互 | pytest + fixtures |
| 并发测试 | 线程安全 | pytest + threading |
| 压力测试 | 内存/性能 | pytest-benchmark |

### 4.3 测试覆盖目标

- 新增代码: 80%+ 覆盖率
- 修改的现有代码: 保持或提高现有覆盖率
- 关键路径: 100% 覆盖率

---

## 5. 风险评估

### 5.1 风险矩阵

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 单例修改破坏现有行为 | 中 | 高 | 全面的回归测试 |
| 缓存策略变更影响性能 | 中 | 中 | 性能基准测试 |
| 递归转迭代引入bug | 低 | 中 | 逐步迁移+对比测试 |
| 新验证拒绝合法输入 | 低 | 高 | 边界条件测试 |

### 5.2 回滚计划

- 每个阶段独立提交
- 使用功能开关控制新行为
- 维护详细的变更日志

---

## 6. 验收标准

### 6.1 Phase 1 验收标准

- [ ] 所有单例模式线程安全
- [ ] 非Java文件分析返回明确错误
- [ ] PartialReadCommand 通过安全验证
- [ ] 批量操作退出码正确
- [ ] 顶层异常记录完整信息

### 6.2 Phase 2 验收标准

- [ ] 文件大小限制可配置且生效
- [ ] 无递归深度超限错误
- [ ] 缓存有大小限制和驱逐策略
- [ ] 所有现有测试通过

### 6.3 Phase 3 验收标准

- [ ] 输入验证一致
- [ ] 错误消息格式统一
- [ ] 缓存基于文件修改时间失效
- [ ] 代码覆盖率 ≥ 80%

---

## 7. 附录

### A. 问题清单完整版

详见各Agent分析报告。

### B. 参考文档

- Python threading: https://docs.python.org/3/library/threading.html
- asyncio 最佳实践: https://docs.python.org/3/library/asyncio.html
- pytest 文档: https://docs.pytest.org/

### C. 变更历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2026-03-05 | Agent Team | 初始设计文档 |
