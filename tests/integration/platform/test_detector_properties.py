import sys
from unittest.mock import MagicMock, patch

from hypothesis import given
from hypothesis import strategies as st

from tree_sitter_analyzer.platform_compat.detector import PlatformDetector, PlatformInfo


@st.composite
def platform_config(draw):
    """Generates random platform configurations."""
    os_name = draw(st.sampled_from(["Windows", "Linux", "Darwin", "Java"]))
    os_version = draw(st.text(min_size=1))
    major = draw(st.integers(min_value=3, max_value=4))
    minor = draw(st.integers(min_value=8, max_value=13))
    return os_name, os_version, major, minor


class TestPlatformDetectorProperties:
    @given(platform_config())
    def test_platform_detection_accuracy(self, config):
        """
        Property 2: Platform detection accuracy
        Validates: Requirements 4.1
        """
        os_name, os_version, major, minor = config

        # Mock system values
        with (
            patch("platform.system", return_value=os_name),
            patch("platform.release", return_value=os_version),
            patch.object(sys, "version_info", MagicMock(major=major, minor=minor)),
        ):
            info = PlatformDetector.detect()

            # Verify OS name normalization
            expected_os = "macos" if os_name == "Darwin" else os_name.lower()
            assert info.os_name == expected_os

            # Verify version
            assert info.os_version == os_version
            assert info.python_version == f"{major}.{minor}"

            # Verify key construction
            assert info.platform_key == f"{expected_os}-{major}.{minor}"

            # Verify types
            assert isinstance(info, PlatformInfo)
            assert isinstance(info.os_name, str)
            assert isinstance(info.platform_key, str)

    @given(platform_config())
    def test_get_profile_path(self, config):
        """Test profile path resolution."""
        os_name, os_version, major, minor = config

        with (
            patch("platform.system", return_value=os_name),
            patch("platform.release", return_value=os_version),
            patch.object(sys, "version_info", MagicMock(major=major, minor=minor)),
        ):
            from pathlib import Path

            base_path = Path("/tmp/profiles")

            # Test with explicit info
            info = PlatformDetector.detect()
            path = PlatformDetector.get_profile_path(base_path, info)

            expected_os = "macos" if os_name == "Darwin" else os_name.lower()
            expected_path = (
                base_path / expected_os / f"{major}.{minor}" / "profile.json"
            )

            assert path == expected_path

            # Test with implicit detection
            path_implicit = PlatformDetector.get_profile_path(base_path)
            assert path_implicit == expected_path
