# Release 执行指南

## 🎯 **快速开始**

本指南提供完整的 release 流程执行步骤，包括问题诊断、修复和自动化执行。

## 🚀 **立即执行 - 修复当前问题**

### **步骤 1: 快速修复 README 问题**

由于当前 README 统计检查失败，我们先运行快速修复脚本：

```bash
# 运行快速修复脚本
python scripts/quick_fix_readme.py
```

这个脚本会：
- ✅ 自动修复版本号不一致问题
- ✅ 同步 README 统计信息
- ✅ 检查并提交更改
- ✅ 推送到 develop 分支

### **步骤 2: 验证修复结果**

修复完成后，检查 GitHub Actions 状态：

```bash
# 检查当前状态
git status

# 查看最近的提交
git log --oneline -5
```

## 🔧 **完整 Release 流程执行**

### **选项 1: 使用自动化脚本（推荐）**

```bash
# 一键执行完整流程
python scripts/gitflow_release_automation.py --version v1.1.0
```

### **选项 2: 手动执行步骤**

#### **阶段 1: 准备和验证**

```bash
# 1. 确保在 develop 分支
git checkout develop
git pull origin develop

# 2. 检查工作目录状态
git status

# 3. 运行测试
uv run pytest tests/ -v

# 4. 同步 README 统计
uv run python scripts/improved_readme_updater.py
```

#### **阶段 2: 创建 Release 分支**

```bash
# 1. 创建 release 分支
git checkout -b release/v1.1.0

# 2. 更新版本号（如果需要）
# 编辑 pyproject.toml: version = "1.1.0"

# 3. 更新 CHANGELOG.md
# 添加新版本条目

# 4. 提交更改
git add pyproject.toml CHANGELOG.md
git commit -m "chore: Prepare release v1.1.0"
```

#### **阶段 3: 推送和 CI/CD**

```bash
# 1. 推送 release 分支
git push origin release/v1.1.0

# 2. 监控 GitHub Actions
# 访问: https://github.com/aimasteracc/tree-sitter-analyzer/actions
```

#### **阶段 4: 完成 Release**

```bash
# 1. 等待 CI/CD 完成
# 2. 切换到 main 分支
git checkout main
git pull origin main

# 3. 合并 release 分支
git merge release/v1.1.0

# 4. 打标签
git tag -a v1.1.0 -m "Release v1.1.0"

# 5. 推送 main 和标签
git push origin main
git push origin --tags

# 6. 切换回 develop
git checkout develop

# 7. 合并 release 分支
git merge release/v1.1.0
git push origin develop

# 8. 清理 release 分支
git branch -d release/v1.1.0
git push origin --delete release/v1.1.0
```

## 📋 **执行检查清单**

### **修复阶段**
- [ ] 运行快速修复脚本
- [ ] 验证 README 文件更新
- [ ] 检查 git 状态
- [ ] 提交并推送更改

### **Release 阶段**
- [ ] 创建 release 分支
- [ ] 更新版本和文档
- [ ] 推送触发 CI/CD
- [ ] 监控执行状态

### **完成阶段**
- [ ] CI/CD 全部通过
- [ ] 合并到 main 分支
- [ ] 创建版本标签
- [ ] 合并回 develop
- [ ] 清理临时分支

## 🔍 **问题诊断和解决**

### **问题 1: README 统计检查失败**

**症状**: `Validate final README content` 失败

**解决方案**:
```bash
# 运行快速修复脚本
python scripts/quick_fix_readme.py

# 或者手动修复
uv run python scripts/improved_readme_updater.py
git add README.md README_zh.md README_ja.md
git commit -m "fix: Sync README statistics"
git push origin develop
```

### **问题 2: 版本号不一致**

**症状**: README 显示旧版本号

**解决方案**:
```bash
# 检查当前版本
grep 'version = ' pyproject.toml

# 修复 README 中的版本号
python scripts/quick_fix_readme.py
```

### **问题 3: CI/CD 失败**

**症状**: GitHub Actions 任务失败

**解决方案**:
1. 查看失败任务日志
2. 修复问题
3. 重新推送 release 分支

## 📊 **监控和验证**

### **GitHub Actions 状态**

监控以下任务：
- ✅ `test` - 测试执行
- ✅ `build-and-deploy` - 构建和部署
- ✅ `create-main-pr` - 创建 PR

### **验证检查点**

1. **推送后**: 确认 CI/CD 开始执行
2. **测试阶段**: 确认所有测试通过
3. **构建阶段**: 确认包构建成功
4. **部署阶段**: 确认 PyPI 发布成功
5. **PR 创建**: 确认到 main 的 PR 创建成功

## 🎯 **最佳实践提示**

1. **自动化优先**: 使用提供的脚本减少人为错误
2. **分步验证**: 每个阶段完成后都要验证
3. **监控 CI/CD**: 密切关注自动化流程状态
4. **及时清理**: 完成后及时清理临时分支
5. **文档同步**: 确保所有文档保持同步

## 🚨 **紧急情况处理**

### **如果 release 分支有问题**

```bash
# 删除有问题的 release 分支
git checkout develop
git branch -D release/v1.1.0
git push origin --delete release/v1.1.0

# 重新开始流程
python scripts/gitflow_release_automation.py --version v1.1.0
```

### **如果合并失败**

```bash
# 中止合并
git merge --abort

# 检查冲突
git status

# 解决冲突后重新合并
git merge release/v1.1.0
```

---

*本指南确保 release 流程的可靠性和一致性。如有问题，请参考 [GitFlow 最佳实践](GITFLOW_BEST_PRACTICES.md) 文档。*
