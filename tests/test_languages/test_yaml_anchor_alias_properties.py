#!/usr/bin/env python3
"""
Property-based tests for YAML anchor and alias detection.

Feature: yaml-language-support
Tests correctness properties for YAML anchor and alias detection to ensure:
- All anchors (&name) are identified with correct names
- All aliases (*name) are identified with correct target names
- Anchor and alias names match correctly
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tree_sitter_analyzer.languages.yaml_plugin import (
    YAML_AVAILABLE,
    YAMLElementExtractor,
)

# Skip all tests if YAML is not available
pytestmark = pytest.mark.skipif(
    not YAML_AVAILABLE, reason="tree-sitter-yaml not installed"
)


# Strategies for generating valid anchor/alias names
@st.composite
def valid_anchor_name(draw):
    """Generate valid YAML anchor names."""
    # YAML anchor names can contain alphanumeric characters, underscores, and hyphens
    first_char = draw(
        st.characters(
            whitelist_categories=("Lu", "Ll"),
            min_codepoint=97,
            max_codepoint=122,
        )
    )
    rest = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                min_codepoint=48,
                max_codepoint=122,
            ).filter(lambda c: c.isalnum() or c in "_-"),
            min_size=0,
            max_size=15,
        )
    )
    return first_char + rest


@st.composite
def yaml_with_anchor_and_alias(draw):
    """Generate YAML content with anchors and aliases."""
    anchor_name = draw(valid_anchor_name())

    # Generate a simple value for the anchor
    value = draw(
        st.one_of(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd"),
                    min_codepoint=97,
                    max_codepoint=122,
                ),
                min_size=1,
                max_size=20,
            ),
            st.integers(min_value=0, max_value=1000).map(str),
            st.sampled_from(["true", "false"]),
        )
    )

    # Create YAML with anchor and alias
    yaml_content = f"""
anchor_def: &{anchor_name} {value}
alias_use: *{anchor_name}
"""
    return yaml_content.strip(), anchor_name


@st.composite
def yaml_with_multiple_anchors(draw):
    """Generate YAML content with multiple anchors and aliases."""
    num_anchors = draw(st.integers(min_value=1, max_value=5))
    anchors = []
    lines = []

    for i in range(num_anchors):
        # Use index to ensure uniqueness
        anchor_name = f"anchor{i}"
        anchors.append(anchor_name)

        value = draw(
            st.one_of(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Lu", "Ll", "Nd"),
                        min_codepoint=97,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=15,
                ),
                st.integers(min_value=0, max_value=100).map(str),
            )
        )

        lines.append(f"key{i}: &{anchor_name} {value}")

    # Add some aliases
    for anchor_name in anchors:
        lines.append(f"ref_{anchor_name}: *{anchor_name}")

    return "\n".join(lines), anchors


@st.composite
def yaml_with_nested_anchor(draw):
    """Generate YAML content with nested structures containing anchors."""
    anchor_name = draw(valid_anchor_name())

    # Create nested structure with anchor
    key1 = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=10,
        )
    )
    key2 = draw(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=10,
        )
    )
    value = draw(st.integers(min_value=0, max_value=100))

    yaml_content = f"""
config: &{anchor_name}
  {key1}: {value}
  {key2}: test
