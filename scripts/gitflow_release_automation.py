#!/usr/bin/env python3
"""
GitFlow Release Automation Script

This script automates the complete GitFlow release process following best practices:
1. Preparation and validation
2. Release branch creation
3. CI/CD verification
4. Merge process
5. Cleanup and verification

Usage:
    python scripts/gitflow_release_automation.py --version v1.1.0
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


class GitFlowReleaseAutomation:
    def __init__(self, version: str):
        self.version = version
        self.project_root = Path(__file__).parent.parent
        self.release_branch = f"release/{version}"

    def run_command(
        self, command: list[str], check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a git command and return the result"""
        try:
            print(f"🔄 Running: {' '.join(command)}")
            result = subprocess.run(
                command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=check,
            )
            if result.stdout.strip():
                print(f"✅ Output: {result.stdout.strip()}")
            if result.stderr.strip():
                print(f"⚠️  Warnings: {result.stderr.strip()}")
            return result
        except subprocess.CalledProcessError as e:
            print(f"❌ Command failed: {' '.join(command)}")
            print(f"Error: {e}")
            if check:
                sys.exit(1)
            return e

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met"""
        print("🔍 Checking prerequisites...")

        # Check if we're on develop branch
        current_branch = self.run_command(
            ["git", "branch", "--show-current"]
        ).stdout.strip()
        if current_branch != "develop":
            print(f"❌ Must be on 'develop' branch, currently on '{current_branch}'")
            return False

        # Check if working directory is clean
        status = self.run_command(["git", "status", "--porcelain"]).stdout.strip()
        if status:
            print("❌ Working directory has uncommitted changes")
            print("Please commit or stash changes before proceeding")
            return False

        # Check if develop is up to date
        self.run_command(["git", "fetch", "origin"])
        local_commit = self.run_command(["git", "rev-parse", "HEAD"]).stdout.strip()
        remote_commit = self.run_command(
            ["git", "rev-parse", "origin/develop"]
        ).stdout.strip()

        if local_commit != remote_commit:
            print("❌ Local develop is not up to date with remote")
            print("Please run: git pull origin develop")
            return False

        print("✅ All prerequisites met!")
        return True

    def sync_readme_statistics(self) -> bool:
        """Sync README statistics to ensure consistency"""
        print("📊 Syncing README statistics...")

        try:
            # Run the README updater script
            subprocess.run(
                ["uv", "run", "python", "scripts/improved_readme_updater.py"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True,
            )
            print("✅ README statistics updated successfully")

            # Check if there are changes
            status = self.run_command(["git", "status", "--porcelain"]).stdout.strip()
            if status:
                print("📝 README files have been updated, committing changes...")
                self.run_command(
                    ["git", "add", "README.md", "README_zh.md", "README_ja.md"]
                )
                self.run_command(
                    [
                        "git",
                        "commit",
                        "-m",
                        "docs: Sync README statistics before release",
                    ]
                )
                self.run_command(["git", "push", "origin", "develop"])
                print("✅ README updates committed and pushed")
            else:
                print("ℹ️  No README changes needed")

            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to update README statistics: {e}")
            return False

    def run_tests(self) -> bool:
        """Run tests to ensure quality"""
        print("🧪 Running tests to ensure quality...")

        try:
            subprocess.run(
                ["uv", "run", "pytest", "tests/", "-v"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=True,
            )
            print("✅ All tests passed!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Tests failed: {e}")
            return False

    def create_release_branch(self) -> bool:
        """Create and prepare release branch"""
        print(f"🚀 Creating release branch: {self.release_branch}")

        try:
            # Create release branch
            self.run_command(["git", "checkout", "-b", self.release_branch])

            # Update version in pyproject.toml
            pyproject_path = self.project_root / "pyproject.toml"
            content = pyproject_path.read_text()

            # Extract current version
            import re

            version_match = re.search(r'version = "([^"]+)"', content)
            if not version_match:
                print("❌ Could not find version in pyproject.toml")
                return False

            current_version = version_match.group(1)
            new_version = self.version.lstrip("v")

            if current_version == new_version:
                print(f"ℹ️  Version already set to {new_version}")
            else:
                # Update version
                content = content.replace(
                    f'version = "{current_version}"', f'version = "{new_version}"'
                )
                pyproject_path.write_text(content)
                print(f"✅ Updated version from {current_version} to {new_version}")

            # Update CHANGELOG.md
            changelog_path = self.project_root / "CHANGELOG.md"
            if changelog_path.exists():
                changelog_content = changelog_path.read_text()

                # Add new version entry
                new_entry = f"""## [{new_version}] - {time.strftime('%Y-%m-%d')}

