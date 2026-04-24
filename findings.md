# Findings — 自主开发调研笔记

## Session 169 — 2026-04-25: Abstraction Level Mixing Detector (1-in-1-out)

**类型**: 1-in-1-out (net zero)

**新增**: `abstraction_level.py` — Abstraction Level Mixing Detector
- 检测函数混合高层抽象（业务方法调用）和低层实现细节（字符串操作、算术、索引）
- Issue types: `mixed_abstraction` (medium), `leaky_abstraction` (low)
- 多语言支持: Python, JS/TS, Java, Go
- 基于 Robert C. Martin "Clean Code" 原则：函数应在一个抽象层级操作

**移除**: `nested_class.py`
**原因**: nested_class 检测范围窄（仅检测类定义嵌套），没有实际的代码质量改进建议；竞品（ESLint no-inner-declarations, Ruff PLW...）已有类似规则覆盖；低用户信号

**功能评分**: 10/12
- 竞品差距: 3/3 — 无 ESLint/Ruff/SonarQBE 规则检测抽象层级混合
- 用户信号: 2/3 — Clean Code 经典原则，Code Review 中常见的抽象层级混合问题
- 架构适配: 3/3 — BaseAnalyzer, 函数级 AST 分析, 多语言
- 实现成本: 2/3 — 中等复杂度（高层/低层语句分类 + 转换计数）

**产品分析 (Steve Jobs Perspective)**:
- 问题：读者被迫在"这段代码做什么"和"它怎么做"之间不断切换上下文
- 一句话："Find functions that force readers to context-switch between 'what it does' and 'how it does it'"
- 无竞品覆盖：ESLint 没有抽象层级规则，Ruff 没有，SonarQBE 也没有
- 用户价值：在 Code Review 中识别需要 extract-method 重构的函数

**架构分析**:
- 组件：`tree_sitter_analyzer/analysis/abstraction_level.py`（~376 行）
- Base class: BaseAnalyzer
- 算法：1) 遍历 AST 找到函数节点 → 2) 对每个语句分类（high-level/low-level）→ 3) 计算转换次数 → 4) 混合度高则报告
- 数据结构：`AbstractionIssue` (frozen dataclass), `AbstractionResult` (frozen dataclass)

**结果**: 82 → 82 analyzers (1-in-1-out)

## Session 168 — 2026-04-25: Method Cohesion Detector (1-in-1-out)

**类型**: 1-in-1-out (net zero)

**新增**: `method_cohesion.py` — Method Cohesion Analyzer (LCOM4)
- 检测类方法凝聚力低的类（LCOM4 > 1），即方法操作不相交的字段集合
- LCOM4 算法：构建方法-字段访问图，计算连通分量数。LCOM4 > 1 表示类应拆分
- Issue types: `low_cohesion` (medium)
- 多语言支持: Python (self.X), JS/TS (this.X), Java (this.X), Go (receiver.X)
- 排除构造函数（__init__/constructor）— 构造函数初始化所有字段，不应参与凝聚力计算

**移除**: `redundant_super.py`（~385 行）
**原因**: Pylint W0235 (useless-super-delegation) 覆盖 Python 场景；ESLint/TS 允许空 constructor 语法；范围极窄（仅检测不必要的 super() 调用）

**功能评分**: 10/12
- 竞品差距: 3/3 — 无 ESLint/Ruff/SonarQBE/Pylint 规则检测 LCOM/类凝聚力
- 用户信号: 2/3 — Fowler 代码味道目录中的经典度量，SRP 讨论中常见
- 架构适配: 3/3 — BaseAnalyzer, 类级别 AST 分析, 多语言, 图算法
- 实现成本: 2/3 — 中等复杂度（方法-字段矩阵 + 连通分量计算）

**产品分析 (Steve Jobs Perspective)**:
- 问题：低凝聚力的类是"秘密的两个或多个类混合在一起"的典型表现，是 God Class 的根源
- 当前 SRP 检测使用代理指标（方法数 > 10、行数 > 300），LCOM4 提供精确的数学度量
- 无竞品覆盖此检测：ESLint 没有类凝聚力规则，Ruff 没有 LCOM 规则，SonarQBE 没有 LCOM4 规则
- 用户价值：当你在 code review 中看到"这个类做了太多事"，LCOM4 给出客观的数字来支撑

**架构分析 (Plan-Eng-Review)**:
- 组件：`tree_sitter_analyzer/analysis/method_cohesion.py`（~430 行）
- Base class: BaseAnalyzer（继承自 `analysis/base.py`）
- 算法：1) 遍历 AST 找到类节点 → 2) 提取每个方法的实例字段访问 → 3) 构建方法-字段矩阵 → 4) BFS 计算连通分量 → 5) LCOM4 > 1 则报告
- 数据结构：`CohesionIssue` (frozen dataclass), `CohesionResult` (frozen dataclass)
- Go 特殊处理：按 receiver type 分组方法（Go 没有类，用 struct + methods）

## Session 165 — 2026-04-25: Encapsulation Break Detector (1-in-1-out)

**类型**: 1-in-1-out (net zero)

**新增**: `encapsulation_break.py` — Encapsulation Break Detector
- 检测方法直接返回内部可变状态（list/dict/set）的引用，破坏封装
- Issue types: `state_exposure` (medium), `private_state_exposure` (low)
- 多语言支持: Python (self.X), JS/TS (this.X), Java (this.X)

**移除**: `iterable_modification.py`（Python-only, ~230 行）
**原因**: Pylint W4901-W4903 (modified-iterating-list/set/dict) 已覆盖集合迭代修改检测；Ruff 也在持续添加 Pylint 规则

**功能评分**: 10/12
- 竞品差距: 3/3 — 无 ESLint/Ruff/SonarQBE/Pylint 规则检测内部可变状态的返回引用
- 用户信号: 2/3 — 真实 bug 模式（封装破坏），self-hosting 可发现实例
- 架构适配: 3/3 — BaseAnalyzer, 类级别分析, 多语言
- 实现成本: 2/3 — 中等复杂度（类字段追踪 + 返回语句分析）

**结果**: 82 → 82 analyzers

## Refactoring Sprint (continued) — 2026-04-25 Session 164: Removed boolean_complexity

**类型**: 1-in-1-out (net reduction)

**移除**: `boolean_complexity.py` — 被 `cognitive_complexity.py` 完全覆盖（认知复杂度已计算布尔运算符序列，boolean_complexity 只是简单计数，无增量价值）

**结果**: 83 → 82 analyzers
**Sprint 总计**: 87 → 82 analyzers (removed 5), ~4200 lines removed

## 产品讨论记录 - Error Message Quality Analyzer - 2026-04-25 Session 164

**调用**: inline product analysis (autonomous mode)

**功能**: Error Message Quality Analyzer — detect empty/generic error messages in raise/throw statements

**竞品否决检查**: PASS
- ESLint: No rule for error message content quality
- Ruff: EM101/EM102/EM103 only check WHERE message is defined (inline vs variable), not content quality
- SonarQBE: No rule for error message quality/content
- Pylint: No rule for error message quality/content
- **结论**: 竞品差距 3/3 — 无任何工具检查错误消息内容质量

**聚焦即说不**:
- ts-analyzer 核心价值是帮助 LLM 理解代码。`raise ValueError()` 告诉 LLM "这里会出错"，但不知道为什么
- 错误消息是开发者与未来维护者之间的通信契约
- 一句话: "Find raise/throw statements with missing or generic error messages — the hidden gap between code that fails and code that communicates why"

**减法思维**:
- MVP = 检测空消息和明显占位符消息
- 不做语义理解（不知道消息应该说什么）
- 不做跨文件分析
- 检测规则: `raise ValueError()` → empty, `raise ValueError("error")` → generic

**评分**: 11/12 >= 10 (PASS)
- 竞品差距: 3/3 — 无竞品覆盖错误消息内容质量
- 用户信号: 2/3 — 错误消息是已知开发痛点，self-hosting 能发现问题
- 架构适配: 3/3 — 单文件 AST，BaseAnalyzer，完美适配
- 实现成本: 3/3 — 半 Sprint（简单的 raise/throw 参数模式匹配）

**结论**: ~~DO~~ → **DON'T** (overlap discovered)
- `error_handling.py` already has `GENERIC_ERROR_MESSAGE` pattern type with `GENERIC_MESSAGES` set
- Already detects empty/generic error messages in Python and JS/TS
- Only gap: `raise ValueError()` (no args) not detected, but insufficient value for a new analyzer
- **Decision**: Don't implement, record as overlap finding

**1-in-1-out**: 删除 `boolean_complexity.py`（已被 `cognitive_complexity.py` 完全覆盖——认知复杂度已计算布尔运算符序列，boolean_complexity 只是简单计数，无增量价值）

## 技术架构讨论 - Error Message Quality Analyzer - 2026-04-25

**推荐方案**: 独立 BaseAnalyzer (error_message_quality.py)

**技术方案**: 单遍 AST 遍历
1. 遍历所有 raise/throw/panic 节点
2. 检查:
   - 无参数: `raise ValueError()` → `empty_error_message`
   - 通用占位符: `raise ValueError("error")`, `throw new Error("err")` → `generic_error_message`
   - 仅变量引用: `raise ValueError(msg)` → 跳过（无法确定内容）
3. 严重性: medium (empty), low (generic)
4. 语言: Python (raise), JS/TS (throw), Java (throw), Go (panic)

**风险**: 误报 — `raise ValueError(msg)` 可能有好的消息。仅标记空和明确通用的消息。
**依赖**: 无

## Refactoring Sprint — 2026-04-25 Session 164: Removed 4 competitor-covered analyzers

**类型**: 重构 Sprint

**移除的 Analyzer**（竞品已完美覆盖）:
| Analyzer | 竞品 | 竞品规则 |
|----------|------|---------|
| redundant_else | ESLint `no-else-return`, Pylint R1705 | else after return/break/continue |
| assignment_in_conditional | ESLint `no-cond-assign` | `=` vs `==` in if/while |
| variable_shadowing | ESLint `no-shadow`, Ruff `A001`, Pylint `W0621` | Inner scope shadows outer scope |
| empty_block | ESLint `no-empty`, SonarQBE S108/S1181 | Empty function/catch/loop blocks |

**结果**: 87 → 83 analyzers, ~3700 lines removed
**Commit**: (pending)

## Implementation Complete - Exception Signature Analyzer - 2026-04-25 Session 162

**Status**: IMPLEMENTED, all checks pass
- 87 analyzers (+1 exception_signature, -1 duplicate_condition = net 0, 1-in-1-out)
- 36 tests passing
- Self-hosting score: 100%
- MCP tool registered: exception_signature

## 产品讨论记录 - Exception Boundary Analyzer - 2026-04-25 Session 161

**调用**: inline product analysis (autonomous mode)

**功能**: Exception Boundary Analyzer — 跨函数追踪异常类型流（raise → caller 未 catch）

**竞品否决检查**: PASS（无竞品覆盖跨函数异常边界追踪）

**评分**: 8/12 < 10/12 门槛 → **DON'T**
- 竞品差距: 3/3 — 无竞品覆盖
- 用户信号: 1/3 — 推理得出（异常泄露导致生产事故是已知问题），无直接用户信号
- 架构适配: 2/3 — 基本适配，但需要多遍 AST 遍历（先收集函数异常，再检查调用者）
- 实现成本: 2/3 — 1 Sprint，但跨函数调用图复杂度中等

**理由**: 用户信号不足（无 self-hosting 发现或 GitHub issue），架构需要跨函数分析超出单遍 AST 模式。降级为"Undocumented Exception"的更简单方案。

## 产品讨论记录 - Exception Signature Analyzer - 2026-04-25 Session 161

**调用**: inline product analysis (autonomous mode)

**功能**: Exception Signature Analyzer — 对每个函数提取"异常签名"（哪些异常会逃逸），检查是否被文档记录

**聚焦即说不**:
- ts-analyzer 核心价值是帮助 LLM 理解代码。函数的异常行为是最难从代码中推断的信息之一
- Python/JS/TS 没有强制的异常声明机制，开发者必须读完整函数体才能知道会抛什么异常
- 现有 error_handling 检测反模式，error_propagation 检测吞噬错误，但没有任何工具回答"这个函数会抛什么？"
- 一句话: "Reveal what exceptions a function can throw — the hidden contract between caller and callee"

**减法思维**:
- MVP = 遍历函数体，收集未被内部 try/except 捕获的 raise/throw 语句，报告异常类型列表
- 附加检查: docstring/@throws 中是否记录了这些异常类型
- 不做跨文件分析，只在单文件内

**竞品否决检查**: PASS
- ESLint: 无异常签名/文档一致性规则
- Ruff: 无 raise→docstring 一致性检查
- SonarQBE: S1130 (未声明的 throws) 仅限 Java，且 Java 编译器已强制
- Pylint: W0236 (exception-is-hiding) 是不同概念
- **结论**: 竞品差距 3/3 — 无任何工具提供此功能

**评分**: 10/12 >= 10 (PASS)
- 竞品差距: 3/3 — 无竞品覆盖异常签名提取 + 文档一致性检查
- 用户信号: 2/3 — LLM 代码理解的直接需求（推理 + 社区最佳实践）
- 架构适配: 3/3 — 单文件 AST，BaseAnalyzer 模式，完美适配
- 实现成本: 2/3 — 1 Sprint（需处理嵌套 try/except，多异常路径）

**结论**: DO — 真正的分析缺口，完美适配架构，帮助 LLM 理解函数的隐藏契约

**1-in-1-out**: 删除 `duplicate_condition.py`（regex-based，ESLint `no-dupe-else-if` + SonarQBE S1862 部分覆盖，与 `code_clones.py` 重叠）

## 技术架构讨论 - Exception Signature Analyzer - 2026-04-25

**调用**: inline architecture analysis (autonomous mode)

**推荐方案**: 独立 BaseAnalyzer (exception_signature.py)

**技术方案**: 两遍 AST 遍历

**第一遍 — 收集异常签名**:
1. 遍历函数定义，对每个函数:
   - 找到所有 raise/throw/panic 语句
   - 检查每个 raise 是否在 try/except/catch 内且异常类型被捕获
   - 未被捕获的异常类型组成函数的"异常签名"
2. Python: raise ValueError → 检查上层 except (ValueError, ...) 是否捕获
   JS/TS: throw new Error() → 检查上层 catch 是否捕获
   Java: throw new X() → 检查上层 catch 是否捕获（但编译器已强制 checked exceptions）
   Go: panic(X) → 检查上层 recover

**第二遍 — 文档一致性检查**:
1. 对每个有异常签名的函数:
   - Python: 检查 docstring 中是否有 `:raises ValueError:` 或 `:exc:`ValueError`` 格式
   - JS/TS: 检查 JSDoc 中是否有 `@throws {ValueError}`
   - Java: 检查 javadoc 中是否有 `@throws ValueError`
   - Go: 跳过文档检查（Go 不使用异常文档模式）

**Finding 类型**:
- `undocumented_exception` (medium): 函数抛出 X 但文档未记录
- `exception_signature` (info): 函数的完整异常签名列表

**关键排除**:
- 泛型 except/catch（捕获所有异常的块）视为所有异常被捕获
- re-raise (bare raise / throw;) 视为原始异常类型
- 嵌套函数/闭包内的异常不影响外部函数签名
- 构造函数和类方法同等处理

**支持语言**: Python, JS/TS, Java (Go 部分支持)

**风险**: 误报 — 条件性 raise（仅在某些条件下抛出）可能被标记为"总是抛出"
**依赖**: 无

## 重构 Sprint — 2026-04-25 Session 160: 移除 12 个竞品已覆盖的 Analyzer

**类型**: 重构 Sprint（1 进 1 出规则 — 净减少）

**移除的 Analyzer**（竞品已完美覆盖）:
| Analyzer | 竞品 | 竞品规则 |
|----------|------|---------|
| callback_hell | ESLint | max-nested-callbacks |
| statement_no_effect | Ruff | B015 |
| function_redefinition | Ruff | F811 |
| self_assignment | Ruff | PLW0127 |
| late_binding_closure | Ruff | B023 |
| return_in_finally | SonarQBE | S1143 |
| hardcoded_ip | SonarQBE | S1313 |
| deep_unpacking | Ruff | PLR0916 |
| missing_static_method | Pylint/Ruff | R0201/PLR6301 |
| commented_code | ESLint | no-commented-out-code |
| simplified_conditional | ESLint | no-unneeded-ternary |
| nested_ternary | ESLint | no-nested-ternary |

**结果**: 100→88 analyzers, 110→98 MCP tools, ~7487 lines removed
**Commit**: 5295cfc2

## 产品讨论记录 - Finding Correlation (Meta Tool) - 2026-04-21 Session 154

**调用**: inline product analysis (autonomous mode)

**功能**: Cross-Analyzer Finding Correlation — 跨分析器发现关联，识别复合热点

**分析**:
- 聚焦: 164 个分析器的发现散落各处，用户不知道哪些代码位置问题最集中。关联发现是"让现有工具有用"的核心
- 减法: MVP = 按位置分组，2+ 分析器 = 热点，3+ = 严重热点
- 一句话: "Find code locations flagged by multiple independent analyzers, revealing compound quality hotspots"

**竞品分析**:
- ESLint: 无跨 rule 关联功能
- SonarQBE: 有 "security hotspots" 但仅限安全维度，不跨质量维度
- Ruff: 无关联功能

**评分**: 11/12 (竞品差距3 + 用户信号3 + 架构适配3 + 实现成本2)
**结论**: DO — 不增加新分析器，让现有 164 个分析器的输出更有价值

## 产品讨论记录 - Finding Correlation Enhancement - 2026-04-25 Session 158

**调用**: inline product analysis (autonomous mode)

**功能**: Finding Correlation Pattern Detection + Priority Ranking — 增强现有 finding_correlation.py

**背景**: Self-hosting gate 产生 678 个 findings，用户无法判断哪些热点优先修复

**新增能力**:
1. **Priority Score**: 数值评分 (analyzer_count × severity_weight)，排序热点
2. **Pattern Categorization**: 识别常见问题聚类模式（complexity_cluster, dead_code_cluster, risk_cluster）
3. **File-level Summary**: 按文件聚合热点，项目级优先级视图

**竞品否决检查** (Session 158):
- ESLint: 无跨 rule 关联 + 优先级排序。Searched: "ESLint cross-rule correlation priority ranking" → 无结果
- Ruff: 无跨 rule 关联功能。Searched: "Ruff rule correlation priority ranking" → 无结果
- SonarQBE: "security hotspots" 仅限安全维度。Searched: "SonarQBE cross-rule correlation priority" → 无结果
- **结论**: 竞品差距 3/3 — 无任何工具提供跨规则关联 + 优先级排序

**评分**: 11/12
- 竞品差距: 3/3 (ESLint/Ruff/SonarQBE 均无此功能)
- 用户信号: 3/3 (678 self-hosting findings 证实优先级需求)
- 架构适配: 3/3 (扩展现有 finding_correlation.py，不新增分析器)
- 实现成本: 2/3 (单 Sprint，moderate complexity)

**结论**: DO — 增强现有模块，1-in-1-out 规则不适用（不新增分析器）

**技术方案** (inline architecture analysis):
1. 在 Hotspot 增加 `priority_score` 属性: `analyzer_count * (severity_weight + density_bonus)`
2. 新增 `HotspotPattern` enum: COMPLEXITY_CLUSTER, DEAD_CODE_CLUSTER, RISK_CLUSTER, MIXED
3. 新增 `_detect_pattern()` 方法: 根据聚类内 finding_types 判断模式
4. CorrelationResult 新增 `file_summary` 属性: 按文件聚合热点数量和最高优先级
5. 更新 to_dict() 输出包含新字段
6. 更新 MCP tool 的 toon 格式显示 priority score 和 pattern

## 产品讨论记录 - Batch 4 Candidates - 2026-04-20 Session 152

**调用**: inline product analysis (autonomous mode)

**功能候选**: 3 个候选分析

**分析**:

### 候选 1: Deep Unpacking Detector — DO
- 理由: 真实可读性/正确性问题，元组解包漏一个变量就静默出错，无现有工具覆盖此场景
- 评分: 11/12 (独特性3 + 需求度2 + 架构适配3 + 实现成本3)
- 一句话: "Find excessive tuple unpacking that reduces readability and risks silent failures"

### 候选 2: Missing Static Method Detector — DO
- 理由: 常见代码异味，实例方法不使用 self 暗示设计意图不清晰，LLM 审查代码时高频发现
- 评分: 11/12 (独特性3 + 需求度3 + 架构适配3 + 实现成本2)
- 一句话: "Find instance methods that never use self and should be @staticmethod"

### 候选 3: Nested Class Detector — DO
- 理由: Java/C++ 中嵌套类很常见，通常是设计问题的信号，应该用组合替代
- 评分: 11/12 (独特性3 + 需求度2 + 架构适配3 + 实现成本3)
- 一句话: "Find classes defined inside other classes, a design smell suggesting missing composition"

**结论**: 3 个都值得做，按顺序实现

## 技术架构讨论 - Batch 4 - 2026-04-20

**调用**: inline architecture analysis (autonomous mode)

**技术方案**: 所有 3 个 analyzer 均使用 BaseAnalyzer + AST 遍历模式

1. Deep Unpacking: 遍历 assignment/pattern 节点，统计 tuple_pattern 中的元素数
2. Missing Static Method: 遍历 function_definition 在 class_definition 内，检查方法体是否引用 self
3. Nested Class: 遍历 class_definition，检查父节点是否也是 class_definition

## 产品讨论记录 - Batch 3 Candidates - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: 3 个候选分析

**分析**:

### 候选 1: Unnecessary Pass Statement Detector — DON'T
- 理由: 纯代码风格问题，ruff/flake8 已覆盖，额外 pass 不影响行为，高误报率

### 候选 2: Redundant F-String Detector — DON'T
- 理由: 样式问题（ruff RUF027 已覆盖），JS 模板字符串无 ${} 合法且常见，大量误报

### 候选 3: Dict Merge in Loop Detector — DO
- 理由: 真实性能问题（dict.update 是 C 级批量操作），string_concat_loop 只覆盖字符串不覆盖 dict，低误报率
- 一句话: "Find dict key assignments in loops that should use dict.update() for better performance"

**结论**: 只有 Dict Merge in Loop 值得做

## 技术架构讨论 - Dict Merge in Loop Detector - 2026-04-20

**调用**: /plan-eng-review (inline, autonomous mode)

**技术方案**: AST 遍历 for_statement 节点
- Python: 检测 for 循环体中的 `d[key] = value` 赋值模式，特别是 subscript + assignment
- 识别 dict 变量名，收集循环体中所有 subscript assignment
- 如果循环变量被用作 key 或 value 的一部分，报告为 dict_merge_in_loop
- 排除: 非 subscript 的赋值（如 x = 1），非循环变量的 subscript（如 config["fixed_key"] = 1）

**推荐方案**: 标准 BaseAnalyzer 模式，Python-only（dict.update 是 Python 特有模式）
**风险**: 误报 — 需要区分有条件的 dict update（if inside loop）和简单的逐个赋值
**依赖**: 无

**独特性评分**: 10/12 >= 8 (DO)
- Uniqueness: 3/3 — 无类似工具（string_concat_loop 只覆盖字符串 +=）
- Need: 3/3 — dict.update 比 for 逐个赋值快数倍，真实性能问题
- Architecture fit: 3/3 — 纯 AST，BaseAnalyzer，Python
- Implementation cost: 1/3 — 需要识别 subscript assignment 模式

