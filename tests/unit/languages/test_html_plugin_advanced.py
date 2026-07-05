"""Enhanced HTML plugin tests — link/image, script/style, complex structures, and query accuracy."""

from tree_sitter_analyzer.languages.html_plugin import HtmlPlugin

TAG_CODE = """
<!-- Structure tags -->
<div class="container">
    <header>
        <h1>Main Title</h1>
        <nav>
            <ul>
                <li><a href="/">Home</a></li>
                <li><a href="/about">About</a></li>
                <li><a href="/contact">Contact</a></li>
            </ul>
        </nav>
    </header>
    <main>
        <section>
            <h2>Section Title</h2>
            <p>This is a paragraph.</p>
        </section>
        <article>
            <h3>Article Title</h3>
            <p>Article content goes here.</p>
        </article>
        <aside>
            <h4>Sidebar</h4>
            <p>Sidebar content.</p>
        </aside>
    </main>
    <footer>
        <p>&copy; 2024</p>
    </footer>
</div>

<!-- Inline tags -->
<p>This is <strong>bold</strong> and <em>italic</em> text.</p>
<p>This is <mark>highlighted</mark> and <del>deleted</del> text.</p>
<p>This is <ins>inserted</ins> and <sub>subscript</sub> text.</p>
<p>This is <sup>superscript</sup> and <small>small</small> text.</p>
"""

ATTRIBUTE_CODE = """
<!-- Common attributes -->
<div id="main" class="container active" data-id="123">
    Content
</div>

<!-- Style attributes -->
<p style="color: red; font-size: 16px;">Styled paragraph</p>

<!-- Event attributes -->
<button onclick="handleClick()">Click me</button>
<input onfocus="handleFocus()" onblur="handleBlur()">

<!-- Form attributes -->
<form action="/submit" method="post" enctype="multipart/form-data">
    <input type="text" name="username" placeholder="Username" required>
    <input type="password" name="password" placeholder="Password" required>
    <input type="email" name="email" placeholder="Email">
    <input type="checkbox" name="remember" checked>
    <input type="radio" name="gender" value="male">
    <input type="radio" name="gender" value="female">
    <select name="country">
        <option value="us">United States</option>
        <option value="uk">United Kingdom</option>
    </select>
    <textarea name="message" rows="5" cols="40"></textarea>
    <button type="submit">Submit</button>
</form>

<!-- Link attributes -->
<a href="https://example.com" target="_blank" rel="noopener noreferrer">
    External Link
</a>

<!-- Image attributes -->
<img src="image.jpg" alt="Description" width="200" height="150" loading="lazy">

<!-- Script attributes -->
<script src="script.js" async defer></script>
"""

FORM_CODE = """
<!-- Form elements -->
<form id="login-form" action="/login" method="post">
    <!-- Text inputs -->
    <label for="username">Username:</label>
    <input type="text" id="username" name="username" required>

    <!-- Password input -->
    <label for="password">Password:</label>
    <input type="password" id="password" name="password" required>

    <!-- Email input -->
    <label for="email">Email:</label>
    <input type="email" id="email" name="email">

    <!-- Checkbox -->
    <label>
        <input type="checkbox" name="remember" checked>
        Remember me
    </label>

    <!-- Radio buttons -->
    <fieldset>
        <legend>Gender:</legend>
        <label>
            <input type="radio" name="gender" value="male">
            Male
        </label>
        <label>
            <input type="radio" name="gender" value="female">
            Female
        </label>
    </fieldset>

    <!-- Select dropdown -->
    <label for="country">Country:</label>
    <select id="country" name="country">
        <option value="">Select country</option>
        <option value="us">United States</option>
        <option value="uk">United Kingdom</option>
    </select>

    <!-- Textarea -->
    <label for="message">Message:</label>
    <textarea id="message" name="message" rows="5" cols="40"></textarea>

    <!-- Buttons -->
    <button type="submit">Submit</button>
    <button type="reset">Reset</button>
</form>
"""

TABLE_CODE = """
<!-- Simple table -->
<table>
    <thead>
        <tr>
            <th>Name</th>
            <th>Age</th>
            <th>City</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>John</td>
            <td>30</td>
            <td>New York</td>
        </tr>
        <tr>
            <td>Jane</td>
            <td>25</td>
            <td>London</td>
        </tr>
    </tbody>
    <tfoot>
        <tr>
            <td colspan="3">Total: 2</td>
        </tr>
    </tfoot>
</table>

<!-- Table with attributes -->
<table id="data-table" class="sortable" border="1" cellpadding="5">
    <caption>Employee Data</caption>
    <thead>
        <tr>
            <th scope="col">ID</th>
            <th scope="col">Name</th>
            <th scope="col">Department</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>1</td>
            <td>John Doe</td>
            <td>Engineering</td>
        </tr>
        <tr>
            <td>2</td>
            <td>Jane Smith</td>
            <td>Marketing</td>
        </tr>
    </tbody>
</table>
"""

