#!/usr/bin/env python3
"""
Automated Release Management Script

This script manages the automated release process from develop to main branch,
including version management, PyPI deployment, and documentation updates.
"""

import argparse
import logging
import subprocess  # nosec B404
import sys
from pathlib import Path

import toml


class AutomatedRelease:
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.project_root = Path(__file__).parent.parent
        self.dry_run = dry_run
        self.verbose = verbose

        # Setup logging
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
        self.logger = logging.getLogger(__name__)

    def get_current_version(self) -> str:
        """Get current version from pyproject.toml"""
        pyproject_path = self.project_root / "pyproject.toml"
        with open(pyproject_path, encoding="utf-8") as f:
            data = toml.load(f)
        return data["project"]["version"]

    def update_version(self, new_version: str) -> bool:
        """Update version in pyproject.toml"""
        pyproject_path = self.project_root / "pyproject.toml"

        try:
            with open(pyproject_path, encoding="utf-8") as f:
                content = f.read()

            # Update version
            import re

            updated_content = re.sub(
                r'version = "([^"]+)"', f'version = "{new_version}"', content
            )

            if not self.dry_run:
                with open(pyproject_path, "w", encoding="utf-8") as f:
                    f.write(updated_content)
                self.logger.info(f"Updated version to {new_version}")
            else:
                self.logger.info(f"Would update version to {new_version} (dry-run)")

            return True
        except Exception as e:
            self.logger.error(f"Failed to update version: {e}")
            return False

    def run_tests(self) -> bool:
        """Run all tests"""
        try:
            cmd = ["uv", "run", "pytest", "tests/", "-v"]
            self.logger.info("Running tests...")

            if not self.dry_run:
                subprocess.run(cmd, cwd=self.project_root, check=True)  # nosec B603
                self.logger.info("All tests passed")
            else:
                self.logger.info("Would run tests (dry-run)")

            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Tests failed: {e}")
            return False

    def build_package(self) -> bool:
        """Build the package"""
        try:
            cmd = ["uv", "run", "python", "-m", "build"]
            self.logger.info("Building package...")

            if not self.dry_run:
                subprocess.run(cmd, cwd=self.project_root, check=True)  # nosec B603
                self.logger.info("Package built successfully")
            else:
                self.logger.info("Would build package (dry-run)")

            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Build failed: {e}")
            return False

    def deploy_to_pypi(self) -> bool:
        """Deploy to PyPI"""
        try:
            cmd = ["uv", "run", "twine", "upload", "dist/*"]
            self.logger.info("Deploying to PyPI...")

            if not self.dry_run:
                subprocess.run(cmd, cwd=self.project_root, check=True)  # nosec B603
                self.logger.info("Successfully deployed to PyPI")
            else:
                self.logger.info("Would deploy to PyPI (dry-run)")

            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"PyPI deployment failed: {e}")
            return False

    def update_readme_statistics(self) -> bool:
        """Update README statistics"""
        try:
            cmd = ["uv", "run", "python", "scripts/improved_readme_updater.py"]
            self.logger.info("Updating README statistics...")

            if not self.dry_run:
                subprocess.run(cmd, cwd=self.project_root, check=True)  # nosec B603
                self.logger.info("README statistics updated")
            else:
                self.logger.info("Would update README statistics (dry-run)")

            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"README update failed: {e}")
            return False

    def create_git_tag(self, version: str) -> bool:
        """Create git tag for release"""
        try:
            tag_name = f"v{version}"
            self.logger.info(f"Creating git tag: {tag_name}")

            if not self.dry_run:
                # Create tag
                subprocess.run(  # nosec B603, B607
                    ["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"],
                    cwd=self.project_root,
                    check=True,
                )
                # Push tag
                subprocess.run(  # nosec B603, B607
                    ["git", "push", "origin", tag_name],
                    cwd=self.project_root,
                    check=True,
                )
                self.logger.info(f"Git tag {tag_name} created and pushed")
            else:
                self.logger.info(f"Would create git tag {tag_name} (dry-run)")

            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Git tag creation failed: {e}")
            return False

    def create_github_release(self, version: str) -> bool:
        """Create GitHub release"""
        try:
            tag_name = f"v{version}"
            self.logger.info(f"Creating GitHub release for {tag_name}")

            if not self.dry_run:
                cmd = [
                    "gh",
                    "release",
                    "create",
                    tag_name,
                    "--title",
                    f"Release {tag_name}",
                    "--notes",
                    f"Automated release {tag_name} from develop branch",
                    "--target",
                    "main",
                ]
                subprocess.run(cmd, cwd=self.project_root, check=True)  # nosec B603
                self.logger.info(f"GitHub release {tag_name} created")
            else:
                self.logger.info(f"Would create GitHub release {tag_name} (dry-run)")

            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"GitHub release creation failed: {e}")
            return False

    def execute_release(self, new_version: str | None = None) -> bool:
        """Execute the complete release process"""
        self.logger.info("Starting automated release process...")

        # Get current version
        current_version = self.get_current_version()
        self.logger.info(f"Current version: {current_version}")

        # Update version if specified
        if new_version:
            if not self.update_version(new_version):
                return False

        # Run tests
        if not self.run_tests():
            return False

        # Build package
        if not self.build_package():
            return False

        # Deploy to PyPI
        if not self.deploy_to_pypi():
            return False

        # Update README statistics
        if not self.update_readme_statistics():
            return False

        # Create git tag
        release_version = new_version or current_version
        if not self.create_git_tag(release_version):
            return False

        # Create GitHub release
        if not self.create_github_release(release_version):
            return False

        self.logger.info("🎉 Release process completed successfully!")
        return True


def main():
    parser = argparse.ArgumentParser(description="Automated Release Management")
    parser.add_argument("--version", help="New version to release")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    release = AutomatedRelease(dry_run=args.dry_run, verbose=args.verbose)

    success = release.execute_release(args.version)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
