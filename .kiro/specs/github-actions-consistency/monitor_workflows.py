#!/usr/bin/env python3
"""
GitHub Actions Workflow Monitor

This script helps monitor GitHub Actions workflow executions and collect metrics.
It can be used to track deployment progress and identify issues.

Usage:
    python monitor_workflows.py --repo owner/repo --token YOUR_GITHUB_TOKEN
    python monitor_workflows.py --repo owner/repo --token YOUR_GITHUB_TOKEN --workflow develop-automation.yml
    python monitor_workflows.py --repo owner/repo --token YOUR_GITHUB_TOKEN --since 2025-11-20
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Error: requests library not found. Install with: pip install requests")
    sys.exit(1)


class WorkflowMonitor:
    """Monitor GitHub Actions workflows and collect metrics."""

    def __init__(self, repo: str, token: str):
        """
        Initialize the workflow monitor.

        Args:
            repo: Repository in format "owner/repo"
            token: GitHub personal access token
        """
        self.repo = repo
        self.token = token
        self.base_url = f"https://api.github.com/repos/{repo}"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def get_workflow_runs(
        self, workflow_name: str | None = None, since: str | None = None
    ) -> list[dict]:
        """
        Get workflow runs from GitHub API.

        Args:
            workflow_name: Optional workflow file name to filter
            since: Optional ISO date string to filter runs after this date

        Returns:
            List of workflow run dictionaries
        """
        url = f"{self.base_url}/actions/runs"
        params = {"per_page": 100}

        if workflow_name:
            # Get workflow ID first
            workflows_url = f"{self.base_url}/actions/workflows"
            response = requests.get(workflows_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            workflows = response.json()["workflows"]

            workflow_id = None
            for workflow in workflows:
                if workflow["path"].endswith(workflow_name):
                    workflow_id = workflow["id"]
                    break

            if workflow_id:
                url = f"{self.base_url}/actions/workflows/{workflow_id}/runs"

        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        runs = response.json()["workflow_runs"]

        # Filter by date if specified
        if since:
            since_date = datetime.fromisoformat(since)
            runs = [
                run
                for run in runs
                if datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
                >= since_date
            ]

        return runs

    def analyze_runs(self, runs: list[dict]) -> dict:
        """
        Analyze workflow runs and calculate metrics.

        Args:
            runs: List of workflow run dictionaries

        Returns:
            Dictionary containing analysis results
        """
        if not runs:
            return {
                "total_runs": 0,
                "successful_runs": 0,
                "failed_runs": 0,
                "success_rate": 0.0,
                "average_duration": 0.0,
                "workflows": {},
            }

        total_runs = len(runs)
        successful_runs = sum(1 for run in runs if run["conclusion"] == "success")
        failed_runs = sum(1 for run in runs if run["conclusion"] == "failure")

        # Calculate durations (in minutes)
        durations = []
        for run in runs:
            if run["conclusion"] in ["success", "failure"]:
                created = datetime.fromisoformat(
                    run["created_at"].replace("Z", "+00:00")
                )
                updated = datetime.fromisoformat(
                    run["updated_at"].replace("Z", "+00:00")
                )
                duration = (updated - created).total_seconds() / 60
                durations.append(duration)

        average_duration = sum(durations) / len(durations) if durations else 0.0

        # Group by workflow
        workflows = {}
        for run in runs:
            workflow_name = run["name"]
            if workflow_name not in workflows:
                workflows[workflow_name] = {
                    "total": 0,
                    "success": 0,
                    "failure": 0,
                    "durations": [],
                }

            workflows[workflow_name]["total"] += 1
            if run["conclusion"] == "success":
                workflows[workflow_name]["success"] += 1
            elif run["conclusion"] == "failure":
                workflows[workflow_name]["failure"] += 1

            if run["conclusion"] in ["success", "failure"]:
                created = datetime.fromisoformat(
                    run["created_at"].replace("Z", "+00:00")
                )
                updated = datetime.fromisoformat(
                    run["updated_at"].replace("Z", "+00:00")
                )
                duration = (updated - created).total_seconds() / 60
                workflows[workflow_name]["durations"].append(duration)

        # Calculate per-workflow metrics
        for _workflow_name, data in workflows.items():
            data["success_rate"] = (
                (data["success"] / data["total"] * 100) if data["total"] > 0 else 0.0
            )
            data["average_duration"] = (
                sum(data["durations"]) / len(data["durations"])
                if data["durations"]
                else 0.0
            )

        return {
            "total_runs": total_runs,
            "successful_runs": successful_runs,
            "failed_runs": failed_runs,
            "success_rate": (
                (successful_runs / total_runs * 100) if total_runs > 0 else 0.0
            ),
            "average_duration": average_duration,
            "workflows": workflows,
        }

    def print_report(self, analysis: dict):
        """
        Print a formatted report of the analysis.

        Args:
            analysis: Analysis results dictionary
        """
        print("\n" + "=" * 80)
        print("GitHub Actions Workflow Monitoring Report")
        print("=" * 80)
        print(f"\nRepository: {self.repo}")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        print("\n" + "-" * 80)
        print("Overall Metrics")
        print("-" * 80)
        print(f"Total Runs: {analysis['total_runs']}")
        print(f"Successful Runs: {analysis['successful_runs']}")
        print(f"Failed Runs: {analysis['failed_runs']}")
        print(f"Success Rate: {analysis['success_rate']:.2f}%")
        print(f"Average Duration: {analysis['average_duration']:.2f} minutes")

        if analysis["workflows"]:
            print("\n" + "-" * 80)
            print("Per-Workflow Metrics")
            print("-" * 80)

            for workflow_name, data in analysis["workflows"].items():
                print(f"\n{workflow_name}:")
                print(f"  Total Runs: {data['total']}")
                print(f"  Successful: {data['success']}")
                print(f"  Failed: {data['failure']}")
                print(f"  Success Rate: {data['success_rate']:.2f}%")
                print(f"  Average Duration: {data['average_duration']:.2f} minutes")

        print("\n" + "=" * 80)

    def export_to_json(self, analysis: dict, output_file: str):
        """
        Export analysis results to JSON file.

        Args:
            analysis: Analysis results dictionary
            output_file: Path to output JSON file
        """
        output_path = Path(output_file)
        with open(output_path, "w") as f:
            json.dump(analysis, f, indent=2)
        print(f"\nAnalysis exported to: {output_path}")

    def get_recent_failures(self, runs: list[dict]) -> list[dict]:
        """
        Get details of recent failed runs.

        Args:
            runs: List of workflow run dictionaries

        Returns:
            List of failed run details
        """
        failures = []
        for run in runs:
            if run["conclusion"] == "failure":
                failures.append(
                    {
                        "workflow": run["name"],
                        "run_number": run["run_number"],
                        "created_at": run["created_at"],
                        "html_url": run["html_url"],
                        "head_branch": run["head_branch"],
                        "head_sha": run["head_sha"][:7],
                    }
                )
        return failures

    def print_failures(self, failures: list[dict]):
        """
        Print details of recent failures.

        Args:
            failures: List of failure dictionaries
        """
        if not failures:
            print("\n✅ No recent failures detected!")
            return

        print("\n" + "-" * 80)
        print("Recent Failures")
        print("-" * 80)

        for failure in failures:
            print(f"\n❌ {failure['workflow']} (Run #{failure['run_number']})")
            print(f"   Branch: {failure['head_branch']}")
            print(f"   Commit: {failure['head_sha']}")
            print(f"   Date: {failure['created_at']}")
            print(f"   URL: {failure['html_url']}")


def main():
    """Main entry point for the workflow monitor."""
    parser = argparse.ArgumentParser(
        description="Monitor GitHub Actions workflow executions"
    )
    parser.add_argument(
        "--repo", required=True, help='Repository in format "owner/repo"'
    )
    parser.add_argument("--token", required=True, help="GitHub personal access token")
    parser.add_argument(
        "--workflow", help="Specific workflow file name to monitor (e.g., ci.yml)"
    )
    parser.add_argument(
        "--since",
        help="Only show runs since this date (ISO format: YYYY-MM-DD)",
    )
    parser.add_argument("--output", help="Export analysis to JSON file")
    parser.add_argument(
        "--show-failures", action="store_true", help="Show details of recent failures"
    )

    args = parser.parse_args()

    try:
        monitor = WorkflowMonitor(args.repo, args.token)

        print(f"Fetching workflow runs for {args.repo}...")
        runs = monitor.get_workflow_runs(workflow_name=args.workflow, since=args.since)

        if not runs:
            print("No workflow runs found matching the criteria.")
            return

        print(f"Found {len(runs)} workflow runs.")

        analysis = monitor.analyze_runs(runs)
        monitor.print_report(analysis)

        if args.show_failures:
            failures = monitor.get_recent_failures(runs)
            monitor.print_failures(failures)

        if args.output:
            monitor.export_to_json(analysis, args.output)

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Error communicating with GitHub API: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
