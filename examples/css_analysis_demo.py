#!/usr/bin/env python3
"""
CSS解析デモンストレーション

このスクリプトは、Tree-sitter AnalyzerのCSS解析機能を実際に使用する例を示します。
comprehensive_sample.cssファイルを解析し、CSSルール、セレクタ、プロパティの分析を行います。
"""

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Any

# Tree-sitter Analyzerのインポート
try:
    from tree_sitter_analyzer.core.analysis_engine import get_analysis_engine
    from tree_sitter_analyzer.languages.css_plugin import CssPlugin
    from tree_sitter_analyzer.models import StyleElement
except ImportError as e:
    print(f"エラー: Tree-sitter Analyzerがインストールされていません: {e}")
    print("以下のコマンドでインストールしてください:")
    print("uv add 'tree-sitter-analyzer[css]'")
    exit(1)


class CssAnalysisDemo:
    """CSS解析デモクラス"""

    def __init__(self):
        self.engine = None
        self.css_plugin = CssPlugin()
        self.sample_file = Path(__file__).parent / "comprehensive_sample.css"

    async def initialize(self):
        """解析エンジンの初期化"""
        print("🔧 Tree-sitter Analyzer エンジンを初期化中...")
        self.engine = await get_analysis_engine()
        print("✅ 初期化完了")

    def check_sample_file(self) -> bool:
        """サンプルファイルの存在確認"""
        if not self.sample_file.exists():
            print(f"❌ サンプルファイルが見つかりません: {self.sample_file}")
            print("comprehensive_sample.cssファイルを作成してください。")
            return False
        return True

    async def analyze_css_structure(self) -> dict[str, Any]:
        """CSS構造の解析"""
        print(f"\n📊 CSS構造解析: {self.sample_file.name}")
        print("=" * 60)

        try:
            # ファイルを解析
            result = await self.engine.analyze_file(str(self.sample_file))

            # 基本統計情報
            print(f"📄 ファイル: {result.file_path}")
            print(f"🔤 言語: {result.language}")
            print(f"📏 総行数: {result.metrics.lines_total}")
            print(f"💻 コード行数: {result.metrics.lines_code}")
            print(f"📝 コメント行数: {result.metrics.lines_comment}")
            print(f"⚪ 空行数: {result.metrics.lines_blank}")
            print(f"🧩 総要素数: {result.metrics.elements.total}")

            return result.to_dict()

        except Exception as e:
            print(f"❌ 解析エラー: {e}")
            return {}

    def analyze_selectors(self, elements: list[dict[str, Any]]):
        """セレクタの分析"""
        print("\n🎯 CSSセレクタ分析")
        print("=" * 60)

        selector_types = defaultdict(int)
        selector_complexity = defaultdict(int)
        all_selectors = []

        for element in elements:
            if element.get("element_type") == "css_rule":
                selector = element.get("selector", "")
                if selector:
                    all_selectors.append(selector)

                    # セレクタタイプの分類
                    if selector.startswith("#"):
                        selector_types["ID"] += 1
                    elif selector.startswith("."):
                        selector_types["Class"] += 1
                    elif selector.startswith("@"):
                        selector_types["At-rule"] += 1
                    elif selector.startswith(":"):
                        selector_types["Pseudo"] += 1
                    elif selector.startswith("::"):
                        selector_types["Pseudo-element"] += 1
                    elif any(
                        tag in selector.lower()
                        for tag in [
                            "html",
                            "body",
                            "div",
                            "span",
                            "p",
                            "h1",
                            "h2",
                            "h3",
                            "h4",
                            "h5",
                            "h6",
                        ]
                    ):
                        selector_types["Element"] += 1
                    else:
                        selector_types["Other"] += 1

                    # セレクタの複雑度（スペースの数で簡易判定）
                    complexity = len(selector.split()) - 1
                    if complexity == 0:
                        selector_complexity["Simple"] += 1
                    elif complexity <= 2:
                        selector_complexity["Medium"] += 1
                    else:
                        selector_complexity["Complex"] += 1

        # セレクタタイプの表示
        print("📊 セレクタタイプ別統計:")
        for selector_type, count in sorted(
            selector_types.items(), key=lambda x: x[1], reverse=True
        ):
            print(f"  {selector_type}: {count}個")

        print("\n🔧 セレクタ複雑度:")
        for complexity, count in sorted(selector_complexity.items()):
            print(f"  {complexity}: {count}個")

        # 代表的なセレクタの例
        print("\n📝 セレクタ例 (最初の10個):")
        for i, selector in enumerate(all_selectors[:10], 1):
            print(f"  {i:2d}. {selector}")

        return selector_types, selector_complexity

    def analyze_properties(self, elements: list[dict[str, Any]]):
        """プロパティの分析"""
        print("\n🎨 CSSプロパティ分析")
        print("=" * 60)

        property_counts = defaultdict(int)
        property_categories = defaultdict(int)
        all_properties = []

        # プロパティカテゴリの定義
        categories = {
            "layout": [
                "display",
                "position",
                "float",
                "clear",
                "flex",
                "grid",
                "align",
                "justify",
            ],
            "box_model": [
                "width",
                "height",
                "margin",
                "padding",
                "border",
                "box-sizing",
            ],
            "typography": [
                "font",
                "text",
                "line-height",
                "letter-spacing",
                "word-spacing",
            ],
            "background": [
                "background",
                "background-color",
                "background-image",
                "background-size",
            ],
            "transition": ["transition", "animation", "transform"],
            "interactivity": ["cursor", "pointer-events", "user-select", "outline"],
        }

        for element in elements:
            if element.get("element_type") == "css_rule":
                properties = element.get("properties", {})

                for prop_name, prop_value in properties.items():
                    property_counts[prop_name] += 1
                    all_properties.append((prop_name, prop_value))

                    # プロパティをカテゴリに分類
                    categorized = False
                    for category, keywords in categories.items():
                        if any(keyword in prop_name.lower() for keyword in keywords):
                            property_categories[category] += 1
                            categorized = True
                            break

                    if not categorized:
                        property_categories["other"] += 1

        # プロパティ使用頻度の表示
        print("📊 プロパティ使用頻度 (上位15個):")
        sorted_props = sorted(property_counts.items(), key=lambda x: x[1], reverse=True)
        for prop, count in sorted_props[:15]:
            print(f"  {prop}: {count}回")

        # プロパティカテゴリの表示
        print("\n🏷️ プロパティカテゴリ別統計:")
        for category, count in sorted(
            property_categories.items(), key=lambda x: x[1], reverse=True
        ):
            print(f"  {category}: {count}個")

        return property_counts, property_categories

    def analyze_css_variables(self, elements: list[dict[str, Any]]):
        """CSS変数（カスタムプロパティ）の分析"""
        print("\n🔧 CSS変数（カスタムプロパティ）分析")
        print("=" * 60)

        css_variables = {}
        variable_usage = defaultdict(int)

        for element in elements:
            if element.get("element_type") == "css_rule":
                selector = element.get("selector", "")
                properties = element.get("properties", {})

                # CSS変数の定義を検索
                if ":root" in selector:
                    for prop_name, prop_value in properties.items():
                        if prop_name.startswith("--"):
                            css_variables[prop_name] = prop_value

                # CSS変数の使用を検索
                for prop_name, prop_value in properties.items():
                    if "var(" in str(prop_value):
                        # var()関数から変数名を抽出（簡易版）
                        import re

                        var_matches = re.findall(r"var\((--[^,)]+)", str(prop_value))
                        for var_name in var_matches:
                            variable_usage[var_name] += 1

        if css_variables:
            print(f"📝 定義されたCSS変数: {len(css_variables)}個")

            # 変数をカテゴリ別に分類
            color_vars = {k: v for k, v in css_variables.items() if "color" in k}
            size_vars = {
                k: v
                for k, v in css_variables.items()
                if any(word in k for word in ["size", "spacing", "width", "height"])
            }
            font_vars = {k: v for k, v in css_variables.items() if "font" in k}

            if color_vars:
                print(f"  🎨 カラー変数: {len(color_vars)}個")
                for var_name, var_value in list(color_vars.items())[:5]:
                    print(f"    {var_name}: {var_value}")

            if size_vars:
                print(f"  📏 サイズ変数: {len(size_vars)}個")
                for var_name, var_value in list(size_vars.items())[:5]:
                    print(f"    {var_name}: {var_value}")

            if font_vars:
                print(f"  🔤 フォント変数: {len(font_vars)}個")
                for var_name, var_value in list(font_vars.items())[:3]:
                    print(f"    {var_name}: {var_value}")

        if variable_usage:
            print("\n📊 CSS変数使用頻度:")
            sorted_usage = sorted(
                variable_usage.items(), key=lambda x: x[1], reverse=True
            )
            for var_name, count in sorted_usage[:10]:
                print(f"  {var_name}: {count}回")

        return css_variables, variable_usage

    def analyze_media_queries(self, elements: list[dict[str, Any]]):
        """メディアクエリの分析"""
        print("\n📱 メディアクエリ分析")
        print("=" * 60)

        media_queries = []
        responsive_properties = defaultdict(int)

        for element in elements:
            if element.get("element_type") == "css_rule":
                selector = element.get("selector", "")

                # メディアクエリの検出
                if "@media" in selector:
                    media_queries.append(selector)

                    # レスポンシブ関連のプロパティをカウント
                    properties = element.get("properties", {})
                    for prop_name in properties.keys():
                        if any(
                            keyword in prop_name.lower()
                            for keyword in [
                                "width",
                                "height",
                                "display",
                                "flex",
                                "grid",
                            ]
                        ):
                            responsive_properties[prop_name] += 1

        if media_queries:
            print(f"📊 メディアクエリ数: {len(media_queries)}個")

            # メディアクエリの種類を分析
            breakpoint_types = defaultdict(int)
            for query in media_queries:
                if "max-width" in query:
                    breakpoint_types["max-width"] += 1
                if "min-width" in query:
                    breakpoint_types["min-width"] += 1
                if "prefers-color-scheme" in query:
                    breakpoint_types["color-scheme"] += 1
                if "prefers-reduced-motion" in query:
                    breakpoint_types["reduced-motion"] += 1
                if "print" in query:
                    breakpoint_types["print"] += 1

            print("📋 メディアクエリタイプ:")
            for query_type, count in sorted(
                breakpoint_types.items(), key=lambda x: x[1], reverse=True
            ):
                print(f"  {query_type}: {count}個")

            # 代表的なメディアクエリの例
            print("\n📝 メディアクエリ例:")
            for i, query in enumerate(media_queries[:5], 1):
                # 長いクエリは切り詰める
                display_query = query if len(query) <= 60 else query[:57] + "..."
                print(f"  {i}. {display_query}")

        else:
            print("📊 メディアクエリは見つかりませんでした")

        return media_queries, responsive_properties

    def analyze_at_rules(self, elements: list[dict[str, Any]]):
        """@ルールの分析"""
        print("\n📐 @ルール分析")
        print("=" * 60)

        at_rules = defaultdict(int)
        keyframes = []

        for element in elements:
            if element.get("element_type") == "css_rule":
                selector = element.get("selector", "")

                if selector.startswith("@"):
                    # @ルールの種類を特定
                    rule_type = selector.split()[0] if " " in selector else selector
                    at_rules[rule_type] += 1

                    # キーフレームの特別処理
                    if "@keyframes" in selector:
                        keyframes.append(selector)

        if at_rules:
            print("📊 @ルール統計:")
            for rule_type, count in sorted(
                at_rules.items(), key=lambda x: x[1], reverse=True
            ):
                print(f"  {rule_type}: {count}個")

            if keyframes:
                print("\n🎬 アニメーション定義:")
                for keyframe in keyframes[:5]:
                    animation_name = keyframe.replace("@keyframes", "").strip()
                    print(f"  {animation_name}")
        else:
            print("📊 @ルールは見つかりませんでした")

        return at_rules, keyframes

    async def run_demo(self):
        """デモの実行"""
        print("🌳 Tree-sitter Analyzer CSS解析デモ")
        print("=" * 60)

        # 初期化
        await self.initialize()

        # サンプルファイルの確認
        if not self.check_sample_file():
            return

        # CSS構造解析
        analysis_result = await self.analyze_css_structure()
        if not analysis_result:
            return

        elements = analysis_result.get("elements", [])
        if not elements:
            print("❌ CSS要素が見つかりませんでした")
            return

        # 各種分析の実行
        self.analyze_selectors(elements)
        self.analyze_properties(elements)
        self.analyze_css_variables(elements)
        self.analyze_media_queries(elements)
        self.analyze_at_rules(elements)

        print("\n✅ CSS解析デモ完了!")
        print(f"📊 解析された要素数: {len(elements)}")
        print("📄 詳細な解析結果は上記をご確認ください。")


async def main():
    """メイン関数"""
    demo = CssAnalysisDemo()
    await demo.run_demo()


if __name__ == "__main__":
    # 非同期実行
    asyncio.run(main())
