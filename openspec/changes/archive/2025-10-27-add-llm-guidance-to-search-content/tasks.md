## 1. ツール定義のdescription拡張

- [x] 1.1 search_content_tool.pyのget_tool_definition()修正
  - [x] 1.1.1 description冒頭に効率性ガイドセクション追加
    - [x] `⚠️ IMPORTANT: Token Efficiency Guide`セクション
    - [x] `🎯 RECOMMENDED WORKFLOW`セクション（段階的フロー）
    - [x] `💡 TOKEN EFFICIENCY COMPARISON`セクション（比較表）
  - [x] 1.1.2 既存のdescriptionを再構成
    - [x] 重要情報を先頭に移動
    - [x] セクションを明確に区切る
    - [x] 可読性を向上させる

- [x] 1.2 パラメータdescriptionの強化
  - [x] 1.2.1 total_onlyパラメータの説明拡張
    - [x] 効率性順位の追加（「最も効率的 ~10 tokens」）
    - [x] 推奨シナリオの追加（「件数確認、フィルタリング」）
    - [x] 排他性警告の追加（「⚠️ EXCLUSIVE」マーカー）
    - [x] 優先順位の明示（「Takes priority over all other formats」）
  - [x] 1.2.2 count_only_matchesパラメータの説明拡張
    - [x] 効率性順位の追加（「~50-200 tokens」）
    - [x] 推奨シナリオの追加（「ファイル分布の理解」）
    - [x] 排他性警告の追加
  - [x] 1.2.3 summary_onlyパラメータの説明拡張
    - [x] 効率性順位の追加（「~500-2000 tokens」）
    - [x] 推奨シナリオの追加（「初期調査、スコープ確認」）
    - [x] 排他性警告の追加
  - [x] 1.2.4 group_by_fileパラメータの説明拡張
    - [x] 効率性順位の追加（「~2000-10000 tokens」）
    - [x] 推奨シナリオの追加（「コンテキストでのレビュー」）
    - [x] 排他性警告の追加
  - [x] 1.2.5 optimize_pathsパラメータの説明拡張
    - [x] 効率性順位の追加（「10-30%削減」）
    - [x] 推奨シナリオの追加（「深いディレクトリ構造」）
    - [x] 排他性警告の追加

## 2. エラーメッセージの多言語化

- [x] 2.1 output_format_validator.pyの修正
  - [x] 2.1.1 エラーメッセージの英語版作成
    - [x] 競合パラメータの明示
    - [x] 正しい使用例の提示
    - [x] フォーマットの統一
  - [x] 2.1.2 エラーメッセージの日本語版作成
    - [x] 既存メッセージの強化
    - [x] 使用例の追加
    - [x] 英語版との一貫性確保
  - [x] 2.1.3 言語選択ロジックの実装（オプション）
    - [x] ロケール検出
    - [x] デフォルト言語設定
    - [x] フォールバック処理

## 3. テストの作成と更新

- [x] 3.1 新規テストファイルの作成
  - [x] 3.1.1 `tests/test_llm_guidance_compliance.py`作成
    - [x] ツール定義の構造検証テスト
    - [x] 必須セクションの存在確認テスト
    - [x] パラメータdescriptionの完全性テスト
    - [x] マーカー（⚠️、🎯、💡）の存在確認テスト
  - [x] 3.1.2 `tests/test_search_content_description.py`作成
    - [x] description長の妥当性テスト
    - [x] セクション構造の検証テスト
    - [x] トークンコスト比較表の検証テスト
    - [x] ワークフロー説明の検証テスト

- [x] 3.2 既存テストの更新
  - [x] 3.2.1 `tests/test_search_content_parameters_fix.py`の更新
    - [x] エラーメッセージの多言語化テスト追加
    - [x] 英語メッセージの検証
    - [x] 日本語メッセージの検証
  - [x] 3.2.2 後方互換性テストの追加
    - [x] 既存パラメータの動作確認
    - [x] レスポンス形式の不変性確認
    - [x] エラー発生条件の一貫性確認

## 4. ドキュメントの更新

