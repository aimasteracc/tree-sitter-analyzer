# Tree-sitter Analyzer データモデル API仕様

**Version**: 1.8.0  
**Date**: 2025-10-13  
**Language Support**: Java, JavaScript, TypeScript, Python, Markdown, HTML, CSS

## 概要

Tree-sitter Analyzerは、多様なプログラミング言語とマークアップ言語に対応した統一的なデータモデルを提供します。v1.8.0では、HTML/CSS専用の特殊化されたデータモデルが追加され、Web技術の解析能力が大幅に向上しました。

## 基本データモデル

### CodeElement（基底クラス）

すべてのコード要素の基底となるクラスです。

```python
class CodeElement:
    name: str                    # 要素名
    start_line: int             # 開始行（1ベース）
    end_line: int               # 終了行（1ベース）
    start_column: int           # 開始列（0ベース）
    end_column: int             # 終了列（0ベース）
    language: str               # プログラミング言語
    element_type: str           # 要素タイプ（自動設定）
    content: Optional[str]      # 要素の内容
    metadata: Dict[str, Any]    # 追加メタデータ
```

**共通プロパティ**:
- `element_type`: 自動的に設定される要素タイプ識別子
- `position`: 位置情報の統一アクセス
- `size`: 要素のサイズ（行数、文字数）

### AnalysisResult

解析結果を格納するコンテナクラスです。

```python
class AnalysisResult:
    file_path: str                      # 解析対象ファイルパス
    language: str                       # 検出された言語
    elements: List[CodeElement]         # 抽出された要素リスト
    total_lines: int                    # 総行数
    analysis_time: float                # 解析時間（秒）
    metadata: Dict[str, Any]            # 追加メタデータ
```

## HTML専用データモデル

### MarkupElement

HTML要素を表現する特殊化されたデータモデルです。

```python
class MarkupElement(CodeElement):
    tag_name: str                       # HTMLタグ名（例: "div", "span"）
    attributes: Dict[str, str]          # 属性辞書（例: {"class": "container", "id": "main"}）
    element_class: str                  # 要素分類（自動分類）
    parent: Optional['MarkupElement']   # 親要素への参照
    children: List['MarkupElement']     # 子要素のリスト
    is_self_closing: bool               # 自己終了タグかどうか
    depth: int                          # ネスト深度
```

**要素分類システム**:

#### 構造要素（structural_elements）
- `html`, `head`, `body`, `header`, `footer`, `nav`, `main`, `section`, `article`, `aside`
- **特徴**: ページの基本構造を定義する要素

#### コンテンツ要素（content_elements）
- `h1`-`h6`, `p`, `span`, `div`, `blockquote`, `pre`, `code`
- **特徴**: テキストコンテンツを含む要素

#### メディア要素（media_elements）
- `img`, `video`, `audio`, `canvas`, `svg`, `picture`, `source`
- **特徴**: メディアコンテンツを表示する要素

#### フォーム要素（form_elements）
- `form`, `input`, `textarea`, `select`, `option`, `button`, `label`, `fieldset`
- **特徴**: ユーザー入力を処理する要素

#### リスト要素（list_elements）
- `ul`, `ol`, `li`, `dl`, `dt`, `dd`
- **特徴**: リスト構造を表現する要素

#### テーブル要素（table_elements）
- `table`, `thead`, `tbody`, `tfoot`, `tr`, `th`, `td`, `caption`, `colgroup`, `col`
- **特徴**: 表形式データを表現する要素

#### メタ要素（meta_elements）
- `meta`, `title`, `link`, `script`, `style`, `base`
- **特徴**: ドキュメントのメタデータを定義する要素

**使用例**:
```python
# div要素の作成
div_element = MarkupElement(
    name="main-container",
    start_line=10,
    end_line=25,
    language="html",
    tag_name="div",
    attributes={"class": "container", "id": "main"},
    element_class="content",  # 自動分類
    is_self_closing=False,
    depth=2
)

# 属性アクセス
class_name = div_element.attributes.get("class", "")
has_id = "id" in div_element.attributes
```

