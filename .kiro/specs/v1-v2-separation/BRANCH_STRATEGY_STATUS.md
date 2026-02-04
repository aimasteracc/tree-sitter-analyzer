# 分支策略执行状态

**日期**: 2026-02-04
**状态**: ✅ 初步完成

---

## 🎯 分支策略目标

根据 `requirements.md` 设计的分支策略：

```
tree-sitter-analyzer/ (主仓库)
├── main                    # 历史主线（保持不变）
├── v1-stable              # V1 维护分支（公开）✅ 已创建
├── v2-rewrite             # V2 开发分支（未来私有）✅ 已存在
└── develop-archive        # 历史归档（不再使用）
```

---

## ✅ 已完成的工作

### 1. v1-stable 分支创建

**来源**: 从 `main` 分支创建
**提交**: `c471495` - "fix(v1): Fix TOON format token duplication"
**内容**:
- ✅ V1 代码完整保留（不包含 v2/ 目录）
- ✅ 应用了 TOON 格式修复（纯 TOON 输出）
- ✅ 所有 pre-commit hooks 通过

**用途**:
- V1 的公开维护分支
- bug 修复和安全更新
- 选择性集成 V2 的创新

### 2. v2-rewrite 分支维护

**来源**: 从 `develop` 分支继续开发
**提交**: `c944853` - "fix(v1): Fix TOON format token duplication issue"
**内容**:
- ✅ V2 代码完整（v2/ 目录）
- ✅ V1 代码完整（tree_sitter_analyzer/ 目录）← 暂时保留
- ✅ V2 验证器（output_validator.py）
- ✅ V1 TOON 修复
- ✅ 规划文档（.kiro/specs/）

**用途**:
- V2 的快速迭代开发
- 同时包含 v1 和 v2（暂时共存）
- 未来私有化准备

---

## 📊 当前分支对比

| 特性 | main | v1-stable | v2-rewrite |
|------|------|-----------|------------|
| **V1 代码** | ✅ 完整 | ✅ 完整 + 修复 | ✅ 完整 + 修复 |
| **V2 代码** | ❌ 无 | ❌ 无 | ✅ 完整 |
| **TOON 修复** | ❌ 旧版 | ✅ 已修复 | ✅ 已修复 |
| **Output 验证器** | ❌ 无 | ❌ 无 | ✅ 有 |
| **规划文档** | ❌ 旧版 | ❌ 无 | ✅ 完整 |
| **用途** | 历史主线 | V1 维护 | V2 开发 |

---

## 🔄 分支工作流

### V1 维护流程（v1-stable）

```bash
# 1. 切换到 v1-stable
git checkout v1-stable

# 2. 创建修复分支
git checkout -b fix/issue-xxx

# 3. 修复并提交
git commit -m "fix(v1): ..."

# 4. 合并回 v1-stable
git checkout v1-stable
git merge fix/issue-xxx

# 5. 发布（可选）
git tag v1.x.y
git push origin v1-stable v1.x.y
```

### V2 开发流程（v2-rewrite）

```bash
# 1. 切换到 v2-rewrite
git checkout v2-rewrite

# 2. 创建功能分支
git checkout -b feat/new-feature

# 3. 开发并提交
git commit -m "feat(v2): ..."

# 4. 合并回 v2-rewrite
git checkout v2-rewrite
git merge feat/new-feature

# 5. 发布 alpha 版（可选）
git tag v2.0.0-alpha.x
```

### 双向学习流程

#### V1 → V2（每周）
```bash
# 在 v2-rewrite 分支
git checkout v2-rewrite
git log origin/v1-stable --oneline --since="1 week ago"
# 选择性 cherry-pick 改进
git cherry-pick <commit-hash>
```

#### V2 → V1（每月）
```bash
# 在 v1-stable 分支
git checkout v1-stable
git log origin/v2-rewrite --oneline --since="1 month ago"
# 选择性 cherry-pick 创新
git cherry-pick <commit-hash>  # 注意：需要手动处理 v2/ 相关文件
```