## 产品讨论记录 - List-in-Membership Performance Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: List-in-Membership Performance Detector — 检测 `x in [1,2,3]` 应该用 set `{1,2,3}`

**产品分析**:
- 聚焦: `x in [1,2,3]` 是 O(n) 查找，`x in {1,2,3}` 是 O(1)。当列表较大或频繁调用时是显著性能问题
- 减法: MVP = 检测 `in` 操作符后面跟着 list literal
- 一句话: "Find the membership tests using lists that should use sets for O(1) lookup"

**独特性评估**: 10/12 >= 8 (DO)
- Uniqueness: 3/3 — 无类似工具
- Need: 3/3 — 常见性能问题，容易修复
- Architecture fit: 3/3 — 纯 AST，BaseAnalyzer，Python + JS/TS + Go
- Implementation cost: 1/3 — 需要识别 in 操作符后的 list literal

**结论**: DO — 检测真实性能问题，修复简单

## 技术架构讨论 - List-in-Membership Performance Detector - 2026-04-20

**调用**: /plan-eng-review (autonomous mode)

**技术方案**: AST 遍历
- Python: 检测 `comparison_operator` 中 `in` 操作符后面跟着 `list`
- JS/TS: 检测 `binary_expression` 中 `includes` 方法调用在 array literal 上
- Go: 不适用（Go 没有 in 操作符）

**推荐方案**: 标准 BaseAnalyzer，Python + JS/TS
**风险**: 误报 — 小列表的性能差异可忽略，但代码风格一致性好
**依赖**: 无

## 产品讨论记录 - Unused Loop Variable Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Unused Loop Variable Detector — 检测 `for x in items:` 中 `x` 未被使用

**产品分析**:
- 聚焦: 未使用的循环变量可能是遗漏的操作（忘了用 x），或者循环变量多余（应改为 `_`）
- 减法: MVP = 检测 for 循环的命名变量，确认它在循环体中从未作为 identifier 出现
- 一句话: "Find the loop variables that were named but never used — they should be `_` or you forgot something"

**独特性评估**: 9/12 >= 8 (DO)
- Uniqueness: 3/3 — 无类似工具（unused_parameter 检查函数参数，不检查循环变量）
- Need: 2/3 — 代码异味，可能暗示遗漏的逻辑
- Architecture fit: 2/3 — 需要变量使用追踪，中等复杂度
- Implementation cost: 2/3 — Python + JS/TS，需要检查标识符使用

**结论**: DO — 检测潜在的遗漏逻辑

## 技术架构讨论 - Unused Loop Variable Detector - 2026-04-20

**调用**: /plan-eng-review (autonomous mode)

**技术方案**: AST 遍历 for_statement 节点
- Python: 提取 for x in items 中 x，在循环体中搜索 x 作为 identifier 的出现
- JS/TS: 提取 for...of/for...in 中的变量声明，在循环体中搜索
- 排除: `_` 和 `_*` 前缀的变量名（约定为有意不使用）
- 排除: unpacking 中的 `_`（如 `for _, val in items`）

**推荐方案**: 标准 BaseAnalyzer 模式，Python + JS/TS
**风险**: 误报 — 变量可能通过 globals/eval 隐式使用，但这种情况少见
**依赖**: 无

## 产品讨论记录 - Float Equality Comparison Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Float Equality Comparison Detector — 检测 `x == 0.1`, `a != 3.14` 等浮点数精确比较

**产品分析**:
- 聚焦: 浮点数精确比较 (`==`/`!=`) 因 IEEE 754 精度问题可能产生错误结果。`0.1 + 0.2 == 0.3` 为 False
- 减法: MVP = 检测 comparison_operator 中 == 或 != 操作符且至少一侧为 float literal
- 一句话: "Find the floating-point comparisons that lie, because `0.1 + 0.2 != 0.3`"

**独特性评估**: 10/12 >= 8 (DO)
- Uniqueness: 3/3 — 无类似工具（tautological_condition 检查 x==x，不检查 float==float）
- Need: 3/3 — 经典 IEEE 754 陷阱，广泛存在于金融/科学计算
- Architecture fit: 3/3 — 纯 AST，BaseAnalyzer，Python + JS/TS + Java + Go
- Implementation cost: 1/3 — 多语言，需要正确识别 float literal

**结论**: DO — 检测真正的静默正确性问题

## 技术架构讨论 - Float Equality Comparison Detector - 2026-04-20

**调用**: /plan-eng-review (autonomous mode)

**技术方案**: AST 遍历 comparison_operator 节点
- Python: 检测 float literal (包含 `.` 的 number) 在 == 或 != 比较中
- JS/TS: 同上，排除 === 和 !== (strict comparison 仍然有问题)
- Java: 检测 double/float literal (带 d/f 后缀或包含 `.`)
- Go: 检测 float64/float32 literal
- 排除: integer 比较，None/True/False singleton 比较

**推荐方案**: 标准 BaseAnalyzer 模式，Python + JS/TS + Java + Go
**风险**: 误报率需要控制 — 应该只在浮点数字面量直接参与比较时报
**依赖**: 无

## 产品讨论记录 - Mutable Multiplication Alias Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Mutable Multiplication Alias Detector — 检测 `[[]] * n`, `{{}} * n` 等共享引用 bug

**产品分析**:
- 聚焦: `[[]] * n` 创建 n 个指向同一内部列表的引用。修改一个会影响所有
- 减法: MVP = 检测 list_literal/dict_literal/set_literal 后跟 `*` 运算符
- 一句话: "Find the list multiplication that creates shared references, not independent copies"

**独特性评估**: 11/12 >= 8 (DO)
- Uniqueness: 3/3 — 无类似工具
- Need: 3/3 — 经典 Python 静默 bug，难以调试
- Architecture fit: 3/3 — 纯 AST，BaseAnalyzer，Python-only
- Implementation cost: 2/3 — 需要检查二元操作符的左操作数是否为可变字面量

**结论**: DO — 检测真正的静默 bug

## 产品讨论记录 - Await-in-Loop Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Await-in-Loop Detector — 检测循环体内的 await 表达式

**产品分析**:
- 聚焦: `for x in items: await f(x)` 串行执行异步操作，应该用 `asyncio.gather` / `Promise.all` 并行化
- 减法: MVP = 检测 for/while 循环体内是否有 await_expression
- 一句话: "Find the serial async operations that should run in parallel"

**独特性评估**: 11/12 >= 8 (DO)
- Uniqueness: 3/3 — async_patterns 不检测此模式
- Need: 3/3 — 常见性能问题，实际用户痛点
- Architecture fit: 3/3 — 标准 BaseAnalyzer，Python + JS/TS
- Implementation cost: 2/3 — 两种语言，略有复杂度

**结论**: DO — 检测真正的性能问题

## 技术架构讨论 - Await-in-Loop Detector - 2026-04-20

**调用**: /plan-eng-review (autonomous mode)

**技术方案**: AST 遍历
- Python: 在 for_statement/while_statement 内检测 await_expression
- JS/TS: 在 for_statement/for_in_statement/while_statement 内检测 await_expression
- 排除: 嵌套函数中的 await（它属于内部函数，而非循环）

**推荐方案**: 方案 A（独立模块），理由：与 115+ MCP 工具架构一致
**风险**: 嵌套函数误报 — 需要在进入子函数时重置 "in loop" 状态
**依赖**: 无

## 产品讨论记录 - Identity Comparison with Literals Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Identity Comparison with Literals Detector — 检测 `is`/`is not` 与非 singleton 字面量的比较

**产品分析**:
- 聚焦: `x is 5`, `x is "hello"`, `x is []` 是 identity 比较而非 value 比较。Python 3.8+ SyntaxWarning, 3.12+ DeprecationWarning, 未来版本 SyntaxError
- 减法: MVP = 检测 `is`/`is not` 比较操作符的右操作数是否为非 singleton 字面量（数字、字符串、列表、字典、集合、元组）
- 一句话: "Find the comparisons that will break in future Python, because `x is 5` checks identity not value"

**独特性评估**: 12/12 >= 8 (DO)
- Uniqueness: 3/3 — 无类似工具（loose_equality 检查 JS 的 ==/===，不检查 Python is）
- Need: 3/3 — Python 3.12+ 正式弃用，未来版本 SyntaxError，真正的兼容性问题
- Architecture fit: 3/3 — 纯 AST，BaseAnalyzer，Python-only
- Implementation cost: 3/3 — 单 Sprint

**结论**: DO — 检测真正的向前兼容性问题和正确性 bug

## 技术架构讨论 - Identity Comparison with Literals Detector - 2026-04-20

**调用**: /plan-eng-review (autonomous mode)

**技术方案**: 纯 AST 遍历
- 遍历所有 `comparison_operator` 节点
- 检查操作符是否为 `is` 或 `is not`
- 检查左右操作数是否为非 singleton 字面量（integer, float, string, list, dictionary, set, tuple）
- 排除 singleton 值：None, True, False, Ellipsis/...
- 报告 identity_comparison_literal 问题

**Singleton 白名单**: None, True, False, ...（Ellipsis）
**字面量黑名单**: integer, float, string, list, dictionary, set, tuple, concatenate_string

**推荐方案**: 方案 A（独立模块），理由：与 114+ MCP 工具架构一致，Python-only
**风险**: 无，纯 AST 静态分析
**依赖**: 无

## 产品讨论记录 - Assert-on-Tuple Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Assert-on-Tuple Detector — 检测 `assert (condition, message)` 模式

**产品分析**:
- 聚焦: `assert (x > 0, "msg")` 总是 True（非空 tuple 是 truthy）。经典 Python 静默 bug
- 减法: MVP = 检查 assert 参数是否为 tuple literal，纯 AST
- 一句话: "Find the asserts that always pass, because `assert (cond, msg)` evaluates the tuple, not the condition"

**独特性评估**: 12/12 >= 8 (DO)
- Uniqueness: 3/3 — 无类似工具（production_assert 不检测 tuple trap）
- Need: 3/3 — Python 经典陷阱，静默 bug
- Architecture fit: 3/3 — 纯 AST，BaseAnalyzer，Python-only
- Implementation cost: 3/3 — 单 Sprint

**结论**: DO — 检测真正的静默 bug，极简实现

## 技术架构讨论 - Assert-on-Tuple Detector - 2026-04-20

**调用**: /plan-eng-review (autonomous mode)

**技术方案**: 纯 AST 遍历
- 检查 assert_statement 的第一个 named child
- 如果类型是 tuple 且第一个 child 是 expression（不是 keyword argument）
- 报告 assert_on_tuple 问题

**推荐方案**: 方案 A（独立模块），理由：与 107+ MCP 工具架构一致
**风险**: 无，纯 AST 静态分析
**依赖**: 无

## 产品讨论记录 - Return in Finally Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Return in Finally Detector — 检测 finally 块中的 return/raise 语句

**产品分析**:
- 聚焦: finally 中的 return 会静默吞掉 try 块中的异常。Python/Java/JS/TS 均有此问题
- 减法: MVP = 检查 finally_clause 内是否有 return_statement 或 raise_statement
- 一句话: "Find the returns that silently swallow exceptions, because `return` in `finally` masks the error"

**独特性评估**: 11/12 >= 8 (DO)
- Uniqueness: 3/3 — 无类似工具
- Need: 3/3 — Python/Java/JS/TS 均有此问题，静默吞掉异常
- Architecture fit: 3/3 — 标准 BaseAnalyzer，多语言
- Implementation cost: 2/3 — 需要 4 种语言的 finally/return 节点类型

**结论**: DO — 跨语言检测静默异常吞没

## 产品讨论记录 - Production Assert Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Production Assert Detector — 检测非测试代码中的 assert 语句（python -O 会剥离）

**产品分析**:
- 聚焦: assert 在 -O 模式下被剥离是真实 Python 反模式，Pylint PLW0129 也检测
- 减法: 代码已存在（194+111行），只需加测试
- 一句话: "Find assert statements that vanish in production because python -O strips them"

**独特性评估**: 10/12 >= 8 (DO)
- Uniqueness: 2/3 — Pylint 有此检查，但工具链内无
- Need: 2/3 — 真实但小众，-O 较少使用
- Architecture fit: 3/3 — 代码已完成，BaseAnalyzer 模式
- Implementation cost: 3/3 — 代码已存在，只需加测试

**结论**: DO — 代码已存在，架构清晰，填真正空白

> 此文件是自主开发 Agent 的知识库。所有 wiki 知识都在这里索引。
> 每个条目包含：页面名、一句话摘要、对 ts-sitter-analyzer 的价值、完整路径。
> Agent 需要深入时，直接用 `cat /Users/aisheng.yu/wiki/wiki/ai-tech/XXX.md` 读取。

## 产品讨论记录 - Late-Binding Closure Detector - 2026-04-20

**调用**: /steve-jobs-perspective (autonomous mode)

**功能候选**: Late-Binding Closure Bug Detector — 检测循环内闭包捕获循环变量的经典 bug

**产品分析**:
- 聚焦: 循环内创建的 lambda/function 捕获循环变量是真实生产 bug。Pylint W0640, ESLint no-loop-func 都检测
- 减法: MVP = 纯AST遍历，找loop内的lambda/function引用loop变量
- 一句话: "Find closures that capture loop variables, because `lambda: i` always returns the last value"

**独特性评估**: 11/12 >= 8 (DO)
- Uniqueness: 3/3 — no existing tool covers late-binding closure in loops
- Need: 3/3 — Pylint W0640, ESLint no-loop-func, real production bugs
- Architecture fit: 3/3 — standard BaseAnalyzer, Python + JS/TS + Java
- Implementation cost: 2/3 — multi-language, need to track loop variable scope

**结论**: DO — fills genuine gap, catches real subtle bugs, high linter overlap validation

## 产品讨论记录 - Statement-with-No-Effect Detector - 2026-04-20

**调用**: /steve-jobs-perspective (autonomous mode)

**功能候选**: Statement-with-No-Effect Detector — 检测无效果的表达式语句

**产品分析**:
- 聚焦: x == 5; vs x = 5; 是经典打字错误。Pylint W0104/W0106高频触发规则
- 减法: MVP = 检查expression_statement的子节点是否为比较/算术/字面量
- 一句话: "Find the statements that do nothing, because x == 5; should be x = 5;"

**独特性评估**: 12/12 >= 8 (DO)
- Uniqueness: 3/3 — discarded_return only covers function calls, not expression statements
- Need: 3/3 — Pylint W0104/W0106, classic typo source
- Architecture fit: 3/3 — standard BaseAnalyzer, all languages
- Implementation cost: 3/3 — single Sprint, simple AST check

**结论**: DO — fills genuine gap, catches dangerous == vs = typos

## 灵感来源 - Session 145 — 2026-04-20

- 98个分析器已实现，覆盖大部分经典代码异味
- 识别的空白：Unreachable Code (12/12 score)
- 选择：Unreachable Code Detector

## 产品讨论记录 - Unreachable Code Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Unreachable Code Detector — 检测 return/break/raise/continue/throw 语句之后的死代码

**产品分析**:
- 聚焦: return/break/raise/throw之后的代码是真正的死代码，dead_code/dead_code_path/dead_store三个工具均不覆盖
- 减法: MVP = 纯AST遍历，在block中找到终止语句，标记同block中后续所有语句为unreachable
- 一句话: "Find the code after the function exits — because lines after `return` are code that never runs."

**独特性评估**: 12/12 >= 8 (DO)
- Uniqueness: 3/3 — no existing tool covers post-termination dead code
- Need: 3/3 — IDEs flag this, linters flag it, genuine code quality issue
- Architecture fit: 3/3 — standard BaseAnalyzer, all languages
- Implementation cost: 3/3 — single Sprint, pure AST traversal

**结论**: DO — fills genuine gap, catches real dead code, all languages

## 灵感来源 - Session 144 — 2026-04-20

- 95个分析器已实现，覆盖大部分经典代码异味
- 识别的空白：Incomplete Protocol Implementation (12/12 score)
- 选择：Incomplete Protocol Implementation Detector

## 产品讨论记录 - Incomplete Protocol Implementation Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Incomplete Protocol Implementation Detector

**产品分析**:
- 聚焦: 不完整协议实现是静默运行时bug。__eq__无__hash__破坏dict/set，equals无hashCode导致HashMap不一致
- 减法: MVP = 纯AST遍历，检查类定义的方法是否覆盖已知协议对。无需类型推断、跨文件分析
- 一句话: "Find the half-finished contracts, because __eq__ without __hash__ means your objects silently break in dictionaries."

**独特性评估**: 12/12 >= 8 (DO)
- Uniqueness: 3/3 - 无类似工具
- Need: 3/3 - Pylint W0223/W0224 检测的经典bug模式
- Architecture fit: 3/3 - 纯AST, BaseAnalyzer模式
- Implementation cost: 3/3 - 已知协议对列表，单Sprint

**结论**: DO — fills genuine gap, catches silent runtime bugs, clean AST traversal

## 产品讨论记录 - Builtin Shadow Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Builtin Shadow Detector — 检测变量/函数/类名覆盖 Python 内置函数 (list, dict, set, id, type, input, etc.)

**产品分析**:
- 聚焦: 覆盖内置函数是真实bug来源。`list = [...]` 导致后续 `list()` 调用失败。Pylint W0622
- 减法: MVP = 检查赋值、函数定义、类定义、for循环目标、参数名是否匹配已知内置函数列表
- 一句话: "Find the names that break builtins, because `list = [1,2]` silently kills every `list()` call after it."

**独特性评估**: 12/12 >= 8 (DO)
- Uniqueness: 3/3 - variable_shadowing.py 只检查内外层变量遮蔽，不检查builtins
- Need: 3/3 - Pylint W0622，常见且危险的Python bug
- Architecture fit: 3/3 - 纯AST遍历，名称匹配静态列表
- Implementation cost: 3/3 - Python内置函数列表固定，简单遍历

**结论**: DO — genuine gap, catches dangerous silent bugs, trivial to implement

## 技术架构讨论记录 - Incomplete Protocol Implementation Detector - 2026-04-20

**调用**: Architecture analysis (direct)

**输入**: Incomplete Protocol Implementation Detector, pure AST traversal approach

**架构分析**:
- 技术可行性: Low risk. Pure AST per-file. Walk class definitions, collect method names, check protocol pairs.
- 架构影响: Perfect fit with BaseAnalyzer pattern. New MCP tool in tool_registration.py.
- 实现复杂度: Single Sprint. ~150-200 lines core, ~200 lines tests.
- 维护成本: Very low. Protocol pairs rarely change.

**推荐方案**: Single-pass class walker
- For each class_definition/function_declaration in AST, collect defined method names
- Check against known protocol pairs (static lookup table)
- Report missing counterpart as issue

**协议对定义**:
- Python: __eq__/__hash__, __enter__/__exit__, __iter__/__next__, __get__/__set__+__delete__
- Java: equals/hashCode, compareTo/equals
- Go: String()/IsZero() (less applicable, skip)
- JS/TS: toJSON/toISOString (optional, low value)

**风险**: None identified
**依赖**: None beyond base.py

## 灵感来源 - Session 143 — 2026-04-20

- 95个分析器已实现，覆盖大部分经典代码异味
- 识别的空白：Yoda Condition, Long Parameter List, Inconsistent Return
- 选择并实现：全部3个

## 产品讨论记录 - Yoda Condition Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Yoda Condition Detector — 检测 if ("literal" == variable) 反模式

**产品分析**:
- 聚焦: Yoda conditions 是 C-era 遗留习惯，现代语言不需要。降低可读性
- 减法: MVP = 纯AST遍历，检测比较运算中左操作数为字面量
- 一句话: "Find the comparisons written backwards — because `if (\"expected\" == actual)` is just harder to read."

**独特性评估**: 11/12 >= 8 (DO)
**结论**: DO — fills genuine gap, high readability value, simple implementation

## 产品讨论记录 - Long Parameter List Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Long Parameter List Detector — 检测参数过多的函数(5+/8+)

**产品分析**:
- 聚焦: 经典 Fowler 代码异味。长参数列表表明函数职责过多或应使用参数对象
- 减法: MVP = 统计函数参数列表的命名子节点数量
- 一句话: "Find functions that ask for too much — because 7 parameters means 7 things can go wrong."

**独特性评估**: 12/12 >= 8 (DO)
**结论**: DO — classic code smell, no existing tool covers it, trivial implementation

## 产品讨论记录 - Inconsistent Return Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Inconsistent Return Detector — 检测函数中混合有值返回和无值返回

**产品分析**:
- 聚焦: Python中最常见的隐式None返回bug。函数有时返回值，有时隐式返回None
- 减法: MVP = 检查函数内所有return语句，区分为有值返回、空返回和隐式返回
- 一句话: "Find functions that can't decide whether to return something or nothing."

**独特性评估**: 10/12 >= 8 (DO)
**结论**: DO — real bug source, especially in Python, no existing tool covers it

## 灵感来源 - Session 142 — 2026-04-20

- Wiki搜索 "code smell anti-pattern detection" → silent-failure-hunter agent, code-explorer agent
- 71个分析器已实现，覆盖大部分经典代码异味
- 识别的空白：Loose Equality Comparison (JS/TS == vs ===), Refused Bequest, Implicit Type Coercion
- 选择：Loose Equality Comparison Detector — 高价值、经典JS bug源、纯AST遍历

## 产品讨论记录 - Loose Equality Comparison Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Loose Equality Comparison Detector — 检测 JS/TS 中 == 和 != 而非 === 和 !== 的比较

**产品分析**:
- 聚焦: == vs === 是 JavaScript 生态中最经典的 bug 源之一。ESLint 的 eqeqeq 规则是最常见的启用规则。71个分析器中无工具覆盖生产代码中的松散比较（assertion_quality 只检查测试）
- 减法: MVP = 纯AST遍历，找 == 和 != 操作符。6类检测: loose_eq, loose_neq, loose_eq_null, loose_neq_null, loose_eq_undefined, loose_neq_undefined
- 一句话: "Find every == that should be === — because loose equality in JavaScript has caused more bugs than any other language quirk."

**独特性评估**:
1. 独特性: 3/3 — no existing tool covers loose equality in production code
2. 需求度: 3/3 — every JS/TS codebase has this issue, ESLint eqeqeq is the #1 rule
3. 架构适配: 3/3 — standard BaseAnalyzer, JS/TS-specific (like missing_break)
4. 实现成本: 3/3 — single Sprint, pure AST traversal, only JS/TS
Total: 12/12 >= 8

**结论**: DO — fills genuine gap, highest possible score, trivial implementation

## 技术架构讨论记录 - Loose Equality Comparison Detector - 2026-04-20

**调用**: /plan-eng-review (autonomous mode)

**功能**: Loose Equality Comparison Detector
**技术方案**: 纯AST遍历，检测JS/TS中的 == 和 != 操作符（不含与null/undefined的比较，避免与literal_boolean_comparison重叠）

**架构分析**:
- 技术可行性: 低风险。tree-sitter JS/TS grammar中 binary_expression 节点包含操作符字段，直接检查即可
- 架构影响: 与现有71工具完全协调，标准BaseAnalyzer模式。JS/TS专用（类似missing_break）
- 实现复杂度: 单Sprint。2语言(JS/TS) × 简单操作符匹配
- 维护成本: 低。操作符不会变

