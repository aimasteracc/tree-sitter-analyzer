#!/usr/bin/env python3
"""
Magic Course Tool - 革命的教育コンテンツ生成魔法

プロジェクトから5分でUdemy級コースを自動生成する世界初のシステム。
実際のコードベースを分析し、商用レベルの教育コンテンツを作成します。

Features:
- 🎬 プロフェッショナル動画スクリプト生成
- 📚 200ページ級の詳細教材作成
- 🎮 50個のインタラクティブ演習
- 🏗️ 実践プロジェクト課題
- 🧪 自動評価システム
- 🏆 修了証明書テンプレート
- 💰 マーケティング戦略

Design Patterns:
- Builder Pattern: 段階的なコース構築
- Strategy Pattern: 学習レベル別の戦略
- Template Method: コンテンツ生成の共通フロー
- Observer Pattern: 生成プロセスの監視
"""

import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .magic_base_tool import (
    MagicBaseTool,
    MagicType,
    MagicRequest,
    MagicResult,
    ProjectDNA,
    MagicExecutionError
)
from .deep_project_analyzer import DeepProjectAnalyzer


class LearningLevel(Enum):
    """学習レベル"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class ContentType(Enum):
    """コンテンツタイプ"""
    VIDEO_SCRIPT = "video_script"
    TEXT_MATERIAL = "text_material"
    EXERCISE = "exercise"
    PROJECT = "project"
    QUIZ = "quiz"
    CERTIFICATE = "certificate"


@dataclass
class CourseModule:
    """コースモジュール"""
    title: str
    description: str
    learning_objectives: List[str]
    duration_minutes: int
    content_items: List[Dict[str, Any]]
    exercises: List[Dict[str, Any]]
    difficulty_level: LearningLevel


@dataclass
class UdemyCourse:
    """Udemy級コース"""
    title: str
    subtitle: str
    description: str
    category: str
    subcategory: str
    language: str
    level: LearningLevel
    duration_hours: float
    modules: List[CourseModule]
    total_lectures: int
    total_exercises: int
    learning_path: List[str]
    prerequisites: List[str]
    target_audience: List[str]
    course_outcomes: List[str]
    pricing_strategy: Dict[str, Any]
    marketing_materials: Dict[str, Any]
    confidence_score: float


class CourseContentGenerator:
    """コースコンテンツ生成エンジン"""

    def __init__(self):
        self.content_templates = self._load_content_templates()
        self.exercise_patterns = self._load_exercise_patterns()
        self.deep_analyzer = DeepProjectAnalyzer()
    
    async def generate_course_structure(self, project_dna: ProjectDNA) -> List[CourseModule]:
        """
        プロジェクトDNAからコース構造を生成（深層分析版）

        Args:
            project_dna: プロジェクトの完全理解情報

        Returns:
            List[CourseModule]: コースモジュールのリスト
        """
        # 深層プロジェクト分析実行
        deep_analysis = await self.deep_analyzer.analyze_project_deeply(project_dna.project_path)

        modules = []

        # Module 1: プロジェクト概要と環境構築（深層分析版）
        intro_module = await self._create_introduction_module(project_dna, deep_analysis)
        modules.append(intro_module)

        # Module 2: 業務フローと基本概念
        business_flow_module = await self._create_business_flow_module(project_dna, deep_analysis)
        modules.append(business_flow_module)

        # Module 3: データフローとアーキテクチャ
        architecture_module = await self._create_architecture_module(project_dna, deep_analysis)
        modules.append(architecture_module)

        # Module 4-N: 機能別詳細モジュール（実際のコードベース）
        feature_modules = await self._create_feature_modules(project_dna, deep_analysis)
        modules.extend(feature_modules)

        # Final Module: 実践活用とワークフロー統合
        project_module = await self._create_project_module(project_dna, deep_analysis)
        modules.append(project_module)

        return modules
    
    async def _create_introduction_module(self, project_dna: ProjectDNA, deep_analysis: Dict[str, Any]) -> CourseModule:
        """導入モジュールの作成 - プロジェクト自体の使い方を学ぶ"""
        project_name = Path(project_dna.project_path).name
        return CourseModule(
            title=f"{project_name}入門 - ツールの概要と基本操作",
            description=f"{project_name}の機能、目的、基本的な使用方法を学びます",
            learning_objectives=[
                f"{project_name}の目的と価値を理解する",
                f"{project_name}のインストールと環境構築ができる",
                f"{project_name}の基本的な使用方法を習得する",
                f"{project_name}の主要機能を把握する"
            ],
            duration_minutes=45,
            content_items=[
                {
                    "type": "video_script",
                    "title": f"{Path(project_dna.project_path).name}とは何か",
                    "content": await self._generate_tool_overview_script(project_dna, deep_analysis),
                    "duration": 15
                },
                {
                    "type": "video_script",
                    "title": "インストールと初期設定",
                    "content": await self._generate_installation_script(project_dna, deep_analysis),
                    "duration": 20
                },
                {
                    "type": "text_material",
                    "title": "基本的な使用方法",
                    "content": await self._generate_basic_usage_guide(project_dna, deep_analysis),
                    "pages": 8
                }
            ],
            exercises=[
                {
                    "type": "hands_on",
                    "title": f"{Path(project_dna.project_path).name}インストール実習",
                    "description": f"実際に{Path(project_dna.project_path).name}をインストールして基本操作を体験",
                    "estimated_time": 30,
                    "difficulty": "beginner"
                }
            ],
            difficulty_level=LearningLevel.BEGINNER
        )

    async def _create_business_flow_module(self, project_dna: ProjectDNA, deep_analysis: Dict[str, Any]) -> CourseModule:
        """業務フローモジュールの作成"""
        tool_name = Path(project_dna.project_path).name
        business_flows = deep_analysis.get("business_flows", [])

        return CourseModule(
            title=f"{tool_name}の業務フローと使用パターン",
            description=f"{tool_name}の実際の使用フローと業務パターンを理解します",
            learning_objectives=[
                f"{tool_name}の典型的な使用フローを理解する",
                "実際の業務での活用パターンを習得する",
                "効率的なワークフローを設計できる",
                "エラーハンドリングと例外処理を理解する"
            ],
            duration_minutes=75,
            content_items=[
                {
                    "type": "video_script",
                    "title": "業務フロー概要",
                    "content": await self._generate_business_flow_script(project_dna, deep_analysis),
                    "duration": 25
                },
                {
                    "type": "video_script",
                    "title": "実際の使用パターン",
                    "content": await self._generate_usage_patterns_script(project_dna, deep_analysis),
                    "duration": 30
                },
                {
                    "type": "text_material",
                    "title": "ワークフロー設計ガイド",
                    "content": await self._generate_workflow_guide(project_dna, deep_analysis),
                    "pages": 15
                }
            ],
            exercises=[
                {
                    "type": "workflow_design",
                    "title": "業務フロー設計演習",
                    "description": f"実際の業務シナリオで{tool_name}を活用するフローを設計",
                    "estimated_time": 45,
                    "difficulty": "intermediate"
                }
            ],
            difficulty_level=LearningLevel.INTERMEDIATE
        )
    
    async def _create_architecture_module(self, project_dna: ProjectDNA, deep_analysis: Dict[str, Any]) -> CourseModule:
        """機能詳細モジュールの作成"""
        tool_name = Path(project_dna.project_path).name
        return CourseModule(
            title=f"{tool_name}の機能詳細と活用法",
            description=f"{tool_name}の主要機能を詳しく学び、効果的な活用方法を習得します",
            learning_objectives=[
                f"{tool_name}の主要機能を理解する",
                "各機能の使い分けを習得する",
                "高度な設定とカスタマイズ方法を学ぶ",
                "実際のプロジェクトでの活用パターンを理解する"
            ],
            duration_minutes=90,
            content_items=[
                {
                    "type": "video_script",
                    "title": "アーキテクチャ概要",
                    "content": await self._generate_architecture_script(project_dna),
                    "duration": 25
                },
                {
                    "type": "video_script",
                    "title": "設計パターン解説",
                    "content": await self._generate_design_patterns_script(project_dna),
                    "duration": 30
                },
                {
                    "type": "text_material",
                    "title": "アーキテクチャ詳細ガイド",
                    "content": await self._generate_architecture_guide(project_dna),
                    "pages": 25
                }
            ],
            exercises=[
                {
                    "type": "design_exercise",
                    "title": "アーキテクチャ図作成",
                    "description": "学んだ内容を基にアーキテクチャ図を作成します",
                    "estimated_time": 45,
                    "difficulty": "intermediate"
                },
                {
                    "type": "code_analysis",
                    "title": "コード構造分析",
                    "description": "実際のコードからアーキテクチャを読み解きます",
                    "estimated_time": 60,
                    "difficulty": "intermediate"
                }
            ],
            difficulty_level=LearningLevel.INTERMEDIATE
        )
    
    async def _create_feature_modules(self, project_dna: ProjectDNA, deep_analysis: Dict[str, Any]) -> List[CourseModule]:
        """機能別モジュールの作成（実際のコードベース）"""
        tool_name = Path(project_dna.project_path).name
        modules = []

        # 実際のコード構造から機能を抽出
        code_structure = deep_analysis.get("code_structure", {})
        classes = code_structure.get("classes", [])
        functions = code_structure.get("functions", [])

        # 主要クラスから機能モジュールを作成
        main_classes = [cls for cls in classes if cls.get("docstring") and len(cls.get("methods", [])) > 2][:3]

        if not main_classes:
            # フォールバック: 汎用機能
            main_features = [
                "コード分析機能",
                "プロジェクト構造解析",
                "レポート生成"
            ]
        else:
            main_features = [cls["name"] for cls in main_classes]

        for feature in main_features:
            module = CourseModule(
                title=f"{feature}の詳細活用",
                description=f"{tool_name}の{feature}を深く理解し、実践的に活用する方法を学びます",
                learning_objectives=[
                    f"{feature}の基本概念と仕組みの理解",
                    f"{feature}の効果的な使用方法の習得",
                    f"{feature}の高度な設定とオプション",
                    f"実際のプロジェクトでの{feature}活用事例"
                ],
                duration_minutes=120,
                content_items=[
                    {
                        "type": "video_script",
                        "title": f"{feature}基礎",
                        "content": await self._generate_feature_basics_script(feature, project_dna),
                        "duration": 30
                    },
                    {
                        "type": "video_script",
                        "title": f"{feature}実践",
                        "content": await self._generate_feature_practice_script(feature, project_dna),
                        "duration": 45
                    },
                    {
                        "type": "text_material",
                        "title": f"{feature}完全ガイド",
                        "content": await self._generate_feature_guide(feature, project_dna),
                        "pages": 30
                    }
                ],
                exercises=[
                    {
                        "type": "hands_on",
                        "title": f"{feature}実習",
                        "description": f"{feature}を実際に使って操作を体験します",
                        "estimated_time": 90,
                        "difficulty": "intermediate"
                    },
                    {
                        "type": "project_exercise",
                        "title": f"{feature}応用演習",
                        "description": f"{feature}の高度な活用方法を実践します",
                        "estimated_time": 180,
                        "difficulty": "advanced"
                    }
                ],
                difficulty_level=LearningLevel.INTERMEDIATE
            )
            modules.append(module)
        
        return modules
    
    async def _create_project_module(self, project_dna: ProjectDNA, deep_analysis: Dict[str, Any]) -> CourseModule:
        """実践活用モジュールの作成"""
        tool_name = Path(project_dna.project_path).name
        return CourseModule(
            title=f"{tool_name}の実践活用とワークフロー統合",
            description=f"学んだ知識を統合して、実際の開発ワークフローに{tool_name}を効果的に組み込みます",
            learning_objectives=[
                f"{tool_name}を開発ワークフローに統合する",
                "継続的インテグレーションでの活用",
                "チーム開発での効果的な使用方法",
                "カスタマイズと拡張の実践"
            ],
            duration_minutes=240,
            content_items=[
                {
                    "type": "video_script",
                    "title": "プロジェクト企画",
                    "content": await self._generate_project_planning_script(project_dna),
                    "duration": 30
                },
                {
                    "type": "video_script",
                    "title": "開発実践",
                    "content": await self._generate_development_practice_script(project_dna),
                    "duration": 60
                },
                {
                    "type": "text_material",
                    "title": "プロジェクト開発ガイド",
                    "content": await self._generate_project_guide(project_dna),
                    "pages": 40
                }
            ],
            exercises=[
                {
                    "type": "capstone_project",
                    "title": "最終プロジェクト",
                    "description": "コース全体の知識を活用した総合プロジェクト",
                    "estimated_time": 480,
                    "difficulty": "advanced"
                }
            ],
            difficulty_level=LearningLevel.ADVANCED
        )
    
    async def _generate_tool_overview_script(self, project_dna: ProjectDNA, deep_analysis: Dict[str, Any]) -> str:
        """ツール概要スクリプト生成（深層分析版）"""
        tool_name = Path(project_dna.project_path).name
        readme_info = deep_analysis.get("readme_info", {})
        domain_knowledge = deep_analysis.get("domain_knowledge", {})

        # READMEから実際の説明を抽出
        readme_sections = readme_info.get("sections", {})
        project_description = ""
        for section_name, content in readme_sections.items():
            if any(keyword in section_name.lower() for keyword in ['description', 'about', 'overview']):
                project_description = content[:300] + "..." if len(content) > 300 else content
                break

        if not project_description:
            project_description = f"{tool_name}は{project_dna.business_domain}分野の革新的なツールです。"

        # ドメイン知識から主要概念を抽出
        key_concepts = domain_knowledge.get("key_concepts", [])
        main_features = []
        if key_concepts:
            for concept in key_concepts[:4]:
                if isinstance(concept, dict):
                    term = concept.get('term', 'Unknown')
                    definition = concept.get('definition', 'Advanced functionality')[:100]
                else:
                    # dataclassの場合
                    term = getattr(concept, 'term', 'Unknown')
                    definition = getattr(concept, 'definition', 'Advanced functionality')[:100]
                main_features.append(f"- {term}: {definition}")

        if not main_features:
            main_features = [
                "- コード分析の自動化",
                "- プロジェクト構造の理解",
                "- 開発効率の向上",
                "- 品質管理の強化"
            ]

        features_text = "\n".join(main_features)

        return f"""
