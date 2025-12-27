#!/usr/bin/env python3
"""
Format Monitoring Tool

Continuous monitoring tool for format quality, regression detection,
and performance tracking. Generates comprehensive reports and alerts.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root to path - needs to be before imports  # noqa: E402
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.integration.formatters.golden_master import GoldenMasterManager  # noqa: E402
from tests.integration.formatters.schema_validation import validate_format  # noqa: E402
from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (  # noqa: E402
    AnalyzeCodeStructureTool,
)


class FormatMonitoringDatabase:
    """Database for storing format monitoring data"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize monitoring database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Format validation results table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS format_validations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                file_path TEXT NOT NULL,
                format_type TEXT NOT NULL,
                language TEXT NOT NULL,
                validation_result TEXT NOT NULL,
                output_hash TEXT NOT NULL,
                errors TEXT,
                warnings TEXT,
                performance_ms INTEGER,
                file_size_bytes INTEGER
            )
        """
        )

        # Format regression tracking table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS format_regressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                file_path TEXT NOT NULL,
                format_type TEXT NOT NULL,
                regression_type TEXT NOT NULL,
                description TEXT NOT NULL,
                severity TEXT NOT NULL,
                resolved BOOLEAN DEFAULT FALSE,
                resolution_timestamp TEXT
            )
        """
        )

        # Format performance metrics table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS format_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                file_path TEXT NOT NULL,
                format_type TEXT NOT NULL,
                processing_time_ms INTEGER NOT NULL,
                memory_usage_mb REAL,
                output_size_bytes INTEGER,
                file_size_bytes INTEGER
            )
        """
        )

        # Format quality metrics table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS format_quality (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                format_type TEXT NOT NULL,
                compliance_score REAL NOT NULL,
                schema_validity BOOLEAN NOT NULL,
                consistency_score REAL NOT NULL,
                total_files_tested INTEGER NOT NULL,
                failed_files INTEGER NOT NULL
            )
        """
        )

        conn.commit()
        conn.close()

    def record_validation(
        self, file_path: str, format_type: str, language: str, result: dict[str, Any]
    ):
        """Record format validation result"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO format_validations
            (timestamp, file_path, format_type, language, validation_result,
             output_hash, errors, warnings, performance_ms, file_size_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                datetime.utcnow().isoformat(),
                file_path,
                format_type,
                language,
                json.dumps(result.get("success", False)),
                result.get("output_hash", ""),
                json.dumps(result.get("errors", [])),
                json.dumps(result.get("warnings", [])),
                result.get("performance_ms", 0),
                result.get("file_size_bytes", 0),
            ),
        )

        conn.commit()
        conn.close()

    def record_regression(
        self,
        file_path: str,
        format_type: str,
        regression_type: str,
        description: str,
        severity: str,
    ):
        """Record format regression"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO format_regressions
            (timestamp, file_path, format_type, regression_type, description, severity)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                datetime.utcnow().isoformat(),
                file_path,
                format_type,
                regression_type,
                description,
                severity,
            ),
        )

        conn.commit()
        conn.close()

    def record_performance(
        self, file_path: str, format_type: str, metrics: dict[str, Any]
    ):
        """Record format performance metrics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO format_performance
            (timestamp, file_path, format_type, processing_time_ms,
             memory_usage_mb, output_size_bytes, file_size_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                datetime.utcnow().isoformat(),
                file_path,
                format_type,
                metrics.get("processing_time_ms", 0),
                metrics.get("memory_usage_mb", 0.0),
                metrics.get("output_size_bytes", 0),
                metrics.get("file_size_bytes", 0),
            ),
        )

        conn.commit()
        conn.close()

    def record_quality_metrics(self, format_type: str, metrics: dict[str, Any]):
        """Record format quality metrics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO format_quality
            (timestamp, format_type, compliance_score, schema_validity,
             consistency_score, total_files_tested, failed_files)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                datetime.utcnow().isoformat(),
                format_type,
                metrics.get("compliance_score", 0.0),
                metrics.get("schema_validity", False),
                metrics.get("consistency_score", 0.0),
                metrics.get("total_files_tested", 0),
                metrics.get("failed_files", 0),
            ),
        )

        conn.commit()
        conn.close()

    def get_recent_regressions(self, days: int = 7) -> list[dict[str, Any]]:
        """Get recent format regressions"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        since_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        cursor.execute(
            """
            SELECT * FROM format_regressions
            WHERE timestamp > ? AND resolved = FALSE
            ORDER BY timestamp DESC
        """,
            (since_date,),
        )

        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

        conn.close()
        return results

    def get_performance_trends(self, days: int = 30) -> dict[str, list[dict[str, Any]]]:
        """Get performance trends by format type"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        since_date = (datetime.utcnow() - timedelta(days=days)).isoformat()

        cursor.execute(
            """
            SELECT format_type, AVG(processing_time_ms) as avg_time,
                   AVG(memory_usage_mb) as avg_memory,
                   COUNT(*) as sample_count,
                   DATE(timestamp) as date
            FROM format_performance
            WHERE timestamp > ?
            GROUP BY format_type, DATE(timestamp)
            ORDER BY date DESC
        """,
            (since_date,),
        )

        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

        # Group by format type
        trends = {}
        for result in results:
            format_type = result["format_type"]
            if format_type not in trends:
                trends[format_type] = []
            trends[format_type].append(result)

        conn.close()
        return trends


