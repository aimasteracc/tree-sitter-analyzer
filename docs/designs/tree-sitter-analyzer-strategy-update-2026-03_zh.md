# PART B — 中文（供人阅读）

## 本文档的目的

本文档是对现有策略文档的**补充和更新**，不替换原文档。
原文档已确立了正确的产品定位：TSA 是"本地优先的 AI 代码上下文引擎"。

本次更新基于两项新的研究输入：
1. 内部竞品分析：Call Graph Analyzer（CGA），一个闭源的内部项目，内部采用面更广
2. 开源市场分析：五个相关开源项目（PageIndex、GitNexus、Evolver、CLI-Anything、
   CocoIndex Code）

---

## 竞争格局：TSA 在和谁竞争

### 内部闭源竞品：Call Graph Analyzer（CGA）

CGA 是比 TSA 更晚起步的内部工具。它也用 tree-sitter 解析 Java，用 Neo4j 存储
关系图，目前在公司内部比 TSA 有更广泛的用户基础。

CGA 有的，TSA 没有：
- 方法调用图（A 调了哪些方法？哪些方法调了 A？）
- SQL/CRUD 自动提取
- JCL 批处理流程分析（主机作业依赖图）
- COBOL 变量追踪（Hensu 搜索）
- Neo4j 图数据库持久化
- 交互式 Web 可视化界面
- Excel/CSV 批量导出

CGA 没有的，TSA 有：
- 17 种语言支持（CGA 只支持 Java/XML/SQL）
- MCP 接入 AI 工具
- Token 优化功能套件
- 项目边界安全控制
- 本地运行（CGA 部署在 AWS）

**最重要的警报**：CGA 的 FY26 Q3 路线图要加入 AI 集成——自然语言查询、LLM
接入、自动生成影响分析报告、自动生成测试用例。这正是 TSA 现在做的事。如果
两个团队各自独立建设 AI 接入层，公司就会有两套重叠的工具，都不完整。

CGA 和 TSA 共享 tree-sitter 解析基础。这是一个天然的集成接口，不应该浪费。

### 开源同类：GitNexus

GitNexus 是开源市场中对 TSA 威胁最大也最值得研究的项目。它和 TSA 高度相似：
- 同样用 tree-sitter 解析
- 同样通过 MCP 交付（已有 7 个 MCP 工具）
- 同样本地优先、隐私保护
- 支持 14 种语言

GitNexus 比 TSA 多的关键能力：
- **`impact` 工具**：改了 X，哪些地方会受影响？
- **`detect_changes`**：增量索引，只重建改动的部分
- **`context`**：一次调用返回完整依赖上下文
- **预计算关系图**：调用链、导入依赖、社区聚类、执行流
- **混合搜索**：BM25 + 语义搜索 + 融合排序

GitNexus 没有的，TSA 有：
- 项目边界安全强制执行
- Token 纪律功能套件
- 企业安全控制
- COBOL/Java 遗留系统专项支持
- CGA 集成路径

GitNexus 是开源的，是同行，不是供应商。TSA 可以学习它的架构、向它贡献代码，
或者在它的弱点上建立差异化。但不能忽视它。

### 开源同类：CocoIndex Code

CocoIndex Code 直接与 TSA 的搜索层竞争。关键特点：
- AST 语义代码搜索
- 用 Rust 编写（性能优势）
- 后台守护进程维护热索引
- 声称减少 70% token 消耗
- 支持 28 种文件类型
- 有 MCP 接入

CocoIndex 没有的：结构化提取（方法、类、调用图）、安全边界控制、大文件
部分读取工作流。

### 开源参考：PageIndex

PageIndex 是一个针对长结构化文档的 RAG 系统。它的架构思路对 TSA 的大文件
问题有直接参考价值：
- 把文档变成层级目录树（类似目录）
- LLM 先推理"看哪一章"，再取回具体内容
- 完全不用向量数据库
- 在金融文档基准测试中准确率达到 98.7%

