# 変更管理クイックガイド

> **完全版**: [`docs/ja/project-management/05_変更管理方針.md`](docs/ja/project-management/05_変更管理方針.md)

## 🚀 変更を始める前に（1分チェック）

```
変更内容は？
  │
  ├─ 新機能追加・既存機能改善？            → OpenSpec または Kiro Specs
  ├─ 重要なバグ修正？                     → OpenSpec または Kiro Specs
  ├─ パフォーマンス最適化？                → OpenSpec または Kiro Specs
  ├─ 新言語サポート追加？                  → OpenSpec または Kiro Specs
  │
  ├─ 誤字修正・軽微な改善？                → PR直接
  │
  └─ PMP更新は定期マイルストーンで集約    → 四半期/メジャーリリース時
```

## 🛠️ 日常開発ツール

### OpenSpec（無料・推奨）

**場所：** `openspec/`

**いつ使う？**
- 新機能追加
- 既存機能の改善
- 重要なバグ修正
- リファクタリング

**ワークフロー：**
```bash
openspec propose <change-id>   # 変更提案
openspec validate <change-id>  # 検証
# → 実装・テスト → PR
```

### Kiro Specs（AI支援開発）

**場所：** `.kiro/specs/`

**いつ使う？**
- Kiro/Claude AIアシスタントとの開発
- 構造化された機能仕様作成

**構造：**
```
.kiro/specs/<feature-name>/
├── requirements.md    # 要件定義
├── design.md          # 設計仕様
└── tasks.md           # 実装タスク
```

## 📋 PMP準拠ドキュメント（戦略層）

**場所：**
- `docs/ja/project-management/` 配下
- `docs/ja/test-management/` 配下

**いつ更新？**
- 四半期レビュー時
- メジャーバージョンリリース時
- 重大な方針変更時

> **Note:** PMP文書は日常開発の変更を定期的に集約して更新します。

## 📊 変更管理フロー

```
日常開発
├── OpenSpec (openspec/)
└── Kiro Specs (.kiro/specs/)
         │
         ▼ 定期マイルストーンで集約
         │
PMP文書 (docs/ja/)
└── 戦略・方針反映
```

## 🔗 詳細情報

- **完全版ドキュメント**: [`docs/ja/project-management/05_変更管理方針.md`](docs/ja/project-management/05_変更管理方針.md)
- **ドキュメント体系**: [`docs/ja/README.md`](docs/ja/README.md)
- **OpenSpec説明**: `.roo/commands/openspec-proposal.md`

## 💡 よくある質問

**Q: どちらで管理すべきか迷ったら？**  
A: まずIssueで議論 → チームで決定

**Q: 小さな変更でもOpenSpecは必要？**  
A: 誤字修正、コメント改善などは不要。PRで直接。

**Q: PMPとOpenSpecで矛盾が生じたら？**  
A: **PMPが優先**。PMPの方針変更を提案。

---

**最終更新:** 2025-11-28  
**管理者:** aisheng.yu
