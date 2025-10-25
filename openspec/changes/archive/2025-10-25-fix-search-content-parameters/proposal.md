## Why

search_contentツールにおいて以下の重要な問題が発生している：

1. **出力形式パラメータの競合**: `total_only`、`count_only_matches`、`summary_only`、`group_by_file`、`optimize_paths`が同時指定可能で、予期しない動作を引き起こす
2. **max_count機能の不具合**: ripgrepコマンドでmax_countパラメータが正しく機能していない
3. **キャッシュ仕様の問題**: 出力形式パラメータを変更してもキャッシュされた結果が返され、期待した形式の結果が得られない

これらの問題はAIアシスタントがコード検索を行う際のユーザビリティと信頼性を著しく損なっている。

## What Changes

- **出力形式パラメータの排他制御**: 複数の出力形式フラグの同時指定を検証で阻止し、明確なエラーメッセージを提供
- **max_count機能の修正**: ripgrepコマンド構築時の`-m`オプション適用を修正し、期待通りに動作させる  
- **キャッシュキー生成の改善**: 出力形式パラメータを含む適切なキャッシュキー生成により、形式変更時に正しい結果を返す
- **包括的なテストスイートの作成**: TDD開発により全ての修正をテストでカバーし、技術負債を防止

## Impact

- 影響を受ける仕様: mcp-tools (新規capability)
- 影響を受けるコード: 
  - `tree_sitter_analyzer/mcp/tools/search_content_tool.py`
  - `tree_sitter_analyzer/mcp/tools/fd_rg_utils.py`
  - `tree_sitter_analyzer/mcp/utils/search_cache.py`
  - テストファイル: `tests/test_search_content_parameters_fix.py` (新規)
- 破壊的変更: なし（後方互換性維持）
- パフォーマンス向上: キャッシュ効率改善によりレスポンス時間短縮