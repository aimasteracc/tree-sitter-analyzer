# V1/V2 分离与双向演进 - 需求文档

**日期**: 2026-02-04
**状态**: Draft - 需求收集
**作者**: tree-sitter-analyzer team

---

## ⚠️ 关键决策

基于实际开发经验和项目现状，做出以下战略决策：

### 🔧 **核心策略**

1. **保持单一仓库（至少 3-6 个月）**
   - V1 和 V2 在同一仓库，通过分支隔离
   - 便于代码共享和双向学习
   - Git 历史完整，随时可独立

2. **V2 优先实用性，而非功能完整性**
   - 不追求 17 种语言全覆盖
   - 聚焦高频语言：Python, Java, TypeScript, C/C++, Go, Rust
   - 确保 Code Graph 功能完整和易用

3. **V1 稳定维护 + 创新实验**
   - 保持 17 语言支持和现有功能
   - 选择性集成 V2 的创新（如 Code Graph）
   - 月度安全更新和 bug 修复

4. **双向学习机制**
   - V1 → V2: 语言插件、TOON 优化、安全验证
   - V2 → V1: Code Graph、Markdown 格式、编码检测
   - 每周/月度定期同步

---

## 1. 项目背景与现状

### 1.1 V1 现状 (tree-sitter-analyzer)

**优势**:
- ✅ **17 语言支持**: Python, TypeScript, JavaScript, Java, C, C++, C#, Go, Rust, Kotlin, PHP, Ruby, SQL, HTML, CSS, YAML, Markdown
- ✅ **8,405 测试**: 单元、集成、回归（Golden Master）
- ✅ **成熟的 MCP 工具**: 8 个工具，生产就绪
- ✅ **TOON 格式**: 50-70% token 减少
- ✅ **fd + ripgrep**: 快速文件和内容搜索
- ✅ **公开仓库**: 社区贡献和 feedback

**劣势**:
- ❌ **单体架构**: 难以扩展和维护
- ❌ **缺少 Code Graph**: 无跨文件分析能力
- ❌ **API 不一致**: 8 个工具，不同的模式
- ❌ **有技术债**: 部分代码混乱，需要重构

**当前分支**: `main`, `develop`
**仓库**: Public (GitHub)

---

### 1.2 V2 现状 (tree-sitter-analyzer v2)

**优势**:
- ✅ **Code Graph**: 跨文件调用图、依赖分析、Mermaid 可视化 (V1 完全没有)
- ✅ **清晰架构**: 插件系统、统一 API、100% type hints
- ✅ **TDD 开发**: 814 测试，测试先行
- ✅ **3 种语言**: Python, Java, TypeScript 完全支持 + Code Graph
- ✅ **生产就绪**: E1, E2, E4 完成，100% 测试通过
- ✅ **已修复痛点**: 编码错误、Markdown 格式、CLI 简化

**劣势**:
- ❌ **功能完整度 20-25%**: 仅 3/17 语言，缺少 14 种语言
- ❌ **仍有痛点**: #4 (--summary), #6 (过滤), #14 (查询)
- ❌ **未实用化**: 尚未成为日常工具

**当前分支**: `v2-rewrite`
**未来定位**: Private (个人/企业级工具)

---

## 2. 战略目标

### 2.1 短期目标 (1-3 个月)

#### V1: 稳定维护 + 实验性创新
- [ ] **稳定维护**: 修复 bugs，安全更新，社区支持
- [ ] **实验性集成 V2 创新**:
  - [ ] Code Graph (experimental flag)
  - [ ] Markdown formatter (新增输出格式)
  - [ ] Encoding detection (增强现有功能)
- [ ] **保持 17 语言支持**
- [ ] **月度发布周期**

#### V2: 实用化优先
- [ ] **解决所有 Critical 痛点**:
  - [x] #10, #11 编码错误 ✅
  - [x] #3 Markdown 格式 ✅
  - [ ] #4 --summary 模式
  - [ ] #14 Code Graph 查询
  - [ ] #6 Code Graph 过滤
- [ ] **补全高频语言**: C/C++, Go, Rust (4 → 7 语言)
- [ ] **成为日常工具**: 每天使用 V2 至少 5 次
- [ ] **测试覆盖 > 80%**

### 2.2 中期目标 (3-6 个月)

#### V1: 持续维护
- [ ] 集成 V2 的成熟创新
- [ ] 社区贡献管理
- [ ] 安全和性能优化

#### V2: 功能完整化
- [ ] 8-10 语言支持（80/20 原则）
- [ ] Code Graph 功能完整（查询、过滤、可视化、增量）
- [ ] 所有痛点解决
- [ ] 文档完善

### 2.3 长期目标 (6+ 个月)

