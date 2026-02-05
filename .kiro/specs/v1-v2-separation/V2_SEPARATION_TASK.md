# V2 代码分离任务

**目标**: 创建 workspace，彻底分离 v1 和 v2 代码

---

## 🎯 最终目标架构

```
workspace/                               # 新建父仓库
├── .git/                               # workspace 的 Git 仓库
├── .gitmodules                         # submodule 配置
├── tree-sitter-analyzer-v1/            # v1-stable 的 git submodule
│   ├── tree_sitter_analyzer/          # V1 代码
│   ├── tests/
│   ├── examples/
│   └── ...
└── tree-sitter-analyzer-v2/            # v2-rewrite 清理后的 git submodule
    ├── tree_sitter_analyzer_v2/       # V2 代码（从 v2/ 目录移出）
    ├── tests/                          # V2 测试
    ├── docs/                           # V2 文档
    ├── .kiro/                          # 规划文档
    └── ...                             # 不包含 V1 代码
```

---

## 📋 执行步骤

### Phase 1: 清理 v2-rewrite 分支

**目标**: 删除所有 V1 代码，将 v2/* 移到根目录

**操作**:
1. 创建新分支 `v2-separated`
2. 删除所有 V1 相关文件：
   - `tree_sitter_analyzer/` 目录（V1 主代码）
   - V1 的配置文件
   - V1 的测试、示例、文档
3. 移动 V2 内容到根目录：
   - `v2/tree_sitter_analyzer_v2/` → `tree_sitter_analyzer_v2/`
   - `v2/tests/` → `tests/`
   - `v2/docs/` → `docs/`
   - `v2/pyproject.toml` → `pyproject.toml`
   - 等等
4. 删除空的 `v2/` 目录
5. 提交并推送到远程

**验证**:
- 根目录只有 `tree_sitter_analyzer_v2/`（V2 代码）
- 没有 `tree_sitter_analyzer/`（V1 代码）
- 没有 `v2/` 目录
- `uv run pytest tests/` 可以运行

---

### Phase 2: 创建 workspace 父仓库

**位置**: `/c/git-private/tree-sitter-analyzer-workspace/`

**操作**:
```bash
cd /c/git-private
mkdir tree-sitter-analyzer-workspace
cd tree-sitter-analyzer-workspace
git init
```

创建 README.md：
```markdown
# Tree-sitter Analyzer Workspace

包含 V1 和 V2 两个独立开发的版本。

## 子模块

- `tree-sitter-analyzer-v1/`: V1 稳定维护版本
- `tree-sitter-analyzer-v2/`: V2 重写开发版本

## 使用

克隆包含所有子模块：
\`\`\`bash
git clone --recursive <workspace-repo-url>
\`\`\`

或者分别进入子模块开发。
```

---

### Phase 3: 添加 Git Submodules

**操作**:
```bash
cd /c/git-private/tree-sitter-analyzer-workspace

# 添加 V1 submodule
git submodule add -b v1-stable \
  https://github.com/aimasteracc/tree-sitter-analyzer.git \
  tree-sitter-analyzer-v1

# 添加 V2 submodule
git submodule add -b v2-separated \
  https://github.com/aimasteracc/tree-sitter-analyzer.git \
  tree-sitter-analyzer-v2

# 提交
git add .gitmodules tree-sitter-analyzer-v1 tree-sitter-analyzer-v2
git commit -m "Add V1 and V2 as submodules"
```

---

### Phase 4: 验证独立性

**测试 V1**:
```bash
cd tree-sitter-analyzer-v1
uv sync
uv run pytest tests/
```

**测试 V2**:
```bash
cd tree-sitter-analyzer-v2
uv sync
uv run pytest tests/
```

**V2 可以修改 V1**:
```bash
cd tree-sitter-analyzer-v2
# 修改代码...
cd ../tree-sitter-analyzer-v1
git pull  # 拉取 V2 的修改
```

---

## 🚨 关键注意事项

1. **Phase 1 必须先完成**: 确保 v2-separated 分支干净，只有 V2 代码
2. **推送到远程**: Phase 1 完成后必须推送 `v2-separated` 分支
3. **Git Submodule 指向分支**:
   - V1 submodule → `v1-stable` 分支
   - V2 submodule → `v2-separated` 分支
4. **保留 .kiro/ 在 V2**: 规划文档保留在 V2 仓库中

---

## ✅ 成功标准

- [x] v2-separated 分支只包含 V2 代码
- [x] workspace 父仓库创建成功（`C:\git-private\tree-sitter-analyzer-workspace`）
- [x] 两个 submodule 已添加（v1-stable → tree-sitter-analyzer-v1，v2-separated → tree-sitter-analyzer-v2）
- [ ] 两个 submodule 都可以独立运行测试（V2 需 `uv sync --extra dev` 后运行；部分既有测试失败）
- [x] V2 与 V1 共享同一远程仓库，不同分支
- [x] 目录结构清晰，v1 和 v2 平等独立

---

**准备好后，启动 agent 执行 Phase 1**
