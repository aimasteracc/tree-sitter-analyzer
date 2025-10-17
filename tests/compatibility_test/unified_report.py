#!/usr/bin/env python3
"""
統合レポート生成スクリプト

このスクリプトは、MCPとCLIの両方のテスト結果と比較結果を統合し、
包括的な互換性レポートを生成します。

機能:
- MCPとCLIの結果を統合
- 機能対応関係に基づく相互比較
- 包括的なHTMLレポート生成
- エグゼクティブサマリー生成
- 推奨事項の提示
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UnifiedReportGenerator:
    """統合レポート生成クラス"""
    
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.result_dir = self.test_dir / "result"
        
        # MCPとCLIの機能対応関係
        self.feature_mapping = {
            "check_code_scale": ["CLI-001-summary", "CLI-003-advanced"],
            "analyze_code_structure": ["CLI-002-structure", "CLI-004-table-full", "CLI-005-table-compact", "CLI-006-table-html", "CLI-007-table-json"],
            "extract_code_section": ["CLI-008-partial-read", "CLI-009-partial-read-column"],
            "query_code": ["CLI-010-query-methods", "CLI-011-query-classes", "CLI-012-query-fields"],
            "list_files": [],  # CLIでは直接対応なし
            "search_content": [],  # CLIでは直接対応なし
            "find_and_grep": [],  # CLIでは直接対応なし
            "set_project_path": []  # CLIでは直接対応なし
        }
    
    def load_mcp_results(self, version: str) -> Optional[Dict[str, Any]]:
        """MCPテスト結果を読み込み"""
        mcp_dir = self.result_dir / "mcp" / f"v-{version}"
        summary_file = mcp_dir / "mcp_test_summary.json"
        
        if not summary_file.exists():
            logger.warning(f"MCPテスト結果が見つかりません: {summary_file}")
            return None
        
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"MCPテスト結果の読み込みエラー: {e}")
            return None
    
    def load_cli_results(self, version: str) -> Optional[Dict[str, Any]]:
        """CLIテスト結果を読み込み"""
        cli_dir = self.result_dir / "cli" / f"v-{version}"
        summary_file = cli_dir / "cli_test_summary.json"
        
        if not summary_file.exists():
            logger.warning(f"CLIテスト結果が見つかりません: {summary_file}")
            return None
        
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"CLIテスト結果の読み込みエラー: {e}")
            return None
    
    def load_comparison_results(self, version1: str, version2: str) -> Tuple[Optional[Dict], Optional[Dict]]:
        """比較結果を読み込み"""
        comparison_dir = self.test_dir / "comparison"
        
        # MCP比較結果
        mcp_comparison_file = comparison_dir / f"mcp_{version1}_vs_{version2}" / "mcp_comparison.json"
        mcp_comparison = None
        if mcp_comparison_file.exists():
            try:
                with open(mcp_comparison_file, 'r', encoding='utf-8') as f:
                    mcp_comparison = json.load(f)
            except Exception as e:
                logger.error(f"MCP比較結果の読み込みエラー: {e}")
        
        # CLI比較結果
        cli_comparison_file = comparison_dir / f"cli_{version1}_vs_{version2}" / "cli_comparison.json"
        cli_comparison = None
        if cli_comparison_file.exists():
            try:
                with open(cli_comparison_file, 'r', encoding='utf-8') as f:
                    cli_comparison = json.load(f)
            except Exception as e:
                logger.error(f"CLI比較結果の読み込みエラー: {e}")
        
        return mcp_comparison, cli_comparison
    
    def analyze_feature_coverage(self, mcp_results: Dict, cli_results: Dict) -> Dict[str, Any]:
        """機能カバレッジを分析"""
        coverage_analysis = {
            "mcp_only_features": [],
            "cli_only_features": [],
            "shared_features": [],
            "feature_compatibility": {}
        }
        
        # MCPテスト結果から機能を抽出
        mcp_tools = set()
        if mcp_results:
            for result in mcp_results.get("results", []):
                if "tool" in result:
                    mcp_tools.add(result["tool"])
        
        # CLIテスト結果から機能を抽出
        cli_commands = set()
        if cli_results:
            for result in cli_results.get("results", []):
                test_id = result.get("test_id", "")
                if test_id.startswith("CLI-"):
                    cli_commands.add(test_id)
        
        # 機能対応関係を分析
        for mcp_tool, cli_equivalents in self.feature_mapping.items():
            if mcp_tool in mcp_tools:
                if any(cli_cmd in cli_commands for cli_cmd in cli_equivalents):
                    coverage_analysis["shared_features"].append({
                        "mcp_tool": mcp_tool,
                        "cli_commands": [cmd for cmd in cli_equivalents if cmd in cli_commands]
                    })
                else:
                    coverage_analysis["mcp_only_features"].append(mcp_tool)
        
        # CLI専用機能を特定
        mapped_cli_commands = set()
        for cli_list in self.feature_mapping.values():
            mapped_cli_commands.update(cli_list)
        
        for cli_cmd in cli_commands:
            if cli_cmd not in mapped_cli_commands:
                coverage_analysis["cli_only_features"].append(cli_cmd)
        
        return coverage_analysis
    
    def calculate_overall_compatibility(self, mcp_comparison: Optional[Dict], cli_comparison: Optional[Dict]) -> Dict[str, Any]:
        """全体的な互換性を計算"""
        overall_stats = {
            "mcp_compatibility_rate": 0.0,
            "cli_compatibility_rate": 0.0,
            "weighted_compatibility_rate": 0.0,
            "overall_level": "unknown"
        }
        
        if mcp_comparison:
            mcp_analysis = mcp_comparison.get("compatibility_analysis", {})
            overall_stats["mcp_compatibility_rate"] = mcp_analysis.get("compatibility_rate", 0.0)
        
        if cli_comparison:
            cli_analysis = cli_comparison.get("compatibility_analysis", {})
            overall_stats["cli_compatibility_rate"] = cli_analysis.get("compatibility_rate", 0.0)
        
        # 重み付き互換性率を計算（MCPを重視）
        mcp_weight = 0.7
        cli_weight = 0.3
        
        if mcp_comparison and cli_comparison:
            overall_stats["weighted_compatibility_rate"] = (
                overall_stats["mcp_compatibility_rate"] * mcp_weight +
                overall_stats["cli_compatibility_rate"] * cli_weight
            )
        elif mcp_comparison:
            overall_stats["weighted_compatibility_rate"] = overall_stats["mcp_compatibility_rate"]
        elif cli_comparison:
            overall_stats["weighted_compatibility_rate"] = overall_stats["cli_compatibility_rate"]
        
        # 全体レベルを判定
        rate = overall_stats["weighted_compatibility_rate"]
        if rate >= 0.95:
            overall_stats["overall_level"] = "excellent"
        elif rate >= 0.90:
            overall_stats["overall_level"] = "good"
        elif rate >= 0.80:
            overall_stats["overall_level"] = "acceptable"
        elif rate >= 0.70:
            overall_stats["overall_level"] = "poor"
        else:
            overall_stats["overall_level"] = "critical"
        
        return overall_stats
    
    def generate_recommendations(self, mcp_comparison: Optional[Dict], cli_comparison: Optional[Dict], overall_stats: Dict) -> List[str]:
        """推奨事項を生成"""
        recommendations = []
        
        overall_rate = overall_stats["weighted_compatibility_rate"]
        
        if overall_rate >= 0.95:
            recommendations.append("✅ 高い互換性が確認されました。安全にアップグレードできます。")
        elif overall_rate >= 0.90:
            recommendations.append("✅ 良好な互換性です。軽微な調整でアップグレード可能です。")
        elif overall_rate >= 0.80:
            recommendations.append("⚠️ 一部非互換性があります。詳細な検証を行ってからアップグレードしてください。")
        elif overall_rate >= 0.70:
            recommendations.append("⚠️ 重要な非互換性があります。修正作業が必要です。")
        else:
            recommendations.append("❌ 重大な非互換性があります。アップグレード前に大幅な修正が必要です。")
        
        # MCP固有の推奨事項
        if mcp_comparison:
            mcp_rate = overall_stats["mcp_compatibility_rate"]
            if mcp_rate < 0.9:
                recommendations.append("🔧 MCPツールに非互換性があります。APIの変更を確認してください。")
        
        # CLI固有の推奨事項
        if cli_comparison:
            cli_rate = overall_stats["cli_compatibility_rate"]
            if cli_rate < 0.8:
                recommendations.append("🔧 CLIコマンドに非互換性があります。コマンドライン引数の変更を確認してください。")
        
        # 機能別推奨事項
        if mcp_comparison:
            mcp_analysis = mcp_comparison.get("compatibility_analysis", {})
            counts = mcp_analysis.get("compatibility_counts", {})
            
            if counts.get("regression", 0) > 0:
                recommendations.append("🚨 リグレッションが検出されました。以前動作していた機能が失敗しています。")
            
            if counts.get("improvement", 0) > 0:
                recommendations.append("✨ 改善が検出されました。以前失敗していた機能が成功するようになりました。")
        
        return recommendations
    
    def generate_unified_report(self, version1: str, version2: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
        """統合レポートを生成"""
        logger.info(f"統合レポート生成開始: {version1} vs {version2}")
        
        # データを読み込み
        mcp_results1 = self.load_mcp_results(version1)
        mcp_results2 = self.load_mcp_results(version2)
        cli_results1 = self.load_cli_results(version1)
        cli_results2 = self.load_cli_results(version2)
        
        mcp_comparison, cli_comparison = self.load_comparison_results(version1, version2)
        
        # 機能カバレッジを分析
        coverage_analysis = {}
        if mcp_results1 and cli_results1:
            coverage_analysis = self.analyze_feature_coverage(mcp_results1, cli_results1)
        
        # 全体的な互換性を計算
        overall_stats = self.calculate_overall_compatibility(mcp_comparison, cli_comparison)
        
        # 推奨事項を生成
        recommendations = self.generate_recommendations(mcp_comparison, cli_comparison, overall_stats)
        
        # 統合レポートを構築
        unified_report = {
            "report_timestamp": datetime.now().isoformat(),
            "versions": {
                "version1": version1,
                "version2": version2
            },
            "test_results": {
                "mcp": {
                    "version1": mcp_results1,
                    "version2": mcp_results2,
                    "comparison": mcp_comparison
                },
                "cli": {
                    "version1": cli_results1,
                    "version2": cli_results2,
                    "comparison": cli_comparison
                }
            },
            "coverage_analysis": coverage_analysis,
            "overall_compatibility": overall_stats,
            "recommendations": recommendations,
            "summary": self.generate_executive_summary(overall_stats, mcp_comparison, cli_comparison)
        }
        
        # 出力ディレクトリを設定
        if output_dir is None:
            output_dir = self.test_dir / "unified_report" / f"{version1}_vs_{version2}"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # レポートを保存
        report_file = output_dir / "unified_compatibility_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(unified_report, f, indent=2, ensure_ascii=False)
        
        # HTMLレポートを生成
        html_file = output_dir / "unified_compatibility_report.html"
        self.generate_html_unified_report(unified_report, str(html_file))
        
        logger.info(f"統合レポート生成完了: {report_file}")
        return unified_report
    
    def generate_executive_summary(self, overall_stats: Dict, mcp_comparison: Optional[Dict], cli_comparison: Optional[Dict]) -> str:
        """エグゼクティブサマリーを生成"""
        summary_parts = []
        
        # 全体的な互換性
        rate = overall_stats["weighted_compatibility_rate"]
        level = overall_stats["overall_level"]
        summary_parts.append(f"全体的な互換性率: {rate:.1%} ({level})")
        
        # MCP互換性
        if mcp_comparison:
            mcp_rate = overall_stats["mcp_compatibility_rate"]
            summary_parts.append(f"MCP互換性: {mcp_rate:.1%}")
        
        # CLI互換性
        if cli_comparison:
            cli_rate = overall_stats["cli_compatibility_rate"]
            summary_parts.append(f"CLI互換性: {cli_rate:.1%}")
        
        return "、".join(summary_parts)
    
    def generate_html_unified_report(self, report: Dict[str, Any], output_file: str):
        """統合HTMLレポートを生成"""
        overall_stats = report["overall_compatibility"]
        level = overall_stats["overall_level"]
        
        html_content = f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>統合互換性レポート</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; text-align: center; }}
        .summary {{ background-color: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
        .stat-card {{ background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .compatibility-excellent {{ border-left: 5px solid #28a745; }}
        .compatibility-good {{ border-left: 5px solid #17a2b8; }}
        .compatibility-acceptable {{ border-left: 5px solid #ffc107; }}
        .compatibility-poor {{ border-left: 5px solid #fd7e14; }}
        .compatibility-critical {{ border-left: 5px solid #dc3545; }}
        .recommendations {{ background-color: #e9ecef; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .recommendation {{ margin: 10px 0; padding: 10px; background-color: white; border-radius: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        .section {{ margin: 30px 0; }}
        .section h2 {{ color: #495057; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }}
        .progress-bar {{ width: 100%; height: 20px; background-color: #e9ecef; border-radius: 10px; overflow: hidden; }}
        .progress-fill {{ height: 100%; transition: width 0.3s ease; }}
        .progress-excellent {{ background-color: #28a745; }}
        .progress-good {{ background-color: #17a2b8; }}
        .progress-acceptable {{ background-color: #ffc107; }}
        .progress-poor {{ background-color: #fd7e14; }}
        .progress-critical {{ background-color: #dc3545; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔄 統合互換性レポート</h1>
        <p>バージョン比較: {report['versions']['version1']} → {report['versions']['version2']}</p>
        <p>生成日時: {report['report_timestamp']}</p>
    </div>
    
    <div class="summary compatibility-{level}">
        <h2>📊 エグゼクティブサマリー</h2>
        <p><strong>{report['summary']}</strong></p>
        <div class="progress-bar">
            <div class="progress-fill progress-{level}" style="width: {overall_stats['weighted_compatibility_rate']:.1%}"></div>
        </div>
        <p>全体互換性レベル: <strong>{level}</strong> ({overall_stats['weighted_compatibility_rate']:.1%})</p>
    </div>
    
    <div class="stats-grid">
        <div class="stat-card">
            <h3>🔧 MCP互換性</h3>
            <p class="h2">{overall_stats['mcp_compatibility_rate']:.1%}</p>
            <p>Model Context Protocol</p>
        </div>
        <div class="stat-card">
            <h3>💻 CLI互換性</h3>
            <p class="h2">{overall_stats['cli_compatibility_rate']:.1%}</p>
            <p>Command Line Interface</p>
        </div>
        <div class="stat-card">
            <h3>⚖️ 重み付き互換性</h3>
            <p class="h2">{overall_stats['weighted_compatibility_rate']:.1%}</p>
            <p>MCP重視の総合評価</p>
        </div>
    </div>
    
    <div class="recommendations">
        <h2>💡 推奨事項</h2>
"""
        
        for recommendation in report["recommendations"]:
            html_content += f'<div class="recommendation">{recommendation}</div>\n'
        
        html_content += """
    </div>
    
    <div class="section">
        <h2>📋 詳細分析</h2>
"""
        
        # MCP詳細
        mcp_comparison = report["test_results"]["mcp"]["comparison"]
        if mcp_comparison:
            mcp_analysis = mcp_comparison.get("compatibility_analysis", {})
            html_content += f"""
        <h3>🔧 MCP詳細分析</h3>
        <table>
            <tr><th>項目</th><th>値</th></tr>
            <tr><td>総テスト数</td><td>{mcp_analysis.get('total_tests', 0)}</td></tr>
            <tr><td>互換テスト数</td><td>{mcp_analysis.get('compatible_tests', 0)}</td></tr>
            <tr><td>互換性率</td><td>{mcp_analysis.get('compatibility_rate', 0):.1%}</td></tr>
            <tr><td>互換性レベル</td><td>{mcp_analysis.get('compatibility_level', 'unknown')}</td></tr>
        </table>
"""
        
        # CLI詳細
        cli_comparison = report["test_results"]["cli"]["comparison"]
        if cli_comparison:
            cli_analysis = cli_comparison.get("compatibility_analysis", {})
            html_content += f"""
        <h3>💻 CLI詳細分析</h3>
        <table>
            <tr><th>項目</th><th>値</th></tr>
            <tr><td>総テスト数</td><td>{cli_analysis.get('total_tests', 0)}</td></tr>
            <tr><td>互換テスト数</td><td>{cli_analysis.get('compatible_tests', 0)}</td></tr>
            <tr><td>互換性率</td><td>{cli_analysis.get('compatibility_rate', 0):.1%}</td></tr>
            <tr><td>互換性レベル</td><td>{cli_analysis.get('compatibility_level', 'unknown')}</td></tr>
        </table>
"""
        
        # 機能カバレッジ
        coverage = report.get("coverage_analysis", {})
        if coverage:
            html_content += """
        <h3>🎯 機能カバレッジ分析</h3>
        <table>
            <tr><th>カテゴリ</th><th>機能数</th><th>詳細</th></tr>
"""
            
            shared_features = coverage.get("shared_features", [])
            mcp_only = coverage.get("mcp_only_features", [])
            cli_only = coverage.get("cli_only_features", [])
            
            html_content += f"""
            <tr><td>共通機能</td><td>{len(shared_features)}</td><td>MCPとCLI両方でサポート</td></tr>
            <tr><td>MCP専用機能</td><td>{len(mcp_only)}</td><td>MCPのみでサポート</td></tr>
            <tr><td>CLI専用機能</td><td>{len(cli_only)}</td><td>CLIのみでサポート</td></tr>
"""
            
            html_content += """
        </table>
"""
        
        html_content += """
    </div>
    
    <div class="section">
        <h2>🔗 関連リンク</h2>
        <ul>
            <li><a href="../mcp_comparison_report.html">詳細MCPレポート</a></li>
            <li><a href="../cli_comparison_report.html">詳細CLIレポート</a></li>
            <li><a href="unified_compatibility_report.json">JSON形式レポート</a></li>
        </ul>
    </div>
    
    <footer style="margin-top: 50px; padding: 20px; background-color: #f8f9fa; text-align: center; border-radius: 8px;">
        <p>このレポートは tree-sitter-analyzer 互換性テストシステムによって自動生成されました。</p>
    </footer>
</body>
</html>
"""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"統合HTMLレポートを生成しました: {output_file}")

def main():
    """メイン関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="統合レポート生成")
    parser.add_argument("version1", help="比較元バージョン")
    parser.add_argument("version2", help="比較先バージョン")
    parser.add_argument("--output", help="出力ディレクトリ")
    parser.add_argument("--verbose", action="store_true", help="詳細ログ出力")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    generator = UnifiedReportGenerator()
    
    try:
        report = generator.generate_unified_report(args.version1, args.version2, args.output)
        
        overall_rate = report['overall_compatibility']['weighted_compatibility_rate']
        logger.info(f"統合レポート生成完了: 全体互換性率 {overall_rate:.1%}")
        
        if overall_rate < 0.8:
            logger.warning("全体的な互換性率が低いです。詳細レポートを確認してください。")
        
    except Exception as e:
        logger.error(f"統合レポート生成エラー: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())