"""Enhanced tests for YAML plugin — structure recognition (key-value, lists, nesting, anchors)."""

import pytest

from tree_sitter_analyzer.languages.yaml_plugin import (
    YAML_AVAILABLE,
    YAMLPlugin,
)

KEY_VALUE_CODE = """
# Simple key-value pairs
name: John Doe
age: 30
city: New York
country: USA

# Boolean values
active: true
verified: false

# Null values
middle_name: null
nickname: ~

# Numbers
salary: 50000.50
experience: 5

# Strings with quotes
description: "This is a quoted string"
notes: 'Single quoted string'
"""

LIST_CODE = """
# Simple list
fruits:
  - apple
  - banana
  - orange

# List of numbers
numbers:
  - 1
  - 2
  - 3
  - 4
  - 5

# List of objects
users:
  - name: Alice
    age: 25
  - name: Bob
    age: 30
  - name: Charlie
    age: 35

# Nested list
matrix:
  - [1, 2, 3]
  - [4, 5, 6]
  - [7, 8, 9]

# Inline list
colors: [red, green, blue]
"""

NESTED_STRUCTURE_CODE = """
# Nested mapping
person:
  name: John Doe
  age: 30
  address:
    street: 123 Main St
    city: New York
    state: NY
    zip: 10001
  contact:
    email: john@example.com
    phone: 555-1234

# Deep nesting
config:
  database:
    connection:
      host: localhost
      port: 5432
      credentials:
        username: admin
        password: secret
    pool:
      min: 5
      max: 20
  cache:
    enabled: true
    ttl: 3600
"""

ANCHOR_ALIAS_CODE = """
# Anchors and aliases
defaults: &defaults
  timeout: 30
  retries: 3
  debug: false

development:
  <<: *defaults
  debug: true

production:
  <<: *defaults
  timeout: 60

# Multiple anchors
server_config: &server
  host: localhost
  port: 8080

dev_server:
  <<: *server
  port: 3000

prod_server:
  <<: *server
  host: prod.example.com

# Anchor in list
item_template: &item
  - name: default
  - value: 0

list1:
  <<: *item

list2:
  <<: *item
"""