**对 TSA 的启示**：源代码和长文档有同样的结构特征——都是层级的
（包 → 类 → 方法）。AI 应该先看"目录"，再按需取回具体代码。这比直接
平铺提取节省 60-80% 的 token。

---

## 能力缺口分析（优先级排序）

### 缺口 1：调用图和影响范围分析（紧急）

现有工具中有：CGA（Java）、GitNexus（14 种语言）
它能做什么："改了方法 X，什么会坏？""谁调用了方法 X？"
TSA 现在能提取单个方法，但不能追踪方法之间的调用关系。
这是 AI 辅助代码调查中最被需要的单项能力。

### 缺口 2：大纲优先检索（重要）

现有工具中有：PageIndex（文档）、GitNexus（代码）
它能做什么：AI 先拿到结构大纲，推理要深入哪部分，再取具体代码。
比平铺提取少用 60-80% token。
TSA 已有部分读取和结构表输出，但没有明确的"大纲优先"协议。

### 缺口 3：后台守护进程 / 增量索引（中等）

现有工具中有：CocoIndex、GitNexus
它能做什么：大型仓库搜索从秒级变成毫秒级，因为索引在后台持续维护。
TSA 目前每次调用都重新计算。

### 缺口 4：具体的 Token 减少基准数字（中等）

现有工具中有：CocoIndex（"减少 70%"）
它能做什么：一个可辩护的数字，向没用过 TSA 的工程师传达价值。
TSA 有 token 优化功能，但没有发布过具体的基准测试数字。

### 缺口 5：MCP 工具名称改为意图导向（低投入，高杠杆）

现有工具中有：GitNexus（`impact`、`context`、`detect_changes`）
它能做什么：当工具名称描述意图而非实现时，AI 代理选择正确工具的准确率
更高。TSA 现在的工具名（`find_and_grep`、`list_files`）描述的是机制，
不是目标。

---

## TSA 的持久竞争优势

这些是 TSA 有而开源同类没有的能力：

1. **项目边界强制执行 + 路径遍历防护**——企业安全要求，GitNexus 和
   CocoIndex 都没有
2. **Token 纪律功能套件**——专门为大文件和大型仓库的 AI 工作流设计
3. **COBOL-to-Java 遗留系统专项**——原始切入市场；通用工具无法匹敌
4. **CGA 集成路径**——只有 TSA 与 CGA 共享 tree-sitter 基础，可以成为
   CGA 的 AI 交付层；GitNexus 没有此路径
5. **17 种语言的深度**——比 GitNexus 广（14 种），比 CocoIndex 深（它
   支持 28 种文件类型但大多数没有结构化提取）

---

## 更新后的架构方向

原策略文档提出的演进路径仍然正确，本次更新在此基础上增加两个新层次：

```
当前架构：
  文件发现 → 内容搜索 → AST 提取 → AI

原文档提议的下一步（仍然有效）：
  边界范围文件集 → CandidateSearchService（预过滤）
    → ripgrep 精确匹配 → AST 结构提取
    → Token 优化 → AI

本次更新增加的层次：
  边界范围文件集
    → CandidateSearchService（热缓存守护进程）
    → ripgrep 精确匹配
    → OutlineService（包→类→方法层级大纲）← 新增
    → AI 导航：深入哪个分支？
    → 定向结构提取（方法体、调用图、SQL 引用）
    → Token 优化后通过 MCP 交付
    → 可选：CGAAdapter（Java 调用图查询 CGA 的 Neo4j）← 新增
```

**新增的服务**（对原有服务的补充，不替换）：

- `OutlineService`：为文件或包构建并提供层级代码大纲，支持 AI 大纲优先
  导航
- `CallGraphService`：追踪方法到方法的调用关系，初期专注 Java；为
  `trace_impact` MCP 工具提供数据
- `CGAAdapter`（可选，渐进式）：当 CGA 可用时查询 Neo4j，不可用时回退
  到 CallGraphService

---

## 更新后的 MCP 工具清单

现有工具（保留，可考虑增加别名）：
- `list_files` → 可考虑别名 `map_project_structure`
- `search_content` → 可考虑别名 `locate_usage`
- `find_and_grep` → 可考虑别名 `find_impacted_files`
- `analyze_file` → 保留；增加大纲模式

