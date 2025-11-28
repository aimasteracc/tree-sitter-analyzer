---
description: GitFlowリリースプロセスを自動化実行 - PR経由でrelease分岐からmainへの安全なマージを実行
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

1. **前提条件確認**: 現在のブランチ状態とリリース準備状況を検証
   - 現在のブランチが`develop`であることを確認
   - 未コミットの変更がないことを確認
   - リモートとの同期状態を確認

2. **バージョン情報取得**: ユーザー入力またはpyproject.tomlから次のバージョンを決定
   - 引数でバージョンが指定された場合: そのバージョンを使用
   - 引数が空の場合: pyproject.tomlから現在のバージョンを読み取り、パッチバージョンを自動インクリメント
   - バージョン形式検証 (semantic versioning: x.y.z)

3. **Release分岐作成**: developからrelease/vX.Y.Z分岐を作成
   ```bash
   git fetch origin
   git checkout -b release/v{VERSION} origin/develop
   ```

4. **リリース準備作業**: バージョン更新と文書同期
   - pyproject.tomlのバージョン更新
   - server_versionの更新
   - `uv run python scripts/sync_version_minimal.py`実行
   - 品質指標取得:
     * テスト数: `uv run python -m pytest --collect-only -q | findstr /C:"collected"`
     * 注意：カバレッジはCodecov自動徽章を使用、手動更新不要
   - 文書更新:
     * README.md (バージョン、テスト数、What's New セクション ≤15行)
     * README_zh.md, README_ja.md (同様の更新)
     * CHANGELOG.md
     * バージョン徽章、テスト徽章更新（カバレッジ徽章はCodecov自動更新）

5. **Release分岐プッシュ**: CIテスト実行トリガー
   ```bash
   git add .
   git commit -m "Release v{VERSION}: Update version and documentation"
   git push origin release/v{VERSION}
   ```

6. **Pull Request作成**: mainへのマージPRを作成
   ```bash
   # PR本文ファイル作成
   cat > pr_body.md << 'EOF'
   ## 📋 Pull Request Description

   ### 🎯 What does this PR do?
   Release v{VERSION} - [主な変更内容を記載]

   ### 🔄 Type of Change
   - [x] ✨ New feature / 📚 Documentation update / 🧪 Test improvements

   ## 🧪 Testing
   - [x] All tests pass locally
   - [x] CI tests pass

   ## 📊 Statistics
   | Metric | Value |
   |--------|-------|
   | Tests | {TEST_COUNT} passed |

   **Full Changelog**: https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CHANGELOG.md
   EOF

   # PR作成 (gh CLI使用、Windowsの場合はPATH設定が必要)
   $env:PATH = "C:\Program Files\Git\bin;$env:PATH"
   gh pr create --base main --head release/v{VERSION} \
     --title "Release v{VERSION}: [タイトル]" \
     --body-file pr_body.md

   # 一時ファイル削除
   rm pr_body.md
   ```

7. **CI待機とPRマージ**: CIテスト通過を確認
   - GitHub ActionsページでCIの実行状況を確認
   - 全テスト通過を確認
   - **ユーザーに手動マージを依頼**（またはgh pr merge使用）
   ```bash
   # オプション: CLIでマージ (--squash, --merge, --rebase から選択)
   gh pr merge --merge
   ```

8. **Main取得とタグ作成**: マージ後のmain分岐更新
   ```bash
   git fetch origin main
   git checkout main
   git pull origin main
   git tag -a v{VERSION} -m "Release v{VERSION}: [タイトル]"
   git push origin v{VERSION}
   ```

9. **GitHub Release作成**: gh CLIを使用したリリース作成
   ```bash
   $env:PATH = "C:\Program Files\Git\bin;$env:PATH"
   gh release create v{VERSION} \
     --title "v{VERSION}: [タイトル]" \
     --notes "## 🎉 Release v{VERSION}

   ### 主な変更
   - [変更内容を記載]

   ### 📊 Statistics
   | Metric | Value |
   |--------|-------|
   | Tests | {TEST_COUNT} passed |

   **Full Changelog**: https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CHANGELOG.md"
   ```

10. **Develop分岐同期**: mainの変更をdevelopに反映
    ```bash
    git checkout develop
    git pull origin develop
    git merge main
    git push origin develop
    ```

11. **クリーンアップ** (オプション): Release分岐削除
    ```bash
    git branch -d release/v{VERSION}
    git push origin --delete release/v{VERSION}
    ```

## 実行フロー

### Phase 1: 準備と検証
- 現在の状態確認 (ブランチ、未コミット変更、リモート同期)
- バージョン決定 (引数 or 自動インクリメント)
- Release分岐作成

### Phase 2: リリース準備
- バージョンファイル更新
- 品質指標取得
- 文書更新とコミット (What's New ≤15行制限に注意)
- Release分岐プッシュ

### Phase 3: PR作成とCI確認
- Pull Request作成 (release/v{VERSION} → main)
- CI テスト通過確認
- **ユーザー手動マージ待機** または gh pr merge

### Phase 4: タグとリリース
- Main分岐取得
- タグ作成・プッシュ
- GitHub Release作成

### Phase 5: 後処理
- Develop分岐同期 (main → develop)
- Release分岐削除 (オプション)
- 完了報告

## エラーハンドリング

### 前提条件エラー
- 現在のブランチがdevelopでない → 指示とともに停止
- 未コミット変更あり → コミットまたはstash指示
- リモート非同期 → fetch/pull指示

### CIテストエラー
- テスト失敗 → ログ確認、修正コミット追加
- What's New 15行制限違反 → セクション圧縮

### PRマージエラー
- コンフリクト発生 → 解決手順提示
- マージ待機 → ユーザーに手動マージ依頼

### gh CLIエラー
- git not found → `$env:PATH = "C:\Program Files\Git\bin;$env:PATH"` 設定

## 成功基準

1. ✅ Release分岐が正常に作成された
2. ✅ バージョンファイルが正しく更新された
3. ✅ Pull Requestが作成された
4. ✅ CIテストが通過した
5. ✅ PRがmainにマージされた
6. ✅ タグが作成・プッシュされた
7. ✅ GitHub Releaseが作成された
8. ✅ Develop分岐がmainと同期された

## 注意事項

- **PR経由マージ**: 直接git mergeではなく、PRを通じてmainにマージ
- **CI必須**: PRマージ前にCIテスト通過が必須
- **What's New制限**: README の What's New セクションは15行以内
- **品質保証**: テスト実行とカバレッジ確認が必須
- **文書同期**: 多言語README更新が必要
- **タグ管理**: セマンティックバージョニング準拠
- **Windows対応**: gh CLI使用時は `$env:PATH` 設定が必要

## PR本文テンプレート

```markdown
## 📋 Pull Request Description

### 🎯 What does this PR do?
Release v{VERSION} introduces [主な機能/変更].

**Key Changes:**
- 🆕 [新機能1]
- 📚 [ドキュメント更新]
- 🧪 [テスト改善]

### 🔄 Type of Change
- [ ] 🐛 Bug fix
- [x] ✨ New feature
- [x] 📚 Documentation update
- [x] 🧪 Test improvements

## 🧪 Testing

### ✅ Test Coverage
- [x] All tests pass locally
- [x] CI tests pass

### 🔍 Test Results
```
================================== {TEST_COUNT} passed ==================================
```

## 📋 Quality Checklist
- [x] ✅ Ruff linting
- [x] ✅ Type checking (mypy)
- [x] ✅ All tests pass

## 📊 Statistics
| Metric | Before | After |
|--------|--------|-------|
| Tests | {BEFORE} | {AFTER} |

**Full Changelog**: https://github.com/aimasteracc/tree-sitter-analyzer/blob/main/CHANGELOG.md
```

このプロセスはGitFlowに準拠し、PR経由の安全なマージにより品質を保証します。
