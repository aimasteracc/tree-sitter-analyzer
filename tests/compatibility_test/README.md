# Tree-sitter Analyzer 互換性テストシステム

## 🎯 プロジェクト概要

Tree-sitter Analyzer互換性テストシステムは、**エンタープライズ品質**のコード分析ツールの異なるバージョン間の互換性を検証するための包括的なテストフレームワークです。現在のバージョン（v1.9.2）と過去のバージョン（v1.6.1等）間の機能互換性、パフォーマンス、出力形式の一貫性を自動的に検証します。

### 🌟 主要特徴

- **🎨 色付きログシステム**: エラーレベル別色分け（ERROR/WARNING/INFO/SUCCESS/DEBUG）
- **📊 進捗表示**: リアルタイムプログレスバーと完了率表示
- **🔧 外部設定管理**: JSONベースのテストケース設定
- **🚀 uvベース軽量実行**: 高速で軽量な実行環境
- **📈 統合レポート**: MCPとCLIの結果を統合した包括的評価
- **🔍 詳細比較**: WinMerge統合による詳細差分確認

## 🏗️ システム構成

### アーキテクチャ概要

```
tests/compatibility_test/
├── 🎯 テスト実行エンジン
│   ├── mcp_test_direct.py      # MCPサーバー直接テスト（20ケース + 3エラーケース）
│   ├── cli_test.py             # CLIコマンドテスト（20ケース + 4エラーケース）
│   └── colored_logger.py       # 色付きログシステム
├── 📋 設定・データ管理
│   ├── config.json             # システム設定
│   ├── mcp_test_cases.json     # MCPテストケース定義
│   ├── cli_test_cases.json     # CLIテストケース定義
│   └── test_case_loader.py     # テストケースローダー
├── 📊 分析・レポート
│   ├── compare_mcp.py          # MCP結果比較
│   ├── compare_cli.py          # CLI結果比較
│   └── unified_report.py       # 統合レポート生成
├── 🔧 ユーティリティ
│   ├── mcp_client.py           # MCPクライアント
│   ├── config_manager.py       # 設定管理
│   └── utils.py                # 共通ユーティリティ
└── 📁 結果保存
    ├── result/                 # テスト結果（自動生成）
    ├── comparison/             # 比較レポート（自動生成）
    └── unified_report/         # 統合レポート（自動生成）
```

### 🛠️ 技術スタック

- **実行環境**: Python 3.10+ + uv（軽量パッケージマネージャー）
- **コア技術**: tree-sitter, MCP (Model Context Protocol), asyncio
- **テスト対象**: 7つのMCPツール + 4つのCLIコマンド
- **出力形式**: JSON, HTML, CSV, テキスト
- **ログシステム**: colorama（Windows ANSI対応）

## 📦 インストールと設定

### 前提条件

- Python 3.10以上
- uv パッケージマネージャー
- tree-sitter-analyzer v1.9.2（現在）またはv1.6.1（比較対象）

### 🚀 クイックスタート

```bash
# 1. プロジェクトルートに移動
cd c:/git-public/tree-sitter-analyzer

# 2. テストディレクトリに移動
cd tests/compatibility_test

# 3. 依存関係の確認（uvが自動的に管理）
uv run python --version

# 4. 基本テスト実行
uv run python mcp_test_direct.py --version current
uv run python cli_test.py --version current 
uv run python compare_mcp.py --version1 current --version2 1.6.1
uv run python compare_cli.py current 1.6.1
uv run python unified_report.py current 1.6.1
```
### 📋 設定ファイル

#### config.json - システム設定
```json
{
  "test_settings": {
    "timeout": 30,
    "max_retries": 3,
    "log_level": "INFO",
    "output_formats": ["json", "html"],
    "enable_performance_logging": true
  },
  "comparison_settings": {
    "tolerance": 0.001,
    "ignore_timestamps": true,
    "compatibility_thresholds": {
      "excellent": 0.95,
      "good": 0.90,
      "acceptable": 0.80,
      "poor": 0.70
    }
  }
}
```

## 🎯 実行方法（詳細）

### 1. 🔄 MCPテスト実行

MCPサーバーを直接初期化して全ツールをテストします。

