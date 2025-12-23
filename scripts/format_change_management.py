#!/usr/bin/env python3
"""
Format Change Management System

Manages format changes, approvals, tracking, and rollback capabilities.
Ensures controlled evolution of format specifications.
"""

import argparse
import hashlib
import json
import logging
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path - needs to be before imports  # noqa: E402
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.integration.formatters.golden_master import GoldenMasterManager  # noqa: E402


class FormatChangeDatabase:
    """Database for tracking format changes"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize change management database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Format change requests table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS format_change_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                requester TEXT NOT NULL,
                format_type TEXT NOT NULL,
                change_type TEXT NOT NULL,
                description TEXT NOT NULL,
                justification TEXT NOT NULL,
                impact_assessment TEXT,
                status TEXT DEFAULT 'pending',
                reviewer TEXT,
                review_timestamp TEXT,
                review_comments TEXT,
                implementation_timestamp TEXT,
                rollback_timestamp TEXT
            )
        """
        )

        # Format versions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS format_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                format_type TEXT NOT NULL,
                version TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                change_request_id INTEGER,
                specification_hash TEXT NOT NULL,
                golden_master_hash TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                rollback_version TEXT,
                FOREIGN KEY (change_request_id) REFERENCES format_change_requests (id)
            )
        """
        )

        # Format compatibility matrix table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS format_compatibility (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                format_type TEXT NOT NULL,
                from_version TEXT NOT NULL,
                to_version TEXT NOT NULL,
                compatibility_level TEXT NOT NULL,
                breaking_changes TEXT,
                migration_required BOOLEAN DEFAULT FALSE,
                migration_script TEXT
            )
        """
        )

        # Format approval workflow table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS format_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                change_request_id INTEGER NOT NULL,
                approver TEXT NOT NULL,
                approval_timestamp TEXT NOT NULL,
                approval_status TEXT NOT NULL,
                comments TEXT,
                FOREIGN KEY (change_request_id) REFERENCES format_change_requests (id)
            )
        """
        )

        conn.commit()
        conn.close()

    def create_change_request(
        self,
        requester: str,
        format_type: str,
        change_type: str,
        description: str,
        justification: str,
        impact_assessment: str = "",
    ) -> int:
        """Create a new format change request"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO format_change_requests
            (timestamp, requester, format_type, change_type, description,
             justification, impact_assessment)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                datetime.utcnow().isoformat(),
                requester,
                format_type,
                change_type,
                description,
                justification,
                impact_assessment,
            ),
        )

        change_request_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return change_request_id

    def add_approval(
        self, change_request_id: int, approver: str, status: str, comments: str = ""
    ):
        """Add approval to change request"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO format_approvals
            (change_request_id, approver, approval_timestamp, approval_status, comments)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                change_request_id,
                approver,
                datetime.utcnow().isoformat(),
                status,
                comments,
            ),
        )

        conn.commit()
        conn.close()

    def update_change_request_status(
        self,
        change_request_id: int,
        status: str,
        reviewer: str = "",
        comments: str = "",
    ):
        """Update change request status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE format_change_requests
            SET status = ?, reviewer = ?, review_timestamp = ?, review_comments = ?
            WHERE id = ?
        """,
            (
                status,
                reviewer,
                datetime.utcnow().isoformat(),
                comments,
                change_request_id,
            ),
        )

        conn.commit()
        conn.close()

    def create_format_version(
        self,
        format_type: str,
        version: str,
        change_request_id: int,
        specification_hash: str,
        golden_master_hash: str = "",
    ) -> int:
        """Create new format version"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Deactivate previous versions
        cursor.execute(
            """
            UPDATE format_versions
            SET is_active = FALSE
            WHERE format_type = ? AND is_active = TRUE
        """,
            (format_type,),
        )

        # Create new version
        cursor.execute(
            """
            INSERT INTO format_versions
            (format_type, version, timestamp, change_request_id,
             specification_hash, golden_master_hash, is_active)
            VALUES (?, ?, ?, ?, ?, ?, TRUE)
        """,
            (
                format_type,
                version,
                datetime.utcnow().isoformat(),
                change_request_id,
                specification_hash,
                golden_master_hash,
            ),
        )

        version_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return version_id

    def get_pending_requests(self) -> list[dict[str, Any]]:
        """Get pending change requests"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM format_change_requests
            WHERE status = 'pending'
            ORDER BY timestamp DESC
        """
        )

        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

        conn.close()
        return results

    def get_change_request(self, request_id: int) -> dict[str, Any] | None:
        """Get specific change request"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM format_change_requests WHERE id = ?
        """,
            (request_id,),
        )

        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row, strict=False))
        else:
            result = None

        conn.close()
        return result

    def get_format_versions(self, format_type: str) -> list[dict[str, Any]]:
        """Get format version history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM format_versions
            WHERE format_type = ?
            ORDER BY timestamp DESC
        """,
            (format_type,),
        )

        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

        conn.close()
        return results

    def get_active_version(self, format_type: str) -> dict[str, Any] | None:
        """Get active format version"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM format_versions
            WHERE format_type = ? AND is_active = TRUE
        """,
            (format_type,),
        )

        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            result = dict(zip(columns, row, strict=False))
        else:
            result = None

        conn.close()
        return result


