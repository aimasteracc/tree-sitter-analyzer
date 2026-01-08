# tree-sitter-analyzer への貢献ガイド（日本語版）

> **English version**: [CONTRIBUTING.md](../CONTRIBUTING.md)

## 変更管理体系

本プロジェクトは**日常開発**と**戦略管理**を分離した変更管理体系を採用しています。

> **クイックガイド**: [CHANGE_MANAGEMENT_GUIDE.md](../../CHANGE_MANAGEMENT_GUIDE.md) を参照

### 日常開発: OpenSpec / Kiro Specs

日常の機能開発・バグ修正には以下のツールを使用します：

#### OpenSpec（無料・推奨）

**場所**: `openspec/`

```bash
openspec propose <change-id>   # 変更提案
openspec validate <change-id>  # 検証
# → 実装・テスト → PR
```

#### Kiro Specs（AI支援開発）

**場所**: `.kiro/specs/`

Kiro/Claude AIアシスタントとの構造化開発に使用：

```
.kiro/specs/<feature-name>/
├── requirements.md    # 要件定義
├── design.md          # 設計仕様
└── tasks.md           # 実装タスク
```

### 戦略管理: PMP準拠ドキュメント

**場所**: `docs/ja/project-management/`, `docs/ja/test-management/`

PMP文書は**定期的なマイルストーン**で日常開発の変更を集約して更新します：

- 四半期レビュー時
- メジャーバージョンリリース時
- 重大な方針変更時

**対象ドキュメント**:
- [プロジェクト憲章](project-management/00_プロジェクト憲章.md) - 全体ビジョン
- [変更管理方針](project-management/05_変更管理方針.md) - 詳細ルール
- [品質管理計画](project-management/03_品質管理計画.md) - 品質基準
- [テスト戦略](test-management/00_テスト戦略.md) - テストアプローチ

### 変更管理フロー

```
日常開発
├── OpenSpec (openspec/) ──────┐
│   └── 機能追加・バグ修正     │
└── Kiro Specs (.kiro/specs/) ─┤
    └── AI支援開発             │
                               ▼
                    定期マイルストーンで集約
                               │
                               ▼
                    PMP文書更新 (docs/ja/)
                    └── 戦略・方針反映
```

## ドキュメント構造

### ディレクトリマップ

```
tree-sitter-analyzer/
├── README.md                    # プロジェクト入口
├── CHANGE_MANAGEMENT_GUIDE.md   # 変更管理クイックガイド
├── CHANGELOG.md                 # バージョン履歴
├── docs/
│   ├── installation.md          # インストールガイド
│   ├── cli-reference.md         # CLIリファレンス
│   ├── smart-workflow.md        # SMARTワークフロー
│   ├── architecture.md          # アーキテクチャ概要
│   ├── features.md              # 機能一覧
│   ├── CONTRIBUTING.md          # 貢献ガイド（英語）
│   ├── new-language-support-checklist.md  # 新言語追加チェックリスト
│   ├── api/
│   │   └── mcp_tools_specification.md  # MCP API仕様
│   └── ja/
│       ├── CONTRIBUTING_ja.md   # 本ドキュメント（日本語）
│       ├── project-management/  # PMP文書（戦略層）
│       ├── specifications/      # 技術仕様
│       ├── test-management/     # テスト管理
│       └── user-guides/         # ユーザーガイド
├── openspec/                    # OpenSpec（戦術層）
│   ├── project.md               # プロジェクト定義
│   └── changes/                 # 変更提案
└── .kiro/specs/                 # AI支援開発仕様
```

## ブランチ戦略 (GitFlow)

本プロジェクトはGitFlowブランチ戦略を採用しています。

> **詳細**: [GITFLOW_ja.md](../../GITFLOW_ja.md) を参照

### ブランチ構造

