# V2 AI Autonomous Development Protocol

> **一句话**: AI 读完此文件后，说"全自动开发"即可启动完整闭环。无需任何额外指令。

---

## 核心理念

```
用户只需说一句话 → AI 自动完成从需求到发布的全部流程
所有代码必须通过 10 位顶级专家评审，指摘为零方可结束
```

本协议将 **8 个角色**、**10 位全球顶级专家评审团**、**Spec 驱动**、**TDD 红绿重构**、**指摘归零闭环** 融合为一个自驱动闭环。
每轮循环由 AI 自主决策、自主执行、自主验证，无需人工干预。

**核心铁律**: 代码必须在"10 位专家全员零指摘"的状态下才能通过 STEP 4→6 关卡。任何一位专家有任何一条指摘，都必须回到 STEP 5 修复后重新评审。

---

## 闭环架构总览

```
                         ┌────────────────────────────┐
                         │     Product Owner          │ STEP 1
                         │  扫描能力缺口 → 定义 Sprint │
                         └─────────────┬──────────────┘
                                       │ .kiro/specs/{feature}/requirements.md
                                       ▼
                         ┌────────────────────────────┐
                         │       Architect             │ STEP 2
                         │  设计方案 → 拆解任务         │
                         └─────────────┬──────────────┘
                                       │ design.md + tasks.md
                                       ▼
              ┌─────────────────────────────────────────────────┐
              │               TDD LOOP (Worker)                 │ STEP 3
              │                                                 │
              │   RED ──► GREEN ──► REFACTOR                    │
              │   写失败    实现功能   Ruff+Mypy                 │
              │   测试     通过测试    清理代码                   │
              │                                                 │
              └─────────────────────────┬───────────────────────┘
                                        │ 代码 + 测试
                                        ▼
              ┌═══════════════════════════════════════════════════════════════┐
              ║         STEP 4 ←→ STEP 5  指摘归零闭环 (ZERO SHITEKI LOOP)  ║
              ║                                                             ║
              ║   ┌──────────────────────────────────┐                      ║
              ║   │  10 Global Expert Panel Review    │ STEP 4              ║
              ║   │  10 位全球顶级专家联合评审          │                      ║
              ║   │  → 每位专家独立评审 → 输出指摘清单   │                      ║
              ║   └──────────────┬───────────────────┘                      ║
              ║                  │                                          ║
              ║          ┌───────┴───────┐                                  ║
              ║          │  指摘 > 0 ?   │                                  ║
              ║          └───┬───────┬───┘                                  ║
              ║          YES │       │ NO (全员零指摘 → 通过!)               ║
              ║              ▼       │                                      ║
              ║   ┌──────────────────┴───────────────┐                      ║
              ║   │   TDD LOOP #2 (Worker)           │ STEP 5              ║
              ║   │   修复全部指摘                     │                      ║
              ║   │   RED → GREEN → REFACTOR          │                      ║
              ║   └──────────────┬───────────────────┘                      ║
              ║                  │ 重新提交到 STEP 4 ──────┘                 ║
              ║                                                             ║
              ╚═════════════════════════════════════════╤═══════════════════╝
                                                        │ 零指摘认证通过
                                                        ▼
                         ┌────────────────────────────┐
                         │      QA Strategist          │ STEP 6
                         │  边界测试 + 回归验证          │
                         └─────────────┬──────────────┘
                                       │ 质量报告
                                       ▼
                         ┌────────────────────────────┐
                         │    Technical Writer          │ STEP 7
                         │  更新 Spec + Progress        │
                         └─────────────┬──────────────┘
                                       │ 文档
                                       ▼
                         ┌────────────────────────────┐
                         │     DevOps Engineer          │ STEP 8
                         │  全量测试 → 自动演示          │
                         └─────────────┬──────────────┘
                                       │ 演示结果 + 版本报告
                                       ▼
                         ┌────────────────────────────┐
                         │     Product Owner            │ → STEP 1
                         │  根据演示结果规划下一轮       │
                         └────────────────────────────┘
```

---

## 触发方式

用户说以下任意一句话，AI **立即**启动完整闭环，无需追问：

| 触发词 | 行为 |
|--------|------|
| "全自动开发" | 启动完整 8 步闭环（含专家评审指摘归零） |
| "继续开发" / "继续全自动" | 从上次暂停的步骤继续 |
| "全自动迭代" | 执行一轮完整闭环后，自动启动下一轮 |
| "执行 Sprint" | 等同于"全自动开发" |
| "批评并重构" | 仅执行 STEP 4-5 指摘归零闭环 |
| "专家评审" | 仅执行 STEP 4（10 位专家评审，输出指摘清单） |
| "演示当前能力" | 仅执行 STEP 8 (DevOps 演示) |

---