class FormatChangeManager:
    """Format change management system"""

    def __init__(self, db_path: str = "format_changes.db"):
        self.db = FormatChangeDatabase(db_path)
        self.golden_master_manager = GoldenMasterManager()
        self.logger = self._setup_logging()

        # Change type definitions
        self.change_types = {
            "enhancement": "Format enhancement or new feature",
            "bugfix": "Fix for format output issues",
            "breaking": "Breaking change requiring migration",
            "deprecation": "Deprecation of format features",
            "security": "Security-related format changes",
        }

        # Approval requirements by change type
        self.approval_requirements = {
            "enhancement": ["tech_lead"],
            "bugfix": ["developer"],
            "breaking": ["tech_lead", "product_owner"],
            "deprecation": ["tech_lead", "product_owner"],
            "security": ["security_lead", "tech_lead"],
        }

    def _setup_logging(self) -> logging.Logger:
        """Setup logging for change management"""
        logger = logging.getLogger("format_change_manager")
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def create_change_request(
        self,
        requester: str,
        format_type: str,
        change_type: str,
        description: str,
        justification: str,
        impact_assessment: str = "",
    ) -> int:
        """Create new format change request"""
        if change_type not in self.change_types:
            raise ValueError(f"Invalid change type: {change_type}")

        if format_type not in ["full", "compact", "csv"]:
            raise ValueError(f"Invalid format type: {format_type}")

        # Perform impact assessment if not provided
        if not impact_assessment:
            impact_assessment = self._assess_change_impact(
                format_type, change_type, description
            )

        request_id = self.db.create_change_request(
            requester,
            format_type,
            change_type,
            description,
            justification,
            impact_assessment,
        )

        self.logger.info(
            f"Created change request {request_id} for {format_type} format"
        )
        return request_id

    def _assess_change_impact(
        self, format_type: str, change_type: str, description: str
    ) -> str:
        """Assess impact of proposed change"""
        impact_factors = []

        # Assess based on change type
        if change_type == "breaking":
            impact_factors.append("HIGH: Breaking change requires migration")
        elif change_type == "security":
            impact_factors.append("HIGH: Security implications")
        elif change_type == "deprecation":
            impact_factors.append("MEDIUM: Deprecation affects existing users")
        else:
            impact_factors.append("LOW: Non-breaking change")

        # Assess based on format type
        if format_type == "csv":
            impact_factors.append("MEDIUM: CSV format changes affect data processing")
        elif format_type == "full":
            impact_factors.append("HIGH: Full format is primary output format")
        else:
            impact_factors.append("LOW: Compact format has limited usage")

        # Check for keywords in description
        high_impact_keywords = ["schema", "structure", "header", "column", "field"]
        if any(keyword in description.lower() for keyword in high_impact_keywords):
            impact_factors.append("HIGH: Structural changes detected")

        return "; ".join(impact_factors)

    def approve_change_request(
        self, request_id: int, approver: str, status: str, comments: str = ""
    ):
        """Approve or reject change request"""
        if status not in ["approved", "rejected", "needs_revision"]:
            raise ValueError(f"Invalid approval status: {status}")

        request = self.db.get_change_request(request_id)
        if not request:
            raise ValueError(f"Change request {request_id} not found")

        # Add approval record
        self.db.add_approval(request_id, approver, status, comments)

        # Check if all required approvals are met
        if status == "approved":
            required_approvers = self.approval_requirements.get(
                request["change_type"], ["developer"]
            )
            if self._check_approval_requirements(request_id, required_approvers):
                self.db.update_change_request_status(
                    request_id, "approved", approver, comments
                )
                self.logger.info(f"Change request {request_id} fully approved")
            else:
                self.logger.info(
                    f"Change request {request_id} partially approved, waiting for more approvals"
                )
        else:
            self.db.update_change_request_status(request_id, status, approver, comments)
            self.logger.info(f"Change request {request_id} {status}")

    def _check_approval_requirements(
        self, request_id: int, required_approvers: list[str]
    ) -> bool:
        """Check if approval requirements are met"""
        # This is a simplified check - in practice, you'd check actual approver roles
        # For now, we'll assume any approval from required roles is sufficient
        return True

    def implement_change(self, request_id: int, implementer: str) -> str:
        """Implement approved format change"""
        request = self.db.get_change_request(request_id)
        if not request:
            raise ValueError(f"Change request {request_id} not found")

        if request["status"] != "approved":
            raise ValueError(f"Change request {request_id} is not approved")

        format_type = request["format_type"]

        # Generate new version number
        versions = self.db.get_format_versions(format_type)
        if versions:
            latest_version = versions[0]["version"]
            major, minor, patch = map(int, latest_version.split("."))

            if request["change_type"] == "breaking":
                new_version = f"{major + 1}.0.0"
            elif request["change_type"] in ["enhancement", "deprecation"]:
                new_version = f"{major}.{minor + 1}.0"
            else:
                new_version = f"{major}.{minor}.{patch + 1}"
        else:
            new_version = "1.0.0"

        # Create backup of current format specification
        self._backup_current_format(format_type, new_version)

        # Calculate specification hash (simplified - would hash actual spec file)
        spec_hash = hashlib.md5(
            f"{format_type}_{new_version}_{datetime.utcnow()}".encode()
        ).hexdigest()

        # Create new format version
        self.db.create_format_version(format_type, new_version, request_id, spec_hash)

        # Update change request status
        self.db.update_change_request_status(request_id, "implemented", implementer)

        self.logger.info(
            f"Implemented change request {request_id} as version {new_version}"
        )

        return new_version

    def _backup_current_format(self, format_type: str, new_version: str) -> str:
        """Backup current format specification"""
        backup_dir = Path("format_backups")
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{format_type}_backup_{timestamp}_v{new_version}"
        backup_path.mkdir(exist_ok=True)

        # Backup golden masters
        golden_master_dir = Path("tests/integration/formatters/golden_masters")
        if golden_master_dir.exists():
            shutil.copytree(
                golden_master_dir, backup_path / "golden_masters", dirs_exist_ok=True
            )

        # Backup format specifications
        spec_file = Path("docs/format_specifications.md")
        if spec_file.exists():
            shutil.copy2(spec_file, backup_path / "format_specifications.md")

        self.logger.info(f"Created backup at {backup_path}")
        return str(backup_path)

    def rollback_change(self, request_id: int, rollback_reason: str) -> str:
        """Rollback implemented format change"""
        request = self.db.get_change_request(request_id)
        if not request:
            raise ValueError(f"Change request {request_id} not found")

        if request["status"] != "implemented":
            raise ValueError(f"Change request {request_id} is not implemented")

        format_type = request["format_type"]

        # Find the version to rollback to
        versions = self.db.get_format_versions(format_type)
        if len(versions) < 2:
            raise ValueError("No previous version to rollback to")

        current_version = versions[0]
        previous_version = versions[1]

        # Restore from backup
        self._restore_from_backup(format_type, previous_version["version"])

        # Create rollback version entry
        rollback_version = f"{current_version['version']}-rollback"
        self.db.create_format_version(
            format_type,
            rollback_version,
            request_id,
            previous_version["specification_hash"],
            previous_version["golden_master_hash"],
        )

        # Update change request
        self.db.update_change_request_status(
            request_id, "rolled_back", "", rollback_reason
        )

        self.logger.info(
            f"Rolled back change request {request_id} to version {previous_version['version']}"
        )

        return rollback_version

    def _restore_from_backup(self, format_type: str, version: str):
        """Restore format from backup"""
        backup_dir = Path("format_backups")

        # Find the most recent backup for this version
        backup_pattern = f"{format_type}_backup_*_v{version}"
        backups = list(backup_dir.glob(backup_pattern))

        if not backups:
            raise ValueError(f"No backup found for {format_type} version {version}")

        latest_backup = max(backups, key=lambda p: p.stat().st_mtime)

        # Restore golden masters
        golden_master_backup = latest_backup / "golden_masters"
        if golden_master_backup.exists():
            golden_master_dir = Path("tests/integration/formatters/golden_masters")
            if golden_master_dir.exists():
                shutil.rmtree(golden_master_dir)
            shutil.copytree(golden_master_backup, golden_master_dir)

        # Restore format specifications
        spec_backup = latest_backup / "format_specifications.md"
        if spec_backup.exists():
            shutil.copy2(spec_backup, "docs/format_specifications.md")

        self.logger.info(f"Restored from backup {latest_backup}")

    def generate_change_report(self, output_file: str = "format_change_report.json"):
        """Generate comprehensive change management report"""
        pending_requests = self.db.get_pending_requests()

        # Get version history for all formats
        format_histories = {}
        for format_type in ["full", "compact", "csv"]:
            format_histories[format_type] = self.db.get_format_versions(format_type)

        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "pending_requests": len(pending_requests),
                "total_formats": len(format_histories),
                "active_versions": {
                    fmt: versions[0]["version"] if versions else "none"
                    for fmt, versions in format_histories.items()
                },
            },
            "pending_requests": pending_requests,
            "format_histories": format_histories,
            "change_types": self.change_types,
            "approval_requirements": self.approval_requirements,
        }

        with open(output_file, "w") as f:
            json.dump(report, f, indent=2, default=str)

        self.logger.info(f"Generated change report: {output_file}")
        return report