#### V1: 公开维护
- [ ] 作为公开的、稳定的代码分析工具
- [ ] 继续支持开源社区
- [ ] 选择性集成 V2 创新

#### V2: 独立私有化
- [ ] 从主仓库分离为独立私有仓库
- [ ] 成为企业级高端工具
- [ ] 商业化准备（可选）

---

## 3. 用户画像与使用场景

### 3.1 V1 用户画像

**主要用户**: 开源社区、AI 助手集成、个人开发者

**使用场景**:
1. **多语言项目分析**: 17 种语言全覆盖
2. **快速代码理解**: AI 助手通过 MCP 集成
3. **开源项目贡献**: 分析陌生代码库
4. **教育和学习**: 理解代码结构

**需求**:
- 稳定性和向后兼容性
- 广泛的语言支持
- 清晰的文档
- 快速响应时间

### 3.2 V2 用户画像

**主要用户**: 企业开发团队、高级工程师、项目维护者

**使用场景**:
1. **大型项目重构**: 跨文件影响分析
2. **代码审查**: 可视化调用链
3. **架构设计**: 依赖关系图
4. **技术债管理**: 识别复杂度热点
5. **新项目学习**: 快速理解代码结构

**需求**:
- Code Graph 功能强大
- 高频语言深度支持
- 性能和准确性
- 高级查询和过滤

---

## 4. 功能需求

### 4.1 V1 必备功能 (MUST-HAVE)

#### FR-V1-1: 17 语言支持
- **要求**: 保持现有 17 种语言支持
- **优先级**: P0 (Critical)
- **验收标准**: 所有语言测试通过

#### FR-V1-2: MCP 工具稳定性
- **要求**: 8 个 MCP 工具持续工作
- **优先级**: P0 (Critical)
- **验收标准**: Claude Desktop/Cursor 集成无问题

#### FR-V1-3: TOON 格式优化
- **要求**: 从 50-70% 提升到 70%+ token 减少
- **优先级**: P1 (High)
- **验收标准**: 基准测试通过

#### FR-V1-4: 安全更新
- **要求**: 月度依赖扫描和更新
- **优先级**: P0 (Critical)
- **验收标准**: 0 已知 CVE

### 4.2 V1 可选功能 (NICE-TO-HAVE)

#### FR-V1-5: Code Graph (实验性)
- **要求**: 集成 V2 的 Code Graph 作为实验性功能
- **优先级**: P2 (Medium)
- **验收标准**: 提供 `--experimental-code-graph` flag

#### FR-V1-6: Markdown 格式
- **要求**: 新增 Markdown 输出格式
- **优先级**: P2 (Medium)
- **验收标准**: 与 V2 格式一致

### 4.3 V2 必备功能 (MUST-HAVE)

#### FR-V2-1: Code Graph 完整性
- **要求**: 查询、过滤、可视化、增量构建全部完成
- **优先级**: P0 (Critical)
- **验收标准**:
  - 支持 `query_methods()`, `find_callers()`, `filter()`, `focus()`
  - Mermaid 图可配置（max_nodes, max_depth, direction）
  - 增量更新 <50ms

#### FR-V2-2: 高频语言支持
- **要求**: Python, Java, TypeScript, C/C++, Go, Rust (7 种)
- **优先级**: P0 (Critical)
- **验收标准**: 每种语言 Code Graph 完整支持

#### FR-V2-3: 痛点全部解决
- **要求**: 所有 Critical 和 High 优先级痛点解决
- **优先级**: P0 (Critical)
- **验收标准**: PAINPOINTS_TRACKER.md 中所有 🔴 和 🔥 标记完成

#### FR-V2-4: 日常可用性
- **要求**: 成为日常主力工具
- **优先级**: P0 (Critical)
- **验收标准**:
  - CLI 命令简化（tsa）✅
  - --summary 模式可用
  - 批量分析 API
  - 每天使用 V2 > 5 次

### 4.4 V2 可选功能 (NICE-TO-HAVE)

#### FR-V2-5: 剩余语言支持
- **要求**: JavaScript, C#, Kotlin, PHP, Ruby, SQL, HTML, CSS, YAML, Markdown (10 种)
- **优先级**: P3 (Low)
- **验收标准**: 80/20 原则，按需实现

#### FR-V2-6: 高级分析
- **要求**: 复杂度分析、死代码检测、代码异味
- **优先级**: P3 (Low)
- **验收标准**: 用户需求驱动

---

## 5. 非功能性需求

### 5.1 性能要求