## CSS専用データモデル

### StyleElement

CSS規則を表現する特殊化されたデータモデルです。

```python
class StyleElement(CodeElement):
    selector: str                       # CSSセレクタ（例: ".container", "#main"）
    properties: Dict[str, str]          # CSSプロパティ辞書
    selector_type: str                  # セレクタタイプ（自動分類）
    specificity: int                    # CSS詳細度
    media_query: Optional[str]          # メディアクエリ（該当する場合）
    is_nested: bool                     # ネストされた規則かどうか
    parent_rule: Optional['StyleElement'] # 親規則への参照
```

**セレクタタイプ分類**:

#### 要素セレクタ（element）
- `div`, `p`, `h1`, `span` など
- **特徴**: HTMLタグ名を直接指定

#### クラスセレクタ（class）
- `.container`, `.btn`, `.header` など
- **特徴**: `.`で始まるクラス名指定

#### IDセレクタ（id）
- `#main`, `#header`, `#sidebar` など
- **特徴**: `#`で始まるID指定

#### 属性セレクタ（attribute）
- `[type="text"]`, `[data-role="button"]` など
- **特徴**: `[]`で囲まれた属性指定

#### 疑似クラス（pseudo-class）
- `:hover`, `:focus`, `:nth-child()` など
- **特徴**: `:`で始まる疑似クラス

#### 疑似要素（pseudo-element）
- `::before`, `::after`, `::first-line` など
- **特徴**: `::`で始まる疑似要素

#### 複合セレクタ（compound）
- `.container .item`, `div > p`, `h1 + p` など
- **特徴**: 複数のセレクタの組み合わせ

**プロパティ分類システム**:

#### レイアウトプロパティ（layout_properties）
- `display`, `position`, `float`, `clear`, `flex`, `grid`
- **特徴**: 要素の配置とレイアウトを制御

#### サイズプロパティ（sizing_properties）
- `width`, `height`, `margin`, `padding`, `border`
- **特徴**: 要素のサイズと間隔を制御

#### タイポグラフィプロパティ（typography_properties）
- `font-family`, `font-size`, `line-height`, `text-align`, `color`
- **特徴**: テキストの表示を制御

#### 背景・色プロパティ（color_properties）
- `background`, `color`, `border-color`, `box-shadow`
- **特徴**: 色と背景の表示を制御

#### アニメーションプロパティ（animation_properties）
- `transition`, `animation`, `transform`, `opacity`
- **特徴**: 動的効果を制御

**使用例**:
```python
# CSS規則の作成
css_rule = StyleElement(
    name=".container",
    start_line=5,
    end_line=12,
    language="css",
    selector=".container",
    properties={
        "width": "100%",
        "max-width": "1200px",
        "margin": "0 auto",
        "padding": "20px"
    },
    selector_type="class",  # 自動分類
    specificity=10
)

# プロパティアクセス
width = css_rule.properties.get("width", "auto")
has_margin = "margin" in css_rule.properties
```

## 要素分類とカテゴリ化

### HTML要素の自動分類

HTML要素は、その意味的役割に基づいて自動的に分類されます：

```python
def classify_html_element(tag_name: str, attributes: Dict[str, str]) -> str:
    """HTML要素を自動分類"""
    structural_tags = {"html", "head", "body", "header", "footer", "nav", "main", "section", "article", "aside"}
    content_tags = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "div", "blockquote", "pre", "code"}
    media_tags = {"img", "video", "audio", "canvas", "svg", "picture", "source"}
    form_tags = {"form", "input", "textarea", "select", "option", "button", "label", "fieldset"}
    list_tags = {"ul", "ol", "li", "dl", "dt", "dd"}
    table_tags = {"table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col"}
    meta_tags = {"meta", "title", "link", "script", "style", "base"}
    
    if tag_name in structural_tags:
        return "structural"
    elif tag_name in content_tags:
        return "content"
    elif tag_name in media_tags:
        return "media"
    elif tag_name in form_tags:
        return "form"
    elif tag_name in list_tags:
        return "list"
    elif tag_name in table_tags:
        return "table"
    elif tag_name in meta_tags:
        return "meta"
    else:
        return "other"
```

