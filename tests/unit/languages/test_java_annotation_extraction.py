"""
TDD tests for Java annotation extraction quality.

Validated against spring-petclinic open source project.
These tests capture the bugs found and the expected correct behavior.

Bug history (all fixed 2026-04-09):
  Bug1+2: Wrong extraction order + _reset_caches() cleared source data
  Bug3:   analyze_code_structure_tool hardcoded annotations=[]
  Bug4:   field_declaration missing from container_node_types
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

# Spring-petclinic paths — tests skip gracefully if project not cloned
PETCLINIC_BASE = Path("/workspaces/claude-source-run-version/spring-petclinic")
OWNER_CONTROLLER = PETCLINIC_BASE / "src/main/java/org/springframework/samples/petclinic/owner/OwnerController.java"
VET = PETCLINIC_BASE / "src/main/java/org/springframework/samples/petclinic/vet/Vet.java"

pytestmark = pytest.mark.skipif(
    not PETCLINIC_BASE.exists(),
    reason="spring-petclinic not cloned at expected path",
)


@pytest.fixture
def mcp_server():
    """MCP server pointed at spring-petclinic."""
    from tree_sitter_analyzer.mcp.server import TreeSitterAnalyzerMCPServer
    return TreeSitterAnalyzerMCPServer(str(PETCLINIC_BASE))


def call(coro):
    """Run async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Bug 1+2: Annotation extraction order + _reset_caches source-data clearing
# ---------------------------------------------------------------------------

class TestAnnotationExtractionOrder:
    """extract_annotations() must run before extract_functions/extract_classes
    and _reset_caches() must NOT clear self.annotations (source data)."""

    def test_annotations_preserved_after_extract_functions(self):
        """self.annotations must survive a call to extract_functions()."""
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        src = """
@Controller
public class FooController {
    @GetMapping("/foo")
    public String doFoo() { return "foo"; }
}
"""
        JAVA_LANG = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = JAVA_LANG
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        # Step 1: populate annotations
        annotations = ext.extract_annotations(tree, src)
        assert len(annotations) >= 2, "Should find @Controller and @GetMapping"

        # Step 2: extract_functions calls _reset_caches internally (side effect is the point)
        ext.extract_functions(tree, src)

        # Step 3: self.annotations must still be populated (Bug 2 fix)
        assert len(ext.annotations) >= 2, (
            "_reset_caches() must not clear self.annotations; "
            "it is source data set by extract_annotations(), not a lookup cache"
        )

    def test_methods_carry_annotations_from_extract_elements(self):
        """extract_elements() must return functions with non-empty annotations."""
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaPlugin

        src = """
@Controller
public class FooController {
    @GetMapping("/foo")
    public String doFoo() { return "foo"; }

    @PostMapping("/bar")
    public String doBar() { return "bar"; }
}
"""
        JAVA_LANG = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = JAVA_LANG
        tree = parser.parse(src.encode())

        plugin = JavaPlugin()
        elements = plugin.extract_elements(tree, src)

        methods_with_annotations = [
            m for m in elements.get("functions", [])
            if m.annotations
        ]
        assert len(methods_with_annotations) >= 2, (
            "Methods with @GetMapping and @PostMapping must have annotations "
            "extracted. Bug: extract_elements called extract_functions before "
            "extract_annotations, leaving self.annotations empty."
        )

    def test_reset_caches_preserves_annotations(self):
        """_reset_caches() must clear lookup caches but preserve self.annotations."""
        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        ext = JavaElementExtractor()
        ext.annotations.append({"name": "Controller", "line": 1})

        ext._reset_caches()

        # Lookup caches cleared
        assert len(ext._annotation_cache) == 0
        assert len(ext._node_text_cache) == 0

        # Source data preserved (Bug 2 fix)
        assert len(ext.annotations) == 1, (
            "self.annotations is source data from extract_annotations(); "
            "_reset_caches() must not clear it."
        )


# ---------------------------------------------------------------------------
# Bug 3: analyze_code_structure_tool hardcoded annotations=[]
# ---------------------------------------------------------------------------