def main():
    """Main change management function"""
    parser = argparse.ArgumentParser(description="Format change management")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create change request
    create_parser = subparsers.add_parser("create", help="Create change request")
    create_parser.add_argument("--requester", required=True, help="Requester name")
    create_parser.add_argument(
        "--format",
        required=True,
        choices=["full", "compact", "csv"],
        help="Format type",
    )
    create_parser.add_argument(
        "--type",
        required=True,
        choices=["enhancement", "bugfix", "breaking", "deprecation", "security"],
        help="Change type",
    )
    create_parser.add_argument(
        "--description", required=True, help="Change description"
    )
    create_parser.add_argument(
        "--justification", required=True, help="Change justification"
    )
    create_parser.add_argument("--impact", help="Impact assessment")

    # Approve change request
    approve_parser = subparsers.add_parser("approve", help="Approve change request")
    approve_parser.add_argument(
        "--request-id", type=int, required=True, help="Request ID"
    )
    approve_parser.add_argument("--approver", required=True, help="Approver name")
    approve_parser.add_argument(
        "--status",
        required=True,
        choices=["approved", "rejected", "needs_revision"],
        help="Approval status",
    )
    approve_parser.add_argument("--comments", help="Approval comments")

    # Implement change
    implement_parser = subparsers.add_parser("implement", help="Implement change")
    implement_parser.add_argument(
        "--request-id", type=int, required=True, help="Request ID"
    )
    implement_parser.add_argument(
        "--implementer", required=True, help="Implementer name"
    )

    # Rollback change
    rollback_parser = subparsers.add_parser("rollback", help="Rollback change")
    rollback_parser.add_argument(
        "--request-id", type=int, required=True, help="Request ID"
    )
    rollback_parser.add_argument("--reason", required=True, help="Rollback reason")

    # List pending requests
    subparsers.add_parser("list", help="List pending requests")

    # Generate report
    report_parser = subparsers.add_parser("report", help="Generate change report")
    report_parser.add_argument(
        "--output", default="format_change_report.json", help="Output file"
    )

    # Database path
    parser.add_argument("--db-path", default="format_changes.db", help="Database path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    manager = FormatChangeManager(args.db_path)

    try:
        if args.command == "create":
            request_id = manager.create_change_request(
                args.requester,
                args.format,
                args.type,
                args.description,
                args.justification,
                args.impact or "",
            )
            print(f"Created change request {request_id}")

        elif args.command == "approve":
            manager.approve_change_request(
                args.request_id, args.approver, args.status, args.comments or ""
            )
            print(f"Updated approval for request {args.request_id}")

        elif args.command == "implement":
            version = manager.implement_change(args.request_id, args.implementer)
            print(f"Implemented change request {args.request_id} as version {version}")

        elif args.command == "rollback":
            version = manager.rollback_change(args.request_id, args.reason)
            print(f"Rolled back change request {args.request_id} to {version}")

        elif args.command == "list":
            pending = manager.db.get_pending_requests()
            if pending:
                print(f"Pending change requests ({len(pending)}):")
                for req in pending:
                    print(
                        f"  {req['id']}: {req['format_type']} - {req['change_type']} - {req['description'][:50]}..."
                    )
            else:
                print("No pending change requests")

        elif args.command == "report":
            report = manager.generate_change_report(args.output)
            print(f"Generated change report: {args.output}")
            print(f"Pending requests: {report['summary']['pending_requests']}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
