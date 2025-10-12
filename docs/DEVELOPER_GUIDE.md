# 🚀 Tree-sitter Analyzer 開発者向け統合ガイド

> **プロジェクトの全体像を理解し、効率的な開発を始めるための包括的ガイド**

## 📋 目次

- [1. 🎯 このガイドについて](#1--このガイドについて)
- [2. 🏗️ プロジェクト概要](#2-️-プロジェクト概要)
- [3. 🚀 開発環境セットアップ](#3--開発環境セットアップ)
- [4. 📁 プロジェクト構造理解](#4--プロジェクト構造理解)
- [5. 🔧 開発ワークフロー](#5--開発ワークフロー)
- [6. 🧪 テストとQA](#6--テストとqa)
- [7. 📚 重要なリソース](#7--重要なリソース)
- [8. 🤝 コントリビューション](#8--コントリビューション)

---

## 1. 🎯 このガイドについて

### 対象読者
- **新規開発者**: プロジェクトに初めて参加する開発者
- **コントリビューター**: オープンソースプロジェクトに貢献したい開発者
- **メンテナー**: プロジェクトの保守・管理を行う開発者
- **LLM開発者**: AI支援開発を行う開発者

### 学習目標
このガイドを完了すると、以下ができるようになります：
- ✅ プロジェクトの全体アーキテクチャを理解する
- ✅ 開発環境を正しくセットアップする
- ✅ 効率的な開発ワークフローを実践する
- ✅ 品質基準に準拠したコードを作成する
- ✅ 適切なテストを作成・実行する

---

## 2. 🏗️ プロジェクト概要

### プロジェクトの使命
Tree-sitter Analyzerは、**AI時代のエンタープライズグレードコード解析ツール**として、以下を実現します：

- 🤖 **深いAI統合**: MCPプロトコルによるネイティブAI支援
- 🔍 **強力な検索**: fd+ripgrepによる高性能ファイル・コンテンツ検索
- 📊 **インテリジェント解析**: Tree-sitterベースの精密コード構造解析
- 🌍 **多言語サポート**: Java、Python、JavaScript、TypeScript、Markdown、HTMLの完全サポート

### 技術スタック

| カテゴリ | 技術 | 用途 |
|---------|------|------|
| **コア言語** | Python 3.10+ | メイン実装言語 |
| **解析エンジン** | Tree-sitter | 構文解析 |
| **検索ツール** | fd + ripgrep | ファイル・コンテンツ検索 |
| **AI統合** | MCP Protocol | AI助手との統合 |
| **パッケージ管理** | uv | 高速Python環境管理 |
| **テスト** | pytest | テストフレームワーク |
| **品質管理** | black, ruff, mypy | コード品質保証 |

### 品質指標
- **2,934テスト** - 100%パス率
- **80.09%カバレッジ** - 包括的テストスイート
- **クロスプラットフォーム** - Windows、macOS、Linux対応

---

## 3. 🚀 開発環境セットアップ

### 前提条件
- **Python 3.10+** (推奨: 3.11)
- **Git** (バージョン管理)
- **uv** (パッケージマネージャー)

### ステップ1: uvのインストール

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# インストール確認
uv --version
```

### ステップ2: プロジェクトのクローンと依存関係インストール

```bash
# リポジトリクローン
git clone https://github.com/aimasteracc/tree-sitter-analyzer.git
cd tree-sitter-analyzer

# 開発用依存関係の完全インストール
uv sync --extra all --extra mcp

# 環境確認
uv run python --version
uv run python -c "import tree_sitter_analyzer; print('✅ インストール成功')"
```

### ステップ3: 外部ツールのインストール

```bash
# macOS (Homebrew)
brew install fd ripgrep

# Windows (winget)
winget install sharkdp.fd BurntSushi.ripgrep.MSVC

# Ubuntu/Debian
sudo apt install fd-find ripgrep

# 確認
fd --version
rg --version
```

### ステップ4: 開発環境の検証

```bash
# 基本テストの実行
uv run pytest tests/test_api.py -v

# 品質チェックの実行
uv run python check_quality.py --new-code-only

# MCPサーバーの起動テスト
uv run python -m tree_sitter_analyzer.mcp.server --help
```

---

## 4. 📁 プロジェクト構造理解

### 4.1 ルートディレクトリ構造

```
tree-sitter-analyzer/
├── 📁 tree_sitter_analyzer/     # メインパッケージ
├── 📁 tests/                    # テストスイート
├── 📁 docs/                     # ドキュメント
├── 📁 training/                 # トレーニング資料
├── 📁 examples/                 # サンプルファイル
├── 📁 scripts/                  # ビルド・リリーススクリプト
├── 📁 .github/                  # GitHub設定
├── 📄 pyproject.toml            # プロジェクト設定
├── 📄 README.md                 # プロジェクト説明
└── 📄 CONTRIBUTING.md           # コントリビューションガイド
```

### 4.2 メインパッケージ構造

```
tree_sitter_analyzer/
├── 📄 __init__.py              # パッケージ初期化
├── 📄 api.py                   # 公開API
├── 📄 models.py                # データモデル
├── 📄 exceptions.py            # カスタム例外
│
├── 📁 core/                    # コアエンジン
│   ├── 📄 analysis_engine.py   # 統合分析エンジン
│   ├── 📄 engine.py            # レガシーエンジン
│   ├── 📄 parser.py            # パーサー
│   ├── 📄 query.py             # クエリ実行
│   └── 📄 query_service.py     # クエリサービス
│
├── 📁 languages/               # 言語プラグイン
│   ├── 📄 java_plugin.py       # Java言語サポート
│   ├── 📄 python_plugin.py     # Python言語サポート
│   ├── 📄 javascript_plugin.py # JavaScript言語サポート
│   ├── 📄 typescript_plugin.py # TypeScript言語サポート
│   ├── 📄 markdown_plugin.py   # Markdown言語サポート
│   └── 📄 html_plugin.py       # HTML言語サポート
│
├── 📁 queries/                 # Tree-sitterクエリ
│   ├── 📄 java.py              # Javaクエリ定義
│   ├── 📄 python.py            # Pythonクエリ定義
│   └── 📄 ...                  # その他言語クエリ
│
├── 📁 formatters/              # 出力フォーマッター
│   ├── 📄 base_formatter.py    # ベースフォーマッター
│   ├── 📄 java_formatter.py    # Java専用フォーマッター
│   └── 📄 ...                  # その他フォーマッター
│
├── 📁 cli/                     # コマンドライン界面
│   ├── 📄 cli_main.py          # CLIメインエントリ
│   └── 📁 commands/            # CLI コマンド実装
│
├── 📁 mcp/                     # MCP統合
│   ├── 📄 server.py            # MCPサーバー
│   ├── 📁 tools/               # MCPツール
│   └── 📁 resources/           # MCPリソース
│
└── 📁 security/                # セキュリティ機能
    ├── 📄 boundary_manager.py  # 境界管理
    └── 📄 validator.py         # バリデーション
```

### 4.3 重要なコンポーネント

#### コアエンジン (`core/`)
- **`analysis_engine.py`**: 新しい統合分析エンジン（584行、7クラス、41メソッド）
- **`engine.py`**: レガシー分析エンジン（後方互換性のため保持）
- **`query_service.py`**: Tree-sitterクエリの実行とフィルタリング

#### 言語プラグイン (`languages/`)
- **プラグインベースアーキテクチャ**: 各言語の独立実装
- **統一インターフェース**: `BaseLanguagePlugin`による一貫したAPI
- **拡張可能設計**: 新言語の追加が容易

#### MCP統合 (`mcp/`)
- **MCPサーバー**: AI助手との統合ポイント
- **豊富なツール**: 12種類のMCPツールを提供
- **リソース管理**: コードファイルとプロジェクト統計へのアクセス

---

## 5. 🔧 開発ワークフロー

### 5.1 日常的な開発サイクル

```bash
# 1. 最新コードの取得
git pull origin main

# 2. 新機能ブランチの作成
git checkout -b feature/新機能名

# 3. 開発作業
# ... コード編集 ...

# 4. 品質チェック
uv run python check_quality.py --new-code-only
uv run python llm_code_checker.py --check-all

# 5. テスト実行
uv run pytest tests/ -v

# 6. コミット
git add .
git commit -m "feat: 新機能の説明"

# 7. プッシュとプルリクエスト
git push origin feature/新機能名
```

### 5.2 コード品質チェック

#### 自動フォーマット
```bash
# コードフォーマット
uv run black .
uv run isort .

# 品質チェック
uv run ruff check . --fix
```

#### 型チェック
```bash
# 型安全性チェック
uv run mypy tree_sitter_analyzer/
```

#### テスト実行
```bash
# 全テスト実行
uv run pytest tests/ -v

# カバレッジ付きテスト
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html

# 特定テストの実行
uv run pytest tests/test_core/ -v
```

### 5.3 新言語プラグインの開発

#### ステップ1: プラグインファイルの作成
```python
# tree_sitter_analyzer/languages/new_language_plugin.py
from tree_sitter_analyzer.plugins.base import BaseLanguagePlugin

class NewLanguagePlugin(BaseLanguagePlugin):
    key = "new_language"
    extensions = [".ext"]
    name = "New Language"
    
    def analyze(self, code: str, file_path: str) -> Dict:
        # 実装
        pass
```

#### ステップ2: クエリ定義の作成
```python
# tree_sitter_analyzer/queries/new_language.py
NEW_LANGUAGE_QUERIES = {
    "functions": """
    (function_declaration
      name: (identifier) @function.name
    )
    """,
    # その他のクエリ
}
```

#### ステップ3: テストの作成
```python
# tests/test_new_language_plugin.py
def test_new_language_plugin():
    plugin = NewLanguagePlugin()
    result = plugin.analyze(sample_code, "test.ext")
    assert result["language"] == "new_language"
```

### 5.4 MCPツールの開発

#### 新しいMCPツールの追加
```python
# tree_sitter_analyzer/mcp/tools/new_tool.py
from tree_sitter_analyzer.mcp.tools.base_tool import BaseTool

class NewTool(BaseTool):
    name = "new_tool"
    description = "新しいツールの説明"
    
    def execute(self, **kwargs):
        # ツールの実装
        pass
```

---

## 6. 🧪 テストとQA

### 6.1 テスト戦略

#### テストピラミッド
```
        🔺 E2E テスト (少数)
       🔺🔺 統合テスト (中程度)
    🔺🔺🔺🔺 単体テスト (多数)
```

#### テストカテゴリ
- **単体テスト**: 個別コンポーネントのテスト
- **統合テスト**: コンポーネント間の連携テスト
- **E2Eテスト**: エンドツーエンドの機能テスト
- **回帰テスト**: 既存機能の保護

### 6.2 テスト実行コマンド

```bash
# 基本テスト実行
uv run pytest tests/ -v

# 特定カテゴリのテスト
uv run pytest tests/test_core/ -v          # コアテスト
uv run pytest tests/test_languages/ -v    # 言語プラグインテスト
uv run pytest tests/test_mcp/ -v          # MCPテスト

# パフォーマンステスト
uv run pytest tests/ -m "not slow" -v     # 高速テストのみ

# カバレッジレポート
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=html
```

### 6.3 品質保証プロセス

#### プリコミットフック
```bash
# プリコミットフックのインストール
uv add pre-commit
pre-commit install

# 手動実行
pre-commit run --all-files
```

#### CI/CDパイプライン
- **GitHub Actions**: 自動テスト・品質チェック
- **複数Python版**: 3.10、3.11、3.12での検証
- **クロスプラットフォーム**: Windows、macOS、Linuxでのテスト

---

## 7. 📚 重要なリソース

### 7.1 ドキュメント

| ドキュメント | 用途 | 対象者 |
|-------------|------|--------|
| **[README.md](../README.md)** | プロジェクト概要 | 全ユーザー |
| **[CONTRIBUTING.md](../CONTRIBUTING.md)** | コントリビューションガイド | 開発者 |
| **[API Documentation](api.md)** | API詳細仕様 | 開発者 |
| **[Training Materials](../training/README.md)** | 学習資料 | 新規開発者 |

### 7.2 アーキテクチャ文書

| 文書 | 内容 | 重要度 |
|------|------|--------|
| **[CURRENT_ARCHITECTURE_ANALYSIS_REPORT.md](../CURRENT_ARCHITECTURE_ANALYSIS_REPORT.md)** | 現状アーキテクチャ分析 | 🔴 必読 |
| **[BACKWARD_COMPATIBILITY_DESIGN.md](../BACKWARD_COMPATIBILITY_DESIGN.md)** | 後方互換性設計 | 🟡 重要 |
| **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** | プロジェクト構造詳細 | 🟡 重要 |

### 7.3 実装ガイド

| ガイド | 内容 | 対象 |
|--------|------|------|
| **[IMPLEMENTATION_RULES.md](IMPLEMENTATION_RULES.md)** | 実装ルールとパターン | 開発者 |
| **[ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)** | アーキテクチャ決定記録 | アーキテクト |
| **[LLM_CONTEXT_GUIDE.md](LLM_CONTEXT_GUIDE.md)** | LLM開発用コンテキスト | AI開発者 |

### 7.4 トレーニング資料

| 資料 | レベル | 時間 |
|------|--------|------|
| **[01_onboarding.md](../training/01_onboarding.md)** | 初心者 | 30-60分 |
| **[02_architecture_map.md](../training/02_architecture_map.md)** | 中級 | 45-90分 |
| **[05_plugin_tutorial.md](../training/05_plugin_tutorial.md)** | 上級 | 60-120分 |
| **[06_quality_workflow.md](../training/06_quality_workflow.md)** | 中級 | 30-60分 |

---

## 8. 🤝 コントリビューション

### 8.1 コントリビューションの種類

- **🐛 バグ修正**: 既存機能の問題解決
- **✨ 新機能**: 新しい機能の追加
- **📚 ドキュメント**: ドキュメントの改善
- **🧪 テスト**: テストカバレッジの向上
- **🔧 リファクタリング**: コード品質の改善

### 8.2 プルリクエストガイドライン

#### 必須チェック項目
- [ ] 品質チェックが全て通過している
- [ ] 適切なテストが追加されている
- [ ] ドキュメントが更新されている
- [ ] 後方互換性が保たれている
- [ ] コミットメッセージが規約に従っている

#### コミットメッセージ規約
```
type(scope): description

feat(core): 新しい分析エンジンを追加
fix(mcp): MCPサーバーの接続問題を修正
docs(readme): インストール手順を更新
test(core): 分析エンジンのテストを追加
refactor(plugins): プラグインシステムをリファクタリング
```

### 8.3 開発者コミュニティ

- **GitHub Issues**: バグ報告・機能要求
- **GitHub Discussions**: 技術的な議論
- **Pull Requests**: コード貢献
- **Sponsor Program**: プロジェクト支援

---

## 🎯 次のステップ

### 新規開発者向け
1. **[オンボーディング](../training/01_onboarding.md)** - 基本操作の習得
2. **[アーキテクチャ理解](../training/02_architecture_map.md)** - システム設計の理解
3. **[プラグイン開発](../training/05_plugin_tutorial.md)** - 実践的な開発スキル

### 経験者向け
1. **[アーキテクチャ分析レポート](../CURRENT_ARCHITECTURE_ANALYSIS_REPORT.md)** - 現状課題の理解
2. **[実装ルール](IMPLEMENTATION_RULES.md)** - 開発標準の習得
3. **[アーキテクチャ決定記録](ARCHITECTURE_DECISIONS.md)** - 設計思想の理解

### AI開発者向け
1. **[LLMコンテキストガイド](LLM_CONTEXT_GUIDE.md)** - AI支援開発の最適化
2. **[MCPツール開発](../training/04_mcp_cheatsheet.md)** - AI統合機能の拡張

---

**🚀 Tree-sitter Analyzerの開発者コミュニティへようこそ！**

*このガイドは、効率的で高品質な開発を支援するために継続的に更新されています。*