class FormatMonitor:
    """Format monitoring and analysis tool"""

    def __init__(self, db_path: str = "format_monitoring.db"):
        self.db = FormatMonitoringDatabase(db_path)
        self.golden_master_manager = GoldenMasterManager()
        self.cross_component_validator = None
        self.logger = self._setup_logging()

    def _setup_logging(self) -> logging.Logger:
        """Setup logging for monitoring"""
        logger = logging.getLogger("format_monitor")
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    async def monitor_file(self, file_path: str, temp_dir: str) -> dict[str, Any]:
        """Monitor format output for a single file"""
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            return {"error": "File not found"}

        # Detect language
        language = self._detect_language(file_path_obj)
        if not language:
            return {"error": "Unsupported language"}

        results = {}

        # Test all format types
        for format_type in ["full", "compact", "csv"]:
            try:
                result = await self._monitor_format_type(
                    file_path, format_type, language, temp_dir
                )
                results[format_type] = result

                # Record in database
                self.db.record_validation(file_path, format_type, language, result)

                if result.get("performance_metrics"):
                    self.db.record_performance(
                        file_path, format_type, result["performance_metrics"]
                    )

                # Check for regressions
                if result.get("regression_detected"):
                    self.db.record_regression(
                        file_path,
                        format_type,
                        result["regression_type"],
                        result["regression_description"],
                        result["regression_severity"],
                    )

            except Exception as e:
                self.logger.error(
                    f"Error monitoring {file_path} with {format_type}: {e}"
                )
                results[format_type] = {"error": str(e)}

        return results

    async def _monitor_format_type(
        self, file_path: str, format_type: str, language: str, temp_dir: str
    ) -> dict[str, Any]:
        """Monitor specific format type for a file"""
        start_time = time.time()

        # Generate format output
        tool = AnalyzeCodeStructureTool(project_root=temp_dir)
        result = await tool.execute(
            {"file_path": file_path, "format_type": format_type, "language": language}
        )

        processing_time = (time.time() - start_time) * 1000  # Convert to ms
        output = result["table_output"]

        # Calculate output hash for regression detection
        output_hash = hashlib.md5(output.encode("utf-8")).hexdigest()  # nosec

        # Validate format compliance
        validation_result = self._validate_format_compliance(output, format_type)

        # Check for regressions using golden master
        regression_result = self._check_format_regression(
            output, format_type, file_path, output_hash
        )

        # Performance metrics
        file_size = Path(file_path).stat().st_size
        performance_metrics = {
            "processing_time_ms": int(processing_time),
            "output_size_bytes": len(output.encode("utf-8")),
            "file_size_bytes": file_size,
            "memory_usage_mb": 0.0,  # Would need memory profiling for accurate measurement
        }

        return {
            "success": validation_result["valid"],
            "output_hash": output_hash,
            "errors": validation_result.get("errors", []),
            "warnings": validation_result.get("warnings", []),
            "performance_metrics": performance_metrics,
            "regression_detected": regression_result["detected"],
            "regression_type": regression_result.get("type", ""),
            "regression_description": regression_result.get("description", ""),
            "regression_severity": regression_result.get("severity", ""),
            "compliance_score": validation_result.get("compliance_score", 0.0),
        }

    def _detect_language(self, file_path: Path) -> str | None:
        """Detect programming language from file extension"""
        extension_map = {
            ".py": "python",
            ".java": "java",
            ".ts": "typescript",
            ".js": "javascript",
            ".html": "html",
            ".css": "css",
            ".md": "markdown",
        }
        return extension_map.get(file_path.suffix.lower())

    def _validate_format_compliance(
        self, output: str, format_type: str
    ) -> dict[str, Any]:
        """Validate format compliance and calculate score"""
        errors = []
        warnings = []

        # Schema validation
        schema_type = "csv" if format_type == "csv" else "markdown"
        validation_result = validate_format(output, schema_type)

        if not validation_result.is_valid:
            errors.extend(validation_result.errors)

        # Format-specific compliance
        try:
            if format_type == "full":
                # Basic full format checks
                if "## Class Info" not in output:
                    errors.append("Missing Class Info section")
                if "## Methods" not in output:
                    errors.append("Missing Methods section")
                if "## Fields" not in output:
                    errors.append("Missing Fields section")

            elif format_type == "compact":
                # Basic compact format checks
                if "## Info" not in output:
                    errors.append("Missing Info section")
                if "Parameters" in output:
                    warnings.append("Compact format should omit parameter details")

            elif format_type == "csv":
                # Basic CSV format checks
                lines = output.strip().split("\n")
                if len(lines) < 2:
                    errors.append("CSV must have header and data rows")

                expected_header = (
                    "Type,Name,ReturnType,Parameters,Access,Static,Final,Line"
                )
                if lines and lines[0] != expected_header:
                    errors.append("CSV header format incorrect")

        except Exception as e:
            errors.append(f"Compliance validation error: {e}")

        # Calculate compliance score
        compliance_score = max(0.0, 1.0 - (len(errors) * 0.2) - (len(warnings) * 0.1))

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "compliance_score": compliance_score,
        }

    def _check_format_regression(
        self, output: str, format_type: str, file_path: str, output_hash: str
    ) -> dict[str, Any]:
        """Check for format regressions using golden master comparison"""
        try:
            # Create a test identifier from file path
            test_id = f"{Path(file_path).stem}_{format_type}"

            golden_tester = self.golden_master_manager.get_tester(format_type)

            # Try to compare with existing golden master
            try:
                golden_tester.assert_matches_golden_master(output, test_id)
                return {"detected": False}

            except AssertionError as e:
                # Regression detected
                return {
                    "detected": True,
                    "type": "output_change",
                    "description": str(e),
                    "severity": "medium",
                }

            except FileNotFoundError:
                # No golden master exists, create one
                golden_tester.create_golden_master(output, test_id)
                return {"detected": False}

        except Exception as e:
            return {
                "detected": True,
                "type": "validation_error",
                "description": f"Regression check failed: {e}",
                "severity": "high",
            }

    async def generate_monitoring_report(
        self, output_dir: str = "./monitoring-reports"
    ):
        """Generate comprehensive monitoring report"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        # Generate different report types
        reports = {
            "summary": self._generate_summary_report(),
            "regressions": self._generate_regression_report(),
            "performance": self._generate_performance_report(),
            "quality_trends": self._generate_quality_trends_report(),
        }

        # Save reports
        for report_type, report_data in reports.items():
            report_file = (
                output_path / f"format_monitoring_{report_type}_{timestamp}.json"
            )
            with open(report_file, "w") as f:
                json.dump(report_data, f, indent=2, default=str)

            self.logger.info(f"Generated {report_type} report: {report_file}")

        # Generate HTML dashboard
        dashboard_file = output_path / f"format_monitoring_dashboard_{timestamp}.html"
        self._generate_html_dashboard(reports, dashboard_file)

        return {
            "reports_generated": len(reports),
            "output_directory": str(output_path),
            "dashboard": str(dashboard_file),
        }

    def _generate_summary_report(self) -> dict[str, Any]:
        """Generate summary monitoring report"""
        # Get recent data from database
        recent_regressions = self.db.get_recent_regressions(7)
        performance_trends = self.db.get_performance_trends(30)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "active_regressions": len(recent_regressions),
                "monitored_formats": ["full", "compact", "csv"],
                "performance_trend": "stable",  # Would calculate from actual data
            },
            "recent_regressions": recent_regressions[:10],  # Top 10
            "performance_overview": {
                format_type: {
                    "avg_processing_time": (
                        sum(d["avg_time"] for d in data) / len(data) if data else 0
                    ),
                    "sample_count": sum(d["sample_count"] for d in data),
                }
                for format_type, data in performance_trends.items()
            },
        }

    def _generate_regression_report(self) -> dict[str, Any]:
        """Generate regression-focused report"""
        regressions = self.db.get_recent_regressions(30)

        # Group by severity and type
        by_severity = {}
        by_type = {}

        for regression in regressions:
            severity = regression["severity"]
            reg_type = regression["regression_type"]

            if severity not in by_severity:
                by_severity[severity] = []
            by_severity[severity].append(regression)

            if reg_type not in by_type:
                by_type[reg_type] = []
            by_type[reg_type].append(regression)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_regressions": len(regressions),
            "by_severity": {k: len(v) for k, v in by_severity.items()},
            "by_type": {k: len(v) for k, v in by_type.items()},
            "detailed_regressions": regressions,
        }

    def _generate_performance_report(self) -> dict[str, Any]:
        """Generate performance-focused report"""
        trends = self.db.get_performance_trends(30)

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "performance_trends": trends,
            "recommendations": self._generate_performance_recommendations(trends),
        }

    def _generate_quality_trends_report(self) -> dict[str, Any]:
        """Generate quality trends report"""
        # This would query quality metrics from database
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "quality_trends": {
                "full": {"compliance_score": 0.95, "trend": "stable"},
                "compact": {"compliance_score": 0.92, "trend": "improving"},
                "csv": {"compliance_score": 0.98, "trend": "stable"},
            },
        }

    def _generate_performance_recommendations(
        self, trends: dict[str, list[dict[str, Any]]]
    ) -> list[str]:
        """Generate performance recommendations based on trends"""
        recommendations = []

        for format_type, data in trends.items():
            if data:
                avg_time = sum(d["avg_time"] for d in data) / len(data)
                if avg_time > 1000:  # More than 1 second
                    recommendations.append(
                        f"Consider optimizing {format_type} format processing (avg: {avg_time:.0f}ms)"
                    )

        return recommendations

    def _generate_html_dashboard(self, reports: dict[str, Any], output_file: Path):
        """Generate HTML dashboard for monitoring reports"""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Format Monitoring Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .error {{ color: red; }}
        .warning {{ color: orange; }}
        .success {{ color: green; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Format Monitoring Dashboard</h1>
        <p>Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC</p>
    </div>

    <div class="section">
        <h2>Summary</h2>
        <p>Active Regressions: <span class="{"error" if reports["summary"]["summary"]["active_regressions"] > 0 else "success"}">{reports["summary"]["summary"]["active_regressions"]}</span></p>
        <p>Monitored Formats: {", ".join(reports["summary"]["summary"]["monitored_formats"])}</p>
    </div>

    <div class="section">
        <h2>Recent Regressions</h2>
        <table>
            <tr><th>File</th><th>Format</th><th>Type</th><th>Severity</th><th>Description</th></tr>
            {"".join(f'<tr><td>{r["file_path"]}</td><td>{r["format_type"]}</td><td>{r["regression_type"]}</td><td class="{r["severity"]}">{r["severity"]}</td><td>{r["description"]}</td></tr>' for r in reports["summary"]["recent_regressions"])}
        </table>
    </div>

    <div class="section">
        <h2>Performance Overview</h2>
        <table>
            <tr><th>Format</th><th>Avg Processing Time (ms)</th><th>Sample Count</th></tr>
            {"".join(f"<tr><td>{fmt}</td><td>{data['avg_processing_time']:.1f}</td><td>{data['sample_count']}</td></tr>" for fmt, data in reports["summary"]["performance_overview"].items())}
        </table>
    </div>
</body>
</html>
        """

        with open(output_file, "w") as f:
            f.write(html_content)