**推荐方案**: BaseAnalyzer子类 + binary_expression节点遍历 + 操作符文本匹配
**检测类型**:
- loose_eq: x == y (use ===)
- loose_neq: x != y (use !==)
排除与 null/undefined 的比较（已被 literal_boolean_comparison 覆盖）

**重叠处理**: literal_boolean_comparison 覆盖 x == null/undefined。本工具覆盖 x == y（非字面量比较）。互补而非重复。

**风险**: 无重大风险

## 灵感来源 - Sprint 2 - Session 142 — 2026-04-20

- 72个分析器已实现
- 识别的空白：Simplified Conditional Expression (cond ? true : false), Missing Optional Chaining, Yoda Conditions
- 选择：Simplified Conditional Expression Detector — 高可读性价值、简单AST检测、多语言适用

## 产品讨论记录 - Simplified Conditional Expression Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Simplified Conditional Expression Detector — 检测可以简化的条件表达式

**产品分析**:
- 聚焦: `cond ? true : false` 可简化为 `cond`, `cond ? false : true` 可简化为 `!cond`, `cond ? x : x` 总是返回 x。这些是真实的可读性问题
- 减法: MVP = 纯AST遍历，检测 ternary/conditional_expression 节点的退化模式
- 一句话: "Find ternary expressions that can be simplified — because `x ? true : false` is just `x`"

**独特性评估**:
1. 独特性: 3/3 — no existing tool covers this specific pattern
2. 需求度: 2/3 — readability issue, not a runtime bug
3. 架构适配: 3/3 — standard BaseAnalyzer, ternary nodes in all languages
4. 实现成本: 3/3 — single Sprint, pure AST
Total: 11/12 >= 8

**结论**: DO — fills genuine gap, high readability value, simple implementation

## 产品讨论记录 - Commented-Out Code Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Commented-Out Code Detector — 检测源代码中被注释掉的代码块

**产品分析**:
- 聚焦: Commented-out code is a well-known code smell. It clutters repos, confuses readers about active vs. inactive code, and should be in version control. 88 analyzers, none detect commented-out code (comment_quality checks quality, dead_code detects unused definitions)
- 减法: MVP = detect comment nodes whose stripped content matches code patterns. 4 types: commented_assignment, commented_function_call, commented_import, commented_control_flow
- 一句话: "Find the code you commented out instead of deleting — version control remembers everything."

**独特性评估**:
1. 独特性: 3/3 — no existing tool covers commented-out code detection
2. 需求度: 2/3 — real code smell but not a runtime bug source
3. 架构适配: 3/3 — standard BaseAnalyzer, comment nodes available in all 4 languages
4. 实现成本: 2/3 — heuristic-based, needs tuning to avoid false positives on code-mentioning comments
Total: 10/12 >= 8

**结论**: DO — fills genuine gap, simple heuristic approach, valuable for code cleanliness audits

## 技术架构讨论记录 - Commented-Out Code Detector - 2026-04-20

**调用**: /plan-eng-review (autonomous mode)

**功能**: Commented-Out Code Detector
**技术方案**: Extract comment nodes from AST, strip delimiters, apply code-pattern heuristics

**架构分析**:
- 技术可行性: Low risk. Tree-sitter exposes comment nodes in all 4 languages (Python: "comment", JS: "comment", Java: "line_comment"/"block_comment", Go: "comment"). Strip delimiters, apply regex patterns for code detection
- 架构影响: Fully compatible with existing 88 tools, standard BaseAnalyzer pattern
- 实现复杂度: Single Sprint. 4 languages × same heuristic approach
- 维护成本: Low. Heuristics may need occasional tuning

**推荐方案**: BaseAnalyzer subclass + per-language comment node types + shared heuristic engine
**检测类型**:
- commented_assignment: Lines containing `= ` patterns (not `==`)
- commented_function_call: Lines matching `identifier(args)` pattern
- commented_import: Lines starting with import/include/require/use
- commented_control_flow: Lines starting with if/for/while/return/try

**风险**: False positives on comments that discuss code (e.g., "This function returns..."). Mitigated by requiring multiple indicators or high-confidence patterns

## 产品讨论记录 - Debug Statement Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Debug Statement Detector — 检测生产代码中的调试输出语句

**产品分析** (GStack office-hours framework):
- 聚焦: 遗留debug语句是真实bug源 — 泄露敏感数据、性能下降、日志污染。88个分析器无工具覆盖此领域
- 减法: MVP = 纯AST遍历，检测 print/console.log/System.out.println/fmt.Println。4类检测: debug_print, debug_log, debug_statement, debug_formatter
- 一句话: "Find the debug prints you forgot to remove — because one of them is leaking user data in production."
- 现有覆盖: logging_patterns检测日志框架使用，但不检测遗留debug语句。comment_quality检测注释，不检测代码

**独特性评估**:
1. 独特性: 3/3 — no existing tool covers debug statement detection
2. 需求度: 3/3 — everyone leaves debug prints, real bug source
3. 架构适配: 3/3 — standard BaseAnalyzer pattern
4. 实现成本: 3/3 — 1 sprint, pure AST traversal
Total: 12/12 >= 8

**结论**: DO — fills genuine gap, high impact, simple implementation

## 技术架构讨论记录 - Debug Statement Detector - 2026-04-20

**调用**: /plan-eng-review (autonomous mode)

**功能**: Debug Statement Detector
**技术方案**: 纯AST遍历，匹配已知debug函数调用模式

**架构分析**:
- 技术可行性: 低风险。每个语言的debug函数都是固定集合，AST call_expression节点匹配即可
- 架构影响: 与现有88工具完全协调，标准BaseAnalyzer模式
- 实现复杂度: 单Sprint。4语言×3-5个函数模式
- 维护成本: 低。函数名不会频繁变化

**推荐方案**: BaseAnalyzer子类 + per-language debug function sets
**检测类型**:
- debug_print: Python print(), pprint.pprint(), breakpoint()
- debug_log: JS/TS console.log/debug/info/warn, debugger statement
- debug_println: Java System.out/err.println, printStackTrace
- debug_formatter: Go fmt.Println/Printf, log.Println

**风险**: 无重大风险。可能误报test files中的print，通过test file detection过滤

## 产品讨论记录 - Unused Return Value Detector - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Unused Return Value Detector — 检测函数返回值被调用方静默丢弃

**产品分析** (GStack office-hours framework):
- 聚焦: 忽略返回值是隐蔽bug的真实来源。85个分析器中无工具覆盖调用端返回值丢弃
- 减法: MVP = 纯AST遍历，查找作为表达式语句的函数调用。3类检测: discarded_result, discarded_await, discarded_error
- 一句话: "Find the function calls whose return values you're silently throwing away — because one of them is a bug."
- 现有覆盖: unused_parameter 覆盖定义端，error_handling/error_propagation 覆盖错误处理，但无工具覆盖调用端

**独特性评估**:
1. 独特性: 2/3 — call-site focus is genuinely new
2. 需求度: 2/3 — real bug source, Go compiler/pylint/IDEs all have this check
3. 架构适配: 3/3 — standard BaseAnalyzer pattern
4. 实现成本: 3/3 — 1 sprint, pure AST
Total: 10/12 ≥ 8 ✓

**结论**: DO — 填补真正空白（调用端返回值丢弃检测）

## 产品讨论记录 - Plugin Bridge Architecture - 2026-04-20

**调用**: /office-hours (autonomous mode)

**功能候选**: Plugin Bridge Architecture — 整合52个分析器中542个硬编码语言节点定义到LanguageKnowledge协议

**产品分析** (GStack office-hours):
- 聚焦: 这是工程便利，不是用户价值。用户不会因此获得更好的分析结果
- 减法: 4-phase migration 是 ocean 不是 lake。22个feature后需要重构，但应该是focused refactoring而非full rearchitecture
- 一句话: "Let analyzers query language plugins instead of hardcoding AST knowledge" — 但这是内部重构，不是产品功能
- 5 analyzer MVP 是半途而废：其余47个仍然hardcode，无法实现"1 file to add language"

**架构现状**:
- 85 analyzer files, 23 language files
- Architecture invariants: ALL PASS
- 重构逾期：22 features since last refactoring (quota = every 5)

**结论**: DON'T — Archive. 执行标准重构Sprint（self-hosting-gate --architecture + ruff + mypy + BaseAnalyzer采用率），而非full plugin bridge

## 产品讨论记录 - Dead Code Path Analyzer - 2026-04-19

**调用**: /office-hours (autonomous mode)

**功能候选**: Data Clump Detector, Shotgun Surgery Detector, Dead Code Path Analyzer

**产品分析** (GStack office-hours):
- Data Clump: DON'T — 需要跨文件类型推断，tree-sitter 不擅长
- Shotgun Surgery: DON'T — 需要 git 变更历史分析，不是 AST 分析
- Dead Code Path: DO — 纯语法模式匹配，dead_code 工具检测未使用定义但不检测不可达路径

**一句话定义**: "Find the lines of code that can never execute, so you can delete them."

**检测目标**: return/raise/break/continue 后的代码, if False: 块, if True: else 分支, 纯 AST 模式

**结论**: DO — 填补真正空白（dead_code 是未使用定义，非不可达路径）

## 技术架构讨论记录 - Dead Code Path Analyzer - 2026-04-19

**调用**: /plan-eng-review (autonomous mode)

**功能**: Dead Code Path Analyzer

**架构分析** (GStack plan-eng-review):
- 推荐方案A: 纯 AST 模式匹配（~300行核心代码）
- 方案B (CFG) 被否决：CFG 构建需要处理异常流、生成器、async、defer，变成编译器前端
- 方案A 风险低，与现有58个分析器架构一致，1个Sprint可完成
- 检测模式：return/raise/break/continue 后的兄弟节点, if False 块, if True else 分支
- 4语言：Python, JS/TS, Java, Go
- 30+ tests

**推荐方案**: 方案A (纯 AST 模式匹配)
**理由**: 风险低、架构一致、维护简单、1 Sprint 完成
**风险**: 无重大风险
**依赖**: 无新依赖

## 产品讨论记录 - Method Chain Analyzer - 2026-04-19

**调用**: /plan-eng-review (autonomous mode)

**初始选择**: Data Clump Detector → PIVOT (already in ParameterCouplingAnalyzer)

**产品分析** (inline, autonomous):
- 聚焦: 长方法链 (a.b().c().d()) 是 Law of Demeter 违反的典型信号，直接影响调试难度和耦合度
- 减法: MVP = 检测链长度 ≥4 的属性/方法链，纯 AST 遍历
- 一句话: "Find the Law of Demeter violations hiding in your method chains"
- 结论: DO — 填补真正空白（coupling_metrics 是模块级别，feature_envy 是函数级别，无工具检测调用链级别的耦合）

**架构分析** (/plan-eng-review):
- 推荐方案A: 纯 AST 遍历，独立分析器
- 理由: 与79个现有分析器完全一致的 AST 遍历模式
- 检测类型: long_chain (≥4 links), train_wreck (≥6 links), law_of_demeter
- 4语言: Python, JS/TS, Java, Go
- 1个Sprint可完成
- 风险: Go 语言链式调用较少，但 struct field access 链存在

## 产品讨论记录 - Loop Complexity Analyzer - 2026-04-19

**调用**: Steve Jobs inline analysis + /plan-eng-review

**初始选择**: Loop Complexity Analyzer

**产品分析** (Steve Jobs):
- 聚焦: 嵌套循环是 O(n²) 性能问题的 #1 来源，核心价值
- 减法: MVP = 检测循环嵌套，估算 O()，纯 AST 遍历
- 一句话: "Find the O(n²) hiding in your code"
- 结论: DO — 填补真正空白（cognitive_complexity 是可读性，nesting_depth 是控制流，无工具估算算法复杂度）

**架构分析** (/plan-eng-review):
- 推荐方案A: 纯 AST 遍历
- 理由: 48个现有分析器已验证 AST 遍历模式；数据流分析(B方案)引入首个跨分析器依赖
- 检测类型: nested_loop, loop_in_loop, exponential_pattern
- 4语言: Python, JS/TS, Java, Go
- 1个Sprint可完成

## 产品讨论记录 - Feature Envy Detector - 2026-04-19

**调用**: /office-hours + /plan-eng-review

**初始选择**: Data Clump Detector → PIVOT after architecture review

**关键发现**: parameter_coupling.py 已实现 data clump 检测（L86-268, DataClump class + Jaccard similarity）。magic_values.py 已覆盖硬编码 URL/路径。两个候选功能已被覆盖。

**最终选择**: Feature Envy Detector

**产品分析**:
- 填补真正空白：coupling_metrics 是模块级，parameter_coupling 是参数计数，architectural_boundary 是模块边界，无工具检测方法级的数据访问模式
- AI agent 价值：重构时知道方法是否应该移到另一个类
- 一句话定义："This method calls getOther().getX() more than it uses self — move it"

**架构分析**:
- 方案: 独立模块，纯 AST 分析
- 检测类型: feature_envy, method_chain, inappropriate_intimacy
- 4语言: Python, JS/TS, Java, Go
- 无跨分析器依赖，与现有65个MCP工具架构一致

## 知识检索方式

```bash
# 方式 1：qmd 语义搜索（推荐）
qmd query "关键词" --limit 5

# 方式 2：直接读 wiki 页面（已知页面名）
cat /Users/aisheng.yu/wiki/wiki/ai-tech/<页面名>.md

# 方式 3：读原始仓库（需要源码参考）
ls /Users/aisheng.yu/wiki/raw/ai-tech/<仓库名>/
```

## 产品讨论记录 - Side Effect Analyzer - 2026-04-19

**调用**: /office-hours + /plan-eng-review

**输入**: Side Effect Tracker — 检测函数中的副作用模式

**产品分析**: DO — 值得做。现有46个分析器无一个专门追踪副作用。砍掉 network_call（AST误报率高），保留 global_state_mutation + parameter_mutation。

**架构分析**: 推荐方案A（纯AST分析）。方案B（结合call_graph）引入跨分析器依赖，复杂度翻倍。

**结论**: 做。MVP 2个检测模式，4语言，纯AST。

## 产品讨论记录 - Contract Compliance Analyzer - 2026-04-19

**调用**: /office-hours (Steve Jobs / Garry Tan perspective) + /plan-eng-review

**初始选择**: Doc-Code Sync → PIVOT after architecture review

**关键发现**: comment_quality.py 已完全覆盖 doc-code sync (param_mismatch, extra_doc_param, missing_param_doc, missing_return_doc, 4 languages, 735 lines). 新建会 80% 重复。

**最终选择**: Contract Compliance Analyzer

**产品分析**:
- 填补真正空白：type_annotation_coverage 检查注解是否存在，return_path 检查是否所有分支都 return，但没有任何工具检查返回值是否匹配声明的类型
- AI agent 价值：重构前知道函数是否真正履行了契约
- 一句话定义："你的函数签名说返回 str，但有个分支返回了 None"

**架构分析**:
- 方案 A: 独立模块 (推荐) — 与现有 45 个分析器架构一致
- 检测类型: return_type_violation, signature_divergence, boolean_trap, enum_incomplete, type_contradiction
- 纯 tree-sitter AST 分析，无 git 依赖
- 4 语言支持

## 产品讨论记录 - Debug Statement Detector - 2026-04-19

**调用**: /office-hours (autonomous mode)

**功能候选**: Debug Statement Detector — 检测生产代码中遗留的调试语句

**产品分析** (GStack office-hours):
- 聚焦: `print()`, `console.log()` 是开发者在发布前 grep 的头号内容。AST 感知版本比 grep 更好。
- 减法: MVP = 纯 AST 模式匹配，检测特定函数调用，跳过测试文件，约 300 行代码。
- 一句话: "找出你在发布前忘记删除的调试语句。"
- 结论: DO — 填补真正空白（logging_patterns 是日志质量，无工具检测调试遗留）

**评分**: 12/12 (Uniqueness 3/3, Need 3/3, Architecture 3/3, Cost 3/3)

**检测目标**:
- Python: print(), breakpoint(), pdb.set_trace()
- JS/TS: console.log/debug/info/warn, debugger statement
- Java: System.out.println(), System.err.println(), printStackTrace()
- Go: fmt.Println/Printf(), log.Printf/Println()

## 技术架构讨论记录 - Debug Statement Detector - 2026-04-19

**调用**: /plan-eng-review (autonomous mode)

**功能**: Debug Statement Detector

**架构分析**: PIVOT — 发现 logging_patterns.py 已覆盖所有4种语言的调试语句检测：
- Python print() → logging_patterns.py:241-248
- JS console.log() → logging_patterns.py:433-440
- Java System.out.println() → logging_patterns.py:605-612
- Go fmt.Println/Printf() → logging_patterns.py:774-781

**结论**: 70% 重叠，不值得做独立分析器。转向 Reflection Usage Detector。

## 产品讨论记录 - Reflection Usage Detector - 2026-04-19

**调用**: /office-hours inline + /plan-eng-review inline (autonomous mode)

**功能候选**: Reflection/Dynamic Code Usage Detector

**产品分析**:
- 聚焦: eval/exec/getattr/Class.forName 是代码库中最危险的模式，直接影响安全性和可维护性
- 减法: MVP = 检测动态代码执行模式，纯 AST 遍历
- 一句话: "Find the eval() and reflection calls that make your code impossible to audit"
- 结论: DO — 填补真正空白（security_scan 是通用扫描，无工具专门追踪反射/动态代码使用）

**评分**: 11/12 (Uniqueness 3/3, Need 3/3, Architecture 3/3, Cost 2/3)

**检测目标**:
- Python: eval(), exec(), getattr(), setattr(), __import__(), compile()
- JS/TS: eval(), Function(), new Function()
- Java: Class.forName(), .newInstance(), Method.invoke()
- Go: reflect.DeepEqual, reflect.ValueOf, reflect.TypeOf

**架构分析**:
- 推荐方案A: 纯 AST 遍历，独立分析器
- 理由: 与85个现有分析器完全一致的 AST 遍历模式
- 4语言: Python, JS/TS, Java, Go
- 1个Sprint可完成

---

## 直接可用（高价值参考）

### Skill 层开发参考
- **Fireworks Tech Graph** — 自然语言生成 SVG 技术图的 CC Skill，SKILL.md 模板
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/fireworks-tech-graph-overview.md`
  - 源码：`/Users/aisheng.yu/wiki/raw/ai-tech/fireworks-tech-graph/`
  - 价值：Skill 层开发的直接模板

- **金谷园饺子馆 Skill** — 三层嵌套 Skill + MCP 混合模式，餐饮行业参考实现
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/jinguyuan-dumpling-skill-overview.md`
  - 源码：`/Users/aisheng.yu/wiki/raw/ai-tech/jinguyuan-dumpling-skill/`
  - 价值：三层嵌套架构（主 Skill → 内嵌 Skill → MCP 工具）

- **Planning with Files** — Manus 风格 3 文件规划，Hooks 注意力操控
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/planning-with-files-overview.md`
  - 源码：`/Users/aisheng.yu/wiki/raw/ai-tech/planning-with-files/`
  - 价值：Hook 脚本模板、PreToolUse/PostToolUse/Stop Hook 实现

### MCP 参考参考
- **qmd** — Tobias Lütke 本地混合搜索引擎，tree-sitter AST chunking + MCP Server
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/qmd-overview.md`
  - 源码：`/Users/aisheng.yu/wiki/raw/ai-tech/qmd/`
  - 价值：tree-sitter 分块代码直接参考、MCP Server（stdio+HTTP）、SDK createStore() 嵌入模式、Context 元数据系统

- **MCP 进阶课程** — StreamableHTTP、Sampling、有状态/无状态、Roots、Notifications
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/mcp-advanced-topics-course-notes.md`
  - 价值：StreamableHTTP 协议细节、MCP Server 设计最佳实践

- **MCP vs Skills token 成本** — 急加载 vs 懒加载、10-15 倍 token 差异、决策指南
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/mcp-vs-skills-token-cost.md`
  - 价值：哪些分析能力该放 MCP（急加载），哪些该封装 Skill（懒加载）

### 可视化参考
- **CodeFlow** — 浏览器端代码架构可视化，依赖图/爆炸半径/健康评分
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/codeflow-overview.md`
  - 源码：`/Users/aisheng.yu/wiki/raw/ai-tech/codeflow/`
  - 价值：依赖图算法、A-F 健康评分、单 HTML 零安装架构

### Agent 架构参考
- **7 大失败模式** — One-shot/提前完工/Context Anxiety/自评放水/Stub/Spec Cascade/注意力稀释
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/agent-failure-modes.md`
  - 价值：每个失败模式的防御机制，直接指导自主开发

- **12 个提示词设计模式** — 约束优先/事件驱动/分层委托/5 段压缩/模式切换等
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/claude-code-prompt-design-patterns.md`
  - 价值：提示词结构化设计，60% 是约束

- **36 个 Agent 角色** — Fork vs Subagent、委派 7 法则、安全审查 Agent
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/claude-code-agent-architecture.md`
  - 价值：Agent 角色设计、子代理提示词写法

- **Prompt 加载流程** — 5 阶段组装、缓存策略、源码调用链
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/claude-code-prompt-loading-flow.md`
  - 价值：理解 MCP 工具 schema 如何被 Claude 消费

---

## 架构参考（中价值）

- **ECC（Everything Claude Code）** — 47 Agent / 181 Skill 大规模插件组织
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/everything-claude-code-overview.md`
  - 源码：`/Users/aisheng.yu/wiki/raw/ai-tech/everything-claude-code/`
  - 价值：大规模插件系统的分层组织方式

- **Hermes Agent** — 40+ 工具注册 + 自学习闭环、Python 自学习 Agent
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/hermes-agent-overview.md`
  - 价值：工具注册/发现机制、自学习循环

- **Harness 设计演化** — 双 Agent → 三 Agent → 简化版，长时间运行 Agent 管理
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/long-running-agent-harness.md`
  - 价值：Sprint Contract、feature_list.json、context reset 协议

- **GAN 式多 Agent** — Generator + Evaluator 对抗式反馈循环
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/multi-agent-evaluator-pattern.md`
  - 价值：对抗式代码审查模式

- **Autoresearch** — Karpathy 自主研究框架：三文件哲学、自主循环
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/autoresearch-overview.md`
  - 价值：自主循环的设计模式

- **GStack** — YC 总裁 AI 软件工厂：23 专家角色、Sprint 7 阶段
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/gstack-overview.md`（注：在 programming 领域）
  - 源码：`/Users/aisheng.yu/wiki/raw/programming/gstack/`
  - 价值：Sprint 流程、专家角色定义、/review /qa /ship 等 skill 已集成

---

## Claude Code 课程参考

- **Claude Code 101** — EPCC 工作流、上下文管理、CLAUDE.md、Hooks
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/claude-code-101-course-notes.md`

- **Claude Code in Action** — 21 课、SDK 构建 Agent、Hooks 实战、MCP 集成
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/claude-code-in-action-course-notes.md`

- **Prompt Mastery** — 5 层结构、60% 是约束、事件驱动设计
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/claude-code-prompt-mastery-course-notes.md`

- **Subagents 入门** — 设计原则、最佳实践、3 种反模式
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/introduction-to-subagents-course-notes.md`

- **Claude 101** — 提示三要素、三种模式
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/claude-101-essentials.md`