| 指标 | V1 目标 | V2 目标 |
|------|---------|---------|
| **文件解析** | <100ms (10KB 文件) | <100ms (10KB 文件) |
| **Code Graph 构建** | N/A | <2s (50 文件) |
| **MCP 响应时间** | <200ms | <200ms |
| **搜索速度 (fd)** | <100ms | <100ms |
| **内容搜索 (ripgrep)** | <200ms | <200ms |

### 5.2 质量要求

| 指标 | V1 目标 | V2 目标 |
|------|---------|---------|
| **测试覆盖率** | 保持 80%+ | 达到 80%+ |
| **测试数量** | 保持 8,405 | 达到 5,000+ |
| **Type Safety** | 部分 | 100% mypy 合规 |
| **文档完整性** | 保持现有 | 达到 V1 水平 |

### 5.3 可维护性要求

#### V1
- [ ] 保持向后兼容性
- [ ] 语义化版本控制
- [ ] 月度发布周期
- [ ] 清晰的 CHANGELOG

#### V2
- [ ] 清晰的模块边界
- [ ] 100% type hints
- [ ] 自动化 CI/CD
- [ ] TDD 方法论

### 5.4 安全要求

#### V1 & V2
- [ ] 依赖扫描（Dependabot）
- [ ] 代码扫描（Bandit）
- [ ] 路径遍历保护
- [ ] ReDoS 防护
- [ ] CVE 响应时间 < 48h

---

## 6. Git 分支策略

### 6.1 分支结构

```
tree-sitter-analyzer/ (主仓库)
├── main                    # 历史主线（保持不变）
├── v1-stable              # V1 维护分支（公开）
├── v2-rewrite             # V2 开发分支（未来私有）
└── develop-archive        # 历史归档（不再使用）
```

### 6.2 分支规则

#### main
- **用途**: 历史主线，不再直接开发
- **保护**: 只读，仅用于发布 tag
- **合并**: 不接受新 PR

#### v1-stable
- **用途**: V1 公开维护
- **保护**: Protected branch，需 PR 审查
- **合并**:
  - V1 bug 修复
  - V1 功能增强
  - 选择性从 v2-rewrite cherry-pick 创新
- **发布**: 月度 patch 版本（v1.x.y）

#### v2-rewrite
- **用途**: V2 快速迭代开发
- **保护**: 未来私有化
- **合并**:
  - V2 新功能
  - V2 bug 修复
  - 选择性从 v1-stable cherry-pick 改进
- **发布**: 周/双周 alpha 版本（v2.0.0-alpha.x）

#### develop-archive
- **用途**: 历史归档
- **保护**: 只读
- **合并**: 不接受

### 6.3 .gitignore 策略

#### v1-stable 分支
```gitignore
# 忽略 V2 代码
v2/
.kiro/specs/v2-complete-rewrite/
```

#### v2-rewrite 分支
```gitignore
# 忽略 V1 代码（保留必要的共享库）
tree_sitter_analyzer/
.kiro/specs/v1-maintenance/

# 保留共享资源
!tree_sitter_analyzer/__init__.py  # 如果需要
```

---

## 7. 双向学习机制

### 7.1 V1 → V2 (优先级高)

| 功能 | V1 状态 | V2 状态 | 学习方式 | 优先级 |
|------|---------|---------|----------|--------|
| **TOON 优化** | 50-70% | 基础 | 代码移植 + 验证 | P0 |
| **14 种语言** | ✅ | ❌ | 插件移植 | P1 |
| **Security 验证** | ✅ | ⚠️ | 模式复用 | P0 |
| **Golden Master** | ✅ | ❌ | 方法论学习 | P1 |

### 7.2 V2 → V1 (创新回流)

| 功能 | V2 状态 | V1 状态 | 学习方式 | 优先级 |
|------|---------|---------|----------|--------|
| **Code Graph** | ✅ | ❌ | 实验性集成 | P1 |
| **Markdown 格式** | ✅ | ❌ | 新增格式 | P2 |
| **Encoding 检测** | ✅ | ⚠️ | 增强现有 | P0 |
| **插件架构** | ✅ | ⚠️ | 重构指导 | P3 |

### 7.3 同步流程

#### 每周同步 (V1 → V2)
```bash
# 在 v2-rewrite 分支
git checkout v2-rewrite
git fetch origin v1-stable
git log origin/v1-stable --oneline --since="1 week ago"
# 选择性 cherry-pick 改进
git cherry-pick <commit-hash>
```

#### 每月回流 (V2 → V1)
```bash
# 在 v1-stable 分支
git checkout v1-stable
git fetch origin v2-rewrite
git log origin/v2-rewrite --oneline --since="1 month ago"
# 选择性 cherry-pick 创新
git cherry-pick <commit-hash>
```

---

## 8. 迁移策略

### 8.1 何时独立？