## STEP 1: Product Owner (产品负责人)

### 执行动作
1. **读取当前状态**:
   - 读取 `.kiro/specs/` 下所有活跃 spec 的 tasks.md，找到 `pending` 任务
   - 运行 `uv run pytest tests/ --co -q` 统计测试数
   - 检查 ROADMAP.md 中的优先级
2. **分析能力缺口**:
   - 运行代码扫描（`ProjectCodeMap.scan`）对真实项目进行分析
   - 对比竞品能力（tree-sitter-cli, ast-grep, semgrep, CodeScene）
   - 识别用户痛点（误报、漏报、性能瓶颈）
3. **输出 Sprint 决策**:
   - 创建 `.kiro/specs/{feature-name}/requirements.md`
   - 定义验收标准（量化的、可自动验证的）
   - 按"用户价值 / 实现成本"排序

### 决策框架

```
价值评估 = (痛点严重度 × 影响用户数) / 实现复杂度

优先级:
  P0: 价值 > 8, 影响核心功能 → 必须本轮完成
  P1: 价值 5-8, 提升用户体验 → 尽量本轮完成
  P2: 价值 < 5, 锦上添花 → 下轮考虑
```

### 输出文件
- `.kiro/specs/{feature}/requirements.md`

---

## STEP 2: Architect (架构师)

### 执行动作
1. **阅读需求**: 读取 STEP 1 的 requirements.md
2. **分析现有代码**:
   - 读取需要修改的源文件
   - 理解当前数据结构和接口
   - 评估影响范围（用 `impact_analysis` 如果已可用）
3. **设计方案**:
   - 画出数据流（文字版或 Mermaid）
   - 定义新的数据结构和方法签名
   - 列出改动文件清单
4. **拆解任务**:
   - 每个任务 ≤ 30 分钟可完成
   - 每个任务有明确的验收标准
   - 任务间有清晰的依赖关系

### 输出文件
- `.kiro/specs/{feature}/design.md` (或 `design-phase{N}-{component}.md`)
- `.kiro/specs/{feature}/tasks.md` (或 `task-phase{N}-{component}.md`)

### 任务模板

```markdown
| Task | Status | Files | Acceptance |
|------|--------|-------|------------|
| T1: 定义数据结构 | pending | `core/xxx.py` | 类型检查通过 |
| T2: 实现核心逻辑 | pending | `core/xxx.py` | 单元测试通过 |
| T3: 集成到入口 | pending | `core/xxx.py` | 集成测试通过 |
```

---

## STEP 3: Worker — TDD Loop #1 (实施者)

### 执行流程

#### Phase RED: 先写失败测试

```
1. 为每个任务写 ≥2 个测试用例
2. 测试覆盖:
   - 正常路径 (happy path)
   - 至少一个边界条件
3. 运行测试 → 确认全部 FAIL
4. 记录: "RED: X/Y tests failing as expected"
```

#### Phase GREEN: 最小实现

```
1. 写最少代码让所有测试通过
2. 不追求完美，只追求正确
3. 运行测试 → 确认全部 PASS
4. 记录: "GREEN: X/Y tests passing"
```

#### Phase REFACTOR: 清理

```
1. 运行 Ruff: uv run ruff check {file} --fix
2. 运行 Mypy: uv run mypy {file} --ignore-missing-imports
3. 修复所有 lint/type 错误
4. 确认测试仍然通过
5. 记录: "REFACTOR: Ruff 0 errors, Mypy 0 errors"
```

### 关键规则
- **禁止跳过 RED**: 必须先看到测试失败才能写实现
- **禁止过度实现**: GREEN 阶段只写让测试通过的最少代码
- **禁止忽略 lint**: REFACTOR 阶段必须 Ruff + Mypy 零错误

---

## STEP 4: 10 Global Expert Panel Review (10 位全球顶级专家联合评审)

> **这是本协议的核心关卡。** 每次代码变更后，AI 必须模拟 10 位全球最顶尖的架构师/设计师，
> 从各自的专业领域对代码进行独立评审。只有当 **全部 10 位专家的指摘（指摘）数为零** 时，
> 代码才能通过此关卡进入 STEP 6。任何一位专家的任何一条指摘，都会触发 STEP 5 修复循环。

### 10 位评审专家及其专业领域

