# FormatterRegistry API仕様

**Version**: 1.8.0  
**Date**: 2025-10-13  
**Pattern**: Registry Pattern + Strategy Pattern

## 概要

FormatterRegistryは、Tree-sitter Analyzerの拡張可能なフォーマッターシステムの中核となるコンポーネントです。動的なフォーマッター登録・管理機能を提供し、新しい出力フォーマットの追加を容易にします。

## アーキテクチャ

### 設計パターン

1. **Registry Pattern**: フォーマッターの動的登録・検索
2. **Strategy Pattern**: フォーマット処理の戦略的切り替え
3. **Factory Pattern**: フォーマッターインスタンスの生成
4. **Singleton Pattern**: グローバルレジストリの管理

### クラス構造

```
FormatterRegistry (Singleton)
├── BaseFormatter (Abstract Base Class)
│   ├── PythonFormatter
│   ├── JavaFormatter
│   ├── JavaScriptFormatter
│   ├── TypeScriptFormatter
│   ├── MarkdownFormatter
│   └── HtmlFormatter (New in v1.8.0)
└── FormatterFactory
```

## FormatterRegistry クラス

### クラス定義

```python
class FormatterRegistry:
    """フォーマッター登録・管理システム"""
    
    _instance: Optional['FormatterRegistry'] = None
    _formatters: Dict[str, Type[BaseFormatter]] = {}
    _initialized: bool = False
```

### 主要メソッド

#### register_formatter

```python
@classmethod
def register_formatter(
    cls, 
    format_name: str, 
    formatter_class: Type[BaseFormatter]
) -> None:
    """
    新しいフォーマッターを登録
    
    Args:
        format_name: フォーマット名（例: "html", "json", "xml"）
        formatter_class: BaseFormatterを継承したフォーマッタークラス
        
    Raises:
        ValueError: 無効なフォーマット名
        TypeError: BaseFormatterを継承していないクラス
        
    Example:
        FormatterRegistry.register_formatter("custom", CustomFormatter)
    """
```

#### get_formatter

```python
@classmethod
def get_formatter(cls, format_name: str) -> BaseFormatter:
    """
    指定されたフォーマッターのインスタンスを取得
    
    Args:
        format_name: 取得するフォーマット名
        
    Returns:
        BaseFormatter: フォーマッターインスタンス
        
    Raises:
        ValueError: 未登録のフォーマット名
        
    Example:
        formatter = FormatterRegistry.get_formatter("html")
        result = formatter.format(elements)
    """
```

#### get_available_formats

```python
@classmethod
def get_available_formats(cls) -> List[str]:
    """
    利用可能なフォーマット一覧を取得
    
    Returns:
        List[str]: 登録済みフォーマット名のリスト
        
    Example:
        formats = FormatterRegistry.get_available_formats()
        # ['full', 'compact', 'json', 'csv', 'html', 'html_json', 'html_compact']
    """
```

#### is_format_available

```python
@classmethod
def is_format_available(cls, format_name: str) -> bool:
    """
    指定されたフォーマットが利用可能かチェック
    
    Args:
        format_name: チェックするフォーマット名
        
    Returns:
        bool: 利用可能な場合True
        
    Example:
        if FormatterRegistry.is_format_available("html"):
            formatter = FormatterRegistry.get_formatter("html")
    """
```

#### unregister_formatter

```python
@classmethod
def unregister_formatter(cls, format_name: str) -> bool:
    """
    フォーマッターの登録を解除
    
    Args:
        format_name: 解除するフォーマット名
        
    Returns:
        bool: 解除に成功した場合True
        
    Example:
        success = FormatterRegistry.unregister_formatter("custom")
    """
```

#### clear_registry

```python
@classmethod
def clear_registry(cls) -> None:
    """
    レジストリをクリア（テスト用）
    
    Warning:
        本番環境では使用しないでください
        
    Example:
        # テストのセットアップ
        FormatterRegistry.clear_registry()
        FormatterRegistry.register_formatter("test", TestFormatter)
    """
```