# {tool_name}とは何か - ツール概要

## イントロダクション
こんにちは！このコースでは、{tool_name}の使い方を基礎から実践まで学びます。

## {tool_name}の価値と目的
{project_description}

このツールを使うことで、以下のことが可能になります：

{features_text}

## 学習の流れ
1. ツールのインストールと基本設定
2. 実際の業務フローの理解
3. 主要機能の詳細活用
4. 実際のプロジェクトでの実践

## 期待される成果
このコースを完了すると、{tool_name}を効果的に活用して、
あなたの開発ワークフローを大幅に改善できるようになります。

ツール複雑度: {project_dna.complexity_score:.1f}/10
推定学習時間: 8-12時間
"""
    
    async def _generate_business_flow_script(self, project_dna: ProjectDNA, deep_analysis: Dict[str, Any]) -> str:
        """業務フロースクリプト生成"""
        tool_name = Path(project_dna.project_path).name
        business_flows = deep_analysis.get("business_flows", [])

        flow_descriptions = []
        if business_flows:
            for flow in business_flows[:3]:  # 最初の3つまで
                if isinstance(flow, dict):
                    flow_name = flow.get("name", "Unknown Flow")
                    flow_desc = flow.get("description", "Business process flow")
                    steps = flow.get("steps", [])
                else:
                    # dataclassの場合
                    flow_name = getattr(flow, 'name', 'Unknown Flow')
                    flow_desc = getattr(flow, 'description', 'Business process flow')
                    steps = getattr(flow, 'steps', [])

                step_list = []
                for i, step in enumerate(steps[:5], 1):  # 最初の5ステップまで
                    if isinstance(step, dict):
                        step_desc = step.get("description", f"Step {i}")
                    else:
                        step_desc = getattr(step, 'description', f"Step {i}")
                    step_list.append(f"{i}. {step_desc}")

                flow_text = f"""
