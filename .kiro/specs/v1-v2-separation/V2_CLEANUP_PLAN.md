# V2 分支清理计划

**目标**: 将 v2-rewrite 分支彻底清理，只保留 V2 代码

---

## 📋 操作步骤

### 1. 创建清理分支
```bash
git checkout v2-rewrite
git checkout -b v2-clean
```

### 2. 删除 V1 相关文件和目录

#### 要删除的目录：
- `tree_sitter_analyzer/` (V1 主代码)
- `tests/` (V1 测试)
- `examples/` (V1 示例，会被 v2/examples/ 替换)
- `docs/` (V1 文档，会被 v2/docs/ 替换)
- `.analysis/`
- `.benchmarks/` (会被 v2/.benchmarks/ 替换)
- `.docs/`
- `.hypothesis/`
- `.mypy_cache/` (会重新生成)
- `.pytest_cache/` (会重新生成)
- `.ruff_cache/` (会重新生成)

#### 要删除的文件：
- `AI_BEST_PRACTICES.md`
- `analyze_coverage.py`
- `analyze_coverage_json.py`
- `CHANGELOG.md` (V1 的)
- `CLAUDE.md` (V1 的，会被 v2/ 的替换)
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md` (会被 v2/ 的替换)
- `LICENSE`
- `pyproject.toml` (会被 v2/ 的替换)
- `README.md` (会被 v2/ 的替换)
- `uv.lock` (会被 v2/ 的替换)
- 所有 V1 的脚本和测试文件

### 3. 移动 V2 内容到根目录

```bash
# 移动 V2 代码
mv v2/tree_sitter_analyzer_v2 ./
mv v2/tests ./
mv v2/examples ./
mv v2/docs ./
mv v2/pyproject.toml ./
mv v2/README.md ./
mv v2/uv.lock ./
mv v2/CONTRIBUTING.md ./
mv v2/.github ./
mv v2/codecov.yml ./
mv v2/scripts ./

# 移动其他 V2 文件
mv v2/.benchmarks ./
mv v2/test_python_golden_master.py ./
mv v2/python_v2_analysis_result.json ./
```

### 4. 删除空的 v2/ 目录

```bash
rm -rf v2/
```

### 5. 保留的文件/目录

- `.kiro/` (规划文档)
- `.git/` (Git 仓库)
- `.gitignore`
- `.gitattributes`
- `.pre-commit-config.yaml`
- `.pre-commit-hooks.yaml`
- `.secrets.baseline`
- `.claude/`, `.cursor/`, `.roo/`, `.kilocode/` (IDE 配置)
- `.cursorrules`, `.kilocodemodes`, `.roomodes`

### 6. 更新配置文件

#### 更新 .gitignore
移除 V1 特定的忽略规则

#### 更新 README.md
确认是 V2 的 README

#### 更新 pyproject.toml
确认是 V2 的配置

---

## 🎯 清理后的目录结构

```
tree-sitter-analyzer-v2/
├── .git/
├── .kiro/                           # 规划文档
├── .github/                         # V2 CI/CD
├── tree_sitter_analyzer_v2/         # V2 主代码
├── tests/                           # V2 测试
├── examples/                        # V2 示例
├── docs/                            # V2 文档
├── scripts/                         # V2 脚本
├── pyproject.toml                   # V2 配置
├── README.md                        # V2 说明
├── uv.lock                          # V2 依赖
└── ...配置文件
```

---

## ⚠️ 注意事项

1. **备份**：清理前确保 v2-rewrite 已推送到远程
2. **新分支**：在 v2-clean 分支操作，不直接修改 v2-rewrite
3. **验证**：清理后运行测试确保 V2 功能正常
4. **文档更新**：更新所有文档中的路径引用

---

## ✅ 验证清单

清理完成后检查：

- [x] V2 代码在根目录 `tree_sitter_analyzer_v2/`
- [x] V2 测试可以运行 `uv run pytest tests/`（项目结构测试已通过；部分集成测试有既有失败）
- [x] 没有 V1 代码残留
- [x] 没有 `v2/` 目录
- [x] `.kiro/` 规划文档保留
- [x] 所有配置文件正确（pyproject/README 为 V2；.gitignore 已移除 V1 的 compatibility_test 规则）
- [ ] Git 历史保留（未改动）

---

**准备好后执行**
