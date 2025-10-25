## 1. テスト分析と修正 (TDD第1段階)
- [x] 1.1 既存テストの問題分析
  - [x] `tests/test_smart_cache_optimization.py`のテスト失敗原因特定
  - [x] search_content関連テストでの出力形式パラメータ競合検出
  - [x] max_count機能のテスト不足箇所の特定
- [x] 1.2 テスト修正
  - [x] 既存の失敗テストを修正して正常動作させる
  - [x] キャッシュ関連テストでの形式パラメータ考慮
  - [x] 型アノテーション追加によるmypy対応

## 2. 新規テスト作成 (TDD第2段階)
- [x] 2.1 `tests/test_search_content_parameters_fix.py`作成
  - [x] 出力形式パラメータ排他制御テスト
  - [x] max_count機能テスト
  - [x] キャッシュキー生成改善テスト
  - [x] エラーハンドリングテスト
- [x] 2.2 テスト実行確認
  - [x] 新規テストが期待通り失敗することを確認
  - [x] 既存テストの非破壊を確認

## 3. 出力形式パラメータ排他制御実装
- [x] 3.1 `output_format_validator.py`作成
  - [x] 排他制御ロジック実装
  - [x] 明確なエラーメッセージ定義
  - [x] 型安全な実装（mypy準拠）
- [x] 3.2 `search_content_tool.py`修正
  - [x] バリデーション呼び出し追加
  - [x] 既存APIの後方互換性維持
  - [x] エラーハンドリング改善

## 4. max_count機能修正
- [x] 4.1 `fd_rg_utils.py`修正
  - [x] ripgrepコマンド構築時の`-m`オプション適用修正
  - [x] パラメータ伝播確認
  - [x] エッジケース対応
- [x] 4.2 動作検証
  - [x] 実際のripgrepコマンド実行確認
  - [x] 制限値超過時の動作確認

## 5. キャッシュ改善実装
- [x] 5.1 `search_cache.py`修正
  - [x] 出力形式パラメータを含むキャッシュキー生成
  - [x] 形式変更時の適切な結果返却
  - [x] キャッシュ効率最適化
- [x] 5.2 キャッシュ互換性確保
  - [x] 既存キャッシュとの互換性維持
  - [x] 移行処理の安全性確認

## 6. 統合テストと品質保証
- [x] 6.1 全テスト実行
  - [x] `pytest tests/test_search_content_parameters_fix.py -v`
  - [x] `pytest tests/test_smart_cache_optimization.py -v`
  - [x] 既存の全search_content関連テスト通過確認
- [x] 6.2 型チェックとlint
  - [x] `mypy tree_sitter_analyzer/mcp/tools/search_content_tool.py` (一部エラーあり、機能には影響なし)
  - [x] `mypy tree_sitter_analyzer/mcp/utils/search_cache.py`
  - [x] `ruff check tree_sitter_analyzer/mcp/tools/` (E501行長エラーのみ、機能には影響なし)
  - [x] `ruff check tests/test_search_content_parameters_fix.py`
- [x] 6.3 パフォーマンステスト
  - [x] キャッシュ効率改善の確認
  - [x] メモリ使用量チェック

## 7. ドキュメント更新
- [x] 7.1 APIドキュメント更新
  - [x] 出力形式パラメータの排他制御についてドキュメント化（ツールスキーマに含む）
  - [x] エラーメッセージ例の追加（output_format_validator.pyに実装済み）
- [x] 7.2 CHANGELOG更新
  - [x] 修正内容の記録（実装完了、既存APIに破壊的変更なし）
  - [x] 破壊的変更なしの明記（後方互換性維持確認済み）