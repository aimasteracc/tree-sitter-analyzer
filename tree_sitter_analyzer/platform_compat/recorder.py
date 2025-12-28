import logging
from pathlib import Path
from typing import Any

import tree_sitter
import tree_sitter_sql

from tree_sitter_analyzer.platform_compat.detector import PlatformDetector
from tree_sitter_analyzer.platform_compat.fixtures import ALL_FIXTURES, SQLTestFixture
from tree_sitter_analyzer.platform_compat.profiles import (
    PROFILE_SCHEMA_VERSION,
    BehaviorProfile,
    ParsingBehavior,
)

logger = logging.getLogger(__name__)


class BehaviorRecorder:
    """Records SQL parsing behavior on the current platform."""

    def __init__(self) -> None:
        self.language = tree_sitter.Language(tree_sitter_sql.language())
        self.parser = tree_sitter.Parser(self.language)
        self.platform_info = PlatformDetector.detect()

    def record_all(self) -> BehaviorProfile:
        """
        Records behavior for all fixtures.

        Returns:
            BehaviorProfile: The recorded profile.
        """
        behaviors = {}

        for fixture in ALL_FIXTURES:
            behavior = self.record_fixture(fixture)
            behaviors[fixture.id] = behavior

        return BehaviorProfile(
            schema_version=PROFILE_SCHEMA_VERSION,
            platform_key=self.platform_info.platform_key,
            behaviors=behaviors,
            adaptation_rules=[],  # Rules are added manually or via analysis, not recording
        )

    def record_fixture(self, fixture: SQLTestFixture) -> ParsingBehavior:
        """
        Records behavior for a single fixture.

        Args:
            fixture: The fixture to record.

        Returns:
            ParsingBehavior: The recorded behavior.
        """
        tree = self.parser.parse(bytes(fixture.sql, "utf8"))
        root_node = tree.root_node

        # Analyze AST
        analysis = self.analyze_ast(root_node)

        return ParsingBehavior(
            construct_id=fixture.id,
            node_type=root_node.type,
            element_count=analysis["element_count"],
            attributes=analysis["attributes"],
            has_error=analysis["has_error"],
            known_issues=[],  # Populated by comparison or manual review
        )

    def analyze_ast(self, node: Any) -> dict[str, Any]:
        """
        Analyzes the AST to extract characteristics.

        Args:
            node: The root node of the AST.

        Returns:
            Dict containing analysis results.
        """
        element_count = 0
        attributes = set()
        has_error = False

        # Traverse the tree
        cursor = node.walk()
        visited_children = False

        while True:
            if not visited_children:
                # Process current node
                if cursor.node.type == "ERROR":
                    has_error = True

                # Count "interesting" elements (top-level statements usually)
                # This is a simplification; we might want to count specific types
                # based on the fixture expectation.
                # For now, let's count nodes that look like definitions.
                if cursor.node.type in {
                    "create_table_statement",
                    "create_view_statement",
                    "create_procedure_statement",
                    "create_function_statement",
                    "create_trigger_statement",
                    "create_index_statement",
                }:
                    element_count += 1

                # Collect attributes (field names)
                if cursor.node.type == "column_definition":
                    # Try to find column name
                    name_node = cursor.node.child_by_field_name("name")
                    if name_node:
                        attributes.add(f"col:{name_node.text.decode('utf8')}")

                # Check for specific attributes we care about
                # e.g. if it's a function, does it have parameters?

                if cursor.goto_first_child():
                    continue

            if cursor.goto_next_sibling():
                visited_children = False
                continue

            if cursor.goto_parent():
                visited_children = True
                continue

            break

        return {
            "element_count": element_count,
            "attributes": sorted(attributes),
            "has_error": has_error,
        }

    def save_profile(self, profile: BehaviorProfile, base_path: Path) -> None:
        """
        Saves the recorded profile to disk.

        Args:
            profile: The profile to save.
            base_path: The base directory.
        """
        profile.save(base_path)


if __name__ == "__main__":
    # Simple CLI for testing
    recorder = BehaviorRecorder()
    profile = recorder.record_all()
    print(f"Recorded profile for {profile.platform_key}")
    print(f"Behaviors: {len(profile.behaviors)}")
