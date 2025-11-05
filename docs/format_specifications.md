# Tree-Sitter Analyzer Format Specifications

このドキュメントは、tree-sitter-analyzerが出力する各フォーマットタイプの正式な仕様を定義します。

## 概要

tree-sitter-analyzerは以下の3つの主要なフォーマットタイプをサポートします：

1. **Full Format** - 完全な詳細情報を含むMarkdown形式
2. **Compact Format** - 簡潔な情報を含むMarkdown形式  
3. **CSV Format** - 構造化データとしてのCSV形式

## 共通仕様

### 文字エンコーディング
- **エンコーディング**: UTF-8
- **改行コード**: LF (`\n`)
- **BOM**: なし

### 言語サポート
- Java
- Python
- TypeScript/JavaScript
- HTML
- CSS
- Markdown

### 共通データ要素
すべてのフォーマットは以下の基本要素を含みます：

- **クラス/型定義**
- **メソッド/関数**
- **フィールド/変数**
- **インポート/依存関係**
- **コメント/ドキュメント**

## Full Format 仕様

### 構造概要
```
# {package}.{ClassName}

## Class Info
| Property | Value |
|----------|-------|
| Name | {ClassName} |
| Package | {package} |
| Type | {class/interface/enum} |
| Access | {public/private/protected} |
| Abstract | {true/false} |
| Final | {true/false} |

## Methods
| Name | Return Type | Parameters | Access | Line |
|------|-------------|------------|--------|------|
| {methodName} | {returnType} | {parameters} | {access} | {lineNumber} |

## Fields
| Name | Type | Access | Static | Final | Line |
|------|------|--------|--------|-------|------|
| {fieldName} | {fieldType} | {access} | {true/false} | {true/false} | {lineNumber} |

## Imports
| Import | Type |
|--------|------|
| {importPath} | {import/static} |
```

### 詳細仕様

#### ヘッダー部分
- **形式**: `# {package}.{ClassName}`
- **必須**: はい
- **例**: `# com.example.service.UserService`

#### Class Info セクション
- **形式**: Markdownテーブル
- **必須フィールド**: Name, Package, Type
- **オプションフィールド**: Access, Abstract, Final, Implements, Extends
- **テーブル形式**: 
  ```markdown
  | Property | Value |
  |----------|-------|
  ```

#### Methods セクション
- **形式**: Markdownテーブル
- **必須フィールド**: Name, Return Type, Parameters, Access, Line
- **パラメータ形式**: `type1 param1, type2 param2`
- **アクセス修飾子**: public, private, protected, package
- **テーブル形式**:
  ```markdown
  | Name | Return Type | Parameters | Access | Line |
  |------|-------------|------------|--------|------|
  ```

#### Fields セクション
- **形式**: Markdownテーブル
- **必須フィールド**: Name, Type, Access, Static, Final, Line
- **boolean値**: `true` または `false`
- **テーブル形式**:
  ```markdown
  | Name | Type | Access | Static | Final | Line |
  |------|------|--------|--------|-------|------|
  ```

#### Imports セクション
- **形式**: Markdownテーブル
- **必須フィールド**: Import, Type
- **Type値**: `import` または `static`
- **テーブル形式**:
  ```markdown
  | Import | Type |
  |--------|------|
  ```

### 言語固有の拡張

#### Java
- **パッケージ情報**: 完全修飾名
- **アノテーション**: サポート
- **ジェネリクス**: 型パラメータ表示

#### Python
- **モジュール情報**: インポートパス
- **デコレータ**: サポート
- **型ヒント**: 表示

#### TypeScript
- **インターフェース**: サポート
- **型定義**: 表示
- **モジュール**: ES6/CommonJS

## Compact Format 仕様

### 構造概要
```
# {ClassName}

## Info
| Property | Value |
|----------|-------|
| Type | {type} |
| Methods | {count} |
| Fields | {count} |

## Methods
| Name | Return Type | Access | Line |
|------|-------------|--------|------|
| {methodName} | {returnType} | {access} | {lineNumber} |

## Fields  
| Name | Type | Access | Line |
|------|------|--------|------|
| {fieldName} | {fieldType} | {access} | {lineNumber} |
```

### 詳細仕様

#### ヘッダー部分
- **形式**: `# {ClassName}`
- **パッケージ情報**: 省略
- **例**: `# UserService`

#### Info セクション
- **形式**: Markdownテーブル
- **必須フィールド**: Type, Methods, Fields
- **カウント形式**: 数値のみ

#### Methods セクション
- **形式**: Markdownテーブル
- **必須フィールド**: Name, Return Type, Access, Line
- **パラメータ**: 省略
- **簡潔な型表示**: プリミティブ型は短縮形

#### Fields セクション
- **形式**: Markdownテーブル
- **必須フィールド**: Name, Type, Access, Line
- **修飾子**: Static/Final情報は省略

### 省略ルール
- パッケージ名は省略
- パラメータ詳細は省略
- 修飾子の詳細は省略
- インポート情報は省略

## CSV Format 仕様

### 構造概要
```csv
Type,Name,ReturnType,Parameters,Access,Static,Final,Line
class,ClassName,,,public,false,false,1
method,methodName,returnType,param1:type1;param2:type2,public,false,false,10
field,fieldName,fieldType,,private,false,true,5
```

### 詳細仕様

#### ヘッダー行
```csv
Type,Name,ReturnType,Parameters,Access,Static,Final,Line
```

#### データ行形式

##### クラス行
- **Type**: `class`, `interface`, `enum`
- **Name**: クラス名（パッケージ名含む）
- **ReturnType**: 空
- **Parameters**: 空
- **Access**: アクセス修飾子
- **Static**: `false`
- **Final**: `true`/`false`
- **Line**: 定義行番号