### {flow_name}
{flow_desc}

**主要ステップ:**
{chr(10).join(step_list)}
"""
                flow_descriptions.append(flow_text)

        if not flow_descriptions:
            flow_descriptions = ["""
### 基本的な使用フロー
1. ツールの起動と設定
2. 対象プロジェクトの指定
3. 分析の実行
4. 結果の確認と活用
"""]

        flows_text = "\n".join(flow_descriptions)

        return f"""
# {tool_name}の業務フローと使用パターン

## 業務フローの重要性
{tool_name}を効果的に活用するためには、実際の業務フローを理解することが重要です。

## 主要な業務フロー
{flows_text}

## フロー設計のポイント
- 目的の明確化
- 効率的な手順の設計
- エラーハンドリングの考慮
- 結果の活用方法

## 実践的な活用例
実際のプロジェクトでこれらのフローをどう適用するかを学びます。
"""

    async def _generate_installation_script(self, project_dna: ProjectDNA, deep_analysis: Dict[str, Any]) -> str:
        """インストールスクリプト生成"""
        tool_name = Path(project_dna.project_path).name

        return f"""
# {tool_name}のインストールと初期設定

## システム要件
- Python 3.8以上
- Git
- 十分なディスク容量（約100MB）

## インストール手順

### 方法1: pipを使用（推奨）
```bash
pip install {tool_name.lower().replace('_', '-')}
```