| # | 专家 | 领域 | 评审聚焦点 | 严厉度 |
|---|------|------|-----------|--------|
| 1 | **Martin Fowler** | 重构与代码坏味道 | God Object、Feature Envy、Shotgun Surgery、Long Method、过度耦合 | ★★★★★ |
| 2 | **Robert C. Martin (Uncle Bob)** | SOLID 原则 | SRP 违反、OCP 违反、DIP 违反、ISP 违反、LSP 违反、Clean Code | ★★★★★ |
| 3 | **Eric Evans** | 领域驱动设计 (DDD) | 贫血模型、Bounded Context 泄漏、Ubiquitous Language 缺失、聚合根设计 | ★★★★☆ |
| 4 | **Sam Newman** | 微服务与模块边界 | 模块耦合度、循环依赖、API 契约、服务边界划分 | ★★★★☆ |
| 5 | **Gregor Hohpe** | 集成模式与 API 设计 | 接口一致性、版本策略、错误传播、契约测试缺失 | ★★★★☆ |
| 6 | **Brendan Burns** | 可扩展性与并发 | 线程安全、资源泄漏、扩展性瓶颈、缓存策略 | ★★★★★ |
| 7 | **Titus Winters** | 大规模代码演进 | API 兼容性、类型系统滥用、技术债积累、代码生命周期 | ★★★★☆ |
| 8 | **Kelsey Hightower** | 运维与可观测性 | 日志完整性、错误处理、配置管理、部署就绪度 | ★★★☆☆ |
| 9 | **Jessica Kerr** | 系统思维与复杂性 | 认知负荷、命名语义、抽象泄漏、系统耦合的涌现行为 | ★★★★☆ |
| 10 | **Linus Torvalds** | 性能与工程纪律 | O(n²) 隐患、不必要的抽象、内存浪费、过度工程、代码膨胀 | ★★★★★ |

### 评审维度矩阵（全部必须检查）

每位专家必须从以下 7 个维度进行评审，不允许跳过：

| 维度 | 检查内容 | 主审专家 | 严重度 |
|------|---------|---------|--------|
| **正确性** | 逻辑漏洞、边界遗漏、并发问题、竞态条件 | Burns, Uncle Bob | Critical |
| **架构** | 职责划分、耦合度、依赖方向、模块边界 | Fowler, Newman, Evans | Critical |
| **性能** | O(n²) 隐患、不必要的内存分配、缓存缺失、热路径优化 | Torvalds, Burns | High |
| **可扩展性** | 硬编码、紧耦合、违反 OCP、扩展点设计 | Uncle Bob, Hohpe | High |
| **API 设计** | 命名一致性、参数合理性、返回值语义、契约明确性 | Hohpe, Winters | Medium |
| **可维护性** | 认知负荷、命名语义、代码可读性、测试质量 | Kerr, Fowler | Medium |
| **运维就绪** | 日志、错误处理、配置管理、安全、可观测性 | Hightower | Medium |

### ⚠️ 已知阻塞问题 (P0 运维)

| 问题 | 根因 | 解决方案 |
|------|------|---------|
| **覆盖率检测长时间不结束** | `uv run pytest --cov` 在 Windows 上超过 600s，阻塞 STEP 6/8 | **DevOps 必须使用 `--no-cov --ignore=tests/benchmarks`**，覆盖率单独在 CI 收集 |
| **pytest 挂起** | benchmark 测试或 coverage 插件导致进程无响应 | 设置 `--timeout=120`，挂起时 `Stop-Process` 终止 |

**STEP 6/8 的测试命令必须为**:
```bash
uv run pytest tests/ -v --tb=short --no-cov --ignore=tests/benchmarks --timeout=120
```

---

### 🔴 评审失败根因分析 & 防护机制

**历史教训**: 内置专家评审曾输出"零指摘"的虚假结果，原因如下:

| # | 根因 | 防护措施 |
|---|------|---------|
| 1 | **未重读代码** — 评审时不重新读取源文件，凭记忆审查 | **强制前置代码重读** (见下方清单) |
| 2 | **自我审查认知偏差** — 同一 AI 写完代码立刻审查，确认偏差极强 | **心智重置**: 评审前必须声明"我现在是独立审计员，不是实现者" |
| 3 | **标准抽象无量化** — "检查 God Object" 但不实际测量行数 | **量化检查项**: 每项必须有数字门槛 |
| 4 | **无可勾选清单** — 7 维度太抽象，容易敷衍 | **强制检查清单**: 逐条打勾，每条必须有文件:行号证据 |
| 5 | **覆盖率超时** — DevOps 步骤因 `--cov` 阻塞 >600s | 见上方"已知阻塞问题" |

---

### 🔒 强制前置代码重读 (MANDATORY PRE-REVIEW CODE READING)

> **铁律**: 评审开始前，AI 必须重新读取所有在本 Sprint 中修改/创建的源文件。
> 不读代码就做评审 = 无效评审。没有例外。

```
PRE_REVIEW_CHECKLIST (在任何专家发言之前完成):

□ 1. 列出本 Sprint 所有修改/新建的源文件清单
□ 2. 对每个文件执行 Read 工具读取完整内容
□ 3. 记录每个文件的行数、类数、函数数
□ 4. 记录所有 `type: ignore` 出现位置
□ 5. 记录所有 `# type: ignore` 和 `object` 类型标注
□ 6. 检查 import 图: 哪些 core/ 文件 import 了 graph/ 或 mcp/
□ 7. 识别所有 >300 行的文件、>50 行的函数
□ 8. 以上数据记录到 progress.md，作为评审证据