```bash
# 基本実行（全20テストケース + 3エラーケース）
uv run python mcp_test_direct.py

# カテゴリ別実行
uv run python mcp_test_direct.py --categories analysis structure
uv run python mcp_test_direct.py --categories search query

# ツール指定実行
uv run python mcp_test_direct.py --tools check_code_scale analyze_code_structure

# 特定テストID実行
uv run python mcp_test_direct.py --test-ids MCP-001 MCP-002

# 詳細ログ出力
uv run python mcp_test_direct.py --verbose

# 色付きログを無効化
uv run python mcp_test_direct.py --no-color
```

#### MCPテストケース（20個 + 3エラーケース）

| カテゴリ | ツール | テスト数 | 説明 |
|----------|--------|----------|------|
| analysis | check_code_scale | 2 | コードスケール・複雑度分析 |
| structure | analyze_code_structure | 3 | コード構造分析・表形式出力 |
| extraction | extract_code_section | 2 | コード部分抽出 |
| query | query_code | 3 | tree-sitterクエリ実行 |
| search | list_files, search_content, find_and_grep | 9 | ファイル・コンテンツ検索 |
| project | set_project_path | 1 | プロジェクト設定 |
| error | - | 3 | エラーハンドリング |

### 2. 🎨 CLIテスト実行

CLIコマンドを直接実行してテストします。

```bash
# 基本実行（全20テストケース + 4エラーケース）
uv run python cli_test.py

# カテゴリ別実行
uv run python cli_test.py --categories basic table
uv run python cli_test.py --categories query info

# 特定テストID実行
uv run python cli_test.py --test-ids CLI-001-summary CLI-002-structure

# エラーテストを除外
uv run python cli_test.py --no-errors

# 利用可能なカテゴリ表示
uv run python cli_test.py --list-categories

# 詳細ログ出力
uv run python cli_test.py --verbose
```

#### CLIテストケース（20個 + 4エラーケース）

| カテゴリ | テスト数 | 説明 |
|----------|----------|------|
| basic | 3 | 基本機能（summary, structure, advanced） |
| table | 4 | テーブル出力形式（full, compact, csv, json） |
| partial | 2 | 部分読み取り機能 |
| query | 3 | クエリ実行（methods, classes, fields） |
| info | 3 | 情報表示（help, list-queries, supported-languages） |
| multi_file | 5 | 多言語ファイル対応 |
| error | 4 | エラーハンドリング |

### 3. 📊 バージョン比較テスト

異なるバージョン間の互換性を比較します。

```bash
# v-current（1.9.2）とv-1.6.1の比較
# 1. 各バージョンでテスト実行
uv run python mcp_test_direct.py --version 1.9.2
uv run python mcp_test_direct.py --version 1.6.1
uv run python cli_test.py --version 1.9.2
uv run python cli_test.py --version 1.6.1

# 2. 比較レポート生成
uv run python compare_mcp.py --version1 1.9.2 --version2 1.6.1
uv run python compare_cli.py 1.9.2 1.6.1

# 3. 統合レポート生成
uv run python unified_report.py 1.9.2 1.6.1
```

### 4. 🔍 情報表示・確認

```bash
# 利用可能なカテゴリ表示
uv run python cli_test.py --list-categories
uv run python mcp_test_direct.py --list-categories

# 利用可能なテストケース表示
uv run python cli_test.py --list-tests
uv run python mcp_test_direct.py --list-tests

# テストケース設定の妥当性確認
uv run python test_case_loader.py

# 色付きログシステムの動作確認
uv run python colored_logger.py
```

## 📈 テスト結果の解釈

### 🎯 互換性評価基準

| レベル | 互換性率 | 評価 | 推奨アクション |
|--------|----------|------|----------------|
| **Excellent** | 95%以上 | 🟢 高い互換性 | 安全にアップグレード可能 |
| **Good** | 90-94% | 🔵 良好な互換性 | 軽微な調整でアップグレード可能 |
| **Acceptable** | 80-89% | 🟡 一部非互換性 | 詳細な検証が必要 |
| **Poor** | 70-79% | 🟠 重要な非互換性 | 修正作業が必要 |
| **Critical** | 70%未満 | 🔴 重大な非互換性 | 大幅な修正が必要 |

### 📁 出力ファイル構造

