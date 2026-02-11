# Tree-sitter Analyzer v2 — 全球顶级代码分析 MCP 项目战略规划

> 作者视角：全球顶尖代码分析系统设计师
> 日期：2026-02-11
> 状态：战略蓝图 v1.0

---

## Part I: 项目现状精确评估

### 1.1 资产盘点

| 维度 | 数据 | 评级 |
|------|------|------|
| 核心代码 | 55 files, 450 symbols, 13,512 LOC | A（精炼） |
| 测试规模 | 998 tests, 91% coverage | A+ |
| 语言支持 | Python, Java, TypeScript/JS (3 + Tree-sitter 基座) | B |
| MCP 工具数 | 12 tools (含 code_intelligence) | A |
| 智能分析 | trace_call_flow, impact_analysis, gather_context | A（独家） |
| TOON 格式 | 50-70% token 压缩率 | A+（独家）|
| v1 实测 | 188 files / 96K LOC / 3,139 symbols / 10.68s | B+（有提升空间）|

### 1.2 竞品全景对照

```
                        我们       ast-grep    semgrep     aider       continue.dev
                        ─────────  ─────────   ─────────   ─────────   ─────────
MCP 原生集成             ★★★★★      ☆☆☆☆☆       ☆☆☆☆☆       ★★☆☆☆       ★★☆☆☆
项目级代码地图            ★★★★☆      ☆☆☆☆☆       ★★☆☆☆       ☆☆☆☆☆       ☆☆☆☆☆
双向调用链追踪            ★★★★★      ★★★☆☆       ★★★★☆       ☆☆☆☆☆       ☆☆☆☆☆
修改影响分析              ★★★★★      ☆☆☆☆☆       ★★★☆☆       ☆☆☆☆☆       ☆☆☆☆☆
LLM 上下文捕获            ★★★★★      ☆☆☆☆☆       ☆☆☆☆☆       ★★★☆☆       ★★★☆☆
Token 优化 (TOON)        ★★★★★      ☆☆☆☆☆       ☆☆☆☆☆       ☆☆☆☆☆       ☆☆☆☆☆
Dead Code 检测           ★★★★☆      ★★☆☆☆       ★★★★★       ☆☆☆☆☆       ☆☆☆☆☆
语言覆盖度               ★★☆☆☆      ★★★★☆       ★★★★★       N/A         N/A
增量更新                 ★★★☆☆      ★★★★★       ★★★★☆       N/A         N/A
规则/查询 DSL            ★★☆☆☆      ★★★★★       ★★★★★       N/A         N/A
```

### 1.3 核心定位差异化

我们的独特价值主张是**其他所有工具都不具备**的组合：

```
MCP 原生 × 项目级智能 × Token 优化 = 唯一面向 AI 助手的代码分析引擎
```

这不是一个与 semgrep/ast-grep 正面竞争的静态分析工具。
这是一个 **让 AI 瞬间理解整个代码库** 的基础设施。

---

## Part II: 差距诊断——距离"全球顶尖"还差什么

### Tier 1: 根基性缺陷（不修则无法称"顶尖"）

| # | 缺陷 | 严重度 | 当前状态 | 竞品参照 |
|---|------|--------|---------|---------|
| G1 | **增量扫描缺失** — 每次 scan 全量重扫 10s+，100K+ LOC 项目不可用 | Critical | graph/incremental.py 存在但 code_map 未集成 | ast-grep: 毫秒级增量 |
| G2 | **类型推断空白** — 无法解析 `x: List[str]`、泛型、继承链 | Critical | 解析器只提取 name/params | semgrep: 完整类型感知 |
| G3 | **语言覆盖不足** — 只有 Py/Java/TS，缺 Go/Rust/C/C++ | High | languages/ 下 3 个 parser | ast-grep: 20+ 语言 |
| G4 | **graph 与 code_map 两套体系割裂** | High | graph/ 用 NetworkX, code_map 用 dataclass，互不相通 | 应统一 |

### Tier 2: 体验性缺陷（不修则无法从"好用"到"惊艳"）

| # | 缺陷 | 严重度 | 说明 |
|---|------|--------|------|
| G5 | **无 Watch 模式** — 不能监听文件变化自动更新代码地图 | High | IDE 集成必需 |
| G6 | **无 Diff 感知** — 不能只分析 git diff 变化的文件 | Medium | PR review 场景关键 |
| G7 | **gather_context 的代码提取过于粗糙** — 只按行号切，不按语义边界 | Medium | 可能截断函数体 |
| G8 | **无类继承链/接口实现追踪** | Medium | OOP 项目核心需求 |

