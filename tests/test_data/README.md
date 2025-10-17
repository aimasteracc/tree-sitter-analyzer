# テストデータディレクトリ

このディレクトリには、tree-sitter-analyzer互換性テスト用のテストデータファイルが含まれています。

## ファイル構成

### 既存のexamplesフォルダのファイルを活用
- `examples/BigService.java` - 大規模Javaクラス（1400行以上）
- `examples/comprehensive_sample.html` - 包括的HTMLサンプル（500行以上）
- `examples/comprehensive_sample.css` - 包括的CSSサンプル（1400行以上）
- `examples/ComprehensiveTypeScript.ts` - 包括的TypeScriptサンプル（600行以上）
- `examples/ModernJavaScript.js` - モダンJavaScriptサンプル（550行以上）

### 追加テストデータファイル
- `small_sample.py` - 小規模Pythonファイル
- `medium_sample.java` - 中規模Javaファイル
- `edge_case.js` - エッジケース用JavaScriptファイル
- `unicode_sample.py` - Unicode文字を含むPythonファイル
- `empty_file.txt` - 空ファイル
- `single_line.js` - 単一行ファイル

## テストケースとの対応

各テストケースは以下のファイルを使用します：

### check_code_scale テスト
- 大規模ファイル: `examples/BigService.java`
- 中規模ファイル: `examples/ComprehensiveTypeScript.ts`
- 小規模ファイル: `examples/ModernJavaScript.js`

### analyze_code_structure テスト
- Java: `examples/BigService.java`
- HTML: `examples/comprehensive_sample.html`
- TypeScript: `examples/ComprehensiveTypeScript.ts`
- JavaScript: `examples/ModernJavaScript.js`
- CSS: `examples/comprehensive_sample.css`

### extract_code_section テスト
- 各言語のサンプルファイルから特定の行範囲を抽出

### query_code テスト
- メソッド抽出: `examples/BigService.java`
- クラス抽出: `examples/ComprehensiveTypeScript.ts`
- 関数抽出: `examples/ModernJavaScript.js`

### ファイル操作テスト (list_files, search_content, find_and_grep)
- examplesディレクトリ全体を対象
- 特定の拡張子やパターンでのフィルタリング

## ファイルの特徴

### BigService.java
- 1400行以上の大規模クラス
- 複数のメソッド、フィールド、コンストラクタ
- Javadocコメント
- 複雑な制御構造

### comprehensive_sample.html
- HTML5の全主要要素を含む
- セマンティック要素、フォーム、テーブル、メディア要素
- 内部CSS、JavaScript
- 構造化データ

### comprehensive_sample.css
- CSS3の包括的な機能
- カスタムプロパティ、アニメーション、レスポンシブデザイン
- メディアクエリ、グリッドレイアウト

### ComprehensiveTypeScript.ts
- TypeScriptの全主要機能
- インターフェース、クラス、ジェネリクス
- デコレーター、非同期処理
- 型ガード、条件型

### ModernJavaScript.js
- モダンJavaScriptの機能
- ES6+構文、クラス、アロー関数
- 非同期処理、モジュール
- React hooks、JSX