### CSS規則の自動分類

CSS規則は、セレクタの形式に基づいて自動的に分類されます：

```python
def classify_css_selector(selector: str) -> str:
    """CSSセレクタを自動分類"""
    selector = selector.strip()
    
    if selector.startswith('.'):
        return "class"
    elif selector.startswith('#'):
        return "id"
    elif selector.startswith('[') and selector.endswith(']'):
        return "attribute"
    elif '::' in selector:
        return "pseudo-element"
    elif ':' in selector:
        return "pseudo-class"
    elif any(combinator in selector for combinator in [' ', '>', '+', '~']):
        return "compound"
    else:
        return "element"
```

## データモデルの拡張

### カスタム要素タイプの追加

新しい要素タイプを追加する場合：

```python
class CustomElement(CodeElement):
    """カスタム要素タイプの例"""
    custom_property: str
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.element_type = "custom"
```

### メタデータの活用

`metadata`フィールドを使用して追加情報を格納：

```python
element = MarkupElement(
    name="interactive-button",
    tag_name="button",
    metadata={
        "accessibility": {
            "aria_label": "Submit form",
            "keyboard_accessible": True
        },
        "performance": {
            "critical_path": True,
            "load_priority": "high"
        },
        "seo": {
            "importance": "medium"
        }
    }
)
```

## 互換性とマイグレーション

### 既存コードとの互換性

v1.8.0では、既存の`CodeElement`ベースのコードは完全に互換性を保持します：

```python
# v1.7.x のコード（そのまま動作）
elements = analyzer.analyze_file("example.py")
for element in elements:
    print(f"{element.name}: {element.element_type}")

# v1.8.0 の新機能（HTML/CSS対応）
html_elements = analyzer.analyze_file("example.html")
for element in html_elements:
    if isinstance(element, MarkupElement):
        print(f"HTML: {element.tag_name} with class {element.attributes.get('class', 'none')}")
    elif isinstance(element, StyleElement):
        print(f"CSS: {element.selector} ({element.selector_type})")
```

### 型チェックとバリデーション

データモデルは実行時型チェックをサポートします：

```python
from tree_sitter_analyzer.models import MarkupElement, StyleElement

def process_web_elements(elements: List[CodeElement]):
    for element in elements:
        if isinstance(element, MarkupElement):
            # HTML要素の処理
            validate_html_element(element)
        elif isinstance(element, StyleElement):
            # CSS要素の処理
            validate_css_element(element)
        else:
            # 従来の要素の処理
            process_generic_element(element)
```

## パフォーマンス考慮事項

### メモリ効率

- 大規模なHTMLファイルでは、`parent`と`children`の循環参照に注意
- 必要に応じて弱参照（weak reference）を使用
- `metadata`フィールドは必要な場合のみ使用

### 処理速度

- 要素分類は初回作成時に一度だけ実行
- プロパティアクセスは辞書ベースで高速
- 大量の要素を扱う場合は、ジェネレータパターンを推奨

## API使用例

### 基本的な解析ワークフロー

```python
from tree_sitter_analyzer import TreeSitterAnalyzer
from tree_sitter_analyzer.models import MarkupElement, StyleElement

# アナライザーの初期化
analyzer = TreeSitterAnalyzer()

# HTMLファイルの解析
result = analyzer.analyze_file("index.html")

# 要素タイプ別の処理
structural_elements = []
content_elements = []
style_elements = []

for element in result.elements:
    if isinstance(element, MarkupElement):
        if element.element_class == "structural":
            structural_elements.append(element)
        elif element.element_class == "content":
            content_elements.append(element)
    elif isinstance(element, StyleElement):
        style_elements.append(element)

# 統計情報の出力
print(f"構造要素: {len(structural_elements)}")
print(f"コンテンツ要素: {len(content_elements)}")
print(f"スタイル規則: {len(style_elements)}")
```