## BaseFormatter 抽象基底クラス

### クラス定義

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from tree_sitter_analyzer.models import CodeElement

class BaseFormatter(ABC):
    """フォーマッターの抽象基底クラス"""
    
    def __init__(self):
        self.name = self.__class__.__name__
        self.version = "1.0.0"
```

### 抽象メソッド

#### format

```python
@abstractmethod
def format(self, elements: List[CodeElement]) -> str:
    """
    要素リストをフォーマットして文字列として返す
    
    Args:
        elements: フォーマット対象の要素リスト
        
    Returns:
        str: フォーマット済み文字列
        
    Raises:
        NotImplementedError: サブクラスで実装が必要
    """
    pass
```

### 共通メソッド

#### get_format_info

```python
def get_format_info(self) -> Dict[str, Any]:
    """
    フォーマッター情報を取得
    
    Returns:
        Dict[str, Any]: フォーマッター情報
        
    Example:
        info = formatter.get_format_info()
        # {
        #     "name": "HtmlFormatter",
        #     "version": "1.0.0",
        #     "supported_elements": ["MarkupElement", "StyleElement"],
        #     "output_type": "text/html"
        # }
    """
```

#### validate_elements

```python
def validate_elements(self, elements: List[CodeElement]) -> bool:
    """
    要素リストの妥当性を検証
    
    Args:
        elements: 検証対象の要素リスト
        
    Returns:
        bool: 妥当な場合True
        
    Raises:
        ValueError: 無効な要素が含まれている場合
    """
```

## HtmlFormatter クラス（v1.8.0新機能）

### クラス定義

```python
from tree_sitter_analyzer.formatters.base_formatter import BaseFormatter
from tree_sitter_analyzer.models import MarkupElement, StyleElement

class HtmlFormatter(BaseFormatter):
    """HTML/CSS要素専用フォーマッター"""
    
    def __init__(self):
        super().__init__()
        self.supported_elements = [MarkupElement, StyleElement]
        self.output_type = "text/html"
```

### 主要メソッド

#### format

```python
def format(self, elements: List[CodeElement]) -> str:
    """
    HTML/CSS要素をHTMLテーブル形式でフォーマット
    
    Args:
        elements: MarkupElementとStyleElementのリスト
        
    Returns:
        str: HTMLテーブル形式の文字列
        
    Example:
        html_elements = [markup_element, style_element]
        formatter = HtmlFormatter()
        html_output = formatter.format(html_elements)
    """
```

#### format_markup_elements

```python
def format_markup_elements(self, elements: List[MarkupElement]) -> str:
    """
    MarkupElement専用フォーマット
    
    Args:
        elements: MarkupElementのリスト
        
    Returns:
        str: HTMLテーブル（HTML要素用）
    """
```

#### format_style_elements

```python
def format_style_elements(self, elements: List[StyleElement]) -> str:
    """
    StyleElement専用フォーマット
    
    Args:
        elements: StyleElementのリスト
        
    Returns:
        str: HTMLテーブル（CSS規則用）
    """
```

### 出力例

```html
<!-- HTML要素テーブル -->
<h3>HTML Elements</h3>
<table border="1" style="border-collapse: collapse; width: 100%;">
<thead>
<tr>
    <th>Tag Name</th>
    <th>Element Class</th>
    <th>Attributes</th>
    <th>Position</th>
    <th>Depth</th>
</tr>
</thead>
<tbody>
<tr>
    <td>div</td>
    <td>content</td>
    <td>class="container", id="main"</td>
    <td>10:1-25:6</td>
    <td>2</td>
</tr>
</tbody>
</table>

<!-- CSS規則テーブル -->
<h3>CSS Rules</h3>
<table border="1" style="border-collapse: collapse; width: 100%;">
<thead>
<tr>
    <th>Selector</th>
    <th>Selector Type</th>
    <th>Properties</th>
    <th>Position</th>
    <th>Specificity</th>
