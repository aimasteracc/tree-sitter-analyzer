from unittest.mock import MagicMock, patch

import pytest

from tree_sitter_analyzer.core.query_service import QueryService


@pytest.fixture
def query_service():
    return QueryService()


def test_query_service_basic(query_service):
    assert query_service is not None


@pytest.mark.asyncio
async def test_query_service_execute_empty(query_service):
    with patch.object(query_service, "_read_file_async", return_value=("", "utf-8")):
        with patch.object(query_service.parser, "parse_code") as mock_parse:
            mock_result = MagicMock()
            mock_result.tree = MagicMock()
            mock_result.tree.language = MagicMock()
            mock_result.tree.root_node = MagicMock()
            mock_parse.return_value = mock_result

            result = await query_service.execute_query(
                "test.py", "python", query_string="(module) @module"
            )
            assert isinstance(result, list)


class TestExtractNodeName:
    """Cover _extract_node_name branches."""

    @patch(
        "tree_sitter_analyzer.core.query_service.get_node_text_safe",
        return_value="my_func",
    )
    def test_name_field_found(self, mock_text, query_service):
        node = MagicMock()
        name_node = MagicMock()
        name_node.type = "identifier"
        node.child_by_field_name.side_effect = lambda f: (
            name_node if f == "name" else None
        )
        assert query_service._extract_node_name(node) == "my_func"

    @patch(
        "tree_sitter_analyzer.core.query_service.get_node_text_safe",
        return_value="inner_name",
    )
    def test_declarator_field_with_inner_declarator(self, mock_text, query_service):
        node = MagicMock()
        decl_node = MagicMock()
        decl_node.type = "function_declarator"
        inner_node = MagicMock()
        decl_node.child_by_field_name.side_effect = lambda f: (
            inner_node if f == "declarator" else None
        )
        node.child_by_field_name.side_effect = lambda f: (
            decl_node if f == "declarator" else None
        )
        assert query_service._extract_node_name(node) == "inner_name"

    @patch(
        "tree_sitter_analyzer.core.query_service.get_node_text_safe",
        return_value="inner_name2",
    )
    def test_declarator_field_with_inner_name(self, mock_text, query_service):
        node = MagicMock()
        decl_node = MagicMock()
        decl_node.type = "function_declarator"
        inner_node = MagicMock()
        decl_node.child_by_field_name.side_effect = lambda f: (
            inner_node if f == "name" else None
        )
        node.child_by_field_name.side_effect = lambda f: (
            decl_node if f == "declarator" else None
        )
        assert query_service._extract_node_name(node) == "inner_name2"

    def test_no_child_by_field_name(self, query_service):
        node = MagicMock(spec=[])
        assert query_service._extract_node_name(node) is None

    @patch(
        "tree_sitter_analyzer.core.query_service.get_node_text_safe", return_value=""
    )
    def test_empty_text_returns_none(self, mock_text, query_service):
        node = MagicMock()
        name_node = MagicMock()
        name_node.type = "identifier"
        node.child_by_field_name.side_effect = lambda f: (
            name_node if f == "name" else None
        )
        assert query_service._extract_node_name(node) is None

    @patch(
        "tree_sitter_analyzer.core.query_service.get_node_text_safe",
        return_value="x" * 201,
    )
    def test_very_long_name_ignored(self, mock_text, query_service):
        node = MagicMock()
        name_node = MagicMock()
        name_node.type = "identifier"
        node.child_by_field_name.side_effect = lambda f: (
            name_node if f == "name" else None
        )
        assert query_service._extract_node_name(node) is None


class TestExtractParentContext:
    """Cover _extract_parent_context branches."""

    def test_no_parent_attr(self, query_service):
        node = MagicMock(spec=[])
        assert query_service._extract_parent_context(node) is None

    @patch(
        "tree_sitter_analyzer.core.query_service.get_node_text_safe",
        return_value="MyClass",
    )
    def test_parent_is_container(self, mock_text, query_service):
        parent = MagicMock()
        parent.type = "class"
        name_node = MagicMock()
        parent.child_by_field_name.return_value = name_node
        parent.parent = None
        node = MagicMock()
        node.parent = parent
        assert query_service._extract_parent_context(node) == "MyClass"

    def test_parent_not_container(self, query_service):
        parent = MagicMock()
        parent.type = "expression_statement"
        parent.parent = None
        node = MagicMock()
        node.parent = parent
        assert query_service._extract_parent_context(node) is None

    @patch(
        "tree_sitter_analyzer.core.query_service.get_node_text_safe", return_value="Mod"
    )
    def test_grandparent_is_container(self, mock_text, query_service):
        name_node = MagicMock()
        gp = MagicMock()
        gp.type = "module"
        gp.child_by_field_name.return_value = name_node
        gp.parent = None
        parent = MagicMock()
        parent.type = "body"
        parent.parent = gp
        node = MagicMock()
        node.parent = parent
        assert query_service._extract_parent_context(node) == "Mod"

    def test_parent_no_type_attr(self, query_service):
        parent = MagicMock(spec=["parent"])
        parent.parent = None
        node = MagicMock()
        node.parent = parent
        assert query_service._extract_parent_context(node) is None

    @patch(
        "tree_sitter_analyzer.core.query_service.get_node_text_safe", return_value=""
    )
    def test_container_with_empty_name(self, mock_text, query_service):
        parent = MagicMock()
        parent.type = "class"
        name_node = MagicMock()
        parent.child_by_field_name.return_value = name_node
        parent.parent = None
        node = MagicMock()
        node.parent = parent
        assert query_service._extract_parent_context(node) is None

    def test_container_with_no_name_node(self, query_service):
        parent = MagicMock()
        parent.type = "class"
        parent.child_by_field_name.return_value = None
        parent.parent = None
        node = MagicMock()
        node.parent = parent
        assert query_service._extract_parent_context(node) is None