### Tier 3: 商业化缺陷（不修则无法形成生态）

| # | 缺陷 | 说明 |
|---|------|------|
| G9 | 无 MCP Marketplace 发布 | 无法被 Claude Desktop 等发现 |
| G10 | 无 benchmark 对比数据 | 无法证明比竞品快 |
| G11 | 无 VS Code 扩展 | 最大开发者群体无法使用 |
| G12 | README 缺乏 animated demo GIF | 首屏吸引力不足 |

---

## Part III: 六大支柱战略

要成为全球最顶尖的代码分析 MCP 项目，需要在六个维度同时建立绝对优势：

```
                    ┌─────────────────────────┐
                    │   PILLAR 1: SPEED       │ ← 增量、并行、缓存
                    │   10ms 响应, 不是 10s    │
                    └────────────┬────────────┘
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
┌────────┴────────┐  ┌──────────┴──────────┐  ┌────────┴────────┐
│ PILLAR 2:       │  │ PILLAR 3:           │  │ PILLAR 4:       │
│ DEPTH           │  │ BREADTH             │  │ INTELLIGENCE    │
│ 类型推断、继承链  │  │ 10+ 语言、统一接口   │  │ 影响分析、重构建议 │
│ 语义级理解       │  │ 一个 parser 加一行   │  │ AI 专属上下文引擎 │
└────────┬────────┘  └──────────┬──────────┘  └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │ PILLAR 5: INTEGRATION   │ ← MCP / VS Code / CLI / API
                    │ 到处可用, 随处集成       │
                    └────────────┬────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │ PILLAR 6: ECOSYSTEM     │ ← 文档 / 示例 / Marketplace
                    │ 社区、星标、信任         │
                    └─────────────────────────┘
```

---

## Part IV: 分阶段执行路线图

### Phase A: "闪电" — 速度革命（2-3 个 Sprint）

**目标**: scan 从 10s 降到 <500ms（已缓存项目）、<2s（冷启动 100K LOC）

| Sprint | 功能 | 技术方案 | 验收标准 |
|--------|------|---------|---------|
| A1 | **mtime 增量扫描** | `_parse_file` 加 mtime 检查 + pickle 缓存 | 第二次 scan 同一项目 <500ms |
| A2 | **并行文件解析** | `concurrent.futures.ProcessPoolExecutor` | 冷启动 100K LOC <2s |
| A3 | **Git Diff 模式** | `git diff --name-only` → 只扫描变更文件 | `scan(mode="diff")` |

**为什么第一个做速度**: 速度是信任的基础。10s 延迟 = AI 助手等待 = 用户放弃。

### Phase B: "深潜" — 语义深度（2-3 个 Sprint）

**目标**: 从"语法级"分析升级到"语义级"分析

| Sprint | 功能 | 技术方案 | 验收标准 |
|--------|------|---------|---------|
| B1 | **类继承链追踪** | AST 提取 bases/implements → 继承图 | `trace_inheritance("MyClass")` 返回完整链 |
| B2 | **接口/协议实现发现** | Protocol/ABC/interface 匹配 | `find_implementations("Serializable")` |
| B3 | **类型注解提取** | 解析 `-> ReturnType`、`param: Type` | SymbolInfo 增加 `type_annotations` 字段 |
| B4 | **Scope-Aware 符号解析** | 函数内局部变量 vs 模块级 vs 类属性 | 消除 gather_context 的误匹配 |

### Phase C: "扩张" — 语言广度（3-4 个 Sprint）

**目标**: 从 3 语言扩展到 10+，且新增语言 <100 LOC

| Sprint | 语言 | 优先级理由 |
|--------|------|-----------|
| C1 | **Go** | 云原生生态核心语言，MCP 用户群大 |
| C2 | **Rust** | 系统编程增长最快语言 |
| C3 | **C/C++** | 嵌入式/底层开发必需 |
| C4 | **Kotlin, Swift** | 移动开发双端 |
| C5 | **Ruby, PHP** | Web 后端长尾需求 |

**技术方案**: 设计统一的 `LanguageProfile` 数据类，每种语言只需定义 AST 节点映射表，不再写 parser class。

```python
@dataclass
class LanguageProfile:
    name: str
    extensions: list[str]
    function_node_types: list[str]     # ["function_definition", "method_definition"]
    class_node_types: list[str]        # ["class_definition"]
    call_node_types: list[str]         # ["call", "method_invocation"]
    import_node_types: list[str]       # ["import_statement", "import_from_statement"]
    decorator_node_types: list[str]    # ["decorator"]
    name_field: str                    # "name" or "declarator"
    body_field: str                    # "body" or "block"
```

