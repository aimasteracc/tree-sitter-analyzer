import platform
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlatformInfo:
    """Platform identification information."""

    os_name: str
    os_version: str
    python_version: str
    platform_key: str


class PlatformDetector:
    """Detects current platform and Python version."""

    @staticmethod
    def detect() -> PlatformInfo:
        """
        Detects the current platform information.

        Returns:
            PlatformInfo: The detected platform information.
        """
        os_name = platform.system().lower()
        os_version = platform.release()
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

        # Normalize os_name
        if os_name == "darwin":
            os_name = "macos"

        platform_key = f"{os_name}-{python_version}"

        return PlatformInfo(
            os_name=os_name,
            os_version=os_version,
            python_version=python_version,
            platform_key=platform_key,
        )

    @staticmethod
    def get_profile_path(
        base_path: Path, platform_info: PlatformInfo | None = None
    ) -> Path:
        """
        Resolves the path to the profile file for the given platform.

        Args:
            base_path: The base directory where profiles are stored.
            platform_info: The platform info to use. If None, detects current platform.

        Returns:
            Path: The path to the profile file.
        """
        if platform_info is None:
            platform_info = PlatformDetector.detect()

        return (
            base_path
            / platform_info.os_name
            / platform_info.python_version
            / "profile.json"
        )