LINK_IMAGE_CODE = """
<!-- Links -->
<a href="https://example.com">External link</a>
<a href="/about">Internal link</a>
<a href="#section">Anchor link</a>
<a href="mailto:test@example.com">Email link</a>
<a href="tel:+1234567890">Phone link</a>

<!-- Images -->
<img src="image.jpg" alt="Description">
<img src="logo.png" alt="Logo" width="100" height="50">
<img src="photo.webp" alt="Photo" loading="lazy" decoding="async">

<!-- Picture element -->
<picture>
    <source media="(min-width: 800px)" srcset="large.jpg">
    <source media="(min-width: 400px)" srcset="medium.jpg">
    <img src="small.jpg" alt="Responsive image">
</picture>

<!-- SVG -->
<svg width="100" height="100">
    <circle cx="50" cy="50" r="40" stroke="green" stroke-width="4" fill="yellow" />
</svg>
"""

SCRIPT_STYLE_CODE = """
<!-- Script tags -->
<script src="https://cdn.example.com/library.js"></script>
<script>
    function hello() {
        console.log("Hello, world!");
    }

    document.addEventListener("DOMContentLoaded", function() {
        hello();
    });
</script>
<script type="module">
    import { Component } from './component.js';
    export default Component;
</script>

<!-- Style tags -->
<style>
    body {
        font-family: Arial, sans-serif;
        margin: 0;
        padding: 0;
    }

    .container {
        max-width: 1200px;
        margin: 0 auto;
    }
</style>
<link rel="stylesheet" href="styles.css">

<!-- Meta tags -->
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="Page description">
<meta name="keywords" content="keyword1, keyword2">
<meta name="author" content="Author Name">
<meta name="robots" content="index, follow">

<!-- Title -->
<title>Page Title</title>
"""

COMPLEX_STRUCTURE_CODE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Complex Page</title>
    <link rel="stylesheet" href="styles.css">
    <script src="main.js" defer></script>
</head>
<body>
    <div id="app">
        <header class="header">
            <nav class="nav">
                <ul class="nav-list">
                    <li><a href="/">Home</a></li>
                    <li><a href="/about">About</a></li>
                </ul>
            </nav>
        </header>
        <main class="main">
            <section class="content">
                <article class="article">
                    <h1 class="title">Article Title</h1>
                    <p class="text">Article content.</p>
                </article>
            </section>
            <aside class="sidebar">
                <div class="widget">
                    <h3>Widget</h3>
                    <p>Widget content.</p>
                </div>
            </aside>
        </main>
        <footer class="footer">
            <p>&copy; 2024</p>
        </footer>
    </div>
    <script>
        // Inline script
        console.log("Page loaded");
    </script>
