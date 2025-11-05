#!/usr/bin/env python3
"""
Format Regression Report Generator

Generates detailed HTML reports when format regressions are detected.
This tool is automatically triggered by CI/CD when format tests fail.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


class RegressionReportGenerator:
    """Generates comprehensive format regression reports"""

    def __init__(self, output_dir: Path = None):
        """
        Initialize regression report generator

        Args:
            output_dir: Directory to save reports (defaults to current directory)
        """
        self.output_dir = output_dir or Path.cwd()
        self.report_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "git_info": self._get_git_info(),
            "environment": self._get_environment_info(),
            "test_failures": [],
            "format_changes": [],
            "recommendations": [],
        }

    def _get_git_info(self) -> dict[str, str]:
        """Get current git information"""
        try:
            return {
                "commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], text=True
                ).strip(),
                "branch": subprocess.check_output(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True
                ).strip(),
                "author": subprocess.check_output(
                    ["git", "log", "-1", "--pretty=format:%an <%ae>"], text=True
                ).strip(),
                "message": subprocess.check_output(
                    ["git", "log", "-1", "--pretty=format:%s"], text=True
                ).strip(),
            }
        except subprocess.CalledProcessError:
            return {"error": "Git information not available"}

    def _get_environment_info(self) -> dict[str, str]:
        """Get environment information"""
        return {
            "python_version": sys.version,
            "platform": sys.platform,
            "working_directory": str(Path.cwd()),
            "ci_environment": os.environ.get("CI", "false"),
            "github_actions": os.environ.get("GITHUB_ACTIONS", "false"),
        }

    def add_test_failure(
        self,
        test_name: str,
        failure_type: str,
        expected: str,
        actual: str,
        diff: str | None = None,
    ) -> None:
        """
        Add a test failure to the report

        Args:
            test_name: Name of the failed test
            failure_type: Type of failure (format_mismatch, schema_violation, etc.)
            expected: Expected output
            actual: Actual output
            diff: Diff between expected and actual (optional)
        """
        self.report_data["test_failures"].append(
            {
                "test_name": test_name,
                "failure_type": failure_type,
                "expected": expected,
                "actual": actual,
                "diff": diff,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def add_format_change(
        self,
        format_type: str,
        change_description: str,
        impact_level: str,
        affected_components: list[str],
    ) -> None:
        """
        Add a format change to the report

        Args:
            format_type: Type of format (markdown, csv, json)
            change_description: Description of the change
            impact_level: Impact level (low, medium, high, critical)
            affected_components: List of affected components
        """
        self.report_data["format_changes"].append(
            {
                "format_type": format_type,
                "change_description": change_description,
                "impact_level": impact_level,
                "affected_components": affected_components,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def add_recommendation(self, recommendation: str, priority: str = "medium") -> None:
        """
        Add a recommendation to the report

        Args:
            recommendation: Recommendation text
            priority: Priority level (low, medium, high)
        """
        self.report_data["recommendations"].append(
            {
                "recommendation": recommendation,
                "priority": priority,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def generate_html_report(self) -> Path:
        """
        Generate HTML regression report

        Returns:
            Path to generated HTML report
        """
        html_content = self._generate_html_content()
        report_path = self.output_dir / "regression_report.html"

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return report_path

    def _generate_html_content(self) -> str:
        """Generate HTML content for the report"""
        return f"""
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Format Regression Report - {self.report_data['timestamp']}</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #d73027; border-bottom: 3px solid #d73027; padding-bottom: 10px; }}
        h2 {{ color: #2166ac; border-bottom: 2px solid #2166ac; padding-bottom: 5px; }}
        h3 {{ color: #5e3c99; }}
        .summary {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .failure {{ background: #f8d7da; border: 1px solid #f5c6cb; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .change {{ background: #d1ecf1; border: 1px solid #bee5eb; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .recommendation {{ background: #d4edda; border: 1px solid #c3e6cb; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .code {{ background: #f8f9fa; border: 1px solid #e9ecef; padding: 10px; border-radius: 3px; font-family: 'Courier New', monospace; white-space: pre-wrap; }}
        .diff {{ background: #f8f9fa; border: 1px solid #e9ecef; padding: 10px; border-radius: 3px; font-family: 'Courier New', monospace; white-space: pre-wrap; font-size: 12px; }}
        .priority-high {{ border-left: 5px solid #d73027; }}
        .priority-medium {{ border-left: 5px solid #fdae61; }}
        .priority-low {{ border-left: 5px solid #abd9e9; }}
        .impact-critical {{ background: #f8d7da; }}
        .impact-high {{ background: #fff3cd; }}
        .impact-medium {{ background: #d1ecf1; }}
        .impact-low {{ background: #d4edda; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        .timestamp {{ color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚨 Format Regression Report</h1>

        <div class="summary">
            <h2>📊 Summary</h2>
            <p><strong>Generated:</strong> {self.report_data['timestamp']}</p>
            <p><strong>Total Test Failures:</strong> {len(self.report_data['test_failures'])}</p>
            <p><strong>Format Changes Detected:</strong> {len(self.report_data['format_changes'])}</p>
            <p><strong>Recommendations:</strong> {len(self.report_data['recommendations'])}</p>
        </div>

        <h2>🔧 Environment Information</h2>
        <table>
            <tr><th>Property</th><th>Value</th></tr>
            <tr><td>Git Commit</td><td>{self.report_data['git_info'].get('commit', 'N/A')}</td></tr>
            <tr><td>Git Branch</td><td>{self.report_data['git_info'].get('branch', 'N/A')}</td></tr>
            <tr><td>Author</td><td>{self.report_data['git_info'].get('author', 'N/A')}</td></tr>
            <tr><td>Commit Message</td><td>{self.report_data['git_info'].get('message', 'N/A')}</td></tr>
            <tr><td>Python Version</td><td>{self.report_data['environment']['python_version']}</td></tr>
            <tr><td>Platform</td><td>{self.report_data['environment']['platform']}</td></tr>
            <tr><td>CI Environment</td><td>{self.report_data['environment']['ci_environment']}</td></tr>
        </table>

        {self._generate_failures_section()}
        {self._generate_changes_section()}
        {self._generate_recommendations_section()}

        <h2>🔗 Next Steps</h2>
        <ol>
            <li>Review all test failures and format changes listed above</li>
            <li>Determine if changes are intentional or regressions</li>
            <li>If intentional, update golden masters: <code>python tests/format_testing/update_golden_masters.py</code></li>
            <li>If regressions, fix the underlying issues and re-run tests</li>
            <li>Consider adding additional test cases to prevent similar regressions</li>
        </ol>

        <div class="timestamp">
            <p>Report generated at {datetime.utcnow().isoformat()} UTC</p>
        </div>
    </div>
</body>
</html>
        """

    def _generate_failures_section(self) -> str:
        """Generate HTML for test failures section"""
        if not self.report_data["test_failures"]:
            return "<h2>✅ No Test Failures</h2><p>All format tests passed successfully.</p>"

        html = "<h2>❌ Test Failures</h2>"
        for failure in self.report_data["test_failures"]:
            html += f"""
            <div class="failure">
                <h3>{failure['test_name']}</h3>
                <p><strong>Failure Type:</strong> {failure['failure_type']}</p>
                <p><strong>Expected:</strong></p>
                <div class="code">{failure['expected']}</div>
                <p><strong>Actual:</strong></p>
                <div class="code">{failure['actual']}</div>
                {f'<p><strong>Diff:</strong></p><div class="diff">{failure["diff"]}</div>' if failure.get('diff') else ''}
                <p class="timestamp">Failed at: {failure['timestamp']}</p>
            </div>
            """
        return html

    def _generate_changes_section(self) -> str:
        """Generate HTML for format changes section"""
        if not self.report_data["format_changes"]:
            return "<h2>📋 No Format Changes Detected</h2>"

        html = "<h2>🔄 Format Changes</h2>"
        for change in self.report_data["format_changes"]:
            impact_class = f"impact-{change['impact_level']}"
            html += f"""
            <div class="change {impact_class}">
                <h3>{change['format_type']} Format Change</h3>
                <p><strong>Impact Level:</strong> {change['impact_level'].upper()}</p>
                <p><strong>Description:</strong> {change['change_description']}</p>
                <p><strong>Affected Components:</strong> {', '.join(change['affected_components'])}</p>
                <p class="timestamp">Detected at: {change['timestamp']}</p>
            </div>
            """
        return html

    def _generate_recommendations_section(self) -> str:
        """Generate HTML for recommendations section"""
        if not self.report_data["recommendations"]:
            return ""

        html = "<h2>💡 Recommendations</h2>"
        for rec in self.report_data["recommendations"]:
            priority_class = f"priority-{rec['priority']}"
            html += f"""
            <div class="recommendation {priority_class}">
                <p><strong>Priority:</strong> {rec['priority'].upper()}</p>
                <p>{rec['recommendation']}</p>
                <p class="timestamp">Added at: {rec['timestamp']}</p>
            </div>
            """
        return html

    def generate_json_report(self) -> Path:
        """
        Generate JSON regression report

        Returns:
            Path to generated JSON report
        """
        report_path = self.output_dir / "regression_report.json"

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(self.report_data, f, indent=2, ensure_ascii=False)

        return report_path


def main():
    """Main function to generate regression report"""
    generator = RegressionReportGenerator()

    # Example usage - in real scenario, this would be populated by test results
    generator.add_test_failure(
        test_name="test_markdown_table_format",
        failure_type="format_mismatch",
        expected="| Name | Type |\n|------|------|\n| Test | class |",
        actual="| Name | Type |\n|:-----|:-----|\n| Test | class |",
        diff="- |------|------|\n+ |:-----|:-----|",
    )

    generator.add_format_change(
        format_type="markdown",
        change_description="Table separator format changed from simple dashes to alignment indicators",
        impact_level="medium",
        affected_components=["MarkdownFormatter", "TableGenerator"],
    )

    generator.add_recommendation(
        "Consider updating golden masters if format changes are intentional",
        priority="high",
    )

    # Generate reports
    html_path = generator.generate_html_report()
    json_path = generator.generate_json_report()

    print(f"HTML report generated: {html_path}")
    print(f"JSON report generated: {json_path}")


if __name__ == "__main__":
    main()