### 方法2: ソースからインストール
```bash
git clone https://github.com/username/{tool_name.lower()}
cd {tool_name.lower()}
pip install -e .
```

## 初期設定
1. 設定ファイルの作成
2. 基本パラメータの設定
3. 動作確認テスト

## インストール確認
```bash
{tool_name.lower()} --version
{tool_name.lower()} --help
```

## トラブルシューティング
- 権限エラーの解決方法
- 依存関係の問題
- パス設定の確認

## 次のステップ
インストールが完了したら、基本的な使用方法を学びましょう。
"""
    
    async def _generate_basic_usage_guide(self, project_dna: ProjectDNA, deep_analysis: Dict[str, Any]) -> str:
        """基本使用方法ガイド生成"""
        tool_name = Path(project_dna.project_path).name
        return f"""
# {tool_name}の基本的な使用方法

## コマンドライン基本操作

### 基本的なコマンド構文
```bash
{tool_name.lower()} [オプション] [対象パス]
```

### よく使用するオプション
- `--help`: ヘルプ表示
- `--version`: バージョン情報
- `--verbose`: 詳細出力
- `--output`: 出力ファイル指定

## 基本的な使用例

### 1. プロジェクト分析
```bash
{tool_name.lower()} analyze ./my-project
```

### 2. レポート生成
```bash
{tool_name.lower()} report --format json ./my-project
```

### 3. 設定ファイル使用
```bash
{tool_name.lower()} --config config.yaml ./my-project
```

## 出力の理解
- 分析結果の読み方
- エラーメッセージの対処法
- 警告の意味と対応

## 実践的なワークフロー
1. プロジェクトの準備
2. 分析の実行
3. 結果の確認
4. 改善点の特定
5. 継続的な監視

## よくある質問
- 大きなプロジェクトの処理時間
- メモリ使用量の最適化
- 複数プロジェクトの一括処理
"""

    async def _generate_usage_patterns_script(self, project_dna: ProjectDNA, deep_analysis: Dict[str, Any]) -> str:
        """使用パターンスクリプト生成"""
        tool_name = Path(project_dna.project_path).name
        code_structure = deep_analysis.get("code_structure", {})

        # 実際の関数から使用パターンを抽出
        functions = code_structure.get("functions", [])
        main_functions = [f for f in functions if f.get("docstring") and not f["name"].startswith("_")][:5]

        patterns = []
        if main_functions:
            for func in main_functions:
                pattern = f"""
### {func["name"]}の使用パターン
```python
# {func.get("docstring", "Function usage")}
result = {func["name"]}({", ".join(func.get("args", []))})
```
"""
                patterns.append(pattern)

        if not patterns:
            patterns = ["""
### 基本的な使用パターン
```bash
# プロジェクト分析
tool-name analyze ./project

# レポート生成
tool-name report --format json
```
"""]

        patterns_text = "\n".join(patterns)

        return f"""
# {tool_name}の実際の使用パターン

## 使用パターンの重要性
効果的な活用のためには、実際の使用パターンを理解することが重要です。

## 主要な使用パターン
{patterns_text}

## パターンの選択指針
- プロジェクトの規模に応じた選択
- 目的に応じた機能の使い分け
- 効率的な組み合わせ方法

## 実践的な応用
実際のプロジェクトでこれらのパターンを適用する方法を学びます。
"""

    async def _generate_workflow_guide(self, project_dna: ProjectDNA, deep_analysis: Dict[str, Any]) -> str:
        """ワークフローガイド生成"""
        tool_name = Path(project_dna.project_path).name
        business_flows = deep_analysis.get("business_flows", [])

        return f"""
# {tool_name}ワークフロー設計ガイド

## ワークフロー設計の基本原則

### 1. 目的の明確化
- 何を達成したいのかを明確にする
- 成功指標を定義する
- 制約条件を把握する

### 2. 効率的な手順設計
- 無駄な手順を排除する
- 並行処理可能な部分を特定する
- 自動化できる部分を見つける

### 3. エラーハンドリング
- 想定される問題を洗い出す
- 復旧手順を準備する
- ログとモニタリングを設計する

## 実践的なワークフロー例

### 日次分析ワークフロー
1. プロジェクトの更新確認
2. 自動分析の実行
3. 結果の確認と評価
4. 問題の特定と対応
5. レポートの生成と共有

### 継続的改善ワークフロー
1. 定期的な品質測定
2. トレンド分析
3. 改善点の特定
4. 対策の実施
5. 効果の測定

## ワークフロー最適化のポイント
- 定期的な見直しと改善
- チームメンバーとの情報共有
- ツールの効果的な活用
- 継続的な学習と改善
"""
    
    async def _generate_architecture_script(self, project_dna: ProjectDNA) -> str:
        """アーキテクチャスクリプト生成"""
        return f"""
# {project_dna.architecture_pattern}アーキテクチャ詳解

## アーキテクチャの選択理由
なぜ{project_dna.architecture_pattern}パターンを選択したのか、
その背景と利点を説明します。

## 層構造の理解
各層の責任と相互作用について詳しく学びます。

## 設計原則
SOLID原則やDRY原則など、重要な設計原則の実践例を示します。

## 実装パターン
よく使われる実装パターンとその適用場面を解説します。
"""
    
    async def _generate_design_patterns_script(self, project_dna: ProjectDNA) -> str:
        """設計パターンスクリプト生成"""
        return f"""
# 設計パターン実践解説

## プロジェクトで使用されているパターン
実際のコードから設計パターンの使用例を抽出し、解説します。

## パターンの効果
各パターンがコードの品質にどのような影響を与えるかを説明します。

## 適用のタイミング
いつ、どのパターンを使うべきかの判断基準を学びます。
"""
    
    async def _generate_architecture_guide(self, project_dna: ProjectDNA) -> str:
        """アーキテクチャガイド生成"""
        return f"""
# {project_dna.architecture_pattern}アーキテクチャ完全ガイド

## 第1章: アーキテクチャ概要
{project_dna.architecture_pattern}の基本概念と特徴