只有以上 8 项全部完成，才能开始专家评审。
```

---

### 📋 每位专家的具体量化检查清单

> 替代原来的"7 个抽象维度"。每位专家必须逐条检查，每条必须给出证据或标注 N/A。

**Martin Fowler 检查清单 (重构)**:
- □ 是否有文件 > 500 行? 列出文件名和行数
- □ 是否有函数/方法 > 50 行? 列出名称和行数
- □ 是否有重复代码? 指出哪两段代码重复
- □ 是否有 Feature Envy? 函数过度使用另一个类的数据
- □ 是否有 Shotgun Surgery? 一个改动需要修改多个文件

**Robert C. Martin 检查清单 (SOLID)**:
- □ SRP: 每个类是否只有一个变更原因? 标注违反者
- □ OCP: 是否有需要修改源码才能扩展的地方?
- □ DIP: core/ 是否直接 import 了 graph/ 或具体实现?
- □ 所有函数参数类型是否明确? 标注所有 `object` 和 `Any` 类型参数
- □ 是否有 `type: ignore` 注释? 每个都需要解释为什么不能消除

**Eric Evans 检查清单 (DDD)**:
- □ 核心数据是否用 `dict[str, Any]` 传递? 应为 TypedDict 或 dataclass
- □ `ModuleInfo.classes/functions/imports` 的类型是否精确?
- □ 是否存在贫血模型 (只有数据没有行为)?

**Sam Newman 检查清单 (模块边界)**:
- □ 是否存在循环依赖? 画出 import 关系
- □ core → graph → mcp 的依赖方向是否正确?
- □ 模块间 API 是否通过 Protocol/ABC 定义?

**Gregor Hohpe 检查清单 (API 设计)**:
- □ MCP 工具返回类型是否统一? 所有 handler 是否返回相同结构?
- □ 错误处理是否用 `bool` 而非异常/Result?
- □ 函数返回类型是否为 `Any`? 列出所有 `-> Any` 或 `-> dict[str, Any]`

**Brendan Burns 检查清单 (并发与扩展)**:
- □ 线程间共享可变状态是否有保护?
- □ 文件句柄/连接是否正确关闭?
- □ ThreadPoolExecutor 的 max_workers 是否可配置?

**Titus Winters 检查清单 (代码演进)**:
- □ 是否有死代码? 函数已定义但永远不会被调用
- □ TypedDict 的 `total` 参数是否合理? 核心字段应 `total=True`
- □ 公开 API 是否向后兼容?

**Kelsey Hightower 检查清单 (运维)**:
- □ 是否有 `except Exception: pass` 吞异常?
- □ 关键操作是否有日志? (scan 开始/结束、cache 命中/miss)
- □ 测试是否能在 120s 内完成? 是否有超时保护?

**Jessica Kerr 检查清单 (认知负荷)**:
- □ 是否有函数认知复杂度 > 15?
- □ 函数名是否语义明确? 是否有 >30 字符或 <3 字符的?
- □ 嵌套层级是否 > 3?

**Linus Torvalds 检查清单 (性能)**:
- □ 是否有 O(n²) 隐患? (嵌套循环、对列表做线性查找)
- □ 是否有不必要的抽象层? (间接调用 > 3 层)
- □ 是否有重复遍历? (同一个集合被遍历多次做不同事情)

---

### 评审执行流程

```
STEP 0 (强制): 执行"强制前置代码重读"清单，记录到 progress.md
STEP 0.5 (心智重置): AI 声明 — "我现在是独立审计员。我要找出所有问题。"

FOR each_expert IN 10_experts:
    1. AI 切换到该专家的思维模式和严厉标准
    2. 逐条执行该专家的"量化检查清单"（见上方）
    3. 对每个发现的问题，输出:
       - 问题描述（一句话）
       - 问题位置（文件:行号）— 必须有具体代码引用
       - 严重度（Critical / High / Medium / Low）
       - 具体修复方案（代码级别的建议）
       - 量化证据（行数、计数、import 链等）
    4. 最终给出该专家的裁定:
       ✅ APPROVED (零指摘) 或
       ❌ REJECTED (附指摘清单)
    
    ⚠️ 如果该专家 APPROVED 但检查清单有未勾选项 → 无效，必须补充
```

### 评审输出格式（必须严格遵循）

```markdown
## 10 Global Expert Panel Review Report — Round {N}

### 评审摘要

