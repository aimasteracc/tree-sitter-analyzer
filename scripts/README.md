# Scripts 管理策略

## 🎯 **原则**

**不要为每个版本创建新脚本！** 这会导致项目难以维护。脚本应该是通用的、可重用的工具。

## 📁 **当前脚本清单**

### 🔧 **核心工具（保留）**



#### 1. `sync_version_minimal.py` - 版本同步工具
- **用途**: 同步核心文件中的版本号（pyproject.toml → __init__.py）
- **何时使用**: 
  - 发布新版本前
  - 版本号不一致时
- **命令**: `uv run python scripts/sync_version_minimal.py`

### 🚀 **GitFlow自动化（保留）**

#### 2. `gitflow_release_automation.py` - GitFlow发布自动化
- **用途**: 完整的GitFlow发布流程自动化
- **何时使用**: 
  - 从develop分支创建release分支
  - 自动化发布流程
- **命令**: `uv run python scripts/gitflow_release_automation.py --version v1.1.2`

#### 3. `gitflow_helper.py` - GitFlow辅助工具
- **用途**: GitFlow工作流的辅助功能
- **何时使用**: 需要GitFlow相关辅助操作时

## ❌ **已删除的重复脚本**

- `quick_fix_v1_1_1.py` - 特定版本脚本，不应该存在
- `version_1_1_2_release_prep.py` - 特定版本脚本，不应该存在
- `sync_version.py` - 与sync_version_minimal.py重复

- `automated_release.py` - 与gitflow_release_automation.py重复

## 🎯 **最佳实践**

### 1. **脚本通用性**
- 脚本应该支持任意版本号，而不是硬编码特定版本
- 使用命令行参数传递版本号：`--version v1.1.2`

### 2. **功能分离**
- 每个脚本只负责一个明确的功能
- 避免功能重复的脚本

### 3. **命名规范**
- 使用描述性名称，说明脚本的用途
- 避免包含版本号的脚本名称

### 4. **维护策略**
- 定期审查脚本，删除不再需要的
- 合并功能相似的脚本
- 保持脚本数量最少

## 🚀 **标准工作流程**

### 发布新版本时：

1. **同步版本号**:
   ```bash
   uv run python scripts/sync_version_minimal.py
   ```

3. **自动化GitFlow发布**:
   ```bash
   uv run python scripts/gitflow_release_automation.py --version v1.1.2
   ```

## 📝 **添加新脚本的规则**

在添加新脚本之前，请确认：

1. **是否真的需要新脚本？**
   - 现有脚本无法完成这个任务吗？
   - 可以扩展现有脚本吗？

2. **脚本是否通用？**
   - 支持任意版本号吗？
   - 可以在不同场景下重用吗？

3. **功能是否明确？**
   - 脚本有单一、明确的职责吗？
   - 不会与现有脚本功能重复吗？

## 🔍 **定期清理**

建议每月审查一次scripts目录：

- 删除不再使用的脚本
- 合并功能相似的脚本
- 更新过时的脚本
- 确保所有脚本都有明确的用途

---

**记住：脚本越少，维护越容易！**
