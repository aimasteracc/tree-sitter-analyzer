#!/usr/bin/env python3
"""
Language Detector HTML/CSS Tests

Test cases for HTML and CSS language detection functionality.
"""

import pytest
from tree_sitter_analyzer.language_detector import LanguageDetector, detect_language_from_file


class TestHtmlCssLanguageDetection:
    """Test HTML and CSS language detection"""

    def setup_method(self):
        """Set up test fixtures"""
        self.detector = LanguageDetector()

    def test_html_extension_detection(self):
        """Test HTML file extension detection"""
        # Test .html extension
        language, confidence = self.detector.detect_language("index.html")
        assert language == "html"
        assert confidence == 0.9

        # Test .htm extension
        language, confidence = self.detector.detect_language("page.htm")
        assert language == "html"
        assert confidence == 0.9

        # Test .xhtml extension
        language, confidence = self.detector.detect_language("document.xhtml")
        assert language == "html"
        assert confidence == 0.8

    def test_css_extension_detection(self):
        """Test CSS file extension detection"""
        # Test .css extension
        language, confidence = self.detector.detect_language("styles.css")
        assert language == "css"
        assert confidence == 0.9

        # Test .scss extension
        language, confidence = self.detector.detect_language("styles.scss")
        assert language == "css"
        assert confidence == 0.8

        # Test .sass extension
        language, confidence = self.detector.detect_language("styles.sass")
        assert language == "css"
        assert confidence == 0.8

        # Test .less extension
        language, confidence = self.detector.detect_language("styles.less")
        assert language == "css"
        assert confidence == 0.8

    def test_html_content_detection(self):
        """Test HTML content-based detection"""
        html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Test Page</title>
</head>
<body>
    <h1>Hello World</h1>
    <p>This is a test paragraph.</p>
    <div class="container">
        <a href="link.html">Link</a>
        <img src="image.jpg" alt="Image">
    </div>
</body>
</html>"""
        
        # Test with .html extension and content
        language, confidence = self.detector.detect_language("test.html", html_content)
        assert language == "html"
        assert confidence == 0.9

        # Test content patterns
        patterns = self.detector.content_patterns.get("html", [])
        assert len(patterns) > 0
        
        # Check that HTML patterns match
        html_score = 0
        for pattern, weight in patterns:
            import re
            if re.search(pattern, html_content, re.MULTILINE):
                html_score += weight
        
        assert html_score > 0

    def test_css_content_detection(self):
        """Test CSS content-based detection"""
        css_content = """/* Main styles */
body {
    margin: 0;
    padding: 0;
    font-family: Arial, sans-serif;
    background-color: #f0f0f0;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

#header {
    color: #333;
    font-size: 2em;
    text-align: center;
}

