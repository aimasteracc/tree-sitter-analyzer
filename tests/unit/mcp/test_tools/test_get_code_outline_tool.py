#!/usr/bin/env python3
"""
Unit tests for GetCodeOutlineTool.

纯 mock 测试：不使用真实 tree-sitter 解析器、不创建临时文件、不调用
asyncio.run(plugin.analyze_file(...))。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool

# ---------------------------------------------------------------------------
# 测试辅助：构造 mock 分析结果
# ---------------------------------------------------------------------------


def _make_element(
    element_type: str,
    name: str,
    start_line: int,
    end_line: int,
    **kwargs,
) -> MagicMock:
    """构造一个模拟的代码元素节点。"""
    elem = MagicMock()
    elem.element_type = element_type
    elem.name = name
    elem.start_line = start_line
    elem.end_line = end_line
    for k, v in kwargs.items():
        setattr(elem, k, v)
    return elem


def _make_analysis_result(
    elements: list,
    file_path: str = "/proj/Foo.java",
    language: str = "java",
    line_count: int = 100,
) -> MagicMock:
    """构造一个模拟的 AnalysisResult。"""
    result = MagicMock()
    result.elements = elements
    result.file_path = file_path
    result.language = language
    result.line_count = line_count
    result.success = True
    return result


# ---------------------------------------------------------------------------
# 初始化测试
# ---------------------------------------------------------------------------


class TestGetCodeOutlineToolInit:
    """测试工具初始化行为。"""

    def test_init_without_project_root(self):
        """无 project_root 时可正常初始化。"""
        tool = GetCodeOutlineTool()
        assert tool is not None
        assert tool.project_root is None
        assert tool.analysis_engine is not None

    def test_set_project_path_updates_engine(self):
        """set_project_path 后 analysis_engine 应被更新。"""
        tool = GetCodeOutlineTool()
        tool.set_project_path("/new/project")
        assert tool.project_root == "/new/project"
        assert tool.analysis_engine is not None


# ---------------------------------------------------------------------------
# 参数校验测试
# ---------------------------------------------------------------------------


class TestGetCodeOutlineToolValidateArguments:
    """测试 validate_arguments 方法。"""

    def setup_method(self):
        self.tool = GetCodeOutlineTool()

    def test_valid_minimal(self):
        """仅提供 file_path 时校验通过。"""
        assert self.tool.validate_arguments({"file_path": "src/Foo.java"}) is True

    def test_valid_all_options(self):
        """提供所有合法参数时校验通过。"""
        result = self.tool.validate_arguments(
            {
                "file_path": "src/Foo.java",
                "language": "java",
                "include_fields": True,
                "include_imports": True,
            }
        )
        assert result is True

    def test_missing_file_path_raises(self):
        """缺少 file_path 时抛出 ValueError。"""
        with pytest.raises(ValueError, match="file_path"):
            self.tool.validate_arguments({})

    def test_empty_file_path_raises(self):
        """空字符串 file_path 时抛出 ValueError。"""
        with pytest.raises(ValueError, match="file_path"):
            self.tool.validate_arguments({"file_path": ""})

    def test_non_string_file_path_raises(self):
        """非字符串 file_path 时抛出 ValueError。"""
        with pytest.raises(ValueError, match="file_path"):
            self.tool.validate_arguments({"file_path": 123})

    def test_non_string_language_raises(self):
        """非字符串 language 时抛出 ValueError。"""
        with pytest.raises(ValueError, match="language"):
            self.tool.validate_arguments({"file_path": "Foo.java", "language": 42})

    def test_non_bool_include_fields_raises(self):
        """非 bool 类型 include_fields 时抛出 ValueError。"""
        with pytest.raises(ValueError, match="include_fields"):
            self.tool.validate_arguments(
                {"file_path": "Foo.java", "include_fields": "yes"}
            )

    def test_non_bool_include_imports_raises(self):
        """非 bool 类型 include_imports 时抛出 ValueError。"""
        with pytest.raises(ValueError, match="include_imports"):
            self.tool.validate_arguments(
                {"file_path": "Foo.java", "include_imports": 1}
            )

    def test_none_language_is_valid(self):
        """language=None 是合法的（会触发自动检测）。"""
        assert (
            self.tool.validate_arguments({"file_path": "Foo.java", "language": None})
            is True
        )


# ---------------------------------------------------------------------------
# _build_outline 单元测试（直接构造 mock AnalysisResult）
# ---------------------------------------------------------------------------


class TestBuildOutlineBasic:
    """测试 _build_outline 的基本结构构建逻辑。"""

    def setup_method(self):
        self.tool = GetCodeOutlineTool()

    def _make_class_elem(self, name, start, end, class_type="class", **kw):
        return _make_element(
            "class",
            name,
            start,
            end,
            class_type=class_type,
            extends_class=kw.get("extends_class"),
            implements_interfaces=kw.get("implements_interfaces", []),
        )

    def _make_method_elem(self, name, start, end, **kw):
        elem = _make_element("function", name, start, end)
        elem.return_type = kw.get("return_type", "void")
        elem.visibility = kw.get("visibility", "public")
        elem.is_constructor = kw.get("is_constructor", False)
        elem.is_static = kw.get("is_static", False)
        elem.parameters = kw.get("parameters", [])
        return elem

    def _make_field_elem(self, name, start, end, **kw):
        elem = _make_element("variable", name, start, end)
        elem.field_type = kw.get("field_type", "String")
        elem.visibility = kw.get("visibility", "private")
        elem.is_static = kw.get("is_static", False)
        return elem

    def _make_pkg_elem(self, name):
        return _make_element("package", name, 1, 1)

    def _make_import_elem(self, name, stmt=None):
        elem = _make_element("import", name, 2, 2)
        elem.import_statement = stmt or name
        return elem

    # 模拟 is_element_of_type 的方式：让 element_type 属性匹配常量
    # 真实代码里 is_element_of_type 比较 elem.element_type — mock 里我们直接
    # patch 它，让它按 element_type 字符串匹配。

    def _patch_is_element_of_type(self):
        """返回一个 is_element_of_type patch，按字符串 element_type 匹配。"""

        def _mock_is_elem(elem, type_const):
            # type_const 在真实代码里是字符串常量
            return getattr(elem, "element_type", "") == type_const

        return patch(
            "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.is_element_of_type",
            side_effect=_mock_is_elem,
        )

    def test_empty_file_outline(self):
        """空文件（无任何元素）时大纲结构正确。"""
        result = _make_analysis_result(elements=[])
        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)

        assert outline["package"] is None
        assert outline["classes"] == []
        assert outline["top_level_functions"] == []
        assert outline["statistics"]["class_count"] == 0
        assert outline["statistics"]["method_count"] == 0
        assert outline["total_lines"] == 100
        assert outline["language"] == "java"

    def test_single_class_with_methods(self):
        """单个类含两个方法时大纲结构正确。"""
        cls = self._make_class_elem("FooService", 10, 80)
        m1 = self._make_method_elem("doSomething", 15, 30, return_type="String")
        m2 = self._make_method_elem(
            "FooService", 11, 14, is_constructor=True, return_type="void"
        )
        elements = [cls, m1, m2]
        result = _make_analysis_result(elements=elements)

        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)

        assert len(outline["classes"]) == 1
        cls_out = outline["classes"][0]
        assert cls_out["name"] == "FooService"
        assert cls_out["line_start"] == 10
        assert cls_out["line_end"] == 80
        # 两个方法均在类内（行号 11-14, 15-30 都在 10-80 范围内）
        assert len(cls_out["methods"]) == 2
        method_names = {m["name"] for m in cls_out["methods"]}
        assert "doSomething" in method_names
        assert "FooService" in method_names
        # 顶层函数为空
        assert outline["top_level_functions"] == []

    def test_top_level_function_detected(self):
        """不在任何类内的方法应归入 top_level_functions。"""
        top_fn = self._make_method_elem("main", 1, 20, return_type="void")
        cls = self._make_class_elem("Bar", 30, 80)
        cls_method = self._make_method_elem("bar", 35, 50)
        elements = [top_fn, cls, cls_method]
        result = _make_analysis_result(elements=elements)

        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)

        assert len(outline["top_level_functions"]) == 1
        assert outline["top_level_functions"][0]["name"] == "main"
        assert len(outline["classes"][0]["methods"]) == 1

    def test_package_extracted(self):
        """package 元素应被提取到 outline.package。"""
        pkg = self._make_pkg_elem("com.example.service")
        result = _make_analysis_result(elements=[pkg])

        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)

        assert outline["package"] == "com.example.service"

    def test_include_fields_false(self):
        """include_fields=False 时类大纲不含 fields 键。"""
        cls = self._make_class_elem("Bar", 1, 50)
        field = self._make_field_elem("count", 5, 5)
        result = _make_analysis_result(elements=[cls, field])

        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(
                result, include_fields=False, include_imports=False
            )

        assert "fields" not in outline["classes"][0]

    def test_include_fields_true(self):
        """include_fields=True 时类大纲应含 fields 列表。"""
        cls = self._make_class_elem("Bar", 1, 50)
        field = self._make_field_elem("count", 5, 5, field_type="int")
        result = _make_analysis_result(elements=[cls, field])

        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(
                result, include_fields=True, include_imports=False
            )

        assert "fields" in outline["classes"][0]
        assert outline["classes"][0]["fields"][0]["name"] == "count"
        assert outline["classes"][0]["fields"][0]["type"] == "int"

    def test_include_imports_false(self):
        """include_imports=False 时大纲不含 imports 键。"""
        imp = self._make_import_elem("java.util.List")
        result = _make_analysis_result(elements=[imp])

        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)

        assert "imports" not in outline

    def test_include_imports_true(self):
        """include_imports=True 时大纲含 imports 列表。"""
        imp = self._make_import_elem("java.util.List", stmt="import java.util.List;")
        result = _make_analysis_result(elements=[imp])

        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, True)

        assert "imports" in outline
        assert "import java.util.List;" in outline["imports"]

    def test_statistics_counts(self):
        """statistics 字段的计数应与元素数量一致。"""
        cls = self._make_class_elem("A", 1, 100)
        m1 = self._make_method_elem("m1", 10, 20)
        m2 = self._make_method_elem("m2", 30, 40)
        f1 = self._make_field_elem("x", 5, 5)
        imp = self._make_import_elem("java.util.List")
        result = _make_analysis_result(elements=[cls, m1, m2, f1, imp])

        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)

        stats = outline["statistics"]
        assert stats["class_count"] == 1
        assert stats["method_count"] == 2
        assert stats["field_count"] == 1
        assert stats["import_count"] == 1

    def test_methods_sorted_by_line(self):
        """类中的方法应按 line_start 升序排列。"""
        cls = self._make_class_elem("A", 1, 100)
        m_late = self._make_method_elem("late", 60, 70)
        m_early = self._make_method_elem("early", 10, 20)
        result = _make_analysis_result(elements=[cls, m_late, m_early])

        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)

        methods = outline["classes"][0]["methods"]
        assert methods[0]["name"] == "early"
        assert methods[1]["name"] == "late"

    def test_extends_and_implements_preserved(self):
        """extends 和 implements 信息应被保留在大纲中。"""
        cls = self._make_class_elem(
            "FooImpl",
            1,
            50,
            extends_class="AbstractFoo",
            implements_interfaces=["IFoo", "Serializable"],
        )
        result = _make_analysis_result(elements=[cls])

        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)

        cls_out = outline["classes"][0]
        assert cls_out["extends"] == "AbstractFoo"
        assert "IFoo" in cls_out["implements"]
        assert "Serializable" in cls_out["implements"]

    # ------------------------------------------------------------------
    # Issue #530: plugins that set ``superclass`` / ``interfaces`` (not
    # the Java-spelling ``extends_class`` / ``implements_interfaces``)
    # must also surface in the outline.  One test per failing language.
    # ------------------------------------------------------------------

    def _make_class_superclass(
        self, name, start, end, superclass=None, interfaces=None
    ):
        """Build a Class mock using the non-Java field spellings."""
        elem = _make_element(
            "class",
            name,
            start,
            end,
            class_type="class",
            # Use the non-Java spellings (JS/TS/Python/Ruby/PHP/C++/C#/Go).
            superclass=superclass,
            interfaces=interfaces or [],
            # Leave extends_class / implements_interfaces at their MagicMock
            # defaults so getattr(cls, "extends_class", None) returns a Mock
            # truthy value — we must NOT set them to sentinel values that
            # accidentally satisfy the truthiness check.  We force them to
            # None / [] explicitly to reproduce the pre-fix behaviour.
            extends_class=None,
            implements_interfaces=[],
        )
        return elem

    def test_js_superclass_field_surfaces_as_extends(self):
        """JS plugin sets superclass=... — outline must surface it as extends."""
        cls = self._make_class_superclass("Dog", 1, 20, superclass="Animal")
        result = _make_analysis_result(
            elements=[cls], file_path="/p/dog.js", language="javascript"
        )
        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)
        cls_out = outline["classes"][0]
        assert cls_out["extends"] == "Animal"
        assert cls_out["implements"] == []

    def test_ts_superclass_and_interfaces_surface_correctly(self):
        """TS plugin sets superclass= and interfaces=[] — both must surface."""
        cls = self._make_class_superclass(
            "AppComponent",
            1,
            30,
            superclass="BaseComponent",
            interfaces=["OnInit", "OnDestroy"],
        )
        result = _make_analysis_result(
            elements=[cls], file_path="/p/app.ts", language="typescript"
        )
        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)
        cls_out = outline["classes"][0]
        assert cls_out["extends"] == "BaseComponent"
        assert cls_out["implements"] == ["OnInit", "OnDestroy"]

    def test_python_superclass_and_interfaces_surface_correctly(self):
        """Python plugin maps first parent to superclass, rest to interfaces."""
        cls = self._make_class_superclass(
            "MyView",
            1,
            40,
            superclass="View",
            interfaces=["LoginRequiredMixin"],
        )
        result = _make_analysis_result(
            elements=[cls], file_path="/p/views.py", language="python"
        )
        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)
        cls_out = outline["classes"][0]
        assert cls_out["extends"] == "View"
        assert cls_out["implements"] == ["LoginRequiredMixin"]

    def test_ruby_superclass_field_surfaces_as_extends(self):
        """Ruby plugin sets superclass= only (no implements in Ruby)."""
        cls = self._make_class_superclass("Dog", 1, 15, superclass="Animal")
        result = _make_analysis_result(
            elements=[cls], file_path="/p/dog.rb", language="ruby"
        )
        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)
        cls_out = outline["classes"][0]
        assert cls_out["extends"] == "Animal"
        assert cls_out["implements"] == []

    def test_php_superclass_and_interfaces_surface_correctly(self):
        """PHP plugin sets superclass= and interfaces= — both must surface."""
        cls = self._make_class_superclass(
            "OrderController",
            1,
            50,
            superclass="AbstractController",
            interfaces=["LoggerAwareInterface"],
        )
        result = _make_analysis_result(
            elements=[cls], file_path="/p/OrderController.php", language="php"
        )
        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)
        cls_out = outline["classes"][0]
        assert cls_out["extends"] == "AbstractController"
        assert cls_out["implements"] == ["LoggerAwareInterface"]

    def test_cpp_superclass_and_interfaces_surface_correctly(self):
        """C++ plugin sets superclass= (first base) and interfaces= (extras)."""
        cls = self._make_class_superclass(
            "ConcreteWidget",
            1,
            60,
            superclass="Widget",
            interfaces=["Paintable"],
        )
        result = _make_analysis_result(
            elements=[cls], file_path="/p/widget.cpp", language="cpp"
        )
        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)
        cls_out = outline["classes"][0]
        assert cls_out["extends"] == "Widget"
        assert cls_out["implements"] == ["Paintable"]

    def test_csharp_superclass_and_interfaces_surface_correctly(self):
        """C# plugin sets superclass= and interfaces= — both must surface."""
        cls = self._make_class_superclass(
            "OrderService",
            1,
            80,
            superclass="BaseService",
            interfaces=["IOrderService", "IDisposable"],
        )
        result = _make_analysis_result(
            elements=[cls], file_path="/p/OrderService.cs", language="csharp"
        )
        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)
        cls_out = outline["classes"][0]
        assert cls_out["extends"] == "BaseService"
        assert cls_out["implements"] == ["IOrderService", "IDisposable"]

    def test_rust_implements_interfaces_field_surfaces_correctly(self):
        """Rust plugin sets implements_interfaces= (derives) — must surface."""
        cls = _make_element(
            "class",
            "MyStruct",
            1,
            20,
            class_type="struct",
            # Rust sets implements_interfaces for derives; no superclass.
            extends_class=None,
            implements_interfaces=["Debug", "Clone"],
            superclass=None,
            interfaces=[],
        )
        result = _make_analysis_result(
            elements=[cls], file_path="/p/lib.rs", language="rust"
        )
        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)
        cls_out = outline["classes"][0]
        assert cls_out["extends"] is None
        assert cls_out["implements"] == ["Debug", "Clone"]

    def test_method_string_parameters(self):
        """当 parameters 是字符串列表时，应原样保留到大纲。"""
        cls = self._make_class_elem("A", 1, 50)
        m = self._make_method_elem(
            "doIt", 10, 20, parameters=["String name", "int count"]
        )
        result = _make_analysis_result(elements=[cls, m])

        with self._patch_is_element_of_type():
            outline = self.tool._build_outline(result, False, False)

        method = outline["classes"][0]["methods"][0]
        assert "String name" in method["parameters"]
        assert "int count" in method["parameters"]