```
result/
├── mcp/
│   ├── v-current/              # 現在バージョン（1.9.2）のMCPテスト結果
│   │   ├── MCP-001_result.json
│   │   ├── MCP-002_result.json
│   │   └── ...
│   └── v-1.6.1/               # 1.6.1バージョンのMCPテスト結果
│       ├── MCP-001_result.json
│       └── ...
├── cli/
│   ├── v-current/              # 現在バージョンのCLIテスト結果
│   │   ├── CLI-001-summary_result.json
│   │   └── ...
│   └── v-1.6.1/               # 1.6.1バージョンのCLIテスト結果
│       └── ...
comparison/
├── mcp_current_vs_1.6.1/      # MCP比較レポート
│   ├── comparison_report.html
│   ├── comparison_report.json
│   └── winmerge/              # WinMerge用テキストファイル
└── cli_current_vs_1.6.1/      # CLI比較レポート
    ├── comparison_report.html
    └── ...
unified_report/
└── current_vs_1.6.1/          # 統合レポート
    ├── unified_compatibility_report.html
    └── unified_compatibility_report.json
```

### 📊 レポート内容

#### 1. MCPテスト結果
- **成功率**: 各ツールの実行成功率
- **出力一貫性**: 同一入力に対する出力の一致度
- **パフォーマンス**: 実行時間の比較
- **エラーハンドリング**: エラーケースの適切な処理

#### 2. CLIテスト結果
- **コマンド互換性**: CLIオプションの互換性
- **出力フォーマット**: 各形式（JSON, CSV, HTML等）の一貫性
- **エラーメッセージ**: エラー時の適切なメッセージ表示

#### 3. 統合評価
- **重み付き評価**: MCP 70% + CLI 30%
- **カテゴリ別分析**: 機能カテゴリごとの詳細評価
- **推奨事項**: アップグレード時の注意点

## 🔧 トラブルシューティング

### よくある問題と解決方法

#### 1. 🚫 uvコマンドが見つからない
```bash
# uvをインストール
pip install uv

# または公式インストーラーを使用
curl -LsSf https://astral.sh/uv/install.sh | sh  # Linux/Mac
# Windows: https://astral.sh/uv/install.sh からダウンロード
```

#### 2. 📦 依存関係エラー
```bash
# 依存関係を同期
uv sync

# coloramaが見つからない場合
uv add colorama

# 全依存関係を再インストール
uv pip install -r requirements.txt
```

#### 3. 🔐 権限エラー
```bash
# Windows: 管理者権限でコマンドプロンプトを実行
# Linux/Mac: 仮想環境を使用
uv run python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

#### 4. 📁 パスエラー
```bash
# 正しいディレクトリから実行
cd tests/compatibility_test
pwd  # 現在のディレクトリを確認

# プロジェクトルートの確認
ls ../../  # pyproject.tomlが見えるはず
```

#### 5. 🎨 色付きログが表示されない
```bash
# coloramaが正しくインストールされているか確認
uv run python -c "import colorama; print('colorama OK')"

# Windows環境でANSIエスケープシーケンスが無効な場合
# Windows 10 1511以降では自動的に有効化されるはず
```

#### 6. 📋 テストケース設定ファイルエラー
```bash
# JSONファイルの構文チェック
uv run python -m json.tool cli_test_cases.json

# テストケースローダーの動作確認
uv run python test_case_loader.py
```

#### 7. 🔄 MCPサーバー接続エラー
```bash
# MCPサーバーが正常に起動するか確認
uv run python -m tree_sitter_analyzer.mcp.server

# プロジェクトルートの設定確認
uv run python mcp_test_direct.py --verbose
```

### 📝 ログファイル

- `compatibility_test.log`: 色付きログシステムのログ（ファイル出力は色なし）
- `cli_test.log`: CLIテスト専用ログ（従来形式）
- `result/cli/v-{version}/`: CLIテスト結果ファイル
- `result/mcp/v-{version}/`: MCPテスト結果ファイル

### 🐛 デバッグ方法

```bash
# 詳細ログ出力でデバッグ
uv run python cli_test.py --verbose

# 特定のテストケースのみ実行してデバッグ
uv run python cli_test.py --test-ids CLI-001-summary --verbose

# テストケース設定の妥当性確認
uv run python test_case_loader.py

# 色付きログシステムの動作確認
uv run python colored_logger.py
```

### 💡 パフォーマンス最適化

```bash
# エラーテストを除外して高速実行
uv run python cli_test.py --no-errors

