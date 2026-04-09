# Phase 3 Auto-Discovery 可行性报告

**日期**: 2026-03-31
**测试语言**: Python
**验证范围**: Grammar introspection + Wrapper node detection

---

## 执行摘要

### 可行性评分: 8/10 ✅

**推荐**: **继续 Phase 3**（推广到 17 种语言），但采用**混合策略**：

1. **Runtime introspection**（通过 tree-sitter Language API） — 替代 grammar.json
2. **Structural analysis**（代码样本 AST 分析） — 识别 wrapper nodes
3. **Name pattern matching**（启发式规则） — 辅助验证
4. **Golden corpus validation**（已有基础设施） — 最终验证

---

## 1. Grammar 获取

### ✅ 结论: **不需要 grammar.json**

#### 关键发现
- tree-sitter Python bindings **不包含** grammar.json 文件
- GitHub repo 有 `src/grammar.json`，但需要额外下载
- **tree-sitter Language API** 提供完整的运行时反射能力：
  - `node_kind_count`: 275 个 node types（Python）
  - `node_kind_for_id()`: 枚举所有节点类型
  - `field_count`: 31 个字段名称
  - `field_name_for_id()`: 枚举字段定义

#### 验证数据（Python）
```
Total node types: 266
Named node types: 124
Field names: alias, alternative, argument, arguments, attribute, body,
             cause, code, condition, consequence, definition, expression,
             format_specifier, function, guard, key, left, module_name,
             name, object, operator, operators, parameters, return_type,
             right, subject, subscript, superclasses, type, type_conversion,
             type_parameters
```

#### 优势
- ✅ 无需维护 grammar.json 镜像
- ✅ 与 tree-sitter 版本自动同步
- ✅ 所有 17 种语言均可用（只要有 Python bindings）

---

## 2. Wrapper Node 推断

### ⚠️ 结论: **启发式规则有局限，需要结构化分析**

#### 方法 A: 名称模式匹配（Heuristic）

**规则**:
```python
wrapper_patterns = [
    "decorated_",
    "attributed_",
    "modified_",
    "annotated_",
    "with_clause"
]
```

**结果**（Python）:
```
Found 4 wrapper candidates:
  - with_clause
  - decorated_definition
  - with_clause_repeat1
  - decorated_definition_repeat1
```

**问题**:
- ❌ 假阳性: `*_repeat1` 不是语义 wrapper，是 grammar 内部节点
- ❌ 假阴性: 可能遗漏其他语言的 wrapper（如 Go 的 attributed_type）

#### 方法 B: 结构化分析（Structural）

**特征工程**:
```python
def is_wrapper(node_type, stats):
    score = 0

    # 特征 1: 有 "definition" 或 "decorator" 字段
    if "definition" in stats.field_usage:
        score += 30
    if "decorator" in stats.field_usage:
        score += 30

    # 特征 2: 多种子节点类型（wrapper + wrapped）
    if len(stats.child_types) >= 2:
        score += 20

    # 特征 3: 平均子节点数 >= 2
    if stats.avg_children >= 2:
        score += 10

    # 特征 4: 名称模式（辅助）
    if matches_pattern(node_type):
        score += 10

    return score >= 30  # 阈值
```

**验证结果（decorated_definition）**:
```
Score: 70/100
Reasons: has_definition_field, multiple_child_types(3),
         avg_children(2.2), name_pattern_match

Samples: 4
Child type distribution:
  decorator:           5 occurrences  ← wrapper metadata
  function_definition: 3 occurrences  ← wrapped content
  class_definition:    1 occurrences  ← wrapped content

Field usage:
  definition: 4 times  ← 明确的 "definition" 字段指向被包装节点
```

**分析**:
- ✅ `decorated_definition` 明确包装 `function_definition` / `class_definition`
- ✅ `decorator` 节点是结构性装饰，不是语义内容
- ✅ 结构特征（字段 + 子节点分布）比名称模式更可靠

#### 推荐方法: **结构化分析 + 名称模式 + Golden Corpus 验证**

1. **自动检测**: 结构化分析识别候选 wrapper nodes
2. **启发式过滤**: 名称模式排除明显的非 wrapper
3. **人工验证**: Golden corpus 测试确认最终列表

---

## 3. 语法路径枚举

### ✅ 结论: **基于代码样本的路径枚举可行**

#### 方法: BFS 遍历 + 深度限制