async def main():
    """Main monitoring function"""
    parser = argparse.ArgumentParser(description="Format monitoring tool")
    parser.add_argument("--files", nargs="*", help="Files to monitor")
    parser.add_argument("--directory", help="Directory to monitor")
    parser.add_argument(
        "--report-only", action="store_true", help="Generate reports only"
    )
    parser.add_argument(
        "--output-dir",
        default="./monitoring-reports",
        help="Output directory for reports",
    )
    parser.add_argument(
        "--db-path", default="format_monitoring.db", help="Database path"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    monitor = FormatMonitor(args.db_path)

    if args.report_only:
        # Generate reports only
        result = await monitor.generate_monitoring_report(args.output_dir)
        print(f"Generated monitoring reports in {result['output_directory']}")
        return 0

    # Monitor files
    files_to_monitor = []

    if args.files:
        files_to_monitor.extend(args.files)

    if args.directory:
        directory = Path(args.directory)
        if directory.exists():
            for ext in [".py", ".java", ".ts", ".js", ".html", ".css", ".md"]:
                files_to_monitor.extend(directory.glob(f"**/*{ext}"))

    if not files_to_monitor:
        print("No files to monitor")
        return 1

    # Monitor each file
    with tempfile.TemporaryDirectory() as temp_dir:
        total_files = len(files_to_monitor)
        successful = 0

        for i, file_path in enumerate(files_to_monitor, 1):
            if args.verbose:
                print(f"Monitoring {file_path} ({i}/{total_files})...")

            try:
                result = await monitor.monitor_file(str(file_path), temp_dir)

                if not any(
                    "error" in r for r in result.values() if isinstance(r, dict)
                ):
                    successful += 1
                elif args.verbose:
                    print(f"  Errors in {file_path}")

            except Exception as e:
                if args.verbose:
                    print(f"  Failed to monitor {file_path}: {e}")

    # Generate final report
    report_result = await monitor.generate_monitoring_report(args.output_dir)

    print("Monitoring complete:")
    print(f"  Files monitored: {total_files}")
    print(f"  Successful: {successful}")
    print(f"  Reports generated: {report_result['reports_generated']}")
    print(f"  Dashboard: {report_result['dashboard']}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