# ---------------------------------------------------------------------------
# execute 异步测试（mock 文件系统 + 分析引擎）
# ---------------------------------------------------------------------------


class TestGetCodeOutlineToolExecute:
    """测试 execute 方法（全部外部依赖均 mock）。"""

    def setup_method(self):
        self.tool = GetCodeOutlineTool()

    def _make_mock_result(self):
        cls = MagicMock()
        cls.element_type = "class"
        cls.name = "MyService"
        cls.start_line = 5
        cls.end_line = 50
        cls.class_type = "class"
        cls.extends_class = None
        cls.implements_interfaces = []

        method = MagicMock()
        method.element_type = "function"
        method.name = "execute"
        method.start_line = 10
        method.end_line = 20
        method.return_type = "void"
        method.visibility = "public"
        method.is_constructor = False
        method.is_static = False
        method.parameters = []

        return _make_analysis_result(elements=[cls, method])

    @pytest.mark.asyncio
    async def test_execute_returns_success(self):
        """正常路径下 execute 应返回 success=True 及 outline。"""

        mock_result = self._make_mock_result()

        with (
            patch.object(
                self.tool,
                "resolve_and_validate_file_path",
                return_value="/proj/MyService.java",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.Path"
            ) as mock_path,
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.detect_language_from_file",
                return_value="java",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.is_element_of_type",
                side_effect=lambda e, t: getattr(e, "element_type", "") == t,
            ),
        ):
            mock_path.return_value.exists.return_value = True
            self.tool.analysis_engine.analyze = AsyncMock(return_value=mock_result)

            # 显式请求 JSON 格式以便测试结构
            response = await self.tool.execute(
                {"file_path": "MyService.java", "output_format": "json"}
            )

        # JSON output is now returned as a plain dict (post-1.12 dogfood
        # cleanup). The previous ``{"content":[{"text": ...}]}`` envelope
        # was MCP transport scaffolding leaking through the tool layer.
        assert isinstance(response, dict)
        assert response["success"] is True
        assert "outline" in response
        outline = response["outline"]
        assert outline["language"] == "java"
        assert len(outline["classes"]) == 1
        assert outline["classes"][0]["name"] == "MyService"
        # Top-level hoisted fields stay in sync with the outline.
        assert response["language"] == "java"
        assert response["class_count"] == 1
        assert response["classes"][0]["name"] == "MyService"

    @pytest.mark.asyncio
    async def test_execute_missing_file_path_raises(self):
        """缺少 file_path 时 execute 应抛出 ValueError。"""
        with pytest.raises(ValueError, match="file_path"):
            await self.tool.execute({})

    @pytest.mark.asyncio
    async def test_execute_file_not_found_raises(self):
        """文件不存在时 execute 应抛出 ValueError。"""
        with (
            patch.object(
                self.tool,
                "resolve_and_validate_file_path",
                return_value="/proj/Missing.java",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.Path"
            ) as mock_path,
        ):
            mock_path.return_value.exists.return_value = False
            with pytest.raises(ValueError, match="File not found"):
                await self.tool.execute({"file_path": "Missing.java"})

    @pytest.mark.asyncio
    async def test_execute_analysis_failure_raises(self):
        """分析引擎返回 None 时 execute 应抛出 RuntimeError。"""
        with (
            patch.object(
                self.tool,
                "resolve_and_validate_file_path",
                return_value="/proj/Foo.java",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.Path"
            ) as mock_path,
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.detect_language_from_file",
                return_value="java",
            ),
        ):
            mock_path.return_value.exists.return_value = True
            self.tool.analysis_engine.analyze = AsyncMock(return_value=None)
            with pytest.raises(RuntimeError, match="Failed to analyze"):
                await self.tool.execute({"file_path": "Foo.java"})

    @pytest.mark.asyncio
    async def test_execute_uses_provided_language(self):
        """提供 language 参数时不调用 detect_language_from_file。"""
        mock_result = self._make_mock_result()

        with (
            patch.object(
                self.tool,
                "resolve_and_validate_file_path",
                return_value="/proj/Foo.java",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.Path"
            ) as mock_path,
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.detect_language_from_file"
            ) as mock_detect,
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.is_element_of_type",
                side_effect=lambda e, t: getattr(e, "element_type", "") == t,
            ),
        ):
            mock_path.return_value.exists.return_value = True
            self.tool.analysis_engine.analyze = AsyncMock(return_value=mock_result)
            await self.tool.execute({"file_path": "Foo.java", "language": "python"})
            mock_detect.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_with_include_fields(self):
        """include_fields=True 时 outline.classes[*] 含 fields 键。"""

        field = MagicMock()
        field.element_type = "variable"
        field.name = "count"
        field.start_line = 6
        field.end_line = 6
        field.field_type = "int"
        field.visibility = "private"
        field.is_static = False

        cls = MagicMock()
        cls.element_type = "class"
        cls.name = "Counter"
        cls.start_line = 5
        cls.end_line = 50
        cls.class_type = "class"
        cls.extends_class = None
        cls.implements_interfaces = []

        mock_result = _make_analysis_result(elements=[cls, field])

        with (
            patch.object(
                self.tool,
                "resolve_and_validate_file_path",
                return_value="/proj/Counter.java",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.Path"
            ) as mock_path,
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.detect_language_from_file",
                return_value="java",
            ),
            patch(
                "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.is_element_of_type",
                side_effect=lambda e, t: getattr(e, "element_type", "") == t,
            ),
        ):
            mock_path.return_value.exists.return_value = True
            self.tool.analysis_engine.analyze = AsyncMock(return_value=mock_result)
            # 显式请求 JSON 格式以便测试结构
            response = await self.tool.execute(
                {
                    "file_path": "Counter.java",
                    "include_fields": True,
                    "output_format": "json",
                }
            )

        # JSON output is now a plain dict (post-1.12 dogfood cleanup).
        assert isinstance(response, dict)
        assert "fields" in response["outline"]["classes"][0]
        assert response["outline"]["classes"][0]["fields"][0]["name"] == "count"