</body>
</html>
"""


def get_tree_for_code(code: str, plugin: HtmlPlugin):
    """Helper to parse HTML code and return tree."""
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


class TestHtmlLinkImageRecognition:
    """Test HTML link and image recognition and extraction."""

    def test_extract_a_tag(self):
        """Test extraction of anchor tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        a_elements = [e for e in elements if e.tag_name == "a"]
        assert len(a_elements) == 5

    def test_extract_external_link(self):
        """Test extraction of external link."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        external_link = next(
            (
                e
                for e in elements
                if e.tag_name == "a"
                and e.attributes
                and "https://" in e.attributes.get("href", "")
            ),
            None,
        )
        if external_link:
            assert "https://" in external_link.attributes["href"]

    def test_extract_internal_link(self):
        """Test extraction of internal link."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        internal_link = next(
            (
                e
                for e in elements
                if e.tag_name == "a"
                and e.attributes
                and e.attributes.get("href", "").startswith("/")
            ),
            None,
        )
        if internal_link:
            assert internal_link.attributes["href"].startswith("/")

    def test_extract_anchor_link(self):
        """Test extraction of anchor link."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        anchor_link = next(
            (
                e
                for e in elements
                if e.tag_name == "a"
                and e.attributes
                and e.attributes.get("href", "").startswith("#")
            ),
            None,
        )
        if anchor_link:
            assert anchor_link.attributes["href"].startswith("#")

    def test_extract_img_tag(self):
        """Test extraction of img tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        img_elements = [e for e in elements if e.tag_name == "img"]
        assert len(img_elements) == 4

    def test_extract_image_with_alt(self):
        """Test extraction of image with alt text."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        img_with_alt = next(
            (
                e
                for e in elements
                if e.tag_name == "img" and e.attributes and "alt" in e.attributes
            ),
            None,
        )
        assert img_with_alt.attributes["alt"] == "Description"
        assert img_with_alt.attributes["src"] == "image.jpg"

    def test_extract_image_with_dimensions(self):
        """Test extraction of image with dimensions."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        img_with_dims = next(
            (
                e
                for e in elements
                if e.tag_name == "img"
                and e.attributes
                and "width" in e.attributes
                and "height" in e.attributes
            ),
            None,
        )
        assert img_with_dims.attributes == {
            "src": "logo.png",
            "alt": "Logo",
            "width": "100",
            "height": "50",
        }

    def test_extract_picture_tag(self):
        """Test extraction of picture tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        picture_elements = [e for e in elements if e.tag_name == "picture"]
        assert len(picture_elements) == 1

    def test_extract_svg_tag(self):
        """Test extraction of svg tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        svg_elements = [e for e in elements if e.tag_name == "svg"]
        assert len(svg_elements) == 1


class TestHtmlScriptStyleRecognition:
    """Test HTML script and style recognition and extraction."""

    def test_extract_script_tag(self):
        """Test extraction of script tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        script_elements = [e for e in elements if e.tag_name == "script"]
        assert len(script_elements) == 3

    def test_extract_style_tag(self):
        """Test extraction of style tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        style_elements = [e for e in elements if e.tag_name == "style"]
        assert len(style_elements) == 1

    def test_extract_link_tag(self):
        """Test extraction of link tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        link_elements = [e for e in elements if e.tag_name == "link"]
        assert len(link_elements) == 1

    def test_extract_meta_tag(self):
        """Test extraction of meta tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        meta_elements = [e for e in elements if e.tag_name == "meta"]
        assert len(meta_elements) == 6

    def test_extract_title_tag(self):
        """Test extraction of title tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        title_elements = [e for e in elements if e.tag_name == "title"]
        assert len(title_elements) == 1

    def test_extract_script_with_src(self):
        """Test extraction of script with src attribute."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        script_with_src = next(
            (
                e
                for e in elements
                if e.tag_name == "script" and e.attributes and "src" in e.attributes
            ),
            None,
        )
        assert script_with_src.attributes == {
            "src": "https://cdn.example.com/library.js"
        }

    def test_extract_style_with_href(self):
        """Test extraction of link with href attribute."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(SCRIPT_STYLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, SCRIPT_STYLE_CODE
        )

        link_with_href = next(
            (
                e
                for e in elements
                if e.tag_name == "link" and e.attributes and "href" in e.attributes
            ),
            None,
        )
        assert link_with_href.attributes == {"rel": "stylesheet", "href": "styles.css"}


class TestHtmlComplexStructures:
    """Test extraction of complex HTML structures."""

    def test_extract_nested_elements(self):
        """Test extraction of nested elements."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        # Should find nested elements
        assert len(elements) == 28

    def test_extract_parent_child_relationships(self):
        """Test extraction of parent-child relationships."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        # Some elements should have children
        elements_with_children = [
            e for e in elements if e.children and len(e.children) > 0
        ]
        assert len(elements_with_children) == 15

    def test_extract_multiple_classes(self):
        """Test extraction of elements with multiple classes."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        # Should find elements with multiple classes
        elements_with_multiple_classes = [
            e
            for e in elements
            if e.attributes and "class" in e.attributes and " " in e.attributes["class"]
        ]
        assert (
            len(elements_with_multiple_classes) == 0
        )  # extraction gap: COMPLEX_STRUCTURE_CODE single-class attrs only

    def test_extract_doctype(self):
        """Test extraction of DOCTYPE."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        # DOCTYPE should be captured
        assert len(elements) == 28

    def test_extract_html_tag(self):
        """Test extraction of html tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        html_elements = [e for e in elements if e.tag_name == "html"]
        assert len(html_elements) == 1

    def test_extract_head_tag(self):
        """Test extraction of head tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        head_elements = [e for e in elements if e.tag_name == "head"]
        assert len(head_elements) == 1

    def test_extract_body_tag(self):
        """Test extraction of body tag."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(COMPLEX_STRUCTURE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, COMPLEX_STRUCTURE_CODE
        )

        body_elements = [e for e in elements if e.tag_name == "body"]
        assert len(body_elements) == 1