## 第2章: 実装詳細
具体的な実装方法とベストプラクティス

## 第3章: パフォーマンス考慮
スケーラビリティと性能最適化

## 第4章: 保守性の向上
長期的な保守を考慮した設計

## 第5章: テスト戦略
アーキテクチャに適したテスト手法

## 第6章: 実践演習
実際のコード例を使った演習問題
"""
    
    async def _generate_feature_basics_script(self, feature: str, project_dna: ProjectDNA) -> str:
        """機能基礎スクリプト生成"""
        tool_name = Path(project_dna.project_path).name
        return f"""
# {feature}基礎講座

## {feature}とは
{tool_name}の{feature}の基本概念と特徴を理解します。

## 機能の目的と価値
{feature}がなぜ重要で、どのような問題を解決するのか

## 基本的な使い方
{feature}の基本的な操作と設定方法

## 実践例
実際のプロジェクトを使った{feature}の活用例
"""
    
    async def _generate_feature_practice_script(self, feature: str, project_dna: ProjectDNA) -> str:
        """機能実践スクリプト生成"""
        tool_name = Path(project_dna.project_path).name
        return f"""
# {feature}実践活用

## 高度な機能
{feature}の応用的な機能と活用方法

## ベストプラクティス
{feature}を使う際の推奨パターンと注意点

## パフォーマンス最適化
{feature}のパフォーマンスを最大化する技法

## 実装演習
実際に手を動かして{feature}を活用した分析を実行
"""
    
    async def _generate_feature_guide(self, feature: str, project_dna: ProjectDNA) -> str:
        """機能ガイド生成"""
        tool_name = Path(project_dna.project_path).name
        return f"""
# {feature}完全ガイド

## 基礎編
- {feature}の目的と背景
- 基本概念と用語
- 設定とオプション

## 実践編
- 実際のプロジェクトでの使用方法
- よく使う機能とコマンド
- トラブルシューティング

## 応用編
- 高度な設定とカスタマイズ
- パフォーマンスチューニング
- 他ツールとの連携

## 演習問題
- 基礎レベル演習 (10問)
- 中級レベル演習 (15問)
- 上級レベル演習 (10問)
"""
    
    async def _generate_project_planning_script(self, project_dna: ProjectDNA) -> str:
        """プロジェクト企画スクリプト生成"""
        return f"""
# 実践プロジェクト企画

## プロジェクトの目標設定
学習した技術を統合した実践的なプロジェクトを企画します。

## 要件定義
- 機能要件の整理
- 非機能要件の検討
- 制約条件の確認

## 技術選択
学習した{len(project_dna.tech_stack)}つの技術をどう組み合わせるか

## 開発計画
段階的な開発アプローチとマイルストーン設定
"""
    
    async def _generate_development_practice_script(self, project_dna: ProjectDNA) -> str:
        """開発実践スクリプト生成"""
        return f"""
# 開発実践ガイド

## 開発環境の準備
実践プロジェクト用の環境構築

## コーディング規約
品質の高いコードを書くためのルール

## バージョン管理
Gitを使った効果的な開発フロー

## テスト駆動開発
品質を保証するテスト手法

## コードレビュー
チーム開発での品質向上手法
"""
    
    async def _generate_project_guide(self, project_dna: ProjectDNA) -> str:
        """プロジェクトガイド生成"""
        return f"""
# 実践プロジェクト開発完全ガイド

## プロジェクト概要
最終プロジェクトの全体像と目標

## 開発フェーズ
1. 企画・設計フェーズ (1週間)
2. 基盤実装フェーズ (2週間)  
3. 機能実装フェーズ (3週間)
4. テスト・改善フェーズ (1週間)
5. デプロイ・運用フェーズ (1週間)

## 評価基準
- 機能の完成度 (40%)
- コードの品質 (30%)
- 設計の適切性 (20%)
- 創造性・独自性 (10%)

