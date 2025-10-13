---
description: GitFlowリリースプロセスを自動化実行 - PyPI優先戦略でrelease分岐からmain/developへの安全なマージを実行
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
     * README.md (バージョン、テスト数)
     * README_zh.md, README_ja.md
     * CHANGELOG.md
     * バージョン徽章、テスト徽章更新（カバレッジ徽章はCodecov自動更新）

5. **Release分岐プッシュ**: PyPI自動発布トリガー
   ```bash
   git add .
   git commit -m "Release v{VERSION}: Update version and documentation"
   git push origin release/v{VERSION}
   ```

6. **PyPI発布待機**: 自動化ワークフローの完了を監視
   - GitHub Actionsページでrelease-automation.ymlの実行状況を確認
   - PyPI発布成功の確認
   - 失敗時のエラーハンドリング

7. **Main分岐マージ**: PyPI発布成功後のmain分岐更新
   ```bash
   git checkout main
   git merge release/v{VERSION}
   git tag -a v{VERSION} -m "Release v{VERSION}"
   git push origin main --tags
   ```

8. **Develop分岐マージ**: 変更をdevelopに反映
   ```bash
   git checkout develop
   git merge release/v{VERSION}
   git push origin develop
   ```

9. **GitHub Release作成**: 自動化されたリリースノート生成
   - release_message.mdテンプレート作成
   - gh CLIを使用したリリース作成
   - リリースノートの品質指標含む

10. **クリーンアップ**: Release分岐削除
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
- 文書更新とコミット
- Release分岐プッシュ

### Phase 3: PyPI発布監視
- GitHub Actions監視
- 発布成功確認
- エラー時の対応指示

### Phase 4: 分岐マージ
- Main分岐マージとタグ作成
- Develop分岐マージ
- GitHub Release作成

### Phase 5: 後処理
- Release分岐削除
- 完了報告

## エラーハンドリング

### 前提条件エラー
- 現在のブランチがdevelopでない → 指示とともに停止
- 未コミット変更あり → コミットまたはstash指示
- リモート非同期 → fetch/pull指示

### PyPI発布エラー
- GitHub Actions失敗 → ログ確認指示
- PyPI発布失敗 → 手動対応手順提示
- タイムアウト → 状況確認と次ステップ提示

### マージエラー
- コンフリクト発生 → 解決手順提示
- プッシュ失敗 → 権限確認指示

## 成功基準

1. ✅ Release分岐が正常に作成された
2. ✅ バージョンファイルが正しく更新された
3. ✅ PyPI発布が成功した
4. ✅ Main分岐にマージされタグが作成された
5. ✅ Develop分岐にマージされた
6. ✅ GitHub Releaseが作成された
7. ✅ Release分岐が削除された

## 注意事項

- **PyPI優先戦略**: パッケージ発布成功後にmain分岐を更新
- **自動化依存**: GitHub Actionsのrelease-automation.ymlに依存
- **品質保証**: テスト実行とカバレッジ確認が必須
- **文書同期**: 多言語README更新が必要
- **タグ管理**: セマンティックバージョニング準拠

このコマンドはGITFLOW_zh.mdで定義されたリリースプロセスを完全自動化し、PyPI優先戦略により安全で確実なリリースを実現します。