| ブランチ | 用途 | 直接プッシュ |
|---------|------|-------------|
| `main` | 本番環境対応コード | ❌ **禁止** |
| `develop` | 機能統合ブランチ | ❌ PR経由のみ |
| `feature/*` | 機能開発 | ✅ 許可 |
| `release/*` | リリース準備 | ✅ 許可 |
| `hotfix/*` | 緊急修正 | ✅ 許可 |

### ⚠️ 重要: main ブランチへの直接プッシュは禁止

```
❌ 禁止: main に直接プッシュ
   git push origin main

✅ 正しい方法: feature → develop → release → main
```

### コントリビューターのワークフロー

```
1. develop から feature ブランチを作成
   git checkout -b feature/my-feature origin/develop

2. 機能開発・テスト

3. feature ブランチをプッシュ
   git push origin feature/my-feature

4. develop への PR を作成
   → レビュー → マージ

5. リリース時に develop → release → main
```

## 開発ワークフロー

### 1. 変更タイプの判断

```
変更内容は？
  │
  ├─ プロジェクト方針・品質基準 → PMP文書を更新
  │
  ├─ 新機能・バグ修正・リファクタリング
  │   ├─ AI支援開発の場合 → .kiro/specs/ で仕様作成
  │   └─ 従来開発の場合  → openspec/ で提案
  │
  └─ 誤字修正・軽微な改善 → feature/* ブランチから PR
```

### 2. 機能開発フロー

```bash
# 1. develop から feature ブランチを作成
git fetch origin
git checkout -b feature/my-feature origin/develop

# 2. 仕様作成（AI支援の場合）
.kiro/specs/<feature-name>/
├── requirements.md  # 要件定義
├── design.md        # 設計
└── tasks.md         # タスク

# 3. 実装
# 4. テスト作成・実行
uv run pytest tests/ -v

# 5. 品質チェック
uv run pre-commit run --all-files

# 6. feature ブランチをプッシュ
git push origin feature/my-feature

# 7. develop への PR を作成
```

### 3. プッシュ前のチェックリスト

```bash
# 1. ローカルでテストを実行
uv run pytest tests/ -v

# 2. 品質チェックを実行
uv run pre-commit run --all-files

# 3. システム依存を確認
fd --version
rg --version

# 4. プッシュ
git push
```

## 特定タスクガイド

### 🌐 新しい言語サポートの追加

新しいプログラミング言語のサポートを追加する場合は、**必ず**以下のチェックリストに従ってください：

> **📋 必読**: [新しい言語サポート追加チェックリスト](../new-language-support-checklist.md)

このチェックリストには以下が含まれます：
- 言語プラグインの実装手順
- フォーマッターの作成と登録
- **ゴールデンマスターテストの作成**（必須！）
- ドキュメント更新（README.md, README_ja.md, README_zh.md）

⚠️ **重要**: ゴールデンマスターテストを忘れると、将来のリグレッションを検出できません。

```bash
# 言語固有のテストを実行
uv run pytest tests/test_{language}/ -v

# ゴールデンマスターテストを実行
uv run pytest tests/test_golden_master_regression.py -v -k "{language}"
```

## コード品質

### テスト要件

- **カバレッジ**: 新規コードは80%以上のカバレッジ必須
- **既存テスト**: すべてのテストがパスすることを確認
- **テストタイプ**: 
  - ユニットテスト: 個別コンポーネントのテスト
  - 統合テスト: コンポーネント間の相互作用テスト
  - E2Eテスト: エンドツーエンドのワークフローテスト

### テストの実行

```bash
# すべてのテストを実行
uv run pytest tests/ -v

# カバレッジレポート付きで実行
uv run pytest tests/ --cov=tree_sitter_analyzer --cov-report=term-missing

# 特定のテストファイルを実行
uv run pytest tests/test_readme/ -v

# 並列実行（高速化）
uv run pytest tests/ -n auto
```

### カバレッジターゲット