| # | 专家 | 裁定 | 指摘数 | Critical | High | Medium | Low |
|---|------|------|--------|----------|------|--------|-----|
| 1 | Martin Fowler | ❌ REJECTED | 3 | 1 | 1 | 1 | 0 |
| 2 | Robert C. Martin | ✅ APPROVED | 0 | 0 | 0 | 0 | 0 |
| ... | ... | ... | ... | ... | ... | ... | ... |

**总计**: {N} 位专家 APPROVED, {M} 位专家 REJECTED, 共 {X} 条指摘
**裁定**: ❌ 未通过 (需修复后重新评审) / ✅ 全员通过 (进入 STEP 6)

---

### 专家 1: Martin Fowler — 重构与代码坏味道

**裁定**: ❌ REJECTED (3 条指摘)

| # | 严重度 | 问题 | 位置 | 修复方案 |
|---|--------|------|------|---------|
| F-1 | Critical | God Object: XxxClass 超过 500 行 | `core/xxx.py` | 拆分为 3 个职责类 |
| F-2 | High | Feature Envy: method_a 过度依赖 ClassB | `core/xxx.py:42` | 移动到 ClassB |
| F-3 | Medium | Magic Number: 阈值 50 应命名为常量 | `core/xxx.py:128` | 抽取为 MAX_DEPTH = 50 |

---

### 专家 2: Robert C. Martin — SOLID 原则

**裁定**: ✅ APPROVED (0 条指摘)

> "代码清晰遵循 SRP，每个模块职责明确。"

---

... (所有 10 位专家)

---

### 指摘汇总（按优先级排序）

| 优先级 | 指摘ID | 专家 | 严重度 | 问题 | 修复方案 |
|--------|--------|------|--------|------|---------|
| P0 | F-1 | Fowler | Critical | God Object | 拆分职责类 |
| P0 | B-2 | Burns | Critical | 线程不安全 | 添加锁 |
| P1 | F-2 | Fowler | High | Feature Envy | 移动方法 |
| P2 | F-3 | Fowler | Medium | Magic Number | 抽取常量 |
```

### 指摘严重度与处理规则

| 严重度 | 处理 | 是否阻塞通过 |
|--------|------|-------------|
| Critical | 必须立即修复，STEP 5 中 P0 处理 | **是 — 必须修复** |
| High | 必须本轮修复，STEP 5 中 P1 处理 | **是 — 必须修复** |
| Medium | 应当本轮修复，STEP 5 中 P2 处理 | **是 — 必须修复（指摘归零要求）** |
| Low | 记录并在下一个 Sprint 处理 | **否 — 唯一可豁免的级别** |

> **注意**: 与传统 P0/P1/P2 不同，本协议要求 **Critical + High + Medium 全部归零** 才能通过。
> 只有 Low 级别的指摘可以延期，但必须记录到 tasks.md 中追踪。

### 评审质量标准（专家行为准则）

- **绝不敷衍**: 每位专家必须从其专业领域深入审查，不允许"看起来还行"的空评价
- **必须具体**: 每条指摘必须指向具体文件和行号，附带代码级修复方案
- **量化衡量**: 用数字说话（"这个类 1485 行，应低于 300 行"而非"太大了"）
- **独立评审**: 每位专家独立给出评判，不受其他专家影响
- **公正严厉**: 不因"已经改进过"就降低标准；以行业最高标准为基线
- **实战检验**: 评审应基于代码在真实项目上的表现，而非仅看代码本身

### 指摘归零闭环（Zero Shiteki Loop）

```python
round_number = 1
while True:
    # STEP 4: 10 位专家评审
    review_report = expert_panel_review(code, round=round_number)

    # 统计非 Low 指摘数
    blocking_shiteki = sum(
        1 for s in review_report.all_shiteki
        if s.severity in ("Critical", "High", "Medium")
    )

    if blocking_shiteki == 0:
        print(f"✅ 全员通过! Round {round_number}, 零指摘 (Low 除外)")
        break  # → 进入 STEP 6

    print(f"❌ Round {round_number}: {blocking_shiteki} 条阻塞性指摘")

    # STEP 5: Worker 修复
    fix_all_shiteki(review_report.blocking_shiteki)  # TDD: RED → GREEN → REFACTOR

    round_number += 1

    # 安全阀: 防止无限循环
    if round_number > 5:
        print("⚠️ 已迭代 5 轮仍有指摘，输出剩余问题清单，请求人工决策")
        break
