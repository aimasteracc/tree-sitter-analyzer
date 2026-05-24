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


_RECORDER_DEFINITION_TYPES: frozenset[str] = frozenset(
    {
        "create_table_statement",
        "create_view_statement",
        "create_procedure_statement",
        "create_function_statement",
        "create_trigger_statement",
        "create_index_statement",
    }
)


def _inspect_node_for_recorder(
    node: Any,
    attributes: set[str],
    element_count: int,
    has_error: bool,
) -> tuple[int, bool]:
    """Apply per-node accounting for the BehaviorRecorder cursor walk.

    Bumps ``element_count`` when the node looks like a top-level SQL
    definition; sets ``has_error`` for ``ERROR`` nodes; adds the column
    name to ``attributes`` for ``column_definition`` nodes (the set is
    mutated in place to keep the signature flat). Returns the updated
    ``(element_count, has_error)`` pair.

    r37dx (dogfood): extracted from ``BehaviorRecorder.record`` so the
    main cursor-walk loop drops from depth 6 to 3.
    """
    if node.type == "ERROR":
        has_error = True
    if node.type in _RECORDER_DEFINITION_TYPES:
        element_count += 1
    if node.type == "column_definition":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            attributes.add(f"col:{name_node.text.decode('utf8')}")
    return element_count, has_error


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
        attributes: set[str] = set()
        has_error = False

        # Traverse the tree
        cursor = node.walk()
        visited_children = False

        # r37dx (dogfood): node inspection抽到 _inspect_node_for_recorder
        # to flatten the cursor-walk loop from depth 6 to 3.
        while True:
            if not visited_children:
                element_count, has_error = _inspect_node_for_recorder(
                    cursor.node, attributes, element_count, has_error
                )
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
