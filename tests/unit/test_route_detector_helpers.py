"""Coverage-boosting tests for _route_detector_helpers.py (target: 50.8% → 85%+)."""

from unittest.mock import Mock

from tree_sitter_analyzer._route_detector_helpers import (
    extract_annotation_value,
    extract_django_handler,
    extract_js_handler,
    extract_template_string,
    find_keyword,
    function_name_after_decorator,
    method_after_annotation,
    parse_methods_list,
    unquote,
    unquote_java_string,
    walk,
)

# ── unquote ──────────────────────────────────────────────────────────────

class TestUnquote:
    def test_double_quoted(self):
        assert unquote('"hello"') == "hello"

    def test_single_quoted(self):
        assert unquote("'world'") == "world"

    def test_no_quotes(self):
        assert unquote("plain") == "plain"

    def test_single_char_quoted(self):
        # len(s) < 2 edge case
        assert unquote('"') == '"'

    def test_mismatched_quotes(self):
        assert unquote('"hello\'') == '"hello\''

    def test_whitespace_around_quotes(self):
        assert unquote('  "hello"  ') == "hello"

    def test_empty_string(self):
        assert unquote("") == ""


# ── unquote_java_string ──────────────────────────────────────────────────

class TestUnquoteJavaString:
    def test_double_quoted(self):
        assert unquote_java_string('"hello"') == "hello"

    def test_not_quoted(self):
        assert unquote_java_string("plain") == "plain"

    def test_single_quoted_not_stripped(self):
        assert unquote_java_string("'hello'") == "'hello'"

    def test_empty_string(self):
        assert unquote_java_string("") == ""

    def test_whitespace_around(self):
        assert unquote_java_string('  "hello"  ') == "hello"


# ── parse_methods_list ───────────────────────────────────────────────────

class TestParseMethodsList:
    def test_multiple_methods(self):
        assert parse_methods_list("methods=['GET', 'POST']") == ["GET", "POST"]

    def test_single_method(self):
        assert parse_methods_list('methods=["DELETE"]') == ["DELETE"]

    def test_no_methods(self):
        assert parse_methods_list("something else") == []

    def test_empty_string(self):
        assert parse_methods_list("") == []

    def test_double_quoted_methods(self):
        assert parse_methods_list('methods=["PUT", "PATCH"]') == ["PUT", "PATCH"]


# ── extract_django_handler ───────────────────────────────────────────────

class TestExtractDjangoHandler:
    def test_dotted_path(self):
        assert extract_django_handler("myapp.views.index") == "index"

    def test_views_prefix(self):
        assert extract_django_handler("views.home") == "home"

    def test_dot_prefix(self):
        assert extract_django_handler(".home") == "home"

    def test_quoted_string(self):
        assert extract_django_handler('"literal_handler"') == "literal_handler"

    def test_single_quoted_string(self):
        assert extract_django_handler("'literal_handler'") == "literal_handler"

    def test_simple_name_no_dot(self):
        assert extract_django_handler("simple") == "simple"


# ── extract_template_string ──────────────────────────────────────────────

class TestExtractTemplateString:
    def test_string_child(self):
        node = Mock()
        child = Mock()
        child.type = "string"
        child.text.decode.return_value = '"/api/users"'
        node.children = [child]
        assert extract_template_string(node) == "/api/users"

    def test_template_string_child(self):
        node = Mock()
        child = Mock()
        child.type = "template_string"
        child.text.decode.return_value = "`/api/${id}`"
        node.children = [child]
        assert extract_template_string(node) == "/api/${id}"

    def test_fallback_backtick_text(self):
        node = Mock()
        node.children = []
        node.text.decode.return_value = "`/fallback`"
        assert extract_template_string(node) == "/fallback"

    def test_fallback_plain_text(self):
        node = Mock()
        node.children = []
        node.text.decode.return_value = "/plain"
        assert extract_template_string(node) == "/plain"


# ── extract_annotation_value ─────────────────────────────────────────────

class TestExtractAnnotationValue:
    def test_parenthesized_string_literal(self):
        node = Mock()
        string_child = Mock()
        string_child.type = "string_literal"
        string_child.text.decode.return_value = '"/api"'
        open_paren = Mock()
        open_paren.type = "("
        node.children = [open_paren, string_child]
        node.child_by_field_name.return_value = None
        assert extract_annotation_value(node) == "/api"

    def test_parenthesized_non_string(self):
        node = Mock()
        next_child = Mock()
        next_child.type = "identifier"
        next_child.text.decode.return_value = "some_value"
        open_paren = Mock()
        open_paren.type = "("
        node.children = [open_paren, next_child]
        node.child_by_field_name.return_value = None
        assert extract_annotation_value(node) == "some_value"

    def test_arguments_field_string_literal(self):
        node = Mock()
        node.children = []
        args_node = Mock()
        child = Mock()
        child.type = "string_literal"
        child.text.decode.return_value = '"/from_args"'
        args_node.children = [child]
        node.child_by_field_name.return_value = args_node
        assert extract_annotation_value(node) == "/from_args"

    def test_arguments_field_string_type(self):
        node = Mock()
        node.children = []
        args_node = Mock()
        child = Mock()
        child.type = "string"
        child.text.decode.return_value = '"/from_args_string"'
        args_node.children = [child]
        node.child_by_field_name.return_value = args_node
        assert extract_annotation_value(node) == "/from_args_string"

    def test_no_paren_no_args(self):
        node = Mock()
        node.children = []
        node.child_by_field_name.return_value = None
        assert extract_annotation_value(node) is None


# ── function_name_after_decorator ────────────────────────────────────────

