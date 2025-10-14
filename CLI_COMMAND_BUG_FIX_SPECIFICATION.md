# CLI Command関連パラメータ不具合修正仕様書

## 1. 概要

本仕様書は、tree-sitter-analyzer v1.8.0（developブランチ）で発生している非同期処理の不整合による重大な不具合の修正方針を定義します。

## 2. 問題の詳細分析

### 2.1 重大不具合: 非同期処理の不整合

**影響範囲**: `QueryCommand`クラス全体
**重要度**: 🔴 Critical（アプリケーションクラッシュ）

#### 根本原因
- **`QueryService.execute_query()`**: 同期メソッド（`async`キーワードなし）
- **`QueryCommand.execute_query()`**: 非同期メソッド（`async`キーワードあり）
- **呼び出し箇所**: `await self.query_service.execute_query()`で同期メソッドを非同期呼び出し

#### 具体的な問題箇所

**ファイル**: `tree_sitter_analyzer/core/query_service.py`
```python
# 行33-40: asyncキーワードが欠如
def execute_query(  # ← async が必要
    self,
    file_path: str,
    language: str,
    query_key: str | None = None,
    query_string: str | None = None,
    filter_expression: str | None = None,
) -> list[dict[str, Any]] | None:
```

**ファイル**: `tree_sitter_analyzer/cli/commands/query_command.py`
```python
# 行31, 39: 同期メソッドをawaitで呼び出し
results = await self.query_service.execute_query(  # ← TypeError発生
    self.args.file_path,
    language,
    query_key=query_name,
    filter_expression=filter_expression,
)
```

### 2.2 既知の修正済み不具合（emergency-backup-html-crisis-20251012ブランチ）

#### 2.2.1 クエリキー + テーブル形式出力の組み合わせ不具合
- **状況**: developブランチで修正済み
- **原因**: `_convert_query_results_to_analysis`メソッドの実装問題

#### 2.2.2 メタデータの不正確な表示
- **状況**: developブランチで部分改善
- **残存問題**: 軽微な表示問題

#### 2.2.3 出力形式による動作の不整合
- **状況**: developブランチで修正済み

## 3. 修正方針と技術的アプローチ

### 3.1 緊急修正戦略

#### 優先度1: 非同期処理の一貫性確保
1. **`QueryService.execute_query()`を非同期化**
   - メソッドに`async`キーワードを追加
   - 内部の同期処理を非同期対応に変更

2. **依存関係の非同期対応**
   - `read_file_safe()`の非同期版への置き換え
   - `parser.parse_code()`の非同期対応確認

#### 優先度2: 一貫性のあるエラーハンドリング
- 非同期処理でのエラーハンドリングの統一
- タイムアウト処理の追加

### 3.2 最小変更原則

#### 変更対象ファイル
1. `tree_sitter_analyzer/core/query_service.py`
2. 必要に応じて依存する同期処理モジュール

#### 変更対象外
- `QueryCommand`クラス（既に正しく非同期実装済み）
- `BaseCommand`クラス（既に正しく非同期実装済み）
- `TableCommand`クラス（問題なし）

## 4. 影響範囲の評価

### 4.1 直接影響
- **CLI Commands**: `QueryCommand`の全機能
- **MCP Tools**: `query_tool.py`の`QueryService`利用箇所

### 4.2 間接影響
- **テスト**: 非同期テストケースの追加が必要
- **パフォーマンス**: 非同期化によるわずかなオーバーヘッド

### 4.3 破壊的変更の回避
- 公開APIの変更なし
- 既存の呼び出し元は`await`を使用済みのため互換性維持

## 5. 実装計画

### 5.1 段階的修正アプローチ

#### フェーズ1: 緊急修正（1-2時間）
1. `QueryService.execute_query()`の非同期化
2. 基本的な動作確認テスト
3. 緊急リリース準備

#### フェーズ2: 包括的テスト（2-4時間）
1. 非同期処理の統合テスト
2. 回帰テストの実行
3. パフォーマンステスト

#### フェーズ3: 品質保証（1-2時間）
1. コードレビュー
2. ドキュメント更新
3. 最終リリース

### 5.2 リスク軽減策

#### 開発環境での検証
- 複数のファイル形式でのテスト
- 異なるクエリタイプでのテスト
- エラーケースでのテスト

#### ロールバック計画
- 修正前のコミットハッシュの記録
- 緊急時の即座のロールバック手順

## 6. 品質保証要件

### 6.1 必須テストケース

#### 機能テスト
- [ ] 基本的なクエリ実行
- [ ] カスタムクエリ実行
- [ ] フィルター機能
- [ ] エラーハンドリング

#### 非同期処理テスト
- [ ] 並行クエリ実行
- [ ] タイムアウト処理
- [ ] 例外処理

#### 回帰テスト
- [ ] 既存の全CLIコマンド
- [ ] MCPツールの動作確認
- [ ] 出力形式の一貫性

### 6.2 パフォーマンス要件
- 非同期化による処理時間の増加: 5%以内
- メモリ使用量の増加: 10%以内

## 7. 成功基準

### 7.1 機能的成功基準
- [ ] `QueryCommand`のクラッシュが解消
- [ ] 全ての既存機能が正常動作
- [ ] 新しい非同期処理が安定動作

### 7.2 技術的成功基準
- [ ] コードの一貫性が向上
- [ ] エラーハンドリングが改善
- [ ] 将来の拡張性が確保

## 8. 次のステップ

1. **即座の対応**: 本仕様書に基づく緊急修正の実装
2. **中期対応**: 非同期処理アーキテクチャの全体的な見直し
3. **長期対応**: 類似問題の予防システムの構築

---

**作成日**: 2025-10-14  
**対象バージョン**: v1.8.0 (develop branch)  
**重要度**: Critical  
**推定修正時間**: 4-8時間