# Analysis Results

このディレクトリは、`speckit.analyze`やその他の分析ツールによる**恒久的な分析結果**を保存するためのディレクトリです。

## 目的

- プロジェクトのアーキテクチャ分析結果
- 依存関係の分析レポート
- コード品質メトリクス
- パフォーマンス分析結果
- セキュリティ監査結果

## ファイル命名規則

- `architecture_overview.md` - アーキテクチャの全体像
- `dependency_analysis.md` - 依存関係の分析
- `code_metrics_YYYY-MM-DD.md` - 日付付きのコードメトリクス
- `performance_report_vX.X.X.md` - バージョン別パフォーマンスレポート
- `speckit_analysis_YYYY-MM-DD.md` - speckit.analyze包括的分析レポート
- `project_metrics_YYYY-MM-DD.md` - プロジェクトスケール評価レポート

## 📊 分析履歴

### 2025年10月
- **[speckit.analyze 包括的分析レポート](./speckit_analysis_2025-10-16.md)** (2025-10-16)
  - プロジェクト全体の包括的分析
  - 技術的負債の詳細評価
  - 戦略的改善ロードマップ
  - 総合評価: B+ (良好) → A- (優秀)への道筋

- **[プロジェクトメトリクス評価](./project_metrics_2025-10-16.md)** (2025-10-16)
  - 定量的メトリクス収集
  - コードベース規模分析
  - 品質指標測定
  - パフォーマンス評価

## 一時的な分析結果について

一時的なバグ修正やリファクタリングに関する分析結果は、`.specify/`や`.temp/analysis/`ディレクトリに保存してください。これらは`.gitignore`で除外されており、作業完了後に削除されます。

## 関連ドキュメント

- [仕様書](../../specs/) - プロジェクトの機能仕様
- [API文書](../api/) - API仕様書
- [開発者ガイド](../developer_guide.md) - 開発者向けガイド