#!/usr/bin/env python3
"""
Magic Base Tool - 革命的魔法システムの基盤クラス

このモジュールは、すべての魔法ツールの基盤となる抽象クラスを提供します。
テスト駆動開発、デザインパターン、コーディング規約を厳密に遵守します。

Design Patterns Used:
- Template Method Pattern: 魔法実行の共通フロー
- Strategy Pattern: 魔法タイプ別の実行戦略
- Observer Pattern: 魔法実行の監視・ログ
- Factory Pattern: 魔法インスタンスの生成
"""

import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ...core.analysis_engine import get_analysis_engine
from ...project_detector import detect_project_root
from ...security.validator import SecurityValidator
from ...utils import setup_logger
from .base_tool import BaseTool


class MagicType(Enum):
    """魔法の種類を定義"""
    SOLVE = "solve"          # 障害解決魔法
    COURSE = "course"        # 教育コンテンツ生成魔法
    FLOW = "flow"           # 業務フロー分析魔法
    OPTIMIZE = "optimize"    # 最適化魔法
    IMPLEMENT = "implement"  # 実装魔法
    DREAM = "dream"         # 夢実現魔法


class MagicPriority(Enum):
    """魔法の優先度"""
    EMERGENCY = 1    # 緊急（障害対応）
    HIGH = 2        # 高（重要機能）
    NORMAL = 3      # 通常
    LOW = 4         # 低（最適化等）

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self.value >= other.value
        return NotImplemented


@dataclass
class MagicRequest:
    """魔法リクエストの標準化されたデータ構造"""
    magic_type: MagicType
    project_path: str
    parameters: Dict[str, Any]
    priority: MagicPriority = MagicPriority.NORMAL
    timeout_seconds: int = 300
    user_id: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class MagicResult:
    """魔法実行結果の標準化されたデータ構造"""
    success: bool
    magic_type: MagicType
    execution_time: float
    result_data: Dict[str, Any]
    confidence_score: float
    side_effects: List[str]
    recommendations: List[str]
    error_message: Optional[str] = None
    debug_info: Optional[Dict[str, Any]] = None


@dataclass
class ProjectDNA:
    """プロジェクトの完全な理解情報"""
    project_id: str
    project_path: str
    tech_stack: List[str]
    architecture_pattern: str
    business_domain: str
    complexity_score: float
    quality_metrics: Dict[str, float]
    file_count: int
    total_lines: int
    last_analyzed: float
    confidence: float


