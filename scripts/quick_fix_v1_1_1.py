#!/usr/bin/env python3
"""
Quick Fix Script for v1.1.1 Branch

This script quickly fixes the current issues in the v1.1.1 branch:
1. Updates README quality metrics
2. Commits and pushes changes
3. Prepares for v1.1.2 release
"""

import logging
import subprocess  # nosec B404
import sys
from pathlib import Path


class QuickFixV111:
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.project_root = Path(__file__).parent.parent
        self.dry_run = dry_run
        self.verbose = verbose

        # Setup logging
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
        self.logger = logging.getLogger(__name__)

    def check_current_branch(self) -> bool:
        """Check if we're on the correct branch"""
        try:
            result = subprocess.run(  # nosec B603
                ["git", "branch", "--show-current"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            current_branch = result.stdout.strip()
            self.logger.info(f"Current branch: {current_branch}")

            if current_branch == "release/v1.1.1":
                return True
            else:
                self.logger.warning(
                    f"Expected to be on release/v1.1.1, but on {current_branch}"
                )
                return False

        except Exception as e:
            self.logger.error(f"Failed to check current branch: {e}")
            return False

    def sync_readme_statistics(self) -> bool:
        """Sync README statistics"""
        try:
            self.logger.info("Syncing README statistics...")

            result = subprocess.run(  # nosec B603
                ["python", "scripts/improved_readme_updater.py"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                self.logger.info("README statistics synced successfully")
                return True
            else:
                self.logger.error(f"README sync failed: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to sync README statistics: {e}")
            return False

    def check_git_status(self) -> bool:
        """Check git status to see what changes need to be committed"""
        try:
            result = subprocess.run(  # nosec B603
                ["git", "status", "--porcelain"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.stdout.strip():
                self.logger.info("Changes detected:")
                for line in result.stdout.strip().split("\n"):
                    self.logger.info(f"  {line}")
                return True
            else:
                self.logger.info("No changes detected")
                return False

        except Exception as e:
            self.logger.error(f"Failed to check git status: {e}")
            return False

    def commit_changes(self) -> bool:
        """Commit all changes"""
        try:
            if self.dry_run:
                self.logger.info("Would commit changes")
                return True

            # Add all changes
            result = subprocess.run(  # nosec B603
                ["git", "add", "."],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                self.logger.error(f"Failed to add changes: {result.stderr}")
                return False

            # Commit changes
            result = subprocess.run(  # nosec B603
                [
                    "git",
                    "commit",
                    "-m",
                    "fix: Update README quality metrics for v1.1.1",
                ],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                self.logger.info("Changes committed successfully")
                return True
            else:
                self.logger.error(f"Failed to commit changes: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to commit changes: {e}")
            return False

    def push_changes(self) -> bool:
        """Push changes to remote"""
        try:
            if self.dry_run:
                self.logger.info("Would push changes")
                return True

            result = subprocess.run(  # nosec B603
                ["git", "push", "origin", "release/v1.1.1"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode == 0:
                self.logger.info("Changes pushed successfully")
                return True
            else:
                self.logger.error(f"Failed to push changes: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to push changes: {e}")
            return False

    def execute_quick_fix(self) -> bool:
        """Execute the complete quick fix process"""
        self.logger.info("Starting quick fix for v1.1.1 branch")

        # 1. Check current branch
        if not self.check_current_branch():
            self.logger.warning("Not on release/v1.1.1 branch, but continuing...")

        # 2. Sync README statistics
        if not self.sync_readme_statistics():
            self.logger.error("Failed to sync README statistics")
            return False

        # 3. Check git status
        has_changes = self.check_git_status()

        if has_changes:
            # 4. Commit changes
            if not self.commit_changes():
                self.logger.error("Failed to commit changes")
                return False

            # 5. Push changes
            if not self.push_changes():
                self.logger.error("Failed to push changes")
                return False
        else:
            self.logger.info("No changes to commit")

        self.logger.info("Quick fix completed successfully!")
        return True


def main():
    parser = argparse.ArgumentParser(description="Quick Fix for v1.1.1 Branch")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    fix = QuickFixV111(dry_run=args.dry_run, verbose=args.verbose)
    success = fix.execute_quick_fix()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    import argparse

    main()