```

### 安全阀机制

- **最大迭代轮数**: 5 轮（超过 5 轮仍有指摘时，暂停并输出诊断报告）
- **每轮收敛检查**: 如果连续 2 轮指摘数没有减少，输出警告并分析原因
- **耗时监控**: 单次评审如果超过预计时间 3x，暂停并报告

---

## STEP 5: Worker — TDD Loop #2 (指摘修复)

> **此步骤在指摘归零闭环内执行，修复完成后自动返回 STEP 4 重新评审。**

### 执行流程
1. 读取 STEP 4 的评审报告
2. 按 P0 (Critical) → P1 (High) → P2 (Medium) 顺序处理
3. 对每个指摘执行完整 TDD 循环:
   - RED: 写一个能暴露该指摘所描述问题的测试
   - GREEN: 实现修复
   - REFACTOR: Ruff + Mypy
4. 每个 Critical 修复后立即运行相关测试套件验证
5. **全部修复完成后 → 自动返回 STEP 4 重新评审**

### 关键规则
- **Critical 全部完成**: 零容忍
- **High 全部完成**: 零容忍
- **Medium 全部完成**: 指摘归零要求
- **Low 记录到 tasks.md**: 标记为 pending，留给下一个 Sprint
- **修复后必须重新评审**: 不能自我判断"已经修好了"，必须回到 STEP 4 让 10 位专家重新审查

---

## STEP 6: QA Strategist (质量策略师)

### 执行动作
1. **边界测试设计**:
   - 空输入、超大输入
   - 同名冲突、循环引用
   - 编码异常（非 UTF-8）
   - 权限问题（只读文件）
2. **回归验证**:
   - 运行全量测试套件
   - 对比覆盖率变化（不允许下降）
   - 检查新增代码的覆盖率（目标 > 85%）
3. **实战验证**:
   - 对真实项目（v1 代码库或其他）运行新功能
   - 检查输出是否合理

### 输出
- 新增 edge case 测试
- 覆盖率报告
- 实战验证结果

---

## STEP 7: Technical Writer (技术文档师)

### 执行动作
1. **更新 Spec 文件**:
   - `tasks.md`: 所有已完成任务标记为 `completed`
   - `progress.md`: 记录本轮会话日志、遇到的问题和解决方案
2. **更新 CHANGELOG**:
   - 按 [Keep a Changelog](https://keepachangelog.com/) 格式追加条目
3. **评估是否需要更新 README**:
   - 新功能是否改变了用户可见行为？
   - 是否需要更新示例？

### 2-Action Rule（强制执行）
> 每执行 2 次非平凡工具调用后，必须更新 `design.md` 或 `progress.md`。
> 防止发现的信息丢失。

---

## STEP 8: DevOps Engineer (运维工程师)

### 执行动作
1. **全量测试** (⚠️ 使用安全命令，禁用覆盖率收集):
   ```bash
   uv run pytest tests/ -v --tb=short --no-cov --ignore=tests/benchmarks --timeout=120
   ```
   - 确认 0 failures
   - ⚠️ **禁止使用 `--cov`**（Windows 上会导致 >600s 超时挂起）
   - 覆盖率由 CI/CD 单独收集，本地开发循环不检查覆盖率
2. **自动演示**:
   - 编写临时演示脚本（`_demo_xxx.py`）
   - 在真实项目上运行新功能
   - 输出量化结果（数字、表格）
   - 运行后删除临时脚本
3. **输出 Sprint 报告**:

```markdown
## Sprint N Complete

| 维度 | 结果 |
|------|------|
| 功能 | {一句话描述} |
| 测试 | {passed}/{total}, {skipped} skipped |
| 覆盖率 | {X}% (vs 上次 {Y}%) |
| Ruff | 0 errors |
| Mypy | 0 errors |
| 演示 | {关键量化指标} |

### 下一轮建议
{PO 视角的下一个优先功能}
```

---

## Spec 文件系统（.kiro 结构）

所有复杂功能（>3 个文件改动）必须使用 Spec 文件驱动：

```
.kiro/specs/{feature-name}/
├── requirements.md     ← STEP 1 (PO)
├── design.md           ← STEP 2 (Architect)
├── tasks.md            ← STEP 2 (Architect) + STEP 7 (Writer) 更新状态
└── progress.md         ← STEP 7 (Writer) 记录每轮日志
```

### 文件生命周期

```
创建 → 活跃开发 → 所有任务 completed → 移到 .kiro/specs/archived/
```

### 命名规则

- 目录名: kebab-case (`code-map-intelligence`, `decorator-awareness`)
- 多阶段功能: `design-phase{N}-{component}.md`, `task-phase{N}-{component}.md`

---

## TDD 严格执行标准

### 红绿重构节奏

```
每个功能点:
  1. RED   → 写 ≥2 个测试 → 运行 → 确认 FAIL → 记录
  2. GREEN → 最小实现 → 运行 → 确认 PASS → 记录
  3. REFACTOR → Ruff + Mypy → 修复 → 确认 PASS → 记录
```

### 测试命名规范

```python
class Test{Feature}:
    def test_{scenario}(self):              # 正常路径
    def test_{edge_case}(self):             # 边界条件
    def test_{error_condition}(self):       # 错误处理