class TestMCPToolAnnotationOutput:
    """MCP analyze_code_structure must surface annotations from model objects."""

    def test_owner_controller_class_has_controller_annotation(self, mcp_server):
        """OwnerController class must have @Controller in output."""
        r = call(mcp_server.call_tool("analyze_code_structure", {
            "file_path": str(OWNER_CONTROLLER),
        }))
        classes = r.get("elements", {}).get("classes", [])
        assert classes, "Should extract at least one class"

        owner_ctrl = next((c for c in classes if c.get("name") == "OwnerController"), None)
        assert owner_ctrl is not None

        ann_names = [a.get("name") for a in owner_ctrl.get("annotations", [])]
        assert "Controller" in ann_names, (
            f"OwnerController must have @Controller annotation. Got: {ann_names}. "
            "Bug: analyze_code_structure_tool.py hardcoded 'annotations': []"
        )

    def test_owner_controller_methods_have_mapping_annotations(self, mcp_server):
        """Methods with @GetMapping/@PostMapping must have those annotations in output."""
        r = call(mcp_server.call_tool("analyze_code_structure", {
            "file_path": str(OWNER_CONTROLLER),
        }))
        methods = r.get("elements", {}).get("methods", [])

        annotated_methods = {
            m.get("name"): [a.get("name") for a in m.get("annotations", [])]
            for m in methods
            if m.get("annotations")
        }

        # initCreationForm has @GetMapping("/owners/new")
        assert "initCreationForm" in annotated_methods, (
            "initCreationForm() must have @GetMapping annotation"
        )
        assert "GetMapping" in annotated_methods.get("initCreationForm", [])

        # processCreationForm has @PostMapping("/owners/new")
        assert "processCreationForm" in annotated_methods, (
            "processCreationForm() must have @PostMapping annotation"
        )
        assert "PostMapping" in annotated_methods.get("processCreationForm", [])

    def test_model_attribute_method_has_annotation(self, mcp_server):
        """findOwner() with @ModelAttribute must have that annotation."""
        r = call(mcp_server.call_tool("analyze_code_structure", {
            "file_path": str(OWNER_CONTROLLER),
        }))
        methods = r.get("elements", {}).get("methods", [])
        find_owner = next((m for m in methods if m.get("name") == "findOwner"), None)
        assert find_owner is not None

        ann_names = [a.get("name") for a in find_owner.get("annotations", [])]
        assert "ModelAttribute" in ann_names, (
            f"findOwner() must have @ModelAttribute. Got: {ann_names}"
        )


# ---------------------------------------------------------------------------
# Bug 4: field_declaration missing from container_node_types
# ---------------------------------------------------------------------------

class TestFieldAnnotationExtraction:
    """Field-level annotations must be extracted (field_declaration in containers)."""

    def test_vet_specialties_has_manytomany_annotation(self, mcp_server):
        """Vet.specialties field must have @ManyToMany annotation."""
        r = call(mcp_server.call_tool("analyze_code_structure", {
            "file_path": str(VET),
        }))
        fields = r.get("elements", {}).get("fields", [])
        specialties = next((f for f in fields if f.get("name") == "specialties"), None)
        assert specialties is not None, "Should find specialties field"

        ann_names = [a.get("name") for a in specialties.get("annotations", [])]
        assert "ManyToMany" in ann_names, (
            f"specialties field must have @ManyToMany. Got: {ann_names}. "
            "Bug: field_declaration was missing from container_node_types, "
            "so the traversal never descended into field modifier nodes."
        )

    def test_vet_specialties_has_jointable_annotation(self, mcp_server):
        """Vet.specialties field must have @JoinTable annotation."""
        r = call(mcp_server.call_tool("analyze_code_structure", {
            "file_path": str(VET),
        }))
        fields = r.get("elements", {}).get("fields", [])
        specialties = next((f for f in fields if f.get("name") == "specialties"), None)
        assert specialties is not None

        ann_names = [a.get("name") for a in specialties.get("annotations", [])]
        assert "JoinTable" in ann_names, (
            f"specialties field must have @JoinTable. Got: {ann_names}"
        )

    def test_annotation_text_includes_parameters(self, mcp_server):
        """Annotation text must include parameters, not just name."""
        r = call(mcp_server.call_tool("analyze_code_structure", {
            "file_path": str(VET),
        }))
        fields = r.get("elements", {}).get("fields", [])
        specialties = next((f for f in fields if f.get("name") == "specialties"), None)
        assert specialties is not None

        many_to_many = next(
            (a for a in specialties.get("annotations", []) if a.get("name") == "ManyToMany"),
            None,
        )
        assert many_to_many is not None
        assert "EAGER" in many_to_many.get("text", ""), (
            "Annotation text must include parameters: "
            f"@ManyToMany(fetch = FetchType.EAGER). Got: {many_to_many}"
        )

    def test_field_annotation_extraction_pure_unit(self):
        """Unit test: field annotations extracted without MCP server."""
        import tree_sitter
        import tree_sitter_java as ts_java

        from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor

        src = """
public class Entity {
    @Column(name = "user_id", nullable = false)
    @NotNull
    private Long userId;
}
"""
        JAVA_LANG = tree_sitter.Language(ts_java.language())
        parser = tree_sitter.Parser()
        parser.language = JAVA_LANG
        tree = parser.parse(src.encode())

        ext = JavaElementExtractor()
        ext.extract_annotations(tree, src)
        fields = ext.extract_variables(tree, src)

        user_id_field = next((f for f in fields if f.name == "userId"), None)
        assert user_id_field is not None

        ann_names = [a.get("name") for a in user_id_field.annotations]
        assert "Column" in ann_names, f"Should extract @Column. Got: {ann_names}"
        assert "NotNull" in ann_names, f"Should extract @NotNull. Got: {ann_names}"
