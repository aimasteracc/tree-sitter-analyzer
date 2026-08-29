#!/usr/bin/env python3
"""
キャッシュ状態レポート生成ユーティリティ

キャッシュの状態を詳細に分析し、テストレポートに含める情報を生成します。
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class CacheReporter:
    """
    キャッシュ状態のレポート生成クラス
    """

    def __init__(self, project_root: str | None = None):
        """
        初期化

        Args:
            project_root: プロジェクトルートパス
        """
        self.project_root = project_root

    def generate_cache_report(self, cache_stats: dict[str, Any]) -> dict[str, Any]:
        """
        キャッシュ統計からレポートを生成

        Args:
            cache_stats: キャッシュ統計情報

        Returns:
            レポート情報
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": self._generate_summary(cache_stats),
            "details": self._generate_details(cache_stats),
            "recommendations": self._generate_recommendations(cache_stats),
            "cache_impact_analysis": self._analyze_cache_impact(cache_stats),
        }

        return report

    def _generate_summary(self, cache_stats: dict[str, Any]) -> dict[str, Any]:
        """サマリー情報を生成"""
        summary = {
            "total_cache_systems": 0,
            "active_caches": 0,
            "total_cached_items": 0,
            "cache_hit_rates": {},
            "potential_issues": [],
        }

        # Analysis Engine キャッシュ
        if "analysis_engine" in cache_stats and not cache_stats["analysis_engine"].get(
            "error"
        ):
            ae_stats = cache_stats["analysis_engine"]
            summary["total_cache_systems"] += 1

            if (
                ae_stats.get("l1_size", 0) > 0
                or ae_stats.get("l2_size", 0) > 0
                or ae_stats.get("l3_size", 0) > 0
            ):
                summary["active_caches"] += 1
                summary["total_cached_items"] += (
                    ae_stats.get("l1_size", 0)
                    + ae_stats.get("l2_size", 0)
                    + ae_stats.get("l3_size", 0)
                )

            if "hit_rate" in ae_stats:
                summary["cache_hit_rates"]["analysis_engine"] = ae_stats["hit_rate"]

        # Search Content キャッシュは廃止済み (SearchContentTool 削除)

        # 潜在的な問題を特定
        if summary["active_caches"] > 0:
            summary["potential_issues"].append(
                "アクティブなキャッシュが検出されました - テスト結果に影響する可能性があります"
            )

        for cache_name, hit_rate in summary["cache_hit_rates"].items():
            if hit_rate > 50:  # 50%以上のヒット率
                summary["potential_issues"].append(
                    f"{cache_name}のヒット率が高い ({hit_rate}%) - バージョン間でキャッシュが共有されている可能性があります"
                )

        return summary

    def _generate_details(self, cache_stats: dict[str, Any]) -> dict[str, Any]:
        """詳細情報を生成"""
        details = {
            "analysis_engine_cache": {},
            # search_content_cache は廃止済み (SearchContentTool 削除)
            "cache_configurations": {},
        }

        # Analysis Engine の詳細
        if "analysis_engine" in cache_stats:
            ae_stats = cache_stats["analysis_engine"]
            if not ae_stats.get("error"):
                details["analysis_engine_cache"] = {
                    "type": "3層階層キャッシュ (L1/L2/L3)",
                    "l1_size": ae_stats.get("l1_size", 0),
                    "l2_size": ae_stats.get("l2_size", 0),
                    "l3_size": ae_stats.get("l3_size", 0),
                    "total_requests": ae_stats.get("total_requests", 0),
                    "hits": ae_stats.get("hits", 0),
                    "misses": ae_stats.get("misses", 0),
                    "hit_rate": ae_stats.get("hit_rate", 0),
                    "storage": "メモリ内 (プロセス終了時に消失)",
                }
            else:
                details["analysis_engine_cache"]["error"] = ae_stats["error"]

        # search_content キャッシュは廃止済み (SearchContentTool 削除)

        # キャッシュ設定情報
        details["cache_configurations"] = {
            "analysis_engine": {
                "default_ttl": "3600秒 (1時間)",
                "l1_default_size": 100,
                "l2_default_size": 1000,
                "l3_default_size": 10000,
            },
        }

        return details

    def _generate_recommendations(self, cache_stats: dict[str, Any]) -> list[str]:
        """推奨事項を生成"""
        recommendations = []

        # アクティブキャッシュの確認
        active_caches = 0
        if "analysis_engine" in cache_stats and not cache_stats["analysis_engine"].get(
            "error"
        ):
            ae_stats = cache_stats["analysis_engine"]
            if (
                ae_stats.get("l1_size", 0) > 0
                or ae_stats.get("l2_size", 0) > 0
                or ae_stats.get("l3_size", 0) > 0
            ):
                active_caches += 1

        # search_content キャッシュは廃止済み

        if active_caches > 0:
            recommendations.append(
                "🚨 アクティブなキャッシュが検出されました。テスト前にキャッシュをクリアすることを強く推奨します。"
            )
            recommendations.append(
                "💡 --no-cache-clear オプションを使用せず、デフォルトのキャッシュクリア機能を有効にしてください。"
            )

        # ヒット率の確認 (search_content は廃止済み)
        for cache_name in ["analysis_engine"]:
            if cache_name in cache_stats and not cache_stats[cache_name].get("error"):
                stats = cache_stats[cache_name]
                hit_rate_key = (
                    "hit_rate"
                    if cache_name == "analysis_engine"
                    else "hit_rate_percent"
                )
                hit_rate = stats.get(hit_rate_key, 0)

                if hit_rate > 30:  # 30%以上のヒット率
                    recommendations.append(
                        f"⚠️ {cache_name}のキャッシュヒット率が高い ({hit_rate}%) - バージョン間でキャッシュが共有されている可能性があります。"
                    )

        # 一般的な推奨事項
        recommendations.extend(
            [
                "✅ 各バージョンのテスト前後でキャッシュをクリアし、クリーンな状態でテストを実行してください。",
                "📊 テスト結果に 'cache_hit': true が表示される場合は、キャッシュの影響を受けている証拠です。",
                "🔄 同じテストを複数回実行して結果の一貫性を確認してください。",
                "📝 キャッシュ状態をテストレポートに記録し、結果の解釈に活用してください。",
            ]
        )

        return recommendations

    def _analyze_cache_impact(self, cache_stats: dict[str, Any]) -> dict[str, Any]:
        """キャッシュがテストに与える影響を分析"""
        impact_analysis = {
            "risk_level": "low",  # low, medium, high
            "risk_factors": [],
            "mitigation_status": "unknown",
            "confidence_score": 0.0,  # 0.0-1.0
        }

        risk_score = 0.0
        max_risk_score = 0.0

        # Analysis Engine キャッシュの影響
        if "analysis_engine" in cache_stats and not cache_stats["analysis_engine"].get(
            "error"
        ):
            ae_stats = cache_stats["analysis_engine"]
            total_items = (
                ae_stats.get("l1_size", 0)
                + ae_stats.get("l2_size", 0)
                + ae_stats.get("l3_size", 0)
            )
            hit_rate = ae_stats.get("hit_rate", 0)

            max_risk_score += 0.4
            if total_items > 0:
                risk_score += 0.2
                impact_analysis["risk_factors"].append(
                    f"Analysis Engineに{total_items}個のキャッシュエントリが存在"
                )

            if hit_rate > 0.3:  # 30%以上
                risk_score += 0.2
                impact_analysis["risk_factors"].append(
                    f"Analysis Engineのヒット率が高い ({hit_rate:.1%})"
                )

        # Search Content キャッシュは廃止済み (SearchContentTool 削除)

        # リスクレベルの決定
        if max_risk_score > 0:
            risk_ratio = risk_score / max_risk_score
            if risk_ratio > 0.7:
                impact_analysis["risk_level"] = "high"
            elif risk_ratio > 0.3:
                impact_analysis["risk_level"] = "medium"
            else:
                impact_analysis["risk_level"] = "low"

            impact_analysis["confidence_score"] = 1.0 - risk_ratio
        else:
            impact_analysis["confidence_score"] = 1.0

        # 緩和策の状態
        if not impact_analysis["risk_factors"]:
            impact_analysis["mitigation_status"] = "not_needed"
        else:
            impact_analysis["mitigation_status"] = "required"

        return impact_analysis

    def format_report_for_markdown(self, report: dict[str, Any]) -> str:
        """レポートをMarkdown形式でフォーマット"""
        md_lines = [
            "## 🧹 キャッシュ状態レポート",
            "",
            f"**生成日時**: {report['timestamp']}",
            "",
            "### 📊 サマリー",
            "",
            f"- **キャッシュシステム数**: {report['summary']['total_cache_systems']}",
            f"- **アクティブキャッシュ数**: {report['summary']['active_caches']}",
            f"- **総キャッシュアイテム数**: {report['summary']['total_cached_items']}",
            "",
        ]

        # ヒット率
        if report["summary"]["cache_hit_rates"]:
            md_lines.append("**キャッシュヒット率**:")
            for cache_name, hit_rate in report["summary"]["cache_hit_rates"].items():
                md_lines.append(f"- {cache_name}: {hit_rate:.1f}%")
            md_lines.append("")

        # 潜在的な問題
        if report["summary"]["potential_issues"]:
            md_lines.extend(["### ⚠️ 潜在的な問題", ""])
            for issue in report["summary"]["potential_issues"]:
                md_lines.append(f"- {issue}")
            md_lines.append("")

        # 影響分析
        impact = report["cache_impact_analysis"]
        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}
        md_lines.extend(
            [
                "### 🎯 キャッシュ影響分析",
                "",
                f"- **リスクレベル**: {risk_emoji.get(impact['risk_level'], '❓')} {impact['risk_level'].upper()}",
                f"- **信頼度スコア**: {impact['confidence_score']:.1%}",
                f"- **緩和策**: {impact['mitigation_status']}",
                "",
            ]
        )

        if impact["risk_factors"]:
            md_lines.append("**リスク要因**:")
            for factor in impact["risk_factors"]:
                md_lines.append(f"- {factor}")
            md_lines.append("")

        # 推奨事項
        if report["recommendations"]:
            md_lines.extend(["### 💡 推奨事項", ""])
            for rec in report["recommendations"]:
                md_lines.append(f"- {rec}")
            md_lines.append("")

        # 詳細情報
        md_lines.extend(["### 🔍 詳細情報", "", "#### Analysis Engine キャッシュ", ""])

        ae_cache = report["details"]["analysis_engine_cache"]
        if "error" not in ae_cache:
            md_lines.extend(
                [
                    f"- **タイプ**: {ae_cache.get('type', 'N/A')}",
                    f"- **L1サイズ**: {ae_cache.get('l1_size', 0)}",
                    f"- **L2サイズ**: {ae_cache.get('l2_size', 0)}",
                    f"- **L3サイズ**: {ae_cache.get('l3_size', 0)}",
                    f"- **総リクエスト数**: {ae_cache.get('total_requests', 0)}",
                    f"- **ヒット数**: {ae_cache.get('hits', 0)}",
                    f"- **ミス数**: {ae_cache.get('misses', 0)}",
                    "",
                ]
            )
        else:
            md_lines.append(f"- **エラー**: {ae_cache['error']}")
            md_lines.append("")

        return "\n".join(md_lines)


def generate_cache_report(project_root: str | None = None) -> dict[str, Any]:
    """
    便利関数：キャッシュレポートを生成

    Args:
        project_root: プロジェクトルートパス

    Returns:
        キャッシュレポート
    """
    try:
        from .cache_manager import CacheManager
    except ImportError:
        # 相対インポートが失敗した場合の代替
        import sys
        from pathlib import Path

        sys.path.append(str(Path(__file__).parent))
        from cache_manager import CacheManager

    cache_manager = CacheManager(project_root)
    cache_stats = cache_manager.get_cache_stats()

    reporter = CacheReporter(project_root)
    return reporter.generate_cache_report(cache_stats)


if __name__ == "__main__":
    # テスト実行

    logging.basicConfig(level=logging.INFO)

    print("📊 キャッシュレポートを生成中...")
    report = generate_cache_report()

    reporter = CacheReporter()
    markdown = reporter.format_report_for_markdown(report)

    print("\n" + "=" * 60)
    print(markdown)
    print("=" * 60)