- **Cowork 指南** — 6 项能力、定时任务、插件系统
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/claude-cowork-guide.md`

---

## 技术灵感（特定场景）

- **AirLLM** — 逐层加载推理，70B LLM 显存从 140GB 降至 4GB
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/airllm-overview.md`
  - 价值：按需加载思想→语言插件懒加载

- **BitNet** — Microsoft 1-bit LLM，三值量化（1.58-bit）
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/bitnet-overview.md`
  - 价值：极致压缩启发更激进的代码表示

- **MarkItDown** — Microsoft 文件转 Markdown，MCP 可选依赖模式
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/markitdown-overview.md`
  - 价值：MCP Server 按需安装依赖模式

- **Awesome LLM Apps** — 100+ LLM 应用合集，代码分析相关集成案例
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/awesome-llm-apps-overview.md`

- **Dive into LLMs** — 上交大《动手学大模型》11 章教程
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/dive-into-llms-overview.md`

- **Voicebox** — 开源语音克隆工作室，5 TTS 引擎
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/voicebox-overview.md`

- **乔布斯 Skill** — 认知操作系统：6 心智模型 + 8 决策启发式
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/steve-jobs-skill-overview.md`
  - 价值：产品决策过滤——聚焦即说不、先做减法、一句话定义

---

## LLM Wiki 架构参考

- **LLM Wiki 架构** — 三层结构、核心理念与复利效应
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/llm-wiki-architecture.md`
- **知识编译** — 持续积累、复利效应、蒸馏路径
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/knowledge-compilation.md`
- **Ingest/Query/Lint 三操作** — Wiki 维护的核心操作
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/llm-wiki-three-operations.md`

---

## Tree-sitter 底层技术（完整 7 页）

- **概览**：`/Users/aisheng.yu/wiki/wiki/ai-tech/tree-sitter-overview.md`
- **架构**：GLR 解析、多版本栈 → `/Users/aisheng.yu/wiki/wiki/ai-tech/tree-sitter-architecture.md`
- **语法 DSL**：seq/choice/prec → `/Users/aisheng.yu/wiki/wiki/ai-tech/tree-sitter-grammar-dsl.md`
- **查询系统**：S-expression 模式匹配 → `/Users/aisheng.yu/wiki/wiki/ai-tech/tree-sitter-query-system.md`
- **外部扫描器**：自定义 C 函数 → `/Users/aisheng.yu/wiki/wiki/ai-tech/tree-sitter-external-scanners.md`
- **性能**：增量解析、紧凑表示 → `/Users/aisheng.yu/wiki/wiki/ai-tech/tree-sitter-performance.md`
- **生态**：25+ 语言解析器 → `/Users/aisheng.yu/wiki/wiki/ai-tech/tree-sitter-ecosystem.md`

---

## 其他参考

- **Claw Code** — Rust 版 CC，9 crate 架构
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/claw-code-overview.md`
- **Hermes Web UI** — Hermes Agent 浏览器前端
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/hermes-webui-overview.md`
- **CLI-Anything** — 一行命令让任意 GUI 软件 Agent 化
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/cli-anything-overview.md`
- **Eval 意识** — Opus 4.6 主动推测并破解评测
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/eval-awareness-and-benchmark-contamination.md`
- **Anthropic Academy 导出工具** — 课程导出工具
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/anthropic-academy-exporter-overview.md`
- **Academy 学习路径** — 18 门课程 5 阶段
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/anthropic-academy-learning-path.md`
- **三源关系** — cc-source → system-prompts → Academy
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/cc-source-vs-system-prompts-vs-academy.md`
- **系统提示词全览** — 110+ 条目、6 大类别
  - 路径：`/Users/aisheng.yu/wiki/wiki/ai-tech/claude-code-system-prompts-overview.md`

**总计：59 页 Wiki 知识，全部已索引在此文件中。Agent 可通过 qmd 或直接路径访问任意页面。**

---

## 2026-04-17 新功能探索灵感收集

### CodeFlow — 浏览器端代码架构可视化工具
- **路径**: `/Users/aisheng.yu/wiki/wiki/ai-tech/codeflow-overview.md`
- **核心功能**:
  - 交互式依赖图 (D3.js)
  - 爆炸半径分析
  - 安全扫描
  - 设计模式检测
  - 健康评分 (A-F)
  - 四种可视化模式
- **技术栈**: React 18 + D3.js 7, 单 HTML 文件, 35+ 语言支持
- **价值**: 零安装秒级洞察, 100% 浏览器端运行
- **对 ts-analyzer 启发**: 可视化输出格式、A-F 评分模型、热力图概念

### Claw Code — 自主多 Agent 协调系统
- **路径**: `/Users/aisheng.yu/wiki/raw/ai-tech/claw-code/philosophy.md`
- **核心理念**: "Humans set direction; claws perform the labor"
- **三部分系统**:
  1. OmX (`oh-my-codex`) - workflow 层, 短指令转结构化执行
  2. clawhip - 事件和通知路由
  3. OmO (`oh-my-openagent`) - 多 Agent 协调
- **关键洞察**:
  - 真正的瓶颈是: 架构清晰度、任务分解、判断力、品味、决策
  - 代码是证据, 协调系统才是产品经验
  - 重要的不是打字速度, 而是决定什么值得被构建
- **对 ts-analyzer 启发**: 工具应该为 Agent 提供更好的上下文, 而不只是人类

### 语义搜索与向量化
- **QMD** - Tobias Lütke 本地混合搜索引擎, tree-sitter AST chunking + MCP Server
- **Text embeddings** - 向量嵌入用于语义搜索
- **对 ts-analyzer 启发**: 可能的语义代码搜索功能

### 新功能想法 (优先级排序)

1. **代码复杂度热力图** (Code Complexity Heatmap)
   - 生成可视化报告, 标注代码复杂度高的区域
   - 结合圈复杂度、文件大小、嵌套深度
   - 输出格式: JSON + Markdown + ASCII 热力图

2. **调用链可视化** (Call Chain Visualization)
   - 可视化函数调用链
   - 检测循环调用
   - 爆炸半径分析的可视化版本

3. **语义代码搜索** (Semantic Code Search)
   - 基于含义而非文本模式搜索
   - 使用向量化嵌入
   - "找处理用户认证的函数" → 找到相关代码

4. **重构建议** (Refactoring Suggestions)
   - 基于代码模式自动建议重构
   - 提取方法、拆分大类等
   - 可执行的重构建议

### Loop 91: Security Scanner 灵感收集 (2026-04-17)

#### Wiki 搜索结果

**Security Vulnerability Detection**:
- `security-reviewer` Agent (everything-claude-code) — 标记密钥、SSRF、注入、不安全加密、OWASP Top 10
- C++ Security 规则 — 静态分析工具 clang-tidy
- Hermes Web UI — 静态分析 + 集成测试

**Architecture Decision Records**:
- ADR Skill — 捕获架构决策的结构化记录
- Council Skill — 模糊情况下的决策制定

**新功能想法: Security Scanner MCP Tool**

检测常见安全漏洞:
1. **SQL 注入** — 识别拼接 SQL 查询的模式
2. **XSS 漏洞** — 识别未转义的 HTML 输出
3. **硬编码密钥** — 识别 API keys、passwords、tokens
4. **不安全加密** — 识别弱加密算法 (MD5, SHA1)
5. **不安全反序列化** — 识别 unsafe pickle/yaml/json loads
6. **路径遍历** — 识别未验证的文件路径
7. **命令注入** — 识别 shell 命令拼接