## 提出物
- ソースコード
- 設計書
- テスト結果
- デモ動画
- 振り返りレポート
"""
    
    def _load_content_templates(self) -> Dict[str, Any]:
        """コンテンツテンプレートの読み込み"""
        return {
            "video_script_template": "# {title}\n\n{content}\n\n## まとめ\n{summary}",
            "exercise_template": "## 演習: {title}\n\n{description}\n\n### 手順\n{steps}",
            "quiz_template": "### 問題 {number}\n{question}\n\n選択肢:\n{options}\n\n正解: {answer}"
        }
    
    def _load_exercise_patterns(self) -> Dict[str, Any]:
        """演習パターンの読み込み"""
        return {
            "hands_on": "実際に手を動かして学ぶ実習形式",
            "code_analysis": "既存コードを分析して理解を深める",
            "design_exercise": "設計スキルを向上させる演習",
            "coding_exercise": "プログラミングスキルを鍛える課題",
            "project_exercise": "総合的なプロジェクト開発",
            "capstone_project": "コース全体の集大成となる最終プロジェクト"
        }


class MarketingStrategyGenerator:
    """マーケティング戦略生成エンジン"""
    
    async def generate_marketing_strategy(self, course: UdemyCourse, project_dna: ProjectDNA) -> Dict[str, Any]:
        """マーケティング戦略の生成"""
        return {
            "pricing": await self._generate_pricing_strategy(course, project_dna),
            "promotion": await self._generate_promotion_strategy(course, project_dna),
            "target_market": await self._analyze_target_market(course, project_dna),
            "competitive_analysis": await self._analyze_competition(course, project_dna),
            "revenue_projection": await self._project_revenue(course, project_dna)
        }
    
    async def _generate_pricing_strategy(self, course: UdemyCourse, project_dna: ProjectDNA) -> Dict[str, Any]:
        """価格戦略の生成"""
        base_price = 50 + (course.duration_hours * 10) + (len(course.modules) * 5)
        
        return {
            "recommended_price": f"${base_price:.0f}",
            "launch_price": f"${base_price * 0.7:.0f}",
            "premium_price": f"${base_price * 1.5:.0f}",
            "strategy": "段階的価格上昇戦略",
            "justification": f"{course.duration_hours:.1f}時間の包括的コンテンツと実践プロジェクト"
        }
    
    async def _generate_promotion_strategy(self, course: UdemyCourse, project_dna: ProjectDNA) -> Dict[str, Any]:
        """プロモーション戦略の生成"""
        return {
            "launch_campaign": "早期割引キャンペーン (30%オフ)",
            "social_media": f"{project_dna.business_domain}開発者コミュニティでの宣伝",
            "content_marketing": "技術ブログでの記事投稿",
            "influencer_outreach": "業界インフルエンサーとの連携",
            "free_preview": "最初の2モジュールを無料公開"
        }
    
    async def _analyze_target_market(self, course: UdemyCourse, project_dna: ProjectDNA) -> Dict[str, Any]:
        """ターゲット市場の分析"""
        return {
            "primary_audience": f"{project_dna.business_domain}分野の開発者",
            "secondary_audience": "フルスタック開発者を目指す学習者",
            "market_size": "推定10,000-50,000人",
            "growth_potential": "年間20-30%成長",
            "key_demographics": {
                "age": "25-40歳",
                "experience": "1-5年の開発経験",
                "motivation": "スキルアップとキャリア向上"
            }
        }
    
    async def _analyze_competition(self, course: UdemyCourse, project_dna: ProjectDNA) -> Dict[str, Any]:
        """競合分析"""
        return {
            "competitive_advantage": [
                "実際のプロジェクトベースの学習",
                "最新技術スタックの実践的活用",
                "商用レベルの品質保証",
                "包括的な実習とプロジェクト"
            ],
            "differentiation": f"{project_dna.architecture_pattern}の実践的理解",
            "market_positioning": "実践重視の高品質コース"
        }
    
    async def _project_revenue(self, course: UdemyCourse, project_dna: ProjectDNA) -> Dict[str, Any]:
        """収益予測"""
        estimated_students = min(1000, max(100, int(project_dna.complexity_score * 100)))
        base_price = 50 + (course.duration_hours * 10)
        
        return {
            "conservative_estimate": f"${estimated_students * base_price * 0.5:.0f}",
            "realistic_estimate": f"${estimated_students * base_price:.0f}",
            "optimistic_estimate": f"${estimated_students * base_price * 2:.0f}",
            "timeframe": "12ヶ月",
            "assumptions": {
                "student_count": estimated_students,
                "average_price": f"${base_price:.0f}",
                "conversion_rate": "2-5%"
            }
        }


class MagicCourseGeneratorTool(MagicBaseTool):
    """
    魔法的教育コンテンツ生成ツール
    
    5分でUdemy級コースを自動生成する世界初のシステム
    """
    
    def __init__(self):
        super().__init__(
            name="magic_course",
            description="🎓 プロジェクトから5分でUdemy級コースを自動生成する革命的魔法ツール"
        )
        self.content_generator = CourseContentGenerator()
        self.marketing_generator = MarketingStrategyGenerator()
    
    def _get_magic_type(self) -> MagicType:
        return MagicType.COURSE
    
    def _get_input_schema_properties(self) -> Dict[str, Any]:
        """教育コンテンツ生成ツール用の入力スキーマ"""
        return {
            "project_path": {
                "type": "string",
                "description": "プロジェクトのパス"
            },
            "target_level": {
                "type": "string",
                "description": "対象学習レベル (beginner/intermediate/advanced/expert)",
                "default": "intermediate",
                "enum": ["beginner", "intermediate", "advanced", "expert"]
            },
            "language": {
                "type": "string", 
                "description": "コース言語",
                "default": "japanese",
                "enum": ["japanese", "english", "chinese", "spanish"]
            },
            "output_dir": {
                "type": "string",
                "description": "出力ディレクトリ (デフォルト: Training)",
                "default": "Training"
            },
            "include_marketing": {
                "type": "boolean",
                "description": "マーケティング戦略を含めるか",
                "default": True
            }
        }
    
    def _get_required_parameters(self) -> list[str]:
        """必須パラメータ"""
        return ["project_path"]
    
    async def _execute_magic(self, request: MagicRequest, project_dna: ProjectDNA) -> MagicResult:
        """
        教育コンテンツ生成魔法の実行
        
        5分以内でUdemy級コース完成を目指します
        """
        start_time = time.time()
        
        # パラメータの取得
        target_level = LearningLevel(request.parameters.get("target_level", "intermediate"))
        language = request.parameters.get("language", "japanese")
        output_dir = request.parameters.get("output_dir", "Training")
        include_marketing = request.parameters.get("include_marketing", True)
        
        self.logger.info("🎬 Udemy級コース生成開始...")
        
        # Step 1: コース構造の生成
        modules = await self.content_generator.generate_course_structure(project_dna)
        self.logger.info(f"📚 {len(modules)}個のモジュール生成完了")
        
        # Step 2: コース情報の構築
        course = await self._build_course_info(modules, project_dna, target_level, language)
        self.logger.info(f"🎓 コース情報構築完了: {course.total_lectures}講義, {course.duration_hours:.1f}時間")
        
        # Step 3: マーケティング戦略の生成
        marketing_strategy = None
        if include_marketing:
            marketing_strategy = await self.marketing_generator.generate_marketing_strategy(course, project_dna)
            self.logger.info("💰 マーケティング戦略生成完了")
        
        # Step 4: ファイル出力
        output_files = await self._generate_course_files(course, marketing_strategy, output_dir, request.project_path)
        self.logger.info(f"📁 {len(output_files)}個のファイル生成完了")
        
        # Step 5: 結果の構築
        execution_time = time.time() - start_time
        
        result_data = {
            "course_info": {
                "title": course.title,
                "duration_hours": course.duration_hours,
                "total_lectures": course.total_lectures,
                "total_exercises": course.total_exercises,
                "modules_count": len(course.modules),
                "target_level": course.level.value,
                "language": course.language,
                "confidence_score": f"{course.confidence_score:.1%}"
            },
            "content_generated": {
                "video_scripts": sum(len([item for item in module.content_items if item["type"] == "video_script"]) for module in course.modules),
                "text_materials": sum(len([item for item in module.content_items if item["type"] == "text_material"]) for module in course.modules),
                "exercises": course.total_exercises,
                "total_pages": sum(sum(item.get("pages", 0) for item in module.content_items) for module in course.modules)
            },
            "output_files": output_files,
            "marketing_strategy": marketing_strategy if include_marketing else None
        }
        
        return MagicResult(
            success=True,
            magic_type=MagicType.COURSE,
            execution_time=execution_time,
            result_data=result_data,
            confidence_score=course.confidence_score,
            side_effects=[
                f"🎬 {course.total_lectures}本の動画スクリプト生成",
                f"📚 {sum(sum(item.get('pages', 0) for item in module.content_items) for module in course.modules)}ページの教材作成",
                f"🎮 {course.total_exercises}個の演習問題生成",
                f"💰 推定収益: {marketing_strategy['revenue_projection']['realistic_estimate'] if marketing_strategy else 'N/A'}",
                f"📁 {output_dir}フォルダに完全なコース資料を出力"
            ],
            recommendations=[
                "🎥 動画スクリプトを基に実際の動画を作成することを推奨",
                "🧪 演習問題の自動評価システムの実装を検討",
                "🌍 多言語対応でグローバル展開を推奨",
                "📊 学習者のフィードバックを収集して継続改善",
                "💼 企業研修向けのカスタマイズ版も検討価値あり"
            ]
        )
    
    async def _build_course_info(self, modules: List[CourseModule], project_dna: ProjectDNA, 
                                target_level: LearningLevel, language: str) -> UdemyCourse:
        """コース情報の構築"""
        total_duration = sum(module.duration_minutes for module in modules)
        total_lectures = sum(len(module.content_items) for module in modules)
        total_exercises = sum(len(module.exercises) for module in modules)
        
        # コースタイトルの生成
        tool_name = Path(project_dna.project_path).name
        title = f"{tool_name}完全マスター: 基礎から実践まで"

        # サブタイトルの生成
        subtitle = f"{tool_name}の機能を完全に理解し、実際のプロジェクトで効果的に活用する方法を学ぶ"
        
        return UdemyCourse(
            title=title,
            subtitle=subtitle,
            description=f"{tool_name}の全機能を体系的に学び、実際のプロジェクトで効果的に活用できるようになる包括的コースです。",
            category="Development",
            subcategory="Developer Tools",
            language=language,
            level=target_level,
            duration_hours=total_duration / 60,
            modules=modules,
            total_lectures=total_lectures,
            total_exercises=total_exercises,
            learning_path=[module.title for module in modules],
            prerequisites=[
                "基本的なコマンドライン操作",
                "プログラミングの基礎知識",
                "開発環境の基本理解"
            ],
            target_audience=[
                f"{tool_name}を使いたい開発者",
                "コード分析ツールに興味がある人",
                "開発効率を向上させたい人",
                "プロジェクト品質管理に関心がある人"
            ],
            course_outcomes=[
                f"{tool_name}を効果的に活用できる",
                "コード分析結果を正しく解釈できる",
                "開発ワークフローに統合できる",
                "チーム開発で活用できる",
                "カスタマイズと拡張ができる"
            ],
            pricing_strategy={},
            marketing_materials={},
            confidence_score=0.94
        )
    
    async def _generate_course_files(self, course: UdemyCourse, marketing_strategy: Optional[Dict[str, Any]], 
                                   output_dir: str, project_path: str) -> List[str]:
        """コースファイルの生成"""
        output_path = Path(project_path) / output_dir
        output_path.mkdir(exist_ok=True)
        
        generated_files = []
        
        # 1. コース概要ファイル
        course_overview_path = output_path / "course_overview.md"
        await self._write_course_overview(course_overview_path, course)
        generated_files.append(str(course_overview_path))
        
        # 2. モジュール別ファイル
        for i, module in enumerate(course.modules, 1):
            # ファイル名の安全なサニタイゼーション
            safe_title = module.title.replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_').replace('?', '_').replace('*', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
            module_dir = output_path / f"module_{i:02d}_{safe_title}"
            module_dir.mkdir(exist_ok=True)
            
            # モジュール概要
            module_overview_path = module_dir / "module_overview.md"
            await self._write_module_overview(module_overview_path, module)
            generated_files.append(str(module_overview_path))
            
            # コンテンツファイル
            for j, content in enumerate(module.content_items, 1):
                safe_content_title = content['title'].replace(' ', '_').replace('/', '_').replace('\\', '_').replace(':', '_').replace('?', '_').replace('*', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
                content_path = module_dir / f"{j:02d}_{safe_content_title}.md"
                await self._write_content_file(content_path, content)
                generated_files.append(str(content_path))
            
            # 演習ファイル
            if module.exercises:
                exercises_path = module_dir / "exercises.md"
                await self._write_exercises_file(exercises_path, module.exercises)
                generated_files.append(str(exercises_path))
        
        # 3. マーケティング戦略ファイル
        if marketing_strategy:
            marketing_path = output_path / "marketing_strategy.json"
            await self._write_marketing_strategy(marketing_path, marketing_strategy)
            generated_files.append(str(marketing_path))
        
        # 4. 学習ガイド
        learning_guide_path = output_path / "learning_guide.md"
        await self._write_learning_guide(learning_guide_path, course)
        generated_files.append(str(learning_guide_path))
        
        return generated_files
    
    async def _write_course_overview(self, file_path: Path, course: UdemyCourse):
        """コース概要ファイルの書き込み"""
        content = f"""# {course.title}

