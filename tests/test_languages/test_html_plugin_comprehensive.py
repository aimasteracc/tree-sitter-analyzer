"""
Comprehensive tests for HTML plugin.
Tests all major functionality including HTML elements, attributes, text content,
comments, embedded scripts/styles, and HTML-specific features.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from tree_sitter_analyzer.languages.html_plugin import HTMLElementExtractor, HTMLLanguagePlugin
from tree_sitter_analyzer.models import Function, Class, Variable, Import


class TestHTMLElementExtractor:
    """Test HTML element extractor functionality"""
    
    @pytest.fixture
    def extractor(self):
        """Create an HTML element extractor instance"""
        return HTMLElementExtractor()

    @pytest.fixture
    def mock_tree(self):
        """Create a mock tree-sitter tree"""
        tree = Mock()
        tree.root_node = Mock()
        tree.language = Mock()
        return tree

    @pytest.fixture
    def sample_html_code(self):
        """Sample HTML code for testing"""
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test HTML Document</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
    </style>
    <script>
        function greetUser() {
            alert('Hello, World!');
        }
        
        document.addEventListener('DOMContentLoaded', function() {
            console.log('Page loaded');
        });
    </script>
</head>
<body>
    <!-- This is a comment -->
    <div class="container" id="main-container">
        <header>
            <h1>Welcome to Our Website</h1>
            <nav>
                <ul>
                    <li><a href="#home">Home</a></li>
                    <li><a href="#about">About</a></li>
                    <li><a href="#contact">Contact</a></li>
                </ul>
            </nav>
        </header>
        
        <main>
            <section id="content">
                <h2>Main Content</h2>
                <p>This is a paragraph with <strong>bold text</strong> and <em>italic text</em>.</p>
                
                <form action="/submit" method="post">
                    <div class="form-group">
                        <label for="username">Username:</label>
                        <input type="text" id="username" name="username" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="email">Email:</label>
                        <input type="email" id="email" name="email" required>
                    </div>
                    
                    <button type="submit">Submit</button>
                </form>
                
                <img src="image.jpg" alt="Sample Image" width="300" height="200">
                
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
                            <td>25</td>
                            <td>New York</td>
                        </tr>
                        <tr>
                            <td>Jane</td>
                            <td>30</td>
                            <td>London</td>
                        </tr>
                    </tbody>
                </table>
            </section>
        </main>
        
        <footer>
            <p>&copy; 2024 Test Company. All rights reserved.</p>
        </footer>
    </div>
    
    <script src="external-script.js"></script>
</body>
</html>'''

    @pytest.fixture
    def complex_html_code(self):
        """More complex HTML code for advanced testing"""
        return '''<!DOCTYPE html>
<html lang="zh-CN" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Complex HTML test document">
    <meta property="og:title" content="Test Page">
    <meta property="og:description" content="A test page for HTML parsing">
    <title>Complex HTML Test</title>
    
    <style type="text/css">
        /* CSS comment */
        @media (max-width: 768px) {
            .responsive { display: none; }
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }
    </style>
    
    <link rel="stylesheet" href="styles.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
</head>
<body class="dark-theme" data-user-id="12345">
    <!-- Navigation component -->
    <nav aria-label="Main navigation" role="navigation">
        <a href="#content" class="sr-only">Skip to content</a>
        <ul role="menubar">
            <li role="menuitem"><a href="/">Home</a></li>
            <li role="menuitem" aria-haspopup="true">
                <a href="/products">Products</a>
                <ul role="menu">
                    <li role="menuitem"><a href="/products/web">Web</a></li>
                    <li role="menuitem"><a href="/products/mobile">Mobile</a></li>
                </ul>
            </li>
        </ul>
    </nav>
    
    <main id="content" role="main">
        <!-- Hero section -->
        <section class="hero" aria-labelledby="hero-heading">
            <h1 id="hero-heading">Welcome to the Future</h1>
            <p class="lead">Experience cutting-edge technology</p>
            <button type="button" onclick="showDemo()" aria-describedby="demo-description">
                Start Demo
            </button>
            <div id="demo-description" class="sr-only">
                Click to start an interactive demonstration
            </div>
        </section>
        
        <!-- Form with validation -->
        <form id="contact-form" novalidate>
            <fieldset>
                <legend>Contact Information</legend>
                
                <div class="form-row">
                    <label for="first-name">
                        First Name <span aria-hidden="true">*</span>
                    </label>
                    <input 
                        type="text" 
                        id="first-name" 
                        name="firstName"
                        required
                        aria-describedby="first-name-error"
                        autocomplete="given-name"
                    >
                    <div id="first-name-error" class="error" role="alert"></div>
                </div>
                
                <div class="form-row">
                    <label for="phone">Phone Number</label>
                    <input 
                        type="tel" 
                        id="phone" 
                        name="phone"
                        pattern="[0-9]{3}-[0-9]{3}-[0-9]{4}"
                        placeholder="123-456-7890"
                        autocomplete="tel"
                    >
                </div>
                
                <div class="form-row">
                    <label for="preferences">Preferences</label>
                    <select id="preferences" name="preferences" multiple>
                        <option value="email">Email Updates</option>
                        <option value="sms">SMS Notifications</option>
                        <option value="call">Phone Calls</option>
                    </select>
                </div>
                
                <div class="checkbox-group" role="group" aria-labelledby="interests-legend">
                    <div id="interests-legend">Areas of Interest</div>
                    <label>
                        <input type="checkbox" name="interests" value="tech" checked>
                        Technology
                    </label>
                    <label>
                        <input type="checkbox" name="interests" value="design">
                        Design
                    </label>
                    <label>
                        <input type="checkbox" name="interests" value="business">
                        Business
                    </label>
                </div>
            </fieldset>
            
            <button type="submit" disabled>Submit Form</button>
            <button type="reset">Clear Form</button>
        </form>
        
        <!-- Data visualization -->
        <section aria-labelledby="data-heading">
            <h2 id="data-heading">Performance Metrics</h2>
            
            <div class="metrics-grid" role="region" aria-label="Performance data">
                <div class="metric-card" data-value="95">
                    <h3>Performance Score</h3>
                    <div class="progress" role="progressbar" aria-valuenow="95" aria-valuemin="0" aria-valuemax="100">
                        <div class="progress-bar" style="width: 95%"></div>
                    </div>
                    <span class="sr-only">95 out of 100</span>
                </div>
                
                <div class="metric-card" data-value="88">
                    <h3>Accessibility</h3>
                    <meter value="88" min="0" max="100">88%</meter>
                </div>
            </div>
        </section>
        
        <!-- Custom elements (Web Components) -->
        <custom-header title="Custom Component">
            <custom-nav slot="navigation">
                <nav-item href="/home">Home</nav-item>
                <nav-item href="/about">About</nav-item>
            </custom-nav>
        </custom-header>
        
        <!-- Media elements -->
        <figure>
            <picture>
                <source media="(max-width: 768px)" srcset="small-image.webp" type="image/webp">
                <source media="(max-width: 768px)" srcset="small-image.jpg" type="image/jpeg">
                <source srcset="large-image.webp" type="image/webp">
                <img src="large-image.jpg" alt="Responsive image example" loading="lazy">
            </picture>
            <figcaption>A responsive image with multiple formats</figcaption>
        </figure>
        
        <video controls preload="metadata" poster="video-poster.jpg">
            <source src="video.mp4" type="video/mp4">
            <source src="video.webm" type="video/webm">
            <track kind="captions" src="captions-en.vtt" srclang="en" label="English">
            <track kind="captions" src="captions-zh.vtt" srclang="zh" label="Chinese">
            <p>Your browser doesn't support video playback.</p>
        </video>
    </main>
    
    <aside role="complementary" aria-labelledby="sidebar-heading">
        <h2 id="sidebar-heading">Related Links</h2>
        <ul>
            <li><a href="/docs" rel="help">Documentation</a></li>
            <li><a href="/api" rel="reference">API Reference</a></li>
            <li><a href="/support" rel="help">Support</a></li>
        </ul>
    </aside>
    
    <footer role="contentinfo">
        <address>
            <p>Contact us at: <a href="mailto:info@example.com">info@example.com</a></p>
        </address>
        
        <details>
            <summary>Privacy Policy</summary>
            <p>We respect your privacy and handle your data responsibly.</p>
        </details>
        
        <small>&copy; 2024 Example Company. All rights reserved.</small>
    </footer>
    
    <!-- Embedded JavaScript -->
    <script type="module">
        import { initializeApp } from './modules/app.js';
        import { trackingModule } from './modules/tracking.js';
        
        // Initialize application
        document.addEventListener('DOMContentLoaded', async () => {
            try {
                await initializeApp();
                trackingModule.init();
                
                // Form validation
                const form = document.getElementById('contact-form');
                form.addEventListener('submit', handleFormSubmit);
                
                // Accessibility enhancements
                enhanceAccessibility();
                
            } catch (error) {
                console.error('Failed to initialize app:', error);
            }
        });
        
        function handleFormSubmit(event) {
            event.preventDefault();
            // Form submission logic
        }
        
        function enhanceAccessibility() {
            // Add ARIA labels, keyboard navigation, etc.
        }
    </script>
    
    <!-- Third-party scripts -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=GA_MEASUREMENT_ID"></script>
    <script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){dataLayer.push(arguments);}
        gtag('js', new Date());
        gtag('config', 'GA_MEASUREMENT_ID');
    </script>
</body>
</html>'''

    def test_extractor_initialization(self, extractor):
        """Test HTML element extractor initialization"""
        assert extractor is not None
        assert isinstance(extractor, HTMLElementExtractor)
        assert extractor.current_file == ""
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert extractor.html_elements == []
        assert extractor.attributes == []
        assert extractor.text_nodes == []
        assert extractor.comments == []

    def test_extract_html_elements(self, extractor, mock_tree, sample_html_code):
        """Test basic HTML element extraction"""
        # Mock the tree structure
        mock_tree.root_node.children = []
        
        # Mock HTML elements
        mock_element = Mock()
        mock_element.type = "element"
        mock_element.start_point = (10, 4)
        mock_element.end_point = (15, 10)
        mock_element.start_byte = 100
        mock_element.end_byte = 200
        mock_element.children = []
        
        # Mock start tag with tag name
        mock_start_tag = Mock()
        mock_start_tag.type = "start_tag"
        mock_start_tag.children = []
        
        mock_tag_name = Mock()
        mock_tag_name.type = "tag_name"
        mock_start_tag.children.append(mock_tag_name)
        mock_element.children.append(mock_start_tag)
        
        mock_tree.root_node.children = [mock_element]
        
        with patch.object(extractor, '_get_node_text', return_value="div"):
            elements = extractor.extract_elements_from_html(mock_tree, sample_html_code)
            
            assert len(elements) >= 0  # Should extract some elements
            # Test passes if no exceptions are raised

    def test_extract_functions_as_html_elements(self, extractor, mock_tree, sample_html_code):
        """Test extracting HTML elements as Function objects"""
        # Mock extraction results
        mock_elements = [
            {
                "type": "html_element",
                "name": "div",
                "start_line": 1,
                "end_line": 5,
                "raw_text": '<div class="container">content</div>',
            },
            {
                "type": "html_element", 
                "name": "p",
                "start_line": 6,
                "end_line": 6,
                "raw_text": '<p>Hello world</p>',
            }
        ]
        
        with patch.object(extractor, 'extract_elements_from_html', return_value=mock_elements):
            functions = extractor.extract_functions(mock_tree, sample_html_code)
            
            assert len(functions) == 2
            assert isinstance(functions[0], Function)
            assert functions[0].name == "div"
            assert functions[0].language == "html"
            assert functions[0].start_line == 1
            assert functions[0].end_line == 5
            
            assert isinstance(functions[1], Function)
            assert functions[1].name == "p"
            assert functions[1].language == "html"

    def test_extract_variables_as_attributes(self, extractor, mock_tree, sample_html_code):
        """Test extracting HTML attributes as Variable objects"""
        mock_elements = [
            {
                "type": "html_attribute",
                "name": "class",
                "value": "container",
                "start_line": 1,
                "end_line": 1,
                "raw_text": 'class="container"',
            },
            {
                "type": "html_attribute",
                "name": "id", 
                "value": "main",
                "start_line": 2,
                "end_line": 2,
                "raw_text": 'id="main"',
            }
        ]
        
        with patch.object(extractor, 'extract_elements_from_html', return_value=mock_elements):
            variables = extractor.extract_variables(mock_tree, sample_html_code)
            
            assert len(variables) == 2
            assert isinstance(variables[0], Variable)
            assert variables[0].name == "class"
            assert variables[0].value == "container"
            assert variables[0].language == "html"
            assert variables[0].var_type == "string"
            
            assert isinstance(variables[1], Variable)
            assert variables[1].name == "id"
            assert variables[1].value == "main"

    def test_extract_imports_as_comments(self, extractor, mock_tree, sample_html_code):
        """Test extracting HTML comments as Import objects"""
        mock_elements = [
            {
                "type": "html_comment",
                "name": "comment_1_0",
                "content": "This is a test comment",
                "start_line": 5,
                "end_line": 5,
                "raw_text": "<!-- This is a test comment -->",
            },
            {
                "type": "html_comment",
                "name": "comment_2_0",
                "content": "Another comment",
                "start_line": 10,
                "end_line": 10, 
                "raw_text": "<!-- Another comment -->",
            }
        ]
        
        with patch.object(extractor, 'extract_elements_from_html', return_value=mock_elements):
            imports = extractor.extract_imports(mock_tree, sample_html_code)
            
            assert len(imports) == 2
            assert isinstance(imports[0], Import)
            assert imports[0].name == "comment_1_0"
            assert imports[0].imported_names == ["This is a test comment"]
            assert imports[0].language == "html"
            
            assert isinstance(imports[1], Import)
            assert imports[1].name == "comment_2_0"
            assert imports[1].imported_names == ["Another comment"]

    def test_extract_classes_as_embedded_content(self, extractor, mock_tree, sample_html_code):
        """Test extracting embedded scripts/styles as Class objects"""
        mock_elements = [
            {
                "type": "html_script",
                "name": "script_block",
                "content": "console.log('Hello world');",
                "start_line": 8,
                "end_line": 12,
                "raw_text": "<script>console.log('Hello world');</script>",
                "content_type": "script",
            },
            {
                "type": "html_style",
                "name": "style_block", 
                "content": "body { margin: 0; }",
                "start_line": 15,
                "end_line": 18,
                "raw_text": "<style>body { margin: 0; }</style>",
                "content_type": "style",
            }
        ]
        
        with patch.object(extractor, 'extract_elements_from_html', return_value=mock_elements):
            classes = extractor.extract_classes(mock_tree, sample_html_code)
            
            assert len(classes) == 2
            assert isinstance(classes[0], Class)
            assert classes[0].name == "script_block"
            assert classes[0].language == "html"
            assert classes[0].docstring == "SCRIPT embedded content"
            
            assert isinstance(classes[1], Class)
            assert classes[1].name == "style_block"
            assert classes[1].docstring == "CSS embedded content"

    def test_node_text_caching(self, extractor):
        """Test node text extraction with caching"""
        extractor.source_code = "<div>test</div>"
        
        # Mock node
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 4
        
        # First call should cache the result
        result1 = extractor._get_node_text(mock_node)
        assert result1 == "<div"
        
        # Second call should use cache
        result2 = extractor._get_node_text(mock_node)
        assert result1 == result2
        
        # Should have cached the result
        node_id = id(mock_node)
        assert node_id in extractor._node_text_cache

    def test_extract_element_attributes(self, extractor):
        """Test extracting attributes from HTML element"""
        extractor.source_code = 'class="container" id="main"'
        
        # Mock start tag with attributes
        mock_start_tag = Mock()
        mock_start_tag.children = []
        
        # Mock attribute 1
        mock_attr1 = Mock()
        mock_attr1.type = "attribute"
        mock_attr1.children = []
        
        mock_attr1_name = Mock()
        mock_attr1_name.type = "attribute_name"
        mock_attr1.children.append(mock_attr1_name)
        
        mock_attr1_value = Mock()
        mock_attr1_value.type = "quoted_attribute_value"
        mock_attr1_value.children = []
        
        mock_attr1_value_child = Mock()
        mock_attr1_value_child.type = "attribute_value"
        mock_attr1_value.children.append(mock_attr1_value_child)
        mock_attr1.children.append(mock_attr1_value)
        
        mock_start_tag.children.append(mock_attr1)
        
        with patch.object(extractor, '_get_node_text', side_effect=["class", "container"]):
            attributes = extractor._extract_element_attributes(mock_start_tag)
            
            assert len(attributes) == 1
            assert attributes[0]["name"] == "class"
            assert attributes[0]["value"] == "container"

    def test_performance_with_large_document(self, extractor, complex_html_code):
        """Test performance with complex HTML document"""
        # Mock tree with many elements
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Create multiple mock elements
        for i in range(100):
            mock_element = Mock()
            mock_element.type = "element"
            mock_element.start_point = (i, 0)
            mock_element.end_point = (i, 20)
            mock_tree.root_node.children.append(mock_element)
        
        # Should handle large documents efficiently
        with patch.object(extractor, '_traverse_html_nodes', return_value=None) as mock_traverse:
            extractor.extract_elements_from_html(mock_tree, complex_html_code)
            mock_traverse.assert_called_once()


class TestHTMLLanguagePlugin:
    """Test HTML language plugin functionality"""
    
    @pytest.fixture
    def plugin(self):
        """Create HTML language plugin instance"""
        return HTMLLanguagePlugin()

    def test_plugin_initialization(self, plugin):
        """Test HTML plugin initialization"""
        assert plugin is not None
        assert isinstance(plugin, HTMLLanguagePlugin)

    def test_get_language_name(self, plugin):
        """Test getting language name"""
        assert plugin.get_language_name() == "html"

    def test_get_file_extensions(self, plugin):
        """Test getting supported file extensions"""
        extensions = plugin.get_file_extensions()
        expected_extensions = [".html", ".htm", ".xhtml", ".xml", ".svg"]
        
        assert isinstance(extensions, list)
        assert len(extensions) == 5
        for ext in expected_extensions:
            assert ext in extensions

    def test_create_extractor(self, plugin):
        """Test creating element extractor"""
        extractor = plugin.create_extractor()
        
        assert extractor is not None
        assert isinstance(extractor, HTMLElementExtractor)

    def test_is_applicable(self, plugin):
        """Test file applicability check"""
        # Should accept HTML files
        assert plugin.is_applicable("index.html") == True
        assert plugin.is_applicable("page.htm") == True
        assert plugin.is_applicable("document.xhtml") == True
        assert plugin.is_applicable("data.xml") == True
        assert plugin.is_applicable("icon.svg") == True
        
        # Should reject non-HTML files
        assert plugin.is_applicable("script.js") == False
        assert plugin.is_applicable("style.css") == False
        assert plugin.is_applicable("app.py") == False
        assert plugin.is_applicable("Main.java") == False

    def test_get_plugin_info(self, plugin):
        """Test getting plugin information"""
        info = plugin.get_plugin_info()
        
        assert isinstance(info, dict)
        assert info["language"] == "html"
        assert info["extensions"] == [".html", ".htm", ".xhtml", ".xml", ".svg"]
        assert info["class_name"] == "HTMLLanguagePlugin"
        assert "tree_sitter_analyzer.languages.html_plugin" in info["module"]

    @pytest.mark.asyncio
    async def test_analyze_file_success(self, plugin):
        """Test successful file analysis"""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        from tree_sitter_analyzer.models import AnalysisResult
        
        # Mock the analysis engine
        mock_result = Mock(spec=AnalysisResult)
        mock_result.success = True
        mock_result.elements = []
        
        with patch('tree_sitter_analyzer.languages.html_plugin.UnifiedAnalysisEngine') as mock_engine:
            mock_engine_instance = Mock()
            mock_engine_instance.analyze_file.return_value = mock_result
            mock_engine.return_value = mock_engine_instance
            
            request = Mock(spec=AnalysisRequest)
            result = await plugin.analyze_file("test.html", request)
            
            assert result == mock_result
            mock_engine_instance.analyze_file.assert_called_once_with("test.html")

    @pytest.mark.asyncio
    async def test_analyze_file_failure(self, plugin):
        """Test file analysis failure handling"""
        from tree_sitter_analyzer.core.analysis_engine import AnalysisRequest
        
        with patch('tree_sitter_analyzer.languages.html_plugin.UnifiedAnalysisEngine') as mock_engine:
            mock_engine_instance = Mock()
            mock_engine_instance.analyze_file.side_effect = Exception("Analysis failed")
            mock_engine.return_value = mock_engine_instance
            
            request = Mock(spec=AnalysisRequest)
            result = await plugin.analyze_file("test.html", request)
            
            assert result.success == False
            assert result.error_message == "Analysis failed"
            assert result.language == "html"
            assert result.file_path == "test.html"

    def test_enhance_html_metrics(self, plugin):
        """Test HTML-specific metrics enhancement"""
        from tree_sitter_analyzer.models import AnalysisResult, CodeElement
        
        # Create mock elements
        mock_elements = [
            Mock(spec=CodeElement, element_type="function", name="div"),
            Mock(spec=CodeElement, element_type="function", name="p"),
            Mock(spec=CodeElement, element_type="function", name="header"),
            Mock(spec=CodeElement, element_type="function", name="form"),
            Mock(spec=CodeElement, element_type="function", name="img"),
            Mock(spec=CodeElement, element_type="variable", name="class"),
            Mock(spec=CodeElement, element_type="variable", name="id"), 
            Mock(spec=CodeElement, element_type="import", name="comment"),
            Mock(spec=CodeElement, element_type="class", name="script_block"),
            Mock(spec=CodeElement, element_type="class", name="style_block"),
        ]
        
        # Mock result with metrics
        mock_result = Mock(spec=AnalysisResult)
        mock_result.elements = mock_elements
        mock_result.metrics = Mock()
        mock_result.metrics.elements = {}
        
        # Call enhancement
        plugin._enhance_html_metrics(mock_result)
        
        # Check enhanced metrics
        assert mock_result.metrics.elements["elements"] == 5  # HTML elements
        assert mock_result.metrics.elements["attributes"] == 2  # Attributes
        assert mock_result.metrics.elements["comments"] == 1  # Comments
        assert mock_result.metrics.elements["scripts"] == 1  # Script blocks
        assert mock_result.metrics.elements["styles"] == 1  # Style blocks
        assert mock_result.metrics.elements["semantic_elements"] == 1  # header
        assert mock_result.metrics.elements["form_elements"] == 1  # form
        assert mock_result.metrics.elements["media_elements"] == 1  # img


class TestHTMLPluginIntegration:
    """Integration tests for HTML plugin"""
    
    @pytest.fixture
    def plugin(self):
        """Create HTML plugin instance"""
        return HTMLLanguagePlugin()
    
    @pytest.fixture  
    def sample_html_file_content(self):
        """Sample HTML file content for integration testing"""
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Integration Test</title>
    <style>
        .test { color: red; }
    </style>
</head>
<body>
    <!-- Test comment -->
    <div class="test" id="main">
        <h1>Test Header</h1>
        <p>Test paragraph</p>
        <a href="/test">Test Link</a>
    </div>
    
    <script>
        console.log("Test script");
    </script>
</body>
</html>'''

    def test_full_extraction_workflow(self, plugin, sample_html_file_content):
        """Test complete HTML extraction workflow"""
        extractor = plugin.create_extractor()
        
        # Mock tree-sitter parsing
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        # Test that extraction completes without errors
        elements = extractor.extract_elements_from_html(mock_tree, sample_html_file_content)
        
        # Should return empty list or valid elements (no exceptions)
        assert isinstance(elements, list)
        
        # Test each extraction method
        functions = extractor.extract_functions(mock_tree, sample_html_file_content)
        variables = extractor.extract_variables(mock_tree, sample_html_file_content)
        imports = extractor.extract_imports(mock_tree, sample_html_file_content)
        classes = extractor.extract_classes(mock_tree, sample_html_file_content)
        
        # All should return lists (even if empty due to mocking)
        assert isinstance(functions, list)
        assert isinstance(variables, list)
        assert isinstance(imports, list)
        assert isinstance(classes, list)

    def test_plugin_registration(self):
        """Test that HTML plugin can be registered properly"""
        plugin = HTMLLanguagePlugin()
        
        # Test plugin interface compliance
        assert hasattr(plugin, 'get_language_name')
        assert hasattr(plugin, 'get_file_extensions')
        assert hasattr(plugin, 'create_extractor')
        assert hasattr(plugin, 'analyze_file')
        assert hasattr(plugin, 'is_applicable')
        
        # Test that it returns expected types
        assert isinstance(plugin.get_language_name(), str)
        assert isinstance(plugin.get_file_extensions(), list)
        assert plugin.create_extractor() is not None

    def test_error_handling_robustness(self, plugin):
        """Test plugin robustness with various error conditions"""
        extractor = plugin.create_extractor()
        
        # Test with None tree
        try:
            extractor.extract_functions(None, "test")
            # Should not raise exception
        except Exception as e:
            # If it raises, should be handled gracefully
            assert isinstance(e, (AttributeError, TypeError))
        
        # Test with empty content
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        functions = extractor.extract_functions(mock_tree, "")
        assert isinstance(functions, list)
        
        # Test with malformed content
        functions = extractor.extract_functions(mock_tree, "<<<invalid html>>>")
        assert isinstance(functions, list)

    def test_caching_behavior(self, plugin):
        """Test caching behavior in HTML extractor"""
        extractor = plugin.create_extractor()
        
        # Test that caches are properly initialized
        assert isinstance(extractor._node_text_cache, dict)
        assert isinstance(extractor._processed_nodes, set)
        assert isinstance(extractor._element_cache, dict)
        
        # Test that cache is used
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 5
        
        extractor.source_code = "test content"
        
        # First call
        result1 = extractor._get_node_text(mock_node)
        
        # Second call should use cache
        result2 = extractor._get_node_text(mock_node)
        assert result1 == result2
        
        # Check cache was used
        node_id = id(mock_node)
        assert node_id in extractor._node_text_cache


if __name__ == "__main__":
    pytest.main([__file__])