@media (max-width: 768px) {
    .container {
        padding: 10px;
    }
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}"""
        
        # Test with .css extension and content
        language, confidence = self.detector.detect_language("styles.css", css_content)
        assert language == "css"
        assert confidence == 0.9

        # Test content patterns
        patterns = self.detector.content_patterns.get("css", [])
        assert len(patterns) > 0
        
        # Check that CSS patterns match
        css_score = 0
        for pattern, weight in patterns:
            import re
            if re.search(pattern, css_content, re.MULTILINE):
                css_score += weight
        
        assert css_score > 0

    def test_html_css_supported_languages(self):
        """Test that HTML and CSS are in supported languages"""
        supported = self.detector.get_supported_languages()
        assert "html" in supported
        assert "css" in supported

    def test_html_css_is_supported(self):
        """Test HTML and CSS support status"""
        assert self.detector.is_supported("html")
        assert self.detector.is_supported("css")

    def test_html_css_extensions_in_mapping(self):
        """Test that HTML and CSS extensions are in extension mapping"""
        extensions = self.detector.get_supported_extensions()
        assert ".html" in extensions
        assert ".htm" in extensions
        assert ".xhtml" in extensions
        assert ".css" in extensions
        assert ".scss" in extensions
        assert ".sass" in extensions
        assert ".less" in extensions

    def test_detect_from_extension_html_css(self):
        """Test quick detection using extension only"""
        assert self.detector.detect_from_extension("index.html") == "html"
        assert self.detector.detect_from_extension("page.htm") == "html"
        assert self.detector.detect_from_extension("doc.xhtml") == "html"
        assert self.detector.detect_from_extension("styles.css") == "css"
        assert self.detector.detect_from_extension("styles.scss") == "css"
        assert self.detector.detect_from_extension("styles.sass") == "css"
        assert self.detector.detect_from_extension("styles.less") == "css"

    def test_get_language_info_html_css(self):
        """Test language info retrieval for HTML and CSS"""
        # Test HTML language info
        html_info = self.detector.get_language_info("html")
        assert html_info["name"] == "html"
        assert html_info["supported"] == True
        assert html_info["tree_sitter_available"] == True
        assert ".html" in html_info["extensions"]
        assert ".htm" in html_info["extensions"]

        # Test CSS language info
        css_info = self.detector.get_language_info("css")
        assert css_info["name"] == "css"
        assert css_info["supported"] == True
        assert css_info["tree_sitter_available"] == True
        assert ".css" in css_info["extensions"]
        assert ".scss" in css_info["extensions"]

    def test_global_detect_function_html_css(self):
        """Test global detection function for HTML and CSS"""
        assert detect_language_from_file("index.html") == "html"
        assert detect_language_from_file("styles.css") == "css"
        assert detect_language_from_file("component.scss") == "css"

    def test_invalid_input_handling(self):
        """Test handling of invalid inputs"""
        # Test empty string
        language, confidence = self.detector.detect_language("")
        assert language == "unknown"
        assert confidence == 0.0

        # Test None input
        language, confidence = self.detector.detect_language(None)
        assert language == "unknown"
        assert confidence == 0.0

        # Test non-string input
        language, confidence = self.detector.detect_language(123)
        assert language == "unknown"
        assert confidence == 0.0

    def test_unknown_extension(self):
        """Test handling of unknown extensions"""
        language, confidence = self.detector.detect_language("file.unknown")
        assert language == "unknown"
        assert confidence == 0.0

    def test_case_insensitive_extensions(self):
        """Test case-insensitive extension handling"""
        # Test uppercase extensions
        language, confidence = self.detector.detect_language("INDEX.HTML")
        assert language == "html"
        
        language, confidence = self.detector.detect_language("STYLES.CSS")
        assert language == "css"

        # Test mixed case extensions
        language, confidence = self.detector.detect_language("page.Html")
        assert language == "html"
        
        language, confidence = self.detector.detect_language("styles.Css")
        assert language == "css"


class TestHtmlCssContentPatterns:
    """Test HTML and CSS content pattern matching"""

    def setup_method(self):
        """Set up test fixtures"""
        self.detector = LanguageDetector()

    def test_html_doctype_pattern(self):
        """Test HTML DOCTYPE pattern matching"""
        content = "<!DOCTYPE html>"
        patterns = self.detector.content_patterns["html"]
        
        import re
        doctype_pattern = next((p for p, w in patterns if "DOCTYPE" in p), None)
        assert doctype_pattern is not None
        assert re.search(doctype_pattern, content, re.IGNORECASE)

    def test_html_tag_patterns(self):
        """Test HTML tag pattern matching"""
        content = "<html><head><title>Test</title></head><body><div><p>Content</p></div></body></html>"
        patterns = self.detector.content_patterns["html"]
        
        import re
        matched_patterns = 0
        for pattern, weight in patterns:
            if re.search(pattern, content, re.MULTILINE):
                matched_patterns += 1
        
        assert matched_patterns > 0

    def test_css_selector_patterns(self):
        """Test CSS selector pattern matching"""
        content = ".class { color: red; } #id { margin: 10px; }"
        patterns = self.detector.content_patterns["css"]
        
        import re
        matched_patterns = 0
        for pattern, weight in patterns:
            if re.search(pattern, content, re.MULTILINE):
                matched_patterns += 1
        
        assert matched_patterns > 0

    def test_css_at_rule_patterns(self):
        """Test CSS at-rule pattern matching"""
        content = "@media screen { .class { display: block; } } @import 'styles.css'; @keyframes fade { from { opacity: 0; } }"
        patterns = self.detector.content_patterns["css"]
        
        import re
        at_rule_matches = 0
        for pattern, weight in patterns:
            if "@" in pattern and re.search(pattern, content, re.MULTILINE):
                at_rule_matches += 1
        
        assert at_rule_matches > 0


if __name__ == "__main__":
    pytest.main([__file__])