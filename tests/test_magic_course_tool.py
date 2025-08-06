#!/usr/bin/env python3
"""
Magic Course Tool のテストスイート

教育コンテンツ生成魔法の品質を保証するための包括的テスト。
Udemy級コース自動生成が確実に動作することを検証します。
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tree_sitter_analyzer.mcp.tools.magic_course_tool import (
    MagicCourseGeneratorTool,
    CourseContentGenerator,
    MarketingStrategyGenerator,
    LearningLevel,
    ContentType,
    CourseModule,
    UdemyCourse
)
from tree_sitter_analyzer.mcp.tools.magic_base_tool import (
    MagicType,
    MagicRequest,
    MagicPriority,
    ProjectDNA
)


class TestCourseContentGenerator:
    """CourseContentGenerator のテスト"""
    
    @pytest.fixture
    def content_generator(self):
        return CourseContentGenerator()
    
    @pytest.fixture
    def sample_project_dna(self):
        return ProjectDNA(
            project_id="test123",
            project_path="/test/project",
            tech_stack=["Python", "FastAPI", "React"],
            architecture_pattern="Clean Architecture",
            business_domain="E-Commerce",
            complexity_score=6.5,
            quality_metrics={"maintainability": 0.85, "readability": 0.80},
            file_count=75,
            total_lines=8500,
            last_analyzed=1234567890.0,
            confidence=0.92
        )
    
    @pytest.mark.asyncio
    async def test_generate_course_structure(self, content_generator, sample_project_dna):
        """コース構造生成のテスト"""
        with patch.object(content_generator.deep_analyzer, 'analyze_project_deeply',
                         return_value={"business_flows": [], "code_structure": {"classes": [], "functions": []},
                                     "domain_knowledge": {"key_concepts": []}, "readme_info": {"sections": {}}}):
            modules = await content_generator.generate_course_structure(sample_project_dna)

        assert isinstance(modules, list)
        assert len(modules) >= 4  # 最低4モジュール（導入、業務フロー、アーキテクチャ、プロジェクト）

        # 導入モジュールの確認
        intro_module = modules[0]
        assert "入門" in intro_module.title
        assert intro_module.difficulty_level == LearningLevel.BEGINNER
        assert len(intro_module.content_items) > 0
        assert len(intro_module.exercises) > 0
    
    @pytest.mark.asyncio
    async def test_create_introduction_module(self, content_generator, sample_project_dna):
        """導入モジュール作成のテスト"""
        deep_analysis = {"readme_info": {"sections": {}}, "domain_knowledge": {"key_concepts": []}}
        module = await content_generator._create_introduction_module(sample_project_dna, deep_analysis)
        
        assert isinstance(module, CourseModule)
        assert sample_project_dna.business_domain in module.title
        assert module.difficulty_level == LearningLevel.BEGINNER
        assert module.duration_minutes > 0
        assert len(module.learning_objectives) >= 3
        assert len(module.content_items) >= 2
        assert len(module.exercises) >= 1
        
        # コンテンツタイプの確認
        video_scripts = [item for item in module.content_items if item["type"] == "video_script"]
        text_materials = [item for item in module.content_items if item["type"] == "text_material"]
        assert len(video_scripts) >= 1
        assert len(text_materials) >= 1
    
    @pytest.mark.asyncio
    async def test_create_architecture_module(self, content_generator, sample_project_dna):
        """アーキテクチャモジュール作成のテスト"""
        deep_analysis = {"readme_info": {"sections": {}}, "domain_knowledge": {"key_concepts": []}}
        module = await content_generator._create_architecture_module(sample_project_dna, deep_analysis)
        
        assert isinstance(module, CourseModule)
        assert sample_project_dna.architecture_pattern in module.title
        assert module.difficulty_level == LearningLevel.INTERMEDIATE
        assert module.duration_minutes > 60  # アーキテクチャは時間がかかる
        assert len(module.exercises) >= 2  # 設計演習とコード分析
    
    @pytest.mark.asyncio
    async def test_create_feature_modules(self, content_generator, sample_project_dna):
        """機能別モジュール作成のテスト"""
        deep_analysis = {"code_structure": {"classes": [], "functions": []}}
        modules = await content_generator._create_feature_modules(sample_project_dna, deep_analysis)
        
        assert isinstance(modules, list)
        assert len(modules) >= 1  # 少なくとも1つのモジュール
        
        if modules:
            module = modules[0]
            assert module.difficulty_level == LearningLevel.INTERMEDIATE
            assert len(module.content_items) >= 2
            assert len(module.exercises) >= 2
    
    @pytest.mark.asyncio
    async def test_create_project_module(self, content_generator, sample_project_dna):
        """実践プロジェクトモジュール作成のテスト"""
        deep_analysis = {"readme_info": {"sections": {}}, "domain_knowledge": {"key_concepts": []}}
        module = await content_generator._create_project_module(sample_project_dna, deep_analysis)
        
        assert isinstance(module, CourseModule)
        assert "実践" in module.title or "プロジェクト" in module.title
        assert module.difficulty_level == LearningLevel.ADVANCED
        assert module.duration_minutes >= 180  # 実践は時間がかかる
        
        # 最終プロジェクトが含まれているか
        capstone_exercises = [ex for ex in module.exercises if ex["type"] == "capstone_project"]
        assert len(capstone_exercises) >= 1
    
    @pytest.mark.asyncio
    async def test_script_generation_methods(self, content_generator, sample_project_dna):
        """スクリプト生成メソッドのテスト"""
        deep_analysis = {"readme_info": {"sections": {}}, "domain_knowledge": {"key_concepts": []}, "code_structure": {"functions": []}}

        # ツール概要スクリプト
        overview_script = await content_generator._generate_tool_overview_script(sample_project_dna, deep_analysis)
        assert isinstance(overview_script, str)
        assert len(overview_script) > 100

        # インストールスクリプト
        install_script = await content_generator._generate_installation_script(sample_project_dna, deep_analysis)
        assert isinstance(install_script, str)
        assert "インストール" in install_script

        # 機能基礎スクリプト
        feature_script = await content_generator._generate_feature_basics_script("コード分析機能", sample_project_dna)
        assert isinstance(feature_script, str)
        assert "コード分析機能" in feature_script


class TestMarketingStrategyGenerator:
    """MarketingStrategyGenerator のテスト"""
    
    @pytest.fixture
    def marketing_generator(self):
        return MarketingStrategyGenerator()
    
    @pytest.fixture
    def sample_course(self):
        return UdemyCourse(
            title="実践E-Commerce開発",
            subtitle="Python・FastAPI・Reactで学ぶ現代的アプリケーション構築",
            description="実際のE-Commerceプロジェクトを通じて学習",
            category="Development",
            subcategory="E-Commerce",
            language="japanese",
            level=LearningLevel.INTERMEDIATE,
            duration_hours=45.0,
            modules=[],
            total_lectures=120,
            total_exercises=50,
            learning_path=[],
            prerequisites=[],
            target_audience=[],
            course_outcomes=[],
            pricing_strategy={},
            marketing_materials={},
            confidence_score=0.94
        )
    
    @pytest.fixture
    def sample_project_dna(self):
        return ProjectDNA(
            project_id="test123",
            project_path="/test/project",
            tech_stack=["Python", "FastAPI", "React"],
            architecture_pattern="Clean Architecture",
            business_domain="E-Commerce",
            complexity_score=6.5,
            quality_metrics={"maintainability": 0.85},
            file_count=75,
            total_lines=8500,
            last_analyzed=1234567890.0,
            confidence=0.92
        )
    
    @pytest.mark.asyncio
    async def test_generate_marketing_strategy(self, marketing_generator, sample_course, sample_project_dna):
        """マーケティング戦略生成のテスト"""
        strategy = await marketing_generator.generate_marketing_strategy(sample_course, sample_project_dna)
        
        assert isinstance(strategy, dict)
        assert "pricing" in strategy
        assert "promotion" in strategy
        assert "target_market" in strategy
        assert "competitive_analysis" in strategy
        assert "revenue_projection" in strategy
    
    @pytest.mark.asyncio
    async def test_generate_pricing_strategy(self, marketing_generator, sample_course, sample_project_dna):
        """価格戦略生成のテスト"""
        pricing = await marketing_generator._generate_pricing_strategy(sample_course, sample_project_dna)
        
        assert isinstance(pricing, dict)
        assert "recommended_price" in pricing
        assert "launch_price" in pricing
        assert "premium_price" in pricing
        assert "strategy" in pricing
        assert "justification" in pricing
        
        # 価格が妥当な範囲内か
        recommended_price = float(pricing["recommended_price"].replace("$", ""))
        assert 50 <= recommended_price <= 500  # 妥当な価格範囲
    
    @pytest.mark.asyncio
    async def test_analyze_target_market(self, marketing_generator, sample_course, sample_project_dna):
        """ターゲット市場分析のテスト"""
        market = await marketing_generator._analyze_target_market(sample_course, sample_project_dna)
        
        assert isinstance(market, dict)
        assert "primary_audience" in market
        assert "secondary_audience" in market
        assert "market_size" in market
        assert "growth_potential" in market
        assert "key_demographics" in market
        
        assert sample_project_dna.business_domain in market["primary_audience"]
    
    @pytest.mark.asyncio
    async def test_project_revenue(self, marketing_generator, sample_course, sample_project_dna):
        """収益予測のテスト"""
        revenue = await marketing_generator._project_revenue(sample_course, sample_project_dna)
        
        assert isinstance(revenue, dict)
        assert "conservative_estimate" in revenue
        assert "realistic_estimate" in revenue
        assert "optimistic_estimate" in revenue
        assert "timeframe" in revenue
        assert "assumptions" in revenue
        
        # 収益予測が論理的か
        conservative = float(revenue["conservative_estimate"].replace("$", "").replace(",", ""))
        realistic = float(revenue["realistic_estimate"].replace("$", "").replace(",", ""))
        optimistic = float(revenue["optimistic_estimate"].replace("$", "").replace(",", ""))
        
        assert conservative <= realistic <= optimistic


class TestMagicCourseGeneratorTool:
    """MagicCourseGeneratorTool のテスト"""
    
    @pytest.fixture
    def magic_course_tool(self):
        return MagicCourseGeneratorTool()
    
    @pytest.fixture
    def temp_project_dir(self):
        """テスト用の一時プロジェクトディレクトリ"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # テスト用プロジェクトファイル作成
            (project_path / "main.py").write_text("""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/items/")
def create_item(item: Item):
    return item
""")
            
            (project_path / "requirements.txt").write_text("""
fastapi>=0.100.0
uvicorn>=0.20.0
pydantic>=2.0.0
""")
            
            (project_path / "README.md").write_text("""
# E-Commerce API Project

This is a sample e-commerce API built with FastAPI.
""")
            
            yield str(project_path)
    
    def test_magic_course_tool_initialization(self, magic_course_tool):
        """MagicCourseGeneratorTool の初期化テスト"""
        assert magic_course_tool.name == "magic_course"
        assert "Udemy級コース" in magic_course_tool.description
        assert magic_course_tool._get_magic_type() == MagicType.COURSE
        assert hasattr(magic_course_tool, 'content_generator')
        assert hasattr(magic_course_tool, 'marketing_generator')
    
    def test_input_schema_properties(self, magic_course_tool):
        """入力スキーマプロパティのテスト"""
        schema = magic_course_tool._get_input_schema_properties()
        
        assert "project_path" in schema
        assert "target_level" in schema
        assert "language" in schema
        assert "output_dir" in schema
        assert "include_marketing" in schema
        
        # デフォルト値の確認
        assert schema["target_level"]["default"] == "intermediate"
        assert schema["language"]["default"] == "japanese"
        assert schema["output_dir"]["default"] == "Training"
        assert schema["include_marketing"]["default"] is True
    
    def test_required_parameters(self, magic_course_tool):
        """必須パラメータのテスト"""
        required = magic_course_tool._get_required_parameters()
        assert "project_path" in required
        assert len(required) == 1  # project_pathのみ必須
    
    @pytest.mark.asyncio
    async def test_execute_magic_success(self, magic_course_tool, temp_project_dir):
        """魔法実行の成功テスト"""
        request = MagicRequest(
            magic_type=MagicType.COURSE,
            project_path=temp_project_dir,
            parameters={
                "target_level": "intermediate",
                "language": "japanese",
                "output_dir": "Training",
                "include_marketing": True
            },
            priority=MagicPriority.NORMAL
        )
        
        project_dna = ProjectDNA(
            project_id="test123",
            project_path=temp_project_dir,
            tech_stack=["Python", "FastAPI"],
            architecture_pattern="REST API",
            business_domain="E-Commerce",
            complexity_score=4.0,
            quality_metrics={"maintainability": 0.8},
            file_count=3,
            total_lines=50,
            last_analyzed=1234567890.0,
            confidence=0.90
        )
        
        # 魔法実行
        result = await magic_course_tool._execute_magic(request, project_dna)
        
        # 結果検証
        assert result.success is True
        assert result.magic_type == MagicType.COURSE
        assert result.execution_time > 0
        assert result.confidence_score >= 0.8
        
        # コース情報の検証
        course_info = result.result_data["course_info"]
        assert "title" in course_info
        assert course_info["duration_hours"] > 0
        assert course_info["total_lectures"] > 0
        assert course_info["total_exercises"] > 0
        assert course_info["modules_count"] >= 4
        assert course_info["target_level"] == "intermediate"
        assert course_info["language"] == "japanese"
        
        # 生成コンテンツの検証
        content = result.result_data["content_generated"]
        assert content["video_scripts"] > 0
        assert content["text_materials"] > 0
        assert content["exercises"] > 0
        assert content["total_pages"] > 0
        
        # 出力ファイルの検証
        output_files = result.result_data["output_files"]
        assert len(output_files) > 0
        
        # マーケティング戦略の検証
        marketing = result.result_data["marketing_strategy"]
        assert marketing is not None
        assert "pricing" in marketing
        assert "revenue_projection" in marketing
        
        # 副次効果と推奨事項の検証
        assert len(result.side_effects) > 0
        assert len(result.recommendations) > 0
        assert any("動画スクリプト" in effect for effect in result.side_effects)
        assert any("推奨" in rec for rec in result.recommendations)
    
    @pytest.mark.asyncio
    async def test_build_course_info(self, magic_course_tool):
        """コース情報構築のテスト"""
        # テスト用モジュール
        modules = [
            CourseModule(
                title="テストモジュール1",
                description="テスト用",
                learning_objectives=["目標1", "目標2"],
                duration_minutes=60,
                content_items=[{"type": "video_script", "title": "動画1"}],
                exercises=[{"type": "exercise", "title": "演習1"}],
                difficulty_level=LearningLevel.BEGINNER
            ),
            CourseModule(
                title="テストモジュール2",
                description="テスト用",
                learning_objectives=["目標3"],
                duration_minutes=90,
                content_items=[{"type": "text_material", "title": "テキスト1"}],
                exercises=[],
                difficulty_level=LearningLevel.INTERMEDIATE
            )
        ]
        
        project_dna = ProjectDNA(
            project_id="test123",
            project_path="/test",
            tech_stack=["Python", "FastAPI"],
            architecture_pattern="Clean Architecture",
            business_domain="E-Commerce",
            complexity_score=5.0,
            quality_metrics={"maintainability": 0.8},
            file_count=50,
            total_lines=5000,
            last_analyzed=1234567890.0,
            confidence=0.95
        )
        
        course = await magic_course_tool._build_course_info(
            modules, project_dna, LearningLevel.INTERMEDIATE, "japanese"
        )
        
        assert isinstance(course, UdemyCourse)
        assert project_dna.business_domain in course.title
        assert course.level == LearningLevel.INTERMEDIATE
        assert course.language == "japanese"
        assert course.duration_hours == 2.5  # (60 + 90) / 60
        assert course.total_lectures == 2
        assert course.total_exercises == 1
        assert len(course.modules) == 2
        assert course.confidence_score > 0.9
    
    @pytest.mark.asyncio
    async def test_generate_course_files(self, magic_course_tool, temp_project_dir):
        """コースファイル生成のテスト"""
        # テスト用コース
        course = UdemyCourse(
            title="テストコース",
            subtitle="テスト用サブタイトル",
            description="テスト用説明",
            category="Development",
            subcategory="Test",
            language="japanese",
            level=LearningLevel.INTERMEDIATE,
            duration_hours=10.0,
            modules=[
                CourseModule(
                    title="テストモジュール",
                    description="テスト用モジュール",
                    learning_objectives=["目標1"],
                    duration_minutes=60,
                    content_items=[{
                        "type": "video_script",
                        "title": "テスト動画",
                        "content": "テスト内容",
                        "duration": 30
                    }],
                    exercises=[{
                        "type": "hands_on",
                        "title": "テスト演習",
                        "description": "テスト演習説明",
                        "estimated_time": 30,
                        "difficulty": "beginner"
                    }],
                    difficulty_level=LearningLevel.BEGINNER
                )
            ],
            total_lectures=1,
            total_exercises=1,
            learning_path=["テストモジュール"],
            prerequisites=["基礎知識"],
            target_audience=["開発者"],
            course_outcomes=["スキル習得"],
            pricing_strategy={},
            marketing_materials={},
            confidence_score=0.95
        )
        
        marketing_strategy = {
            "pricing": {"recommended_price": "$100"},
            "revenue_projection": {"realistic_estimate": "$10000"}
        }
        
        # ファイル生成
        output_files = await magic_course_tool._generate_course_files(
            course, marketing_strategy, "Training", temp_project_dir
        )
        
        # 生成ファイルの検証
        assert len(output_files) > 0
        
        # 各ファイルが実際に存在するか確認
        for file_path in output_files:
            assert Path(file_path).exists()
            assert Path(file_path).stat().st_size > 0  # ファイルが空でない
        
        # 特定ファイルの内容確認
        training_dir = Path(temp_project_dir) / "Training"
        assert training_dir.exists()
        
        course_overview = training_dir / "course_overview.md"
        assert course_overview.exists()
        
        with open(course_overview, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "テストコース" in content
            assert "10.0時間" in content
        
        # マーケティング戦略ファイルの確認
        marketing_file = training_dir / "marketing_strategy.json"
        assert marketing_file.exists()
        
        with open(marketing_file, 'r', encoding='utf-8') as f:
            marketing_data = json.load(f)
            assert "pricing" in marketing_data
            assert "revenue_projection" in marketing_data


class TestIntegration:
    """統合テスト"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_course_generation(self):
        """エンドツーエンドのコース生成テスト"""
        magic_tool = MagicCourseGeneratorTool()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # 実際のプロジェクト構造を模擬
            (project_path / "src").mkdir()
            (project_path / "src" / "main.py").write_text("""
from fastapi import FastAPI
from sqlalchemy import create_engine

app = FastAPI(title="E-Commerce API")

@app.get("/products")
def get_products():
    return {"products": []}
""")
            
            (project_path / "requirements.txt").write_text("fastapi>=0.100.0")
            (project_path / "README.md").write_text("# E-Commerce Project")
            
            arguments = {
                "project_path": str(project_path),
                "target_level": "intermediate",
                "language": "japanese",
                "output_dir": "Training",
                "include_marketing": True
            }
            
            # セキュリティ検証をモック
            with patch.object(magic_tool.security_validator, 'validate_file_path', return_value=(True, None)):
                result = await magic_tool.execute(arguments)
            
            # エンドツーエンドの結果検証
            assert result["success"] is True
            assert "course_info" in result["result"]
            assert "content_generated" in result["result"]
            assert "output_files" in result["result"]
            assert "marketing_strategy" in result["result"]
            
            # 実際にファイルが生成されているか確認
            training_dir = project_path / "Training"
            assert training_dir.exists()
            
            # 主要ファイルの存在確認
            assert (training_dir / "course_overview.md").exists()
            assert (training_dir / "learning_guide.md").exists()
            assert (training_dir / "marketing_strategy.json").exists()
            
            # モジュールディレクトリの存在確認
            module_dirs = [d for d in training_dir.iterdir() if d.is_dir() and d.name.startswith("module_")]
            assert len(module_dirs) >= 4  # 最低4モジュール


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
