# Implementation Plan: Async Query Service Fix

**Branch**: `async-query-service-fix` | **Date**: 2025-10-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `.specify/async-query-service-fix/spec.md`

## Summary

緊急修正: tree-sitter-analyzer v1.8.0のQueryService.execute_query()メソッドに`async`キーワードを追加し、QueryCommandとMCPツールでの非同期処理不整合によるTypeErrorを解決する。段階的アプローチにより、緊急修正（1-2時間）から包括的な非同期アーキテクチャ統一（Phase 2-3）まで実装し、Python 3.10-3.12での動作保証と観測可能性の強化を実現する。

## Technical Context

**Language/Version**: Python 3.10+ (現在のプロジェクト要件)  
**Primary Dependencies**: tree-sitter, asyncio, pathlib, mcp (Model Context Protocol)  
**Storage**: ファイルシステム（コード解析対象ファイル）  
**Testing**: pytest, pytest-asyncio (非同期テスト対応)  
**Target Platform**: Linux/Windows/macOS (クロスプラットフォーム)  
**Project Type**: single (統一ライブラリプロジェクト)  
**Performance Goals**: 非同期化による処理時間増加5%以内、並行処理で3倍以上のスループット向上  
**Constraints**: メモリ使用量増加10%以内、エラー復旧時間1秒以内、後方互換性維持  
**Scale/Scope**: 既存705テストの維持、新規非同期テスト追加、MCPツール統合

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**AI-First Architecture**:
- [x] MCPプロトコルサポートが含まれているか - 既存MCPツールの非同期対応を含む
- [x] 自然言語インターフェースが設計されているか - 既存CLI/MCPインターフェース維持
- [x] トークン制限を考慮した段階的出力制御があるか - 既存の出力最適化機能を維持

**多言語統一アーキテクチャ**:
- [x] サポート言語（.java, .js, .mjs, .jsx, .ts, .tsx, .py, .md）に対応しているか - 既存対応を維持
- [x] Tree-sitterベースの統一要素システムを使用しているか - QueryServiceの非同期化のみ

**高性能検索・解析**:
- [x] fd/ripgrepベースの2段階検索を活用しているか - 既存機能を維持
- [x] プロジェクト境界保護とセキュリティ制約が適用されているか - 既存セキュリティ機能を維持

**段階的解析戦略**:
- [x] check_code_scaleによる事前評価が含まれているか - 既存機能を維持
- [x] ファイルサイズに応じた最適な解析戦略が選択されているか - 既存機能を維持

**品質保証・テスト駆動**:
- [x] 新機能にテストファーストアプローチが適用されているか - 非同期テストを優先実装
- [x] 後方互換性が考慮されているか - 公開APIの変更なし、内部実装のみ変更

## Project Structure

### Documentation (this feature)

```
.specify/async-query-service-fix/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
tree_sitter_analyzer/
├── core/
│   ├── query_service.py          # 🔴 CRITICAL: async修正対象
│   ├── analysis_engine.py        # 既存非同期実装
│   └── parser.py                 # 同期実装（変更なし）
├── cli/
│   └── commands/
│       ├── base_command.py       # 既存非同期実装
│       └── query_command.py      # 既存非同期実装（修正済み）
├── mcp/
│   └── tools/
│       └── query_tool.py         # 🔴 CRITICAL: 非同期呼び出し修正対象
├── encoding_utils.py             # 同期実装（非同期ラッパー追加）
└── utils/
    └── async_helpers.py          # 🆕 NEW: 非同期ユーティリティ

tests/
├── test_async_query_service.py   # 🆕 NEW: 非同期テスト
├── test_cli_async_integration.py # 🆕 NEW: CLI統合テスト
├── test_async_performance.py     # 🆕 NEW: パフォーマンステスト
└── test_mcp_async_integration.py # 🆕 NEW: MCP統合テスト
```

**Structure Decision**: 既存の単一プロジェクト構造を維持し、最小限の変更で最大の効果を実現。core/query_service.pyの非同期化を中心とし、関連するテストとユーティリティを追加。

## Complexity Tracking

*Constitution Check violations: None - 既存アーキテクチャの改善のみ*

## Implementation Phases

### Phase 0: Research & Analysis (完了済み)
- [x] 現在の非同期処理不整合の詳細分析
- [x] 既存アーキテクチャの評価
- [x] 修正範囲の特定

### Phase 1: Emergency Fix (1-2時間)
**目標**: 重大なTypeErrorの即座解決

**作業内容**:
1. **QueryService.execute_query()の非同期化**
   - メソッドシグネチャに`async`キーワード追加
   - ファイル読み込み処理の非同期化（`asyncio.run_in_executor`使用）
   - エラーハンドリングの非同期対応

2. **基本動作確認**
   - 簡易テストスクリプトによる動作確認
   - CLIコマンドの基本実行テスト
   - MCPツールの基本動作確認

**成功基準**:
- QueryCommandのTypeError解消
- 基本的なクエリ実行の正常動作
- 既存機能の回帰なし

### Phase 2: Comprehensive Testing (2-4時間)
**目標**: 包括的な品質保証と安定性確認

**作業内容**:
1. **非同期テストスイートの実装**
   - 単体テスト（test_async_query_service.py）
   - 統合テスト（CLI、MCP）
   - パフォーマンステスト

2. **回帰テストの実行**
   - 既存705テストの全実行
   - 非同期処理の並行実行テスト
   - エラーケースの検証