```

### 测试质量要求
- 每个测试只验证一件事
- 测试名清晰表达意图（读测试名就知道测什么）
- 测试之间互相独立（不依赖执行顺序）
- 使用 fixture 共享设置代码
- 断言信息包含诊断数据

---

## 错误处理协议

### 遇到测试失败

```
1. 阅读错误信息
2. 定位根因（不是症状）
3. 修复代码（不是修复测试）
4. 重新运行 → 确认通过
5. 记录到 progress.md:
   | Error | Attempt | Resolution |
   |-------|---------|------------|
   | XXX   | 1       | YYY        |
```

### 遇到 Ruff/Mypy 错误

```
1. ruff check --fix (自动修复)
2. 手动修复剩余项
3. mypy 类型错误 → 添加类型注解或 cast
4. 再次运行确认 0 errors
```

### 遇到全量测试回归

```
1. 定位失败测试
2. 分析是自己的改动导致还是预存问题
3. 如果是自己导致 → 修复实现代码
4. 如果是预存问题 → 记录但不阻塞本轮
```

### 绝对禁止

- 禁止删除或跳过失败的测试来"解决"问题
- 禁止连续 3 次用相同方法重试（必须变换策略）
- 禁止忽略 lint 错误

---

## 多轮连续执行

当用户说"全自动迭代"时，AI 执行以下循环:

```python
while True:
    # STEP 1-3: 需求 → 设计 → 实现
    feature = po_define_sprint()
    architect_design(feature)
    worker_tdd_implement(feature)

    # STEP 4-5: 指摘归零闭环 (核心关卡)
    review_round = 1
    while review_round <= 5:
        report = expert_panel_review_10(code, round=review_round)
        blocking = count_blocking_shiteki(report)  # Critical + High + Medium
        if blocking == 0:
            break  # ✅ 全员零指摘 → 通过!
        worker_fix_all_shiteki(report)
        review_round += 1

    # STEP 6-8: 质量验证 → 文档 → 演示
    qa_verify()
    writer_update_docs()
    sprint_result = devops_demo()

    # PO 规划下一轮
    next_feature = po_analyze_gaps(sprint_result)
    if next_feature.value_cost_ratio < 3:
        break  # 价值太低，停止迭代
```

每轮迭代自动:
1. PO 根据上轮演示结果决定下一功能
2. Architect 基于上轮代码状态设计
3. Worker TDD 实现
4. **10 位专家联合评审** ← 核心关卡
5. Worker 修复全部指摘 → 返回 4 重新评审（直到零指摘）
6. QA 验证
7. Writer 记录
8. DevOps 演示

---

## 角色快速参照

| # | 角色 | 类比 | 核心动作 | 输出物 |
|---|------|------|---------|--------|
| 1 | Product Owner | CEO/PM | 扫描缺口 → 定义需求 | requirements.md |
| 2 | Architect | CTO | 设计方案 → 拆解任务 | design.md + tasks.md |
| 3 | Worker (TDD #1) | Senior Dev | RED → GREEN → REFACTOR | 代码 + 测试 |
| **4** | **10 Expert Panel** | **10 位世界级架构师** | **联合评审 → 指摘清单 → 归零闭环** | **评审报告 + 指摘清单** |
| **5** | **Worker (TDD #2)** | **Senior Dev** | **修复全部指摘 → 返回 STEP 4** | **零指摘代码** |
| 6 | QA Strategist | QA Lead | 边界测试 + 回归 | 质量报告 |
| 7 | Technical Writer | DevRel | 更新 Spec + CHANGELOG | 文档 |
| 8 | DevOps Engineer | SRE | 全量测试 + 演示 | Sprint 报告 |

### STEP 4↔5 指摘归零闭环详细流程

```
Round 1:  STEP 4 (评审) → 发现 12 条指摘 → STEP 5 (修复) → 重新提交
Round 2:  STEP 4 (评审) → 发现 3 条指摘  → STEP 5 (修复) → 重新提交
Round 3:  STEP 4 (评审) → 发现 0 条指摘  → ✅ 通过! → STEP 6
```

> **铁律**: 只有当 10 位专家中 **每一位** 的 Critical + High + Medium 指摘都为 0 时，
> 代码才能离开这个闭环。这是整个协议中最严格的质量关卡。

---

## 快速启动命令

```bash
# 启动完整闭环（含 10 专家指摘归零）
"全自动开发"

# 从上次暂停处继续
"继续开发"

# 多轮连续迭代（直到价值耗尽）
"全自动迭代"

# 仅执行 10 位专家评审 + 指摘归零修复
"批评并重构"

# 仅执行 10 位专家评审（不修复，仅输出指摘清单）
"专家评审"