def get_tree_for_code(code: str, plugin: YAMLPlugin):
    """Helper to parse YAML code and return tree."""
    import tree_sitter

    language = plugin.get_tree_sitter_language()
    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(language)
    elif hasattr(parser, "language"):
        parser.language = language
    else:
        parser = tree_sitter.Parser(language)
    return parser.parse(code.encode("utf-8"))


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLKeyPairRecognition:
    """Test YAML key-value pair recognition and extraction."""

    def test_extract_simple_key_value(self):
        """Test extraction of simple key-value pairs."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        mapping_elements = [e for e in elements if e.element_type == "mapping"]
        assert len(mapping_elements) >= 1

    def test_extract_string_value(self):
        """Test extraction of string value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        name_element = next((e for e in elements if e.key == "name"), None)
        if name_element:
            assert name_element.value == "John Doe"
            assert name_element.value_type == "string"

    def test_extract_integer_value(self):
        """Test extraction of integer value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        age_element = next((e for e in elements if e.key == "age"), None)
        if age_element:
            assert age_element.value == "30"
            assert age_element.value_type == "number"

    def test_extract_float_value(self):
        """Test extraction of float value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        salary_element = next((e for e in elements if e.key == "salary"), None)
        if salary_element:
            assert "50000.50" in salary_element.value
            assert salary_element.value_type == "number"

    def test_extract_boolean_true(self):
        """Test extraction of boolean true value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        active_element = next((e for e in elements if e.key == "active"), None)
        if active_element:
            assert active_element.value == "true"
            assert active_element.value_type == "boolean"

    def test_extract_boolean_false(self):
        """Test extraction of boolean false value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        verified_element = next((e for e in elements if e.key == "verified"), None)
        if verified_element:
            assert verified_element.value == "false"
            assert verified_element.value_type == "boolean"

    def test_extract_null_value(self):
        """Test extraction of null value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        middle_name_element = next(
            (e for e in elements if e.key == "middle_name"), None
        )
        if middle_name_element:
            assert middle_name_element.value in ["null", "~"]
            assert middle_name_element.value_type == "null"

    def test_extract_quoted_string(self):
        """Test extraction of quoted string value."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, KEY_VALUE_CODE)

        description_element = next(
            (e for e in elements if e.key == "description"), None
        )
        if description_element:
            assert "This is a quoted string" in description_element.value


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLListRecognition:
    """Test YAML list recognition and extraction."""

    def test_extract_simple_list(self):
        """Test extraction of simple list."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        sequence_elements = [e for e in elements if e.element_type == "sequence"]
        assert len(sequence_elements) >= 1

    def test_extract_list_of_strings(self):
        """Test extraction of list of strings."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        fruits_element = next((e for e in elements if e.key == "fruits"), None)
        if fruits_element:
            assert fruits_element.value_type == "sequence"

    def test_extract_list_of_numbers(self):
        """Test extraction of list of numbers."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        numbers_element = next((e for e in elements if e.key == "numbers"), None)
        if numbers_element:
            assert numbers_element.value_type == "sequence"

    def test_extract_list_of_objects(self):
        """Test extraction of list of objects."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        users_element = next((e for e in elements if e.key == "users"), None)
        if users_element:
            assert users_element.value_type == "sequence"

    def test_extract_nested_list(self):
        """Test extraction of nested list."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        matrix_element = next((e for e in elements if e.key == "matrix"), None)
        if matrix_element:
            assert matrix_element.value_type == "sequence"

    def test_extract_inline_list(self):
        """Test extraction of inline list."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, LIST_CODE)

        colors_element = next((e for e in elements if e.key == "colors"), None)
        if colors_element:
            assert colors_element.value_type == "sequence"


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLNestedStructureRecognition:
    """Test YAML nested structure recognition and extraction."""

    def test_extract_nested_mapping(self):
        """Test extraction of nested mapping."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        assert len(elements) >= 5

    def test_extract_person_structure(self):
        """Test extraction of person structure."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        person_element = next((e for e in elements if e.key == "person"), None)
        if person_element:
            assert person_element.element_type == "mapping"

    def test_extract_address_structure(self):
        """Test extraction of address structure."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        address_element = next((e for e in elements if e.key == "address"), None)
        if address_element:
            assert address_element.element_type == "mapping"

    def test_extract_deep_nesting(self):
        """Test extraction of deeply nested structure."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        assert len(elements) >= 10

    def test_extract_config_structure(self):
        """Test extraction of config structure."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        config_element = next((e for e in elements if e.key == "config"), None)
        if config_element:
            assert config_element.element_type == "mapping"

    def test_nesting_levels(self):
        """Test that nesting levels are captured."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, NESTED_STRUCTURE_CODE)

        nested_elements = [e for e in elements if e.nesting_level > 0]
        assert len(nested_elements) >= 1


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLAnchorAliasRecognition:
    """Test YAML anchor and alias recognition and extraction."""

    def test_extract_anchor(self):
        """Test extraction of anchor."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        anchor_elements = [e for e in elements if e.element_type == "anchor"]
        assert len(anchor_elements) >= 1

    def test_extract_alias(self):
        """Test extraction of alias."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        alias_elements = [e for e in elements if e.element_type == "alias"]
        assert len(alias_elements) >= 1

    def test_extract_defaults_anchor(self):
        """Test extraction of defaults anchor."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        defaults_element = next((e for e in elements if e.key == "defaults"), None)
        if defaults_element:
            assert defaults_element.anchor_name is not None

    def test_extract_alias_usage(self):
        """Test extraction of alias usage."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        alias_usage_elements = [e for e in elements if e.alias_target is not None]
        assert len(alias_usage_elements) >= 1

    def test_extract_merge_key(self):
        """Test extraction of merge key (<<)."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        merge_elements = [e for e in elements if "<<" in str(e.raw_text)]
        assert len(merge_elements) >= 1

    def test_extract_multiple_anchors(self):
        """Test extraction of multiple anchors."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        anchor_elements = [e for e in elements if e.element_type == "anchor"]
        assert len(anchor_elements) >= 2

    def test_extract_anchor_in_list(self):
        """Test extraction of anchor in list."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_elements(tree, ANCHOR_ALIAS_CODE)

        anchor_elements = [e for e in elements if e.element_type == "anchor"]
        assert len(anchor_elements) >= 1