**触发条件** (全部满足)：
- ✅ V2 功能完整度 > 80%
- ✅ V2 语言支持 ≥ 10/17
- ✅ V2 日常使用无阻碍
- ✅ V2 测试覆盖 > 80%
- ✅ 有明确的私有化需求

**预计时间**: 3-6 个月后

### 8.2 独立方式

#### 方案 1: Git Subtree Split（推荐）

```bash
# 从 v2-rewrite 分支提取 v2/ 目录
git subtree split --prefix=v2 -b v2-only

# 创建新私有仓库
mkdir tree-sitter-analyzer-v2-private
cd tree-sitter-analyzer-v2-private
git init
git pull ../tree-sitter-analyzer v2-only
git remote add origin <private-repo-url>
git push -u origin main
```

#### 方案 2: Git Submodule

```bash
# 在新私有仓库
git init tree-sitter-analyzer-v2-private
cd tree-sitter-analyzer-v2-private

# 复制 V2 代码
cp -r ../tree-sitter-analyzer/v2/* .

# 将 V1 作为 submodule（复用共享代码）
git submodule add https://github.com/your/tree-sitter-analyzer.git v1-shared
```

---

## 9. 风险与缓解

### 9.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **Git 分支混乱** | 高 | 中 | 清晰的分支策略文档 |
| **代码冲突** | 中 | 高 | cherry-pick 而非 merge |
| **V2 实用化失败** | 高 | 中 | 每周评估，快速迭代 |
| **双向学习中断** | 中 | 低 | 定期同步流程 |

### 9.2 业务风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| **V1 社区不满** | 中 | 低 | 透明沟通，继续维护 |
| **V2 未达预期** | 高 | 中 | 聚焦实用性，不追求完整性 |
| **资源分散** | 中 | 高 | 明确优先级，阶段性聚焦 |

---

## 10. 成功指标

### 10.1 短期成功指标 (1 个月)

- [ ] Git 分支结构清晰，所有分支推送到远程
- [ ] V2 所有 Critical 痛点解决
- [ ] V2 每天使用次数 > 5
- [ ] 双向学习流程建立并执行 1 轮

### 10.2 中期成功指标 (3 个月)

- [ ] V2 功能完整度 > 50%
- [ ] V2 语言支持 ≥ 7
- [ ] V1 集成 V2 至少 1 个创新
- [ ] 双向学习流程稳定运行

### 10.3 长期成功指标 (6 个月)

- [ ] V2 功能完整度 > 80%
- [ ] V2 成为日常主力工具
- [ ] V2 准备好独立私有化
- [ ] V1 持续稳定维护

---

## 11. 术语表

- **V1**: tree-sitter-analyzer 现有版本（公开、稳定维护）
- **V2**: tree-sitter-analyzer v2 完全重写版本（私有、快速迭代）
- **Code Graph**: V2 独有的跨文件调用图和依赖分析功能
- **TOON**: Token-Optimized Output Notation（token 优化输出格式）
- **Golden Master**: 回归测试方法论，通过输出对比检测变更
- **双向学习**: V1 和 V2 相互借鉴和移植功能的机制
- **Painpoints**: V2 实际使用中发现的问题和改进点
- **cherry-pick**: Git 命令，选择性移植单个 commit

---

## 12. 参考资料

### 内部文档
- `.kiro/specs/v2-complete-rewrite/requirements.md` - V2 需求文档
- `.kiro/specs/v2-complete-rewrite/V1_VS_V2_GAP_ANALYSIS.md` - 差距分析
- `.kiro/specs/v2-complete-rewrite/PAINPOINTS_TRACKER.md` - 痛点跟踪
- `.kiro/specs/v2-complete-rewrite/PRODUCTION_READY.md` - 生产就绪评估

### Git 文档
- [Git Branching Strategies](https://git-scm.com/book/en/v2/Git-Branching-Branching-Workflows)
- [Git Subtree](https://www.atlassian.com/git/tutorials/git-subtree)
- [Git Submodule](https://git-scm.com/book/en/v2/Git-Tools-Submodules)

---

## 13. 下一步

1. **设计阶段**: 创建 `design.md` 详细设计文档
2. **任务拆解**: 创建 `tasks.md` 任务分解文档
3. **执行 Git 重组**: 执行分支重组命令
4. **开始双向学习**: 第一轮 V1 → V2 功能移植

---

## 批准与签核

| 角色 | 名称 | 日期 | 状态 |
|------|------|------|--------|
| **项目负责人** | TBD | 2026-02-04 | Draft |
| **技术负责人** | TBD | 2026-02-04 | Draft |

---

**最后更新**: 2026-02-04
**文档版本**: 1.0
**下次审查**: 设计完成后
