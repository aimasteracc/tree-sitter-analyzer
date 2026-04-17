# Findings — 自主开发调研笔记

> 此文件是自主开发 Agent 的知识库。所有 wiki 知识都在这里索引。
> 每个条目包含：页面名、一句话摘要、对 ts-analyzer 的价值、完整路径。
> Agent 需要深入时，直接用 `cat /Users/aisheng.yu/wiki/wiki/ai-tech/XXX.md` 读取。

## 知识检索方式

```bash
# 方式 1：qmd 语义搜索（推荐）
qmd query "关键词" --limit 5

# 方式 2：直接读 wiki 页面（已知页面名）
cat /Users/aisheng.yu/wiki/wiki/ai-tech/<页面名>.md

# 方式 3：读原始仓库（需要源码参考）
ls /Users/aisheng.yu/wiki/raw/ai-tech/<仓库名>/
```

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