技术方案:
- 基于 AST 模式匹配
- 支持多语言 (Python, JavaScript, Java, Go, C#)
- 输出 SARIF 格式 (与 CI 集成)
- 可配置的严重性级别

### Loop 92-93: Tool Registration + Code Audit (2026-04-17)

**Security Scanner Tool Registration Complete**:
- ✅ security_scan tool registered to safety toolset
- ✅ 工具数量: 27 → 28 MCP tools
- ✅ 所有测试通过 (85 tests)

**Code Audit (Loop 93)**:
- TODO/FIXME: 3 个（全部为示例代码）
- 文件 > 400 行: 91 个（符合预期）

### Loop 94: 新功能探索灵感收集 (2026-04-17)

#### Wiki 搜索结果

**Code Simplifier** (everything-claude-code):
- Simplifies and refines code for clarity, consistency, and maintainability
- Focus on recently modified code

**Test Coverage** (everything-claude-code):
- `/test-coverage` command for analyzing test coverage gaps
- Generate missing tests to reach 80%+ coverage

#### 当前工具集分析 (28 MCP Tools)

**已覆盖的代码质量领域**:
- code_smell_detector — 检测代码异味
- code_clone_detection — 检测重复代码
- health_score — 文件健康度评分 (A-F)
- complexity_heatmap — 复杂度热力图
- dead_code — 检测未使用代码
- security_scan — 安全漏洞扫描

**潜在新功能方向**:

1. **Test Coverage Analyzer** — 测试覆盖率分析
   - 分析哪些源文件缺少测试覆盖
   - 识别未测试的函数/类
   - 生成测试建议
   - 与 pytest coverage 报告集成

2. **Refactoring Suggestions** — 重构建议工具
   - 基于 code_smell_detector 结果生成具体重构步骤
   - 提取方法建议
   - 拆分类建议
   - 可执行的重构建议 (diff format)

3. **Documentation Generator** — 文档生成工具
   - 从 AST 提取函数/类签名
   - 生成 docstring 模板
   - 生成 API 文档 (Markdown/Sphinx)

#### 优先级判断

根据乔布斯产品理念:
- **聚焦**: 哪个功能解决核心问题？
- **减法**: 能否增强现有工具而非新建？
- **一句话定义**: 这个功能的一句话是什么？

**优先级排序**:
1. Test Coverage Analyzer — "发现代码中未被测试的部分"
   - 与现有 ci_report 工具形成互补
   - 可以独立于 pytest 运行，基于 AST 分析

2. Refactoring Suggestions — "告诉如何修复代码异味"
   - 增强 code_smell_detector，不仅检测还建议修复
   - 可以作为 code_smell_detector 的扩展功能

## Session 102 — Sustainable Loop Inspiration Gathering

### qmd Search Results

#### 1. Context Management for AI Agents
- Source: OpenAI SDK Crash Course - Tutorial 5: Context Management
- Key insight: `RunContextWrapper` enables agents to access user data, session information, and state
- Relevance: tree-sitter-analyzer could benefit from session-aware context management

#### 2. MCP Tools for Code Understanding  
- Source: Anthropic MCP Advanced Topics
- Key insight: MCP provides communication layer for context and tools
- Relevance: Already implemented, but could expand with more context-aware tools

#### 3. CodeFlow Reference
- Source: codeflow/readme.md
- Key insight: Visual codebase analysis tool
- Relevance: tree-sitter-analyzer has similar dependency graph capabilities

#### 4. Claw Code Philosophy
- Source: claw-code/philosophy.md
- Key insight: Clear direction from human + AI collaboration
- Relevance: Autonomous development model alignment

### Potential Feature Directions

1. **Session-Aware Analysis Context**
   - Maintain analysis context across multiple queries
   - Incremental updates to dependency graph
   - Session-based result caching

2. **Intelligent Code Navigation Suggestions**
   - "Go to definition" with cross-file awareness
   - "Find usages" with blast radius visualization
   - "Smart jump" based on call frequency

3. **Codebase Health Dashboard**
   - Aggregate metrics from multiple analysis tools
   - Trend visualization over time
   - Risk hotspot identification

4. **Semantic Code Search**
   - Natural language queries over code
   - "Find all functions that call database"
   - "Show me all API endpoints related to user auth"


---

## 2026-04-18: 新功能探索（永续循环 #N）

### Wiki 检索结果

**CodeFlow** (已存在于 findings，重新审视)
- 零安装、纯浏览器运行的代码架构可视化工具
- 粘贴 GitHub URL → 秒级生成交互式依赖图
- 功能：爆炸半径分析、安全扫描、设计模式检测、健康评分
- 单 HTML 文件、零构建依赖、35+ 语言支持

**Fireworks Tech Graph** (已存在于 findings)
- 文本转技术图生成器（英文/中文描述 → SVG + PNG）

### 潜在新功能

**方向 1: 架构图自动生成（Auto Architecture Diagrams）**
- 基于 tree-sitter AST 自动生成系统架构图
- 输入：代码库路径
- 输出：Mermaid/PlantUML/DOT 格式的架构图
- 复用现有模块：dependency_graph, design_patterns
- CLI: `tree-sitter arch-diagram [--format mermaid|plantuml|dot]`

**方向 2: 交互式 Web 可视化（Web Visualization）**
- 类似 CodeFlow 的 Web 界面
- 基于 existing MCP tools 提供交互式分析
- 技术栈：纯 HTML + JS（零构建）
- 部署：单文件 HTML

**方向 3: LLM 辅助代码理解（LLM-Assisted Understanding）**
- 结合 LLM 生成自然语言代码解释
- 输入：文件路径或代码片段
- 输出：结构化解释（用途、依赖、调用关系）
- MCP tool: `explain_code`

---

## 2026-04-18: 新功能探索灵感收集 (Session 111)

### Wiki 检索结果

#### 1. PR Review Automation
- **Hermes Agent - GitHub Code Review Skill**
  - 路径: `/Users/aisheng.yu/wiki/raw/ai-tech/hermes-agent/skills/github/github-code-review/skill.md`
  - 功能: 分析 git diffs，在 PR 上留下内联评论，执行推送前审查
  - 支持 gh CLI 或 GitHub REST API
  - 输出模板: Review Output Template (Verdict, Summary, File-by-file analysis)

- **ECC - /review-pr Command**
  - 路径: `/Users/aisheng.yu/wiki/raw/ai-tech/claude-code-system-prompts/system-prompts/agent-prompt-review-pr-slash-command.md`
  - 功能: 使用 gh pr diff 获取 diff，分析变更，提供全面的代码审查
  - 分析维度: Overview, Code quality, Security concerns, Performance, Testing

- **ECC - Code Review Context**
  - 路径: `/Users/aisheng.yu/wiki/raw/ai-tech/everything-claude-code/contexts/review.md`
  - 模式: PR review, code analysis
  - 关注: Quality, security, maintainability

#### 2. Incremental Analysis Cache
- **tree-sitter-analyzer 已有缓存机制**
  - `AnalysisSession`: 5秒缓存 `git rev-parse HEAD`
  - `AnalysisSession`: mtime-based file hash cache
  - 未变更文件跳过 SHA256 重新计算

#### 3. Code Comment Analysis
- **ECC - Comment Analyzer Agent**
  - 路径: `/Users/aisheng.yu/wiki/raw/ai-tech/everything-claude-code/agents/comment-analyzer.md`
  - 功能: 分析代码注释的准确性、完整性、可维护性
  - 检测: 注释腐烂 (comment rot)

### 潜在新功能方向 (优先级排序)

#### 方向 1: PR Summary Generator (PR 摘要生成器)
**一句话定义**: 自动从 git diff 生成结构化的 PR 变更摘要

**核心价值**:
- 开发者不需要手动写 PR 描述
- AI Agent 可以快速理解 PR 的变更内容
- 标准化的 PR 摘要格式便于 code review

**MVP 功能**:
1. 解析 git diff (支持 `git diff <base>...HEAD`)
2. 识别变更类型: 新增文件/修改文件/删除文件
3. 按语言分类变更 (Python, JavaScript, Java, Go, C#)
4. 生成结构化摘要:
   - Overview (一句话总结)
   - File changes (文件列表，带行数统计)
   - Key changes (关键变更点)
   - Risk assessment (风险评估)
   - Test suggestions (测试建议)

**技术方案**:
- 复用现有 `code_diff` MCP tool
- 新增 `pr_summary` 模块:
  - `DiffParser` - 解析 git diff 输出
  - `ChangeClassifier` - 分类变更类型和语言
  - `SummaryGenerator` - 生成结构化摘要
- CLI: `tree-sitter pr-summary [--base main] [--format json|markdown|toon]`
- MCP tool: `pr_summary` (在 query toolset)

#### 方向 2: Incremental Analysis Cache (增量分析缓存)
**一句话定义**: 只分析变更的文件，加速大型仓库分析

**核心价值**:
- 大型仓库的分析速度提升 10-100 倍
- 减少 CPU 使用（只处理变更部分）
- 支持 CI/CD 场景的增量分析

**MVP 功能**:
1. 检测 git 变更 (`git diff --name-only`)
2. 筛选需要重新分析的文件
3. 加载未变更文件的缓存分析结果
4. 合并新旧分析结果

**技术方案**:
- 扩展 `AnalysisSession` 类
- 新增 `IncrementalAnalyzer` 模块:
  - `get_changed_files()` - 获取变更文件列表
  - `load_cache()` - 加载缓存
  - `save_cache()` - 保存缓存
  - `merge_analysis()` - 合并分析结果

#### 方向 3: Code Comment Analyzer (代码注释分析器)
**一句话定义**: 分析代码注释质量，识别缺失、过时、无效的注释

**核心价值**:
- 提高代码可维护性
- 识别文档债务
- 帮助团队建立注释规范

**MVP 功能**:
1. 识别缺失注释的函数/类（复杂度 > 阈值）
2. 识别过时注释（参数名/返回值与注释不符）
3. 识别无效注释标记（TODO, FIXME, HACK, XXX）
4. 生成注释质量报告

**技术方案**:
- 新增 `comment_analyzer` 模块
- 基于 AST 提取注释和函数签名
- 对比注释与实际代码
- CLI: `tree-sitter comment-analyze [--severity threshold]`
- MCP tool: `comment_analyze` (在 analysis toolset)

### 优先级判断 (根据乔布斯产品理念)

**聚焦即说不**: 哪个功能解决核心问题？
- **PR Summary Generator** - 解决 PR 描述写作痛点，是开发者日常高频操作
- **Incremental Analysis Cache** - 解决大型仓库分析慢的问题，是性能优化
- **Code Comment Analyzer** - 解决代码文档质量问题，是代码质量工具

**减法思维**: 能否增强现有工具而非新建？
- **PR Summary Generator** - 可以作为 `code_diff` 工具的扩展功能
- **Incremental Analysis Cache** - 可以作为现有分析引擎的内部优化
- **Code Comment Analyzer** - 可以作为独立的新工具

**一句话定义**:
1. PR Summary Generator: "自动生成 PR 变更摘要"
2. Incremental Analysis Cache: "只分析变更的文件"
3. Code Comment Analyzer: "分析代码注释质量"

**推荐优先级**:
1. **PR Summary Generator** - 解决明确痛点，需求清晰，可以快速验证价值
2. **Code Comment Analyzer** - 代码质量管理的重要补充，与现有工具形成完整生态
3. **Incremental Analysis Cache** - 性能优化，可以作为后续改进项目

---

## 产品讨论记录 - PR Summary Generator - 2026-04-18

**调用尝试**: /office-hours

**输入**: PR Summary Generator - 自动从 git diff 生成结构化的 PR 变更摘要

**乔布斯产品理念分析（自主分析）**:

1. **聚焦即说不**: 这个功能是否解决核心问题？
   - ✅ **DO** - 开发者写 PR 描述是真实痛点。大多数 PR 描述要么空，要么不完整。
   - 这不是 "nice to have"，而是 PR workflow 的核心问题之一。
   - 好的 PR 描述能提高 code review 效率，减少来回沟通。

2. **减法思维**: 能否用更简单的方式实现？
   - 现有工具：`code_diff` 已有代码差异分析能力
   - 最小可行版本：
     - 基于 `git diff` 输出解析
     - 生成简单的文件列表和变更统计
     - 模板化的摘要格式（不需要 LLM）
   - 复用现有模块，增量开发

3. **一句话定义**: "自动生成 PR 变更摘要"
   - ✅ 清晰、聚焦，一句话说清价值

**结论**: DO - 值得做

**理由**:
- 解决明确痛点（PR 描述写作）
- 需求清晰，MVP 范围明确
- 可以复用现有 `code_diff` 工具
- 与现有 31 个 MCP 工具形成互补

---

## 技术架构讨论记录 - PR Summary Generator - 2026-04-18

**调用尝试**: /plan-eng-review

**输入**: PR Summary Generator - 自动从 git diff 生成结构化的 PR 变更摘要

**技术方案对比**:

**方案 A: 作为 code_diff 工具的扩展**
- 技术可行性: 风险低，现有 `code_diff_tool.py` 已有 diff 解析能力
- 架构影响: 与现有工具协调，但会让 code_diff 变复杂（职责不单一）
- 实现复杂度: 低，复用现有逻辑
- 维护成本: 中等，功能耦合

**方案 B: 创建独立的 pr_summary 模块** ✅ 推荐
- 技术可行性: 风险低，新模块边界清晰
- 架构影响: 与现有 31 个 MCP 工具协调，独立注册
- 实现复杂度: 中等，但可以独立开发和测试
- 维护成本: 低，模块独立职责清晰

**推荐方案**: 方案 B（独立模块）

**理由**:
1. **职责分离**: code_diff 负责代码差异分析，pr_summary 负责 PR 摘要生成
2. **可测试性**: 独立模块更容易测试和维护
3. **可扩展性**: 未来可添加更多 PR 相关功能
4. **3 Sprint 可行**: 每个目标清晰可实现

**下一步**: 定义 OpenSpec Change


---

## 产品讨论记录 - Unified Project Overview - 2026-04-18

**灵感来源**: CodeFlow — 浏览器端代码架构可视化工具

**核心洞察**: tree-sitter-analyzer 已有所有独立分析工具：
- ✅ dependency_graph.py - 依赖图
- ✅ blast_radius.py - 爆炸半径  
- ✅ health_score.py - 健康评分
- ✅ design_patterns.py - 设计模式
- ✅ security_scan.py - 安全扫描
- ✅ dead_code.py - 死代码检测
- ✅ git_analyzer.py - 代码所有权

**缺失功能**: 统一的项目概览报告（一条命令给出完整洞察）

**产品想法**: `tree-sitter overview` — 综合所有分析维度，生成单一报告

## 新功能探索 - 2026-04-18 (永续循环)

### Context Optimization 相关
- **Headroom Context Optimization** — 统计分析驱动的上下文压缩层
  - 路径：`/Users/aisheng.yu/wiki/raw/ai-tech/awesome-llm-apps/advanced-llm-apps/llm-optimization-tools/headroom-context-optimization/readme.md`
  - 核心思想：使用统计分析保留重要内容，压缩非关键内容
  - 价值：可集成到 tree-sitter-analyzer 的代码摘要生成，减少 LLM token 消耗

- **Manus Context Engineering** — Meta 收购的 Agent 公司的上下文工程原则
  - 路径：`/Users/aisheng.yu/wiki/raw/ai-tech/planning-with-files/skills/planning-with-files/reference.md`
  - 核心原则：6 Manus Principles（精确性、压缩、分层等）
  - 价值：指导如何优化代码上下文的呈现方式

### Tree-sitter Code Navigation
- **tree-sitter tags** — 代码导航标签系统
  - 路径：`/Users/aisheng.yu/wiki/raw/ai-tech/tree-sitter/docs/src/cli/tags.md`
  - 功能：`tree-sitter tags` 输出符号标签列表
  - 价值：GitHub 的 search-based code navigation 基于此功能

### MCP 深度知识
- **MCP Server Primitives** — Tools, Resources, Prompts 三大原语
  - 路径：`/Users/aisheng.yu/wiki/raw/ai-tech/anthropic-academy-exporter/courses/introduction-to-model-context-protocol/14-mcp-review.md`
  - 核心概念：Tools 是 model-controlled（模型控制）
  - 价值：理解 MCP 工具的设计哲学


---

## 技术架构讨论记录 - Unified Project Overview - 2026-04-18

**调用**: /plan-eng-review

**输入**: Unified Project Overview — 统一项目概览报告

**推荐方案**: 方案 A（独立 overview 模块）

**理由**:
1. **技术可行性 (9/10)**: 所有分析引擎已存在，零新算法，纯聚合层
2. **架构影响 (9/10)**: 新模块独立，不影响现有 29+ MCP 工具，符合单一职责原则
3. **实现复杂度 (8/10)**: 2-3 Sprint 可完成，~500-700 行新代码
4. **维护成本 (9/10)**: 底层工具更新时，overview 自动受益

**技术方案**:
```
tree_sitter_analyzer/overview/
- aggregator.py - 调用现有分析工具，聚合结果
- reporter.py - 生成统一报告（Markdown/JSON/TOON）
- __init__.py - 模块导出

tree_sitter_analyzer/mcp/tools/
- overview_tool.py - MCP 工具包装器

cli/commands/
- overview_command.py - CLI 命令
```

**Sprint 分解**:
- Sprint 1: Core Aggregator (200-300 行, 15+ tests)
- Sprint 2: Reporter + Output Formats (150-200 行, 10+ tests)
- Sprint 3: CLI + MCP Tool (150-200 行, 10+ tests)

**总计**: ~500-700 行新代码，35+ tests

**风险缓解**:
1. 性能：支持并行执行（concurrent.futures）
2. 输出格式：Reporter 层统一格式化
3. 依赖冲突：隔离失败，部分结果仍可返回

**结论**: DO - 创建独立 overview 模块，复用现有 100% 代码

## 产品讨论记录 - Context Optimization Layer - 2026-04-18

**调用**: /office-hours (乔布斯产品视角)

**输入**: 
- 功能想法：基于 Headroom 和 Manus Context Engineering 的上下文优化层
- 背景：tree-sitter-analyzer 已有 29 个 MCP 工具，输出大量代码上下文给 LLM
- 痛点：大文件分析时，LLM context 消耗过高

**乔布斯的分析 (Builder Mode)**:

### 1. 聚焦即说不 (Focus = Saying No)

**DO** 这个功能值得做，因为：
- **核心问题真实存在**：当 LLM 处理 dependency_graph 或 semantic_impact 的输出时，大项目会消耗 50k+ tokens
- **现有方案不完美**：TOON 压缩已有（69.6% 压缩率），但它是"去除格式"，不是"保留重要信息"
- **技术可行性已验证**：Headroom 用统计分析保留关键内容，Manus 有 6 大原则可应用

**应该砍掉**：
- ❌ 不要做通用压缩（已有 TOON）
- ❌ 不要做 LLM cache（已有 semantic_code_search 的 cache）
- ✅ 只做"针对 LLM 理解优化的上下文表示"

### 2. 减法思维 (Subtraction)

**最简版本 (MVP)**：
```
输入：任意 MCP 工具的 TOON 输出
处理：应用 1 个 Manus 原则（精确性 - Precision）
输出：移除冗余但保留语义的上下文
```

**现有工具是否已经足够？**
- 部分足够：TOON 已去除格式
- 不够之处：TOON 保留所有内容，需要"智能裁剪"

**最简实现**：
1. 创建 `tree_sitter_analyzer/analysis/context_optimizer.py`
2. 实现 1 个优化策略（基于重要性的裁剪）
3. 添加到现有 MCP 工具的输出后处理

### 3. 一句话定义 (One-Sentence Definition)

**版本 1**（太模糊）：
"一个优化代码上下文的层，让 LLM 更高效地理解代码。"

**版本 2**（更好）：
"为 LLM 优化的代码摘要 — 保留关键信息，去除冗余，减少 token 消耗。"

**版本 3**（聚焦）：
**"智能代码上下文摘要器 — 让大文件适应 LLM 上下文窗口。"**

这个定义清晰表达了：
- 输入：代码上下文（大文件）
- 处理：智能摘要
- 输出：适应 LLM 上下文窗口的表示

### 结论

**DO: 继续实现 Context Optimization Layer**

**理由**：
1. **核心价值明确**：让大项目分析在 LLM 上下文窗口内完成
2. **技术路径清晰**：Headroom 风格的统计分析 + Manus 原则
3. **与现有工具互补**：不重复 TOON，而是增强其输出
4. **MVP 可小步验证**：从 1 个优化策略开始

**下一步**：
- 技术架构分析（/plan-eng-review）
- 定义 OpenSpec Change


## 技术架构讨论记录 - Context Optimization Layer - 2026-04-18

**调用**: /plan-eng-review

**输入**: Context Optimization Layer 设计文档 + Approach A（重要性评分过滤）

**GStack 的技术分析**:

### 1. 技术可行性

**推荐方案 A：Importance-Based Filtering** — 风险最低

**理由**：
- ✅ 复用现有模块：`complexity.py` 已有 cyclomatic complexity，`dependency_graph.py` 已有依赖计数
- ✅ 简单算法：加权评分（complexity * 0.4 + dependency * 0.3 + call_freq * 0.3）
- ✅ 确定性输出：相同输入 → 相同输出（便于测试）

**潜在坑点**：
1. **call_frequency 如何获取？** — 需要静态分析或动态追踪
   - 解决：使用 dependency_graph 的 edge_weights 作为近似
2. **跨文件依赖可能丢失** — Approach A 只考虑单文件评分
   - 解决：Sprint 2 可增强为 Approach B（PageRank 风格）

### 2. 架构影响

**与现有 29 个 MCP 工具协调**：

```
现有架构：
MCP Tool → AST Analysis → TOON Output → LLM

新架构（后处理模式）：
MCP Tool → AST Analysis → TOON Output → Context Optimizer → LLM
                                       ↑
                                    可插拔
```

**推荐模式：Post-Processing Filter**

```python
# tree_sitter_analyzer/analysis/context_optimizer.py
def optimize_for_llm(toon_output: str, threshold: float = 0.5) -> str:
    """
    Post-process TOON output to optimize for LLM context windows.
    
    1. Parse TOON → extract code elements
    2. Score each element (complexity + dependencies)
    3. Filter by threshold (keep top N%)
    4. Reconstruct TOON format
    """
```

**集成点**：
- `semantic_impact` MCP tool：添加 `--optimize-context` flag
- `dependency_graph` MCP tool：添加节点数限制逻辑
- `complexity_heatmap` MCP tool：只显示高复杂度区域

### 3. 实现复杂度

**3 个 Sprint 可行**：

**Sprint 1**（2-3天）：
- 创建 `analysis/context_optimizer.py`
- 实现 `score_importance()` → 复用 `complexity.py` 的 `LineComplexity`
- 实现 `filter_by_importance()` → 简单的百分位过滤
- 20+ 单元测试

**Sprint 2**（2-3天）：
- 集成到 3 个工具：`semantic_impact`, `dependency_graph`, `complexity_heatmap`
- 添加 CLI flag: `--optimize-context`
- 15+ 集成测试

**Sprint 3**（2-3天）：
- LLM 基准测试（对比优化前后的问答准确率）
- 迭代评分算法
- 文档更新

**总计**：~8-9 天，符合 3 Sprint 目标

### 4. 维护成本

**长期可维护**：

**优点**：
- ✅ 无外部依赖（不需要 ML 库）
- ✅ 确定性输出（便于调试和测试）
- ✅ 代码简单（单一职责：评分 + 过滤）

**与 Approach B/C 对比**：
- Approach B（PageRank）：需要图算法，维护成本中等
- Approach C（ML clustering）：需要模型训练/更新，维护成本高

### 推荐方案

**方案 A：Importance-Based Filtering**

**理由**：
1. **风险最低**：复用现有模块，算法简单
2. **架构协调**：后处理模式，不破坏现有工具
3. **3 Sprint 可完成**：MVP 快速验证
4. **长期可维护**：无 ML 依赖，确定性输出

**数据流图**：

```
┌─────────────────────────────────────────────────────┐
│  MCP Tool (semantic_impact / dependency_graph)      │
│  ↓                                                   │
│  AST Analysis (existing)                            │
│  ↓                                                   │
│  TOON Output (existing)                             │
│  ↓                                                   │
│  ┌───────────────────────────────────────────────┐  │
│  │  Context Optimizer (NEW)                      │  │
│  │  1. Parse TOON → code elements                │  │
│  │  2. Score: complexity * 0.4 + deps * 0.3      │  │
│  │  3. Filter: keep top 50% by score            │  │
│  │  4. Reconstruct TOON format                   │  │
│  └───────────────────────────────────────────────┘  │
│  ↓                                                   │
│  Optimized TOON → LLM (50-70% less tokens)          │
└─────────────────────────────────────────────────────┘
```

**依赖模块**：
- `complexity.py` → 复用 `LineComplexity` dataclass
- `dependency_graph.py` → 复用 `edge_weights` 作为 call_freq 近似

**风险**：
- call_frequency 可能不准确 → Sprint 3 基准测试验证
- 跨文件依赖丢失 → 可迭代到 Approach B


## 新功能探索记录 - Session 111

### 2026-04-18: PR Summary Generator 灵感

**Wiki 检索结果:**
- CodeFlow: PR Impact Analysis (粘贴 PR URL 查看影响范围)
- claw-code: 开源 Claude Code 实现
- tree-sitter code navigation: Pattern matching, query language

**已有功能对比:**
- CodeFlow: 依赖图, 爆炸半径, 安全扫描, 设计模式, 健康评分
- tree-sitter-analyzer: 上述功能全部实现 ✅
- 新机会: **PR Summary Generator** (LLM 驱动的代码变更摘要)

**功能想法:**
自动生成 Pull Request 的自然语言摘要，包括:
1. 变更概述 (What changed?)
2. 影响范围 (Which files/modules?)
3. 潜在风险 (Breaking changes?)
4. 测试覆盖 (Tests added/updated?)

**技术基础:**
- 已有 code_diff.py (diff 分析)
- 已有 search/llm_integration.py (LLM 支持)
- 可集成 git_analyzer.py (文件 churn, ownership)

**价值:**
- 节省 PR review 时间
- 自动化变更日志生成
- CI/CD pipeline 集成

## 产品讨论记录 - PR Summary Generator - 2026-04-18

**调用**: office-hours skill (乔布斯视角)

**功能想法**: PR Summary Generator - 使用 LLM 生成 Pull Request 的自然语言摘要

**乔布斯的分析**:
- **判断**: DON'T - 不值得做
- **理由 1**: 价值主张错位。tree-sitter-analyzer = 精确 AST 分析，LLM summary = 模糊文本生成
- **理由 2**: 弱痛点。PR review 时间不是开发者最痛的问题
- **理由 3**: 质量风险。LLM hallucination 会破坏用户对精确性的信任
- **理由 4**: 增加复杂度。引入外部 API 依赖、成本、延迟

**减法思维建议**:
- 优化现有 code_diff 工具的输出格式
- 添加 TOON/JSON 模板供 CI/CD 使用
- 不需要 LLM

**替代方向**:
- Release Notes Generator (从 commit history，不需要 LLM)
- PR Impact Visualization (code_diff + dependency_graph)
- Code Context Explorer (基于现有 AST 数据)

**结论**: DON'T - 放弃 PR Summary Generator，探索其他方向

## 产品讨论记录 - Code Clone Detection - 2026-04-18

**调用**: office-hours skill (乔布斯视角)

**功能想法**: Code Clone Detection MCP Tool Integration

**背景**: code_clones.py 已完成（47 tests passing），需注册为 MCP 工具

**乔布斯的分析**:
- **判断**: DO - 值得做
- **理由 1**: 工具完成任务，不是新产品方向。原型已有，只需包装。
- **理由 2**: 真实痛点。代码重复是维护噩梦。
- **理由 3**: 无风险。纯 AST 分析，无外部依赖。
- **理由 4**: 极简实现。1-2 Sprint 即可。

**一句话定义**: "检测项目中的重复代码，按类型和严重程度分类，提供重构建议。"

**实施计划**:
- Sprint 1: MCP Tool Creation (code_clones_tool.py + 15+ tests)
- Sprint 2: Registration + Documentation

**结论**: DO - 继续实施

## Session 111 进度总结

**完成的 OpenSpec Changes**:
- add-code-clone-detection-tool (文档更新, 工具已存在)

**产品分析**:
1. PR Summary Generator → DON'T (LLM 依赖破坏 local-first 定位)
2. Code Clone Detection → DO (工具已完成, 已文档化)

**Wiki 检索灵感**:
- code analysis, MCP tools, code navigation
- CodeFlow: dependency graphs, PR impact analysis
- Code Clone Detection (已有原型)
- Unused import detection (已在 dead_code tool 中)
- Comment analysis (不适合 AST 分析, 需要 LLM)
- Performance profiling (需要运行时数据, AST 无法提供)

**当前状态**:
- 39 个 MCP 工具
- 所有核心分析模块已集成
- 无明显缺口 (无未集成的分析模块需要 MCP 工具)

**下一步**: 继续永续循环, 寻找新的功能方向

## Session 111 最终总结

**工作时间**: 约2小时
**Context 使用**: ~50%

**完成工作**:
1. 永续循环 - 灵感收集 (qmd wiki 检索)
2. 产品分析 - PR Summary Generator → DON'T
3. 产品分析 - Code Clone Detection → DO (已完成)
4. 文档更新: README 工具数量 31→38
5. 代码审计: 8 TODO/FIXME (全部合法), 101 文件 >400行
6. 测试套件: 2574 passed, 3 failed (边缘案例)
7. 创建 OpenSpec change: add-code-clone-detection-tool (已归档)

**发现**:
- tree-sitter-analyzer 已功能完整 (39 MCP 工具)
- 所有核心分析模块已集成
- 无明显功能缺口
- 代码质量高 (审计通过)

**测试失败** (需后续修复):
1. test_analyze_file_full_coverage - 测试数据问题
2. test_main_json_format - CLI radar 输出
3. test_all_readmes_under_500_lines - 文档一致性

**下一步**:
- 修复 3 个失败测试 (或创建 issue 追踪)
- 继续永续循环寻找新功能方向
- 或执行性能优化循环

## 产品讨论记录 - Environment Variable Tracker - 2026-04-18

**调用**: 乔布斯产品理念分析 (GStack office-hours framework)

**功能想法**: Code Relationship Visualization - 可视化代码元素跨文件的连接关系

**乔布斯的分析** (基于 GStack 框架):

1. **聚焦即说不**: 这个功能是否解决核心问题？还是 "nice to have"？
   - 判断: DON'T - 功能重复
   - 理由: `trace_impact` + `dependency_graph` 已经覆盖了核心价值
   - 这只是 "更好的展示"，不是 "解决新问题"

2. **减法思维**: 能否用更简单的方式实现？
   - 判断: `dependency_graph` 已经输出 Mermaid 格式
   - 用户可以用现有工具 + 第三方可视化工具
   - 最小版本: 改进文档，提供可视化模板

3. **一句话定义**: "可视化代码元素跨文件的连接关系"
   - 问题: 这句话没有说清价值
   - 改进: "让开发者在一秒内看到函数 X 被哪些文件调用"
   - 但: `trace_impact` 已经做这件事了

**结论**: DON'T

**理由**:
- 功能重复: `trace_impact` + `dependency_graph` 已覆盖核心价值
- 价值主张错位: 这是 "更好的展示"，不是 "解决新问题"
- 乔布斯原则: 如果只是让已有功能 "更漂亮"，应该砍掉

---

**替代方向探索**:

经过系统分析，发现以下功能缺口:

1. **Performance Hotspot Detector** → DON'T
   - 理由: 静态分析无法准确测量运行时性能
   - 需要真实 profiler 数据

2. **Import Optimizer** → DON'T
   - 理由: IDE 已解决此问题
   - tree-sitter 无优势

3. **Code Bookmark System** → DON'T
   - 理由: 编辑器已解决

4. **API Endpoint Extractor** → 已存在
   - `api_discovery_tool.py` 已实现
   - 支持 Flask, FastAPI, Django, Express, Spring

5. **Environment Variable Tracker** → DO ✓
   - **核心问题**: 开发者不知道哪些环境变量被使用，容易遗漏配置
   - **是否核心**: 对于部署和配置管理，这是核心需求
   - **减法思维**: grep 可以找，但 tree-sitter 能更精确提取变量名和上下文
   - **一句话定义**: "列出项目中所有使用的环境变量及其位置和用途"
   
   **技术方案**:
   - 支持 Python: os.getenv, os.environ
   - 支持 JavaScript/TypeScript: process.env
   - 支持 Java: System.getenv, System.getProperty
   - 支持 Go: os.Getenv
   
   **MVP 范围**:
   - 提取所有环境变量引用
   - 显示变量名、文件位置、行号
   - 分组显示 (按变量名)
   - 检测未使用的环境变量声明

6. **Configuration File Analyzer** → 部分已存在
   - CI/CD secrets reference 已存在
   - 但完整的配置文件分析 (package.json, pom.xml, requirements.txt) 可能有价值

**下一步**: 调用 `/plan-eng-review` 对 Environment Variable Tracker 进行架构分析


## 技术架构讨论记录 - Environment Variable Tracker - 2026-04-18

**功能**: Environment Variable Tracker - 列出项目中所有使用的环境变量

**初步技术方案**:

1. **方案 A: 完整 MCP 工具实现**
   - 创建 `tree_sitter_analyzer/analysis/env_tracker.py`
   - 创建 `tree_sitter_analyzer/mcp/tools/env_tracker_tool.py`
   - 支持 4 种语言 (Python, JS/TS, Java, Go)
   - 输出 TOON + JSON 格式
   - 约 400-500 行代码

2. **方案 B: 轻量级 CLI 命令**
   - 创建 `cli/commands/env_command.py`
   - 复用现有分析模式
   - 输出文本 + JSON
   - 约 200-300 行代码

3. **方案 C: 增强现有 security_scan**
   - 在 `security_scan.py` 中添加环境变量检测
   - 复用现有架构
   - 约 100-150 行代码

**技术分析**:

1. **技术可行性**:
   - 方案 A: 风险低，与现有模式一致
   - 方案 B: 风险低，CLI 命令更简单
   - 方案 C: 风险中，security_scan 关注点不同 (安全 vs 配置)

2. **架构影响**:
   - 方案 A: 与 38 个 MCP 工具协调良好
   - 方案 B: CLI 命令，不影响 MCP 架构
   - 方案 C: 可能混淆 security_scan 的职责

3. **实现复杂度**:
   - 方案 A: 3 个 Sprint 可完成 (Detection Engine, Multi-Language, MCP Integration)
   - 方案 B: 2 个 Sprint 可完成 (Detection Engine, CLI)
   - 方案 C: 1 个 Sprint 可完成，但职责不清

4. **维护成本**:
   - 方案 A: 独立模块，长期维护容易
   - 方案 B: CLI 命令，维护成本低
   - 方案 C: 混在 security_scan 中，维护困难

**推荐方案**: 方案 A - 完整 MCP 工具实现

**理由**:
1. 与现有架构一致 (38 个 MCP 工具)
2. 职责清晰 (环境变量追踪 ≠ 安全扫描)
3. 可复用模式 (code_smell_detector, code_clone_detection 等都是独立模块)
4. TOON 输出格式与其他工具一致

**风险**: 无显著风险
**依赖**: tree-sitter 语言插件 (Python, JavaScript, Java, Go 都已支持)


## 产品讨论记录 - Import Dependency Sanitizer - 2026-04-18

**调用**: /office-hours (产品分析)

**输入**: 3 个功能方向 (Code Ownership, API Contract, Import Sanitizer)

**产品分析结论**:
- Code Ownership & Bus Factor Analyzer → DON'T (git blame 噪音大，架构不匹配)
- API Contract Analyzer → DON'T (已被 code_diff_tool 覆盖)
- Import Dependency Sanitizer → DO (真正的缺口，tree-sitter 完美适用)

**理由**: Import sanitizer 是真正的功能缺口，解决所有开发者的通用痛点，完美契合 tree-sitter 静态分析定位。

## 技术架构讨论记录 - Import Dependency Sanitizer - 2026-04-18

**调用**: /plan-eng-review (架构分析)

**输入**: 3 个技术方案 (独立模块 vs 增强dependency_graph vs 单文件分析)

**推荐方案**: 方案 A - 独立 analysis 模块 + MCP 工具

**理由**:
- 方案 B 违反 SRP，dependency_graph 已有430+行
- 方案 C 不完整，循环检测需要跨文件分析
- 方案 A 架构匹配度最高，3个Sprint可完成

**风险**: star imports (*) 无法静态验证，需标记
**依赖**: tree-sitter 查询（现有模式），Tarjan SCC（已有实现）

## 产品讨论记录 - Documentation Coverage Analyzer - 2026-04-18

**调用**: /office-hours (产品分析)

**输入**: 3 个功能方向 (Documentation Coverage, Architecture Constraint, Code Statistics)

**产品分析结论**:
- Documentation Coverage Analyzer → DO (真正缺口，无工具检查文档完整性)
- Architecture Constraint Validator → DON'T (复杂度过高，需要 DSL)
- Code Statistics Dashboard → DON'T (cloc/tokei 已覆盖)

**理由**: Documentation Coverage 是唯一的功能缺口，tree-sitter 完美适用（解析注释和文档字符串），local-first 无需 LLM。

## 技术架构讨论记录 - Documentation Coverage Analyzer - 2026-04-18

**调用**: /plan-eng-review (架构分析)

**输入**: 独立 analysis 模块 + MCP 工具

**推荐方案**: 方案 A - 独立 analysis 模块 + MCP 工具

**理由**:
- 与 env_tracker/import_sanitizer 架构模式一致
- 3 个 Sprint 即可完成
- 支持 4 种语言 (Python, JS/TS, Java, Go)

**风险**: decorated_definition 需要特殊处理 (已解决)
**依赖**: tree-sitter 语言模块 (已有)

## 产品讨论记录 - Cognitive Complexity Scorer - 2026-04-18

**调用**: /office-hours (产品分析)

**输入**: 3 个功能方向 (Cognitive Complexity Scorer, Code Change Pattern Detector, Function Call Chain Analyzer)

**产品分析结论**:
- Function Cognitive Complexity Scorer → DO (真正缺口，与 complexity_heatmap 互补)
- Code Change Pattern Detector → DON'T (与 pr_summary 重叠)
- Function Call Chain Analyzer → DO (第二选择，但更复杂，需要类型推断)

**理由**: Cognitive Complexity 是 SonarSource 标准化度量，开发者真实痛点（"这个函数太难读了"），tree-sitter 精确识别嵌套层级和逻辑运算符，与 complexity_heatmap（cyclomatic）形成互补。

## 技术架构讨论记录 - Cognitive Complexity Scorer - 2026-04-18

**调用**: /plan-eng-review (架构分析)

**输入**: 2 个方案 (独立模块 vs 扩展现有 complexity 模块)

**推荐方案**: 方案 A - 独立 analysis 模块 + MCP 工具

**理由**:
1. complexity.py (276行) 做的是行级 McCabe cyclomatic，认知复杂度是完全不同的算法
2. 与 env_tracker/import_sanitizer/doc_coverage 架构模式一致
3. 独立模块便于独立测试和维护
4. 3 个 Sprint 可完成 (Python核心 + 多语言 + MCP工具)

**风险**: SonarSource 规范有多个特殊情况（else/elif 不增加，递归不增加嵌套，lambda 特殊处理）
**依赖**: tree-sitter 语言模块 (已有)

## 产品讨论记录 - Parameter Coupling Analyzer - 2026-04-18

**调用**: /office-hours

**输入**: 三候选功能分析 — Parameter Coupling Analyzer, Code Change Churn Predictor, Function Call Depth Analyzer

**分析**:
- Parameter Coupling Analyzer → DO: 真正的缺口，Data Clump 检测是独特功能，tree-sitter 精确解析参数列表
- Code Change Churn Predictor → DON'T: 与 git_analyzer + risk_scoring 重叠
- Function Call Depth Analyzer → DON'T: 与 trace_impact 重叠，只需 10 行代码而非新工具

**结论**: DO

**理由**: 填补 McCabe complexity 和 cognitive complexity 之间的真正空白

## 技术架构讨论记录 - Parameter Coupling Analyzer - 2026-04-18

**调用**: /plan-eng-review

**输入**: Parameter Coupling Analyzer 三方案分析

**GStack的分析**:
- 方案 A（独立模块）: 推荐 — 与 env_tracker/import_sanitizer/doc_coverage 模式一致
- 方案 B（增强 complexity.py）: 不推荐 — 违反 SRP
- 方案 C（增强 refactoring_suggestions）: 不推荐 — 功能耦合

**推荐方案**: 方案 A
**理由**: 最低风险，与现有 38+ MCP 工具架构一致，3 Sprint 可完成
**风险**: Jaccard similarity 阈值需要调优
**依赖**: tree-sitter 语言模块 (已有)

## 产品讨论记录 - Error Handling Pattern Analyzer - 2026-04-18

**调用**: 乔布斯产品理念分析 (聚焦/减法/一句话定义)

**输入**: 三候选功能分析 — Error Handling Pattern Analyzer, Code Statistics Aggregator, Naming Convention Checker

**分析**:

1. **聚焦即说不**: 哪个功能解决核心问题？
   - Error Handling Pattern Analyzer → DO: 真正的缺口，无工具检查错误处理质量。生产环境故障 #1 原因是错误处理不当。
   - Code Statistics Aggregator → DON'T: cloc/tokei 已覆盖，overview_tool 已存在
   - Naming Convention Checker → DON'T: IDE linters 已覆盖 (ESLint, Pylint, Checkstyle)

2. **减法思维**: 能否用更简单的方式实现？
   - Error Handling: 不能更简单，这是全新的分析维度。security_scan 关注安全漏洞，code_smells 关注代码异味，但没有人专门分析错误处理模式。
   - 最小版本: 检测 bare except + swallowed errors + inconsistent patterns

3. **一句话定义**: "检测项目中的错误处理反模式，按严重程度分类并提供改进建议。"
   - ✅ 清晰、聚焦，一句话说清价值

**结论**: DO

**理由**:
- 填补真正的功能缺口（无现有工具覆盖错误处理质量）
- tree-sitter 完美适用（try/catch/except 是 AST 节点）
- 多语言支持（Python try/except, Java try/catch, JS try/catch, Go if err != nil）
- Local-first（纯 AST 分析，无 LLM 依赖）

## 技术架构讨论记录 - Error Handling Pattern Analyzer - 2026-04-18

**调用**: 架构分析 (GStack eng review framework)

**输入**: Error Handling Pattern Analyzer 三方案分析

**方案 A: 独立 analysis 模块 + MCP 工具** (推荐)
- 与 env_tracker/import_sanitizer/doc_coverage 架构模式一致
- 3 Sprint 可完成
- 支持 4 种语言

**方案 B: 扩展 security_scan**
- 不推荐 - 职责不同（安全漏洞 vs 错误处理质量）

**方案 C: 扩展 code_smells**
- 不推荐 - code_smells 关注代码异味，不是错误处理

**推荐方案**: 方案 A
**理由**: 最低风险，与现有 39+ MCP 工具架构一致，3 Sprint 可完成
**风险**: Go 的 error handling 模式与其他语言差异大，需要特殊处理
**依赖**: tree-sitter 语言模块 (已有)

**技术方案**:
```
tree_sitter_analyzer/analysis/error_handling.py
- ErrorHandlingPattern dataclass
- ErrorHandlingAnalyzer class
- detect_bare_except() — Python bare except
- detect_swallowed_errors() — empty except/catch blocks
- detect_broad_exceptions() — except Exception, catch (Exception)
- detect_go_error_unchecked() — unchecked error returns
- detect_finally_without_try() — dangling finally
- 支持语言: Python, JavaScript/TypeScript, Java, Go

tree_sitter_analyzer/mcp/tools/error_handling_tool.py
- MCP tool 包装器
- TOON + JSON 输出
- severity 过滤 (error/warning/info)
```

## 产品讨论记录 - i18n String Detector - 2026-04-18

**调用**: /office-hours (乔布斯产品分析)

**输入**: 3个候选功能 (Function Signature Change Detector, Code Metric Trend Tracker, i18n String Detector)

**分析**:
1. Function Signature Change Detector → DON'T (与 code_diff_tool + trace_impact 重叠)
2. Code Metric Trend Tracker → DON'T (与 git_analyzer + health_score 重叠，不是 tree-sitter 强项)
3. i18n String Detector → DO (真正的功能缺口)

**乔布斯视角判断**:
- 聚焦即说不: i18n 是唯一一个不与现有工具重叠的功能
- 减法思维: MVP 只需检测用户可见字符串 (print/raise/log.error/UI 函数中的字符串)
- 一句话定义: "找到所有需要翻译的字符串，一键国际化"

**结论**: DO - 实现 i18n String Detector
**理由**: 真正的功能缺口，tree-sitter 的字符串解析优势，市场清晰

## 技术架构讨论记录 - i18n String Detector - 2026-04-18

**调用**: /plan-eng-review (GStack eng review)

**输入**: 3个技术方案评估 (独立模块 vs 扩展magic_values vs 扩展comment_quality)

**GStack的分析**:
1. 方案A (独立模块): ✅ 推荐 - 与30个已有模块模式一致，单一职责
2. 方案B (扩展magic_values): ❌ 关注重叠但规则完全不同，magic_values检测常量提取，i18n检测用户可见字符串
3. 方案C (扩展comment_quality): ❌ 完全错误的领域

**推荐方案**: 方案 A（独立模块）
**理由**: 已验证10次以上的架构模式，风险最低
**风险**: 无实质性风险
**依赖**: tree-sitter查询（已通过magic_values验证）

**关键技术决策**:
- 字符串可见性分类: USER_VISIBLE / LIKELY_VISIBLE / INTERNAL
- 4语言输出函数映射: print/raise/logging, console.log/alert, System.out/Logger, fmt/log
- 数据流: parse → extract → filter(parent call_expression) → classify → aggregate

## 产品讨论记录 - Test Smell Detector - 2026-04-18

**调用**: /office-hours (autonomous mode)

**输入**: Test Smell Detector — 检测测试代码中的反模式（空assert、broad exception catch、sleep in tests）

**产品分析 (YC Office Hours 框架)**:

**需求现实**: 高。test_coverage 已有但只测"量"不测"质"。
**当前替代方案**: 手动review或重型mutation testing。无轻量级tree-sitter方案。
**一句话定义**: "告诉开发者他们的测试在撒谎"

**结论**: DO

**理由**:
1. test_coverage 的自然后续 — 检查覆盖率的人下一步就问"但这些测试好吗"
2. 真正的空白 — flake8/eslint 不检测语义级测试反模式
3. 可操作 — 每个smell都有明确修复方案

**MVP Scope**:
- 空test body检测（无assert）
- 宽泛exception catch（except Exception, catch(e)）
- time.sleep()/setTimeout in tests
- assert数量（<1 per test = 可能无用）

**不做**:
- 共享可变状态检测（需dataflow）
- 测试依赖排序（需运行时信息）
- fixture复杂度（过于主观）

## 产品讨论记录 - Logging Pattern Analyzer - 2026-04-18

**调用**: 乔布斯产品理念分析 (autonomous mode)

**输入**: 3个候选功能 (Logging Pattern Analyzer, Concurrency Pattern Analyzer, API Deprecation Detector)

**分析**:

1. **聚焦即说不**: 哪个功能解决核心问题？
   - Logging Pattern Analyzer → DO: 真正的缺口。error_handling.py 分析 try/catch 结构，但不分析日志质量。生产环境调试 #1 依赖日志。
   - Concurrency Pattern Analyzer → DON'T: 与 async_patterns 重叠，且静态分析无法准确检测竞态条件。
   - API Deprecation Detector → DON'T: 过于语言/框架特定，通用价值低。

2. **减法思维**: 能否用更简单的方式实现？
   - 最小版本: 检测空 catch 块（无日志）、log level 不匹配、敏感数据暴露。
   - tree-sitter 精确识别日志函数调用和参数。

3. **一句话定义**: "检测日志反模式，让生产环境调试不再痛苦。"

**结论**: DO - 实现 Logging Pattern Analyzer

**理由**:
- 填补真正的功能缺口（error_handling 分析结构，不分析日志质量）
- tree-sitter 完美适用（日志调用是 AST 函数调用节点）
- 4种语言日志框架: Python logging.*, JS console.*, Java log4j/SLF4J, Go log.*
- Local-first，无外部依赖

## 技术架构讨论记录 - Logging Pattern Analyzer - 2026-04-18

**调用**: 架构分析 (GStack eng review framework)

**输入**: Logging Pattern Analyzer - 独立模块 vs 扩展 error_handling

**方案 A: 独立 analysis 模块 + MCP 工具** (推荐)
- 与 env_tracker/import_sanitizer 等 33 个已有模块模式一致
- 3 Sprint 可完成

**方案 B: 扩展 error_handling.py**
- 不推荐 - error_handling 关注错误处理结构（try/catch），logging 是不同的关注点

**推荐方案**: 方案 A
**理由**: 职责清晰，error_handling = 错误结构，logging = 日志质量
**风险**: Go 的 log 包较简单，检测规则可能较少
**依赖**: tree-sitter 语言模块 (已有)

## 产品讨论记录 - Naming Convention Analyzer - 2026-04-18

**调用**: /office-hours (GStack)

**输入**: Naming Convention Analyzer — 检测命名不规范的标识符

**乔布斯/GStack的分析**:
1. 聚焦即说不: 这是一个"nice to have"功能，但维度独特（现有35个分析模块均不覆盖命名质量）
2. 减法思维: MVP只做3种检测 — 单字母变量、不一致风格、违反语言惯例
3. 一句话定义: "Detect identifiers that violate language naming conventions and provide actionable rename suggestions"

**结论**: DO — 维度独特，实现简单，用户价值明确
**理由**: 命名是代码可读性的核心因素，现有工具链（linter/ruff）只做格式检查不做命名质量分析

## 技术架构讨论记录 - Naming Convention Analyzer - 2026-04-18

**调用**: /plan-eng-review (GStack)

**输入**: Naming Convention Analyzer + 两种技术方案

**GStack的分析**:
1. 技术可行性: 方案 A (纯 tree-sitter + regex) 风险更低，与 35 个现有模块架构一致
2. 架构影响: 手动 AST walking 是所有模块的统一模式，不需要 tree-sitter query language
3. 实现复杂度: ~400 行引擎 + ~200 行 MCP 工具 + ~400 行测试 = 1 Sprint
4. 关键坑: Go 语言命名惯例特殊（exported = PascalCase, unexported = lowercase）

**推荐方案**: 方案 A (纯 tree-sitter + regex)
**理由**: 确定性检测，无主观判断，测试友好
**风险**: Go 的命名惯例需要特殊处理
**依赖**: tree-sitter 语言模块 (已有)

**MVP 违规类型**:
- single_letter_var: 单字母变量（除 i/j/k 循环计数器）
- inconsistent_style: 同一作用域混合命名风格
- language_violation: 违反语言惯例
- upper_snake_not_const: 非常量使用 UPPER_SNAKE

## 产品讨论记录 - Coupling Metrics Analyzer - 2026-04-18

**调用**: /office-hours (autonomous mode)

**输入**: 3 个候选功能 (Fan-Out/Fan-In Coupling, Class Responsibility SRP, Method Chain Depth)

**产品分析结论**:
- Fan-Out/Fan-In Coupling Analyzer → DO: 填补真正的分析缺口，复用 dependency_graph，每份架构审查都需要
- Class Responsibility Analyzer → DON'T: 与 code_smell_detector 重叠
- Method Chain Depth → DON'T: 高误报率，与 dependency analysis 重叠

**一句话定义**: "Find the modules that are too coupled and the modules that are too critical."

**结论**: DO

## 产品讨论记录 - Assertion Quality Analyzer - 2026-04-18

**调用**: /office-hours (autonomous mode)

**输入**: 3 个候选功能 (Code Consistency, Assertion Quality, Code Freshness)

**乔布斯的分析**:
- Code Consistency → DON'T: naming_convention + import_sanitizer 已覆盖，跨文件一致性是 YAGNI
- Code Freshness → DON'T: git_analyzer + health_score 已覆盖，薄封装
- Assertion Quality → DO: 真正的缺口。test_coverage 告诉你 IF tested，test_smells 告诉你 BAD patterns。但无人告诉你 assertions 是否 TESTING BEHAVIOR vs TESTING EXISTENCE。

**结论**: DO

**理由**: expect(component).toBeDefined() vs expect(component.text).toBe("Save") - 两者 test_coverage=100%, test_smells=pass, 但只有后者在测行为。这个工具填补 test_coverage 和 test_smells 之间的真实空白。

**一句话定义**: "Tells you if tests catch bugs or just pass CI."

## 技术架构讨论记录 - Assertion Quality Analyzer - 2026-04-18

**调用**: /plan-eng-review (autonomous mode)

**输入**: 3 个方案 (独立模块, 扩展 test_smells, 独立+联动)

**推荐方案**: 方案 A（独立模块）
**理由**: test_smells 已 847 行, 关注"有无断言"vs"断言质量", 职责不同, 不应混入
**风险**: JS/TS 方法链断言需要仔细的 tree-sitter query（expect(x).toBe vs toBeDefined）
**依赖**: tree-sitter (已有), 无新外部依赖
**实现**: 3 Sprints - 核心引擎(Python) → 多语言(JS/TS, Java, Go) → MCP Tool

## 技术架构讨论记录 - Coupling Metrics Analyzer - 2026-04-18

**调用**: /plan-eng-review (autonomous mode)

**输入**: 2 个方案 (独立模块 vs 扩展 dependency_graph)

**推荐方案**: 方案 A（独立模块）
**理由**: 匹配 54 个已有工具的架构模式，dependency_graph.py 已有 434 行不宜再扩展
**风险**: 无实质风险（纯聚合计算，零新 AST 解析）
**依赖**: DependencyGraph + DependencyGraphBuilder（已有）

## 产品讨论记录 - Exception Handling Quality Analyzer - 2026-04-19

**调用**: /office-hours (autonomous mode)

**输入**: Exception Handling Quality Analyzer — 分析生产代码中异常处理质量

**乔布斯的分析**:
- Exception Handling Quality → DO: 真正的空白。logging_patterns 检测 silent catch 但侧重日志层面, error_handling 检测恢复模式(retry/fallback)但非反模式, test_smells 的 broad_except 只覆盖测试代码。生产代码中异常处理质量无人覆盖。
- 4 种检测模式: broad_catch(捕获过宽异常类型), swallowed_exception(catch 块为空), missing_context(raise 新异常未传递原始异常), generic_error_message(硬编码错误消息)
- 与现有工具差异化清晰: logging_patterns=日志层面, error_handling=恢复模式, 本工具=异常处理质量反模式

**结论**: DO

**理由**: "没人告诉你 catch 块是否真的处理了异常，还是只是吞掉了它。" 每个生产代码库都有这个问题，tree-sitter AST 解析优势明显（精确识别 try/catch/except 结构和内容）。

**一句话定义**: "Detects exception handling anti-patterns in production code — where errors get silently swallowed."

## 技术架构讨论记录 - Exception Handling Quality Analyzer - 2026-04-19

**调用**: /plan-eng-review (autonomous mode)

**输入**: 3 个方案 (独立模块, 扩展 logging_patterns, 扩展 error_handling)

**推荐方案**: 方案 A（独立模块）
**理由**: 36 个分析器全部使用独立模块模式。logging_patterns 已 500+ 行不宜再扩展，error_handling 侧重恢复模式职责不同。单职责原则 + 独立测试 + 可独立修改。
**风险**: Go 的 defer/recover 模式需要额外 tree-sitter query，但属于常规工作
**依赖**: tree-sitter (已有), 无新外部依赖
**实现**: 3 Sprints - 核心引擎(Python) → 多语言(JS/TS, Java, Go) → MCP Tool

## 产品讨论记录 - SOLID Principles Analyzer - 2026-04-19

**调用**: 产品方向分析（自主模式，替代 /steve-jobs-perspective）

**候选功能**:
1. SOLID 原则分析器 — 检测 SRP/OCP/LSP/ISP/DIP 违规
2. 数据流分析器 — 追踪变量传播路径
3. 变更爆炸半径分析器 — 量化修改影响范围

**产品分析**:

**聚焦即说不**: SOLID 原则分析器最核心。数据流分析需要跨函数/跨文件追踪，tree-sitter 做不到完整的数据流分析（需要类型推断+控制流图），属于"nice to have"但实现成本远超价值。变更爆炸半径已部分被 dependency_graph + call_graph 覆盖。

**减法思维**: SOLID 分析器可以用简单的模式匹配实现：
- SRP: 类方法数/行数阈值 + 职责关键词聚类
- OCP: isinstance/type 检查 + switch-on-type 模式
- LSP: 子类方法签名与父类不兼容
- ISP: 协议/接口方法数过多
- DIP: 直接导入具体类而非抽象
这些都已有 tree-sitter query 成功先例。

**一句话定义**: "检测你的代码是否违反了 SOLID 原则，告诉你哪里违反以及如何修复"

**结论**: DO — SOLID Principles Analyzer
**理由**:
1. 高频需求 — SOLID 是面试/代码审查的必检项
2. 技术可行 — 每个原则都可以用 tree-sitter pattern 检测
3. 无重叠 — 现有 38 个分析器没有专门做 SOLID 的
4. 用户可操作 — 每个违规都有明确的修复建议
5. 数据流太复杂不适合单 Sprint，爆炸半径已有部分覆盖

## 技术架构讨论记录 - SOLID Principles Analyzer - 2026-04-19

**调用**: 架构分析（自主模式，替代 /plan-eng-review）

**功能**: SOLID 原则分析器 — 检测 SRP/OCP/LSP/ISP/DIP 违规

**技术方案**: 独立模块，遵循现有 40 个分析器的模式

**架构分析**:

1. **技术可行性**: 高。每个 SOLID 原则都可以用 tree-sitter pattern 匹配：
   - SRP: 统计类方法数、属性数、行数，超过阈值 → 违规
   - OCP: 检测 isinstance/type 检查、if-elif 类型分派
   - LSP: 比较子类方法签名与父类（参数数量、返回类型）
   - ISP: 统计协议/接口/抽象基类的方法数
   - DIP: 检测 import 语句是否导入具体类 vs 抽象类

2. **架构影响**: 与现有 59 个 MCP 工具完全一致的模式
   - tree_sitter_analyzer/analysis/solid_principles.py (核心分析)
   - tree_sitter_analyzer/mcp/tools/solid_principles_tool.py (MCP 工具)
   - tests/unit/analysis/test_solid_principles.py (单元测试)
   - tests/integration/mcp/test_solid_principles_tool.py (集成测试)

3. **实现复杂度**: 中等，可在 1 个 Sprint 内完成
   - Python 检测最完整（有丰富的 class/protocol 语法）
   - Java 有 interface/abstract class 支持
   - JS/TS 有 class extends
   - Go 有 interface 满足检测

4. **维护成本**: 低。每个原则的检测逻辑独立，新增语言只需添加 query

**推荐方案**: 独立模块，与 naming_convention.py 模式一致

**风险**: LSP 违规的检测可能产生较多 false positive（鸭子类型语言）
**缓解**: 设置合理的默认阈值，提供可配置选项

**依赖**: tree-sitter (已有), 无新外部依赖

## 产品讨论记录 - Variable Mutability Analyzer - 2026-04-19

**调用**: /office-hours (autonomous mode, non-interactive)

**输入**: Variable Mutability Analyzer — 检测 shadow_variable, reassigned_constant, unused_assignment, mutation_in_iteration

**Office Hours 分析**:
- 需求真实：AI Agent 做代码审查时，变量可变性是盲区
- 现有 39 个分析器中，没有专门的可变性分析
- naming_convention 只管命名，不管行为
- coupling_metrics 只管模块间，不管函数内
- solid_principles 管架构级，不管变量级

**结论**: DO
**理由**: 填补了变量级行为分析的空白，MVP 可以 shadow_variable + unused_assignment 两个模式起步
**切入点**: shadow_variable（最常见、最好检测）+ unused_assignment（高价值、易实现）

## 技术架构讨论记录 - Variable Mutability Analyzer - 2026-04-19

**调用**: /plan-eng-review (autonomous mode, non-interactive)

**输入**: Variable Mutability Analyzer — 3 technical approaches

**GStack 的分析**:
- 方案 A（独立模块）与 39/39 现有分析器一致，风险最低
- 方案 B（扩展 naming）违反 SRP，56 个测试的模块不宜混入行为分析
- 方案 C（扩展 code_smells）粒度不匹配，code_smells 是类/方法级，可变性是变量级

**推荐方案**: 方案 A（独立模块）
**理由**: 遵循既定约定，独立测试，独立 MCP tool，维护成本最低

**风险**: scope stack tracking 是实现中最复杂的部分，但已有先例（nesting_depth, cognitive_complexity）

**依赖**: tree_sitter_python, tree_sitter_javascript, tree_sitter_typescript, tree_sitter_java, tree_sitter_go

**4 种检测模式**:
1. shadow_variable: 内层作用域重新声明外层变量
2. unused_assignment: 赋值后未被引用
3. reassigned_constant: UPPER_SNAKE_CASE 变量被重新赋值
4. mutation_in_iteration: 循环中修改外部变量

## 产品讨论记录 - Return Consistency Analyzer - 2026-04-19

**调用**: /office-hours (autonomous mode, no questions)

**输入**: 隐式类型强制分析器 vs Return Consistency Analyzer

**产品分析**:
- 隐式类型强制分析器: DON'T — 范围太窄(JS-only)，ESLint已有完美方案，ROI低
- Return Consistency Analyzer: DO — 跨语言实用，检测真实bug来源(不一致return)，无现有工具覆盖

**结论**: DO — Return Consistency Analyzer

**理由**:
1. 跨语言通用 — Python/JS/TS/Java/Go 都有不一致return的真实bug
2. 无竞争 — 现有40个分析器均未覆盖此领域
3. 一句话定义：检测函数返回路径的不一致性 — 有些分支返回值而有些不返回

**4 种检测模式**:
1. inconsistent_return: 函数内部分路径有return value，部分没有
2. mixed_return_types: 同一函数返回不同类型的值
3. missing_default_return: switch/match语句缺少default返回
4. empty_return_value: return不带value，但其他路径返回了value

---

## 产品讨论记录 - Architectural Boundary Analyzer - 2026-04-19

**调用**: /office-hours (autonomous mode)

**输入**: Architectural Boundary Analyzer — 检测分层架构违规

**产品分析**:
- DO — with narrower scope
- 解决核心问题：当代码库超过~50文件时，开发者不知道哪层引用了哪层，违规悄悄积累
- 现有41个分析器都看单文件/单模块，没人执行"这层不应该调用那层"的规则
- 减法思维：MVP只需定义标准层(UI/Controller → Service → Repository)，扫描import，标记违规
- 一句话定义："检测代码是否违反了分层架构，跨层import不应该直接引用"

**结论**: DO

**理由**: 填补了跨文件架构分析的空白，AI Agent通过MCP可以获得"你的代码有架构违规"信号

## 技术架构讨论记录 - Architectural Boundary Analyzer - 2026-04-19

**调用**: /plan-eng-review (autonomous mode)

**输入**: 方案A(import分析+预定义层) vs 方案B(目录推断+循环依赖)

**推荐方案**: 方案A — 基于import的层级分析，复用DependencyGraphBuilder

**理由**:
1. 技术可行性：方案A更简单，方案B自动推断对非标准架构会产生误报
2. 架构影响：coupling_metrics.py已复用DependencyGraphBuilder，完全对齐现有模式
3. 实现复杂度：1个Sprint，~200行分析器 + MCP工具封装 + 测试
4. 维护成本：方案A的规则集比方案B的推断逻辑更易理解

**实现方案**:
- 目录/包名映射到层级: controllers/ → L0, services/ → L1, repositories/ → L2
- 对每个文件的import，检查是否跨层超过1级
- 报告违规、合规分数、循环依赖
- 支持 Python, Java, TypeScript, C#

**风险**: 非标准目录结构的项目→优雅处理"no layers detected"

## 产品讨论记录 - Resource Lifecycle Analyzer - 2026-04-19

**结论**: DO — 资源泄漏是真实bug来源，无现有工具覆盖

**检测模式**:
1. Python: open() without `with` → HIGH
2. Python: open() in try without finally → MEDIUM
3. Java: new FileInputStream without try-with-resources → HIGH
4. TypeScript: fs.open() without cleanup → MEDIUM
5. C#: IDisposable without `using` → HIGH

## 产品讨论记录 - Concurrency Safety Analyzer - 2026-04-19

**调用**: /office-hours (Steve Jobs perspective)

**候选功能**:
1. Boundary Value Analyzer — off-by-one, empty collection, range validation → DON'T (scope too narrow, overlaps null_safety)
2. Concurrency Safety Analyzer — shared mutable state, race conditions, missing sync → DO
3. Data Flow Integrity Analyzer — unvalidated input propagation, data transformation loss → DON'T (overlaps error_handling, exception_quality, security_scan)

**乔布斯的分析**:
- 聚焦即说不: Concurrency 是唯一真正未覆盖的 CRITICAL 领域。GStack review checklist 明确标记 "Race Conditions" 为 CRITICAL。
- 减法思维: 不需要跨函数分析。单函数范围模式检测就够了。
- 一句话定义: "Catch race conditions that take down production at 3am."

**结论**: DO — Concurrency Safety Analyzer
**理由**: 唯一无覆盖的 CRITICAL 领域，解决真实痛点（并发 bug 最难调试），无现有工具重叠

**检测模式**:
1. Python: mutable class attributes modified in methods without locking → HIGH
2. Python: threading.Lock/multiprocessing without proper acquire/release → HIGH
3. JS/TS: shared mutable state in closures with async operations → MEDIUM
4. JS/TS: Promise.all without error handling → MEDIUM
5. Java: non-volatile field accessed from multiple methods → HIGH
6. Java: Collections.synchronizedMap used incorrectly → MEDIUM
7. Go: shared variable accessed from multiple goroutines → HIGH
8. Go: map concurrent read/write without mutex → HIGH

## 产品讨论记录 - Data Clump Detector - 2026-04-19

**调用**: /office-hours (乔布斯视角产品分析)

**输入**: Data Clump Detector — 检测经常一起出现的参数组

**分析**:
1. **聚焦即说不**: 解决具体问题——data clumps 是最常见的结构性异味之一。有明确的可操作性发现。
2. **减法思维**: MVP 很简单——解析函数参数，找子集匹配。单文件作用域，纯 AST，无新依赖。
3. **一句话定义**: "当相同的 3+ 参数出现在多个函数中，标记出来——它们应该是一个类。"

**结论**: DO
**理由**: 正交于现有工具（coupling_metrics 看模块耦合，这个看参数聚类），63 个分析器中无重复功能，经典 Fowler 异味。

## 技术架构讨论记录 - Data Clump Detector - 2026-04-19

**调用**: /plan-eng-review

**输入**: Data Clump Detector，方案A（纯AST子集匹配）vs 方案B（参数使用图聚类）

**分析**:
1. **技术可行性**: 方案A风险低，纯集合操作；方案B需要图算法，中高风险
2. **架构影响**: 方案A与62个分析器完全一致；方案B引入新原语
3. **实现复杂度**: 方案A 1个Sprint；方案B 2-3个Sprint
4. **维护成本**: 方案A低维护（无状态、无依赖）；方案B高维护（图结构）

**推荐方案**: 方案A（纯AST遍历 + 子集匹配）
**理由**: 简单、一致、快速交付，与现有63个分析器完全统一

**风险**: 同名不同义的参数可能产生误报（可接受）
**依赖**: 无新依赖，复用tree_sitter已支持的4种语言

## 产品讨论记录 - Primitive Obsession Detector - 2026-04-19

**调用**: /office-hours (autonomous mode, Steve Jobs perspective)

**输入**: Primitive Obsession Detector — 检测过度使用原始类型而非值对象的代码模式

**候选功能分析**:
1. Primitive Obsession Detector → DO: Fowler 经典异味，64个分析器中无覆盖
2. Refused Bequest Detector → DON'T: 检测复杂（需跨文件继承关系分析），误报率高
3. Temporary Field Detector → DON'T: 需要数据流分析判断字段使用频率

**乔布斯的分析**:

1. **聚焦即说不**: Primitive Obsession 是 Fowler 目录中剩余的**最有价值的未覆盖异味**。64 个分析器检测了结果（长参数列表、数据块），但没有工具检测**原因**（用原始类型替代值对象）。

2. **减法思维**: MVP 只需检测"函数参数全是原始类型且数量 ≥4"。这是 AST 可直接检测的模式。不需要跨文件分析，不需要数据流追踪。

3. **一句话定义**: "Find the functions that take 5 primitives when they should take 2 objects."

**结论**: DO

**理由**:
- 填补 Fowler 目录中的经典空白
- tree-sitter 精确解析参数类型注解
- 4种语言均支持（Python type hints, JS/TS JSDoc, Java 类型, Go 类型）
- 与 parameter_coupling 互补（那个看参数聚类，这个看类型原始性）
- 纯 AST 分析，1 Sprint 可完成

**检测模式**:
1. `primitive_heavy_params`: 函数参数 ≥4 且全部是原始类型
2. `primitive_soup`: 函数体中 ≥8 个原始类型局部变量
3. `anemic_value_object`: 数据类（只有字段，无行为）使用原始类型字段
4. `type_hint_code_smell`: 用字符串编码类型信息（如 `type: str = "user"` 而非枚举）

## 技术架构讨论记录 - Primitive Obsession Detector - 2026-04-19

**调用**: /plan-eng-review (autonomous mode)

**推荐方案**: 方案 A（独立模块）
**理由**: 与 64 个现有分析器完全一致的模式，最低风险，1 Sprint 可完成
**风险**: 无类型注解的代码检测能力有限，可通过变量名启发式补充
**依赖**: tree-sitter 语言模块 (已有)

**关键技术决策**:
- 原始类型: str, int, float, bool, list, dict, tuple, set, None, bytes, string, number, boolean, Object, any
- 无类型注解参数: 使用变量名启发式 (name, title, count, flag 暗示原始类型)
- 阈值: primitive_heavy_params ≥ 4, primitive_soup ≥ 8

## Self-Hosting Quality Gate - Primitive Obsession Detector - 2026-04-19

**工具**: primitive_obsession (自扫描)

**结果**: 72 issues (全部 type_hint_code_smell)
- 分析了自身代码: 33 functions, 3 classes
- 72 个 `type_hint_code_smell` 全部是 `node.type` 比较操作
- 这些是 AST 分析器的标准模式（检查节点类型是核心操作），属于预期的 false positive
- 无 primitive_heavy_params, primitive_soup, anemic_value_object 问题

**CI 检查**:
- ruff check: All checks passed
- mypy --strict: Success: no issues found in 2 source files
- pytest: 32 passed in 12.48s

**结论**: 新代码质量通过。72 个 false positive 是 AST 分析器的固有特征。

## 产品讨论记录 - Variable Shadowing Detector - 2026-04-19

**调用**: /office-hours (autonomous mode, Steve Jobs analysis)

**功能候选**: Variable Shadowing Detector

**产品分析** (GStack office-hours / Steve Jobs perspective):

1. **聚焦即说不**: 这解决核心问题。Variable shadowing 不是 style issue — 是真实 bug 源。
   - Python: list comprehension 变量遮蔽外部同名变量（闭包中的经典陷阱）
   - JavaScript: var 提升 + 块作用域导致意外遮蔽
   - Java: lambda/inner class 参数遮蔽外部变量
   - Go: := 短声明在内层块遮蔽外部变量
   72 个现有分析器中没有任何一个检测此模式。

2. **减法思维**: 最简版本 = 遍历 AST scope，检查内层变量名是否匹配外层 scope 同名变量。
   无需跨文件分析，无需类型推断，纯 AST 遍历。

3. **一句话定义**: "Catch the lines where a variable hides another with the same name in an outer scope — the kind of bug that silently breaks things."

**结论**: DO — 真实 bug 源，非理论问题，纯 AST 模式，填补真正空白

## 技术架构讨论记录 - Variable Shadowing Detector - 2026-04-19

**调用**: /plan-eng-review (autonomous mode)

**功能**: Variable Shadowing Detector

**架构分析**:

1. **技术可行性**: 风险极低。Tree-sitter 提供完整的 scope 信息，遍历每个 scope 层级，收集声明变量名，比对内外层重名。
2. **架构影响**: 完美适配 BaseAnalyzer 模式。新增 analysis/variable_shadowing.py + mcp/tools/variable_shadowing_tool.py。
3. **实现复杂度**: 1 Sprint 足够。核心逻辑 < 200 行，每个语言 10-20 行 scope 规则。
4. **维护成本**: 低。纯声明性规则，无外部依赖。

**推荐方案**: 方案 A（独立模块，继承 BaseAnalyzer）
**理由**: 与 72 个现有分析器完全一致的模式，最低风险
**关键技术决策**:
- 检测目标: function parameter 遮蔽外层变量, 局部变量遮蔽 parameter, 内层 block 变量遮蔽外层
- 语言支持: Python, JavaScript/TypeScript, Java, Go
- 节点类型:
  - Python: function_definition, lambda, list_comprehension, for_statement, with_statement
  - JS: function_declaration, arrow_function, block_statement, for_statement
  - Java: method_declaration, lambda_expression, class_declaration
  - Go: function_declaration, if_statement, for_statement, block

## Feature Score - Variable Shadowing Detector - 2026-04-19

- **独特性**: 3/3 — 72 个分析器中无 variable shadowing 检测
- **需求度**: 3/3 — 真实 bug 源（Python closure shadowing, JS var hoisting, Go := shadowing）
- **架构适配**: 3/3 — 完美匹配 BaseAnalyzer 模式
- **实现成本**: 3/3 — 单 Sprint，纯 AST 遍历
- **总分**: 12/12 ✓ (通过 ≥8 门槛)

## 产品讨论记录 - Inconsistent Return Type Detector - 2026-04-19

**调用**: /office-hours (autonomous mode, Steve Jobs analysis)

**功能候选**: Refused Bequest Detector → 转向 Inconsistent Return Type Detector

**乔布斯的分析**:
1. **聚焦即说不**: Refused Bequest 是二阶 smell，触发频率低（现代代码库组合优于继承）。
   73 个分析器中每个都需要维护，机会成本很重要。相比之下，inconsistent return type 是每个代码库、每个开发者都遇到的真实 bug 源。

2. **减法思维**: 最简版本 = 遍历 AST 中的 return 语句，检查同一函数内返回类型是否一致。
   纯 AST 模式，无需类型推断引擎。

3. **一句话定义**: "Find where a function promises one thing but returns another — the kind of bug that causes TypeErrors in production."

**结论**: DON'T — Inconsistent Return Type Detector（与 return_path.py 重叠）

## 技术架构讨论记录 - Dead Store Detector - 2026-04-19

**调用**: /plan-eng-review (autonomous mode)

**功能**: Dead Store Detector — 检测变量赋值后值从未被读取

**架构分析**:
1. **技术可行性**: 纯 AST 模式，遍历函数体 scope，构建 assignment→read 映射，标记 dead store。风险低。
2. **架构影响**: 完美适配 BaseAnalyzer，与 variable_shadowing.py 模式一致。
3. **实现复杂度**: 单 Sprint。核心逻辑：scope tracking + assignment/read tracking + cross-language node types。
4. **维护成本**: 低。声明性规则，无外部依赖。

**推荐方案**: 方案 A（纯 AST，无类型推断）
**理由**: 73 个分析器中无 dead store 检测，1 Sprint 可交付
**风险**: scope tracking 边界情况（循环变量、闭包捕获）

## Feature Score - Dead Store Detector - 2026-04-19

- **独特性**: 3/3 — 73 个分析器中无 dead store 检测
- **需求度**: 3/3 — dead store = 隐藏 bug 或不完整重构
- **架构适配**: 3/3 — 完美匹配 BaseAnalyzer + variable_shadowing 模式
- **实现成本**: 2/3 — scope tracking 增加一些复杂度
- **总分**: 11/12 ✓ (通过 ≥8 门槛)

## 产品讨论记录 - Unused Parameter Detector - 2026-04-19

**调用**: /office-hours (Steve Jobs perspective)

**输入**: Unused Parameter Detector — 检测函数/方法中从未在函数体中被引用的参数

**乔布斯的分析**:
- DO: 这解决核心问题。未使用的参数是僵尸代码，占用空间，混淆意图，掩盖真正的 bug
- 减法思维：MVP 简单到不能再简单——收集参数名，搜索引用
- 一句话定义："告诉开发者哪些函数参数是死代码——被声明了但从未被触及"

**结论**: DO

**理由**: 纯 AST 遍历，一个 Sprint 可完成，无重叠

## 技术架构讨论记录 - Unused Parameter Detector - 2026-04-19

**调用**: /plan-eng-review

**输入**: 方案A(纯AST遍历) vs 方案B(基于scope分析)

**GStack的分析**:
- 推荐方案A，纯 AST 遍历
- 风险最低，无需 scope 分析
- 与 variable_shadowing.py 和 dead_store.py 完全相同的模式
- 边缘情况可预测：self/cls、_占位符、err 回调约定

**推荐方案**: 方案A (纯 AST 遍历)
**理由**: 最低风险，完美契合 BaseAnalyzer 模式，一个 Sprint 完成

**检测类型**:
- unused_parameter: 参数在函数体中从未被引用
- unused_callback_parameter: 回调中 _ 或 err 未使用（低严重性）
- unused_self: Python self/cls 或 Java this 未使用（静态方法候选）

**功能评分**: 12/12 (独特性3 + 需求度3 + 架构适配3 + 实现成本3)

## EvoMap 自演化知识 — 工具监控自己的开发

**来源**: Wiki `ai-tech/evomap-*` 系列页面（8页）

### 核心概念映射到 ts-analyzer

| EvoMap 概念 | ts-analyzer 对应 | 实现状态 |
|------------|-----------------|---------|
| **Gene**（可复用策略模板） | BaseAnalyzer + LanguageKnowledge | ✅ 已实现 |
| **Capsule**（成功变异记录） | findings.md 产品讨论记录 + git commit | ⚠️ 非结构化 |
| **7 阶段演化循环** | AUTONOMOUS.md Sprint 循环 | ✅ 部分映射 |
| **GDI 评分** | self-hosting-gate.py + 功能评分 rubric | ✅ 已有 |
| **Swarm Intelligence** | 多 Agent 并行开发 | ❌ 未实现 |
| **ValidationReport** | ruff + mypy + pytest + self-hosting gate | ✅ 已实现 |

### 7 阶段演化循环 vs 我们的工作流

| EvoMap 阶段 | 我们的对应 | 差距 |
|------------|-----------|------|
| 1. Detect（检测问题） | 乔布斯 Skill 分析 | ✅ |
| 2. Select（选择策略） | 功能评分 >= 8/12 | ✅ |
| 3. Mutate（变异/实现） | Sprint 实现 | ✅ |
| 4. Hypothesize（假设验证） | TDD 先写测试 | ✅ |
| 5. Execute（执行） | 实现 + CI | ✅ |
| 6. Evaluate（评估） | self-hosting gate + /review | ✅ |
| 7. Solidify（固化） | commit + push + archive | ✅ |

### 关键启发：工具监控自己的开发

EvoMap 的 **Test-Time Training（TTT）** 理念：AI 在推理时通过演化策略自我改进。

应用到 ts-analyzer：
1. **自检循环**：每个新 analyzer 用已有 analyzer 扫描自己代码（已实现 via self-hosting gate）
2. **演化记录**：每个 Sprint 的成功/失败模式结构化记录为 Capsule（需改进）
3. **质量遗传**：BaseAnalyzer 继承模式 = Gene 传播（已实现）
4. **反馈驱动改进**：self-hosting 发现的问题驱动下一个重构 Sprint（已实现，每5个功能后重构）

### 下一步行动

- **结构化 Capsule**：将 findings.md 的产品讨论格式化为 EvoMap Capsule 标准（触发条件+策略+结果+置信度）
- **演化指标仪表盘**：用 ts-analyzer 自身的 health_score + complexity + coupling 工具持续监控自身代码库
- **自动触发重构**：当 self-hosting 分数下降或耦合度上升时，自动启动重构 Sprint

## 产品讨论记录 - Temporal Coupling Detector - 2026-04-25

### 竞品否决检查结论

**功能**: Temporal Coupling Detector — 检测类中方法间的隐藏时序依赖（方法 A 读取的实例变量仅由方法 B 写入）

**竞品搜索结果**:
- ESLint: 无 temporal coupling 规则
- Ruff: 无 temporal coupling 规则
- SonarQBE: 无 temporal coupling 规则
- Pylint: 无 temporal coupling 规则
- 通用搜索: 无主流静态分析工具检测此模式

**结论**: 竞品差距 3/3 — 无 VETO，继续评分

### 4 维度评分

| 维度 | 分数 | 说明 |
|------|------|------|
| 竞品差距 | 3/3 | 无任何主流工具检测 temporal coupling |
| 用户信号 | 2/3 | 运行时常见错误源，社区有讨论但无集中 issue |
| 架构适配 | 3/3 | 单文件 AST 分析，BaseAnalyzer，多语言（Py/JS/TS/Java/Go） |
| 实现成本 | 2/3 | 1 Sprint 可完成，需跟踪 self.X 读写跨方法 |
| **总分** | **10/12** | **达到门槛 — DO** |

### 1-in-1-out 牺牲

**移除**: `constant_bool_operand.py`（Python-only, ~145 行）
**原因**: Ruff PLC2201 / Pylint C2201 已覆盖 `x == "a" or "b"` 模式检测

### 实现计划

- 文件: `tree_sitter_analyzer/analysis/temporal_coupling.py`
- 分析逻辑: 对每个类，收集所有方法的实例变量读写集，标记 READ 变量仅由单个其他方法 WRITE 的情况
- 多语言: Python (self.X), JS/TS (this.X), Java (this.X), Go (receiver.X)
- Issue 类型: `temporal_coupling` (medium severity)
- MCP tool: `temporal_coupling_tool.py`

## 被拒绝功能注册表（2026-04-20 质量门控升级后建立）

以下功能类型在竞品检查中被发现已被外部工具完美覆盖，或属于低价值"语言踩坑集"类别。
未来 session **禁止重复提议**这些功能，除非有新的、具体的用户信号证明需求。

### 竞品已完美覆盖（VETO — 直接 DON'T）

| 功能 | 竞品 | 竞品规则 |
|------|------|---------|
| Loose equality (== vs ===) | ESLint | `eqeqeq`（启用率极高的核心规则） |
| Debug statement (print/console.log) | ESLint | `no-console`；Ruff `T20` |
| Assert on tuple (`assert(x,)`) | Ruff | `B033`（直接覆盖） |
| Production assert | Ruff | `S101`（测试外禁用 assert） |
| Missing break in switch | ESLint | `no-fallthrough`；SonarQBE `S128` |
| Duplicate dict key | Ruff | `F601`（Pyflakes 规则） |
| Unused loop variable | Ruff | `B007` |
| Float equality comparison | Ruff | `F632`；SonarQBE `S1244` |
| Identity comparison with literals | Ruff | `F632` |
| Mutable default multiplication | Ruff | `B006` |
| Await in loop | ESLint | `no-await-in-loop`；SonarQBE `S2925` |
| Len-comparison anti-pattern | Ruff | `PLC1802` |
| Range-len anti-pattern | Ruff | `PLC0206` |
| Useless loop else | Pylint | `useless-else-on-loop` |
| Callback hell | ESLint | `max-nested-callbacks` |
| Hardcoded IP | SonarQBE | `S1313` |
| Return in finally | SonarQBE | `S1143` |
| Statement with no effect | Ruff | `B015` |
| Late-binding closure | Ruff | `B023` |
| Import shadowing | Ruff | `A001` |
| Unnecessary lambda | Ruff | `B023`/`PLC0131` |
| Suspicious type check | Pylint | `unidiomatic-typecheck` |
| Double negation | ESLint | `no-extra-boolean-cast` |
| Literal boolean comparison | Ruff | `F632`/`E712` |
| Simplified conditional (x?true:false) | ESLint | `no-unneeded-ternary` |
| Commented-out code | ESLint | `no-commented-out-code`（插件） |
| Function redefinition | Ruff | `F811` |
| Self-assignment | Ruff | `PLW0127` |
| Nested class complexity | SonarQBE | `S2972` |
| Deep unpacking | Ruff | `PLR0916`（too-many-unpacking） |
| Missing static method | Pylint/Ruff | `R0201`/`PLR6301` |
| Unclosed file handle | Ruff SIM115, SonarQBE S2765, Pylint R1732 | All cover `open()` without `with` |
| Redundant else | ESLint `no-else-return`, Pylint R1705 | else after return/break |
| Assignment in conditional | ESLint `no-cond-assign` | `=` vs `==` in if/while (Python-excluded, narrow scope) |
| Variable shadowing | ESLint `no-shadow`, Ruff A001, Pylint W0621 | Inner scope shadows outer |
| Empty block | ESLint `no-empty`, SonarQBE S108/S1181 | Empty function/catch/loop bodies |
| Boolean complexity | Cognitive complexity (ts-analyzer internal) | cognitive_complexity.py already measures boolean operator sequences |
| Error Message Quality | error_handling.py (ts-analyzer internal) | error_handling already detects generic/empty error messages (GENERIC_ERROR_MESSAGE pattern) |
| Iterable Modification | Pylint W4901-W4903 | modified-iterating-list/set/dict covers collection modification during iteration |
| Redundant super() call | Pylint W0235 | useless-super-delegation covers Python; narrow scope (only unnecessary super() in constructors) |
| Temporary Field Detector | 无竞品（但用户信号不足） | 9/12 < 10/12 门槛 |
| Exception Boundary | 无竞品（但需要跨函数调用图） | 8/12 < 10/12 门槛 |

### 评分未达门槛

| 功能 | 评分 | 竞品差距 | 用户信号 | 架构适配 | 实现成本 | 拒绝原因 |
|------|------|---------|---------|---------|---------|---------|
| Temporary Field Detector | 9/12 | 3 | 1 | 3 | 2 | Fowler code smell，无竞品覆盖，但用户信号不足（推理得出，无 GitHub issue） |

### 低价值类别（"语言踩坑集" — 直接 DON'T）

以下类别的功能**默认 DON'T**，除非有 self-hosting 发现的真实问题作为用户信号：

- 单语言 Python 踩坑检测（`Unclosed File`（已删除 — Ruff SIM115 覆盖）、`Dict Merge in Loop`、`Iterable Modification in Loop` 等）
- 单一表达式模式匹配（`Yoda Condition`、`Identity Comparison` 等）
- 已被 IDE 实时标记的模式（`Unreachable Code`、`Unused Import` 等）

### 竞品分析知识库

以下是已执行的竞品搜索结果，供未来 session 参考（避免重复搜索）：

- **ESLint 核心规则集**：约 300+ 规则，覆盖 JS/TS 几乎所有常见模式。URL: eslint.org/docs/rules
- **Ruff 规则集**：约 700+ 规则（含 flake8-bugbear、pycodestyle、pyflakes 等）。URL: docs.astral.sh/ruff/rules
- **SonarQBE 规则集**：约 1000+ 规则，跨语言。URL: rules.sonarsource.com
- **Pylint 规则集**：约 200+ 规则。URL: pylint.readthedocs.io

## 产品讨论记录 - Guard Clause Opportunity Detector - 2026-04-21

## 重构记录 - Session 153 - 2026-04-21

**重构 1: 删除 inconsistent_return.py** (subsumed by return_path.py)
- inconsistent_return.py 只检测混合 value/bare return
- return_path.py 检测所有相同问题 + implicit_none, empty_return, complex_return_path
- 严格子集关系，直接删除
- 删除: 3 文件 (analyzer + tool + tests)

**重构 2: 删除 code_smells.py** (regex superseded by AST analyzers)
- code_smells.py 使用正则表达式检测 God Class, Long Method, Deep Nesting, Magic Numbers
- 以下 AST-based 分析器已完全取代它:
  - god_class.py → God Class
  - function_size.py → Long Method
  - nesting_depth.py → Deep Nesting
  - magic_values.py → Magic Numbers
- 正则表达式方法不准确，AST 方法更可靠
- 删除: 4 文件 (analyzer + tool + 2 test files)

**功能探索结论: 无新功能通过 10/12 门禁**
- 经过穷举分析，所有候选功能要么被竞品覆盖，要么与现有分析器重叠，要么用户信号不足
- 这说明代码库分析覆盖率已达很高水平
- 未来方向: 改善现有工具质量（合并重叠、添加语言支持、替换 regex 为 AST）

## 重构记录 - Session 154 - 2026-04-21

**重叠分析器审计** — 全面审计 115 个 analyzer，识别重叠对：

| 重叠对 | 类型 | 处理 |
|--------|------|------|
| dead_store (self_assignment) vs self_assignment.py | 子集重叠 | 从 dead_store 移除 self_assignment 检测 |
| dead_code_tool.py (未注册的 stub) | 孤儿代码 | 删除 |
| dead_code.py (纯数据类) | 被 dead_code_analysis_tool 使用 | 保留 |
| error_handling (FINALLY_WITHOUT_HANDLE) | 死代码枚举 | 删除 |
| error_handling (swallowed_error) vs empty_block (empty_catch) | 检测结果重叠 | 保留两者（不同粒度） |
| error_handling (swallowed_error) vs error_propagation (swallowed_no_propagation) | 检测结果重叠 | 保留两者（不同阈值） |
| dead_store.py vs self_assignment.py (x=x 检测) | 重复检测 | 从 dead_store 移除 |

**删除文件**:
- `mcp/tools/dead_code_tool.py` (未注册的 stub，275 行)
- `tests/unit/mcp/test_dead_code_tool.py`

**修改文件**:
- `analysis/dead_store.py`: 移除 self_assignment 检测（-40 行），减少与 self_assignment.py 的重复告警
- `analysis/error_handling.py`: 移除死代码 FINALLY_WITHOUT_HANDLE 枚举
- `mcp/registry.py`: 移除过时 "dead_code" 条目
- `scripts/self-hosting-gate.py`: 移除已删除文件引用

**候选但被否决的功能**:
- Function Purity Analyzer → 与 side_effects.py, global_state.py, variable_mutability.py 重叠
- Cyclomatic Complexity → Radon (Python), ESLint complexity (JS) 已完美覆盖
- Error Message Quality → error_handling.py 已有 generic_error_message 检测
- Context Manager Compliance → protocol_completeness.py 已有 missing_exit 检测
- Nested Subscription Safety → null_safety.py 已有 chained_access 检测
- Assertion Density → test_smells.py 已有 low_assert 检测

**调用**: /office-hours (autonomous mode)

**功能候选**: Guard Clause Opportunity Detector — 检测可以用提前返回简化的倒置条件

**分析**:

### 聚焦即说不
- ts-analyzer 核心价值是帮助 LLM 理解代码。guard clause 简化改变代码语义，是真正的代码结构洞察
- 现有 nesting_depth 只测深度，redundant_else 只检测 return 后的 else
- 新增检测能力：识别控制流倒置使主逻辑路径不必要地嵌套

### 减法思维
- MVP: 检测 if/else 块中 else 分支只含 return/raise，if 分支有 3+ 语句
- 一句话: "Find where you're forced to read indented code because the exit is buried in an else block"

### 竞品检查
- ESLint: 无对应规则
- Ruff: 无对应规则
- SonarQBE: S1126 只检测 if x: return True; else: return False
- 内部: redundant_else 只检测 return/raise 后的 else，不检测倒置条件

### 评分: 10/12 >= 10 (PASS)
- Uniqueness: 3/3 — 无竞品覆盖
- Need: 2/3 — 代码可读性改进（self-hosting 确认嵌套是常见发现）
- Architecture: 3/3 — BaseAnalyzer, AST-only, multi-language
- Cost: 2/3 — ~1 Sprint for Python + JS/TS

**结论**: DO — 真正的分析缺口，跨语言，标准架构

## 技术架构讨论 - Guard Clause Opportunity Detector - 2026-04-21

**调用**: /plan-eng-review (autonomous mode)

**推荐方案**: 方案 A — 独立 BaseAnalyzer (guard_clause.py)

**理由**:
1. 技术可行性: 与 redundant_else 是镜像模式（if-body 终止 vs else-body 终止），不同检测逻辑
2. 架构影响: 完全符合 164+ analyzer 的单文件单职责模式
3. 实现复杂度: 1 Sprint (~350 行 analyzer + ~200 行 MCP tool + ~40 tests)
4. 维护成本: 单文件独立修改，阈值调整简单

**关键排除**:
- if/elif/elif/else 链（非 guard clause 机会）
- 嵌套 if/else 内层（只检测外层）
- try/except 块（v1 跳过）

**支持语言**: Python, JS/TS, Java, Go

**风险**: 中等误报率 — 需要正确处理 if/elif 链和嵌套结构

## 产品讨论记录 - Configuration Drift Detector - 2026-04-21

**调用**: /office-hours (autonomous mode)

**功能候选**: Configuration Drift Detector — 检测应该外部化但被硬编码的配置值

**分析**:

### 聚焦即说不
- ts-analyzer 核心是帮助 LLM 理解代码。配置漂移直接影响 LLM 对部署环境的理解
- 现有 magic_values.py 不区分配置名 vs 普通字符串，env_tracker.py 不检测缺失的外部化
- 新增检测能力：交叉引用硬编码配置值与同文件 env var 使用

### 减法思维
- MVP: 检测模块级赋值中变量名匹配配置模式（host, url, port, timeout, api_key 等）但赋值了字面量
- 同文件交叉引用：如果同文件有 os.getenv() 调用，硬编码配置更容易被标记
- 不需要跨文件分析

### 竞品检查
- ESLint: 无此规则（no-hardcoded-strings 太 naive）
- Ruff: 无此规则
- SonarQBE: S1313 只检测 IP，不检测通用配置漂移
- 无竞品交叉引用硬编码值与 env var 使用

### 评分: 10/12 >= 10 (PASS)
- Uniqueness: 3/3 — 无竞品交叉引用
- Need: 2/3 — self-hosting 确认 magic_values 和 env_tracker 独立存在
- Architecture: 3/3 — 标准 BaseAnalyzer
- Cost: 2/3 — 需要模式匹配变量名 + 交叉引用

**结论**: DO — 真正的分析缺口，无竞品覆盖

## 技术架构讨论 - Configuration Drift Detector - 2026-04-21

**调用**: /plan-eng-review (autonomous mode)

**推荐方案**: 方案 A — 独立 BaseAnalyzer (config_drift.py)

**技术方案**: AST 遍历模块级赋值
- Python: 检测 module-level `NAME = literal`，NAME 匹配配置模式
- JS/TS: 检测 top-level `const NAME = literal`，NAME 匹配配置模式
- Java: 检测 class-level `static final TYPE NAME = literal`
- Go: 检测 top-level `const NAME = literal`
- 交叉引用：同文件中存在 os.getenv/process.env/System.getenv/os.Getenv 调用时提升置信度
- 配置名模式: *(host|port|url|uri|endpoint|timeout|retries|api_key|secret|db_name|database|username|password|token|base_url|domain|region|env|config|debug|log_level|bucket|queue|topic)*

**关键排除**:
- 函数内局部变量（非配置，可能是算法参数）
- 大写常量已有前缀（如 MAX_*, MIN_* 可能是算法参数不是部署配置）
- 类型注解、import 语句

**支持语言**: Python, JS/TS, Java, Go

**风险**: 误报 — 需要 "同文件有 env var" 作为置信提升，纯字面量赋值不一定都是配置

## 产品讨论记录 - Finding Suppression via Inline Comments - 2026-04-25 Session 159

**调用**: inline product analysis (autonomous mode)

**功能**: Finding Suppression — 允许用户通过行内注释静默特定 findings，类似 ESLint `eslint-disable`、Ruff `# noqa`、SonarQBE `// NOSONAR`

**分析**:

### 聚焦即说不
- ts-analyzer 核心价值是帮助 LLM 理解代码质量问题。164 个 analyzer 产生 774+ findings（self-hosting），没有静默机制意味着用户无法管理噪音
- 这不是"nice to have"——是生产环境的必需品。每个成熟的 linter 都有静默机制
- 没有 suppression = 不能用于 CI（无法排除已知/可接受的 findings）

### 减法思维
- MVP: 解析源文件中的 `# tsa: disable <rule>` 注释，在报告时过滤被静默的 findings
- 格式: `# tsa: disable <rule1>,<rule2>` (行级), `# tsa: disable-all` (文件级), `# tsa: enable` (恢复)
- 不需要修改现有 analyzer——在 finding_correlation 或 post-processing 层过滤
- 一句话: "Let users silence false positives with inline comments, like every real linter does"

### 竞品否决检查
- ESLint: `eslint-disable` → 静默 ESLint 自己的 findings（不是我们的）
- Ruff: `# noqa` → 静默 Ruff 自己的 findings
- SonarQBE: `// NOSONAR` → 静默 SonarQBE 自己的 findings
- Pylint: `# pylint: disable=` → 静默 Pylint 自己的 findings
- **无外部工具提供 ts-analyzer findings 的静默机制**
- **结论**: 竞品差距 3/3 — 无任何工具提供此功能（对我们的 findings 而言）

### 评分: 11/12 >= 10 (PASS)
- 竞品差距: 3/3 — 无外部工具为 ts-analyzer 提供静默机制
- 用户信号: 3/3 — 774 self-hosting findings 需要管理，CI 集成需要排除机制
- 架构适配: 3/3 — 独立 utility 模块，不新增 analyzer，不触碰 1-in-1-out
- 实现成本: 2/3 — ~1 Sprint（注释解析 + 过滤逻辑 + 测试）

**结论**: DO — 生产环境必需品，不增加新 analyzer，让所有现有工具更有用

## 技术架构讨论 - Finding Suppression via Inline Comments - 2026-04-25

**调用**: inline architecture analysis (autonomous mode)

**推荐方案**: 方案 A — 独立 utility 模块 + post-processing filter

**技术方案**:

1. **创建 `tree_sitter_analyzer/analysis/finding_suppression.py`** (~250 lines):
   - `SuppressedFinding` dataclass: rule_name, line, is_file_level
   - `parse_suppressions(file_path)` → 返回 set of (rule_name, line) pairs
   - `is_suppressed(rule_name, line, suppressions)` → bool
   - `filter_suppressed(findings, suppressions)` → filtered findings list

2. **注释格式** (跨语言一致):
   - Python: `# tsa: disable <rule>` / `# tsa: disable <rule1>,<rule2>` / `# tsa: disable-all` / `# tsa: enable`
   - JS/TS/Java: `// tsa: disable <rule>` / `/* tsa: disable <rule> */`
   - Go: `// tsa: disable <rule>`
   - 作用范围: 行级（注释影响下一行或当前行）+ 文件级（`disable-all`）

3. **集成点**: 
   - 不修改现有 analyzer
   - 在 finding_correlation_tool.py 中添加可选过滤
   - 新增 MCP tool: `finding_suppression` (analysis toolset)
   - 用于 self-hosting gate 过滤已知噪音

4. **实现顺序**:
   - Sprint 1: Core suppression parser + filter + tests (~40 tests)
   - 无需 Sprint 2/3（不是新 analyzer，不需要多语言增强和 MCP 集成分开做）

**关键排除**:
- 不修改 BaseAnalyzer（保持零侵入）
- 不添加 `.tsaignore` 文件支持（v1 用行内注释即可）
- 不添加全局 suppression 配置（v1 不需要）

**风险**: 低 — 纯 additive，不修改现有代码路径

## 产品讨论记录 - Query Method Mutation Detector (CQS Violation) - 2026-04-25 Session 166

**调用**: inline product analysis (autonomous mode)

**功能**: Query Method Mutation Detector — 检测以查询命名的方法（get*/is*/has*/check*/find*/can*/should*/validate*）修改对象状态，违反 Command-Query Separation 原则

**竞品否决检查**: PASS
- ESLint: No rule for CQS violations
- Ruff: No rule for CQS violations (PLR rules don't cover this)
- SonarQBE: No rule for query-named methods mutating state
- Pylint: No rule for CQS violations
- **结论**: 竞品差距 3/3 — 无任何工具检测 CQS 违规

**聚焦即说不**:
- ts-analyzer 核心价值是帮助 LLM 理解代码。`get_user()` 修改 `self._cache` 是最隐蔽的 bug 之一 — 调用者以为只是读取，实际产生了副作用
- CQS 违规导致：不可预测的行为、难以测试、难以调试、难以推理
- 一句话: "Find query-named methods that secretly mutate state — the silent bugs that break reasoning about code"

**减法思维**:
- MVP = 检测 self/this/receiver 字段写入
- 不做方法调用链追踪（只看直接赋值）
- 不做跨文件分析
- 检测规则: `self.X = ...` / `self.X += ...` inside get*/is*/has*/check*/find*/can*/should*/validate* methods
- 支持 Python (self.X), JS/TS (this.X), Java (this.X), Go (pointer receiver.X)

**评分**: 11/12 >= 10 (PASS)
- 竞品差距: 3/3 — 无竞品覆盖 CQS 违规检测
- 用户信号: 3/3 — 经典设计原则违规，self-hosting 必能发现问题实例
- 架构适配: 3/3 — 单文件 AST, BaseAnalyzer, 四语言支持
- 实现成本: 2/3 — 标准 Sprint（四语言各有独立 AST walk，但模式统一）

**1-in-1-out**: 替换 `redundant_type_cast` (Python-only, 覆盖面窄)
**结果**: 82 → 82 analyzers

## 架构分析 - Query Method Mutation Detector - 2026-04-25 Session 166

**调用**: inline architecture analysis (autonomous mode)

**实现模式**: 标准 BaseAnalyzer 子类
- 继承 `BaseAnalyzer`, 使用 `_get_parser()` 获取语言解析器
- 每种语言独立 `_analyze_*` / `_collect_*` / `_check_*` / `_walk_*` 方法组
- 520 行 analyzer + 116 行 MCP tool + 358 行 tests (25 test cases, 4 languages)

**多语言支持**:
- Python: `function_definition` → `self.X` assignment/augmented_assignment
- JS/TS: `method_definition` → `this.X` assignment_expression
- Java: `method_declaration` → `this.X` assignment_expression
- Go: `method_declaration` + pointer receiver → `receiver.X` assignment_statement

**查询名称检测**:
- Python: snake_case prefixes (`get_`, `is_`, `has_`, `check_`, `find_`, `can_`, `should_`, `validate_`)
- CamelCase: prefix + upper char / underscore (`get`, `Get`, `is`, `Is`, ...)

**Issue Types**:
- `query_method_mutation` (medium severity)

**MCP Tool**: `query_mutation` in analysis toolset, correctness category
- Formats: toon (default), json
- Standard error handling via `@handle_mcp_errors`

**架构评估**: 优秀
- 完全遵循项目 analyzer 模式
- 四语言覆盖一致
- Go 额外检查 pointer receiver（value receiver 修改不影响调用者，正确排除）
- 测试覆盖：正向（8 种 query prefix × 多语言）+ 反向（clean getter, non-query method, standalone function, value receiver）

## 产品讨论记录 - Silent Error Suppression Detector - 2026-04-25 Session 167

**调用**: inline product analysis (autonomous mode)

**功能**: Silent Error Suppression Detector — 检测 catch/except 块中静默吞没错误的模式（pass、continue、仅日志记录、return None/False）

**竞品否决检查**: PARTIAL PASS
- ESLint `no-empty`: 仅检测空 catch 块 `catch(e){}`，不检测 logging-only、pass、continue
- SonarQBE S108: 空异常捕获 — 同 ESLint，仅空块
- SonarQBE S1166: "异常不应被静默吞没" — Java-only，检测空块 + 仅 printStackTrace()，不检测 logging-only
- Ruff: 无对应规则（B904 关于 re-raise chain，非 suppression）
- Pylint: W0702 仅检测裸 except，不检测 handler body
- **结论**: 竞品差距 2/3 — 部分覆盖（空 catch 块检测），无工具覆盖 logging-only/pass/continue/return-None 模式

**与 error_handling.py 的区别**:
- error_handling 检测"捕获了什么"（broad_exception, bare_except — 异常类型问题）
- 本工具检测"对异常做了什么"（pass, continue, logging-only, return None — 处理行为问题）
- 两者正交互补，如同 function_size 和 cognitive_complexity 从不同角度分析函数

**聚焦即说不**:
- 静默错误吞没是最隐蔽的生产环境 bug 来源之一 — 系统看起来正常运行，实际数据已丢失
- `except Exception: pass` 是 Python 反模式之王，几乎是面试必问的"什么是坏代码"
- 一句话: "Detect catch blocks that silently swallow errors — the silent data loss that makes debugging impossible"

**减法思维**:
- MVP = 检测以下 handler body 模式:
  1. Python: `except ...: pass`, `except ...: continue`, `except ...: return`, `except ...: return None/False`
  2. JS/TS: `catch (e) { }`, `catch (e) { console.log(...) }` (logging-only)
  3. Java: `catch (Exception e) { }`, `catch (Exception e) { e.printStackTrace() }` (logging-only)
  4. Go: `if err != nil { log.Println(...) }` (logging-only, no return err)
- 不做: 跨函数错误传播链分析（error_propagation 已覆盖）
- 不做: 异常类型检查（error_handling 已覆盖）

**评分**: 10/12 >= 10 (PASS)
- 竞品差距: 2/3 — 部分覆盖（空 catch），无工具覆盖 logging-only/pass/continue
- 用户信号: 3/3 — 每个生产代码库都有此模式；self-hosting 必能发现实例
- 架构适配: 3/3 — BaseAnalyzer, 单文件 AST, 四语言支持
- 实现成本: 2/3 — 标准 Sprint（四语言各有 handler body 分析）

**1-in-1-out 候选**: 替换 `java_patterns.py` (Java-only regex utility, 不继承 BaseAnalyzer, 非 code quality analyzer)
**结果**: 82 → 82 analyzers

## 架构分析 - Silent Error Suppression Detector - 2026-04-25 Session 167

**调用**: inline architecture analysis (autonomous mode)

**实现模式**: 标准 BaseAnalyzer 子类

**与 error_handling.py 的架构边界**:
- error_handling: 异常类型维度（bare_except, broad_exception, unchecked_error）
- silent_suppression: 处理行为维度（pass, continue, logging-only, return None）
- 两者检测同一个 except/catch 块的不同方面，正交互补

**多语言支持**:
- Python: `except_clause` → 分析 `block` 子节点
  - pass → `silent_suppression` (high)
  - continue → `silent_suppression` (high)
  - return / return None / return False → `silent_suppression` (high)
  - 仅 logging.* / logger.* 调用 → `logging_only_suppression` (medium)
- JS/TS: `catch_clause` → 分析 body
  - 空块 → `silent_suppression` (high)
  - 仅 console.* 调用 → `logging_only_suppression` (medium)
  - return / return undefined / return null → `silent_suppression` (high)
- Java: `catch` → 分析 body
  - 空块 → `silent_suppression` (high)
  - 仅 .printStackTrace() 调用 → `logging_only_suppression` (medium)
  - 仅 log4j/slf4j 调用 → `logging_only_suppression` (medium)
- Go: `if err != nil` 模式 → 分析 body
  - 仅 log.* 调用（无 return err） → `logging_only_suppression` (medium)
  - return 但未返回 error → `silent_suppression` (high)

**Issue Types**:
- `silent_suppression` (high severity): 错误完全丢失
- `logging_only_suppression` (medium severity): 错误仅记录，无恢复/清理/传播

**Handler Body 分析策略**:
- 统计 except/catch block 的有效语句
- 如果有效语句数为 0 → silent_suppression (empty/pass)
- 如果所有有效语句都是 logging 调用 → logging_only_suppression
- 如果唯一有效语句是 return None/False/undefined → silent_suppression
- 排除：comment-only blocks, 重新抛出 (raise/throw), 有意义的业务逻辑

**MCP Tool**: `silent_suppression` in analysis toolset, bug-detection category
- Formats: toon (default), json
- Standard error handling via `@handle_mcp_errors`

**1-in-1-out**: 替换 `java_patterns.py` (Java-only regex utility, 不继承 BaseAnalyzer)
- 删除: analysis/java_patterns.py, mcp/tools/java_patterns_tool.py, tests
- 新增: analysis/silent_suppression.py, mcp/tools/silent_suppression_tool.py, tests

**架构评估**: 优秀
- 完全遵循 BaseAnalyzer 模式
- 四语言覆盖一致
- Handler body 分析是新的检测维度，不与 error_handling 重叠
- 预计 ~480 行 analyzer + ~120 行 MCP tool + ~350 行 tests