| モジュールカテゴリ | カバレッジ目標 | 優先度 |
|-------------------|---------------|--------|
| コアエンジン | ≥85% | クリティカル |
| 例外処理 | ≥90% | クリティカル |
| MCPインターフェース | ≥80% | 高 |
| CLIコマンド | ≥85% | 高 |
| フォーマッター | ≥80% | 中 |
| クエリモジュール | ≥85% | 中 |

## 多言語README更新責任

README.mdに構造的変更を加える場合、コントリビューターは以下の責任を負います。

### 必須の同期更新

| ファイル | 言語 | 必須 |
|---------|------|------|
| README.md | English | ✅ Primary |
| README_ja.md | 日本語 | ✅ 同期必須 |
| README_zh.md | 简体中文 | ✅ 同期必須 |

### README変更チェックリスト

- [ ] 新しいセクションを追加した場合、README_ja.mdとREADME_zh.mdにも同じセクションを追加
- [ ] セクションの順序を変更した場合、すべてのREADMEで同じ順序に更新
- [ ] セクションのemojiを変更した場合、すべてのREADMEで同じemojiに更新
- [ ] `tests/test_readme/` のテストがすべてパスすることを確認

### 構造一貫性の検証

```bash
# README構造テストを実行
uv run pytest tests/test_readme/ -v
```

このテストは以下を検証します：
- README行数が500行以内
- すべての必須セクションが存在
- セクションのemoji一貫性
- ドキュメントリンクの有効性
- 多言語READMEの構造一致

## CI/CD ワークフロー

### GitHub Actions による自動化

| ブランチ | ワークフロー | テスト | デプロイ | PR作成 |
|---------|------------|--------|---------|--------|
| `develop` | develop-automation.yml | ✅ 全テスト | ❌ なし | ✅ main へ |
| `release/*` | release-automation.yml | ✅ 全テスト | ✅ PyPI | ✅ main へ |
| `hotfix/*` | hotfix-automation.yml | ✅ 全テスト | ✅ PyPI | ✅ main へ |
| `main` | ci.yml | ✅ 全テスト | ❌ なし | ❌ なし |
| `feature/*` | ci.yml | ✅ 全テスト | ❌ なし | ❌ なし |

### main ブランチ保護ルール（推奨設定）

GitHub リポジトリの Settings → Branches → Branch protection rules で以下を設定：

- [x] **Require a pull request before merging** - PR必須
- [x] **Require approvals** - レビュー承認必須
- [x] **Require status checks to pass** - CI通過必須
- [x] **Do not allow bypassing the above settings** - 管理者も例外なし

### main への直接プッシュが来た場合の対応

コントリビューターが誤って main に直接プッシュした場合：

1. **保護ルールが設定されていれば自動的に拒否されます**
2. コントリビューターに正しいワークフローを案内：
   ```
   正しい手順:
   1. feature/* ブランチを作成
   2. 変更をコミット
   3. develop への PR を作成
   ```

### テスト環境

- **Python バージョン**: 3.10, 3.11, 3.12, 3.13
- **OS プラットフォーム**: ubuntu-latest, windows-latest, macos-latest
- **システム依存**: fd, ripgrep
- **品質チェック**: mypy, black, ruff, isort, bandit, pydocstyle

詳細は [CI/CD Overview](../ci-cd-overview.md) を参照してください。

## リリース管理

### バージョニング
- セマンティックバージョニングに従う
- 破壊的変更は major バージョンアップ

### リリースノート
- `CHANGELOG.md` を更新
- 重要な変更は `openspec/` にも記録

## 関連ドキュメント

### 開発ガイド
- [新しい言語サポート追加チェックリスト](../new-language-support-checklist.md)
- [テストガイドライン](../TESTING.md)
- [変更管理クイックガイド](../../CHANGE_MANAGEMENT_GUIDE.md)

### CI/CD
- [CI/CD Overview](../ci-cd-overview.md)
- [CI/CD Troubleshooting](../ci-cd-troubleshooting.md)

### プロジェクト管理
- [PMP文書体系](README.md)