class TestFunctionNameAfterDecorator:
    def test_function_definition_with_name(self):
        func_def = Mock()
        func_def.type = "function_definition"
        name_node = Mock()
        name_node.text.decode.return_value = "my_func"
        func_def.child_by_field_name.return_value = name_node

        parent = Mock()
        parent.children = [Mock(), func_def]

        decorator = Mock()
        decorator.parent = parent

        assert function_name_after_decorator(decorator) == "my_func"

    def test_identifier_child(self):
        ident = Mock()
        ident.type = "identifier"
        ident.text.decode.return_value = "some_id"

        parent = Mock()
        parent.children = [ident]

        decorator = Mock()
        decorator.parent = parent

        assert function_name_after_decorator(decorator) == "some_id"

    def test_no_parent(self):
        decorator = Mock()
        decorator.parent = None
        assert function_name_after_decorator(decorator) == "<unknown>"

    def test_no_matching_child(self):
        other = Mock()
        other.type = "other_stuff"

        parent = Mock()
        parent.children = [other]

        decorator = Mock()
        decorator.parent = parent

        assert function_name_after_decorator(decorator) == "<unknown>"


# ── method_after_annotation ──────────────────────────────────────────────

class TestMethodAfterAnnotation:
    def test_method_declaration_with_identifier(self):
        ident = Mock()
        ident.type = "identifier"
        ident.text.decode.return_value = "doSomething"

        method_decl = Mock()
        method_decl.type = "method_declaration"
        method_decl.children = [ident]

        parent = Mock()
        parent.children = [Mock(), method_decl]

        annotation = Mock()
        annotation.parent = parent

        assert method_after_annotation(annotation) == "doSomething"

    def test_no_parent(self):
        annotation = Mock()
        annotation.parent = None
        assert method_after_annotation(annotation) == "<unknown>"

    def test_no_method_declaration(self):
        other = Mock()
        other.type = "other"

        parent = Mock()
        parent.children = [other]

        annotation = Mock()
        annotation.parent = parent

        assert method_after_annotation(annotation) == "<unknown>"


# ── find_keyword ─────────────────────────────────────────────────────────

class TestFindKeyword:
    def test_finds_keyword(self):
        ident = Mock()
        ident.type = "identifier"
        ident.text.decode.return_value = "target_kw"

        kw_arg = Mock()
        kw_arg.type = "keyword_argument"
        kw_arg.children = [ident]

        args_node = Mock()
        args_node.children = [Mock(), kw_arg]

        result = find_keyword(args_node, "target_kw")
        assert result is kw_arg

    def test_keyword_not_found(self):
        ident = Mock()
        ident.type = "identifier"
        ident.text.decode.return_value = "other_kw"

        kw_arg = Mock()
        kw_arg.type = "keyword_argument"
        kw_arg.children = [ident]

        args_node = Mock()
        args_node.children = [kw_arg]

        assert find_keyword(args_node, "missing_kw") is None

    def test_no_keyword_arguments(self):
        args_node = Mock()
        args_node.children = []
        assert find_keyword(args_node, "anything") is None


# ── extract_js_handler ───────────────────────────────────────────────────

class TestExtractJsHandler:
    def test_identifier_handler(self):
        ident = Mock()
        ident.type = "identifier"
        ident.text.decode.return_value = "myHandler"

        comma = Mock()
        comma.type = ","

        args_node = Mock()
        args_node.children = [Mock(), comma, ident]

        assert extract_js_handler(args_node) == "myHandler"

    def test_arrow_function_handler(self):
        arrow = Mock()
        arrow.type = "arrow_function"

        comma = Mock()
        comma.type = ","

        args_node = Mock()
        args_node.children = [Mock(), comma, arrow]

        assert extract_js_handler(args_node) == "<anonymous>"

    def test_function_expression_handler(self):
        func_expr = Mock()
        func_expr.type = "function_expression"

        comma = Mock()
        comma.type = ","

        args_node = Mock()
        args_node.children = [Mock(), comma, func_expr]

        assert extract_js_handler(args_node) == "<anonymous>"

    def test_call_expression_handler(self):
        call_expr = Mock()
        call_expr.type = "call_expression"
        call_expr.text.decode.return_value = "router.handle()"

        comma = Mock()
        comma.type = ","

        args_node = Mock()
        args_node.children = [Mock(), comma, call_expr]

        result = extract_js_handler(args_node)
        assert result == "router.handle()"

    def test_string_handler(self):
        string_node = Mock()
        string_node.type = "string"
        string_node.text.decode.return_value = '"save_handler"'

        comma = Mock()
        comma.type = ","

        args_node = Mock()
        args_node.children = [Mock(), comma, string_node]

        assert extract_js_handler(args_node) == "save_handler"

    def test_single_arg_fallback(self):
        child = Mock()
        child.text.decode.return_value = "'/api/users'"

        args_node = Mock()
        args_node.children = [child]

        assert extract_js_handler(args_node) == "/api/users"

    def test_empty_args(self):
        args_node = Mock()
        args_node.children = []
        assert extract_js_handler(args_node) == "<unknown>"


# ── walk ─────────────────────────────────────────────────────────────────

class TestWalk:
    def test_walk_single_node(self):
        """walk should yield the root node at minimum."""
        node = Mock()
        cursor = Mock()
        cursor.node = node
        cursor.goto_first_child.return_value = False
        cursor.goto_next_sibling.return_value = False

        # First goto_parent returns True (not at root yet), second returns False
        cursor.goto_parent.side_effect = [True, False]
        node.walk.return_value = cursor

        results = list(walk(node))
        assert len(results) >= 1
        assert results[0] is node