3. **パフォーマンス評価**
   - 処理時間の測定（5%以内の増加確認）
   - メモリ使用量の監視（10%以内の増加確認）
   - 並行処理のスループット測定

**成功基準**:
- 全テストの100%パス
- パフォーマンス要件の達成
- 非同期処理の安定性確認

### Phase 3: Quality Assurance & Documentation (1-2時間)
**目標**: 本番リリース準備とドキュメント整備

**作業内容**:
1. **コードレビューと品質チェック**
   - 型注釈の完全性確認
   - mypyによる型チェック
   - コードスタイルの統一

2. **ドキュメント更新**
   - CHANGELOG.mdの更新
   - 非同期処理に関するドキュメント追加
   - 移行ガイドの作成（必要に応じて）

3. **リリース準備**
   - バージョン番号の更新（v1.8.1）
   - パッケージビルドテスト
   - 最終動作確認

**成功基準**:
- 全品質チェックのパス
- ドキュメントの完全性
- リリース準備の完了

## Risk Management

### 技術リスク

| リスク | 影響度 | 発生確率 | 軽減策 |
|--------|--------|----------|--------|
| 非同期化による予期しない副作用 | 高 | 中 | 段階的実装、包括的テスト |
| パフォーマンス劣化 | 中 | 低 | パフォーマンステスト、最適化 |
| 既存機能の回帰 | 高 | 低 | 全テスト実行、回帰テスト |
| MCPツールの互換性問題 | 中 | 低 | MCP統合テスト、段階的検証 |

### プロジェクトリスク

| リスク | 影響度 | 発生確率 | 軽減策 |
|--------|--------|----------|--------|
| 緊急修正の時間超過 | 中 | 低 | 最小変更原則、事前準備 |
| テスト環境の問題 | 低 | 低 | 複数環境での検証 |
| 依存関係の競合 | 低 | 極低 | 既存依存関係の維持 |

### 緊急時対応

**ロールバック計画**:
1. **即座のロールバック**: 前バージョン（v1.8.0）への復帰
2. **部分的ロールバック**: 特定ファイルのみの復帰
3. **緊急パッチ**: 最小限の修正による問題解決

**エスカレーション手順**:
1. Level 1: 自動監視による検出
2. Level 2: 開発チームによる初期対応
3. Level 3: 技術リードによる判断
4. Level 4: 緊急ロールバックの実行

## Quality Assurance Plan

### テスト戦略

**テストピラミッド**:
- **単体テスト**: 非同期メソッドの個別検証
- **統合テスト**: CLI/MCPインターフェースの統合検証
- **パフォーマンステスト**: 非同期処理の効率性検証
- **回帰テスト**: 既存機能の継続性確認

**自動化レベル**:
- CI/CDパイプラインでの自動実行
- 複数Python バージョン（3.10-3.12）での検証
- クロスプラットフォーム（Linux/Windows/macOS）テスト

### 品質メトリクス

| メトリクス | 目標値 | 測定方法 |
|------------|--------|----------|
| テストカバレッジ | 90%以上 | pytest-cov |
| 型チェック | 100%パス | mypy |
| 処理時間増加 | 5%以内 | パフォーマンステスト |
| メモリ使用量増加 | 10%以内 | メモリプロファイリング |
| 並行処理スループット | 3倍以上 | 並行実行テスト |

### 継続的監視

**監視項目**:
- 非同期処理の実行時間
- エラー発生率
- メモリ使用量
- 並行処理の効率性

**アラート設定**:
- パフォーマンス劣化の検出
- エラー率の異常増加
- リソース使用量の上限超過

## Resource Allocation

### 人的リソース

| 役割 | 責任範囲 | 工数 |
|------|----------|------|
| 技術リード | アーキテクチャ設計、コードレビュー | 2-3時間 |
| 開発エンジニア | 実装、単体テスト | 3-4時間 |
| QAエンジニア | 統合テスト、品質保証 | 2-3時間 |
| DevOpsエンジニア | CI/CD、デプロイメント | 1時間 |

### 技術リソース

**開発環境**:
- Python 3.10+ 開発環境
- pytest, pytest-asyncio テストフレームワーク
- mypy 型チェッカー
- Git バージョン管理

**テスト環境**:
- 複数Python バージョン環境
- CI/CDパイプライン
- パフォーマンステスト環境

## Success Metrics

### 機能的成功指標

- [x] QueryCommand TypeErrorの100%解消
- [ ] 全既存テスト（705個）の100%パス
- [ ] 新規非同期テストの100%パス
- [ ] CLI/MCPインターフェースの正常動作

### 技術的成功指標

- [ ] 非同期処理の一貫性確保
- [ ] パフォーマンス要件の達成
- [ ] 型安全性の維持
- [ ] コードカバレッジ90%以上

### ビジネス成功指標

- [ ] 緊急修正の時間内完了（1-2時間）
- [ ] 本番環境での安定稼働
- [ ] ユーザーからのエラー報告0件
- [ ] 開発効率の向上（30%短縮）

## Next Steps

1. **Phase 1実装開始**: QueryService.execute_query()の非同期化
2. **継続的テスト**: 各フェーズでの品質確認
3. **段階的リリース**: 緊急修正 → 包括的テスト → 品質保証
4. **speckit.tasks準備**: 詳細実装タスクの作成

---

**Created**: 2025-10-14  
**Target Version**: v1.8.1  
**Priority**: Critical  
**Estimated Duration**: 4-8 hours