</tr>
</thead>
<tbody>
<tr>
    <td>.container</td>
    <td>class</td>
    <td>width: 100%, margin: 0 auto</td>
    <td>5:1-12:2</td>
    <td>10</td>
</tr>
</tbody>
</table>
```

## カスタムフォーマッターの作成

### 基本的な実装

```python
from tree_sitter_analyzer.formatters.base_formatter import BaseFormatter
from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
from tree_sitter_analyzer.models import CodeElement
from typing import List

class CustomFormatter(BaseFormatter):
    """カスタムフォーマッターの例"""
    
    def __init__(self):
        super().__init__()
        self.output_type = "application/json"
    
    def format(self, elements: List[CodeElement]) -> str:
        """カスタムフォーマット実装"""
        result = {
            "metadata": {
                "formatter": self.name,
                "version": self.version,
                "element_count": len(elements)
            },
            "elements": []
        }
        
        for element in elements:
            element_data = {
                "name": element.name,
                "type": element.element_type,
                "language": element.language,
                "position": {
                    "start_line": element.start_line,
                    "end_line": element.end_line
                }
            }
            
            # 要素タイプ別の特殊処理
            if hasattr(element, 'tag_name'):  # MarkupElement
                element_data["html"] = {
                    "tag_name": element.tag_name,
                    "attributes": element.attributes,
                    "element_class": element.element_class
                }
            elif hasattr(element, 'selector'):  # StyleElement
                element_data["css"] = {
                    "selector": element.selector,
                    "properties": element.properties,
                    "selector_type": element.selector_type
                }
            
            result["elements"].append(element_data)
        
        return json.dumps(result, indent=2, ensure_ascii=False)

# フォーマッターの登録
FormatterRegistry.register_formatter("custom_json", CustomFormatter)
```

### 高度な実装例

```python
class AdvancedHtmlFormatter(BaseFormatter):
    """高度なHTMLフォーマッター"""
    
    def __init__(self, theme: str = "default", include_css: bool = True):
        super().__init__()
        self.theme = theme
        self.include_css = include_css
        self.templates = self._load_templates()
    
    def format(self, elements: List[CodeElement]) -> str:
        """テーマ対応HTMLフォーマット"""
        html_parts = []
        
        if self.include_css:
            html_parts.append(self._generate_css())
        
        html_parts.append('<div class="code-analysis-report">')
        
        # 要素タイプ別にグループ化
        grouped_elements = self._group_elements_by_type(elements)
        
        for element_type, element_list in grouped_elements.items():
            section_html = self._format_element_section(element_type, element_list)
            html_parts.append(section_html)
        
        html_parts.append('</div>')
        
        return '\n'.join(html_parts)
    
    def _generate_css(self) -> str:
        """テーマ別CSSを生成"""
        if self.theme == "dark":
            return """
            <style>
            .code-analysis-report {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Consolas', monospace;
            }
            .element-section {
                margin: 20px 0;
                border: 1px solid #3c3c3c;
                border-radius: 5px;
            }
            </style>
            """
        else:
            return """
            <style>
            .code-analysis-report {
                background-color: #ffffff;
                color: #333333;
                font-family: 'Arial', sans-serif;
            }
            .element-section {
                margin: 20px 0;
                border: 1px solid #cccccc;
                border-radius: 5px;
            }
            </style>
            """
    
    def _group_elements_by_type(self, elements: List[CodeElement]) -> Dict[str, List[CodeElement]]:
        """要素をタイプ別にグループ化"""
        groups = {}
        for element in elements:
            element_type = element.element_type
            if element_type not in groups:
                groups[element_type] = []
            groups[element_type].append(element)
        return groups
    
    def _format_element_section(self, element_type: str, elements: List[CodeElement]) -> str:
        """要素セクションをフォーマット"""
        section_html = f'<div class="element-section">'
        section_html += f'<h3>{element_type.title()} Elements ({len(elements)})</h3>'
        
        # 要素タイプに応じた特殊フォーマット
        if element_type == "markup":
            section_html += self._format_markup_table(elements)
        elif element_type == "style":
            section_html += self._format_style_table(elements)
        else:
            section_html += self._format_generic_table(elements)
        
        section_html += '</div>'
        return section_html