class TestCreateResultDictFull:
    """Cover _create_result_dict with name and parent extraction."""

    @patch(
        "tree_sitter_analyzer.core.query_service.get_node_text_safe",
        return_value="my_method",
    )
    def test_with_name_and_parent(self, mock_text, query_service):
        name_node = MagicMock()
        name_node.type = "identifier"
        parent_name_node = MagicMock()
        parent = MagicMock()
        parent.type = "class"
        parent.child_by_field_name.return_value = parent_name_node
        parent.parent = None
        node = MagicMock()
        node.type = "method_declaration"
        node.start_point = (2, 0)
        node.end_point = (10, 0)
        node.child_by_field_name.side_effect = lambda f: (
            name_node if f == "name" else None
        )
        node.parent = parent
        # Call order: content extraction, name extraction, parent extraction
        mock_text.side_effect = ["def my_method(): pass", "my_method", "MyClass"]
        result = query_service._create_result_dict(
            node, "method", "def my_method(): pass"
        )
        assert result["name"] == "my_method"
        assert result["parent"] == "MyClass"
        assert result["start_line"] == 3
        assert result["end_line"] == 11

    def test_node_missing_start_end_point(self, query_service):
        node = MagicMock(spec=["type"])
        node.type = "identifier"
        result = query_service._create_result_dict(node, "ident", "code")
        assert result["start_line"] == 0
        assert result["end_line"] == 0


class TestExecutePluginQueryElementConversion:
    """Cover MockNode creation and element conversion in _execute_plugin_query."""

    def test_element_with_raw_text(self, query_service):
        element = MagicMock()
        element.start_line = 1
        element.end_line = 3
        element.element_type = "function"
        element.raw_text = "def foo(): pass"
        plugin = MagicMock()
        plugin.execute_query_strategy.return_value = [element]
        root = MagicMock()
        with patch.object(
            query_service.plugin_manager, "get_plugin", return_value=plugin
        ):
            captures = query_service._execute_plugin_query(
                root, "functions", "python", "def foo(): pass"
            )
            assert len(captures) == 1
            mock_node, name = captures[0]
            assert name == "functions"
            assert mock_node.type == "function"
            assert mock_node.start_point == (0, 0)
            assert mock_node.end_point == (2, 0)

    def test_null_query_key_defaults(self, query_service):
        element = MagicMock()
        element.start_line = 1
        element.end_line = 1
        element.element_type = "thing"
        element.raw_text = "x"
        plugin = MagicMock()
        plugin.execute_query_strategy.return_value = [element]
        root = MagicMock()
        with patch.object(
            query_service.plugin_manager, "get_plugin", return_value=plugin
        ):
            captures = query_service._execute_plugin_query(root, None, "python", "x")
            assert len(captures) == 1
            _, name = captures[0]
            assert name == "element"

    def test_no_plugin_uses_fallback(self, query_service):
        root = MagicMock()
        root.children = []
        with patch.object(
            query_service.plugin_manager, "get_plugin", return_value=None
        ):
            captures = query_service._execute_plugin_query(
                root, "function", "unknown_lang", "code"
            )
            assert isinstance(captures, list)

    def test_plugin_returns_none_elements(self, query_service):
        plugin = MagicMock()
        plugin.execute_query_strategy.return_value = None
        root = MagicMock()
        with patch.object(
            query_service.plugin_manager, "get_plugin", return_value=plugin
        ):
            captures = query_service._execute_plugin_query(
                root, "functions", "python", "code"
            )
            assert isinstance(captures, list)


class TestReadFileAsync:
    """Cover _read_file_async with actual file."""

    @pytest.mark.asyncio
    async def test_read_file_async_actual(self, query_service, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("print('hello')\n", encoding="utf-8")
        content, encoding = await query_service._read_file_async(str(f))
        assert "print('hello')" in content
        assert isinstance(encoding, str)