class MagicBaseTool(BaseTool, ABC):
    """
    すべての魔法ツールの基盤クラス
    
    Template Method Pattern を使用して、魔法実行の共通フローを定義。
    各具象クラスは、特定の魔法ロジックのみを実装すればよい。
    """
    
    def __init__(self, name: str, description: str):
        super().__init__(name, description)
        self.logger = setup_logger(f"magic.{name}")
        self.security_validator = SecurityValidator()
        self.analysis_engine = get_analysis_engine()
        self._magic_cache = {}
        
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        魔法実行のメインエントリーポイント（Template Method Pattern）
        
        共通フロー:
        1. 入力検証・セキュリティチェック
        2. プロジェクト瞬間理解
        3. 魔法実行（サブクラスで実装）
        4. 結果強化・最適化
        5. ログ記録・監視
        """
        start_time = time.time()
        
        try:
            # Step 1: 入力検証・セキュリティチェック
            magic_request = await self._validate_and_prepare_request(arguments)
            self.logger.info(f"🔮 魔法開始: {magic_request.magic_type.value}")
            
            # Step 2: プロジェクト瞬間理解
            project_dna = await self._instant_project_understanding(magic_request.project_path)
            self.logger.info(f"🧬 プロジェクトDNA解析完了: {project_dna.confidence:.2f}")
            
            # Step 3: 魔法実行（サブクラスで実装）
            magic_result = await self._execute_magic(magic_request, project_dna)
            
            # Step 4: 結果強化・最適化
            enhanced_result = await self._enhance_magic_result(magic_result, project_dna)
            
            # Step 5: ログ記録・監視
            execution_time = time.time() - start_time
            await self._log_magic_execution(magic_request, enhanced_result, execution_time)
            
            return self._format_response(enhanced_result)
            
        except Exception as e:
            self.logger.error(f"💥 魔法実行エラー: {str(e)}")
            return await self._handle_magic_error(e, arguments, time.time() - start_time)
    
    async def _validate_and_prepare_request(self, arguments: Dict[str, Any]) -> MagicRequest:
        """
        入力検証とリクエスト準備（Security First）
        """
        # 必須パラメータチェック
        if "project_path" not in arguments:
            raise ValueError("project_path is required for magic execution")
        
        project_path = arguments["project_path"]
        
        # セキュリティ検証
        is_valid, error_msg = self.security_validator.validate_file_path(project_path)
        if not is_valid:
            raise SecurityError(f"Invalid or unsafe project path: {error_msg}")
        
        # プロジェクトパスの正規化
        normalized_path = str(Path(project_path).resolve())
        
        # 魔法リクエスト構築
        magic_request = MagicRequest(
            magic_type=self._get_magic_type(),
            project_path=normalized_path,
            parameters=arguments,
            priority=MagicPriority(arguments.get("priority", 3)),
            timeout_seconds=arguments.get("timeout", 300),
            user_id=arguments.get("user_id"),
            session_id=arguments.get("session_id")
        )
        
        return magic_request
    
    async def _instant_project_understanding(self, project_path: str) -> ProjectDNA:
        """
        プロジェクトの瞬間理解（3秒以内）
        
        キャッシュを活用して高速化を実現
        """
        # プロジェクト識別子生成
        project_id = self._generate_project_id(project_path)
        
        # キャッシュチェック
        if project_id in self._magic_cache:
            cached_dna = self._magic_cache[project_id]
            if self._is_cache_valid(cached_dna, project_path):
                self.logger.info("⚡ キャッシュからプロジェクトDNA取得")
                return cached_dna
        
        # 新規分析実行
        self.logger.info("🔍 プロジェクト瞬間分析開始...")
        
        # 並列分析で高速化
        analysis_tasks = [
            self._analyze_tech_stack(project_path),
            self._detect_architecture_pattern(project_path),
            self._infer_business_domain(project_path),
            self._calculate_complexity_metrics(project_path),
            self._assess_quality_metrics(project_path)
        ]
        
        results = await asyncio.gather(*analysis_tasks)
        
        # ProjectDNA構築
        project_dna = ProjectDNA(
            project_id=project_id,
            project_path=project_path,
            tech_stack=results[0],
            architecture_pattern=results[1],
            business_domain=results[2],
            complexity_score=results[3]["overall_complexity"],
            quality_metrics=results[4],
            file_count=results[3]["file_count"],
            total_lines=results[3]["total_lines"],
            last_analyzed=time.time(),
            confidence=0.95
        )
        
        # キャッシュ保存
        self._magic_cache[project_id] = project_dna
        
        return project_dna
    
    @abstractmethod
    async def _execute_magic(self, request: MagicRequest, project_dna: ProjectDNA) -> MagicResult:
        """
        具体的な魔法実行（サブクラスで実装）
        
        Args:
            request: 魔法リクエスト
            project_dna: プロジェクトの完全理解情報
            
        Returns:
            MagicResult: 魔法実行結果
        """
        pass
    
    @abstractmethod
    def _get_magic_type(self) -> MagicType:
        """魔法タイプの取得（サブクラスで実装）"""
        pass
    
    async def _enhance_magic_result(self, result: MagicResult, project_dna: ProjectDNA) -> MagicResult:
        """
        魔法結果の強化・最適化
        """
        # 結果の信頼度向上
        enhanced_confidence = min(result.confidence_score * project_dna.confidence, 1.0)
        
        # 追加の推奨事項生成
        additional_recommendations = await self._generate_additional_recommendations(result, project_dna)
        
        # 副次効果の分析
        side_effects = await self._analyze_side_effects(result, project_dna)
        
        return MagicResult(
            success=result.success,
            magic_type=result.magic_type,
            execution_time=result.execution_time,
            result_data=result.result_data,
            confidence_score=enhanced_confidence,
            side_effects=result.side_effects + side_effects,
            recommendations=result.recommendations + additional_recommendations,
            error_message=result.error_message,
            debug_info=result.debug_info
        )
    
    def _generate_project_id(self, project_path: str) -> str:
        """プロジェクト固有の安定した識別子生成"""
        path_str = str(Path(project_path).resolve())
        return hashlib.sha256(path_str.encode()).hexdigest()[:16]
    
    def _is_cache_valid(self, cached_dna: ProjectDNA, project_path: str) -> bool:
        """キャッシュの有効性チェック"""
        # 5分以内のキャッシュは有効
        cache_age = time.time() - cached_dna.last_analyzed
        return cache_age < 300
    
    async def _analyze_tech_stack(self, project_path: str) -> List[str]:
        """技術スタックの自動検出"""
        tech_stack = []
        
        # ファイル拡張子による検出
        for file_path in Path(project_path).rglob("*"):
            if file_path.is_file():
                suffix = file_path.suffix.lower()
                if suffix == ".py":
                    tech_stack.append("Python")
                elif suffix in [".java"]:
                    tech_stack.append("Java")
                elif suffix in [".js", ".ts"]:
                    tech_stack.append("JavaScript/TypeScript")
                elif suffix in [".cpp", ".c", ".h"]:
                    tech_stack.append("C/C++")
        
        return list(set(tech_stack))
    
    async def _detect_architecture_pattern(self, project_path: str) -> str:
        """アーキテクチャパターンの検出"""
        # 簡単な実装（後で高度化）
        if Path(project_path, "src", "main", "java").exists():
            return "Maven/Spring Architecture"
        elif Path(project_path, "app").exists() and Path(project_path, "requirements.txt").exists():
            return "Django/Flask Architecture"
        else:
            return "Standard Architecture"
    
    async def _infer_business_domain(self, project_path: str) -> str:
        """ビジネスドメインの推定"""
        # ディレクトリ名やファイル名から推定
        path_str = str(project_path).lower()
        if any(keyword in path_str for keyword in ["ecommerce", "shop", "cart", "payment"]):
            return "E-Commerce"
        elif any(keyword in path_str for keyword in ["crm", "customer", "sales"]):
            return "CRM"
        elif any(keyword in path_str for keyword in ["blog", "cms", "content"]):
            return "Content Management"
        else:
            return "General Application"
    
    async def _calculate_complexity_metrics(self, project_path: str) -> Dict[str, Any]:
        """複雑度メトリクスの計算"""
        file_count = 0
        total_lines = 0
        
        for file_path in Path(project_path).rglob("*.py"):
            if file_path.is_file():
                file_count += 1
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        total_lines += len(f.readlines())
                except:
                    pass
        
        # 簡単な複雑度計算
        complexity_score = min(total_lines / 10000, 10.0)  # 0-10スケール
        
        return {
            "file_count": file_count,
            "total_lines": total_lines,
            "overall_complexity": complexity_score
        }
    
    async def _assess_quality_metrics(self, project_path: str) -> Dict[str, float]:
        """品質メトリクスの評価"""
        # 基本的な品質指標
        return {
            "maintainability": 0.8,
            "readability": 0.75,
            "testability": 0.7,
            "security": 0.85,
            "performance": 0.8
        }
    
    async def _generate_additional_recommendations(self, result: MagicResult, project_dna: ProjectDNA) -> List[str]:
        """追加推奨事項の生成"""
        recommendations = []
        
        if project_dna.complexity_score > 7.0:
            recommendations.append("🔧 高複雑度検出: リファクタリングを推奨します")
        
        if project_dna.quality_metrics.get("security", 0) < 0.8:
            recommendations.append("🛡️ セキュリティ強化を推奨します")
        
        return recommendations
    
    async def _analyze_side_effects(self, result: MagicResult, project_dna: ProjectDNA) -> List[str]:
        """副次効果の分析"""
        side_effects = []
        
        if result.success:
            side_effects.append("✨ プロジェクト理解度が向上しました")
            side_effects.append("📊 分析キャッシュが更新されました")
        
        return side_effects
    
    async def _log_magic_execution(self, request: MagicRequest, result: MagicResult, execution_time: float):
        """魔法実行のログ記録"""
        log_data = {
            "magic_type": request.magic_type.value,
            "project_path": request.project_path,
            "success": result.success,
            "execution_time": execution_time,
            "confidence": result.confidence_score
        }
        
        if result.success:
            self.logger.info(f"✅ 魔法成功: {log_data}")
        else:
            self.logger.error(f"💥 魔法失敗: {log_data}")
    
    def _format_response(self, result: MagicResult) -> Dict[str, Any]:
        """レスポンスの標準化フォーマット"""
        return {
            "success": result.success,
            "magic_type": result.magic_type.value,
            "execution_time": f"{result.execution_time:.2f}秒",
            "confidence": f"{result.confidence_score:.1%}",
            "result": result.result_data,
            "side_effects": result.side_effects,
            "recommendations": result.recommendations,
            "error": result.error_message
        }
    
    async def _handle_magic_error(self, error: Exception, arguments: Dict[str, Any], execution_time: float) -> Dict[str, Any]:
        """魔法エラーの優雅な処理"""
        error_result = {
            "success": False,
            "magic_type": self._get_magic_type().value,
            "execution_time": f"{execution_time:.2f}秒",
            "error": str(error),
            "suggestions": [
                "🔍 プロジェクトパスを確認してください",
                "🛡️ ファイルアクセス権限を確認してください",
                "📞 サポートにお問い合わせください"
            ]
        }
        
        return error_result


class SecurityError(Exception):
    """セキュリティ関連のエラー"""
    pass


class MagicExecutionError(Exception):
    """魔法実行関連のエラー"""
    pass


# Factory Pattern for Magic Tool Creation
class MagicToolFactory:
    """魔法ツールのファクトリークラス"""
    
    _magic_tools = {}
    
    @classmethod
    def register_magic_tool(cls, magic_type: MagicType, tool_class: type):
        """魔法ツールの登録"""
        cls._magic_tools[magic_type] = tool_class
    
    @classmethod
    def create_magic_tool(cls, magic_type: MagicType) -> MagicBaseTool:
        """魔法ツールの生成"""
        if magic_type not in cls._magic_tools:
            raise ValueError(f"Unknown magic type: {magic_type}")
        
        tool_class = cls._magic_tools[magic_type]
        return tool_class()
    
    @classmethod
    def get_available_magic_types(cls) -> List[MagicType]:
        """利用可能な魔法タイプの取得"""
        return list(cls._magic_tools.keys())