新增工具（基于竞争差距分析）：
- `get_code_outline`：返回文件或模块的层级大纲，不含方法体内容；支持
  大纲优先导航
- `trace_impact`：给定方法或类名，返回所有调用者和被调用者；回答"改
  了 X 什么会坏"
- `get_call_chain`：从入口点追踪到目标方法的执行路径
- `map_sql_usage`：返回范围内所有 SQL 操作，映射到调用它们的方法
  （初期 Java 为主）

---

## 更新后的 SMART 工作流映射

```
S（设定范围）→ list_files / map_project_structure
               建立项目边界，枚举文件范围

M（绘制结构）→ get_code_outline（新增）
               构建层级结构大纲；AI 导航后再取内容

A（分析依赖）→ trace_impact / map_sql_usage / CallGraphService（新增）
               依赖分析、影响范围、SQL/DB 调用面

R（取回代码）→ analyze_file / search_content / find_and_grep
               定向提取 AI 需要的具体内容

T（追踪路径）→ get_call_chain / 时序图（通过 CGAAdapter 可选）
               执行路径追踪，调用序列重建
```

---

## 更新后的战略赌注

原文档的三个赌注仍然有效，本次增加两个：

**赌注 1（不变）**：重新定位产品叙事（"AI 代码上下文引擎"）

**赌注 2（不变）**：加入 CandidateSearchService 预过滤层

**赌注 3（不变）**：把 SMART 变成产品教义

**赌注 4（新增）**：大纲优先检索
增加 `get_code_outline` 作为一级 MCP 工具。这是与 GitNexus 直接竞争
的单一改动，同时与 TSA 的 AST 基础完全一致。代价是一个新工具，收益是
一种全新的 AI 导航模式。

**赌注 5（新增）**：发布基准数字
测量一个代表性大型 Java 文件在三种情况下的 token 消耗：
(a) 原始全文件投喂，(b) TSA 结构提取，(c) TSA 大纲优先导航。
把比例数字放进 README 第一句话。这把 TSA 的 token 优化故事从功能描述
变成可防御的主张。

---

## 更新后的 90 天日程

### 第 0 阶段（立即，优先于所有其他行动）：建立 CGA 合作

- 联系 CGA 团队（NTA 区分6）
- 提议：TSA 负责 AI 交付（MCP），CGA 负责图分析（Neo4j）
- 具体要求：CGA 从 Neo4j 暴露读 API；TSA 构建 CGAAdapter
- 理由：CGA Q3 AI 集成开发窗口还未关闭，但时间有限
- 如果 CGA 拒绝：TSA 独立构建 CallGraphService；这个能力无论如何
  都需要

### 第 1 阶段（第 1-4 周）：叙事修正

- 用新的一行描述更新 README
- 加入基准数字（token 减少测量结果）
- 统一"本地优先代码上下文引擎"的分类表述

### 第 2 阶段（第 4-8 周）：架构新增

- 上线 `get_code_outline` MCP 工具
- 引入 CandidateSearchService（原文档已规划）
- 测量大型仓库的延迟改善

### 第 3 阶段（第 8-12 周）：平台整合

- 上线 `trace_impact` MCP 工具（CallGraphService 或 CGAAdapter）
- 把 SMART 变成标准入门路径，附带明确的工具映射
- 为每个 MCP 工具发布 SKILL.md（AI 代理可发现的工具文档）

---

## 更新后的指挥官意图

我们不是在建一个更好的解析器。
我们不是在建可视化工具。

我们在建：
- **开源生态里**：安全的本地上下文层，让 AI 能在真实企业代码库上工作；
  做到 GitNexus 做不到的（安全控制 + 企业合规 + 遗留系统专项）
- **公司内部**：CGA 的 AI 交付层；把闭源图分析工具的洞察通过 MCP 交付给
  AI 代理

一句话：

`我们是连接企业代码库与 AI 代理的安全本地上下文基础设施。`
