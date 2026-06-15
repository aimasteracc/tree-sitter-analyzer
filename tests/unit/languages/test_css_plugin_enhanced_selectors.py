"""Enhanced tests for CSS plugin — selectors, properties, rules, and media queries."""

from tree_sitter_analyzer.languages.css_plugin import CssPlugin

SELECTOR_CODE = """
/* Simple selectors */
body {
    margin: 0;
    padding: 0;
}

.class-selector {
    color: blue;
}

#id-selector {
    background: red;
}

/* Attribute selectors */
input[type="text"] {
    border: 1px solid #ccc;
}

a[href^="https"] {
    color: green;
}

/* Pseudo-classes */
a:hover {
    color: red;
}

input:focus {
    outline: none;
}

/* Pseudo-elements */
p::before {
    content: "→ ";
}

p::after {
    content: " ←";
}

/* Combinators */
div p {
    color: black;
}

div > p {
    color: blue;
}

div + p {
    color: green;
}

div ~ p {
    color: purple;
}
"""

PROPERTY_CODE = """
/* Layout properties */
.container {
    display: flex;
    position: relative;
    z-index: 10;
}

/* Typography properties */
.text {
    font-family: Arial, sans-serif;
    font-size: 16px;
    font-weight: bold;
    line-height: 1.5;
    color: #333;
    text-align: center;
}

/* Box model properties */
.box {
    margin: 10px 20px;
    padding: 15px;
    border: 1px solid #ccc;
    border-radius: 5px;
    width: 100%;
    height: 200px;
    max-width: 1200px;
    min-height: 100px;
}

/* Background properties */
.background {
    background: #f0f0f0;
    background-color: #fff;
    background-image: url('bg.png');
    background-position: center;
    background-repeat: no-repeat;
    background-size: cover;
}

/* Flexbox properties */
.flex {
    display: flex;
    flex-direction: row;
    justify-content: center;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}

/* Grid properties */
.grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    grid-template-rows: auto;
    gap: 20px;
}
"""

MEDIA_QUERY_CODE = """
/* Media queries */
@media screen and (max-width: 768px) {
    .container {
        padding: 10px;
    }

    h1 {
        font-size: 1.5em;
    }
}

@media screen and (min-width: 769px) and (max-width: 1024px) {
    .container {
        padding: 15px;
    }
}

@media print {
    body {
        background: white;
        color: black;
    }

    .no-print {
        display: none;
    }
}

@media (prefers-color-scheme: dark) {
    body {
        background: #333;
        color: #fff;
    }
}
"""

COMPLEX_STRUCTURE_CODE = """
/* Complex CSS structure */
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');

@layer base {
    * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
    }
}

@layer components {
    .btn {
        padding: 10px 20px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
    }

    .btn-primary {
        background: #007bff;
        color: white;
    }

    .btn-secondary {
        background: #6c757d;
        color: white;
    }
}

@layer utilities {
    .text-center {
        text-align: center;
    }

    .flex-center {
        display: flex;
        justify-content: center;
        align-items: center;
    }
}

.container {
    display: grid;
    grid-template-areas:
        "header header"
        "sidebar main"
        "footer footer";
    grid-template-columns: 250px 1fr;
    grid-template-rows: auto 1fr auto;
}

.header {
    grid-area: header;
}

.sidebar {
    grid-area: sidebar;
}

.main {
    grid-area: main;
}

.footer {
    grid-area: footer;
}

/* Complex selector */
.nav ul li a:not(.external):hover {
    color: #007bff;
    text-decoration: underline;
}

/* Multiple backgrounds */
.multi-bg {
    background:
        linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)),
        url('bg1.jpg'),
        url('bg2.jpg');
}

/* Complex box shadow */
.shadow {
    box-shadow:
        0 1px 3px rgba(0,0,0,0.12),
        0 1px 2px rgba(0,0,0,0.24),
        0 4px 6px rgba(0,0,0,0.1);
}
"""


def get_tree_for_code(code: str, plugin: CssPlugin):
    """Helper to parse CSS code and return tree."""
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