# 仅演示当前能力
"演示当前能力"

# 指定功能开发
"全自动开发 {feature-name}"

# 在真实项目上验证
"用 v2 分析 v1 代码"
```

---

## 实战案例回放

### Sprint 1: 装饰器感知 Dead Code 检测

```
PO:        扫描 v1 → 发现 827 dead code 中大量 @click/@route 误报
Architect: 设计双策略检测 (parser metadata + AST fallback)
Worker:    RED: 8 个测试全部 FAIL → GREEN: 10/10 PASS

--- 10 Expert Panel Review ---
Round 1:   12 条指摘
  Torvalds: "递归无深度限制 → StackOverflow 风险" (Critical)
  Fowler:   "检测逻辑和缓存逻辑混在一个方法里" (High)
  Uncle Bob: "违反 SRP: DeadCodeDetector 又检测又缓存" (High)
  ... 其他 9 条 Medium
Worker:    修复全部 12 条 → 重新提交

Round 2:   2 条指摘
  Burns:    "缓存未线程安全" (High)
  Kerr:     "变量名 _dec 语义不清" (Medium)
Worker:    修复 2 条 → 重新提交

Round 3:   0 条指摘 ✅ 全员通过!
--- End of Review Loop ---

QA:        发现 FQN 重复 bug → 修复 fixture → 61/61 PASS
Writer:    更新 tasks.md + progress.md
DevOps:    976/976 PASS, 91% coverage
           v1 实测: 283 decorators, 0 false positives, dead code 827→505
```

### Sprint 效果量化

| 指标 | Before | After | 改善 |
|------|--------|-------|------|
| Dead Code 误报率 | ~39% | 0% | -100% |
| 识别框架装饰器数 | 0 | 283 | +283 |
| 测试总数 | 962 | 976 | +14 |
| 代码覆盖率 | 87% | 91% | +4% |
| 专家评审轮数 | N/A | 3 轮 | 指摘 12→2→0 |

---

## 本文件的使用方式

1. **AI 首次加载项目时**: 自动读取本文件，理解完整协议
2. **用户说"全自动开发"时**: AI 从 STEP 1 开始执行，无需追问
3. **STEP 4 是核心关卡**: 10 位专家联合评审，指摘归零才能通过
4. **每轮结束时**: AI 输出 Sprint 报告，并自动建议下一轮目标
5. **用户无需记住任何流程**: 所有流程已编码在本文件中

**AI 承诺**: 读完本文件后，我能够在用户说出触发词的瞬间，自主执行完整的 8 步闭环，
从分析能力缺口到全量测试演示，期间无需任何人工干预。
**每一行代码都将通过 10 位世界顶级架构师的联合评审，直到指摘归零方可通过。**

---

## 附录: 10 位专家评审深度指南

### 各专家的"红线"（一票否决项）

每位专家有各自的"红线"——碰到即自动 Critical，不允许协商降级：

| 专家 | 红线 (一票否决) |
|------|----------------|
| Martin Fowler | 单文件 > 500 行且无拆分计划；方法 > 50 行 |
| Robert C. Martin | 一个类承担 > 2 个职责；具体类之间的直接依赖（应依赖抽象） |
| Eric Evans | 核心领域用 `dict[str, Any]` 传递（应为 Domain Object） |
| Sam Newman | 模块间循环依赖；API 无版本策略 |
| Gregor Hohpe | 接口返回 `Any` 类型；错误用 `bool` 表示而非异常/Result |
| Brendan Burns | 共享可变状态无并发保护；资源打开未关闭 |
| Titus Winters | 公开 API 签名变更无向后兼容策略 |
| Kelsey Hightower | `except Exception: pass`（吞掉异常）；无日志的错误路径 |
| Jessica Kerr | 函数名 > 30 字符或 < 3 字符；认知复杂度 > 15 |
| Linus Torvalds | 嵌套循环 > 2 层且无算法优化说明；不必要的抽象层（间接跳转 > 3 层） |

### 评审时的思维框架

每位专家在评审时，应模拟以下思维过程：

```
1. 我是 {专家名}，我在 {领域} 有 20+ 年经验
2. 我看到的这段代码，在我的标准下:
   - 哪些部分是合格的? (明确认可)
   - 哪些部分我无法接受? (指摘 + 具体修复方案)
   - 这段代码在生产环境会出什么问题? (实战预判)
3. 我的最终裁定: APPROVED / REJECTED
```

### 评审不是挑刺，是守护质量

> 专家评审的目的不是为了让代码无法通过，而是通过世界最高标准的审视，
> 确保每一行代码都经得起推敲。如果代码确实写得好，10 位专家会在 Round 1 就全员 APPROVED。
> 如果需要多轮迭代，说明代码确实有可改进之处——这正是闭环的价值所在。
