"""Issue #456 — Go receiver methods nested under their struct in structure/outline.

Before this fix (P2): methods like ``func (s *Service) Name()`` landed in
``top_level_functions`` and every struct had ``methods: []`` — an agent asking
"what methods does Service have" got an empty list.

After this fix: receiver_type-based association groups those methods under their
struct so ``Service.methods == [Name, IsRunning, Start, run, tick, Stop, stop]``
and ``top_level_functions`` contains only true free functions.

Test plan (RED-first):
1. Unit: mock elements — method with receiver_type outside cls range → should
   appear in cls.methods, not top_level_functions.
2. Integration: parse real ``examples/sample.go`` via the Go plugin and verify
   exact counts and names via ``_build_outline``.
3. Rust: same receiver_type mechanism — verify Rust impl-block methods also
   nest under their struct in the outline.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers (mirrors test_get_code_outline_tool.py helpers)
# ---------------------------------------------------------------------------


def _make_element(
    element_type: str, name: str, start: int, end: int, **kw
) -> MagicMock:
    elem = MagicMock()
    elem.element_type = element_type
    elem.name = name
    elem.start_line = start
    elem.end_line = end
    elem.receiver_type = kw.get("receiver_type", None)
    elem.is_method = kw.get("is_method", False)
    elem.return_type = kw.get("return_type", "void")
    elem.visibility = kw.get("visibility", "public")
    elem.is_constructor = kw.get("is_constructor", False)
    elem.is_static = kw.get("is_static", False)
    elem.parameters = kw.get("parameters", [])
    elem.class_type = kw.get("class_type", "class")
    elem.extends_class = kw.get("extends_class", None)
    elem.implements_interfaces = kw.get("implements_interfaces", [])
    elem.field_type = kw.get("field_type", "Unknown")
    return elem


def _make_result(
    elements: list, file_path: str = "/p/foo.go", language: str = "go"
) -> MagicMock:
    r = MagicMock()
    r.elements = elements
    r.file_path = file_path
    r.language = language
    r.line_count = 300
    r.success = True
    return r


def _patch_is_elem():
    """Patch is_element_of_type to compare element_type strings directly."""

    def _mock(elem, type_const):
        return getattr(elem, "element_type", "") == type_const

    return patch(
        "tree_sitter_analyzer.mcp.tools.get_code_outline_tool.is_element_of_type",
        side_effect=_mock,
    )


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------


class TestNormalizeReceiverType:
    """_normalize_receiver_type helper."""

    def test_strips_pointer_prefix(self) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            _normalize_receiver_type,
        )

        assert _normalize_receiver_type("*Counter") == "Counter"
        assert _normalize_receiver_type("*Service") == "Service"

    def test_no_star_unchanged(self) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            _normalize_receiver_type,
        )

        assert _normalize_receiver_type("Counter") == "Counter"

    def test_none_returns_none(self) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            _normalize_receiver_type,
        )

        assert _normalize_receiver_type(None) is None
        assert _normalize_receiver_type("") is None


class TestMethodOwnedByClass:
    """_method_owned_by_class helper."""

    def test_line_range_containment(self) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            _method_owned_by_class,
        )

        m = _make_element("function", "foo", 15, 20)
        assert _method_owned_by_class(m, "Bar", 10, 80) is True

    def test_line_range_miss_no_receiver(self) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            _method_owned_by_class,
        )

        m = _make_element("function", "standalone", 100, 110)
        assert _method_owned_by_class(m, "Bar", 10, 80) is False

    def test_receiver_type_match_pointer(self) -> None:
        """Go pointer receiver: receiver_type='*Service' → normalized 'Service' matches."""
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            _method_owned_by_class,
        )

        m = _make_element("function", "Name", 89, 91, receiver_type="*Service")
        # method is outside struct range (71-77)
        assert _method_owned_by_class(m, "Service", 71, 77) is True

    def test_receiver_type_match_no_pointer(self) -> None:
        """Go value receiver: receiver_type='Service' → matches."""
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            _method_owned_by_class,
        )

        m = _make_element("function", "Get", 89, 91, receiver_type="Service")
        assert _method_owned_by_class(m, "Service", 71, 77) is True

    def test_receiver_type_mismatch(self) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            _method_owned_by_class,
        )

        m = _make_element("function", "Start", 221, 226, receiver_type="*WorkerPool")
        # Does NOT belong to Service
        assert _method_owned_by_class(m, "Service", 71, 77) is False


class TestInClassRanges:
    """_in_class_ranges helper — backward-compat and new class_names path."""

    def test_old_signature_still_works(self) -> None:
        """No class_names → pure line-range check (backward compat)."""
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            _in_class_ranges,
        )

        m = _make_element("function", "foo", 15, 20)
        assert _in_class_ranges(m, [(10, 80)]) is True
        assert _in_class_ranges(m, [(100, 200)]) is False

    def test_receiver_type_detected_with_class_names(self) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            _in_class_ranges,
        )

        m = _make_element("function", "Name", 89, 91, receiver_type="*Service")
        # range (71, 77) does not contain 89, but class_name='Service' matches
        assert _in_class_ranges(m, [(71, 77)], ["Service"]) is True

    def test_no_match_with_class_names(self) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            _in_class_ranges,
        )

        m = _make_element(
            "function", "Chain", 257, 264
        )  # free function, no receiver_type
        assert _in_class_ranges(m, [(71, 77)], ["Service"]) is False


# ---------------------------------------------------------------------------
# Unit tests: _build_outline integration (mock elements)
# ---------------------------------------------------------------------------


class TestBuildOutlineGoReceiverAssociation:
    """End-to-end outline builder with mock Go elements."""

    def setup_method(self) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            GetCodeOutlineTool,
        )

        self.tool = GetCodeOutlineTool()

    def test_go_method_with_pointer_receiver_nested_under_struct(self) -> None:
        """func (s *Service) Name() should appear in Service.methods, NOT top_level_functions."""
        struct = _make_element("class", "Service", 71, 77, class_type="struct")
        method = _make_element(
            "function",
            "Name",
            89,
            91,
            receiver_type="*Service",
            is_method=True,
            return_type="string",
        )
        free_fn = _make_element(
            "function", "NewService", 80, 86, return_type="*Service"
        )

        result = _make_result([struct, method, free_fn])
        with _patch_is_elem():
            outline = self.tool._build_outline(result, False, False)

        assert len(outline["classes"]) == 1
        svc = outline["classes"][0]
        assert svc["name"] == "Service"
        # Method is nested under struct
        assert len(svc["methods"]) == 1
        assert svc["methods"][0]["name"] == "Name"
        # Only the true free function is at top-level
        assert len(outline["top_level_functions"]) == 1
        assert outline["top_level_functions"][0]["name"] == "NewService"

    def test_go_value_receiver_nested_under_struct(self) -> None:
        """func (s Service) Get() — value receiver (no *) also associates."""
        struct = _make_element("class", "Counter", 5, 8, class_type="struct")
        method = _make_element(
            "function",
            "Get",
            15,
            17,
            receiver_type="Counter",
            is_method=True,
            return_type="int",
        )
        result = _make_result([struct, method])
        with _patch_is_elem():
            outline = self.tool._build_outline(result, False, False)

        assert len(outline["classes"][0]["methods"]) == 1
        assert outline["top_level_functions"] == []

    def test_multiple_structs_each_get_correct_methods(self) -> None:
        """Service.methods and WorkerPool.methods stay separate."""
        service = _make_element("class", "Service", 71, 77, class_type="struct")
        worker_pool = _make_element(
            "class", "WorkerPool", 206, 210, class_type="struct"
        )
        svc_method = _make_element(
            "function", "Name", 89, 91, receiver_type="*Service", is_method=True
        )
        wp_method = _make_element(
            "function", "Start", 221, 226, receiver_type="*WorkerPool", is_method=True
        )
        free_fn = _make_element("function", "NewService", 80, 86)

        result = _make_result([service, worker_pool, svc_method, wp_method, free_fn])
        with _patch_is_elem():
            outline = self.tool._build_outline(result, False, False)

        names = {c["name"]: c for c in outline["classes"]}
        assert len(names["Service"]["methods"]) == 1
        assert names["Service"]["methods"][0]["name"] == "Name"
        assert len(names["WorkerPool"]["methods"]) == 1
        assert names["WorkerPool"]["methods"][0]["name"] == "Start"
        assert len(outline["top_level_functions"]) == 1

    def test_free_function_stays_top_level(self) -> None:
        """NewService (no receiver) stays at top_level_functions."""
        struct = _make_element("class", "Service", 71, 77, class_type="struct")
        free_fn = _make_element("function", "NewService", 80, 86)

        result = _make_result([struct, free_fn])
        with _patch_is_elem():
            outline = self.tool._build_outline(result, False, False)

        assert outline["classes"][0]["methods"] == []
        assert len(outline["top_level_functions"]) == 1
        assert outline["top_level_functions"][0]["name"] == "NewService"


# ---------------------------------------------------------------------------
# Integration test: real sample.go parsed via GoPlugin
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Unit tests: P2 single-ownership invariant
# ---------------------------------------------------------------------------


class TestSingleOwnershipInvariant:
    """P2: Each method is assigned to exactly one class (or zero).

    A method cannot land in both classes A.methods and B.methods.
    Precedence: line-range containment wins over receiver_type matching.
    """

    def setup_method(self) -> None:
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            GetCodeOutlineTool,
        )

        self.tool = GetCodeOutlineTool()

    def test_method_inside_class_range_takes_precedence_over_receiver_type(
        self,
    ) -> None:
        """Method in A's range with receiver_type=B → goes to A, not B."""
        class_a = _make_element("class", "A", 10, 40, class_type="struct")
        class_b = _make_element("class", "B", 50, 80, class_type="struct")
        # Method is inside A's range (10-40) but receiver_type points to B
        method = _make_element(
            "function", "Foo", 25, 27, receiver_type="B", is_method=True
        )
        result = _make_result([class_a, class_b, method])
        with _patch_is_elem():
            outline = self.tool._build_outline(result, False, False)

        class_dict = {c["name"]: c for c in outline["classes"]}
        # Method appears in A (line-range wins)
        assert len(class_dict["A"]["methods"]) == 1
        assert class_dict["A"]["methods"][0]["name"] == "Foo"
        # Method does NOT appear in B (claimed by A first)
        assert len(class_dict["B"]["methods"]) == 0
        # Method does not appear in top_level_functions either
        assert len(outline["top_level_functions"]) == 0
        # Assert total method count across all classes == 1 (single ownership)
        total_methods = sum(len(c["methods"]) for c in outline["classes"]) + len(
            outline["top_level_functions"]
        )
        assert total_methods == 1, (
            f"Method should appear in exactly one place; got {total_methods}"
        )

    def test_multiple_methods_never_double_counted(self) -> None:
        """Three methods: two in A's range, one with A's receiver_type outside range."""
        class_a = _make_element("class", "A", 10, 30, class_type="struct")
        # Inside range
        m1 = _make_element("function", "M1", 15, 17, is_method=True)
        m2 = _make_element("function", "M2", 20, 22, is_method=True)
        # Outside range, but receiver_type=A
        m3 = _make_element("function", "M3", 50, 52, receiver_type="A", is_method=True)
        result = _make_result([class_a, m1, m2, m3])
        with _patch_is_elem():
            outline = self.tool._build_outline(result, False, False)

        # All 3 methods should nest under A (2 by line, 1 by receiver)
        assert len(outline["classes"]) == 1
        assert len(outline["classes"][0]["methods"]) == 3
        # sum of all appearances == 3
        total = sum(len(c["methods"]) for c in outline["classes"]) + len(
            outline["top_level_functions"]
        )
        assert total == 3, f"Three methods should appear once each; got {total} total"


