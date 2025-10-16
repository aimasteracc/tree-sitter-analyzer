# Tree-sitter Analyzer 開発者ガイド

**Version**: 1.8.0  
**Date**: 2025-10-13  
**Target Audience**: プラグイン開発者、カスタムフォーマッター作成者
**Language Support**: Java, JavaScript, TypeScript, Python, Markdown, HTML, CSS

## 概要

このガイドでは、Tree-sitter Analyzerの拡張機能を開発する方法について詳しく説明します。新しい言語プラグインの作成、カスタムフォーマッターの実装、アーキテクチャの理解など、開発者が知っておくべき情報を包括的に提供します。

## 目次

1. [アーキテクチャ概要](#アーキテクチャ概要)
2. [開発環境のセットアップ](#開発環境のセットアップ)
3. [新しい言語プラグインの作成](#新しい言語プラグインの作成)
4. [HTML/CSSプラグインの開発](#htmlcssプラグインの開発)
5. [カスタムフォーマッターの作成](#カスタムフォーマッターの作成)
6. [データモデルの拡張](#データモデルの拡張)
7. [新しいクエリシステム](#新しいクエリシステム)
8. [テストの作成](#テストの作成)
9. [FileOutputManagerベストプラクティス](#fileoutputmanagerベストプラクティス)
10. [パフォーマンス最適化](#パフォーマンス最適化)
11. [デバッグとトラブルシューティング](#デバッグとトラブルシューティング)

## アーキテクチャ概要

### システム構成

```
Tree-sitter Analyzer
├── Core Engine
│   ├── Parser (tree-sitter integration)
│   ├── Query Service (language-specific queries)
│   └── Analysis Engine (element extraction)
├── Plugin System
│   ├── Language Plugins (extensible)
│   └── Plugin Registry (dynamic loading)
├── Formatter System
│   ├── Base Formatter (abstract interface)
│   ├── Formatter Registry (dynamic registration)
│   └── Built-in Formatters (language-specific)
├── Data Models
│   ├── CodeElement (base class)
│   ├── MarkupElement (HTML-specific)
│   └── StyleElement (CSS-specific)
└── Interfaces
    ├── CLI Interface
    ├── MCP Server Interface
    └── API Interface
```

### 設計パターン

1. **Plugin Pattern**: 言語サポートの動的拡張
2. **Strategy Pattern**: フォーマット処理の切り替え
3. **Registry Pattern**: プラグイン・フォーマッターの管理
4. **Factory Pattern**: オブジェクト生成の抽象化
5. **Template Method Pattern**: 共通処理フローの定義

## 開発環境のセットアップ

### 必要な依存関係

```bash
# 基本開発環境
pip install tree-sitter-analyzer[dev]

# 追加の開発ツール
pip install pytest pytest-cov black isort mypy

# Tree-sitter言語パッケージ（必要に応じて）
pip install tree-sitter-python tree-sitter-javascript tree-sitter-java
pip install tree-sitter-html tree-sitter-css  # HTML/CSS対応
```

### プロジェクト構造

```
your_extension/
├── setup.py
├── README.md
├── your_extension/
│   ├── __init__.py
│   ├── plugins/
│   │   ├── __init__.py
│   │   └── your_language_plugin.py
│   ├── formatters/
│   │   ├── __init__.py
│   │   └── your_formatter.py
│   └── queries/
│       └── your_language.py
├── tests/
│   ├── __init__.py
│   ├── test_plugin.py
│   └── test_formatter.py
└── examples/
    └── sample_files/
```

## 新しい言語プラグインの作成

### 基本的なプラグイン実装

```python
# your_extension/plugins/your_language_plugin.py
from typing import List, Dict, Any, Optional
from tree_sitter_analyzer.plugins.base import LanguagePlugin
from tree_sitter_analyzer.models import CodeElement
import tree_sitter_your_language as ts_your_language

class YourLanguagePlugin(LanguagePlugin):
    """あなたの言語用プラグイン"""
    
    def __init__(self):
        super().__init__()
        self._language = None
    
    def get_language_name(self) -> str:
        """言語名を返す"""
        return "your_language"
    
    def get_file_extensions(self) -> List[str]:
        """対応ファイル拡張子を返す"""
        return [".yourlang", ".yl"]
    
    def get_tree_sitter_language(self):
        """Tree-sitter言語オブジェクトを返す"""
        if self._language is None:
            self._language = ts_your_language.language()
        return self._language
    
    def get_queries(self) -> Dict[str, str]:
        """言語固有のクエリを返す"""
        return {
            "functions": """
                (function_declaration
                    name: (identifier) @name
                    parameters: (parameter_list) @params
                    body: (block) @body) @function
            """,
            "classes": """
                (class_declaration
                    name: (identifier) @name
                    body: (class_body) @body) @class
            """,
            "variables": """
                (variable_declaration
                    (variable_declarator
                        name: (identifier) @name
                        value: (_)? @value)) @variable
            """,
            "imports": """
                (import_declaration
                    source: (string_literal) @source) @import
            """
        }
    
    def create_element(self, node, element_type: str, **kwargs) -> CodeElement:
        """ノードからCodeElementを作成"""
        return CodeElement(
            name=self._extract_name(node, element_type),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            language=self.get_language_name(),
            content=self._extract_content(node),
            metadata=self._extract_metadata(node, element_type)
        )
```

## HTML/CSSプラグインの開発

### HTML専用プラグインの実装

```python
# your_extension/plugins/html_plugin.py
from typing import List, Dict, Any, Optional
from tree_sitter_analyzer.plugins.base import LanguagePlugin
from tree_sitter_analyzer.models import MarkupElement
import tree_sitter_html as ts_html

class CustomHtmlPlugin(LanguagePlugin):
    """カスタムHTML解析プラグイン"""
    
    def __init__(self):
        super().__init__()
        self._language = None
    
    def get_language_name(self) -> str:
        return "html"
    
    def get_file_extensions(self) -> List[str]:
        return [".html", ".htm", ".xhtml"]
    
    def get_tree_sitter_language(self):
        if self._language is None:
            self._language = ts_html.language()
        return self._language
    
    def get_queries(self) -> Dict[str, str]:
        """HTML専用クエリ定義"""
        return {
            "elements": """
                (element
                    (start_tag
                        (tag_name) @tag_name
                        (attribute
                            (attribute_name) @attr_name
                            (quoted_attribute_value) @attr_value)*) @start_tag
                    (end_tag)? @end_tag) @element
            """,
            "self_closing": """
                (self_closing_tag
                    (tag_name) @tag_name
                    (attribute
                        (attribute_name) @attr_name
                        (quoted_attribute_value) @attr_value)*) @self_closing
            """,
            "text_content": """
                (text) @text
            """,
            "comments": """
                (comment) @comment
            """,
            "doctype": """
                (doctype) @doctype
            """
        }
    
    def create_element(self, node, element_type: str, **kwargs) -> MarkupElement:
        """HTMLノードからMarkupElementを作成"""
        tag_name = self._extract_tag_name(node)
        attributes = self._extract_attributes(node)
        element_class = self._classify_html_element(tag_name, attributes)
        
        return MarkupElement(
            name=self._generate_element_name(tag_name, attributes),
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            language="html",
            tag_name=tag_name,
            attributes=attributes,
            element_class=element_class,
            is_self_closing=element_type == "self_closing",
            depth=self._calculate_depth(node),
            content=self._extract_text_content(node)
        )
    
    def _extract_tag_name(self, node) -> str:
        """タグ名を抽出"""
        if node.type == "element":
            start_tag = node.child_by_field_name("start_tag")
            if start_tag:
                tag_name_node = start_tag.child_by_field_name("name")
                if tag_name_node:
                    return tag_name_node.text.decode('utf-8')
        elif node.type == "self_closing_tag":
            tag_name_node = node.child_by_field_name("name")
            if tag_name_node:
                return tag_name_node.text.decode('utf-8')
        return "unknown"
    
    def _extract_attributes(self, node) -> Dict[str, str]:
        """属性を抽出"""
        attributes = {}
        
        # start_tagまたはself_closing_tagから属性を取得
        tag_node = None
        if node.type == "element":
            tag_node = node.child_by_field_name("start_tag")
        elif node.type == "self_closing_tag":
            tag_node = node
        
        if tag_node:
            for child in tag_node.children:
                if child.type == "attribute":
                    attr_name = None
                    attr_value = None
                    
                    for attr_child in child.children:
                        if attr_child.type == "attribute_name":
                            attr_name = attr_child.text.decode('utf-8')
                        elif attr_child.type == "quoted_attribute_value":
                            # クォートを除去
                            attr_value = attr_child.text.decode('utf-8')[1:-1]
                    
                    if attr_name:
                        attributes[attr_name] = attr_value or ""
        
        return attributes
    
    def _classify_html_element(self, tag_name: str, attributes: Dict[str, str]) -> str:
        """HTML要素を分類"""
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

### CSS専用プラグインの実装

```python
# your_extension/plugins/css_plugin.py
from typing import List, Dict, Any, Optional
from tree_sitter_analyzer.plugins.base import LanguagePlugin
from tree_sitter_analyzer.models import StyleElement
import tree_sitter_css as ts_css

class CustomCssPlugin(LanguagePlugin):
    """カスタムCSS解析プラグイン"""
    
    def __init__(self):
        super().__init__()
        self._language = None
    
    def get_language_name(self) -> str:
        return "css"
    
    def get_file_extensions(self) -> List[str]:
        return [".css", ".scss", ".sass", ".less"]
    
    def get_tree_sitter_language(self):
        if self._language is None:
            self._language = ts_css.language()
        return self._language
    
    def get_queries(self) -> Dict[str, str]:
        """CSS専用クエリ定義"""
        return {
            "rules": """
                (rule_set
                    (selectors
                        (selector) @selector)
                    (block
                        (declaration
                            (property_name) @property
                            (value) @value)*) @declarations) @rule
            """,
            "at_rules": """
                (at_rule
                    (at_keyword) @keyword
                    (block)? @block) @at_rule
            """,
            "media_queries": """
                (media_statement
                    (media_query_list) @media_query
                    (block) @block) @media
            """,
            "keyframes": """
                (keyframes_statement
                    (keyframes_name) @name
                    (keyframe_block_list) @keyframes) @keyframes_rule
            """,
            "imports": """
                (import_statement
                    (string_value) @import_path) @import
            """,
            "variables": """
                (declaration
                    (property_name) @var_name
                    (value) @var_value) @variable
                (#match? @var_name "^--")
            """
        }
    
    def create_element(self, node, element_type: str, **kwargs) -> StyleElement:
        """CSSノードからStyleElementを作成"""
        selector = self._extract_selector(node)
        properties = self._extract_properties(node)
        selector_type = self._classify_css_selector(selector)
        specificity = self._calculate_specificity(selector)
        
        return StyleElement(
            name=selector or f"css_{element_type}",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            start_column=node.start_point[1],
            end_column=node.end_point[1],
            language="css",
            selector=selector,
            properties=properties,
            selector_type=selector_type,
            specificity=specificity,
            media_query=kwargs.get('media_query'),
            is_nested=kwargs.get('is_nested', False),
            content=node.text.decode('utf-8')
        )
    
    def _extract_selector(self, node) -> str:
        """セレクタを抽出"""
        if node.type == "rule_set":
            selectors_node = node.child_by_field_name("selectors")
            if selectors_node:
                return selectors_node.text.decode('utf-8').strip()
        elif node.type == "at_rule":
            # @media, @keyframes等の処理
            return node.children[0].text.decode('utf-8') if node.children else ""
        return ""
    
    def _extract_properties(self, node) -> Dict[str, str]:
        """CSSプロパティを抽出"""
        properties = {}
        
        if node.type == "rule_set":
            block_node = node.child_by_field_name("block")
            if block_node:
                for child in block_node.children:
                    if child.type == "declaration":
                        prop_name = None
                        prop_value = None
                        
                        for decl_child in child.children:
                            if decl_child.type == "property_name":
                                prop_name = decl_child.text.decode('utf-8')
                            elif decl_child.type == "value":
                                prop_value = decl_child.text.decode('utf-8').strip()
                        
                        if prop_name and prop_value:
                            properties[prop_name] = prop_value
        
        return properties
    
    def _classify_css_selector(self, selector: str) -> str:
        """CSSセレクタを分類"""
        if not selector:
            return "unknown"
        
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
        elif selector.startswith('@'):
            return "at-rule"
        else:
            return "element"
    
    def _calculate_specificity(self, selector: str) -> int:
        """CSS詳細度を計算"""
        if not selector:
            return 0
        
        # 簡単な詳細度計算（実際の実装ではより詳細な計算が必要）
        specificity = 0
        
        # ID セレクタ: 100点
        specificity += selector.count('#') * 100
        
        # クラス、属性、疑似クラス: 10点
        specificity += selector.count('.') * 10
        specificity += selector.count('[') * 10
        specificity += selector.count(':') * 10
        
        # 要素セレクタ: 1点
        # 簡略化された計算
        elements = selector.replace('.', ' ').replace('#', ' ').replace('[', ' ').replace(':', ' ')
        element_count = len([part for part in elements.split() if part and not part.startswith('@')])
        specificity += element_count
        
        return specificity
```

### Web技術統合プラグイン

```python
# your_extension/plugins/web_integration_plugin.py
from typing import List, Dict, Any, Optional, Union
from tree_sitter_analyzer.plugins.base import LanguagePlugin
from tree_sitter_analyzer.models import CodeElement, MarkupElement, StyleElement

class WebIntegrationPlugin(LanguagePlugin):
    """HTML/CSS/JavaScript統合解析プラグイン"""
    
    def __init__(self):
        super().__init__()
        self.html_plugin = CustomHtmlPlugin()
        self.css_plugin = CustomCssPlugin()
    
    def analyze_web_document(self, html_content: str) -> Dict[str, List[CodeElement]]:
        """Webドキュメントを統合解析"""
        results = {
            "html_elements": [],
            "css_rules": [],
            "inline_styles": [],
            "script_blocks": []
        }
        
        # HTML解析
        html_tree = self.html_plugin.parse_content(html_content)
        html_elements = self.html_plugin.extract_elements(html_tree)
        results["html_elements"] = html_elements
        
        # インラインCSS抽出
        for element in html_elements:
            if isinstance(element, MarkupElement):
                if element.tag_name == "style":
                    css_content = element.content
                    if css_content:
                        css_rules = self._parse_inline_css(css_content, element.start_line)
                        results["inline_styles"].extend(css_rules)
                
                # style属性の解析
                if "style" in element.attributes:
                    style_rules = self._parse_style_attribute(
                        element.attributes["style"],
                        element.start_line
                    )
                    results["inline_styles"].extend(style_rules)
        
        return results
    
    def _parse_inline_css(self, css_content: str, base_line: int) -> List[StyleElement]:
        """インラインCSSを解析"""
        css_tree = self.css_plugin.parse_content(css_content)
        css_elements = self.css_plugin.extract_elements(css_tree)
        
        # 行番号を調整
        for element in css_elements:
            if isinstance(element, StyleElement):
                element.start_line += base_line - 1
                element.end_line += base_line - 1
        
        return css_elements
    
    def _parse_style_attribute(self, style_attr: str, line_number: int) -> List[StyleElement]:
        """style属性を解析"""
        # style属性の内容をCSS宣言として解析
        css_content = f"dummy {{ {style_attr} }}"
        css_tree = self.css_plugin.parse_content(css_content)
        
        # 簡略化された処理
        properties = {}
        declarations = style_attr.split(';')
        
        for decl in declarations:
            if ':' in decl:
                prop, value = decl.split(':', 1)
                properties[prop.strip()] = value.strip()
        
        if properties:
            return [StyleElement(
                name="inline_style",
                start_line=line_number,
                end_line=line_number,
                start_column=0,
                end_column=len(style_attr),
                language="css",
                selector="[inline]",
                properties=properties,
                selector_type="inline",
                specificity=1000  # インラインスタイルは高い詳細度
            )]
        
        return []
    
    def analyze_css_html_relationships(self, html_elements: List[MarkupElement],
                                     css_rules: List[StyleElement]) -> Dict[str, Any]:
        """CSS-HTML関係性を分析"""
        relationships = {
            "matched_elements": [],
            "unused_selectors": [],
            "missing_styles": [],
            "specificity_conflicts": []
        }
        
        # セレクタマッチング（簡略化）
        for css_rule in css_rules:
            if isinstance(css_rule, StyleElement):
                matched = False
                
                for html_element in html_elements:
                    if isinstance(html_element, MarkupElement):
                        if self._selector_matches_element(css_rule.selector, html_element):
                            relationships["matched_elements"].append({
                                "css_rule": css_rule,
                                "html_element": html_element,
                                "match_type": css_rule.selector_type
                            })
                            matched = True
                
                if not matched:
                    relationships["unused_selectors"].append(css_rule)
        
        return relationships
    
    def _selector_matches_element(self, selector: str, element: MarkupElement) -> bool:
        """セレクタが要素にマッチするかチェック（簡略化）"""
        if not selector or not element:
            return False
        
        # 要素セレクタ
        if selector == element.tag_name:
            return True
        
        # クラスセレクタ
        if selector.startswith('.'):
            class_name = selector[1:]
            element_classes = element.attributes.get('class', '').split()
            return class_name in element_classes
        
        # IDセレクタ
        if selector.startswith('#'):
            id_name = selector[1:]
            return element.attributes.get('id') == id_name
        
        return False
```

## カスタムフォーマッターの作成

### 基本的なフォーマッター実装

```python
# your_extension/formatters/your_formatter.py
from typing import List, Dict, Any
from tree_sitter_analyzer.formatters.base_formatter import BaseFormatter
from tree_sitter_analyzer.models import CodeElement

class YourCustomFormatter(BaseFormatter):
    """カスタムフォーマッターの実装例"""
    
    def __init__(self, **options):
        super().__init__()
        self.options = options
        self.indent_size = options.get('indent_size', 2)
        self.include_metadata = options.get('include_metadata', True)
        self.color_output = options.get('color_output', False)
    
    def format(self, elements: List[CodeElement]) -> str:
        """要素リストをカスタムフォーマットで出力"""
        if not elements:
            return self._format_empty_result()
        
        output_parts = []
        
        # ヘッダー情報
        output_parts.append(self._format_header(elements))
        
        # 要素をタイプ別にグループ化
        grouped_elements = self._group_elements_by_type(elements)
        
        # 各グループをフォーマット
        for element_type, element_list in grouped_elements.items():
            section = self._format_element_section(element_type, element_list)
            output_parts.append(section)
        
        # フッター情報
        if self.include_metadata:
            output_parts.append(self._format_footer(elements))
        
        return '\n'.join(output_parts)
```

### JSON出力フォーマッター

```python
class JsonFormatter(BaseFormatter):
    """JSON出力フォーマッター"""
    
    def format(self, elements: List[CodeElement]) -> str:
        import json
        
        result = {
            "metadata": {
                "total_elements": len(elements),
                "generated_at": self._get_timestamp(),
                "formatter": self.__class__.__name__
            },
            "elements": []
        }
        
        for element in elements:
            element_data = {
                "name": element.name,
                "type": element.element_type,
                "language": element.language,
                "position": {
                    "start": {"line": element.start_line, "column": element.start_column},
                    "end": {"line": element.end_line, "column": element.end_column}
                }
            }
            
            # 要素固有のデータを追加
            if hasattr(element, 'tag_name'):
                element_data["html"] = {
                    "tag_name": element.tag_name,
                    "attributes": element.attributes,
                    "element_class": getattr(element, 'element_class', None)
                }
            
            if hasattr(element, 'selector'):
                element_data["css"] = {
                    "selector": element.selector,
                    "properties": element.properties,
                    "selector_type": getattr(element, 'selector_type', None)
                }
            
            if element.metadata:
                element_data["metadata"] = element.metadata
            
            result["elements"].append(element_data)
        
        return json.dumps(result, indent=2, ensure_ascii=False)
```

## データモデルの拡張

### カスタム要素タイプの作成

```python
from tree_sitter_analyzer.models import CodeElement

class DatabaseElement(CodeElement):
    """データベース要素用のカスタムデータモデル"""
    
    def __init__(self, table_name: str, columns: List[str], **kwargs):
        super().__init__(**kwargs)
        self.table_name = table_name
        self.columns = columns
        self.element_type = "database"
    
    @property
    def column_count(self) -> int:
        """カラム数を返す"""
        return len(self.columns)
    
    def has_column(self, column_name: str) -> bool:
        """指定されたカラムが存在するかチェック"""
        return column_name in self.columns

class ConfigElement(CodeElement):
    """設定ファイル要素用のカスタムデータモデル"""
    
    def __init__(self, config_key: str, config_value: Any, config_type: str, **kwargs):
        super().__init__(**kwargs)
        self.config_key = config_key
        self.config_value = config_value
        self.config_type = config_type
        self.element_type = "config"
    
    @property
    def is_sensitive(self) -> bool:
        """機密情報かどうかを判定"""
        sensitive_keys = ["password", "secret", "token", "key", "api_key"]
        return any(sensitive in self.config_key.lower() for sensitive in sensitive_keys)
```

## 新しいクエリシステム

### v1.8.0のクエリシステム拡張

Tree-sitter Analyzer v1.8.0では、HTML/CSS言語サポートの追加に伴い、クエリシステムが大幅に拡張されました。

#### 統一クエリインターフェース

```python
from tree_sitter_analyzer.core.query_service import QueryService
from tree_sitter_analyzer.models import MarkupElement, StyleElement

class UnifiedQueryService:
    """統一クエリサービス"""
    
    def __init__(self):
        self.query_service = QueryService()
    
    def query_elements_by_type(self, file_path: str, element_types: List[str]) -> List[CodeElement]:
        """要素タイプ別クエリ"""
        results = []
        
        for element_type in element_types:
            elements = self.query_service.query_code(
                file_path=file_path,
                query_key=element_type
            )
            results.extend(elements)
        
        return results
    
    def query_html_by_tag(self, file_path: str, tag_names: List[str]) -> List[MarkupElement]:
        """HTMLタグ別クエリ"""
        all_elements = self.query_service.query_code(
            file_path=file_path,
            query_key="elements"
        )
        
        html_elements = [e for e in all_elements if isinstance(e, MarkupElement)]
        return [e for e in html_elements if e.tag_name in tag_names]
    
    def query_css_by_selector_type(self, file_path: str, selector_types: List[str]) -> List[StyleElement]:
        """CSSセレクタタイプ別クエリ"""
        all_elements = self.query_service.query_code(
            file_path=file_path,
            query_key="rules"
        )
        
        css_elements = [e for e in all_elements if isinstance(e, StyleElement)]
        return [e for e in css_elements if e.selector_type in selector_types]
```

#### 高度なフィルタリング機能

```python
class AdvancedQueryFilter:
    """高度なクエリフィルタ"""
    
    @staticmethod
    def filter_html_by_attributes(elements: List[MarkupElement],
                                 attribute_filters: Dict[str, str]) -> List[MarkupElement]:
        """属性によるHTMLフィルタリング"""
        filtered = []
        
        for element in elements:
            if isinstance(element, MarkupElement):
                match = True
                for attr_name, attr_value in attribute_filters.items():
                    if attr_name not in element.attributes:
                        match = False
                        break
                    
                    if attr_value and element.attributes[attr_name] != attr_value:
                        match = False
                        break
                
                if match:
                    filtered.append(element)
        
        return filtered
    
    @staticmethod
    def filter_css_by_properties(elements: List[StyleElement],
                                property_filters: Dict[str, str]) -> List[StyleElement]:
        """プロパティによるCSSフィルタリング"""
        filtered = []
        
        for element in elements:
            if isinstance(element, StyleElement):
                match = True
                for prop_name, prop_value in property_filters.items():
                    if prop_name not in element.properties:
                        match = False
                        break
                    
                    if prop_value and element.properties[prop_name] != prop_value:
                        match = False
                        break
                
                if match:
                    filtered.append(element)
        
        return filtered
    
    @staticmethod
    def filter_by_element_class(elements: List[MarkupElement],
                               element_classes: List[str]) -> List[MarkupElement]:
        """要素分類によるフィルタリング"""
        return [e for e in elements
                if isinstance(e, MarkupElement) and e.element_class in element_classes]
    
    @staticmethod
    def filter_by_specificity_range(elements: List[StyleElement],
                                   min_specificity: int,
                                   max_specificity: int) -> List[StyleElement]:
        """詳細度範囲によるフィルタリング"""
        return [e for e in elements
                if isinstance(e, StyleElement)
                and min_specificity <= e.specificity <= max_specificity]
```

#### カスタムクエリビルダー

```python
class CustomQueryBuilder:
    """カスタムクエリビルダー"""
    
    def __init__(self):
        self.query_parts = []
        self.filters = []
    
    def select_html_elements(self, tag_names: List[str] = None) -> 'CustomQueryBuilder':
        """HTML要素選択"""
        if tag_names:
            tag_filter = " | ".join(f'"{tag}"' for tag in tag_names)
            self.query_parts.append(f"(element (start_tag (tag_name) @tag_name) @element)")
            self.filters.append(f"(#match? @tag_name \"^({tag_filter})$\")")
        else:
            self.query_parts.append("(element) @element")
        return self
    
    def select_css_rules(self, selector_patterns: List[str] = None) -> 'CustomQueryBuilder':
        """CSS規則選択"""
        if selector_patterns:
            pattern_filter = " | ".join(selector_patterns)
            self.query_parts.append("(rule_set (selectors) @selector (block) @block) @rule")
            self.filters.append(f"(#match? @selector \"({pattern_filter})\")")
        else:
            self.query_parts.append("(rule_set) @rule")
        return self
    
    def with_attributes(self, attribute_names: List[str]) -> 'CustomQueryBuilder':
        """属性条件追加"""
        for attr_name in attribute_names:
            self.filters.append(f"(attribute (attribute_name) @attr_name (#eq? @attr_name \"{attr_name}\"))")
        return self
    
    def with_properties(self, property_names: List[str]) -> 'CustomQueryBuilder':
        """プロパティ条件追加"""
        for prop_name in property_names:
            self.filters.append(f"(declaration (property_name) @prop_name (#eq? @prop_name \"{prop_name}\"))")
        return self
    
    def build(self) -> str:
        """クエリ文字列を構築"""
        query = "\n".join(self.query_parts)
        if self.filters:
            query += "\n" + "\n".join(self.filters)
        return query

# 使用例
builder = CustomQueryBuilder()
query = (builder
         .select_html_elements(["div", "span"])
         .with_attributes(["class", "id"])
         .build())

print(query)
# 出力:
# (element (start_tag (tag_name) @tag_name) @element)
# (#match? @tag_name "^(div | span)$")
# (attribute (attribute_name) @attr_name (#eq? @attr_name "class"))
# (attribute (attribute_name) @attr_name (#eq? @attr_name "id"))
```

#### 複合クエリシステム

```python
class CompositeQuerySystem:
    """複合クエリシステム"""
    
    def __init__(self):
        self.html_queries = {}
        self.css_queries = {}
        self.composite_queries = {}
    
    def register_html_query(self, name: str, query: str):
        """HTMLクエリ登録"""
        self.html_queries[name] = query
    
    def register_css_query(self, name: str, query: str):
        """CSSクエリ登録"""
        self.css_queries[name] = query
    
    def register_composite_query(self, name: str, html_query: str, css_query: str):
        """複合クエリ登録"""
        self.composite_queries[name] = {
            "html": html_query,
            "css": css_query
        }
    
    def execute_composite_query(self, name: str, html_file: str, css_file: str) -> Dict[str, List[CodeElement]]:
        """複合クエリ実行"""
        if name not in self.composite_queries:
            raise ValueError(f"Composite query '{name}' not found")
        
        query_config = self.composite_queries[name]
        results = {}
        
        # HTMLクエリ実行
        if query_config["html"]:
            html_service = QueryService()
            results["html"] = html_service.query_code(
                file_path=html_file,
                query_string=query_config["html"]
            )
        
        # CSSクエリ実行
        if query_config["css"]:
            css_service = QueryService()
            results["css"] = css_service.query_code(
                file_path=css_file,
                query_string=query_config["css"]
            )
        
        return results

# 使用例
composite_system = CompositeQuerySystem()

# 複合クエリ登録
composite_system.register_composite_query(
    "form_analysis",
    html_query="""
        (element
            (start_tag (tag_name) @tag_name)
            (#match? @tag_name "^(form|input|button)$")) @form_element
    """,
    css_query="""
        (rule_set
            (selectors (selector) @selector)
            (#match? @selector "(form|input|button)")) @form_style
    """
)

# クエリ実行
results = composite_system.execute_composite_query(
    "form_analysis",
    "form.html",
    "styles.css"
)
```

#### パフォーマンス最適化クエリ

```python
import os
from typing import Dict, List, Any

class OptimizedQueryExecutor:
    """最適化クエリ実行器"""
    
    def __init__(self):
        self.query_cache = {}
        self.result_cache = {}
    
    def execute_cached_query(self, file_path: str, query_key: str) -> List[CodeElement]:
        """キャッシュ機能付きクエリ実行"""
        cache_key = f"{file_path}:{query_key}"
        
        if cache_key in self.result_cache:
            return self.result_cache[cache_key]
        
        # ファイルの最終更新時間をチェック
        file_mtime = os.path.getmtime(file_path)
        cache_entry = self.result_cache.get(cache_key)
        
        if cache_entry and cache_entry["mtime"] >= file_mtime:
            return cache_entry["results"]
        
        # クエリ実行
        query_service = QueryService()
        results = query_service.query_code(
            file_path=file_path,
            query_key=query_key
        )
        
        # 結果をキャッシュ
        self.result_cache[cache_key] = {
            "results": results,
            "mtime": file_mtime
        }
        
        return results
    
    def batch_execute_queries(self, file_path: str, query_keys: List[str]) -> Dict[str, List[CodeElement]]:
        """バッチクエリ実行"""
        results = {}
        
        # ファイルを一度だけパース
        query_service = QueryService()
        
        for query_key in query_keys:
            results[query_key] = self.execute_cached_query(file_path, query_key)
        
        return results
    
    def clear_cache(self):
        """キャッシュクリア"""
        self.query_cache.clear()
        self.result_cache.clear()
```

#### クエリ結果の後処理

```python
class QueryResultProcessor:
    """クエリ結果後処理器"""
    
    @staticmethod
    def group_by_element_type(elements: List[CodeElement]) -> Dict[str, List[CodeElement]]:
        """要素タイプ別グループ化"""
        groups = {}
        for element in elements:
            element_type = element.element_type
            if element_type not in groups:
                groups[element_type] = []
            groups[element_type].append(element)
        return groups
    
    @staticmethod
    def sort_by_position(elements: List[CodeElement]) -> List[CodeElement]:
        """位置順ソート"""
        return sorted(elements, key=lambda e: (e.start_line, e.start_column))
    
    @staticmethod
    def filter_by_size(elements: List[CodeElement], min_lines: int = 1) -> List[CodeElement]:
        """サイズフィルタ"""
        return [e for e in elements if (e.end_line - e.start_line + 1) >= min_lines]
    
    @staticmethod
    def extract_statistics(elements: List[CodeElement]) -> Dict[str, Any]:
        """統計情報抽出"""
        stats = {
            "total_count": len(elements),
            "by_type": {},
            "by_language": {},
            "size_distribution": {
                "small": 0,   # 1-5行
                "medium": 0,  # 6-20行
                "large": 0    # 21行以上
            }
        }
        
        for element in elements:
            # タイプ別統計
            element_type = element.element_type
            stats["by_type"][element_type] = stats["by_type"].get(element_type, 0) + 1
            
            # 言語別統計
            language = element.language
            stats["by_language"][language] = stats["by_language"].get(language, 0) + 1
            
            # サイズ分布
            size = element.end_line - element.start_line + 1
            if size <= 5:
                stats["size_distribution"]["small"] += 1
            elif size <= 20:
                stats["size_distribution"]["medium"] += 1
            else:
                stats["size_distribution"]["large"] += 1
        
        return stats
    
    @staticmethod
    def create_hierarchy_map(html_elements: List[MarkupElement]) -> Dict[str, Any]:
        """HTML階層マップ作成"""
        hierarchy = {
            "root_elements": [],
            "max_depth": 0,
            "depth_distribution": {}
        }
        
        for element in html_elements:
            if isinstance(element, MarkupElement):
                depth = getattr(element, 'depth', 0)
                hierarchy["max_depth"] = max(hierarchy["max_depth"], depth)
                
                if depth not in hierarchy["depth_distribution"]:
                    hierarchy["depth_distribution"][depth] = 0
                hierarchy["depth_distribution"][depth] += 1
                
                if depth == 0:
                    hierarchy["root_elements"].append(element)
        
        return hierarchy
```

## テストの作成

### プラグインのテスト

```python
# tests/test_plugin.py
import unittest
from your_extension.plugins.your_language_plugin import YourLanguagePlugin

class TestYourLanguagePlugin(unittest.TestCase):
    
    def setUp(self):
        """テストセットアップ"""
        self.plugin = YourLanguagePlugin()
    
    def test_language_name(self):
        """言語名のテスト"""
        self.assertEqual(self.plugin.get_language_name(), "your_language")
    
    def test_file_extensions(self):
        """ファイル拡張子のテスト"""
        extensions = self.plugin.get_file_extensions()
        self.assertIn(".yourlang", extensions)
        self.assertIn(".yl", extensions)
    
    def test_queries(self):
        """クエリのテスト"""
        queries = self.plugin.get_queries()
        self.assertIn("functions", queries)
        self.assertIn("classes", queries)
        self.assertIn("variables", queries)
    
    def test_element_creation(self):
        """要素作成のテスト"""
        # モックノードを作成
        mock_node = self._create_mock_node()
        element = self.plugin.create_element(mock_node, "function")
        
        self.assertEqual(element.element_type, "function")
        self.assertEqual(element.language, "your_language")
        self.assertIsNotNone(element.name)
    
    def _create_mock_node(self):
        """テスト用モックノードを作成"""
        class MockNode:
            def __init__(self):
                self.start_point = (0, 0)
                self.end_point = (10, 20)
                self.text = b"function test() {}"
                self.type = "function_declaration"
            
            def child_by_field_name(self, field_name):
                if field_name == "name":
                    return MockNameNode()
                return None
        
        class MockNameNode:
            def __init__(self):
                self.text = b"test"
        
        return MockNode()
```

### フォーマッターのテスト

```python
# tests/test_formatter.py
import unittest
from your_extension.formatters.your_formatter import YourCustomFormatter
from tree_sitter_analyzer.models import CodeElement

class TestYourCustomFormatter(unittest.TestCase):
    
    def setUp(self):
        """テストセットアップ"""
        self.formatter = YourCustomFormatter()
        self.test_elements = self._create_test_elements()
    
    def test_format_output(self):
        """フォーマット出力のテスト"""
        output = self.formatter.format(self.test_elements)
        
        # 基本的な出力内容をチェック
        self.assertIn("Code Analysis Report", output)
        self.assertIn("test_function", output)
        self.assertIn("test_class", output)
    
    def test_empty_elements(self):
        """空要素リストのテスト"""
        output = self.formatter.format([])
        self.assertIn("No elements found", output)
    
    def test_color_output(self):
        """カラー出力のテスト"""
        color_formatter = YourCustomFormatter(color_output=True)
        output = color_formatter.format(self.test_elements)
        
        # ANSI カラーコードが含まれているかチェック
        self.assertIn("\033[", output)
    
    def _create_test_elements(self):
        """テスト用要素を作成"""
        return [
            CodeElement(
                name="test_function",
                start_line=1,
                end_line=10,
                language="python",
                element_type="function"
            ),
            CodeElement(
                name="test_class",
                start_line=15,
                end_line=30,
                language="python",
                element_type="class"
            )
        ]
```

## FileOutputManagerベストプラクティス

### v1.8.0での統一化実装

Tree-sitter Analyzer v1.8.0では、FileOutputManagerの重複初期化問題を解決するため、Managed Singleton Factory Patternが導入されました。これにより、メモリ効率と設定の一貫性が大幅に改善されました。

#### 推奨使用方法

##### 新しいMCPツール開発

```python
from tree_sitter_analyzer.mcp.utils.file_output_manager import FileOutputManager
from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool

class YourMCPTool(BaseMCPTool):
    """新しいMCPツールの推奨実装パターン"""
    
    def __init__(self, project_root: str = None):
        super().__init__(project_root)
        # 推奨: ファクトリー管理インスタンスを使用
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)
    
    def set_project_path(self, project_path: str) -> None:
        """プロジェクトパス更新時の対応"""
        super().set_project_path(project_path)
        # ファクトリー管理インスタンスを再取得
        self.file_output_manager = FileOutputManager.get_managed_instance(project_path)
        logger.info(f"YourMCPTool project path updated to: {project_path}")
```

##### 便利関数の使用

```python
from tree_sitter_analyzer.mcp.utils.file_output_factory import get_file_output_manager

class SimpleMCPTool:
    """便利関数を使用した簡単な実装"""
    
    def __init__(self, project_root: str = None):
        self.project_root = project_root
        # 便利関数を使用（内部でファクトリーを使用）
        self.file_output_manager = get_file_output_manager(project_root)
    
    def save_analysis_result(self, content: str, filename: str = None):
        """解析結果の保存"""
        return self.file_output_manager.save_to_file(
            content=content,
            base_name=filename or "analysis_result"
        )
```

#### メモリ効率の最適化

##### Before（旧方式）
```python
# 非推奨: 各ツールが独自のインスタンスを作成
class OldMCPTool:
    def __init__(self, project_root):
        self.file_output_manager = FileOutputManager(project_root)  # 重複作成

# 結果: 4つのツール = 4つのインスタンス
tool1 = OldMCPTool(project_root)  # インスタンス1
tool2 = OldMCPTool(project_root)  # インスタンス2（重複）
tool3 = OldMCPTool(project_root)  # インスタンス3（重複）
tool4 = OldMCPTool(project_root)  # インスタンス4（重複）
```

##### After（新方式）
```python
# 推奨: ファクトリー管理インスタンスを使用
class NewMCPTool:
    def __init__(self, project_root):
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)

# 結果: 4つのツール = 1つの共有インスタンス
tool1 = NewMCPTool(project_root)  # インスタンス1（新規作成）
tool2 = NewMCPTool(project_root)  # インスタンス1（共有）
tool3 = NewMCPTool(project_root)  # インスタンス1（共有）
tool4 = NewMCPTool(project_root)  # インスタンス1（共有）

# メモリ使用量75%削減を実現
```

#### 高度な使用パターン

##### マルチプロジェクト対応

```python
from tree_sitter_analyzer.mcp.utils.file_output_factory import FileOutputManagerFactory

class MultiProjectTool:
    """複数プロジェクトを扱うツール"""
    
    def __init__(self):
        self.current_project = None
        self.file_output_manager = None
    
    def switch_project(self, project_root: str):
        """プロジェクト切り替え"""
        self.current_project = project_root
        self.file_output_manager = FileOutputManagerFactory.get_instance(project_root)
        
        # 現在管理されているプロジェクト数を確認
        project_count = FileOutputManagerFactory.get_instance_count()
        logger.info(f"Managing {project_count} projects")
    
    def list_managed_projects(self) -> list[str]:
        """管理中のプロジェクト一覧"""
        return FileOutputManagerFactory.get_managed_project_roots()
    
    def cleanup_unused_projects(self, active_projects: list[str]):
        """未使用プロジェクトのクリーンアップ"""
        managed_projects = self.list_managed_projects()
        for project in managed_projects:
            if project not in active_projects:
                FileOutputManagerFactory.clear_instance(project)
                logger.info(f"Cleaned up unused project: {project}")
```

##### テスト環境での使用

```python
import pytest
from tree_sitter_analyzer.mcp.utils.file_output_factory import FileOutputManagerFactory

class TestYourMCPTool:
    """テストクラスでのベストプラクティス"""
    
    def setup_method(self):
        """各テスト前のセットアップ"""
        # ファクトリーをクリーンな状態にリセット
        FileOutputManagerFactory.clear_all_instances()
    
    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        # テスト間でインスタンスが残らないようにクリーンアップ
        FileOutputManagerFactory.clear_all_instances()
    
    def test_tool_initialization(self):
        """ツール初期化のテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            tool = YourMCPTool(temp_dir)
            
            # インスタンスが正しく管理されているか確認
            assert FileOutputManagerFactory.get_instance_count() == 1
            
            # 同じプロジェクトルートで別のツールを作成
            tool2 = YourMCPTool(temp_dir)
            
            # インスタンスが共有されているか確認
            assert tool.file_output_manager is tool2.file_output_manager
            assert FileOutputManagerFactory.get_instance_count() == 1
```

#### パフォーマンス監視

```python
from tree_sitter_analyzer.mcp.utils.file_output_factory import FileOutputManagerFactory
import psutil
import os

class PerformanceMonitor:
    """FileOutputManagerのパフォーマンス監視"""
    
    @staticmethod
    def get_memory_usage() -> dict:
        """メモリ使用量を取得"""
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        return {
            "rss_mb": memory_info.rss / 1024 / 1024,  # 物理メモリ使用量
            "vms_mb": memory_info.vms / 1024 / 1024,  # 仮想メモリ使用量
            "managed_instances": FileOutputManagerFactory.get_instance_count(),
            "managed_projects": len(FileOutputManagerFactory.get_managed_project_roots())
        }
    
    @staticmethod
    def compare_memory_usage(old_pattern_count: int, new_pattern_count: int) -> dict:
        """旧方式と新方式のメモリ使用量比較"""
        # 理論的な比較（実際の測定値に基づく）
        old_memory_estimate = old_pattern_count * 100  # KB per instance
        new_memory_estimate = 100  # KB for shared instance
        
        reduction_percentage = ((old_memory_estimate - new_memory_estimate) / old_memory_estimate) * 100
        
        return {
            "old_pattern_memory_kb": old_memory_estimate,
            "new_pattern_memory_kb": new_memory_estimate,
            "reduction_percentage": reduction_percentage,
            "memory_saved_kb": old_memory_estimate - new_memory_estimate
        }

# 使用例
monitor = PerformanceMonitor()
memory_stats = monitor.get_memory_usage()
print(f"Current memory usage: {memory_stats['rss_mb']:.2f} MB")
print(f"Managing {memory_stats['managed_instances']} instances for {memory_stats['managed_projects']} projects")

# 4つのMCPツールでの比較
comparison = monitor.compare_memory_usage(old_pattern_count=4, new_pattern_count=1)
print(f"Memory reduction: {comparison['reduction_percentage']:.1f}%")
```

#### エラーハンドリングとフォールバック

```python
class RobustMCPTool:
    """エラー耐性のあるMCPツール実装"""
    
    def __init__(self, project_root: str = None):
        self.project_root = project_root
        self.file_output_manager = self._initialize_file_output_manager()
    
    def _initialize_file_output_manager(self):
        """安全なFileOutputManager初期化"""
        try:
            # 推奨: ファクトリー管理インスタンスを試行
            return FileOutputManager.get_managed_instance(self.project_root)
        except Exception as e:
            logger.warning(f"Factory initialization failed, falling back to direct instantiation: {e}")
            # フォールバック: 直接インスタンス作成
            return FileOutputManager.create_instance(self.project_root)
    
    def save_with_retry(self, content: str, base_name: str, max_retries: int = 3):
        """リトライ機能付きファイル保存"""
        for attempt in range(max_retries):
            try:
                return self.file_output_manager.save_to_file(
                    content=content,
                    base_name=base_name
                )
            except Exception as e:
                logger.warning(f"Save attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise
                
                # ファイル出力マネージャーを再初期化
                self.file_output_manager = self._initialize_file_output_manager()
```

#### 移行ガイドライン

##### 段階的移行戦略

1. **Phase 1: 新規開発**
   - 新しいMCPツールでは必ず `get_managed_instance()` を使用

2. **Phase 2: 既存ツールの更新**
   - 既存ツールを段階的に新方式に移行
   - テストを実行して動作確認

3. **Phase 3: 最適化**
   - パフォーマンス監視を実装
   - 不要なインスタンスのクリーンアップ

##### 移行チェックリスト

```python
# 移行前チェックリスト
class MigrationChecklist:
    """移行チェックリスト"""
    
    @staticmethod
    def check_current_usage(tool_class):
        """現在の使用方法をチェック"""
        # 1. 直接インスタンス化を使用しているか？
        uses_direct_instantiation = "FileOutputManager(" in inspect.getsource(tool_class)
        
        # 2. set_project_path メソッドでインスタンスを更新しているか？
        has_project_path_update = "set_project_path" in dir(tool_class)
        
        # 3. テストでクリーンアップを実装しているか？
        # （テストファイルを確認）
        
        return {
            "uses_direct_instantiation": uses_direct_instantiation,
            "has_project_path_update": has_project_path_update,
            "migration_needed": uses_direct_instantiation
        }
    
    @staticmethod
    def validate_migration(tool_instance):
        """移行後の検証"""
        # 1. ファクトリー管理インスタンスを使用しているか？
        manager = tool_instance.file_output_manager
        factory_instance = FileOutputManager.get_managed_instance(tool_instance.project_root)
        
        is_managed = manager is factory_instance
        
        # 2. インスタンス数が適切か？
        instance_count = FileOutputManagerFactory.get_instance_count()
        
        return {
            "is_managed_instance": is_managed,
            "instance_count": instance_count,
            "migration_successful": is_managed
        }
```

### 新しいMCPツール開発ガイドライン

#### 必須実装パターン

```python
from tree_sitter_analyzer.mcp.tools.base_tool import BaseMCPTool
from tree_sitter_analyzer.mcp.utils.file_output_manager import FileOutputManager

class NewMCPToolTemplate(BaseMCPTool):
    """新しいMCPツールのテンプレート"""
    
    def __init__(self, project_root: str = None):
        super().__init__(project_root)
        # 必須: ファクトリー管理インスタンスを使用
        self.file_output_manager = FileOutputManager.get_managed_instance(project_root)
    
    def set_project_path(self, project_path: str) -> None:
        """プロジェクトパス更新（必須実装）
        
        全MCPツールで統一されたインターフェース。
        SearchContentToolとFindAndGrepToolでも同様に実装済み。
        """
        super().set_project_path(project_path)
        # 必須: ファクトリー管理インスタンスを再取得
        self.file_output_manager = FileOutputManager.get_managed_instance(project_path)
        logger.info(f"{self.__class__.__name__} project path updated to: {project_path}")
    
    def get_tool_definition(self) -> dict:
        """MCPツール定義（必須実装）"""
        return {
            "name": "your_tool_name",
            "description": "Your tool description",
            "inputSchema": {
                "type": "object",
                "properties": {
                    # ファイル出力機能を含める場合は以下を追加
                    "output_file": {
                        "type": "string",
                        "description": "Optional filename to save output to file (extension auto-detected based on content)"
                    },
                    "suppress_output": {
                        "type": "boolean",
                        "description": "When true and output_file is specified, suppress detailed output in response to save tokens",
                        "default": False
                    }
                },
                "required": ["your_required_params"]
            }
        }
    
    async def execute(self, arguments: dict) -> dict:
        """ツール実行（必須実装）"""
        try:
            # ツール固有の処理
            result = await self._process_tool_logic(arguments)
            
            # ファイル出力処理（推奨パターン）
            output_file = arguments.get("output_file")
            suppress_output = arguments.get("suppress_output", False)
            
            if output_file:
                try:
                    # ファイル保存
                    import json
                    json_content = json.dumps(result, indent=2, ensure_ascii=False)
                    saved_file_path = self.file_output_manager.save_to_file(
                        content=json_content,
                        base_name=output_file
                    )
                    
                    result["output_file_path"] = saved_file_path
                    result["file_saved"] = True
                    
                    # 出力抑制処理
                    if suppress_output:
                        return {
                            "success": result.get("success", True),
                            "count": result.get("count", 0),
                            "output_file_path": saved_file_path,
                            "file_saved": True
                        }
                
                except Exception as e:
                    logger.error(f"Failed to save output to file: {e}")
                    result["file_save_error"] = str(e)
                    result["file_saved"] = False
            
            return result
            
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _process_tool_logic(self, arguments: dict) -> dict:
        """ツール固有のロジック（サブクラスで実装）"""
        raise NotImplementedError("Subclasses must implement _process_tool_logic")
```

これらのベストプラクティスに従うことで、メモリ効率的で一貫性のあるMCPツールを開発できます。

## パフォーマンス最適化

### 効率的なクエリの作成

```python
class OptimizedLanguagePlugin(LanguagePlugin):
    """パフォーマンス最適化されたプラグイン"""
    
    def __init__(self):
        super().__init__()
        self._compiled_queries = {}
    
    def get_compiled_query(self, query_name: str):
        """コンパイル済みクエリを取得（キャッシュ機能付き）"""
        if query_name not in self._compiled_queries:
            query_string = self.get_queries()[query_name]
            language = self.get_tree_sitter_language()
            self._compiled_queries[query_name] = language.query(query_string)
        
        return self._compiled_queries[query_name]
    
    def batch_analyze_elements(self, content: str) -> List[CodeElement]:
        """バッチ処理による効率的な要素解析"""
        tree = self.parse_content(content)
        elements = []
        
        # 全クエリを一度に実行
        for query_name in self.get_queries().keys():
            compiled_query = self.get_compiled_query(query_name)
            captures = compiled_query.captures(tree.root_node)
            
            for node, capture_name in captures:
                element = self.create_element(node, query_name)
                elements.append(element)
        
        return elements
```

### メモリ効率的なフォーマッター

```python
class StreamingFormatter(BaseFormatter):
    """ストリーミング処理によるメモリ効率的なフォーマッター"""
    
    def format(self, elements: List[CodeElement]) -> str:
        """ジェネレータを使用したストリーミング処理"""
        return ''.join(self._format_stream(elements))
    
    def _format_stream(self, elements: List[CodeElement]):
        """要素をストリーミング処理でフォーマット"""
        yield self._format_header_stream(len(elements))
        
        current_type = None
        for element in elements:
            if element.element_type != current_type:
                if current_type is not None:
                    yield self._format_section_end()
                yield self._format_section_start(element.element_type)
                current_type = element.element_type
            
            yield self._format_element_stream(element)
        
        if current_type is not None:
            yield self._format_section_end()
        
        yield self._format_footer_stream()
    
    def _format_header_stream(self, element_count: int) -> str:
        """ヘッダーをストリーミング形式でフォーマット"""
        return f"Analysis Report ({element_count} elements)\n{'='*50}\n"
    
    def _format_element_stream(self, element: CodeElement) -> str:
        """単一要素をストリーミング形式でフォーマット"""
        return f"- {element.name} ({element.element_type})\n"
```

## デバッグとトラブルシューティング

### ログ機能の実装

```python
import logging
from typing import Any

class DebuggablePlugin(LanguagePlugin):
    """デバッグ機能付きプラグイン"""
    
    def __init__(self, debug_mode: bool = False):
        super().__init__()
        self.debug_mode = debug_mode
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        """ロガーをセットアップ"""
        logger = logging.getLogger(f"{self.__class__.__name__}")
        
        if self.debug_mode:
            logger.setLevel(logging.DEBUG)
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def create_element(self, node, element_type: str, **kwargs) -> CodeElement:
        """デバッグ情報付きで要素を作成"""
        self.logger.debug(f"Creating element: {element_type}")
        self.logger.debug(f"Node type: {node.type}")
        self.logger.debug(f"Node position: {node.start_point}-{node.end_point}")
        
        try:
            element = super().create_element(node, element_type, **kwargs)
            self.logger.debug(f"Successfully created element: {element.name}")
            return element
        except Exception as e:
            self.logger.error(f"Failed to create element: {e}")
            raise
    
    def validate_tree_structure(self, tree) -> bool:
        """ツリー構造の妥当性を検証"""
        self.logger.debug("Validating tree structure")
        
        if tree.root_node.has_error:
            self.logger.warning("Tree contains syntax errors")
            self._log_syntax_errors(tree.root_node)
            return False
        
        self.logger.debug("Tree structure is valid")
        return True
    
    def _log_syntax_errors(self, node, depth: int = 0):
        """構文エラーをログ出力"""
        indent = "  " * depth
        
        if node.type == "ERROR":
            self.logger.error(f"{indent}Syntax error at {node.start_point}-{node.end_point}")
            self.logger.error(f"{indent}Content: {node.text.decode('utf-8', errors='ignore')}")
        
        for child in node.children:
            self._log_syntax_errors(child, depth + 1)
```

### エラーハンドリング

```python
class RobustFormatter(BaseFormatter):
    """エラー耐性のあるフォーマッター"""
    
    def format(self, elements: List[CodeElement]) -> str:
        """エラーハンドリング付きフォーマット"""
        try:
            return self._safe_format(elements)
        except Exception as e:
            return self._format_error_fallback(elements, e)
    
    def _safe_format(self, elements: List[CodeElement]) -> str:
        """安全なフォーマット処理"""
        output_parts = []
        
        for i, element in enumerate(elements):
            try:
                formatted_element = self._format_single_element(element)
                output_parts.append(formatted_element)
            except Exception as e:
                error_msg = f"Error formatting element {i}: {e}"
                output_parts.append(f"[ERROR] {error_msg}")
                logging.warning(error_msg)
        
        return '\n'.join(output_parts)
    
    def _format_error_fallback(self, elements: List[CodeElement], error: Exception) -> str:
        """エラー時のフォールバック処理"""
        return f"""
Formatting Error Occurred
========================
Error: {error}
Elements Count: {len(elements)}
Timestamp: {self._get_timestamp()}

Basic Element List:
{chr(10).join(f"- {e.name} ({e.element_type})" for e in elements)}
"""
```

## 統合とデプロイ

### パッケージ化

```python
# setup.py
from setuptools import setup, find_packages

setup(
    name="your-tree-sitter-extension",
    version="1.0.0",
    description="Custom Tree-sitter Analyzer extension",
    author="Your Name",
    author_email="your.email@example.com",
    packages=find_packages(),
    install_requires=[
        "tree-sitter-analyzer>=1.8.0",
        "tree-sitter-your-language>=1.0.0"
    ],
    entry_points={
        "tree_sitter_analyzer.plugins": [
            "your_language = your_extension.plugins.your_language_plugin:YourLanguagePlugin"
        ],
        "tree_sitter_analyzer.formatters": [
            "your_format = your_extension.formatters.your_formatter:YourCustomFormatter"
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.8",
)
```

### CI/CD設定

```yaml
# .github/workflows/test.yml
name: Test Extension

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, "3.10"]
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e .
        pip install pytest pytest-cov
    
    - name: Run tests
      run: |
        pytest tests/ --cov=your_extension --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v1
      with:
        file: ./coverage.xml
```

## ベストプラクティス

### 1. パフォーマンス

- クエリのコンパイル結果をキャッシュする
- 大きなファイルではストリーミング処理を使用
- 不要なメタデータの生成を避ける

### 2. エラーハンドリング

- 構文エラーのあるファイルでも部分的な解析を提供
- 詳細なログ出力でデバッグを支援
- フォールバック処理を実装

### 3. テスト

- 様々なコードパターンでテスト
- エラーケースもテストに含める
- パフォーマンステストを実装

### 4. ドキュメント

- APIドキュメントを充実させる
- 使用例を豊富に提供
- 制限事項を明記

## 参考資料

- [Tree-sitter Documentation](https://tree-sitter.github.io/tree-sitter/)
- [Tree-sitter Analyzer API Reference](./api/)
- [Python Plugin Development Guide](https://docs.python.org/3/extending/)
- [Testing Best Practices](https://docs.pytest.org/en/stable/)

---

このガイドを参考に、Tree-sitter Analyzerの機能を拡張し、新しい言語やフォーマットのサポートを追加してください。質問や提案がある場合は、GitHubのIssuesまたはDiscussionsをご利用ください。