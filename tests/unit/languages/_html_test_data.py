"""Shared HTML test data constants."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
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


