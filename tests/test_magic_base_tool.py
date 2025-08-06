#!/usr/bin/env python3
"""
Magic Base Tool のテストスイート

テスト駆動開発（TDD）により、魔法基盤の品質を保証します。
すべての魔法ツールの基盤となるため、100%のテストカバレッジを目指します。
"""

import asyncio
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from tree_sitter_analyzer.mcp.tools.magic_base_tool import (
    MagicBaseTool,
    MagicType,
    MagicPriority,
    MagicRequest,
    MagicResult,
    ProjectDNA,
    MagicToolFactory,
    SecurityError,
    MagicExecutionError
)


class TestMagicBaseTool:
    """MagicBaseTool の包括的テストスイート"""
    
    @pytest.fixture
    def temp_project_dir(self):
        """テスト用の一時プロジェクトディレクトリ"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # テスト用ファイル作成
            (project_path / "main.py").write_text("""
def hello_world():
    print("Hello, World!")
    
class TestClass:
    def __init__(self):
        self.value = 42
    
    def get_value(self):
        return self.value
""")
            
            (project_path / "requirements.txt").write_text("pytest>=7.0.0\nfastapi>=0.100.0")
            
            yield str(project_path)
    



class TestMagicRequest:
    """MagicRequest データクラスのテスト"""
    
    def test_magic_request_creation(self):
        """MagicRequest の正常作成テスト"""
        request = MagicRequest(
            magic_type=MagicType.SOLVE,
            project_path="/test/path",
            parameters={"param1": "value1"},
            priority=MagicPriority.HIGH
        )
        
        assert request.magic_type == MagicType.SOLVE
        assert request.project_path == "/test/path"
        assert request.parameters == {"param1": "value1"}
        assert request.priority == MagicPriority.HIGH
        assert request.timeout_seconds == 300  # デフォルト値
    
    def test_magic_request_defaults(self):
        """MagicRequest のデフォルト値テスト"""
        request = MagicRequest(
            magic_type=MagicType.COURSE,
            project_path="/test/path",
            parameters={}
        )
        
        assert request.priority == MagicPriority.NORMAL
        assert request.timeout_seconds == 300
        assert request.user_id is None
        assert request.session_id is None


class TestMagicResult:
    """MagicResult データクラスのテスト"""
    
    def test_magic_result_creation(self):
        """MagicResult の正常作成テスト"""
        result = MagicResult(
            success=True,
            magic_type=MagicType.FLOW,
            execution_time=1.5,
            result_data={"flow": "diagram"},
            confidence_score=0.9,
            side_effects=["Effect 1"],
            recommendations=["Recommendation 1"]
        )
        
        assert result.success is True
        assert result.magic_type == MagicType.FLOW
        assert result.execution_time == 1.5
        assert result.result_data == {"flow": "diagram"}
        assert result.confidence_score == 0.9
        assert result.side_effects == ["Effect 1"]
        assert result.recommendations == ["Recommendation 1"]
        assert result.error_message is None


class TestProjectDNA:
    """ProjectDNA データクラスのテスト"""
    
    def test_project_dna_creation(self):
        """ProjectDNA の正常作成テスト"""
        dna = ProjectDNA(
            project_id="test123",
            project_path="/test/project",
            tech_stack=["Python", "FastAPI"],
            architecture_pattern="MVC",
            business_domain="E-Commerce",
            complexity_score=5.5,
            quality_metrics={"maintainability": 0.8},
            file_count=10,
            total_lines=1000,
            last_analyzed=1234567890.0,
            confidence=0.95
        )
        
        assert dna.project_id == "test123"
        assert dna.tech_stack == ["Python", "FastAPI"]
        assert dna.architecture_pattern == "MVC"
        assert dna.business_domain == "E-Commerce"
        assert dna.complexity_score == 5.5
        assert dna.confidence == 0.95


class TestMagicBaseToolCore:
    """MagicBaseTool の核心機能テスト"""

    @pytest.fixture
    def mock_magic_tool(self):
        """テスト用のモック魔法ツール"""
        class MockMagicTool(MagicBaseTool):
            def __init__(self):
                super().__init__("test_magic", "Test magic tool")

            async def _execute_magic(self, request: MagicRequest, project_dna: ProjectDNA) -> MagicResult:
                return MagicResult(
                    success=True,
                    magic_type=MagicType.SOLVE,
                    execution_time=0.5,
                    result_data={"test": "success"},
                    confidence_score=0.95,
                    side_effects=["Test side effect"],
                    recommendations=["Test recommendation"]
                )

            def _get_magic_type(self) -> MagicType:
                return MagicType.SOLVE

        return MockMagicTool()

    @pytest.mark.asyncio
    async def test_execute_success_flow(self, mock_magic_tool, temp_project_dir):
        """魔法実行の正常フローテスト"""
        arguments = {
            "project_path": temp_project_dir,
            "test_param": "test_value"
        }
        
        with patch.object(mock_magic_tool.security_validator, 'validate_path', return_value=True):
            result = await mock_magic_tool.execute(arguments)
        
        assert result["success"] is True
        assert result["magic_type"] == "solve"
        assert "execution_time" in result
        assert "confidence" in result
        assert result["result"]["test"] == "success"
        assert len(result["side_effects"]) > 0
        assert len(result["recommendations"]) > 0
    
    @pytest.mark.asyncio
    async def test_execute_missing_project_path(self, mock_magic_tool):
        """project_path 未指定時のエラーハンドリングテスト"""
        arguments = {"other_param": "value"}
        
        result = await mock_magic_tool.execute(arguments)
        
        assert result["success"] is False
        assert "project_path is required" in result["error"]
        assert "suggestions" in result
    
    @pytest.mark.asyncio
    async def test_execute_security_validation_failure(self, mock_magic_tool, temp_project_dir):
        """セキュリティ検証失敗時のテスト"""
        arguments = {"project_path": temp_project_dir}
        
        with patch.object(mock_magic_tool.security_validator, 'validate_path', return_value=False):
            result = await mock_magic_tool.execute(arguments)
        
        assert result["success"] is False
        assert "Invalid or unsafe project path" in result["error"]
    
    @pytest.mark.asyncio
    async def test_instant_project_understanding(self, mock_magic_tool, temp_project_dir):
        """プロジェクト瞬間理解のテスト"""
        with patch.object(mock_magic_tool.security_validator, 'validate_path', return_value=True):
            project_dna = await mock_magic_tool._instant_project_understanding(temp_project_dir)
        
        assert isinstance(project_dna, ProjectDNA)
        assert project_dna.project_path == temp_project_dir
        assert len(project_dna.tech_stack) > 0
        assert project_dna.architecture_pattern is not None
        assert project_dna.business_domain is not None
        assert 0 <= project_dna.complexity_score <= 10
        assert 0 <= project_dna.confidence <= 1
    
    @pytest.mark.asyncio
    async def test_project_understanding_caching(self, mock_magic_tool, temp_project_dir):
        """プロジェクト理解のキャッシュ機能テスト"""
        with patch.object(mock_magic_tool.security_validator, 'validate_path', return_value=True):
            # 初回実行
            dna1 = await mock_magic_tool._instant_project_understanding(temp_project_dir)
            
            # 2回目実行（キャッシュから取得されるはず）
            dna2 = await mock_magic_tool._instant_project_understanding(temp_project_dir)
        
        assert dna1.project_id == dna2.project_id
        assert dna1.last_analyzed == dna2.last_analyzed  # キャッシュから取得された証拠
    
    def test_generate_project_id_consistency(self, mock_magic_tool):
        """プロジェクトID生成の一貫性テスト"""
        path1 = "/test/project"
        path2 = "/test/project"
        path3 = "/test/different"
        
        id1 = mock_magic_tool._generate_project_id(path1)
        id2 = mock_magic_tool._generate_project_id(path2)
        id3 = mock_magic_tool._generate_project_id(path3)
        
        assert id1 == id2  # 同じパスは同じID
        assert id1 != id3  # 異なるパスは異なるID
        assert len(id1) == 16  # 16文字のハッシュ
    
    @pytest.mark.asyncio
    async def test_tech_stack_detection(self, mock_magic_tool, temp_project_dir):
        """技術スタック検出のテスト"""
        tech_stack = await mock_magic_tool._analyze_tech_stack(temp_project_dir)
        
        assert "Python" in tech_stack  # .py ファイルがあるため
        assert isinstance(tech_stack, list)
        assert len(tech_stack) > 0
    
    @pytest.mark.asyncio
    async def test_architecture_pattern_detection(self, mock_magic_tool, temp_project_dir):
        """アーキテクチャパターン検出のテスト"""
        pattern = await mock_magic_tool._detect_architecture_pattern(temp_project_dir)
        
        assert isinstance(pattern, str)
        assert len(pattern) > 0
    
    @pytest.mark.asyncio
    async def test_business_domain_inference(self, mock_magic_tool, temp_project_dir):
        """ビジネスドメイン推定のテスト"""
        domain = await mock_magic_tool._infer_business_domain(temp_project_dir)
        
        assert isinstance(domain, str)
        assert len(domain) > 0
    
    @pytest.mark.asyncio
    async def test_complexity_metrics_calculation(self, mock_magic_tool, temp_project_dir):
        """複雑度メトリクス計算のテスト"""
        metrics = await mock_magic_tool._calculate_complexity_metrics(temp_project_dir)
        
        assert "file_count" in metrics
        assert "total_lines" in metrics
        assert "overall_complexity" in metrics
        assert metrics["file_count"] >= 1  # 少なくとも1つのPythonファイルがある
        assert metrics["total_lines"] > 0
        assert 0 <= metrics["overall_complexity"] <= 10
    
    @pytest.mark.asyncio
    async def test_quality_metrics_assessment(self, mock_magic_tool, temp_project_dir):
        """品質メトリクス評価のテスト"""
        quality = await mock_magic_tool._assess_quality_metrics(temp_project_dir)
        
        assert "maintainability" in quality
        assert "readability" in quality
        assert "testability" in quality
        assert "security" in quality
        assert "performance" in quality
        
        # すべての値が0-1の範囲内
        for metric_value in quality.values():
            assert 0 <= metric_value <= 1


class TestMagicToolFactory:
    """MagicToolFactory のテスト"""
    
    def test_register_and_create_magic_tool(self):
        """魔法ツールの登録と生成テスト"""
        class TestMagicTool(MagicBaseTool):
            def __init__(self):
                super().__init__("test", "Test tool")
            
            async def _execute_magic(self, request, project_dna):
                pass
            
            def _get_magic_type(self):
                return MagicType.OPTIMIZE
        
        # 登録
        MagicToolFactory.register_magic_tool(MagicType.OPTIMIZE, TestMagicTool)
        
        # 生成
        tool = MagicToolFactory.create_magic_tool(MagicType.OPTIMIZE)
        
        assert isinstance(tool, TestMagicTool)
        assert tool._get_magic_type() == MagicType.OPTIMIZE
    
    def test_create_unknown_magic_tool(self):
        """未知の魔法タイプでの生成エラーテスト"""
        with pytest.raises(ValueError, match="Unknown magic type"):
            MagicToolFactory.create_magic_tool(MagicType.DREAM)
    
    def test_get_available_magic_types(self):
        """利用可能な魔法タイプ取得テスト"""
        # 前のテストで OPTIMIZE が登録されているはず
        available_types = MagicToolFactory.get_available_magic_types()
        
        assert isinstance(available_types, list)
        assert MagicType.OPTIMIZE in available_types


class TestMagicEnums:
    """魔法関連のEnum テスト"""
    
    def test_magic_type_enum(self):
        """MagicType Enum のテスト"""
        assert MagicType.SOLVE.value == "solve"
        assert MagicType.COURSE.value == "course"
        assert MagicType.FLOW.value == "flow"
        assert MagicType.OPTIMIZE.value == "optimize"
        assert MagicType.IMPLEMENT.value == "implement"
        assert MagicType.DREAM.value == "dream"
    
    def test_magic_priority_enum(self):
        """MagicPriority Enum のテスト"""
        assert MagicPriority.EMERGENCY.value == 1
        assert MagicPriority.HIGH.value == 2
        assert MagicPriority.NORMAL.value == 3
        assert MagicPriority.LOW.value == 4
        
        # 優先度の順序テスト
        assert MagicPriority.EMERGENCY < MagicPriority.HIGH
        assert MagicPriority.HIGH < MagicPriority.NORMAL
        assert MagicPriority.NORMAL < MagicPriority.LOW


class TestErrorHandling:
    """エラーハンドリングのテスト"""
    
    @pytest.mark.asyncio
    async def test_magic_execution_error_handling(self, mock_magic_tool, temp_project_dir):
        """魔法実行エラーの優雅な処理テスト"""
        # _execute_magic でエラーを発生させる
        async def failing_execute_magic(request, project_dna):
            raise MagicExecutionError("Test magic execution error")
        
        mock_magic_tool._execute_magic = failing_execute_magic
        
        arguments = {"project_path": temp_project_dir}
        
        with patch.object(mock_magic_tool.security_validator, 'validate_path', return_value=True):
            result = await mock_magic_tool.execute(arguments)
        
        assert result["success"] is False
        assert "Test magic execution error" in result["error"]
        assert "suggestions" in result
        assert len(result["suggestions"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