class TestGoSampleIntegration:
    """Parse examples/sample.go end-to-end and verify exact association counts."""

    @pytest.fixture(autouse=True)
    def _check_deps(self) -> None:
        pytest.importorskip("tree_sitter_go", reason="tree-sitter-go not installed")

    def _build_outline_for_go_sample(self) -> dict:
        import asyncio
        from pathlib import Path

        from tree_sitter_analyzer.core.analysis_engine import (
            AnalysisRequest,
            get_analysis_engine,
        )
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            GetCodeOutlineTool,
        )

        sample = Path("examples/sample.go")
        if not sample.exists():
            pytest.skip("examples/sample.go not found")

        engine = get_analysis_engine(str(sample.parent.parent))
        request = AnalysisRequest(
            file_path=str(sample.resolve()),
            language="go",
            include_complexity=False,
            include_details=True,
        )
        result = asyncio.run(engine.analyze(request))
        assert result is not None, "Engine returned None"
        assert getattr(result, "success", True) is not False, (
            f"Engine failed: {getattr(result, 'error_message', '?')}"
        )

        tool = GetCodeOutlineTool()
        return tool._build_outline(result, include_fields=False, include_imports=False)

    def test_service_struct_has_correct_method_count(self) -> None:
        """Service should have exactly 7 receiver methods nested under it."""
        outline = self._build_outline_for_go_sample()
        by_name = {c["name"]: c for c in outline["classes"]}
        assert "Service" in by_name, (
            f"Service struct not found; classes={[c['name'] for c in outline['classes']]}"
        )
        svc_methods = by_name["Service"]["methods"]
        method_names = sorted(m["name"] for m in svc_methods)
        assert method_names == sorted(
            ["Name", "IsRunning", "Start", "run", "tick", "Stop", "stop"]
        ), f"got {method_names}"
        assert len(svc_methods) == 7

    def test_worker_pool_struct_has_correct_method_count(self) -> None:
        """WorkerPool should have exactly 4 receiver methods."""
        outline = self._build_outline_for_go_sample()
        by_name = {c["name"]: c for c in outline["classes"]}
        assert "WorkerPool" in by_name
        wp_methods = by_name["WorkerPool"]["methods"]
        method_names = sorted(m["name"] for m in wp_methods)
        assert method_names == sorted(["Start", "worker", "Submit", "Shutdown"]), (
            f"got {method_names}"
        )
        assert len(wp_methods) == 4

    def test_top_level_functions_are_free_functions_only(self) -> None:
        """top_level_functions must contain only non-receiver functions."""
        outline = self._build_outline_for_go_sample()
        top_names = sorted(fn["name"] for fn in outline["top_level_functions"])
        # NewService, ProcessData, process, NewWorkerPool, Chain, WithTimeout, WithRetry
        expected = sorted(
            [
                "NewService",
                "ProcessData",
                "process",
                "NewWorkerPool",
                "Chain",
                "WithTimeout",
                "WithRetry",
            ]
        )
        assert top_names == expected, f"got {top_names}"
        assert len(outline["top_level_functions"]) == 7

    def test_total_method_count_unchanged(self) -> None:
        """statistics.method_count == 20: 18 receiver methods + Reader.Read and
        Writer.Write interface signatures (owned via receiver_type since #588)."""
        outline = self._build_outline_for_go_sample()
        assert outline["statistics"]["method_count"] == 20

    def test_interface_method_signatures_nested_under_interface(self) -> None:
        """#588: Reader/Writer interfaces own their method signatures."""
        outline = self._build_outline_for_go_sample()
        by_name = {c["name"]: c for c in outline["classes"]}
        assert [m["name"] for m in by_name["Reader"]["methods"]] == ["Read"]
        assert [m["name"] for m in by_name["Writer"]["methods"]] == ["Write"]
        # Embedding-only interface gains no phantom methods.
        assert by_name["ReadWriter"]["methods"] == []