# 基本カテゴリのみで高速チェック
uv run python cli_test.py --categories basic

# 並列実行（将来の機能）
# uv run python cli_test.py --parallel
```

## 🚀 完全テスト実行手順

### Phase 1: 環境準備
```bash
cd tests/compatibility_test
uv sync  # 依存関係の同期
```

### Phase 2: 現在バージョン（v1.9.2）テスト実行
```bash
# MCPテスト実行
uv run python mcp_test_direct.py --verbose

# CLIテスト実行
uv run python cli_test.py --verbose
```

### Phase 3: v-1.6.1テスト実行
```bash
# v-1.6.1環境でのMCPテスト
uv run python mcp_test_direct.py --version 1.6.1 --verbose

# v-1.6.1環境でのCLIテスト
uv run python cli_test.py --version 1.6.1 --verbose
```

### Phase 4: 比較レポート生成
```bash
# MCP比較レポート
uv run python compare_mcp.py --version1 current --version2 1.6.1

# CLI比較レポート
uv run python compare_cli.py current 1.6.1

# 統合レポート
uv run python unified_report.py current 1.6.1
```

### Phase 5: 結果確認
```bash
# 生成されたレポートの確認
ls -la unified_report/current_vs_1.6.1/
ls -la comparison/
ls -la result/
```

## 🔮 今後の改善点

### 短期的改善（次のリリース）
1. **並列実行**: テスト実行時間の短縮
2. **CI/CD統合**: GitHub Actionsでの自動テスト
3. **メモリ使用量監視**: リソース消費の詳細分析
4. **カスタムテストケース**: ユーザー定義テストケースのサポート

### 中期的改善（今後6ヶ月）
1. **パフォーマンスベンチマーク**: 実行時間の詳細比較
2. **回帰テスト**: 自動的な回帰検出
3. **レポートダッシュボード**: Web UIでのリアルタイム監視
4. **多言語対応**: テストケースの国際化

### 長期的改善（今後1年）
1. **機械学習による異常検出**: AIを活用した品質評価
2. **クラウド統合**: AWS/Azure/GCPでの分散テスト
3. **エンタープライズ機能**: 大規模組織向けの機能拡張
4. **API統合**: 外部システムとの連携

## 📚 関連ドキュメント

- [`CONFIG_GUIDE.md`](CONFIG_GUIDE.md): 詳細な設定ガイド
- [`SIMPLE_VERSION_GUIDE.md`](SIMPLE_VERSION_GUIDE.md): 簡素化バージョン管理ガイド
- [`ARCHITECTURE_DIAGRAMS.md`](ARCHITECTURE_DIAGRAMS.md): システムアーキテクチャ図
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md): トラブルシューティングガイド
- [`../../docs/CONTRIBUTING.md`](../../docs/CONTRIBUTING.md): 貢献ガイド
- [`../../README.md`](../../README.md): プロジェクトメインドキュメント

### 📖 ドキュメント構成

| ドキュメント | 目的 | 対象読者 |
|-------------|------|----------|
| [`README.md`](README.md) | システム概要・使用方法 | 全ユーザー |
| [`CONFIG_GUIDE.md`](CONFIG_GUIDE.md) | 設定ファイル詳細 | 設定管理者 |
| [`SIMPLE_VERSION_GUIDE.md`](SIMPLE_VERSION_GUIDE.md) | バージョン管理 | 開発者 |
| [`ARCHITECTURE_DIAGRAMS.md`](ARCHITECTURE_DIAGRAMS.md) | システム設計 | 開発者・保守担当者 |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | 問題解決 | 全ユーザー |

## 🤝 貢献

このテストシステムの改善に貢献する場合：

1. **新しいテストケースの追加**: `*_test_cases.json`ファイルの拡張
2. **エラーハンドリングの改善**: より堅牢なエラー処理の実装
3. **パフォーマンスの最適化**: 実行速度の向上
4. **ドキュメントの更新**: 使いやすさの向上
5. **統合レポートシステムの機能拡張**: より詳細な分析機能

詳細は[`CONTRIBUTING.md`](../../docs/CONTRIBUTING.md)を参照してください。

---

**Tree-sitter Analyzer 互換性テストシステム**
現在のバージョン: v1.9.2
© 2024 aisheng.yu. MIT License.
