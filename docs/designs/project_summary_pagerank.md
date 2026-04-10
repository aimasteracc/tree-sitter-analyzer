# SDD: Project Summary — 跨会话代码库智能

**状态:** Shipped (v3 + modification_guard连携)  
**日期:** 2026-04-10  
**PR:** #127 (feat/project-summary-pagerank → develop)

---

## 1. 核心价值

> **让Claude在新会话里不用探索就能做正确的事。**

两个工具，两个角色：
- `get_project_summary` → 给Claude**知识**（项目骨架是什么）
- `modification_guard` → 给Claude**约束**（改这个文件安不安全）

后者比前者有用十倍。

---

## 2. 已实现

### v1: 基础设施 (commit 30432c1)
- 纯Python幂迭代PageRank（无外部依赖）
- 增量更新（mtime+size对比，缓存命中16ms）
- 修复目录静默消失bug（spring-framework 11k文件从输出中消失）
- 目录分类：core / context / tooling
- `_describe_dir` 读 README.md 作为回退
- summary.toon 预渲染，get_project_summary直接读取
- 33个TDD测试

### v2: First-Party过滤 (commit 6726a0b)
- 从pom.xml `<groupId>` / build.gradle `group` 读取项目根包
- 只有匹配根包的import创建边，stdlib/third-party自动排除
- 回退链：构建文件 → 源文件扫描 → 不过滤
- HTML标签清理（caffeine README修复）
- buildSrc分类修正
- 15个新测试

### v3: Architecture-Only (commit aceed04)
- **只用extends/implements建图，完全丢弃import边**
- import语句仅用于反查包路径，不创建边
- 过滤单字母泛型参数（T, E, K, V）
- 过滤java.lang自动导入类（RuntimeException, Serializable等）
- 构建时间：19s → 5.7s（spring-framework 11k文件）

### P0: modification_guard连携 (commit f4ce922)
- modification_guard 读取 `.tree-sitter-cache/critical_nodes.json`
- 命中时返回 `architecture_rank`、`architecture_score`、`architecture_warning`
- Top-10节点自动提升safety verdict一级（CAUTION → REVIEW）

---

## 3. 验证结果

### Spring-Framework (11,338 files)

| 排名 | v1 | v2 | v3 |
|---|---|---|---|
| #1 | `Nullable` ❌ | `Contract` ❌ | **`Aware`** ✅ |
| #2 | `Test` ❌ | `Assert` ❌ | **`NestedRuntimeException`** ✅ |
| #3 | `Target` ❌ | `RuntimeException` ❌ | **`InitializingBean`** ✅ |
| #4 | `ElementType` ❌ | `NestedRuntimeException` ⚠️ | **`EnvironmentCapable`** ✅ |
| #5 | `Assert` ❌ | `Annotation` ❌ | **`Ordered`** ✅ |

v3的top 5全部是真正的架构扩展点。

### 端到端评估

对Spring这种Claude训练数据已包含的项目，summary的增量价值有限（省3-5次工具调用）。
真正的价值场景：**Claude不认识的私有项目**——省去整个探索阶段。

---

## 4. 设计决策

### 为什么只用extends/implements，不用import？

import衡量的是"谁用了谁"——大框架中工具类（Assert 1537次）永远赢。
extends/implements衡量的是"谁是谁的一种"——只有真正的架构接口会被继承。

```
import = USES关系 → 工具类赢（Assert > BeanFactory）
extends = IS-A关系 → 架构接口赢（BeanFactory > Assert）
```

### 为什么从构建文件读根包？

isort/ruff I001已经解决了import分类：stdlib → third-party → first-party。
构建文件（pom.xml groupId, build.gradle group）是项目作者自己声明的命名空间，
最权威。不自己猜，不维护黑名单。

### 为什么extends/implements也需要过滤？

`extends RuntimeException` 没有包路径。用同文件的import语句反查：
- `import java.lang.RuntimeException` → 不是first-party → 跳过
- 不在import里 → java.lang自动导入（`_JAVA_LANG_CLASSES`集合）→ 跳过
- 不在上述两种情况 → 同包引用 → 保留

---

## 5. 存储布局

```
.tree-sitter-cache/
  project-index.json      ← PageRank结果 + 项目元数据
  summary.toon            ← 预渲染TOON（get_project_summary直读）
  critical_nodes.json     ← PageRank top N（modification_guard读取）
  file_hashes.json        ← {filepath: [mtime, size]}（增量判断用）
```

---

## 6. 文件变更总览

| 文件 | 变更 |
|---|---|
| `mcp/utils/project_index.py` | PageRank、边提取、first-party过滤、目录分类、HTML清理、增量更新、render_toon |
| `mcp/tools/get_project_summary_tool.py` | 读取summary.toon、notes追加、is_fresh恢复 |
| `mcp/tools/build_project_index_tool.py` | (未改动，通过ProjectIndexManager间接受益) |
| `mcp/tools/modification_guard_tool.py` | 读取critical_nodes.json、architecture_warning、verdict boost |
| `mcp/tools/analyze_scale_tool.py` | annotations dict bug修复 |
| `tests/unit/mcp/test_project_summary_pagerank.py` | 48个测试 |
| `tests/unit/mcp/test_modification_guard_tool.py` | +4个测试（27总计） |
| `tests/unit/mcp/test_get_project_summary_tool.py` | 既存テスト调整 |

---

## 7. 下一步

| 优先级 | 功能 | 状态 |
|---|---|---|
| **P1** | Python first-party filtering (`sys.stdlib_module_names`) | 未着手 |
| P2 | TypeScript first-party filtering（相对导入判断） | 未着手 |
| P3 | 在Claude不认识的私有项目上做端到端行为测试 | 未着手 |
| P4 | MCP sampling增强（等 ≥ 2客户端支持） | 阻塞中 |

### 新增语言的步骤

1. `_extract_edges_from_file`中添加该语言的`elif`块（正则提取extends/implements）
2. 实现该语言的first-party检测（构建文件读取 或 stdlib API）
3. 完成 — PageRank、TOON渲染、modification_guard全自动工作