# ---------------------------------------------------------------------------
# Rust integration test — Rust impl methods also benefit from receiver_type fix
# ---------------------------------------------------------------------------


class TestCrossFileScopes:
    """Known limitation: receiver_type matching is per-file only.

    A method with receiver_type="Service" in the analysis result while NO class
    named Service exists in the same result will NOT be assigned to any class.
    It will remain in top_level_functions.

    This is a documented scope limitation — cross-file resolution is not
    supported. To fix this would require symbol resolution across file
    boundaries, which is out of scope for the outline builder.
    """

    def test_method_with_unknown_receiver_type_stays_top_level(self) -> None:
        """Method with receiver_type='Service' but NO Service class in result."""
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            GetCodeOutlineTool,
        )

        # Define only a Counter struct; method has receiver_type="Service"
        # (referencing a struct that exists in a different file).
        counter = _make_element("class", "Counter", 5, 8, class_type="struct")
        unknown_receiver_method = _make_element(
            "function",
            "Name",
            20,
            22,
            receiver_type="Service",
            is_method=True,
        )
        result = _make_result([counter, unknown_receiver_method])
        tool = GetCodeOutlineTool()
        with _patch_is_elem():
            outline = tool._build_outline(result, False, False)

        # Method should NOT be in Counter.methods (different receiver_type).
        assert len(outline["classes"][0]["methods"]) == 0, (
            "Method with unknown receiver_type should not land in unrelated class"
        )
        # Method should stay in top_level_functions (cross-file limitation).
        assert len(outline["top_level_functions"]) == 1, (
            "Method with unknown receiver_type stays top-level due to per-file scope"
        )
        assert outline["top_level_functions"][0]["name"] == "Name"


