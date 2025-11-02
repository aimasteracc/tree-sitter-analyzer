# 変更管理クイックガイド

> **完全版**: [`docs/ja/project-management/05_変更管理方針.md`](docs/ja/project-management/05_変更管理方針.md)

## 🚀 変更を始める前に（1分チェック）

```
変更内容は？
  │
  ├─ プロジェクト全体の方向性に影響？      → PMP準拠ドキュメント更新
  ├─ 品質基準・テスト戦略の変更？          → PMP準拠ドキュメント更新
  ├─ 技術スタック・アーキテクチャ変更？    → PMP準拠ドキュメント更新
  ├─ ドキュメント体系全体の再構築？        → PMP準拠ドキュメント更新
  │
  ├─ 新機能追加・既存機能改善？            → OpenSpec
  ├─ 重要なバグ修正？                     → OpenSpec
  ├─ パフォーマンス最適化？                → OpenSpec
  ├─ 新言語サポート追加？                  → OpenSpec
  │
  └─ 誤字修正・軽微な改善？                → PR直接
```

## 📋 PMP準拠ドキュメント（戦略層）

**いつ使う？**
- プロジェクト全体に影響する変更
- 品質基準・方針の変更
- 四半期レビュー

**対象ドキュメント：**
- `docs/ja/project-management/` 配下
- `docs/ja/test-management/` 配下

**更新頻度：** 四半期 / 重大変更時

## 🚀 OpenSpec（戦術層）

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

**更新頻度：** 継続的（開発サイクルに同期）

## 📊 統合管理

```
PMP（戦略）
    ↓ 方向性・基準
OpenSpec（戦術）
    ↓ 具体的実装
コード・テスト
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

**最終更新:** 2025-11-03  
**管理者:** aisheng.yu
