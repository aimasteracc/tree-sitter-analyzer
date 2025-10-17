#!/usr/bin/env python3
"""
テストケースローダー

外部JSON設定からテストケースを読み込み、パラメータ化されたテストケースを生成します。
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from colored_logger import get_logger

logger = get_logger(__name__)


class TestCaseTemplate:
    """テストケーステンプレートクラス"""
    
    def __init__(self, template_data: Dict[str, Any]):
        self.test_id = template_data["test_id"]
        self.name = template_data["name"]
        self.description = template_data["description"]
        self.template = template_data["template"]
        self.parameters = template_data.get("parameters", {})
        self.expected_success = template_data.get("expected_success", True)
        self.category = template_data.get("category", "default")
        self.timeout = template_data.get("timeout", 30)
        
    def generate_args(self) -> List[str]:
        """テンプレートからコマンド引数を生成"""
        try:
            # テンプレート文字列にパラメータを適用
            command_str = self.template.format(**self.parameters)
            
            # 空白で分割してリストに変換
            args = command_str.split()
            
            # 空の引数を除去
            args = [arg for arg in args if arg.strip()]
            
            return args
            
        except KeyError as e:
            logger.error(f"テンプレート {self.test_id} でパラメータが不足: {e}")
            raise
        except Exception as e:
            logger.error(f"テンプレート {self.test_id} の処理でエラー: {e}")
            raise
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "test_id": self.test_id,
            "name": self.name,
            "description": self.description,
            "args": self.generate_args(),
            "expected_success": self.expected_success,
            "category": self.category,
            "timeout": self.timeout
        }


class TestCaseLoader:
    """テストケースローダークラス"""
    
    def __init__(self, config_file: Union[str, Path]):
        self.config_file = Path(config_file)
        self.config_data: Dict[str, Any] = {}
        self.templates: List[TestCaseTemplate] = []
        self.error_templates: List[TestCaseTemplate] = []
        
        self._load_config()
        self._parse_templates()
    
    def _load_config(self) -> None:
        """設定ファイルを読み込み"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
            logger.info(f"設定ファイルを読み込みました: {self.config_file}")
        except FileNotFoundError:
            logger.error(f"設定ファイルが見つかりません: {self.config_file}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"設定ファイルのJSON解析エラー: {e}")
            raise
        except Exception as e:
            logger.error(f"設定ファイル読み込みエラー: {e}")
            raise
    
    def _parse_templates(self) -> None:
        """テンプレートを解析"""
        # 通常のテストケース
        cli_test_cases = self.config_data.get("cli_test_cases", [])
        for case_data in cli_test_cases:
            try:
                template = TestCaseTemplate(case_data)
                self.templates.append(template)
            except Exception as e:
                logger.warning(f"テストケース {case_data.get('test_id', 'unknown')} の解析に失敗: {e}")
        
        # エラーテストケース
        error_test_cases = self.config_data.get("error_test_cases", [])
        for case_data in error_test_cases:
            try:
                template = TestCaseTemplate(case_data)
                self.error_templates.append(template)
            except Exception as e:
                logger.warning(f"エラーテストケース {case_data.get('test_id', 'unknown')} の解析に失敗: {e}")
        
        logger.info(f"通常テストケース: {len(self.templates)}個")
        logger.info(f"エラーテストケース: {len(self.error_templates)}個")
    
    def get_all_test_cases(self) -> List[Dict[str, Any]]:
        """全テストケースを取得"""
        all_cases = []
        
        # 通常テストケース
        for template in self.templates:
            all_cases.append(template.to_dict())
        
        # エラーテストケース
        for template in self.error_templates:
            all_cases.append(template.to_dict())
        
        return all_cases
    
    def get_test_cases_by_category(self, category: str) -> List[Dict[str, Any]]:
        """カテゴリ別テストケースを取得"""
        cases = []
        
        for template in self.templates + self.error_templates:
            if template.category == category:
                cases.append(template.to_dict())
        
        return cases
    
    def get_test_cases_by_ids(self, test_ids: List[str]) -> List[Dict[str, Any]]:
        """ID指定でテストケースを取得"""
        cases = []
        
        for template in self.templates + self.error_templates:
            if template.test_id in test_ids:
                cases.append(template.to_dict())
        
        return cases
    
    def get_categories(self) -> Dict[str, Dict[str, Any]]:
        """カテゴリ情報を取得"""
        return self.config_data.get("test_categories", {})
    
    def get_global_settings(self) -> Dict[str, Any]:
        """グローバル設定を取得"""
        return self.config_data.get("global_settings", {})
    
    def validate_test_cases(self) -> bool:
        """テストケースの妥当性を検証"""
        valid = True
        
        # 重複IDチェック
        all_ids = []
        for template in self.templates + self.error_templates:
            if template.test_id in all_ids:
                logger.error(f"重複するテストID: {template.test_id}")
                valid = False
            all_ids.append(template.test_id)
        
        # テンプレート生成テスト
        for template in self.templates + self.error_templates:
            try:
                args = template.generate_args()
                if not args:
                    logger.warning(f"空の引数が生成されました: {template.test_id}")
            except Exception as e:
                logger.error(f"テンプレート生成エラー {template.test_id}: {e}")
                valid = False
        
        return valid
    
    def filter_test_cases(self, 
                         categories: Optional[List[str]] = None,
                         test_ids: Optional[List[str]] = None,
                         include_errors: bool = True) -> List[Dict[str, Any]]:
        """条件に基づいてテストケースをフィルタリング"""
        
        if test_ids:
            return self.get_test_cases_by_ids(test_ids)
        
        cases = []
        
        # 通常テストケース
        for template in self.templates:
            if categories is None or template.category in categories:
                cases.append(template.to_dict())
        
        # エラーテストケース
        if include_errors:
            for template in self.error_templates:
                if categories is None or template.category in categories:
                    cases.append(template.to_dict())
        
        return cases
    
    def get_test_summary(self) -> Dict[str, Any]:
        """テストケースサマリーを取得"""
        categories = {}
        
        # カテゴリ別集計
        for template in self.templates + self.error_templates:
            if template.category not in categories:
                categories[template.category] = {
                    "count": 0,
                    "normal": 0,
                    "error": 0
                }
            
            categories[template.category]["count"] += 1
            
            if template in self.templates:
                categories[template.category]["normal"] += 1
            else:
                categories[template.category]["error"] += 1
        
        return {
            "total_cases": len(self.templates) + len(self.error_templates),
            "normal_cases": len(self.templates),
            "error_cases": len(self.error_templates),
            "categories": categories,
            "config_file": str(self.config_file)
        }


def load_test_cases(config_file: Union[str, Path], 
                   categories: Optional[List[str]] = None,
                   test_ids: Optional[List[str]] = None,
                   include_errors: bool = True) -> List[Dict[str, Any]]:
    """テストケースを読み込む便利関数"""
    loader = TestCaseLoader(config_file)
    
    if not loader.validate_test_cases():
        logger.warning("テストケースの妥当性検証で問題が見つかりました")
    
    return loader.filter_test_cases(categories, test_ids, include_errors)


def demo_test_case_loader():
    """テストケースローダーのデモ"""
    logger = get_logger("demo")
    
    logger.section_header("テストケースローダーのデモ")
    
    try:
        # テストケースファイルのパス
        config_file = Path(__file__).parent / "cli_test_cases.json"
        
        # ローダーを作成
        loader = TestCaseLoader(config_file)
        
        # サマリー表示
        summary = loader.get_test_summary()
        logger.info(f"総テストケース数: {summary['total_cases']}")
        logger.info(f"通常テストケース: {summary['normal_cases']}")
        logger.info(f"エラーテストケース: {summary['error_cases']}")
        
        # カテゴリ別表示
        logger.info("\nカテゴリ別テストケース:")
        for category, info in summary['categories'].items():
            logger.info(f"  {category}: {info['count']}個 (通常:{info['normal']}, エラー:{info['error']})")
        
        # 基本カテゴリのテストケースを取得
        basic_cases = loader.get_test_cases_by_category("basic")
        logger.info(f"\n基本カテゴリのテストケース: {len(basic_cases)}個")
        
        for case in basic_cases[:3]:  # 最初の3個を表示
            logger.info(f"  {case['test_id']}: {case['description']}")
            logger.info(f"    引数: {' '.join(case['args'])}")
        
        # 妥当性検証
        if loader.validate_test_cases():
            logger.success("テストケースの妥当性検証: 成功")
        else:
            logger.error("テストケースの妥当性検証: 失敗")
        
    except Exception as e:
        logger.error(f"デモ実行エラー: {e}")


if __name__ == "__main__":
    demo_test_case_loader()