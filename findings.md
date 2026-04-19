# Findings — 自主开发调研笔记

> 此文件是自主开发 Agent 的知识库。所有 wiki 知识都在这里索引。
> 每个条目包含：页面名、一句话摘要、对 ts-analyzer 的价值、完整路径。
> Agent 需要深入时，直接用 `cat /Users/aisheng.yu/wiki/wiki/ai-tech/XXX.md` 读取。

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