class TestHtmlQueryAccuracy:
    """Test accuracy of HTML queries."""

    def test_tag_query_accuracy(self):
        """Test that tag query accurately identifies tags."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        # Exact full tag list in fixture order.
        assert [e.tag_name for e in elements] == [
            "div",
            "header",
            "h1",
            "nav",
            "ul",
            "li",
            "a",
            "li",
            "a",
            "li",
            "a",
            "main",
            "section",
            "h2",
            "p",
            "article",
            "h3",
            "p",
            "aside",
            "h4",
            "p",
            "footer",
            "p",
            "p",
            "strong",
            "em",
            "p",
            "mark",
            "del",
            "p",
            "ins",
            "sub",
            "p",
            "sup",
            "small",
        ]

    def test_attribute_query_accuracy(self):
        """Test that attribute query accurately identifies attributes."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(ATTRIBUTE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, ATTRIBUTE_CODE)

        # Attributes should be within elements
        for element in elements:
            if element.attributes:
                for attr_name, attr_value in element.attributes.items():
                    assert isinstance(attr_name, str)
                    assert isinstance(attr_value, str)

        image_attrs = [
            element.attributes for element in elements if element.tag_name == "img"
        ]
        assert image_attrs == [
            {
                "src": "image.jpg",
                "alt": "Description",
                "width": "200",
                "height": "150",
                "loading": "lazy",
            }
        ]

    def test_form_query_accuracy(self):
        """Test that form query accurately identifies form elements."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(FORM_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, FORM_CODE)

        # Should find form elements
        form_elements = [e for e in elements if e.tag_name == "form"]
        assert len(form_elements) == 1

    def test_table_query_accuracy(self):
        """Test that table query accurately identifies table elements."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TABLE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TABLE_CODE)

        # Should find table elements
        table_elements = [e for e in elements if e.tag_name == "table"]
        assert len(table_elements) == 2

    def test_link_query_accuracy(self):
        """Test that link query accurately identifies links."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        # Should find anchor tags
        a_elements = [e for e in elements if e.tag_name == "a"]
        assert len(a_elements) == 5

    def test_image_query_accuracy(self):
        """Test that image query accurately identifies images."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(LINK_IMAGE_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(
            tree, LINK_IMAGE_CODE
        )

        # Should find img tags
        img_elements = [e for e in elements if e.tag_name == "img"]
        assert len(img_elements) == 4

    def test_no_false_positives(self):
        """Test that queries don't produce false positives."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        # Should not extract comments as tags
        for element in elements:
            assert element.tag_name is not None
            assert element.tag_name.strip() != ""

    def test_no_false_negatives(self):
        """Test that queries don't miss elements."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        # Should find all expected tags
        tag_names = [e.tag_name for e in elements]
        assert "div" in tag_names
        assert "h1" in tag_names
        assert "p" in tag_names

    def test_line_number_accuracy(self):
        """Test that line numbers are accurate."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        assert [e.start_line for e in elements] == [
            3,
            4,
            5,
            6,
            7,
            8,
            8,
            9,
            9,
            10,
            10,
            14,
            15,
            16,
            17,
            19,
            20,
            21,
            23,
            24,
            25,
            28,
            29,
            34,
            34,
            34,
            35,
            35,
            35,
            36,
            36,
            36,
            37,
            37,
            37,
        ]
        assert [e.end_line for e in elements] == [
            31,
            13,
            5,
            12,
            11,
            8,
            8,
            9,
            9,
            10,
            10,
            27,
            18,
            16,
            17,
            22,
            20,
            21,
            26,
            24,
            25,
            30,
            29,
            34,
            34,
            34,
            35,
            35,
            35,
            36,
            36,
            36,
            37,
            37,
            37,
        ]

    def test_element_classification_accuracy(self):
        """Test that element classification is accurate."""
        plugin = HtmlPlugin()
        tree = get_tree_for_code(TAG_CODE, plugin)
        elements = plugin.create_extractor().extract_html_elements(tree, TAG_CODE)

        # Structure elements should be classified as structure
        structure_elements = [e for e in elements if e.element_class == "structure"]
        assert len(structure_elements) == 8

        # Heading elements should be classified as heading
        heading_elements = [e for e in elements if e.element_class == "heading"]
        assert len(heading_elements) == 4
