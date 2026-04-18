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