---

## 🗂️ 目录结构对比

### v1-stable 分支结构
```
tree-sitter-analyzer/
├── tree_sitter_analyzer/      # V1 主代码
│   ├── mcp/
│   │   └── utils/
│   │       └── format_helper.py  ✅ 已修复
│   ├── formatters/
│   ├── plugins/
│   └── ...
├── examples/
├── tests/
├── docs/
└── .kiro/
    └── specs/
        └── v1-v2-separation/  ❌ 暂无（未来可添加）
```

### v2-rewrite 分支结构
```
tree-sitter-analyzer/
├── tree_sitter_analyzer/      # V1 代码（暂时保留）
│   └── mcp/utils/format_helper.py  ✅ 已修复
├── v2/                         # V2 代码
│   └── tree_sitter_analyzer_v2/
│       ├── utils/
│       │   └── output_validator.py  ✅ 新增
│       ├── graph/
│       ├── mcp/
│       └── ...
├── examples/
├── tests/
├── docs/
└── .kiro/
    └── specs/
        ├── v1-v2-separation/   ✅ 完整
        └── v2-complete-rewrite/  ✅ 完整
```

---

## 📝 下一步计划

### 短期（1-2 周）

1. **清理 v2-rewrite 中的测试文件**
   - [x] 删除临时测试脚本
   - [x] 只保留核心文件

2. **推送分支到远程**
   - [ ] `git push origin v1-stable`
   - [ ] `git push origin v2-rewrite`

3. **建立 CI/CD 流程**
   - [ ] v1-stable: 运行完整测试套件
   - [ ] v2-rewrite: 运行 v2 测试 + v2 验证器

### 中期（1 个月）

4. **V1 发布计划**
   - [ ] 从 v1-stable 发布 v1.10.6（包含 TOON 修复）
   - [ ] 更新 PyPI
   - [ ] 更新文档

5. **V2 实用化**
   - [ ] 解决所有 Critical 痛点
   - [ ] 补全高频语言（C/C++, Go, Rust）
   - [ ] 每天使用 v2 至少 5 次

### 长期（3-6 个月）

6. **分支独立化准备**
   - [ ] V2 功能完整度 > 80%
   - [ ] V2 语言支持 ≥ 10/17
   - [ ] 从 v2-rewrite 中移除 v1 代码
   - [ ] 创建独立私有仓库（可选）

---

## ⚠️ 注意事项

### Cherry-pick 冲突处理

当从 v2-rewrite cherry-pick 到 v1-stable 时：
- ✅ 只保留 V1 相关的修改
- ❌ 移除所有 v2/ 目录相关的修改
- ❌ 移除所有 .kiro/specs/v2-complete-rewrite/ 相关的修改

**示例**:
```bash
git cherry-pick <commit> --no-commit
# 移除 v2 相关文件
git rm -r v2/
git rm -r .kiro/specs/v2-complete-rewrite/
# 只提交 v1 相关修改
git commit -m "..."
```

### 避免合并混乱

- ❌ 不要直接 `merge` v2-rewrite 到 v1-stable
- ✅ 使用 `cherry-pick` 选择性移植
- ✅ 每次移植后测试验证

---

## 🎯 成功指标

### 分支策略成功的标志

- [x] v1-stable 和 v2-rewrite 分支清晰分离
- [x] TOON 修复同时应用到两个分支
- [ ] CI/CD 流程正常运行
- [ ] 双向学习机制建立并执行
- [ ] V2 成为日常工具（每天使用 > 5 次）

---

## 📚 相关文档

- `requirements.md` - 分支策略设计
- `design.md` - 技术方案
- `tasks.md` - 任务拆解
- `TOON_FIX_SUMMARY.md` - TOON 修复总结

---

**最后更新**: 2026-02-04
**下次审查**: 推送到远程后
