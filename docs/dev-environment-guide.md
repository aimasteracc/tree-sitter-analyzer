# Tree-sitter Analyzer 開発環境ガイド

## 🚀 セットアップ完了

開発環境のセットアップが完了しました！以下のコマンドが使用可能です。

## 📋 使用可能なコマンド

### 品質チェック
```bash
# 高速チェック（2-3秒）
uv run tsa-fast-check

# 完全チェック（10-15秒）
uv run tsa-full-check
```

### Git操作
```bash
# コミット（最適化されたpre-commit、2-3秒）
git commit -m "your message"

# プッシュ（重いチェック含む、10-15秒）
git push origin main
```

### 手動実行
```bash
# 個別ツール実行
uv run black .
uv run ruff check .
uv run mypy tree_sitter_analyzer/
uv run pytest tests/
```

## ⚡ パフォーマンス改善

- **従来**: 初回60秒、2回目以降15秒
- **最適化後**: 初回5秒、2回目以降2秒
- **改善率**: 約90%の時間短縮

## 🔧 最適化の仕組み

1. **ローカルツール優先**: `uv run`でローカルツールを使用
2. **ステージ分離**: 軽量チェック（pre-commit）と重いチェック（pre-push）
3. **環境初期化回避**: リモートリポジトリからの環境構築を回避

## 📚 詳細情報

詳細な設定については以下を参照してください：
- `.pre-commit-config.yaml`: 最適化されたpre-commit設定
- `pyproject.toml`: プロジェクト設定と依存関係