### 高度な解析例

```python
# セレクタタイプ別のCSS統計
css_stats = {}
for element in style_elements:
    selector_type = element.selector_type
    css_stats[selector_type] = css_stats.get(selector_type, 0) + 1

print("CSS セレクタ統計:")
for selector_type, count in css_stats.items():
    print(f"  {selector_type}: {count}")

# HTML階層構造の分析
def analyze_html_hierarchy(elements):
    max_depth = 0
    depth_distribution = {}
    
    for element in elements:
        if isinstance(element, MarkupElement):
            depth = element.depth
            max_depth = max(max_depth, depth)
            depth_distribution[depth] = depth_distribution.get(depth, 0) + 1
    
    return max_depth, depth_distribution

max_depth, depth_dist = analyze_html_hierarchy(result.elements)
print(f"最大ネスト深度: {max_depth}")
print(f"深度分布: {depth_dist}")
```

## エラーハンドリング

### 型安全性

```python
def safe_element_access(element: CodeElement) -> Dict[str, Any]:
    """型安全な要素アクセス"""
    info = {
        "name": element.name,
        "type": element.element_type,
        "language": element.language
    }
    
    if isinstance(element, MarkupElement):
        info.update({
            "tag_name": element.tag_name,
            "attributes": element.attributes,
            "element_class": element.element_class
        })
    elif isinstance(element, StyleElement):
        info.update({
            "selector": element.selector,
            "properties": element.properties,
            "selector_type": element.selector_type
        })
    
    return info
```

### バリデーション

```python
def validate_markup_element(element: MarkupElement) -> bool:
    """MarkupElementのバリデーション"""
    if not element.tag_name:
        raise ValueError("tag_name is required for MarkupElement")
    
    if not isinstance(element.attributes, dict):
        raise TypeError("attributes must be a dictionary")
    
    if element.depth < 0:
        raise ValueError("depth must be non-negative")
    
    return True

def validate_style_element(element: StyleElement) -> bool:
    """StyleElementのバリデーション"""
    if not element.selector:
        raise ValueError("selector is required for StyleElement")
    
    if not isinstance(element.properties, dict):
        raise TypeError("properties must be a dictionary")
    
    if element.specificity < 0:
        raise ValueError("specificity must be non-negative")
    
    return True
```

## 今後の拡張予定

### v1.9.0での予定機能

- **JavaScript/TypeScript DOM操作の解析**: HTML要素とJavaScriptコードの関連性分析
- **CSS-in-JS対応**: styled-componentsやemotion等のライブラリサポート
- **アクセシビリティ分析**: ARIA属性とセマンティック構造の検証
- **SEO分析**: メタタグとコンテンツ構造の最適化提案

### 長期ロードマップ

- **Vue.js/React/Angular対応**: フレームワーク固有のコンポーネント解析
- **SCSS/Less対応**: CSS前処理言語のサポート
- **WebAssembly対応**: WASM モジュールの解析機能
- **パフォーマンス分析**: Critical Path CSS、Lazy Loading等の最適化分析

## 参考資料

- [HTML Living Standard](https://html.spec.whatwg.org/)
- [CSS Specifications](https://www.w3.org/Style/CSS/specs.en.html)
- [Tree-sitter Documentation](https://tree-sitter.github.io/tree-sitter/)
- [MDN Web Docs](https://developer.mozilla.org/)

---

このドキュメントは、Tree-sitter Analyzer v1.8.0の新しいデータモデルの完全な仕様を提供します。質問や提案がある場合は、GitHubのIssuesまたはDiscussionsをご利用ください。