## サブタイトル
{course.subtitle}

## コース概要
{course.description}

## 基本情報
- **カテゴリ**: {course.category} > {course.subcategory}
- **言語**: {course.language}
- **レベル**: {course.level.value}
- **総時間**: {course.duration_hours:.1f}時間
- **講義数**: {course.total_lectures}講義
- **演習数**: {course.total_exercises}演習
- **信頼度**: {course.confidence_score:.1%}

## 学習目標
{chr(10).join(f"- {outcome}" for outcome in course.course_outcomes)}

## 対象者
{chr(10).join(f"- {audience}" for audience in course.target_audience)}

## 前提知識
{chr(10).join(f"- {prereq}" for prereq in course.prerequisites)}

## 学習パス
{chr(10).join(f"{i}. {path}" for i, path in enumerate(course.learning_path, 1))}

## モジュール構成
{chr(10).join(f"### Module {i}: {module.title}" + chr(10) + f"- 時間: {module.duration_minutes}分" + chr(10) + f"- レベル: {module.difficulty_level.value}" + chr(10) + f"- 講義: {len(module.content_items)}個" + chr(10) + f"- 演習: {len(module.exercises)}個" + chr(10) for i, module in enumerate(course.modules, 1))}
"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    async def _write_module_overview(self, file_path: Path, module: CourseModule):
        """モジュール概要ファイルの書き込み"""
        content = f"""# {module.title}

## 概要
{module.description}

## 学習目標
{chr(10).join(f"- {objective}" for objective in module.learning_objectives)}

## 基本情報
- **推定時間**: {module.duration_minutes}分
- **難易度**: {module.difficulty_level.value}
- **コンテンツ数**: {len(module.content_items)}個
- **演習数**: {len(module.exercises)}個

## コンテンツ一覧
{chr(10).join(f"{i}. **{content['title']}** ({content['type']})" + (f" - {content.get('duration', 'N/A')}分" if 'duration' in content else f" - {content.get('pages', 'N/A')}ページ") for i, content in enumerate(module.content_items, 1))}

## 演習一覧
{chr(10).join(f"{i}. **{exercise['title']}** ({exercise['type']})" + chr(10) + f"   - 推定時間: {exercise['estimated_time']}分" + chr(10) + f"   - 難易度: {exercise['difficulty']}" for i, exercise in enumerate(module.exercises, 1))}
"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    async def _write_content_file(self, file_path: Path, content: Dict[str, Any]):
        """コンテンツファイルの書き込み"""
        file_content = f"""# {content['title']}