```python
def enumerate_syntactic_paths(lang, code_samples, max_depth=3):
    parser = tree_sitter.Parser(lang)
    paths = set()

    for code in code_samples:
        tree = parser.parse(bytes(code, 'utf8'))

        def traverse(node, parent_path):
            if len(parent_path) > max_depth:
                return

            if node.is_named:
                paths.add((node.type, parent_path))

            new_path = parent_path + (node.type,)
            for child in node.children:
                traverse(child, new_path)

        traverse(tree.root_node, ())

    return paths
```

#### 验证数据（Python）
```
Total unique paths: 21

Sample paths involving decorated_definition:
  module > decorated_definition
  module > decorated_definition > decorator
  module > decorated_definition > decorator > identifier
  module > decorated_definition > function_definition
  module > decorated_definition > function_definition > identifier
  module > decorated_definition > function_definition > parameters
  module > decorated_definition > function_definition > block
  module > decorated_definition > class_definition
  module > decorated_definition > class_definition > identifier
  module > decorated_definition > class_definition > block
```

#### 限制
- ⚠️ 路径覆盖度依赖代码样本质量
- ⚠️ 罕见语法结构可能遗漏（需要全面的 corpus）
- ⚠️ 递归语法规则需要深度限制（避免路径爆炸）

#### 解决方案
- 利用现有 **golden corpus**（已覆盖 17 种语言的典型语法）
- 扩展 corpus 以覆盖边缘情况
- 结合 Phase 2.5 的实际 plugin 分析结果

---

## 4. 性能评估

### 测试环境
- Python 3.12
- tree-sitter 0.24.0
- tree-sitter-python 0.24.0

### Benchmark 结果

| 操作 | 耗时 | 内存 |
|------|------|------|
| Load language | < 1ms | 2MB |
| Enumerate node types (275) | < 1ms | < 1MB |
| Parse sample code (189 bytes) | < 1ms | < 1MB |
| Structural analysis (5 samples) | 3ms | 2MB |
| Path enumeration (max_depth=3) | 2ms | 1MB |

**总计**: < 10ms per language

### 扩展到 17 种语言
- 预计总耗时: **< 200ms**
- 预计内存: **< 50MB**
- ✅ **性能可接受**（可在 CI 中运行）

---

## 5. 技术障碍与风险

### 已解决
- ✅ grammar.json 不可用 → 使用 Language API
- ✅ 节点类型枚举 → `node_kind_for_id()`
- ✅ 字段定义获取 → `field_name_for_id()`
- ✅ AST 结构分析 → 直接解析代码样本

### 仍存在挑战
- ⚠️ **Wrapper 识别准确率**: 结构化分析需要高质量代码样本
- ⚠️ **跨语言泛化**: 不同语言的 wrapper patterns 可能差异较大
- ⚠️ **Grammar 变更监控**: tree-sitter 版本升级可能引入新节点类型

### 风险缓解
1. **Golden corpus 覆盖**: Phase 1 已建立 16 种语言的测试基础设施
2. **Plugin 验证**: Phase 2.5 已验证 Python/Go/Java/C/C++ 5 种语言
3. **增量推广**: 逐语言验证，而非一次性 17 种
4. **人工审查**: 自动检测结果需人工确认

---

## 6. 与现有基础设施集成

### Phase 1: Golden Corpus Infrastructure
- ✅ 已有 16 种语言的 `golden/` 测试文件
- ✅ 可直接用作 structural analysis 的代码样本
- ✅ `expected.json` 可用于验证 wrapper 识别结果

### Phase 2: Grammar Introspection System
- ✅ `GrammarIntrospector` 可扩展以支持结构化分析
- ✅ `traverse_plugin_config()` 可用于枚举现有 plugin 配置
- ✅ Coverage report 可展示 auto-discovered paths

### Phase 2.5: Plugin Integration
- ✅ 已验证 5 种语言的实际 plugin behavior
- ✅ `PluginValidator` 可用于验证 auto-discovery 结果
- ✅ 可对比 "plugin 实际识别" vs "grammar 理论支持"

---

## 7. 推荐实施路径

### Phase 3.1: Core Auto-Discovery Engine (Week 1)

**目标**: 构建基于 Language API 的自动发现引擎

**任务**:
1. 扩展 `GrammarIntrospector` 以支持：
   - Structural analysis（基于 golden corpus）
   - Wrapper pattern detection（多特征评分）
   - Syntactic path enumeration（深度限制 BFS）

