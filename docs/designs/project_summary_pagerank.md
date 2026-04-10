# SDD: Project Summary v2 — First-Party过滤

**状态:** Active  
**日期:** 2026-04-10  
**范围:** `build_project_index` 的 PageRank 噪音过滤（仅Java）

---

## 1. 核心价值

> **让Claude在新会话里不用探索就能做正确的事。**

Claude没有长期记忆。`get_project_summary`是唯一的跨会话记忆机制。

v1已经做了PageRank。但输出全是噪音（`Nullable`、`Test`、`Assert`）。
等于这个功能不存在。v2只做一件事：**让PageRank结果准确。**

---

## 2. 问题

spring-framework上验证，PageRank top 7全是标准库/测试框架：

| 排名 | 实际结果 | 期望结果 |
|---|---|---|
| #1 | `Nullable`（3177引用） | `BeanFactory` |
| #2 | `Test`（2628引用） | `ApplicationContext` |
| #3 | `Target`（318引用） | `AbstractBeanFactory` |

**根因：** `import java.util.List` 创建了边。每个文件都导入标准库，
标准库类的PageRank被虚高到架构核心之上。

---

## 3. 设计

### 3.1 只保留first-party的import

不维护噪音黑名单。反过来：**只保留项目自身的import。**

isort / ruff I001 已经解了这个分类问题：
- stdlib → 噪音
- third-party → 噪音
- first-party → 保留 ✓

### 3.2 Java：从构建文件读取根包

```python
def _detect_java_root_packages(self, project_path: Path) -> frozenset[str]:
    """从pom.xml/build.gradle读取项目groupId作为根包。"""
    roots: set[str] = set()

    # Maven
    for pom in project_path.rglob("pom.xml"):
        m = re.search(r"<groupId>([^<]+)</groupId>",
                       pom.read_text(encoding="utf-8", errors="replace"))
        if m:
            roots.add(m.group(1).strip())

    # Gradle
    for gf_name in ["build.gradle", "build.gradle.kts"]:
        for gradle in project_path.rglob(gf_name):
            m = re.search(r"""group\s*=\s*['"]([^'"]+)['"]""",
                          gradle.read_text(encoding="utf-8", errors="replace"))
            if m:
                roots.add(m.group(1).strip())

    return frozenset(roots)
```

**过滤逻辑：**

```
import org.springframework.beans.factory.BeanFactory;
  → 包 = "org.springframework.beans.factory"
  → startswith("org.springframework") → True → 创建边 ✓

import java.util.List;
  → 包 = "java.util"
  → startswith("org.springframework") → False → 跳过 ✗
```

`java.util`、`org.junit`、`lombok` 全都不匹配项目根包，自动排除。
新增任何第三方依赖也不需要更新任何列表。

### 3.3 回退链

```
pom.xml / build.gradle 的 groupId 有结果？
  YES → 用它
  NO  → 扫描 .java 的 package 声明，取高频前缀（≥10%）
    有结果？
      YES → 用它
      NO  → 不过滤（v1行为，有噪音但不丢数据）
```

### 3.4 同步修复（不属于SDD scope，直接bugfix）

- HTML标签清理：`re.sub(r"<[^>]+>", "", text)` — 1行
- buildSrc分类：`_classify_dir`加构建目录名判断 — 3行

---

## 4. 文件变更

| 文件 | 变更 |
|---|---|
| `mcp/utils/project_index.py` | 新增`_detect_java_root_packages`、`_is_first_party_java`；更新`_extract_edges_from_file` Java分支按根包过滤；bugfix: HTML清理、buildSrc分类 |

预估：约30行。

---

## 5. 成功标准

### 技术指标

1. spring-framework `critical:` 前3名包含`BeanFactory`或`ApplicationContext`
2. `Nullable`、`Test`、`Assert`、`List`不出现在任何项目的top 7中
3. caffeine `what:` 无HTML标签
4. `buildSrc/` 分类为`core`

### 端到端验证（核心）

5. **行为测试：** 给Claude `get_project_summary`的输出，然后问
   "spring-framework里事务是怎么实现的"。
   - 有critical_nodes时：Claude应直接定位到`TransactionInterceptor`
     或`PlatformTransactionManager`，工具调用 ≤ 5次
   - 无critical_nodes时：Claude需要search + 逐文件读取，工具调用 ≥ 15次
   - **差值 ≥ 10次工具调用 = 通过**

---

## 6. 下一步（v2之后）

| 优先级 | 功能 | 理由 |
|---|---|---|
| **P0** | `modification_guard`读取`critical_nodes.json` | PageRank给Claude知识，modification_guard给Claude**行动约束**。后者比前者有用十倍 |
| P1 | Python first-party过滤（`sys.stdlib_module_names`） | 第二大语言，5行代码 |
| P2 | TypeScript first-party过滤（相对导入判断） | 第三大语言，2行代码 |
| P3 | MCP sampling增强 | 等 ≥ 2个客户端支持 |

### 可扩展设计（为P1/P2预留）

每种语言的first-party检测是独立函数。新增语言 = 新增一个函数 + 一个`elif`块：

| 语言 | 检测方式 | 代码量 |
|---|---|---|
| Java | `pom.xml` groupId / `build.gradle` group | 15行（本次实现） |
| Python | `sys.stdlib_module_names` + `importlib.metadata` | 5行 |
| TypeScript | 相对导入 `./` `../` = first-party | 2行 |
| Go | `go.mod` module行 | 3行 |
| Kotlin | 同Java | 复用 |