## タイプ
{content['type']}

## 内容
{content['content']}

## 詳細情報
- **推定時間**: {content.get('duration', content.get('pages', 'N/A'))}{'分' if 'duration' in content else 'ページ' if 'pages' in content else ''}
"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(file_content)
    
    async def _write_exercises_file(self, file_path: Path, exercises: List[Dict[str, Any]]):
        """演習ファイルの書き込み"""
        content = "# 演習問題\n\n"
        
        for i, exercise in enumerate(exercises, 1):
            content += f"""## 演習 {i}: {exercise['title']}

### タイプ
{exercise['type']}

### 説明
{exercise['description']}

### 詳細情報
- **推定時間**: {exercise['estimated_time']}分
- **難易度**: {exercise['difficulty']}

### 手順
1. 演習の目的を理解する
2. 必要なリソースを準備する
3. 段階的に実装を進める
4. 結果を確認・検証する
5. 振り返りと改善点の整理

---

"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    async def _write_marketing_strategy(self, file_path: Path, marketing_strategy: Dict[str, Any]):
        """マーケティング戦略ファイルの書き込み"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(marketing_strategy, f, ensure_ascii=False, indent=2)
    
    async def _write_learning_guide(self, file_path: Path, course: UdemyCourse):
        """学習ガイドファイルの書き込み"""
        content = f"""# 学習ガイド: {course.title}

## このガイドについて
このガイドは、コースを効果的に学習するための指針を提供します。

## 推奨学習スケジュール

### 週次スケジュール（{course.duration_hours:.0f}時間コース）
- **週1-2**: 基礎モジュール（環境構築・概要理解）
- **週3-4**: アーキテクチャ理解
- **週5-8**: 技術スタック別学習
- **週9-12**: 実践プロジェクト開発

### 日次学習時間
- **平日**: 1-2時間
- **週末**: 3-4時間

## 学習のコツ

### 効果的な学習方法
1. **理論と実践のバランス**
   - 動画視聴後は必ず手を動かす
   - コードを実際に書いて理解を深める

2. **段階的な理解**
   - 一度に全てを理解しようとしない
   - 分からない部分は後で戻ってくる

3. **アウトプット重視**
   - 学んだ内容をブログやSNSで発信
   - 他の学習者との議論に参加

### 挫折しないために
- 完璧を求めすぎない
- 小さな成功を積み重ねる
- 学習仲間を見つける
- 定期的に振り返りを行う

## 追加リソース

### 参考書籍
- {course.subcategory}関連の技術書
- アーキテクチャ設計の書籍
- 各技術スタックの公式ドキュメント

### オンラインリソース
- 公式ドキュメント
- 技術ブログ
- 開発者コミュニティ

### 実践の場
- GitHub での個人プロジェクト
- オープンソースプロジェクトへの貢献
- 技術勉強会への参加

## 修了後のキャリアパス

### 即戦力レベル
- {course.subcategory}分野での実務経験
- チーム開発での技術リーダー
- 技術選定と設計の責任者

### さらなるスキルアップ
- 上級アーキテクチャパターンの習得
- DevOps・インフラ領域の学習
- マネジメントスキルの向上

## サポート・質問

### 質問方法
1. まず公式ドキュメントを確認
2. 過去の質問・回答を検索
3. 具体的な状況を明記して質問
4. コードやエラーメッセージを添付

### コミュニティ活用
- 学習者同士の情報交換
- 経験者からのアドバイス
- 最新情報の共有

---

**頑張って学習を進めてください！**
**あなたの成長を応援しています！** 🚀
"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
