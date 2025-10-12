# スナップショットテスト体制

## 概要

このディレクトリは、tree-sitter-analyzerプロジェクトのスナップショットテスト体制を管理します。PyPiパッケージ（tree-sitter-analyzer-pypi）を基準として、新しい実装との回帰検出を行います。

## ディレクトリ構造

```
test_snapshots/
├── README.md                    # このファイル
├── baselines/                   # PyPiパッケージによるベースライン出力
│   ├── java/                   # Java言語のスナップショット
│   ├── python/                 # Python言語のスナップショット
│   ├── javascript/             # JavaScript言語のスナップショット
│   ├── typescript/             # TypeScript言語のスナップショット
│   ├── html/                   # HTML言語のスナップショット
│   └── markdown/               # Markdown言語のスナップショット
├── current/                    # 現在の実装による出力
│   ├── java/
│   ├── python/
│   ├── javascript/
│   ├── typescript/
│   ├── html/
│   └── markdown/
├── diffs/                      # 差分レポート
│   ├── summary.json           # 差分サマリー
│   └── detailed/              # 詳細な差分レポート
├── config/                     # テスト設定
│   ├── test_cases.json        # テストケース定義
│   └── comparison_rules.json  # 比較ルール設定
└── reports/                    # テストレポート
    ├── latest_report.html     # 最新のHTMLレポート
    └── history/               # 過去のレポート履歴
```

## テストケース

### 対象ファイル
- `examples/BigService.java` - 大規模Javaファイル
- `examples/Sample.java` - 標準Javaファイル
- `examples/MultiClass.java` - 複数クラスJavaファイル
- `examples/JavaDocTest.java` - JavaDocテストファイル
- `examples/sample.py` - Pythonサンプルファイル
- `examples/cache_demo.py` - Python機能デモファイル
- `examples/ModernJavaScript.js` - JavaScript機能ファイル
- `examples/ComprehensiveTypeScript.ts` - TypeScript包括ファイル
- `examples/TypeScriptDeclarations.d.ts` - TypeScript宣言ファイル
- `examples/comprehensive_html.html` - HTML包括ファイル
- `examples/test_markdown.md` - Markdownテストファイル

### テスト項目
1. **構造解析結果**
   - クラス、メソッド、フィールドの検出
   - 行番号とコード位置の正確性
   - 要素の階層関係

2. **メタデータ**
   - ファイルサイズ、行数統計
   - 複雑度計算
   - 言語固有の特徴

3. **出力形式**
   - JSON形式の一貫性
   - CSV形式の互換性
   - テキスト形式の可読性

4. **エラーハンドリング**
   - 不正なファイルの処理
   - エンコーディング問題の対応
   - 例外処理の一貫性

## 使用方法

### ベースライン生成
```bash
python scripts/generate_snapshots.py --mode baseline
```

### 現在の実装テスト
```bash
python scripts/generate_snapshots.py --mode current
```

### 差分比較
```bash
python -m pytest tests/test_snapshot_regression.py -v
```

### レポート生成
```bash
python scripts/generate_snapshots.py --mode report
```

## CI/CD統合

GitHub Actionsでの自動実行:
- プルリクエスト時の回帰テスト
- マージ前の差分レポート生成
- リリース前の包括的検証

## 注意事項

- ベースラインは定期的に更新する必要があります
- 意図的な変更は事前に設定ファイルで除外してください
- 大きな差分が検出された場合は、詳細な調査を行ってください