# 高度なフォーマッターの登録
FormatterRegistry.register_formatter("advanced_html", AdvancedHtmlFormatter)
FormatterRegistry.register_formatter("dark_html", lambda: AdvancedHtmlFormatter(theme="dark"))
```

## プラグインシステムとの統合

### 言語プラグインとの連携

```python
from tree_sitter_analyzer.plugins.base import LanguagePlugin

class HtmlPlugin(LanguagePlugin):
    """HTMLプラグイン"""
    
    def get_default_formatter(self) -> str:
        """デフォルトフォーマッターを指定"""
        return "html"
    
    def get_supported_formats(self) -> List[str]:
        """サポートするフォーマット一覧"""
        return ["html", "html_json", "html_compact", "json", "csv"]
    
    def register_custom_formatters(self) -> None:
        """カスタムフォーマッターを登録"""
        FormatterRegistry.register_formatter("html_json", HtmlJsonFormatter)
        FormatterRegistry.register_formatter("html_compact", HtmlCompactFormatter)

# プラグイン初期化時にフォーマッター登録
plugin = HtmlPlugin()
plugin.register_custom_formatters()
```

### 動的フォーマッター選択

```python
def get_best_formatter(elements: List[CodeElement]) -> BaseFormatter:
    """要素タイプに基づいて最適なフォーマッターを選択"""
    
    # 要素タイプを分析
    has_markup = any(isinstance(e, MarkupElement) for e in elements)
    has_style = any(isinstance(e, StyleElement) for e in elements)
    
    if has_markup or has_style:
        # HTML/CSS要素が含まれている場合
        if FormatterRegistry.is_format_available("html"):
            return FormatterRegistry.get_formatter("html")
    
    # デフォルトフォーマッター
    return FormatterRegistry.get_formatter("full")

# 使用例
elements = analyzer.analyze_file("index.html")
formatter = get_best_formatter(elements)
output = formatter.format(elements)
```

## エラーハンドリング

### 例外クラス

```python
class FormatterError(Exception):
    """フォーマッター関連のベース例外"""
    pass

class FormatterNotFoundError(FormatterError):
    """フォーマッターが見つからない場合の例外"""
    pass

class FormatterRegistrationError(FormatterError):
    """フォーマッター登録時の例外"""
    pass

class InvalidFormatterError(FormatterError):
    """無効なフォーマッタークラスの例外"""
    pass
```

### エラーハンドリング例

```python
def safe_format_elements(elements: List[CodeElement], format_name: str) -> str:
    """安全な要素フォーマット"""
    try:
        if not FormatterRegistry.is_format_available(format_name):
            raise FormatterNotFoundError(f"Formatter '{format_name}' is not available")
        
        formatter = FormatterRegistry.get_formatter(format_name)
        
        # 要素の妥当性チェック
        if not formatter.validate_elements(elements):
            raise ValueError("Invalid elements provided")
        
        return formatter.format(elements)
        
    except FormatterNotFoundError:
        # フォールバック処理
        logger.warning(f"Formatter '{format_name}' not found, using default")
        default_formatter = FormatterRegistry.get_formatter("full")
        return default_formatter.format(elements)
        
    except Exception as e:
        logger.error(f"Formatting failed: {e}")
        # 最小限の出力を生成
        return f"Formatting error: {len(elements)} elements could not be formatted"
