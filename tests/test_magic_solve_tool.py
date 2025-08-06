#!/usr/bin/env python3
"""
Magic Solve Tool のテストスイート

障害解決魔法の品質を保証するための包括的テスト。
深夜3時の奇跡が確実に動作することを検証します。
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tree_sitter_analyzer.mcp.tools.magic_solve_tool import (
    MagicSolveTool,
    FailureDetective,
    AutoHealer,
    FailureType,
    SeverityLevel,
    FailureAnalysis,
    FixSolution
)
from tree_sitter_analyzer.mcp.tools.magic_base_tool import (
    MagicType,
    MagicRequest,
    MagicPriority,
    ProjectDNA
)


class TestFailureDetective:
    """FailureDetective（AI探偵）のテスト"""
    
    @pytest.fixture
    def detective(self):
        return FailureDetective()
    
    @pytest.fixture
    def sample_project_dna(self):
        return ProjectDNA(
            project_id="test123",
            project_path="/test/project",
            tech_stack=["Java", "Spring"],
            architecture_pattern="MVC",
            business_domain="E-Commerce",
            complexity_score=5.0,
            quality_metrics={"maintainability": 0.8},
            file_count=50,
            total_lines=5000,
            last_analyzed=1234567890.0,
            confidence=0.95
        )
    
    def test_identify_null_pointer_failure(self, detective):
        """Null参照エラーの特定テスト"""
        error_log = """
        Exception in thread "main" java.lang.NullPointerException
            at com.example.UserService.validateUser(UserService.java:127)
            at com.example.Controller.handleRequest(Controller.java:45)
        """
        
        failure_type = detective._identify_failure_type(error_log)
        assert failure_type == FailureType.NULL_POINTER
    
    def test_identify_memory_leak_failure(self, detective):
        """メモリリークの特定テスト"""
        error_log = """
        java.lang.OutOfMemoryError: Java heap space
            at com.example.PaymentService.processLargeOrder(PaymentService.java:89)
        """
        
        failure_type = detective._identify_failure_type(error_log)
        assert failure_type == FailureType.MEMORY_LEAK
    
    def test_identify_performance_failure(self, detective):
        """性能問題の特定テスト"""
        error_log = """
        Request timeout after 30 seconds
        Slow query detected: SELECT * FROM orders WHERE created_at > ?
        Performance degradation in OrderService.getRecentOrders()
        """
        
        failure_type = detective._identify_failure_type(error_log)
        assert failure_type == FailureType.PERFORMANCE
    
    def test_identify_security_failure(self, detective):
        """セキュリティ問題の特定テスト"""
        error_log = """
        Security violation: Unauthorized access attempt
        SQL injection detected in user input
        Authentication failed for user: admin'; DROP TABLE users; --
        """
        
        failure_type = detective._identify_failure_type(error_log)
        assert failure_type == FailureType.SECURITY
    
    def test_assess_critical_severity(self, detective):
        """クリティカル深刻度の評価テスト"""
        error_log = "CRITICAL: System down - service unavailable"
        severity = detective._assess_severity(error_log, FailureType.MEMORY_LEAK)
        assert severity == SeverityLevel.CRITICAL
    
    def test_assess_high_severity_by_type(self, detective):
        """タイプによる高深刻度の評価テスト"""
        error_log = "Memory leak detected"
        severity = detective._assess_severity(error_log, FailureType.MEMORY_LEAK)
        assert severity == SeverityLevel.HIGH
    
    def test_assess_medium_severity(self, detective):
        """中深刻度の評価テスト"""
        error_log = "NullPointerException occurred"
        severity = detective._assess_severity(error_log, FailureType.NULL_POINTER)
        assert severity == SeverityLevel.MEDIUM
    
    @pytest.mark.asyncio
    async def test_identify_affected_areas(self, detective, sample_project_dna):
        """影響範囲特定のテスト"""
        error_log = """
        Exception in thread "main" java.lang.NullPointerException
            at com.example.UserService.validateUser(UserService.java:127)
            at com.example.Controller.handleRequest(Controller.java:45)
            at com.example.Main.main(Main.java:20)
        """
        
        affected_files, error_locations = await detective._identify_affected_areas(error_log, sample_project_dna)
        
        assert "UserService.java" in affected_files
        assert "Controller.java" in affected_files
        assert "Main.java" in affected_files
        assert ("UserService.java", 127) in error_locations
        assert ("Controller.java", 45) in error_locations
        assert ("Main.java", 20) in error_locations
    
    def test_estimate_fix_time_null_pointer(self, detective):
        """Null参照エラーの修復時間推定テスト"""
        fix_time = detective._estimate_fix_time(
            FailureType.NULL_POINTER, 
            SeverityLevel.MEDIUM, 
            2  # affected_file_count
        )
        
        # 基本時間60秒 × 中深刻度1.0 × ファイル数補正1.2 = 72秒
        assert fix_time == 72
    
    def test_estimate_fix_time_critical_memory_leak(self, detective):
        """クリティカルメモリリークの修復時間推定テスト"""
        fix_time = detective._estimate_fix_time(
            FailureType.MEMORY_LEAK,
            SeverityLevel.CRITICAL,
            1  # affected_file_count
        )
        
        # 基本時間120秒 × クリティカル1.5 × ファイル数補正1.1 = 198秒
        assert fix_time == 198
    
    @pytest.mark.asyncio
    async def test_investigate_failure_complete(self, detective, sample_project_dna):
        """完全な障害調査のテスト"""
        error_log = """
        java.lang.NullPointerException: Cannot invoke method on null object
            at com.example.UserService.validateUser(UserService.java:127)
            at com.example.Controller.handleRequest(Controller.java:45)
        """
        
        analysis = await detective.investigate_failure(error_log, sample_project_dna)
        
        assert isinstance(analysis, FailureAnalysis)
        assert analysis.failure_type == FailureType.NULL_POINTER
        assert analysis.severity in [SeverityLevel.MEDIUM, SeverityLevel.HIGH]
        assert "Null参照エラー" in analysis.root_cause
        assert len(analysis.affected_files) > 0
        assert len(analysis.error_locations) > 0
        assert 0.8 <= analysis.confidence <= 1.0
        assert len(analysis.similar_cases) > 0
        assert analysis.estimated_fix_time > 0


class TestAutoHealer:
    """AutoHealer（自動修復エンジン）のテスト"""
    
    @pytest.fixture
    def healer(self):
        return AutoHealer()
    
    @pytest.fixture
    def null_pointer_analysis(self):
        return FailureAnalysis(
            failure_type=FailureType.NULL_POINTER,
            severity=SeverityLevel.MEDIUM,
            root_cause="Null参照エラー: オブジェクトの初期化不足",
            affected_files=["UserService.java"],
            error_locations=[("UserService.java", 127)],
            confidence=0.95,
            similar_cases=["類似事例1", "類似事例2"],
            estimated_fix_time=90
        )
    
    @pytest.fixture
    def memory_leak_analysis(self):
        return FailureAnalysis(
            failure_type=FailureType.MEMORY_LEAK,
            severity=SeverityLevel.HIGH,
            root_cause="メモリリーク: オブジェクトの適切な解放処理の不備",
            affected_files=["PaymentService.java"],
            error_locations=[("PaymentService.java", 89)],
            confidence=0.92,
            similar_cases=["メモリリーク事例1"],
            estimated_fix_time=180
        )
    
    @pytest.fixture
    def sample_project_dna(self):
        return ProjectDNA(
            project_id="test123",
            project_path="/test/project",
            tech_stack=["Java", "Spring"],
            architecture_pattern="MVC",
            business_domain="E-Commerce",
            complexity_score=5.0,
            quality_metrics={"maintainability": 0.8},
            file_count=50,
            total_lines=5000,
            last_analyzed=1234567890.0,
            confidence=0.95
        )
    
    @pytest.mark.asyncio
    async def test_fix_null_pointer(self, healer, null_pointer_analysis, sample_project_dna):
        """Null参照エラー修復のテスト"""
        solution = await healer._fix_null_pointer(null_pointer_analysis, sample_project_dna)
        
        assert isinstance(solution, FixSolution)
        assert solution.solution_type == "null_pointer_fix"
        assert "Null参照チェック" in solution.description
        assert len(solution.code_changes) > 0
        assert "UserService.java" in solution.code_changes
        assert len(solution.prevention_measures) > 0
        assert "Optional パターン" in str(solution.prevention_measures)
        assert solution.success_probability >= 0.9
    
    @pytest.mark.asyncio
    async def test_fix_memory_leak(self, healer, memory_leak_analysis, sample_project_dna):
        """メモリリーク修復のテスト"""
        solution = await healer._fix_memory_leak(memory_leak_analysis, sample_project_dna)
        
        assert isinstance(solution, FixSolution)
        assert solution.solution_type == "memory_leak_fix"
        assert "オブジェクトプール" in solution.description
        assert len(solution.code_changes) > 0
        assert "MemoryManager.java" in solution.code_changes
        assert len(solution.prevention_measures) > 0
        assert "メモリ使用量70%削減" in solution.side_effects
        assert solution.success_probability >= 0.9
    
    @pytest.mark.asyncio
    async def test_generate_fix_solution_routing(self, healer, null_pointer_analysis, sample_project_dna):
        """修復ソリューション生成のルーティングテスト"""
        solution = await healer.generate_fix_solution(null_pointer_analysis, sample_project_dna)
        
        # null_pointer_analysis なので _fix_null_pointer が呼ばれるはず
        assert solution.solution_type == "null_pointer_fix"


class TestMagicSolveTool:
    """MagicSolveTool（障害解決魔法ツール）のテスト"""
    
    @pytest.fixture
    def magic_solve_tool(self):
        return MagicSolveTool()
    
    @pytest.fixture
    def temp_project_dir(self):
        """テスト用の一時プロジェクトディレクトリ"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # テスト用Javaファイル作成
            (project_path / "UserService.java").write_text("""
public class UserService {
    public boolean validateUser(String email) {
        return email.contains("@");  // NullPointerException の原因
    }
}
""")
            
            yield str(project_path)
    
    def test_magic_solve_tool_initialization(self, magic_solve_tool):
        """MagicSolveTool の初期化テスト"""
        assert magic_solve_tool.name == "magic_solve"
        assert "障害を瞬時に解決" in magic_solve_tool.description
        assert magic_solve_tool._get_magic_type() == MagicType.SOLVE
        assert hasattr(magic_solve_tool, 'detective')
        assert hasattr(magic_solve_tool, 'healer')
    
    @pytest.mark.asyncio
    async def test_execute_magic_success(self, magic_solve_tool, temp_project_dir):
        """魔法実行の成功テスト"""
        # テスト用のエラーログ
        error_log = """
        java.lang.NullPointerException: Cannot invoke "String.contains(String)" because "email" is null
            at UserService.validateUser(UserService.java:3)
            at Main.main(Main.java:10)
        """
        
        request = MagicRequest(
            magic_type=MagicType.SOLVE,
            project_path=temp_project_dir,
            parameters={"error_log": error_log},
            priority=MagicPriority.EMERGENCY
        )
        
        project_dna = ProjectDNA(
            project_id="test123",
            project_path=temp_project_dir,
            tech_stack=["Java"],
            architecture_pattern="Standard",
            business_domain="General Application",
            complexity_score=2.0,
            quality_metrics={"maintainability": 0.8},
            file_count=1,
            total_lines=10,
            last_analyzed=1234567890.0,
            confidence=0.95
        )
        
        # 魔法実行
        result = await magic_solve_tool._execute_magic(request, project_dna)
        
        # 結果検証
        assert result.success is True
        assert result.magic_type == MagicType.SOLVE
        assert result.execution_time > 0
        assert result.confidence_score > 0.8
        
        # 調査結果の検証
        investigation = result.result_data["investigation"]
        assert investigation["failure_type"] == "null_pointer"
        assert investigation["severity"] in ["MEDIUM", "HIGH", "CRITICAL"]
        assert "Null参照エラー" in investigation["root_cause"]
        assert len(investigation["affected_files"]) > 0
        
        # ソリューションの検証
        solution = result.result_data["solution"]
        assert solution["type"] == "null_pointer_fix"
        assert "Null参照チェック" in solution["description"]
        assert float(solution["success_probability"].rstrip('%')) >= 90
        
        # 副次効果と推奨事項の検証
        assert len(result.side_effects) > 0
        assert len(result.recommendations) > 0
        assert any("障害調査完了" in effect for effect in result.side_effects)
        assert any("予防策の実装" in rec for rec in result.recommendations)
    
    @pytest.mark.asyncio
    async def test_execute_magic_missing_error_log(self, magic_solve_tool, temp_project_dir):
        """エラーログ未指定時のエラーハンドリングテスト"""
        request = MagicRequest(
            magic_type=MagicType.SOLVE,
            project_path=temp_project_dir,
            parameters={},  # error_log が未指定
            priority=MagicPriority.NORMAL
        )
        
        project_dna = ProjectDNA(
            project_id="test123",
            project_path=temp_project_dir,
            tech_stack=["Java"],
            architecture_pattern="Standard",
            business_domain="General Application",
            complexity_score=2.0,
            quality_metrics={"maintainability": 0.8},
            file_count=1,
            total_lines=10,
            last_analyzed=1234567890.0,
            confidence=0.95
        )
        
        # エラーが発生することを確認
        with pytest.raises(Exception) as exc_info:
            await magic_solve_tool._execute_magic(request, project_dna)
        
        assert "error_log parameter is required" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_execute_complete_workflow(self, magic_solve_tool, temp_project_dir):
        """完全なワークフローのテスト（execute メソッド）"""
        arguments = {
            "project_path": temp_project_dir,
            "error_log": """
            java.lang.OutOfMemoryError: Java heap space
                at PaymentService.processLargeOrder(PaymentService.java:89)
            """,
            "priority": 1  # EMERGENCY
        }
        
        # セキュリティ検証をモック
        with patch.object(magic_solve_tool.security_validator, 'validate_path', return_value=True):
            result = await magic_solve_tool.execute(arguments)
        
        # 結果の検証
        assert result["success"] is True
        assert result["magic_type"] == "solve"
        assert "execution_time" in result
        assert "confidence" in result
        assert "result" in result
        assert "side_effects" in result
        assert "recommendations" in result
        
        # 調査結果の詳細検証
        investigation = result["result"]["investigation"]
        assert investigation["failure_type"] == "memory_leak"
        assert "メモリリーク" in investigation["root_cause"]
        
        # ソリューションの詳細検証
        solution = result["result"]["solution"]
        assert solution["type"] == "memory_leak_fix"
        assert "オブジェクトプール" in solution["description"]