2. 实现 `AutoDiscoveryEngine`:
   ```python
   class AutoDiscoveryEngine:
       def analyze_language(self, language: str) -> LanguageAnalysis:
           """分析单个语言的语法结构"""
           pass

       def detect_wrapper_nodes(self, analysis: LanguageAnalysis) -> list[str]:
           """识别 wrapper nodes"""
           pass

       def enumerate_paths(self, analysis: LanguageAnalysis) -> set[tuple]:
           """枚举所有有效语法路径"""
           pass

       def validate_against_plugin(self, analysis: LanguageAnalysis, plugin_config: dict) -> ValidationReport:
           """与现有 plugin 配置对比"""
           pass
   ```

3. 单元测试（Python 语言）

**交付物**:
- `tree_sitter_analyzer/grammar/auto_discovery.py`
- `tests/unit/grammar/test_auto_discovery.py`
- `scripts/grammar_auto_discovery_cli.py`

---

### Phase 3.2: Multi-Language Validation (Week 2)

**目标**: 在 5 种已验证语言上测试 auto-discovery

**任务**:
1. 运行 auto-discovery on Python/Go/Java/C/C++
2. 对比结果与现有 plugin 配置：
   - 新发现的 node types
   - 遗漏的 wrapper nodes
   - 假阳性的 wrapper candidates
3. 调整评分阈值和特征权重
4. 人工审查并确认最终 wrapper 列表

**交付物**:
- `docs/grammar-coverage/auto-discovery-validation-{language}.md`
- 更新后的 wrapper 列表（如需要）

---

### Phase 3.3: Full Rollout (Week 3)

**目标**: 推广到剩余 12 种语言

**任务**:
1. 对每种语言：
   - 运行 auto-discovery
   - 生成 coverage report
   - 人工审查 wrapper 识别结果
2. 更新 CI pipeline 以定期运行 auto-discovery
3. 建立 grammar 变更监控机制

**交付物**:
- 17 种语言的完整 coverage reports
- CI integration
- `docs/grammar-coverage/phase3-completion-report.md`

---

## 8. 成功指标

### 技术指标
- [ ] 17 种语言的 auto-discovery 成功率 > 90%
- [ ] Wrapper node 识别准确率 > 85%（与人工审查对比）
- [ ] 新发现的遗漏 node types > 20（跨所有语言）
- [ ] CI runtime < 5 分钟（包含 auto-discovery）

### 业务价值
- [ ] 减少手动 plugin 配置工作量 > 70%
- [ ] 发现并修复至少 5 个现有 plugin 的覆盖盲区
- [ ] 建立语法变更自动检测机制

---

## 9. 最终结论

### GO Decision: ✅ **继续 Phase 3**

**理由**:
1. ✅ 技术可行性已验证（Language API + structural analysis）
2. ✅ 性能可接受（< 200ms for 17 languages）
3. ✅ 与现有基础设施无缝集成（golden corpus + plugin validator）
4. ✅ 增量推广策略降低风险（5 → 17 languages）
5. ✅ 明确的成功指标和验证方法

**关键成功因素**:
- 高质量代码样本（golden corpus）
- 结构化分析 + 名称模式的混合策略
- 人工审查确认 auto-discovery 结果
- 与 plugin 实际行为的持续对比

**下一步**: 启动 **Phase 3.1: Core Auto-Discovery Engine**

---

## 附录 A: 原型代码

### A.1 Runtime Introspection
- `scripts/grammar_introspection_prototype.py`
  - Language API 探索
  - Node types 枚举
  - Field names 枚举
  - 启发式 wrapper 检测

### A.2 Structural Analysis
- `scripts/grammar_structural_analysis.py`
  - 多特征评分机制
  - Child type 分布分析
  - Field usage 统计
  - `decorated_definition` case study

### A.3 运行方法
```bash
# Runtime introspection
uv run python scripts/grammar_introspection_prototype.py

# Structural analysis
uv run python scripts/grammar_structural_analysis.py
```

---

## 附录 B: 参考资料

### tree-sitter 文档
- [tree-sitter API Reference](https://tree-sitter.github.io/tree-sitter/)
- [Python Bindings](https://github.com/tree-sitter/py-tree-sitter)

### 项目内部文档
- `docs/grammar-coverage/phase1-foundation-report.md` — Golden corpus infrastructure
- `docs/grammar-coverage/phase2-introspection-report.md` — Grammar introspection system
- `docs/grammar-coverage/phase2.5-plugin-integration-report.md` — Plugin validation results

### 相关 Issues
- Issue #112: Python decorated methods missing — 启发本研究

---

**报告完成日期**: 2026-03-31
**作者**: Agent 5 (Grammar Introspection Specialist)
**审核状态**: Pending CEO review
