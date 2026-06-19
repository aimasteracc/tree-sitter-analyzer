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

    def test_extract_key_value_shapes(self):
        """Test representative key-value scalar shapes in one parse."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(KEY_VALUE_CODE, plugin)
        elements = plugin.extractor.extract_yaml_elements(tree, KEY_VALUE_CODE)

        mapping_elements = [e for e in elements if e.element_type == "mapping"]
        assert len(mapping_elements) == 12

        by_key = {e.key: e for e in elements if e.key}
        name_element = next((e for e in elements if e.key == "name"), None)
        if name_element:
            assert name_element.value == "John Doe"
            assert name_element.value_type == "string"

        age_element = by_key.get("age")
        if age_element:
            assert age_element.value == "30"
            assert age_element.value_type == "number"

        salary_element = by_key.get("salary")
        if salary_element:
            assert "50000.50" in salary_element.value
            assert salary_element.value_type == "number"

        active_element = by_key.get("active")
        if active_element:
            assert active_element.value == "true"
            assert active_element.value_type == "boolean"

        verified_element = by_key.get("verified")
        if verified_element:
            assert verified_element.value == "false"
            assert verified_element.value_type == "boolean"

        middle_name_element = by_key.get("middle_name")
        if middle_name_element:
            assert middle_name_element.value in ["null", "~"]
            assert middle_name_element.value_type == "null"

        description_element = by_key.get("description")
        if description_element:
            assert "This is a quoted string" in description_element.value


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLListRecognition:
    """Test YAML list recognition and extraction."""

    def test_extract_list_shapes(self):
        """Test representative list shapes in one parse."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(LIST_CODE, plugin)
        elements = plugin.extractor.extract_yaml_elements(tree, LIST_CODE)

        sequence_elements = [e for e in elements if e.element_type == "sequence"]
        assert len(sequence_elements) == 8

        by_key = {e.key: e for e in elements if e.key}
        for key in ["fruits", "numbers", "users", "matrix", "colors"]:
            element = by_key.get(key)
            if element:
                assert element.value_type == "sequence"


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLNestedStructureRecognition:
    """Test YAML nested structure recognition and extraction."""

    def test_extract_nested_structure_shapes(self):
        """Test nested mapping structure and nesting levels in one parse."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(NESTED_STRUCTURE_CODE, plugin)
        elements = plugin.extractor.extract_yaml_elements(tree, NESTED_STRUCTURE_CODE)

        assert len(elements) == 28

        by_key = {e.key: e for e in elements if e.key}
        for key in ["person", "address", "config"]:
            element = by_key.get(key)
            if element:
                assert element.element_type == "mapping"

        nested_elements = [e for e in elements if e.nesting_level > 0]
        assert len(nested_elements) == 25


@pytest.mark.skipif(not YAML_AVAILABLE, reason="tree-sitter-yaml not installed")
class TestYAMLAnchorAliasRecognition:
    """Test YAML anchor and alias recognition and extraction."""

    def test_extract_anchor_alias_shapes(self):
        """Test anchors, aliases, merge keys, and list anchors in one parse."""
        plugin = YAMLPlugin()
        tree = get_tree_for_code(ANCHOR_ALIAS_CODE, plugin)
        elements = plugin.extractor.extract_yaml_elements(tree, ANCHOR_ALIAS_CODE)

        anchor_elements = [e for e in elements if e.element_type == "anchor"]
        assert len(anchor_elements) == 3

        alias_elements = [e for e in elements if e.element_type == "alias"]
        assert len(alias_elements) == 6

        defaults_element = next((e for e in elements if e.key == "defaults"), None)
        if defaults_element:
            assert defaults_element.anchor_name is not None

        alias_usage_elements = [e for e in elements if e.alias_target is not None]
        assert len(alias_usage_elements) == 6

        merge_elements = [e for e in elements if "<<" in str(e.raw_text)]
        assert len(merge_elements) == 13