```

## パフォーマンス最適化

### 遅延初期化

```python
class LazyFormatterRegistry:
    """遅延初期化対応レジストリ"""
    
    def __init__(self):
        self._formatters = {}
        self._formatter_factories = {}
    
    def register_formatter_factory(self, format_name: str, factory_func: Callable[[], BaseFormatter]):
        """ファクトリ関数を登録（遅延初期化用）"""
        self._formatter_factories[format_name] = factory_func
    
    def get_formatter(self, format_name: str) -> BaseFormatter:
        """フォーマッターを取得（必要時に初期化）"""
        if format_name not in self._formatters:
            if format_name in self._formatter_factories:
                self._formatters[format_name] = self._formatter_factories[format_name]()
            else:
                raise FormatterNotFoundError(f"Formatter '{format_name}' not found")
        
        return self._formatters[format_name]
```

### キャッシュ機能

```python
from functools import lru_cache

class CachedFormatter(BaseFormatter):
    """キャッシュ機能付きフォーマッター"""
    
    @lru_cache(maxsize=128)
    def format_cached(self, elements_hash: str, elements: tuple) -> str:
        """キャッシュ機能付きフォーマット"""
        return self.format(list(elements))
    
    def format(self, elements: List[CodeElement]) -> str:
        """キャッシュを活用したフォーマット"""
        # 要素のハッシュを計算
        elements_hash = self._calculate_elements_hash(elements)
        elements_tuple = tuple(elements)
        
        return self.format_cached(elements_hash, elements_tuple)
    
    def _calculate_elements_hash(self, elements: List[CodeElement]) -> str:
        """要素リストのハッシュを計算"""
        import hashlib
        content = ''.join(f"{e.name}:{e.element_type}:{e.start_line}" for e in elements)
        return hashlib.md5(content.encode()).hexdigest()
```

## テスト支援機能

### テスト用ユーティリティ

```python
class FormatterTestUtils:
    """フォーマッターテスト用ユーティリティ"""
    
    @staticmethod
    def create_test_registry() -> FormatterRegistry:
        """テスト用レジストリを作成"""
        FormatterRegistry.clear_registry()
        FormatterRegistry.register_formatter("test", TestFormatter)
        return FormatterRegistry
    
    @staticmethod
    def assert_formatter_output(formatter: BaseFormatter, elements: List[CodeElement], expected: str):
        """フォーマッター出力をアサート"""
        actual = formatter.format(elements)
        assert actual.strip() == expected.strip(), f"Expected:\n{expected}\n\nActual:\n{actual}"
    
    @staticmethod
    def create_mock_elements() -> List[CodeElement]:
        """テスト用モック要素を作成"""
        from tree_sitter_analyzer.models import MarkupElement, StyleElement
        
        return [
            MarkupElement(
                name="test-div",
                start_line=1,
                end_line=5,
                language="html",
                tag_name="div",
                attributes={"class": "test"},
                element_class="content"
            ),
            StyleElement(
                name=".test",
                start_line=10,
                end_line=15,
                language="css",
                selector=".test",
                properties={"color": "red"},
                selector_type="class"
            )
        ]
```

### 単体テスト例

```python
import unittest
from tree_sitter_analyzer.formatters.formatter_registry import FormatterRegistry
from tree_sitter_analyzer.formatters.html_formatter import HtmlFormatter

class TestFormatterRegistry(unittest.TestCase):
    
    def setUp(self):
        """テストセットアップ"""
        FormatterRegistry.clear_registry()
    
    def test_register_and_get_formatter(self):
        """フォーマッター登録・取得テスト"""
        FormatterRegistry.register_formatter("test", HtmlFormatter)
        
        self.assertTrue(FormatterRegistry.is_format_available("test"))
        formatter = FormatterRegistry.get_formatter("test")
        self.assertIsInstance(formatter, HtmlFormatter)
    
    def test_get_available_formats(self):
        """利用可能フォーマット取得テスト"""
        FormatterRegistry.register_formatter("html", HtmlFormatter)
        FormatterRegistry.register_formatter("custom", HtmlFormatter)
        
        formats = FormatterRegistry.get_available_formats()
        self.assertIn("html", formats)
        self.assertIn("custom", formats)
    
    def test_unregister_formatter(self):
        """フォーマッター登録解除テスト"""
        FormatterRegistry.register_formatter("temp", HtmlFormatter)
        self.assertTrue(FormatterRegistry.is_format_available("temp"))
        
        success = FormatterRegistry.unregister_formatter("temp")
        self.assertTrue(success)
        self.assertFalse(FormatterRegistry.is_format_available("temp"))

