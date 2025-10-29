# エンコーディング検索互換性修正

## なぜ

search_contentツールはShift_JISエンコードされたファイル内の日本語テキストを見つけることができませんが、extract_code_sectionツールは同じコンテンツを正常に読み取ります。この不整合により、ユーザー体験が悪化し、国際的なコードベースでのツールの有効性が制限されています。

**現在の問題:**
- `extract_code_section`は`examples/encoding.txt`（Shift_JIS）から日本語テキストを正常に読み取る
- `search_content`は同じファイルで日本語テキスト「これは」に対して0件のマッチを返す
- ユーザーはエンコーディングパラメータを手動で指定する必要があり、エラーが発生しやすい

**根本原因:**
- `extract_code_section`は`EncodingManager`による自動エンコーディング検出を使用
- `search_content`は手動エンコーディング指定でripgrepに依存
- 検索ワークフローに自動エンコーディング検出統合が不足

## 変更内容

- **自動エンコーディング検出の追加** - ripgrep実行前にsearch_contentツールに追加
- **EncodingManagerの統合** - ツール間で一貫したエンコーディング処理
- **エンコーディングフォールバック戦略の強化** - ripgrepがデフォルトエンコーディングで失敗した場合
- **後方互換性の維持** - 既存のencodingパラメータの動作は変更なし
- **包括的テストカバレッジの追加** - マルチエンコーディング検索シナリオ用

## 影響

- **影響を受ける仕様**: mcp-tools（search_contentツールの拡張）
- **影響を受けるコード**:
  - `tree_sitter_analyzer/mcp/tools/search_content_tool.py`
  - `tree_sitter_analyzer/mcp/tools/fd_rg_utils.py`
  - エンコーディング互換性用テストファイル
- **破壊的変更**: なし - 純粋に追加的な拡張
- **パフォーマンスへの影響**: 最小限 - 必要時のみエンコーディング検出
- **ユーザー体験**: 国際的なコードベースで大幅に改善