class TestRustImplMethodAssociation:
    """Rust impl-block methods should nest under their struct via receiver_type."""

    @pytest.fixture(autouse=True)
    def _check_deps(self) -> None:
        pytest.importorskip("tree_sitter_rust", reason="tree-sitter-rust not installed")

    RUST_SRC = """\
struct Counter { n: i32 }

impl Counter {
    fn inc(&mut self) { self.n += 1; }
    fn get(&self) -> i32 { self.n }
}

fn standalone() {}
"""

    def _build_outline(self) -> dict:
        import tree_sitter
        import tree_sitter_rust

        from tree_sitter_analyzer.languages.rust_plugin import RustElementExtractor
        from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import (
            GetCodeOutlineTool,
        )

        lang = tree_sitter.Language(tree_sitter_rust.language())
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(self.RUST_SRC.encode())
        extractor = RustElementExtractor()
        extractor._source_code = self.RUST_SRC

        classes = extractor.extract_classes(tree, self.RUST_SRC)
        functions = extractor.extract_functions(tree, self.RUST_SRC)

        elements = classes + functions

        result = MagicMock()
        result.elements = elements
        result.file_path = "/tmp/sample.rs"
        result.language = "rust"
        result.line_count = 10
        result.success = True

        tool = GetCodeOutlineTool()
        return tool._build_outline(result, include_fields=False, include_imports=False)

    def test_rust_impl_method_nested_under_struct(self) -> None:
        """inc and get should appear in Counter.methods, not top_level_functions."""
        outline = self._build_outline()
        struct_names = [c["name"] for c in outline["classes"]]
        assert "Counter" in struct_names, f"Counter not found; classes={struct_names}"
        counter = next(c for c in outline["classes"] if c["name"] == "Counter")
        method_names = sorted(m["name"] for m in counter["methods"])
        assert method_names == sorted(["inc", "get"]), f"got {method_names}"
        assert len(counter["methods"]) == 2

    def test_rust_free_function_stays_top_level(self) -> None:
        outline = self._build_outline()
        top_names = [fn["name"] for fn in outline["top_level_functions"]]
        assert "standalone" in top_names, f"got {top_names}"
        assert len(outline["top_level_functions"]) == 1