##### メソッド行
- **Type**: `method`, `constructor`
- **Name**: メソッド名
- **ReturnType**: 戻り値の型
- **Parameters**: `param1:type1;param2:type2` 形式
- **Access**: アクセス修飾子
- **Static**: `true`/`false`
- **Final**: `true`/`false`
- **Line**: 定義行番号

##### フィールド行
- **Type**: `field`, `property`
- **Name**: フィールド名
- **ReturnType**: フィールドの型
- **Parameters**: 空
- **Access**: アクセス修飾子
- **Static**: `true`/`false`
- **Final**: `true`/`false`
- **Line**: 定義行番号

### CSVエスケープルール
- **カンマ**: フィールド内のカンマは `"` で囲む
- **引用符**: フィールド内の `"` は `""` でエスケープ
- **改行**: フィールド内の改行は `"` で囲む

### パラメータエンコーディング
- **区切り文字**: セミコロン (`;`)
- **型と名前**: コロン (`:`) で区切り
- **例**: `userId:Long;options:Map<String,Object>`

## フォーマット検証ルール

### 共通検証ルール
1. **文字エンコーディング**: UTF-8であること
2. **改行コード**: LF統一
3. **空行**: 不要な空行がないこと
4. **文字制限**: 1行あたり1000文字以内

### Markdown形式検証ルール
1. **ヘッダー**: `#` で始まること
2. **テーブル**: 正しいMarkdownテーブル形式
3. **セパレータ**: `|---|` 形式のセパレータ行
4. **セル内容**: パイプ文字のエスケープ

### CSV形式検証ルール
1. **ヘッダー**: 必須フィールドがすべて存在
2. **データ行**: ヘッダーと同じ列数
3. **エスケープ**: RFC 4180準拠
4. **文字制限**: フィールドあたり500文字以内

## エラーハンドリング仕様

### パースエラー時の動作
- **空ファイル**: 適切なエラーメッセージ
- **構文エラー**: 部分的な結果を返す
- **エンコーディングエラー**: UTF-8変換を試行

### フォーマットエラー時の動作
- **不正な文字**: エスケープまたは除去
- **長すぎる行**: 切り詰めて警告
- **不完全なデータ**: 利用可能な情報のみ出力

## バージョン管理

### フォーマットバージョン
- **現在のバージョン**: 1.0
- **互換性**: 後方互換性を維持
- **変更管理**: セマンティックバージョニング

### 変更履歴
- **1.0.0**: 初期仕様
- **1.0.1**: CSV形式のパラメータエンコーディング改善
- **1.0.2**: Markdown形式のエスケープルール明確化

## 実装ガイドライン

### パフォーマンス要件
- **大きなファイル**: 10MB以上のファイルでも5秒以内
- **メモリ使用量**: ファイルサイズの3倍以内
- **並行処理**: スレッドセーフな実装

### 品質要件
- **テストカバレッジ**: 90%以上
- **型安全性**: 厳密な型チェック
- **エラーハンドリング**: 適切な例外処理

### セキュリティ要件
- **パス検証**: ディレクトリトラバーサル防止
- **入力検証**: 悪意のある入力の検証
- **リソース制限**: DoS攻撃の防止

## テスト仕様

### 単体テスト
- **フォーマッター**: 各フォーマットタイプ
- **バリデーター**: 検証ルール
- **エラーハンドリング**: 異常系テスト

### 統合テスト
- **エンドツーエンド**: 完全なパイプライン
- **クロスコンポーネント**: インターフェース間の一貫性
- **パフォーマンス**: 大きなファイルでの動作

### 回帰テスト
- **ゴールデンマスター**: 既知の正しい出力との比較
- **フォーマット安定性**: 出力の一貫性
- **互換性**: バージョン間の互換性

## 付録

### サンプル出力

#### Full Format サンプル
```markdown
# com.example.service.UserService

## Class Info
| Property | Value |
|----------|-------|
| Name | UserService |
| Package | com.example.service |
| Type | class |
| Access | public |
| Abstract | false |
| Final | false |

## Methods
| Name | Return Type | Parameters | Access | Line |
|------|-------------|------------|--------|------|
| UserService | void | UserRepository repository | public | 15 |
| findById | User | Long id | public | 20 |
| save | User | User user | public | 25 |

## Fields
| Name | Type | Access | Static | Final | Line |
|------|------|--------|--------|-------|------|
| repository | UserRepository | private | false | true | 10 |
| logger | Logger | private | true | true | 12 |

## Imports
| Import | Type |
|--------|------|
| java.util.List | import |
| java.util.Optional | import |
| org.slf4j.Logger | import |
```

#### Compact Format サンプル
```markdown
# UserService

## Info
| Property | Value |
|----------|-------|
| Type | class |
| Methods | 3 |
| Fields | 2 |

## Methods
| Name | Return Type | Access | Line |
|------|-------------|--------|------|
| UserService | void | public | 15 |
| findById | User | public | 20 |
| save | User | public | 25 |

## Fields
| Name | Type | Access | Line |
|------|------|--------|------|
| repository | UserRepository | private | 10 |
| logger | Logger | private | 12 |
```

#### CSV Format サンプル
```csv
Type,Name,ReturnType,Parameters,Access,Static,Final,Line
class,com.example.service.UserService,,,public,false,false,8
method,UserService,void,repository:UserRepository,public,false,false,15
method,findById,User,id:Long,public,false,false,20
method,save,User,user:User,public,false,false,25
field,repository,UserRepository,,private,false,true,10
field,logger,Logger,,private,true,true,12
```

### 関連ドキュメント
- [API仕様書](api_specifications.md)
- [テスト戦略](testing_strategy.md)
- [開発ガイドライン](development_guidelines.md)