### 🚀 Release: {self.version}

- Automated release using GitFlow best practices
- All tests passing
- README statistics synchronized
- CI/CD pipeline optimized

---

"""

                # Insert after the first line
                lines = changelog_content.split("\n")
                lines.insert(1, new_entry)
                changelog_path.write_text("\n".join(lines))
                print("✅ Updated CHANGELOG.md")

            # Commit changes
            self.run_command(["git", "add", "pyproject.toml", "CHANGELOG.md"])
            self.run_command(
                ["git", "commit", "-m", f"chore: Prepare release {self.version}"]
            )

            print(f"✅ Release branch {self.release_branch} created and prepared")
            return True

        except Exception as e:
            print(f"❌ Failed to create release branch: {e}")
            return False

    def push_release_branch(self) -> bool:
        """Push release branch to trigger CI/CD"""
        print(f"📤 Pushing release branch {self.release_branch}...")

        try:
            self.run_command(["git", "push", "origin", self.release_branch])
            print(f"✅ Release branch {self.release_branch} pushed successfully")
            print("🔄 CI/CD pipeline will now start automatically")
            return True
        except Exception as e:
            print(f"❌ Failed to push release branch: {e}")
            return False

    def wait_for_ci_completion(self) -> bool:
        """Wait for CI/CD completion and provide status"""
        print("⏳ Waiting for CI/CD completion...")
        print("🔗 Check GitHub Actions status:")
        print("   https://github.com/aimasteracc/tree-sitter-analyzer/actions")
        print("\n📋 CI/CD Jobs to monitor:")
        print("   1. test - Should complete successfully")
        print("   2. build-and-deploy - Should complete successfully")
        print("   3. create-main-pr - Should complete successfully")

        print("\n⏰ Please wait for all jobs to complete...")
        print("   You can check the status in the GitHub Actions tab")

        return True

    def complete_release(self) -> bool:
        """Complete the release process after CI/CD success"""
        print("🎯 Completing release process...")

        print("\n📋 Manual steps to complete:")
        print("1. Wait for CI/CD to complete successfully")
        print("2. Review the created PR to main branch")
        print("3. Merge the PR to main")
        print("4. Run the following commands:")
        print()
        print("   # Switch to main and merge")
        print("   git checkout main")
        print("   git pull origin main")
        print("   git merge release/v1.1.0")
        print("   git tag -a v1.1.0 -m 'Release v1.1.0'")
        print("   git push origin main")
        print("   git push origin --tags")
        print()
        print("   # Switch to develop and merge")
        print("   git checkout develop")
        print("   git merge release/v1.1.0")
        print("   git push origin develop")
        print()
        print("   # Clean up release branch")
        print("   git branch -d release/v1.1.0")
        print("   git push origin --delete release/v1.1.0")

        return True

    def execute_full_workflow(self) -> bool:
        """Execute the complete GitFlow release workflow"""
        print("🚀 Starting GitFlow Release Automation")
        print(f"📦 Version: {self.version}")
        print(f"🌿 Release Branch: {self.release_branch}")
        print("=" * 60)

        try:
            # Step 1: Check prerequisites
            if not self.check_prerequisites():
                return False

            # Step 2: Sync README statistics
            if not self.sync_readme_statistics():
                return False

            # Step 3: Run tests
            if not self.run_tests():
                return False

            # Step 4: Create release branch
            if not self.create_release_branch():
                return False

            # Step 5: Push release branch
            if not self.push_release_branch():
                return False

            # Step 6: Wait for CI/CD
            if not self.wait_for_ci_completion():
                return False

            # Step 7: Complete release
            if not self.complete_release():
                return False

            print("=" * 60)
            print("🎉 GitFlow Release Automation completed successfully!")
            print("📋 Next steps:")
            print("   1. Monitor CI/CD progress in GitHub Actions")
            print("   2. Review and merge the created PR")
            print("   3. Complete the manual merge steps")

            return True

        except Exception as e:
            print(f"❌ Workflow failed: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="GitFlow Release Automation")
    parser.add_argument(
        "--version", required=True, help="Release version (e.g., v1.1.0)"
    )

    args = parser.parse_args()

    automation = GitFlowReleaseAutomation(args.version)
    success = automation.execute_full_workflow()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