class TestCssSelectorRecognition:
    """Test CSS selector recognition and extraction."""

    def test_extract_simple_class_selector(self):
        """Test extraction of simple class selector."""
        plugin = CssPlugin()
        tree = get_tree_for_code(SELECTOR_CODE, plugin)
        extractor = plugin.create_extractor()
        elements = extractor.extract_css_rules(tree, SELECTOR_CODE)

        class_selectors = [e for e in elements if e.selector == ".class-selector"]
        assert len(class_selectors) == 1

    def test_extract_id_selector(self):
        """Test extraction of ID selector."""
        plugin = CssPlugin()
        tree = get_tree_for_code(SELECTOR_CODE, plugin)
        extractor = plugin.create_extractor()
        elements = extractor.extract_css_rules(tree, SELECTOR_CODE)

        id_selectors = [e for e in elements if e.selector == "#id-selector"]
        assert len(id_selectors) == 1

    def test_extract_element_selector(self):
        """Test extraction of element selector."""
        plugin = CssPlugin()
        tree = get_tree_for_code(SELECTOR_CODE, plugin)
        extractor = plugin.create_extractor()
        elements = extractor.extract_css_rules(tree, SELECTOR_CODE)

        element_selectors = [e for e in elements if e.selector == "body"]
        assert len(element_selectors) == 1

    def test_extract_attribute_selector(self):
        """Test extraction of attribute selector."""
        plugin = CssPlugin()
        tree = get_tree_for_code(SELECTOR_CODE, plugin)
        extractor = plugin.create_extractor()
        elements = extractor.extract_css_rules(tree, SELECTOR_CODE)

        # Match bracketed attribute selectors so prefix-match operators
        # ([href^=...]) count too — a literal 'href=' substring misses them
        attr_selectors = [
            e for e in elements if "[type=" in e.selector or "[href^=" in e.selector
        ]
        assert len(attr_selectors) == 2
        assert sorted(e.selector for e in attr_selectors) == [
            'a[href^="https"]',
            'input[type="text"]',
        ]

    def test_extract_pseudo_class_selector(self):
        """Test extraction of pseudo-class selector."""
        plugin = CssPlugin()
        tree = get_tree_for_code(SELECTOR_CODE, plugin)
        extractor = plugin.create_extractor()
        elements = extractor.extract_css_rules(tree, SELECTOR_CODE)

        pseudo_selectors = [
            e for e in elements if ":hover" in e.selector or ":focus" in e.selector
        ]
        assert len(pseudo_selectors) == 2

    def test_extract_pseudo_element_selector(self):
        """Test extraction of pseudo-element selector."""
        plugin = CssPlugin()
        tree = get_tree_for_code(SELECTOR_CODE, plugin)
        extractor = plugin.create_extractor()
        elements = extractor.extract_css_rules(tree, SELECTOR_CODE)

        pseudo_element_selectors = [
            e for e in elements if "::before" in e.selector or "::after" in e.selector
        ]
        assert len(pseudo_element_selectors) == 2

    def test_extract_combinator_selector(self):
        """Test extraction of combinator selector."""
        plugin = CssPlugin()
        tree = get_tree_for_code(SELECTOR_CODE, plugin)
        extractor = plugin.create_extractor()
        elements = extractor.extract_css_rules(tree, SELECTOR_CODE)

        combinator_selectors = [
            e
            for e in elements
            if " " in e.selector
            or ">" in e.selector
            or "+" in e.selector
            or "~" in e.selector
        ]
        assert len(combinator_selectors) == 4

    def test_selector_complexity(self):
        """Test that complex selectors are handled."""
        plugin = CssPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        extractor = plugin.create_extractor()
        elements = extractor.extract_css_rules(tree, COMPLEX_STRUCTURE_CODE)

        complex_selectors = [
            e for e in elements if ":" in e.selector and " " in e.selector
        ]
        assert len(complex_selectors) == 1