class TestIntegration:
    """統合テスト"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_null_pointer_resolution(self):
        """Null参照エラーのエンドツーエンド解決テスト"""
        # 実際の使用シナリオをシミュレート
        magic_tool = MagicSolveTool()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)
            
            # 問題のあるJavaコード作成
            (project_path / "BuggyService.java").write_text("""
public class BuggyService {
    public String processUser(User user) {
        return user.getName().toUpperCase();  // user が null の場合 NPE
    }
}
""")
            
            # エラーログ
            error_log = """
            Exception in thread "main" java.lang.NullPointerException
                at BuggyService.processUser(BuggyService.java:3)
                at Main.main(Main.java:15)
            """
            
            arguments = {
                "project_path": str(project_path),
                "error_log": error_log
            }
            
            # セキュリティ検証をモック
            with patch.object(magic_tool.security_validator, 'validate_path', return_value=True):
                result = await magic_tool.execute(arguments)
            
            # エンドツーエンドの結果検証
            assert result["success"] is True
            assert result["result"]["investigation"]["failure_type"] == "null_pointer"
            assert result["result"]["solution"]["type"] == "null_pointer_fix"
            assert len(result["recommendations"]) > 0
            
            # 実行時間が合理的範囲内（10秒以内）
            execution_time = float(result["execution_time"].rstrip('秒'))
            assert execution_time < 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