# ---------------------------------------------------------------------------
# 工具定义测试
# ---------------------------------------------------------------------------


class TestGetCodeOutlineToolDefinition:
    """测试 get_tool_definition 和 get_tool_schema。"""

    def setup_method(self):
        self.tool = GetCodeOutlineTool()

    def test_tool_description_mentions_outline(self):
        """工具描述应提及 outline。"""
        defn = self.tool.get_tool_definition()
        assert "outline" in defn["description"].lower()

    def test_schema_requires_file_path(self):
        """JSON schema 的 required 应包含 file_path。"""
        schema = self.tool.get_tool_schema()
        assert "file_path" in schema["required"]

    def test_schema_no_additional_properties(self):
        """schema 应禁止额外属性。"""
        schema = self.tool.get_tool_schema()
        assert schema.get("additionalProperties") is False

    def test_schema_optional_fields(self):
        """schema 应定义 language、include_fields、include_imports 属性。"""
        schema = self.tool.get_tool_schema()
        props = schema["properties"]
        assert "language" in props
        assert "include_fields" in props
        assert "include_imports" in props

    def test_input_schema_present(self):
        """get_tool_definition 的 inputSchema 应与 get_tool_schema 一致。"""
        defn = self.tool.get_tool_definition()
        schema = self.tool.get_tool_schema()
        assert defn["inputSchema"] == schema