class TestCssPropertyRecognition:
    """Test CSS property recognition and extraction."""

    def test_extract_layout_properties(self):
        """Test extraction of layout properties."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        extractor = plugin.create_extractor()
        elements = extractor.extract_css_rules(tree, PROPERTY_CODE)

        layout_elements = [e for e in elements if e.element_class == "layout"]
        assert len(layout_elements) == 1

    def test_extract_typography_properties(self):
        """Test extraction of typography properties."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        extractor = plugin.create_extractor()
        elements = extractor.extract_css_rules(tree, PROPERTY_CODE)

        text_element = next((e for e in elements if e.selector == ".text"), None)
        if text_element:
            assert "font" in str(text_element.raw_text).lower()
            assert "color" in str(text_element.raw_text).lower()

    def test_extract_box_model_properties(self):
        """Test extraction of box model properties."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        box_element = next((e for e in elements if e.selector == ".box"), None)
        if box_element:
            assert "margin" in str(box_element.raw_text).lower()
            assert "padding" in str(box_element.raw_text).lower()
            assert "border" in str(box_element.raw_text).lower()

    def test_extract_background_properties(self):
        """Test extraction of background properties."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        bg_element = next((e for e in elements if e.selector == ".background"), None)
        if bg_element:
            assert "background" in str(bg_element.raw_text).lower()

    def test_extract_flexbox_properties(self):
        """Test extraction of flexbox properties."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        flex_element = next((e for e in elements if e.selector == ".flex"), None)
        if flex_element:
            assert "flex" in str(flex_element.raw_text).lower()

    def test_extract_grid_properties(self):
        """Test extraction of grid properties."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        grid_element = next((e for e in elements if e.selector == ".grid"), None)
        if grid_element:
            assert "grid" in str(grid_element.raw_text).lower()

    def test_property_values(self):
        """Test that property values are extracted."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        for element in elements:
            if element.properties:
                for prop_name, prop_value in element.properties.items():
                    assert prop_name is not None
                    assert prop_value is not None


class TestCssRuleRecognition:
    """Test CSS rule recognition and extraction."""

    def test_extract_simple_rule(self):
        """Test extraction of simple CSS rule."""
        plugin = CssPlugin()
        tree = get_tree_for_code(SELECTOR_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, SELECTOR_CODE)

        assert len(elements) == 13

    def test_extract_multiple_rules(self):
        """Test extraction of multiple CSS rules."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        assert len(elements) == 6

    def test_rule_selector(self):
        """Test that rule selector is captured."""
        plugin = CssPlugin()
        tree = get_tree_for_code(SELECTOR_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, SELECTOR_CODE)

        for element in elements:
            assert element.selector is not None
            assert element.selector != ""

    def test_rule_properties(self):
        """Test that rule properties are captured."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        assert sorted(len(e.properties) for e in elements if e.properties) == [
            3,
            4,
            6,
            6,
            6,
            8,
        ]

    def test_rule_line_numbers(self):
        """Test that rule line numbers are accurate."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        assert sorted(e.start_line for e in elements) == [3, 10, 20, 32, 42, 52]
        for element in elements:
            assert element.end_line >= element.start_line


class TestCssMediaQueryRecognition:
    """Test CSS media query recognition and extraction."""

    def test_extract_simple_media_query(self):
        """Test extraction of simple media query."""
        plugin = CssPlugin()
        tree = get_tree_for_code(MEDIA_QUERY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, MEDIA_QUERY_CODE)

        media_queries = [e for e in elements if e.selector.startswith("@media")]
        assert len(media_queries) == 4

    def test_extract_max_width_media_query(self):
        """Test extraction of max-width media query."""
        plugin = CssPlugin()
        tree = get_tree_for_code(MEDIA_QUERY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, MEDIA_QUERY_CODE)

        max_width_queries = [e for e in elements if "max-width" in e.selector]
        assert len(max_width_queries) == 2

    def test_extract_min_width_media_query(self):
        """Test extraction of min-width media query."""
        plugin = CssPlugin()
        tree = get_tree_for_code(MEDIA_QUERY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, MEDIA_QUERY_CODE)

        min_width_queries = [e for e in elements if "min-width" in e.selector]
        assert len(min_width_queries) == 1

    def test_extract_combined_media_query(self):
        """Test extraction of combined media query."""
        plugin = CssPlugin()
        tree = get_tree_for_code(MEDIA_QUERY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, MEDIA_QUERY_CODE)

        combined_queries = [e for e in elements if "and" in e.selector]
        assert len(combined_queries) == 2

    def test_extract_print_media_query(self):
        """Test extraction of print media query."""
        plugin = CssPlugin()
        tree = get_tree_for_code(MEDIA_QUERY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, MEDIA_QUERY_CODE)

        print_queries = [e for e in elements if "print" in e.selector]
        assert len(print_queries) == 2

    def test_extract_prefers_color_scheme_media_query(self):
        """Test extraction of prefers-color-scheme media query."""
        plugin = CssPlugin()
        tree = get_tree_for_code(MEDIA_QUERY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, MEDIA_QUERY_CODE)

        color_scheme_queries = [
            e for e in elements if "prefers-color-scheme" in e.selector
        ]
        assert len(color_scheme_queries) == 1
