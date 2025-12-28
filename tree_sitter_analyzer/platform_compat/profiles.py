import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import jsonschema
from cachetools import TTLCache

logger = logging.getLogger(__name__)

PROFILE_SCHEMA_VERSION = "1.0.0"


@dataclass
class ParsingBehavior:
    """Describes how a specific SQL construct parses on a platform."""

    construct_id: str
    node_type: str
    element_count: int
    attributes: list[str]
    has_error: bool
    known_issues: list[str] = field(default_factory=list)


@dataclass
class BehaviorProfile:
    """Complete behavior profile for a platform."""

    schema_version: str
    platform_key: str
    behaviors: dict[str, ParsingBehavior]
    adaptation_rules: list[str]

    def __post_init__(self) -> None:
        """Ensure behaviors are ParsingBehavior objects."""
        if self.behaviors:
            for key, value in self.behaviors.items():
                if isinstance(value, dict):
                    self.behaviors[key] = ParsingBehavior(**value)

    @classmethod
    def load(
        cls, platform_key: str, base_path: Path | None = None
    ) -> Optional["BehaviorProfile"]:
        """
        Loads a profile for the given platform key.

        Args:
            platform_key: The platform key (e.g. "windows-3.12").
            base_path: The base directory where profiles are stored.

        Returns:
            BehaviorProfile: The loaded profile, or None if not found.
        """
        if base_path is None:
            # Default to tests/platform_profiles relative to package root?
            # Or maybe we should require base_path.
            # For now, let's assume the caller provides it or we look in a standard location.
            # Let's try to find the package root.
            current_file = Path(__file__)
            # tree_sitter_analyzer/platform_compat/profiles.py -> tree_sitter_analyzer/ -> root
            package_root = current_file.parent.parent.parent
            base_path = package_root / "tests" / "platform_profiles"

        # We need to reconstruct the path from the key
        # key format: os-version
        try:
            parts = platform_key.split("-")
            os_name = parts[0]
            python_version = parts[1]
        except IndexError:
            logger.error(f"Invalid platform key format: {platform_key}")
            return None

        profile_path = base_path / os_name / python_version / "profile.json"

        if not profile_path.exists():
            logger.warning(f"Profile not found for {platform_key} at {profile_path}")
            return None

        try:
            with open(profile_path, encoding="utf-8") as f:
                data = json.load(f)

            validate_profile(data)
            data = migrate_profile_schema(data)

            # Convert behaviors dict to ParsingBehavior objects
            behaviors = {}
            for key, b_data in data.get("behaviors", {}).items():
                behaviors[key] = ParsingBehavior(**b_data)

            return cls(
                schema_version=data["schema_version"],
                platform_key=data["platform_key"],
                behaviors=behaviors,
                adaptation_rules=data.get("adaptation_rules", []),
            )
        except Exception as e:
            logger.error(f"Error loading profile for {platform_key}: {e}")
            return None

    def save(self, base_path: Path) -> None:
        """Saves the profile to disk."""
        parts = self.platform_key.split("-")
        os_name = parts[0]
        python_version = parts[1]

        profile_dir = base_path / os_name / python_version
        profile_dir.mkdir(parents=True, exist_ok=True)

        profile_path = profile_dir / "profile.json"

        data = asdict(self)

        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


# Schema definition
PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string"},
        "platform_key": {"type": "string"},
        "behaviors": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "construct_id": {"type": "string"},
                    "node_type": {"type": "string"},
                    "element_count": {"type": "integer"},
                    "attributes": {"type": "array", "items": {"type": "string"}},
                    "has_error": {"type": "boolean"},
                    "known_issues": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "construct_id",
                    "node_type",
                    "element_count",
                    "attributes",
                    "has_error",
                ],
            },
        },
        "adaptation_rules": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["schema_version", "platform_key", "behaviors", "adaptation_rules"],
}


def validate_profile(data: dict[str, Any]) -> None:
    """Validates profile data against the schema."""
    jsonschema.validate(instance=data, schema=PROFILE_SCHEMA)


def migrate_profile_schema(data: dict[str, Any]) -> dict[str, Any]:
    """Migrates profile data to the current schema version."""
    version = data.get("schema_version", "0.0.0")
    if version == PROFILE_SCHEMA_VERSION:
        return data

    if version == "0.0.0":
        return migrate_to_1_0_0(data)

    return data


def migrate_to_1_0_0(data: dict[str, Any]) -> dict[str, Any]:
    """Initial migration to 1.0.0."""
    data["schema_version"] = "1.0.0"
    if "behaviors" not in data:
        data["behaviors"] = {}
    if "adaptation_rules" not in data:
        data["adaptation_rules"] = []
    return data


class ProfileCache:
    """Thread-safe cache for behavior profiles."""

    def __init__(self, maxsize: int = 10, ttl: int = 3600):
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> BehaviorProfile | None:
        with self._lock:
            if key in self._cache:
                self._hits += 1
                return self._cache[key]  # type: ignore[no-any-return]
            self._misses += 1
            return None

    def put(self, key: str, profile: BehaviorProfile) -> None:
        with self._lock:
            self._cache[key] = profile

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    @property
    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache),
            }