reference: *{anchor_name}
"""
    return yaml_content.strip(), anchor_name


class TestYAMLAnchorAliasProperties:
    """Property-based tests for YAML anchor and alias detection."""

    @settings(max_examples=100)
    @given(yaml_data=yaml_with_anchor_and_alias())
    def test_property_6_anchor_detection(self, yaml_data: tuple[str, str]):
        """
        Feature: yaml-language-support, Property 6: Anchor and Alias Detection

        For any YAML file containing anchors (&name), the extractor SHALL identify
        all anchors with their correct names.

        Validates: Requirements 2.2
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        yaml_content, expected_anchor_name = yaml_data

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Property: Anchors must be extracted
        anchors = [e for e in elements if e.element_type == "anchor"]

        assert len(anchors) >= 1, (
            f"Expected at least 1 anchor, got {len(anchors)}. "
            f"Content:\n{yaml_content}"
        )

        # Property: Anchor must have correct name
        anchor_names = [a.anchor_name for a in anchors]
        assert expected_anchor_name in anchor_names, (
            f"Expected anchor name '{expected_anchor_name}' not found. "
            f"Found: {anchor_names}. "
            f"Content:\n{yaml_content}"
        )

        # Property: Anchor element must have anchor_name attribute
        for anchor in anchors:
            assert (
                anchor.anchor_name is not None
            ), f"Anchor at line {anchor.start_line} must have anchor_name attribute"
            assert (
                len(anchor.anchor_name) > 0
            ), f"Anchor name at line {anchor.start_line} must not be empty"

        # Property: Anchor element_type must be "anchor"
        for anchor in anchors:
            assert anchor.element_type == "anchor", (
                f"Anchor at line {anchor.start_line} must have element_type 'anchor', "
                f"got '{anchor.element_type}'"
            )

        # Property: Anchor name should match the name in raw_text
        for anchor in anchors:
            assert (
                f"&{anchor.anchor_name}" in anchor.raw_text
                or anchor.anchor_name in anchor.raw_text
            ), f"Anchor name '{anchor.anchor_name}' should appear in raw_text '{anchor.raw_text}'"

    @settings(max_examples=100)
    @given(yaml_data=yaml_with_anchor_and_alias())
    def test_property_6_alias_detection(self, yaml_data: tuple[str, str]):
        """
        Feature: yaml-language-support, Property 6: Anchor and Alias Detection

        For any YAML file containing aliases (*name), the extractor SHALL identify
        all aliases with their correct target names.

        Validates: Requirements 2.2
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        yaml_content, expected_target_name = yaml_data

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Property: Aliases must be extracted
        aliases = [e for e in elements if e.element_type == "alias"]

        assert len(aliases) >= 1, (
            f"Expected at least 1 alias, got {len(aliases)}. "
            f"Content:\n{yaml_content}"
        )

        # Property: Alias must have correct target name
        alias_targets = [a.alias_target for a in aliases]
        assert expected_target_name in alias_targets, (
            f"Expected alias target '{expected_target_name}' not found. "
            f"Found: {alias_targets}. "
            f"Content:\n{yaml_content}"
        )

        # Property: Alias element must have alias_target attribute
        for alias in aliases:
            assert (
                alias.alias_target is not None
            ), f"Alias at line {alias.start_line} must have alias_target attribute"
            assert (
                len(alias.alias_target) > 0
            ), f"Alias target at line {alias.start_line} must not be empty"

        # Property: Alias element_type must be "alias"
        for alias in aliases:
            assert alias.element_type == "alias", (
                f"Alias at line {alias.start_line} must have element_type 'alias', "
                f"got '{alias.element_type}'"
            )

        # Property: Alias target should match the name in raw_text
        for alias in aliases:
            assert (
                f"*{alias.alias_target}" in alias.raw_text
                or alias.alias_target in alias.raw_text
            ), f"Alias target '{alias.alias_target}' should appear in raw_text '{alias.raw_text}'"

    @settings(max_examples=100)
    @given(yaml_data=yaml_with_anchor_and_alias())
    def test_property_6_anchor_alias_correspondence(self, yaml_data: tuple[str, str]):
        """
        Feature: yaml-language-support, Property 6: Anchor and Alias Detection

        For any YAML file containing both anchors and aliases, the alias target
        SHALL match the anchor name.

        Validates: Requirements 2.2
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        yaml_content, expected_name = yaml_data

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Get anchors and aliases
        anchors = [e for e in elements if e.element_type == "anchor"]
        aliases = [e for e in elements if e.element_type == "alias"]

        # Property: If both anchors and aliases exist, they should correspond
        if anchors and aliases:
            anchor_names = {a.anchor_name for a in anchors}
            alias_targets = {a.alias_target for a in aliases}

            # Property: All alias targets should reference existing anchors
            for alias_target in alias_targets:
                assert alias_target in anchor_names, (
                    f"Alias target '{alias_target}' does not match any anchor name. "
                    f"Anchor names: {anchor_names}. "
                    f"Content:\n{yaml_content}"
                )

    @settings(max_examples=50)
    @given(yaml_data=yaml_with_multiple_anchors())
    def test_property_6_multiple_anchors_detection(
        self, yaml_data: tuple[str, list[str]]
    ):
        """
        Feature: yaml-language-support, Property 6: Anchor and Alias Detection

        For any YAML file containing multiple anchors, the extractor SHALL identify
        all anchors with their unique names.

        Validates: Requirements 2.2
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        yaml_content, expected_anchor_names = yaml_data

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Get anchors
        anchors = [e for e in elements if e.element_type == "anchor"]

        # Property: Number of anchors should match expected count
        assert len(anchors) == len(expected_anchor_names), (
            f"Expected {len(expected_anchor_names)} anchors, got {len(anchors)}. "
            f"Expected: {expected_anchor_names}. "
            f"Found: {[a.anchor_name for a in anchors]}. "
            f"Content:\n{yaml_content}"
        )

        # Property: All expected anchor names should be found
        found_anchor_names = {a.anchor_name for a in anchors}
        expected_set = set(expected_anchor_names)

        assert found_anchor_names == expected_set, (
            f"Anchor names mismatch. "
            f"Expected: {expected_set}. "
            f"Found: {found_anchor_names}. "
            f"Content:\n{yaml_content}"
        )

        # Property: Anchor names should be unique
        anchor_name_list = [a.anchor_name for a in anchors]
        assert len(anchor_name_list) == len(
            set(anchor_name_list)
        ), f"Duplicate anchor names found: {anchor_name_list}"

    @settings(max_examples=50)
    @given(yaml_data=yaml_with_multiple_anchors())
    def test_property_6_multiple_aliases_detection(
        self, yaml_data: tuple[str, list[str]]
    ):
        """
        Feature: yaml-language-support, Property 6: Anchor and Alias Detection

        For any YAML file containing multiple aliases, the extractor SHALL identify
        all aliases with their correct target names.

        Validates: Requirements 2.2
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        yaml_content, expected_anchor_names = yaml_data

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Get aliases
        aliases = [e for e in elements if e.element_type == "alias"]

        # Property: Number of aliases should match number of anchors
        assert len(aliases) == len(expected_anchor_names), (
            f"Expected {len(expected_anchor_names)} aliases, got {len(aliases)}. "
            f"Content:\n{yaml_content}"
        )

        # Property: All alias targets should match anchor names
        alias_targets = {a.alias_target for a in aliases}
        expected_set = set(expected_anchor_names)

        assert alias_targets == expected_set, (
            f"Alias targets mismatch. "
            f"Expected: {expected_set}. "
            f"Found: {alias_targets}. "
            f"Content:\n{yaml_content}"
        )

    @settings(max_examples=50)
    @given(yaml_data=yaml_with_nested_anchor())
    def test_property_6_nested_anchor_detection(self, yaml_data: tuple[str, str]):
        """
        Feature: yaml-language-support, Property 6: Anchor and Alias Detection

        For any YAML file containing anchors in nested structures, the extractor
        SHALL identify anchors with correct names and nesting levels.

        Validates: Requirements 2.2
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        yaml_content, expected_anchor_name = yaml_data

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Get anchors
        anchors = [e for e in elements if e.element_type == "anchor"]

        # Property: Anchor must be found
        assert len(anchors) >= 1, (
            f"Expected at least 1 anchor, got {len(anchors)}. "
            f"Content:\n{yaml_content}"
        )

        # Property: Anchor name must match expected
        anchor_names = [a.anchor_name for a in anchors]
        assert expected_anchor_name in anchor_names, (
            f"Expected anchor name '{expected_anchor_name}' not found. "
            f"Found: {anchor_names}"
        )

        # Property: Anchor must have valid nesting_level
        for anchor in anchors:
            assert hasattr(
                anchor, "nesting_level"
            ), f"Anchor at line {anchor.start_line} must have nesting_level attribute"
            assert isinstance(
                anchor.nesting_level, int
            ), f"nesting_level must be int, got {type(anchor.nesting_level)}"
            assert (
                anchor.nesting_level >= 0
            ), f"nesting_level must be non-negative, got {anchor.nesting_level}"

        # Property: Anchor must have valid line numbers
        for anchor in anchors:
            assert (
                anchor.start_line > 0
            ), f"Anchor start_line must be positive, got {anchor.start_line}"
            assert (
                anchor.end_line >= anchor.start_line
            ), "Anchor end_line must be >= start_line"

    @settings(max_examples=100)
    @given(
        anchor_name=valid_anchor_name(),
        value=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=20,
        ),
    )
    def test_property_6_anchor_name_extraction_accuracy(
        self, anchor_name: str, value: str
    ):
        """
        Feature: yaml-language-support, Property 6: Anchor and Alias Detection

        For any valid anchor name, the extractor SHALL extract the exact anchor
        name without the & prefix.

        Validates: Requirements 2.2
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        # Create YAML with anchor
        yaml_content = f"key: &{anchor_name} {value}"

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Get anchors
        anchors = [e for e in elements if e.element_type == "anchor"]

        # Property: Exactly one anchor should be found
        assert len(anchors) == 1, (
            f"Expected exactly 1 anchor, got {len(anchors)}. "
            f"Content: {yaml_content}"
        )

        # Property: Anchor name must match exactly (without &)
        extracted_anchor = anchors[0]
        assert extracted_anchor.anchor_name == anchor_name, (
            f"Anchor name mismatch. "
            f"Expected: '{anchor_name}'. "
            f"Got: '{extracted_anchor.anchor_name}'. "
            f"Content: {yaml_content}"
        )

        # Property: Anchor name should not contain & prefix
        assert not extracted_anchor.anchor_name.startswith("&"), (
            f"Anchor name should not contain & prefix. "
            f"Got: '{extracted_anchor.anchor_name}'"
        )

    @settings(max_examples=100)
    @given(
        anchor_name=valid_anchor_name(),
        value=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=20,
        ),
    )
    def test_property_6_alias_target_extraction_accuracy(
        self, anchor_name: str, value: str
    ):
        """
        Feature: yaml-language-support, Property 6: Anchor and Alias Detection

        For any valid alias reference, the extractor SHALL extract the exact target
        name without the * prefix.

        Validates: Requirements 2.2
        """
        try:
            import tree_sitter
            import tree_sitter_yaml as ts_yaml
        except ImportError:
            pytest.skip("tree-sitter-yaml not available")

        # Create YAML with anchor and alias
        yaml_content = f"""
anchor: &{anchor_name} {value}
alias: *{anchor_name}
"""

        # Parse the YAML content
        YAML_LANGUAGE = tree_sitter.Language(ts_yaml.language())
        parser = tree_sitter.Parser()
        parser.language = YAML_LANGUAGE
        tree = parser.parse(yaml_content.encode("utf-8"))

        # Extract elements
        extractor = YAMLElementExtractor()
        elements = extractor.extract_yaml_elements(tree, yaml_content)

        # Get aliases
        aliases = [e for e in elements if e.element_type == "alias"]

        # Property: Exactly one alias should be found
        assert len(aliases) == 1, (
            f"Expected exactly 1 alias, got {len(aliases)}. " f"Content: {yaml_content}"
        )

        # Property: Alias target must match anchor name exactly (without *)
        extracted_alias = aliases[0]
        assert extracted_alias.alias_target == anchor_name, (
            f"Alias target mismatch. "
            f"Expected: '{anchor_name}'. "
            f"Got: '{extracted_alias.alias_target}'. "
            f"Content: {yaml_content}"
        )

        # Property: Alias target should not contain * prefix
        assert not extracted_alias.alias_target.startswith("*"), (
            f"Alias target should not contain * prefix. "
            f"Got: '{extracted_alias.alias_target}'"
        )
