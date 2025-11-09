# Proposal: Improve Language Formatter Isolation

**Change ID**: improve-language-formatter-isolation
**Type**: Architecture Improvement
**Priority**: High
**Status**: Draft

## Problem Statement

現在の言語フォーマッターシステムには以下の設計上の問題があります：

### 1. 中央集権的な登録システムの脆弱性
- 全言語のフォーマッターが単一のファクトリークラス（`LanguageFormatterFactory`）に依存
- 新しい言語サポート追加時に既存言語の登録が意図せず削除される可能性
- SQLサポート追加時にJava、JavaScript、TypeScriptの登録が削除され、デグレが発生
- HTML、CSS、Markdownフォーマッターも同様のリスクに晒されている

### 2. 型安全性の欠如
- `TableCommand`で存在しない`format_table()`メソッドを呼び出していた
- コンパイル時に検出されない設計上の不整合

### 3. テスト不足による回帰リスク
- 新機能追加時の既存機能への影響チェックが不十分
- 言語間の相互影響を検出する仕組みが不足

## Proposed Solution

### 1. 分散型フォーマッター登録システム
各言語フォーマッターが自己登録する仕組みに変更：

```python
# 各フォーマッターが自動登録
class JavaTableFormatter(BaseTableFormatter):
    @classmethod
    def get_supported_languages(cls) -> list[str]:
        return ["java"]
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        LanguageFormatterFactory.auto_register(cls)
```

### 2. プラグイン型アーキテクチャ
- 各言語フォーマッターを独立したプラグインとして実装
- 動的ロードによる言語サポートの追加/削除
- 言語間の依存関係を排除

### 3. 型安全性の向上
- 抽象基底クラスによるインターフェース統一
- Protocol型による型チェック強化
- mypy による静的型検査の徹底

### 4. 包括的回帰テスト
- 全言語の相互影響テスト
- 新言語追加時の既存言語テスト自動実行
- ゴールデンマスターテストの強化

## Benefits

1. **安全性向上**: 新言語追加時の既存言語への影響を排除
2. **保守性向上**: 各言語フォーマッターの独立性確保
3. **拡張性向上**: プラグイン型による柔軟な言語サポート追加
4. **品質向上**: 型安全性と包括的テストによる信頼性向上

## Impact Assessment

### Affected Components
- `tree_sitter_analyzer/formatters/language_formatter_factory.py`
- `tree_sitter_analyzer/cli/commands/table_command.py`
- 全言語フォーマッター（Java、JavaScript、TypeScript、Python、SQL、HTML、CSS、Markdown等）
- 関連テストスイート

### Breaking Changes
- フォーマッターファクトリーのAPIが変更される可能性
- 既存のフォーマッター登録方法が変更

### Migration Strategy
1. 段階的移行：既存APIとの互換性を保ちながら新システムを導入
2. 包括的テスト：全言語での動作確認
3. ドキュメント更新：新しいフォーマッター開発ガイドの作成

## Success Criteria

1. ✅ 新言語追加時に既存言語が影響を受けない
2. ✅ 全言語フォーマッターの型安全性確保
3. ✅ 包括的回帰テストの実装
4. ✅ プラグイン型アーキテクチャの実現
5. ✅ 既存機能の完全な互換性維持

## Related Issues

- Java解析デグレ問題（SQLサポート追加時）
- フォーマッターメソッド不整合問題
- 言語間相互影響の検出不足

## Next Steps

1. 詳細設計の作成
2. プロトタイプ実装
3. 包括的テストスイートの設計
4. 段階的移行計画の策定
