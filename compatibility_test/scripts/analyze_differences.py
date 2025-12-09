#!/usr/bin/env python3
"""
tree-sitter-analyzer 出力差分分析スクリプト

使用方法:
    python compatibility_test/scripts/analyze_differences.py --version-a 1.9.2 --version-b 1.9.3
"""

import argparse
import difflib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from compatibility_test.utils.smart_json_comparator import SmartJsonComparator


class DifferenceAnalyzer:
    def __init__(
        self,
        version_a: str,
        version_b: str,
        project_root: str = None,
        config_path: str = None,
        smart_compare: bool = False,
        generate_normalized: bool = False,
    ):
        self.version_a = version_a
        self.version_b = version_b
        self.project_root = (
            Path(project_root) if project_root else Path(__file__).parent.parent.parent
        )
        self.smart_compare = smart_compare
        self.generate_normalized = generate_normalized

        self.results_dir = self.project_root / "compatibility_test" / "results"
        self.version_a_dir = self.results_dir / f"v{version_a}"
        self.version_b_dir = self.results_dir / f"v{version_b}"

        if self.smart_compare or self.generate_normalized:
            if config_path:
                self.config_path = Path(config_path)
            else:
                self.config_path = (
                    self.project_root
                    / "compatibility_test"
                    / "config"
                    / "comparison_config.json"
                )

            if not self.config_path.exists():
                raise FileNotFoundError(
                    f"比較設定ファイルが見つかりません: {self.config_path}"
                )

            self.json_comparator = SmartJsonComparator(self.config_path)

            if self.generate_normalized:
                self.version_a_normalized_dir = (
                    self.results_dir / f"v{version_a}-normalized"
                )
                self.version_b_normalized_dir = (
                    self.results_dir / f"v{version_b}-normalized"
                )

        self.analysis_results = {
            "breaking_changes": [],
            "non_breaking_changes": [],
            "bugs_or_unintended": [],
            "identical_outputs": [],
            "performance_changes": [],
        }

    def analyze_json_differences(self, file_a: Path, file_b: Path) -> dict[str, Any]:
        """JSONファイルの構造的差分を分析"""
        if self.smart_compare:
            report = self.json_comparator.compare_with_report(file_a, file_b)

            severity = "none"
            if not report["is_identical_normalized"]:
                severity = "high"  # 正規化後に差分があれば破壊的変更とみなす
            elif not report["is_identical_raw"]:
                severity = "low"  # 正規化後に一致すれば非破壊的変更

            return {
                "type": "smart_json_comparison",
                "raw_diff": report["raw_diff"],
                "normalized_diff": report["normalized_diff"],
                "is_identical_raw": report["is_identical_raw"],
                "is_identical_normalized": report["is_identical_normalized"],
                "severity": severity,
            }

        try:
            with open(file_a, encoding="utf-8") as f:
                data_a = json.load(f)
            with open(file_b, encoding="utf-8") as f:
                data_b = json.load(f)
        except json.JSONDecodeError as e:
            return {"type": "json_parse_error", "error": str(e), "severity": "high"}
        except Exception as e:
            return {"type": "file_read_error", "error": str(e), "severity": "high"}

        differences = []

        # 構造的差分を検出
        structural_diffs = self._compare_json_structure(data_a, data_b, "")
        differences.extend(structural_diffs)

        # パフォーマンスメトリクスの変化を検出
        perf_diffs = self._compare_performance_metrics(data_a, data_b)
        differences.extend(perf_diffs)

        return {
            "type": "json_comparison",
            "differences": differences,
            "severity": self._determine_severity(differences),
        }

    def _compare_json_structure(
        self, obj_a: Any, obj_b: Any, path: str
    ) -> list[dict[str, Any]]:
        """JSON構造を再帰的に比較"""
        differences = []

        if not isinstance(obj_a, type(obj_b)) and not isinstance(obj_b, type(obj_a)):
            differences.append(
                {
                    "type": "type_change",
                    "path": path,
                    "old_type": type(obj_a).__name__,
                    "new_type": type(obj_b).__name__,
                    "severity": "high",
                }
            )
            return differences

        if isinstance(obj_a, dict):
            # キーの追加・削除を検出
            keys_a = set(obj_a.keys())
            keys_b = set(obj_b.keys())

            added_keys = keys_b - keys_a
            removed_keys = keys_a - keys_b
            common_keys = keys_a & keys_b

            for key in added_keys:
                differences.append(
                    {
                        "type": "key_added",
                        "path": f"{path}.{key}" if path else key,
                        "value": obj_b[key],
                        "severity": "low",
                    }
                )

            for key in removed_keys:
                differences.append(
                    {
                        "type": "key_removed",
                        "path": f"{path}.{key}" if path else key,
                        "value": obj_a[key],
                        "severity": "high",
                    }
                )

            # 共通キーの値を比較
            for key in common_keys:
                new_path = f"{path}.{key}" if path else key
                if obj_a[key] != obj_b[key]:
                    if isinstance(obj_a[key], dict | list):
                        differences.extend(
                            self._compare_json_structure(
                                obj_a[key], obj_b[key], new_path
                            )
                        )
                    else:
                        # 特定のキー名に基づいて重要度を判定
                        severity = self._determine_field_severity(
                            key, obj_a[key], obj_b[key]
                        )
                        differences.append(
                            {
                                "type": "value_changed",
                                "path": new_path,
                                "old_value": obj_a[key],
                                "new_value": obj_b[key],
                                "severity": severity,
                            }
                        )

        elif isinstance(obj_a, list):
            if len(obj_a) != len(obj_b):
                differences.append(
                    {
                        "type": "list_length_changed",
                        "path": path,
                        "old_length": len(obj_a),
                        "new_length": len(obj_b),
                        "severity": "medium",
                    }
                )

            # リスト要素を比較（長さの短い方まで）
            min_length = min(len(obj_a), len(obj_b))
            for i in range(min_length):
                new_path = f"{path}[{i}]"
                if obj_a[i] != obj_b[i]:
                    if isinstance(obj_a[i], dict | list):
                        differences.extend(
                            self._compare_json_structure(obj_a[i], obj_b[i], new_path)
                        )
                    else:
                        differences.append(
                            {
                                "type": "list_item_changed",
                                "path": new_path,
                                "old_value": obj_a[i],
                                "new_value": obj_b[i],
                                "severity": "medium",
                            }
                        )

        return differences

    def _determine_field_severity(
        self, field_name: str, old_value: Any, new_value: Any
    ) -> str:
        """フィールド名と値に基づいて重要度を判定"""
        # 破壊的変更の可能性が高いフィールド
        breaking_fields = [
            "capture_name",
            "node_type",
            "name",
            "type",
            "id",
            "start_line",
            "end_line",
            "start_column",
            "end_column",
        ]

        # パフォーマンス関連フィールド
        performance_fields = [
            "elapsed_ms",
            "execution_time",
            "fd_elapsed_ms",
            "rg_elapsed_ms",
            "processing_time",
            "duration",
        ]

        if field_name in breaking_fields:
            return "high"
        elif field_name in performance_fields:
            return "low"
        elif isinstance(old_value, str) and isinstance(new_value, str):
            # 文字列の場合、大幅な変更は重要度が高い
            if len(old_value) > 0 and len(new_value) == 0:
                return "high"
            elif abs(len(old_value) - len(new_value)) > len(old_value) * 0.5:
                return "medium"

        return "medium"

    def _compare_performance_metrics(
        self, data_a: Any, data_b: Any
    ) -> list[dict[str, Any]]:
        """パフォーマンスメトリクスの変化を分析"""
        differences = []

        def extract_metrics(obj, path=""):
            metrics = {}
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_path = f"{path}.{key}" if path else key
                    if key.endswith("_ms") or key.endswith("_time") or "elapsed" in key:
                        if isinstance(value, int | float):
                            metrics[new_path] = value
                    elif isinstance(value, dict):
                        metrics.update(extract_metrics(value, new_path))
            return metrics

        metrics_a = extract_metrics(data_a)
        metrics_b = extract_metrics(data_b)

        for path in metrics_a:
            if path in metrics_b:
                old_val = metrics_a[path]
                new_val = metrics_b[path]
                if old_val != new_val and old_val > 0:
                    change_percent = ((new_val - old_val) / old_val) * 100
                    differences.append(
                        {
                            "type": "performance_change",
                            "path": path,
                            "old_value": old_val,
                            "new_value": new_val,
                            "change_percent": round(change_percent, 2),
                            "severity": "low",
                        }
                    )

        return differences

    def _determine_severity(self, differences: list[dict[str, Any]]) -> str:
        """差分リストから全体の重要度を判定"""
        if any(diff["severity"] == "high" for diff in differences):
            return "high"
        elif any(diff["severity"] == "medium" for diff in differences):
            return "medium"
        else:
            return "low"

    def analyze_text_differences(self, file_a: Path, file_b: Path) -> dict[str, Any]:
        """テキストファイルの差分を分析"""
        try:
            with open(file_a, encoding="utf-8") as f:
                content_a = f.read()
            with open(file_b, encoding="utf-8") as f:
                content_b = f.read()
        except Exception as e:
            return {"type": "file_read_error", "error": str(e), "severity": "high"}

        if content_a == content_b:
            return {"type": "identical", "severity": "none"}

        # 行単位での差分を生成
        diff_lines = list(
            difflib.unified_diff(
                content_a.splitlines(keepends=True),
                content_b.splitlines(keepends=True),
                fromfile=f"v{self.version_a}/{file_a.name}",
                tofile=f"v{self.version_b}/{file_b.name}",
            )
        )

        # 変更の性質を分析
        added_lines = sum(
            1
            for line in diff_lines
            if line.startswith("+") and not line.startswith("+++")
        )
        removed_lines = sum(
            1
            for line in diff_lines
            if line.startswith("-") and not line.startswith("---")
        )

        return {
            "type": "text_difference",
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "diff": "".join(diff_lines),
            "severity": "medium" if added_lines + removed_lines > 10 else "low",
        }

    def analyze_all_differences(self) -> dict[str, Any]:
        """全ての差分を分析"""
        print(f"🔍 v{self.version_a} と v{self.version_b} の差分を分析中...")

        if self.generate_normalized:
            print(f"  ...正規化ファイルを出力中: v{self.version_a}-normalized")
            self.json_comparator.generate_normalized_files(
                self.version_a_dir, self.version_a_normalized_dir
            )
            print(f"  ...正規化ファイルを出力中: v{self.version_b}-normalized")
            self.json_comparator.generate_normalized_files(
                self.version_b_dir, self.version_b_normalized_dir
            )
            print("  ✅ 正規化ファイルの生成が完了しました。")

        if not self.version_a_dir.exists():
            print(
                f"❌ v{self.version_a} の結果ディレクトリが見つかりません: {self.version_a_dir}"
            )
            return {}

        if not self.version_b_dir.exists():
            print(
                f"❌ v{self.version_b} の結果ディレクトリが見つかりません: {self.version_b_dir}"
            )
            return {}

        # ファイル一覧を取得
        files_a = {f.name: f for f in self.version_a_dir.iterdir() if f.is_file()}
        files_b = {f.name: f for f in self.version_b_dir.iterdir() if f.is_file()}

        common_files = set(files_a.keys()) & set(files_b.keys())
        missing_in_b = set(files_a.keys()) - set(files_b.keys())
        missing_in_a = set(files_b.keys()) - set(files_a.keys())

        results = {
            "analysis_date": datetime.now().isoformat(),
            "version_a": self.version_a,
            "version_b": self.version_b,
            "file_analysis": {},
            "summary": {
                "total_files": len(common_files),
                "identical_files": 0,
                "different_files": 0,
                "breaking_changes": 0,
                "non_breaking_changes": 0,
                "performance_changes": 0,
            },
            "missing_files": {
                "missing_in_b": list(missing_in_b),
                "missing_in_a": list(missing_in_a),
            },
        }

        # 共通ファイルを分析
        for filename in sorted(common_files):
            file_a = files_a[filename]
            file_b = files_b[filename]

            print(f"  📄 分析中: {filename}")

            if filename.endswith(".json"):
                analysis = self.analyze_json_differences(file_a, file_b)
            else:
                analysis = self.analyze_text_differences(file_a, file_b)

            results["file_analysis"][filename] = analysis

            # 統計を更新
            if analysis.get("type") == "identical" or analysis.get(
                "is_identical_normalized"
            ):
                results["summary"]["identical_files"] += 1
            else:
                results["summary"]["different_files"] += 1

                if analysis.get("severity") == "high":
                    results["summary"]["breaking_changes"] += 1
                elif analysis.get("severity") in ["medium", "low"]:
                    results["summary"]["non_breaking_changes"] += 1

                # パフォーマンス変更をカウント
                if analysis.get("type") == "json_comparison":
                    perf_changes = [
                        d
                        for d in analysis.get("differences", [])
                        if d.get("type") == "performance_change"
                    ]
                    results["summary"]["performance_changes"] += len(perf_changes)
                elif analysis.get("type") == "smart_json_comparison":
                    if not analysis.get("is_identical_raw") and analysis.get(
                        "is_identical_normalized"
                    ):
                        results["summary"]["performance_changes"] += (
                            1  # Or a more specific count
                        )

        return results

    def generate_analysis_report(self, analysis_results: dict[str, Any]) -> str:
        """分析レポートを生成"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_name = (
            "smart_comparison_report"
            if self.smart_compare
            else f"difference_analysis_{self.version_a}_vs_{self.version_b}"
        )
        report_file = (
            self.project_root
            / "compatibility_test"
            / "reports"
            / f"{report_name}_{timestamp}.md"
        )

        # レポート内容を生成
        report_title = f"# {'スマート' if self.smart_compare else ''}差分分析レポート: v{self.version_a} vs v{self.version_b}"
        report_lines = [
            report_title,
            "",
            f"- **分析実施日**: {analysis_results['analysis_date']}",
            f"- **分析対象**: v{self.version_a} → v{self.version_b}",
            "",
            "## 分析サマリー",
            "",
            "| 項目 | 値 |",
            "| :--- | :--- |",
            f"| 総ファイル数 | {analysis_results['summary']['total_files']} |",
            f"| 一致ファイル | {analysis_results['summary']['identical_files']} |",
            f"| 差分ファイル | {analysis_results['summary']['different_files']} |",
            f"| 破壊的変更 | {analysis_results['summary']['breaking_changes']} |",
            f"| 非破壊的変更 | {analysis_results['summary']['non_breaking_changes']} |",
            f"| パフォーマンス変更 | {analysis_results['summary']['performance_changes']} |",
            "",
        ]

        # 欠落ファイルがある場合
        missing = analysis_results.get("missing_files", {})
        if missing.get("missing_in_a") or missing.get("missing_in_b"):
            report_lines.extend(
                [
                    "## 欠落ファイル",
                    "",
                ]
            )

            if missing.get("missing_in_b"):
                report_lines.extend([f"### v{self.version_b}で欠落:", ""])
                for filename in missing["missing_in_b"]:
                    report_lines.append(f"- {filename}")
                report_lines.append("")

            if missing.get("missing_in_a"):
                report_lines.extend([f"### v{self.version_a}で欠落:", ""])
                for filename in missing["missing_in_a"]:
                    report_lines.append(f"- {filename}")
                report_lines.append("")

        # ファイル別詳細分析
        report_lines.extend(["## ファイル別詳細分析", ""])

        for filename, analysis in analysis_results.get("file_analysis", {}).items():
            report_lines.extend([f"### {filename}", ""])

            if analysis.get("type") == "identical":
                report_lines.append("✅ **完全一致**")
            elif analysis.get("type") == "smart_json_comparison":
                if analysis["is_identical_normalized"]:
                    report_lines.append("- **Raw比較**: 差異あり")
                    report_lines.append("- **正規化比較**: 一致")
                    report_lines.append("- **最終判定**: 実質的に同一 ✅")
                    if analysis["raw_diff"]:
                        report_lines.append("\n**詳細分析:**")
                        # 無視されたフィールドの差分などを表示
                        ignored_diffs = analysis["raw_diff"].get("values_changed", {})
                        for key, values in ignored_diffs.items():
                            report_lines.append(
                                f"- {key}: {values['old_value']} vs {values['new_value']}"
                            )
                else:
                    report_lines.append("- **Raw比較**: 差異あり")
                    report_lines.append("- **正規化比較**: 差異あり")
                    report_lines.append("- **最終判定**: 差分あり ❌")
                    if analysis["normalized_diff"]:
                        report_lines.append("\n**正規化後の差分:**")
                        report_lines.append(
                            f"```json\n{analysis['normalized_diff'].to_json(indent=2)}\n```"
                        )

            elif analysis.get("type") == "json_comparison":
                differences = analysis.get("differences", [])
                if differences:
                    report_lines.append(f"⚠️ **{len(differences)}件の差分を検出**")
                    report_lines.append("")

                    # 重要度別に分類
                    high_severity = [
                        d for d in differences if d.get("severity") == "high"
                    ]
                    medium_severity = [
                        d for d in differences if d.get("severity") == "medium"
                    ]
                    low_severity = [
                        d for d in differences if d.get("severity") == "low"
                    ]

                    if high_severity:
                        report_lines.append("#### 🚨 高重要度の変更:")
                        for diff in high_severity:
                            report_lines.append(
                                f"- **{diff['type']}**: `{diff['path']}`"
                            )
                            if "old_value" in diff and "new_value" in diff:
                                report_lines.append(
                                    f"  - 変更前: `{diff['old_value']}`"
                                )
                                report_lines.append(
                                    f"  - 変更後: `{diff['new_value']}`"
                                )
                        report_lines.append("")

                    if medium_severity:
                        report_lines.append("#### ⚠️ 中重要度の変更:")
                        for diff in medium_severity:
                            report_lines.append(
                                f"- **{diff['type']}**: `{diff['path']}`"
                            )
                        report_lines.append("")

                    if low_severity:
                        report_lines.append("#### ℹ️ 低重要度の変更:")
                        for diff in low_severity:
                            if diff["type"] == "performance_change":
                                change_pct = diff.get("change_percent", 0)
                                direction = "向上" if change_pct < 0 else "悪化"
                                report_lines.append(
                                    f"- **パフォーマンス{direction}**: `{diff['path']}` ({change_pct:+.1f}%)"
                                )
                            else:
                                report_lines.append(
                                    f"- **{diff['type']}**: `{diff['path']}`"
                                )
                        report_lines.append("")
                else:
                    report_lines.append("✅ **構造的差分なし**")

            elif analysis.get("type") == "text_difference":
                added = analysis.get("added_lines", 0)
                removed = analysis.get("removed_lines", 0)
                report_lines.append(f"📝 **テキスト差分**: +{added}行, -{removed}行")

            report_lines.append("")

        # レポートを保存
        report_content = "\n".join(report_lines)
        report_file.parent.mkdir(parents=True, exist_ok=True)

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)

        print(f"📄 差分分析レポートを生成しました: {report_file}")
        return str(report_file)


def main():
    """メイン実行関数"""
    parser = argparse.ArgumentParser(description="tree-sitter-analyzer 出力差分分析")
    parser.add_argument(
        "--version-a", required=True, help="比較元バージョン (例: 1.9.2)"
    )
    parser.add_argument(
        "--version-b", required=True, help="比較先バージョン (例: 1.9.3)"
    )
    parser.add_argument(
        "--project-root", help="プロジェクトルートパス (デフォルト: 自動検出)"
    )
    parser.add_argument("--output-json", help="分析結果をJSONファイルに出力")
    parser.add_argument(
        "--smart-compare", action="store_true", help="スマート比較モードを有効化"
    )
    parser.add_argument(
        "--generate-normalized",
        action="store_true",
        help="正規化されたJSONファイルを出力",
    )
    parser.add_argument("--config", help="比較設定ファイルのパス")

    args = parser.parse_args()

    analyzer = DifferenceAnalyzer(
        version_a=args.version_a,
        version_b=args.version_b,
        project_root=args.project_root,
        config_path=args.config,
        smart_compare=args.smart_compare,
        generate_normalized=args.generate_normalized,
    )

    try:
        # 差分分析を実行
        analysis_results = analyzer.analyze_all_differences()

        if not analysis_results:
            print("❌ 分析に失敗しました")
            sys.exit(1)

        # レポート生成
        report_file = analyzer.generate_analysis_report(analysis_results)

        # JSON出力（オプション）
        if args.output_json:
            json_file = Path(args.output_json)
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(analysis_results, f, indent=2, ensure_ascii=False)
            print(f"📄 JSON結果を保存しました: {json_file}")

        # サマリー表示
        summary = analysis_results["summary"]
        print("\n" + "=" * 60)
        print("🎉 差分分析完了!")
        print(f"📊 総ファイル数: {summary['total_files']}")
        print(
            f"📊 一致: {summary['identical_files']}, 差分: {summary['different_files']}"
        )
        print(
            f"📊 破壊的変更: {summary['breaking_changes']}, 非破壊的変更: {summary['non_breaking_changes']}"
        )
        print(f"📋 詳細レポート: {report_file}")

    except Exception as e:
        print(f"❌ 分析エラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
