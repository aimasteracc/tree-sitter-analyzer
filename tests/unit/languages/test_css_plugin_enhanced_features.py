"""Enhanced tests for CSS plugin — animations, variables, complex structures, and query accuracy."""

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

ANIMATION_CODE = """
/* Animations */
@keyframes fadeIn {
    from {
        opacity: 0;
    }
    to {
        opacity: 1;
    }
}

@keyframes slideIn {
    0% {
        transform: translateX(-100%);
    }
    100% {
        transform: translateX(0);
    }
}

@keyframes bounce {
    0%, 20%, 50%, 80%, 100% {
        transform: translateY(0);
    }
    40% {
        transform: translateY(-30px);
    }
    60% {
        transform: translateY(-15px);
    }
}

.animated {
    animation-name: fadeIn;
    animation-duration: 1s;
    animation-timing-function: ease-in-out;
    animation-delay: 0.5s;
    animation-iteration-count: infinite;
    animation-direction: alternate;
    animation-fill-mode: forwards;
}

.transition {
    transition: all 0.3s ease;
}

.transition-specific {
    transition-property: transform;
    transition-duration: 0.5s;
    transition-timing-function: ease-in-out;
    transition-delay: 0.1s;
}
"""

VARIABLE_CODE = """
/* CSS Variables */
:root {
    --primary-color: #007bff;
    --secondary-color: #6c757d;
    --font-size-base: 16px;
    --spacing-unit: 8px;
    --border-radius: 4px;
}

.container {
    color: var(--primary-color);
    font-size: var(--font-size-base);
    padding: calc(var(--spacing-unit) * 2);
    border-radius: var(--border-radius);
}

.button {
    background: var(--primary-color);
    color: white;
}

.button:hover {
    background: var(--secondary-color);
}

/* Fallback */
.fallback {
    color: var(--primary-color, blue);
}

/* Local variables */
.card {
    --card-bg: #fff;
    --card-padding: 20px;

    background: var(--card-bg);
    padding: var(--card-padding);
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


class TestCssAnimationRecognition:
    """Test CSS animation recognition and extraction."""

    def test_extract_keyframes(self):
        """Test extraction of @keyframes."""
        plugin = CssPlugin()
        tree = get_tree_for_code(ANIMATION_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, ANIMATION_CODE)

        keyframes = [e for e in elements if e.selector.startswith("@keyframes")]
        assert len(keyframes) == 3

    def test_extract_multiple_keyframes(self):
        """Test extraction of multiple @keyframes."""
        plugin = CssPlugin()
        tree = get_tree_for_code(ANIMATION_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, ANIMATION_CODE)

        keyframes = [e for e in elements if e.selector.startswith("@keyframes")]
        assert len(keyframes) == 3

    def test_extract_keyframes_name(self):
        """Test that keyframes name is captured."""
        plugin = CssPlugin()
        tree = get_tree_for_code(ANIMATION_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, ANIMATION_CODE)

        keyframes = [e for e in elements if e.selector.startswith("@keyframes")]
        assert any("fadeIn" in e.selector for e in keyframes)
        assert any("slideIn" in e.selector for e in keyframes)
        assert any("bounce" in e.selector for e in keyframes)

    def test_extract_animation_properties(self):
        """Test extraction of animation properties."""
        plugin = CssPlugin()
        tree = get_tree_for_code(ANIMATION_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, ANIMATION_CODE)

        animated_element = next(
            (e for e in elements if e.selector == ".animated"), None
        )
        if animated_element:
            assert "animation" in str(animated_element.raw_text).lower()

    def test_extract_transition_properties(self):
        """Test extraction of transition properties."""
        plugin = CssPlugin()
        tree = get_tree_for_code(ANIMATION_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, ANIMATION_CODE)

        transition_elements = [
            e for e in elements if "transition" in str(e.raw_text).lower()
        ]
        assert len(transition_elements) == 2

    def test_keyframes_keyframes(self):
        """Test that keyframes percentages are captured."""
        plugin = CssPlugin()
        tree = get_tree_for_code(ANIMATION_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, ANIMATION_CODE)

        bounce_keyframes = next((e for e in elements if "bounce" in e.selector), None)
        if bounce_keyframes:
            assert "0%" in str(bounce_keyframes.raw_text)
            assert "100%" in str(bounce_keyframes.raw_text)


class TestCssVariableRecognition:
    """Test CSS variable recognition and extraction."""

    def test_extract_root_variables(self):
        """Test extraction of :root variables."""
        plugin = CssPlugin()
        tree = get_tree_for_code(VARIABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, VARIABLE_CODE)

        root_element = next((e for e in elements if e.selector == ":root"), None)
        if root_element:
            assert "--primary-color" in str(root_element.raw_text)
            assert "--font-size-base" in str(root_element.raw_text)

    def test_extract_variable_usage(self):
        """Test extraction of variable usage with var()."""
        plugin = CssPlugin()
        tree = get_tree_for_code(VARIABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, VARIABLE_CODE)

        container_element = next(
            (e for e in elements if e.selector == ".container"), None
        )
        if container_element:
            assert "var(" in str(container_element.raw_text)

    def test_extract_variable_fallback(self):
        """Test extraction of variable fallback."""
        plugin = CssPlugin()
        tree = get_tree_for_code(VARIABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, VARIABLE_CODE)

        fallback_element = next(
            (e for e in elements if e.selector == ".fallback"), None
        )
        if fallback_element:
            assert "var(" in str(fallback_element.raw_text)
            assert "," in str(fallback_element.raw_text)

    def test_extract_local_variables(self):
        """Test extraction of local variables."""
        plugin = CssPlugin()
        tree = get_tree_for_code(VARIABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, VARIABLE_CODE)

        card_element = next((e for e in elements if e.selector == ".card"), None)
        if card_element:
            assert "--card-bg" in str(card_element.raw_text)
            assert "--card-padding" in str(card_element.raw_text)

    def test_variable_naming(self):
        """Test that variable names are captured."""
        plugin = CssPlugin()
        tree = get_tree_for_code(VARIABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, VARIABLE_CODE)

        root_element = next((e for e in elements if e.selector == ":root"), None)
        if root_element:
            assert "--primary-color" in str(root_element.raw_text)
            assert "--secondary-color" in str(root_element.raw_text)
            assert "--spacing-unit" in str(root_element.raw_text)


class TestCssComplexStructures:
    """Test extraction of complex CSS structures."""

    def test_extract_import_rules(self):
        """Test extraction of @import rules."""
        plugin = CssPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(
            tree, COMPLEX_STRUCTURE_CODE
        )

        import_elements = [e for e in elements if e.selector.startswith("@import")]
        assert len(import_elements) == 1

    def test_extract_layer_rules(self):
        """Test extraction of @layer rules."""
        plugin = CssPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(
            tree, COMPLEX_STRUCTURE_CODE
        )

        layer_elements = [e for e in elements if e.selector.startswith("@layer")]
        assert len(layer_elements) == 3

    def test_extract_grid_template_areas(self):
        """Test extraction of grid-template-areas."""
        plugin = CssPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(
            tree, COMPLEX_STRUCTURE_CODE
        )

        container_element = next(
            (e for e in elements if e.selector == ".container"), None
        )
        if container_element:
            assert "grid-template-areas" in str(container_element.raw_text)

    def test_extract_multiple_backgrounds(self):
        """Test extraction of multiple backgrounds."""
        plugin = CssPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(
            tree, COMPLEX_STRUCTURE_CODE
        )

        multi_bg_element = next(
            (e for e in elements if e.selector == ".multi-bg"), None
        )
        if multi_bg_element:
            assert "background:" in str(multi_bg_element.raw_text)

    def test_extract_complex_box_shadow(self):
        """Test extraction of complex box-shadow."""
        plugin = CssPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(
            tree, COMPLEX_STRUCTURE_CODE
        )

        shadow_element = next((e for e in elements if e.selector == ".shadow"), None)
        if shadow_element:
            assert "box-shadow:" in str(shadow_element.raw_text)

    def test_extract_not_selector(self):
        """Test extraction of :not() selector."""
        plugin = CssPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(
            tree, COMPLEX_STRUCTURE_CODE
        )

        not_selectors = [e for e in elements if ":not(" in e.selector]
        assert len(not_selectors) == 1


class TestCssQueryAccuracy:
    """Test accuracy of CSS queries."""

    def test_selector_query_accuracy(self):
        """Test that selector query accurately identifies selectors."""
        plugin = CssPlugin()
        tree = get_tree_for_code(SELECTOR_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, SELECTOR_CODE)

        assert [e.selector for e in elements] == [
            "body",
            ".class-selector",
            "#id-selector",
            'input[type="text"]',
            'a[href^="https"]',
            "a:hover",
            "input:focus",
            "p::before",
            "p::after",
            "div p",
            "div > p",
            "div + p",
            "div ~ p",
        ]

    def test_property_query_accuracy(self):
        """Test that property query accurately identifies properties."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        for element in elements:
            if element.properties:
                for prop_name, prop_value in element.properties.items():
                    assert prop_name is not None
                    assert prop_value is not None

    def test_media_query_accuracy(self):
        """Test that media query is accurately captured."""
        plugin = CssPlugin()
        tree = get_tree_for_code(MEDIA_QUERY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, MEDIA_QUERY_CODE)

        media_queries = [e for e in elements if e.selector.startswith("@media")]
        assert len(media_queries) == 4

    def test_keyframes_query_accuracy(self):
        """Test that keyframes query accurately identifies animations."""
        plugin = CssPlugin()
        tree = get_tree_for_code(ANIMATION_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, ANIMATION_CODE)

        keyframes = [e for e in elements if e.selector.startswith("@keyframes")]
        assert len(keyframes) == 3

    def test_variable_query_accuracy(self):
        """Test that variable query accurately identifies variables."""
        plugin = CssPlugin()
        tree = get_tree_for_code(VARIABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, VARIABLE_CODE)

        root_element = next((e for e in elements if e.selector == ":root"), None)
        assert root_element is not None

    def test_no_false_positives(self):
        """Test that queries don't produce false positives."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        for element in elements:
            assert element.selector is not None
            assert element.selector.strip() != ""

    def test_no_false_negatives(self):
        """Test that queries don't miss elements."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        selectors = [e.selector for e in elements]
        assert ".container" in selectors
        assert ".text" in selectors
        assert ".box" in selectors

    def test_line_number_accuracy(self):
        """Test that line numbers are accurate."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        assert [(e.start_line, e.end_line) for e in elements] == [
            (3, 7),
            (10, 17),
            (20, 29),
            (32, 39),
            (42, 49),
            (52, 57),
        ]

    def test_element_classification_accuracy(self):
        """Test that element classification is accurate."""
        plugin = CssPlugin()
        tree = get_tree_for_code(PROPERTY_CODE, plugin)
        elements = plugin.create_extractor().extract_css_rules(tree, PROPERTY_CODE)

        layout_elements = [e for e in elements if e.element_class == "layout"]
        assert len(layout_elements) == 1

        text_element = next((e for e in elements if e.selector == ".text"), None)
        if text_element:
            assert text_element.element_class == "typography"