### Phase D: "觉醒" — AI 智能升级（2-3 个 Sprint）

**目标**: 从"被动查询"升级到"主动洞察"

| Sprint | 功能 | 说明 |
|--------|------|------|
| D1 | **重构建议引擎** | 基于 dead code + 高复杂度 + 超大函数 → 自动生成重构建议 |
| D2 | **代码异味检测** | 循环依赖、God Class、过深继承链 → TOON 格式报告 |
| D3 | **变更风险预测** | 结合 impact_analysis + git history → "这次改动的风险是 HIGH" |
| D4 | **智能代码摘要** | 对每个模块生成一句话自然语言摘要（用符号数据，不用 LLM）|

### Phase E: "连接" — 集成生态（持续）

| 优先级 | 目标 | 方案 |
|--------|------|------|
| E1 | **MCP Marketplace 发布** | 规范化 tool schema、添加 metadata |
| E2 | **VS Code 扩展** | 调用 CLI/API，显示代码地图侧边栏 |
| E3 | **GitHub Action** | PR review 自动生成影响分析评论 |
| E4 | **Benchmark 站点** | 对比 ast-grep/semgrep 的扫描速度和准确度 |

---

## Part V: 技术架构演进蓝图

### 当前架构（v2.0-alpha）

```
┌─────────────────────────────────────────────────────┐
│                    MCP Server                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ analyze  │ │ extract  │ │ search   │ ...×12     │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘            │
│       │            │            │                    │
│  ┌────┴────────────┴────────────┴─────────┐         │
│  │         Tool Layer (BaseTool)           │         │
│  └────────────────┬───────────────────────┘         │
│                   │                                  │
│  ┌────────────────┼───────────────────────┐         │
│  │ code_map.py    │   graph/builder.py    │ ← 割裂！│
│  │ (dataclass)    │   (NetworkX)          │         │
│  └────────────────┴───────────────────────┘         │
│                   │                                  │
│  ┌────────────────┴───────────────────────┐         │
│  │   Language Parsers (Py/Java/TS)        │         │
│  └────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────┘
```

### 目标架构（v2.1+）

```
┌──────────────────────────────────────────────────────────┐
│                    MCP Server                             │
│  ┌─────────────────────────────────────────────────┐     │
│  │          Unified Tool Layer (12+ tools)          │     │
│  └────────────────────┬────────────────────────────┘     │
│                       │                                   │
│  ┌────────────────────┴────────────────────────────┐     │
│  │           Project Intelligence Engine            │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐    │     │
│  │  │ CodeMap  │ │ CallGraph│ │ TypeResolver  │    │     │ ← 统一
│  │  │ (symbols)│ │ (edges)  │ │ (inheritance) │    │     │
│  │  └────┬─────┘ └────┬─────┘ └──────┬───────┘    │     │
│  │       └─────────────┼──────────────┘            │     │
│  │              Unified ProjectModel               │     │
│  └────────────────────┬────────────────────────────┘     │
│                       │                                   │
│  ┌────────────────────┴────────────────────────────┐     │
│  │        Incremental Scan Engine                   │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐    │     │
│  │  │ mtime    │ │ parallel │ │ git diff     │    │     │
│  │  │ cache    │ │ parse    │ │ mode         │    │     │
│  │  └──────────┘ └──────────┘ └──────────────┘    │     │
│  └────────────────────┬────────────────────────────┘     │
│                       │                                   │
│  ┌────────────────────┴────────────────────────────┐     │
│  │   Universal Language Adapter                     │     │
│  │  ┌─────────────────────────────────────────┐    │     │
│  │  │  LanguageProfile (data-driven, no class) │    │     │ ← 新增语言
│  │  │  Py │ Java │ TS │ Go │ Rust │ C │ ...   │    │     │   只需一个
│  │  └─────────────────────────────────────────┘    │     │   配置文件
│  └─────────────────────────────────────────────────┘     │
│                                                           │
│  ┌─────────────────────────────────────────────────┐     │
│  │   Output Engine (TOON / JSON / Mermaid / MD)    │     │
│  └─────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────┘
```

### 统一 ProjectModel 的核心设计