class TestHtmlFormatter(unittest.TestCase):
    
    def setUp(self):
        """テストセットアップ"""
        self.formatter = HtmlFormatter()
        self.test_elements = FormatterTestUtils.create_mock_elements()
    
    def test_format_output(self):
        """フォーマット出力テスト"""
        output = self.formatter.format(self.test_elements)
        
        # HTML要素テーブルが含まれているかチェック
        self.assertIn("<h3>HTML Elements</h3>", output)
        self.assertIn("<h3>CSS Rules</h3>", output)
        self.assertIn("test-div", output)
        self.assertIn(".test", output)
    
    def test_empty_elements(self):
        """空要素リストのテスト"""
        output = self.formatter.format([])
        self.assertIn("No elements to display", output)
```

## 設定とカスタマイズ

### 設定ファイル

```yaml
# formatter_config.yaml
formatters:
  html:
    class: "tree_sitter_analyzer.formatters.html_formatter.HtmlFormatter"
    enabled: true
    options:
      include_css: true
      theme: "default"
  
  custom_json:
    class: "my_project.formatters.CustomJsonFormatter"
    enabled: true
    options:
      indent: 2
      sort_keys: true

  advanced_html:
    class: "my_project.formatters.AdvancedHtmlFormatter"
    enabled: false
    options:
      theme: "dark"
      include_statistics: true
```

### 設定ローダー

```python
import yaml
from typing import Dict, Any

class FormatterConfigLoader:
    """フォーマッター設定ローダー"""
    
    @staticmethod
    def load_config(config_path: str) -> Dict[str, Any]:
        """設定ファイルを読み込み"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    @staticmethod
    def register_formatters_from_config(config: Dict[str, Any]) -> None:
        """設定からフォーマッターを登録"""
        formatters_config = config.get('formatters', {})
        
        for format_name, formatter_config in formatters_config.items():
            if not formatter_config.get('enabled', True):
                continue
            
            class_path = formatter_config['class']
            options = formatter_config.get('options', {})
            
            # 動的クラスインポート
            formatter_class = FormatterConfigLoader._import_class(class_path)
            
            # オプション付きファクトリ関数を作成
            def create_formatter():
                return formatter_class(**options)
            
            FormatterRegistry.register_formatter(format_name, create_formatter)
    
    @staticmethod
    def _import_class(class_path: str):
        """クラスパスから動的インポート"""
        module_path, class_name = class_path.rsplit('.', 1)
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name)

# 使用例
config = FormatterConfigLoader.load_config("formatter_config.yaml")
FormatterConfigLoader.register_formatters_from_config(config)
```

## 今後の拡張予定

### v1.9.0での予定機能

- **テンプレートエンジン統合**: Jinja2テンプレートによるカスタマイズ
- **出力フィルター**: 要素フィルタリング機能
- **国際化対応**: 多言語出力サポート
- **プラグイン自動発見**: 自動フォーマッター検出機能

### 長期ロードマップ

- **リアルタイムフォーマット**: ストリーミング出力対応
- **インタラクティブ出力**: HTML+JavaScript対応
- **PDF出力**: レポート生成機能
- **API統合**: REST API経由でのフォーマット提供

---

このドキュメントは、FormatterRegistryシステムの完全な仕様と使用方法を提供します。新しいフォーマッターの作成や既存システムとの統合に関する質問は、GitHubのIssuesまたはDiscussionsをご利用ください。