- [x] 4.1 Rooルールへの追加
  - [x] 4.1.1 `.roo/rules/search-best-practices.md`作成
    - [x] トークン効率的な検索戦略の説明
    - [x] 段階的情報取得フローの記載
    - [x] 出力形式選択ガイドラインの追加
    - [x] よくある間違いと解決策のリスト
  - [x] 4.1.2 既存ルールファイルの更新
    - [x] `specify-rules.md`への追記
    - [x] ベストプラクティスの統合

- [x] 4.2 プロジェクトドキュメントの更新
  - [x] 4.2.1 `README.md`の更新
    - [x] Token-Efficient Search Strategiesセクション追加
    - [x] Output Format Selection Guideセクション追加
    - [x] 使用例の追加
  - [x] 4.2.2 `docs/mcp_fd_rg_design.md`の更新
    - [x] LLMガイダンス設計の追加
    - [x] トークン効率性の考慮事項追加
  - [x] 4.2.3 `MCP_SETUP_USERS.md`の更新
    - [x] search_content使用のベストプラクティス追加
    - [x] 効率的な検索パターンの例示

## 5. コード品質とバリデーション

- [x] 5.1 型チェック
  - [x] 5.1.1 `mypy tree_sitter_analyzer/mcp/tools/search_content_tool.py --strict`
  - [x] 5.1.2 `mypy tree_sitter_analyzer/mcp/tools/output_format_validator.py --strict`
  - [x] 5.1.3 型エラーの修正

- [x] 5.2 コードスタイルチェック
  - [x] 5.2.1 `ruff check tree_sitter_analyzer/mcp/tools/`
  - [x] 5.2.2 `black tree_sitter_analyzer/mcp/tools/` (フォーマット)
  - [x] 5.2.3 lintエラーの修正

- [x] 5.3 テスト実行
  - [x] 5.3.1 新規テストの実行と通過確認
  - [x] 5.3.2 既存テストの非破壊確認
  - [x] 5.3.3 カバレッジ確認（90%以上維持）

## 6. OpenSpec validation

- [x] 6.1 仕様検証
  - [x] 6.1.1 `openspec validate add-llm-guidance-to-search-content --strict`
  - [x] 6.1.2 検証エラーの修正
  - [x] 6.1.3 シナリオの完全性確認

- [x] 6.2 仕様の一貫性確認
  - [x] 6.2.1 llm-guidanceとmcp-toolsの整合性チェック
  - [x] 6.2.2 要件の重複や矛盾の解消
  - [x] 6.2.3 シナリオ例の実行可能性確認

## 7. 統合テストと品質保証

- [x] 7.1 E2Eテスト
  - [x] 7.1.1 LLMによるツール使用シミュレーション
  - [x] 7.1.2 段階的フローの実行確認
  - [x] 7.1.3 エラーハンドリングの確認

- [x] 7.2 パフォーマンステスト
  - [x] 7.2.1 descriptionサイズの測定（トークン数）
  - [x] 7.2.2 ツール定義の読み込み時間測定
  - [x] 7.2.3 パフォーマンスへの影響評価

- [x] 7.3 ユーザビリティテスト
  - [x] 7.3.1 LLMがガイダンスに従えるか確認
  - [x] 7.3.2 エラーメッセージの分かりやすさ確認
  - [x] 7.3.3 改善前後の比較分析

## 8. デプロイ前最終チェック

- [x] 8.1 後方互換性の最終確認
  - [x] 8.1.1 既存コードでの動作確認
  - [x] 8.1.2 APIレスポンス形式の不変性確認
  - [x] 8.1.3 エラー条件の一貫性確認

- [x] 8.2 ドキュメントの最終レビュー
  - [x] 8.2.1 全ドキュメントの整合性確認
  - [x] 8.2.2 リンク切れチェック
  - [x] 8.2.3 typoと文法チェック

- [x] 8.3 changelogの更新
  - [x] 8.3.1 `CHANGELOG.md`に変更内容を記録
  - [x] 8.3.2 破壊的変更なしの明記
  - [x] 8.3.3 改善効果の数値化（可能な場合）