```python
@dataclass
class ProjectModel:
    """One model to rule them all — replaces CodeMapResult + NetworkX graph."""

    # Identity
    root_path: Path
    scan_timestamp: float

    # Symbols (the heart)
    symbols: dict[str, SymbolNode]        # FQN → node (function/class/method/variable)
    modules: dict[str, ModuleNode]        # path → module

    # Relationships (the blood vessels)
    calls: EdgeIndex                       # caller_fqn → set[callee_fqn]
    imports: EdgeIndex                     # module_path → set[imported_fqn]
    inheritance: EdgeIndex                 # class_fqn → set[parent_fqn]
    implementations: EdgeIndex             # class_fqn → set[interface_fqn]

    # Derived intelligence (computed lazily, cached)
    _dead_code: Lazy[list[SymbolNode]]
    _hot_spots: Lazy[list[tuple[SymbolNode, int]]]
    _entry_points: Lazy[list[SymbolNode]]
    _dependency_graph: Lazy[MermaidDiagram]

    # Intelligence APIs (same as current, but on unified model)
    def trace_call_flow(self, name: str, max_depth: int = 3) -> CallFlowResult: ...
    def impact_analysis(self, name: str) -> ImpactResult: ...
    def gather_context(self, query: str, max_tokens: int = 4000) -> ContextResult: ...
    def find_implementations(self, interface: str) -> list[SymbolNode]: ...
    def trace_inheritance(self, class_name: str) -> InheritanceChain: ...
    def suggest_refactorings(self) -> list[RefactoringSuggestion]: ...
```

---

## Part VI: 质量门禁标准（成为顶尖的底线）

| 门禁 | 标准 | 当前 | 目标 |
|------|------|------|------|
| 测试覆盖率 | ≥90% | 91% | 维持 |
| 单元测试数 | ≥1000 | 998 | ≥1500 |
| Ruff 错误 | 0 | 0 | 维持 |
| Mypy 错误 | 0 | 0 | 维持 |
| 冷启动扫描 (100K LOC) | <2s | ~10s | <2s |
| 热缓存响应 | <50ms | ~6ms | 维持 |
| 支持语言数 | ≥10 | 3 | ≥10 |
| MCP 工具数 | ≥15 | 12 | ≥15 |
| Dead Code 误报率 | <5% | ~0% (已知项目) | <5% 通用 |
| 文档完整性 | API 100% docstring | ~80% | 100% |

---

## Part VII: 优先级排序——下一步做什么

### 价值/成本矩阵

```
价值 ↑
│  ★ A1 增量扫描        ★ B1 继承链
│  (极高价值,中等成本)    (高价值,中等成本)
│
│  ★ A2 并行解析         ★ C1 Go 语言
│  (高价值,低成本)        (高价值,高成本)
│
│  ★ D1 重构建议         ★ G4 统一模型
│  (中价值,中成本)        (高价值,极高成本)
│
│  ★ E1 Marketplace      ★ C3 C/C++
│  (中价值,低成本)        (中价值,高成本)
│───────────────────────────────────── 成本 →
```

### 推荐执行顺序（接下来 6 个 Sprint）

| Sprint | 功能 | Phase | 理由 |
|--------|------|-------|------|
| **S3** | 增量扫描 (mtime cache) | A1 | 速度是第一性原理，10s→<0.5s |
| **S4** | 类继承链追踪 | B1 | 用户问得最多的问题 |
| **S5** | 并行文件解析 | A2 | 冷启动提速 5-10x |
| **S6** | LanguageProfile 统一适配层 | C0 | 为 Go/Rust 铺路 |
| **S7** | Go 语言支持 | C1 | 云原生生态最大增量 |
| **S8** | 重构建议引擎 | D1 | "主动洞察"品牌差异化 |

---

## Part VIII: 品牌定位声明

```
tree-sitter-analyzer v2

The Code Intelligence Engine for AI Assistants.

不是又一个 linter。不是又一个 AST 查询工具。
这是唯一一个从第一天就为 LLM 设计的代码分析引擎。

一次扫描 → 全局理解 → 精准上下文 → 零幻觉

Scan once. Understand everything. Hallucinate never.
```

---

## Part IX: 致开发者

这个项目已经拥有了竞品不具备的核心护城河：
- **MCP 原生**: 不是后加的，是从骨子里为 AI 助手设计的
- **TOON 格式**: 独创的 token 优化输出，节省 50-70%
- **智能三件套**: trace_call_flow + impact_analysis + gather_context 组合拳
- **装饰器感知**: 业界领先的 dead code 精确度

现在需要的是：
1. **速度**——让"瞬间理解"变成真正的"瞬间"
2. **深度**——从语法级走向语义级
3. **广度**——从 3 语言到 10+ 语言
4. **生态**——从一个人的工具变成一个社区的标准

按照这份蓝图执行，6 个 Sprint 后，这将是全球最好的代码分析 MCP 项目。
不是之一。是**唯一**。
