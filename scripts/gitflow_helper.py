#!/usr/bin/env python3
"""
GitFlow Helper Script

This script helps developers follow the correct GitFlow branching strategy
and automates common GitFlow operations.
"""

import argparse
import subprocess  # nosec B404
import sys
from pathlib import Path


class GitFlowHelper:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent

    def run_command(
        self, command: list[str], check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a git command and return the result"""
        try:
            result = subprocess.run(  # nosec B603
                command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=check,
            )
            return result
        except subprocess.CalledProcessError as e:
            print(f"❌ Command failed: {' '.join(command)}")
            print(f"Error: {e}")
            sys.exit(1)

    def get_current_branch(self) -> str:
        """Get the current git branch"""
        result = self.run_command(["git", "branch", "--show-current"])
        return result.stdout.strip()

    def check_branch_exists(self, branch: str) -> bool:
        """Check if a branch exists locally or remotely"""
        local_result = self.run_command(
            ["git", "branch", "--list", branch], check=False
        )
        remote_result = self.run_command(
            ["git", "branch", "-r", "--list", f"origin/{branch}"], check=False
        )
        return bool(local_result.stdout.strip()) or bool(remote_result.stdout.strip())

    def start_feature(self, feature_name: str):
        """Start a new feature branch from develop"""
        current_branch = self.get_current_branch()
        if current_branch != "develop":
            print("❌ You must be on the 'develop' branch to start a feature")
            print(f"Current branch: {current_branch}")
            print("Please run: git checkout develop")
            sys.exit(1)

        # Pull latest develop
        print("📥 Pulling latest changes from develop...")
        self.run_command(["git", "pull", "origin", "develop"])

        # Create and checkout feature branch
        feature_branch = f"feature/{feature_name}"
        print(f"🌿 Creating feature branch: {feature_branch}")
        self.run_command(["git", "checkout", "-b", feature_branch])

        print(f"✅ Feature branch '{feature_branch}' created successfully!")
        print("🚀 You can now start developing your feature")

    def finish_feature(self, feature_name: str):
        """Finish a feature branch and merge back to develop"""
        feature_branch = f"feature/{feature_name}"
        current_branch = self.get_current_branch()

        if not current_branch.startswith("feature/"):
            print("❌ You must be on a feature branch to finish it")
            print(f"Current branch: {current_branch}")
            sys.exit(1)

        # Check if there are uncommitted changes
        status_result = self.run_command(["git", "status", "--porcelain"])
        if status_result.stdout.strip():
            print("❌ You have uncommitted changes. Please commit or stash them first.")
            sys.exit(1)

        # Switch to develop and pull latest
        print("📥 Switching to develop branch...")
        self.run_command(["git", "checkout", "develop"])
        self.run_command(["git", "pull", "origin", "develop"])

        # Merge feature branch
        print(f"🔀 Merging {feature_branch} into develop...")
        self.run_command(["git", "merge", feature_branch])

        # Push develop
        print("📤 Pushing develop to remote...")
        self.run_command(["git", "push", "origin", "develop"])

        # Delete feature branch
        print(f"🗑️ Deleting feature branch {feature_branch}...")
        self.run_command(["git", "branch", "-d", feature_branch])

        print(f"✅ Feature '{feature_name}' completed and merged to develop!")

    def start_release(self, version: str):
        """Start a new release branch from develop"""
        current_branch = self.get_current_branch()
        if current_branch != "develop":
            print("❌ You must be on the 'develop' branch to start a release")
            print(f"Current branch: {current_branch}")
            print("Please run: git checkout develop")
            sys.exit(1)

        # Pull latest develop
        print("📥 Pulling latest changes from develop...")
        self.run_command(["git", "pull", "origin", "develop"])

        # Create and checkout release branch
        release_branch = f"release/{version}"
        print(f"🚀 Creating release branch: {release_branch}")
        self.run_command(["git", "checkout", "-b", release_branch])

        print(f"✅ Release branch '{release_branch}' created successfully!")
        print("📦 This branch will be used for PyPI deployment")
        print("🔀 After deployment, merge to both main and develop")

    def finish_release(self, version: str):
        """Finish a release branch and merge to main and develop"""
        release_branch = f"release/{version}"
        current_branch = self.get_current_branch()

        if not current_branch.startswith("release/"):
            print("❌ You must be on a release branch to finish it")
            print(f"Current branch: {current_branch}")
            sys.exit(1)

        # Check if there are uncommitted changes
        status_result = self.run_command(["git", "status", "--porcelain"])
        if status_result.stdout.strip():
            print("❌ You have uncommitted changes. Please commit or stash them first.")
            sys.exit(1)

        # Switch to main and merge
        print("📥 Switching to main branch...")
        self.run_command(["git", "checkout", "main"])
        self.run_command(["git", "pull", "origin", "main"])
        self.run_command(["git", "merge", release_branch])

        # Tag the release
        print(f"🏷️ Tagging release {version}...")
        self.run_command(["git", "tag", "-a", version, "-m", f"Release {version}"])

        # Push main and tags
        print("📤 Pushing main and tags to remote...")
        self.run_command(["git", "push", "origin", "main"])
        self.run_command(["git", "push", "origin", "--tags"])

        # Switch to develop and merge
        print("📥 Switching to develop branch...")
        self.run_command(["git", "checkout", "develop"])
        self.run_command(["git", "pull", "origin", "develop"])
        self.run_command(["git", "merge", release_branch])

        # Push develop
        print("📤 Pushing develop to remote...")
        self.run_command(["git", "push", "origin", "develop"])

        # Delete release branch
        print(f"🗑️ Deleting release branch {release_branch}...")
        self.run_command(["git", "branch", "-d", release_branch])

        print(f"✅ Release '{version}' completed and merged to main and develop!")

    def start_hotfix(self, hotfix_name: str):
        """Start a new hotfix branch from main"""
        current_branch = self.get_current_branch()
        if current_branch != "main":
            print("❌ You must be on the 'main' branch to start a hotfix")
            print(f"Current branch: {current_branch}")
            print("Please run: git checkout main")
            sys.exit(1)

        # Pull latest main
        print("📥 Pulling latest changes from main...")
        self.run_command(["git", "pull", "origin", "main"])

        # Create and checkout hotfix branch
        hotfix_branch = f"hotfix/{hotfix_name}"
        print(f"🚨 Creating hotfix branch: {hotfix_branch}")
        self.run_command(["git", "checkout", "-b", hotfix_branch])

        print(f"✅ Hotfix branch '{hotfix_branch}' created successfully!")
        print("🚨 This branch is for critical bug fixes only")

    def finish_hotfix(self, hotfix_name: str):
        """Finish a hotfix branch and merge to main and develop"""
        hotfix_branch = f"hotfix/{hotfix_name}"
        current_branch = self.get_current_branch()

        if not current_branch.startswith("hotfix/"):
            print("❌ You must be on a hotfix branch to finish it")
            print(f"Current branch: {current_branch}")
            sys.exit(1)

        # Check if there are uncommitted changes
        status_result = self.run_command(["git", "status", "--porcelain"])
        if status_result.stdout.strip():
            print("❌ You have uncommitted changes. Please commit or stash them first.")
            sys.exit(1)

        # Switch to main and merge
        print("📥 Switching to main branch...")
        self.run_command(["git", "checkout", "main"])
        self.run_command(["git", "pull", "origin", "main"])
        self.run_command(["git", "merge", hotfix_branch])

        # Tag the hotfix
        print(f"🏷️ Tagging hotfix {hotfix_name}...")
        self.run_command(
            ["git", "tag", "-a", f"hotfix-{hotfix_name}", "-m", f"Hotfix {hotfix_name}"]
        )

        # Push main and tags
        print("📤 Pushing main and tags to remote...")
        self.run_command(["git", "push", "origin", "main"])
        self.run_command(["git", "push", "origin", "--tags"])

        # Switch to develop and merge
        print("📥 Switching to develop branch...")
        self.run_command(["git", "checkout", "develop"])
        self.run_command(["git", "pull", "origin", "develop"])
        self.run_command(["git", "merge", hotfix_branch])

        # Push develop
        print("📤 Pushing develop to remote...")
        self.run_command(["git", "push", "origin", "develop"])

        # Delete hotfix branch
        print(f"🗑️ Deleting hotfix branch {hotfix_branch}...")
        self.run_command(["git", "branch", "-d", hotfix_branch])

        print(f"✅ Hotfix '{hotfix_name}' completed and merged to main and develop!")

    def show_status(self):
        """Show current GitFlow status"""
        current_branch = self.get_current_branch()
        print(f"📍 Current branch: {current_branch}")

        # Show recent commits
        print("\n📝 Recent commits:")
        self.run_command(["git", "log", "--oneline", "-5"], check=False)

        # Show branch status
        print("\n🌿 Branch status:")
        self.run_command(["git", "status", "--short"], check=False)


def main():
    parser = argparse.ArgumentParser(
        description="GitFlow Helper - Manage GitFlow branching strategy"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Feature commands
    feature_start = subparsers.add_parser(
        "feature-start", help="Start a new feature branch"
    )
    feature_start.add_argument("name", help="Feature name (e.g., user-auth)")

    feature_finish = subparsers.add_parser(
        "feature-finish", help="Finish a feature branch"
    )
    feature_finish.add_argument("name", help="Feature name (e.g., user-auth)")

    # Release commands
    release_start = subparsers.add_parser(
        "release-start", help="Start a new release branch"
    )
    release_start.add_argument("version", help="Release version (e.g., v1.0.0)")

    release_finish = subparsers.add_parser(
        "release-finish", help="Finish a release branch"
    )
    release_finish.add_argument("version", help="Release version (e.g., v1.0.0)")

    # Hotfix commands
    hotfix_start = subparsers.add_parser(
        "hotfix-start", help="Start a new hotfix branch"
    )
    hotfix_start.add_argument("name", help="Hotfix name (e.g., critical-bug)")

    hotfix_finish = subparsers.add_parser(
        "hotfix-finish", help="Finish a hotfix branch"
    )
    hotfix_finish.add_argument("name", help="Hotfix name (e.g., critical-bug)")

    # Status command
    subparsers.add_parser("status", help="Show current GitFlow status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    helper = GitFlowHelper()

    if args.command == "feature-start":
        helper.start_feature(args.name)
    elif args.command == "feature-finish":
        helper.finish_feature(args.name)
    elif args.command == "release-start":
        helper.start_release(args.version)
    elif args.command == "release-finish":
        helper.finish_release(args.version)
    elif args.command == "hotfix-start":
        helper.start_hotfix(args.name)
    elif args.command == "hotfix-finish":
        helper.finish_hotfix(args.name)
    elif args.command == "status":
        helper.show_status()


if __name__ == "__main__":
    main()
