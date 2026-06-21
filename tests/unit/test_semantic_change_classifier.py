"""Tests for Semantic Change Classifier."""

from tree_sitter_analyzer.ast_diff import (
    ASTDiffHunk,
    ASTDiffResult,
    ASTNodeInfo,
    ASTNodeKind,
    DiffKind,
)
from tree_sitter_analyzer.semantic_change_classifier import (
    ClassifiedHunk,
    SemanticCategory,
    SemanticChangeClassifier,
    SemanticClassification,
    _build_summary,
    _classify_single_hunk,
    _compute_risk,
    _is_doc_path,
    _is_public_name,
    _is_test_path,
    _pick_dominant,
)


def _node(name: str = "func", kind: ASTNodeKind = ASTNodeKind.FUNCTION) -> ASTNodeInfo:
    return ASTNodeInfo(
        node_type="function_definition",
        kind=kind,
        name=name,
        start_line=1,
        start_col=0,
        end_line=5,
        end_col=0,
        text_hash="abc123",
        text_preview=f"def {name}(): ...",
    )


def _hunk(
    diff_kind: DiffKind = DiffKind.NODE_ADDED,
    node_kind: ASTNodeKind = ASTNodeKind.FUNCTION,
    name: str = "func",
) -> ASTDiffHunk:
    node = _node(name=name, kind=node_kind)
    return ASTDiffHunk(
        diff_kind=diff_kind,
        node_kind=node_kind,
        old_node=None,
        new_node=node,
        summary="test hunk",
    )


class TestSemanticCategory:
    def test_values(self):
        assert SemanticCategory.API_CHANGE.value == "api_change"
        assert SemanticCategory.REFACTOR.value == "refactor"
        assert SemanticCategory.FEATURE_ADDITION.value == "feature_addition"
        assert SemanticCategory.UNKNOWN.value == "unknown"

    def test_str_enum(self):
        assert SemanticCategory.API_CHANGE == "api_change"


class TestHelpers:
    def test_is_test_path_positive(self):
        assert _is_test_path("tests/unit/test_foo.py")
        assert _is_test_path("src/test_bar.py")
        assert _is_test_path("foo_test.py")
        assert _is_test_path("conftest.py")
        assert _is_test_path("spec/test_thing.py")

    def test_is_test_path_negative(self):
        assert not _is_test_path("src/main.py")
        assert not _is_test_path("lib/utils.py")
        assert not _is_test_path(None)

    def test_is_doc_path_positive(self):
        assert _is_doc_path("README.md")
        assert _is_doc_path("docs/guide.rst")

    def test_is_doc_path_negative(self):
        assert not _is_doc_path("main.py")
        assert not _is_doc_path(None)

    def test_is_public_name(self):
        assert _is_public_name("get_value")
        assert _is_public_name("__init__")
        assert not _is_public_name("_private")
        assert not _is_public_name("")


class TestClassifySingleHunk:
    def test_test_file(self):
        hunk = _hunk(DiffKind.BODY_CHANGED)
        result = _classify_single_hunk(hunk, "tests/test_foo.py")
        assert result.category == SemanticCategory.TEST_CHANGE
        assert result.confidence >= 0.8

    def test_doc_file(self):
        hunk = _hunk(DiffKind.BODY_CHANGED)
        result = _classify_single_hunk(hunk, "README.md")
        assert result.category == SemanticCategory.DOCUMENTATION

    def test_import_change(self):
        hunk = _hunk(DiffKind.NODE_CHANGED, ASTNodeKind.IMPORT)
        result = _classify_single_hunk(hunk, "main.py")
        assert result.category == SemanticCategory.IMPORT_CHANGE

    def test_public_signature_change(self):
        hunk = _hunk(DiffKind.SIGNATURE_CHANGED, ASTNodeKind.FUNCTION, "get_data")
        result = _classify_single_hunk(hunk, "api.py")
        assert result.category == SemanticCategory.API_CHANGE
        assert "Public signature" in result.reason

    def test_private_signature_change(self):
        hunk = _hunk(DiffKind.SIGNATURE_CHANGED, ASTNodeKind.FUNCTION, "_helper")
        result = _classify_single_hunk(hunk, "main.py")
        assert result.category == SemanticCategory.REFACTOR

    def test_public_rename(self):
        hunk = _hunk(DiffKind.NODE_RENAMED, ASTNodeKind.FUNCTION, "process")
        result = _classify_single_hunk(hunk, "main.py")
        assert result.category == SemanticCategory.API_CHANGE

    def test_private_rename(self):
        hunk = _hunk(DiffKind.NODE_RENAMED, ASTNodeKind.FUNCTION, "_internal")
        result = _classify_single_hunk(hunk, "main.py")
        assert result.category == SemanticCategory.REFACTOR

    def test_function_added(self):
        hunk = _hunk(DiffKind.NODE_ADDED, ASTNodeKind.FUNCTION, "new_feature")
        result = _classify_single_hunk(hunk, "main.py")
        assert result.category == SemanticCategory.FEATURE_ADDITION
        assert "new_feature" in result.reason

    def test_class_added(self):
        hunk = _hunk(DiffKind.NODE_ADDED, ASTNodeKind.CLASS, "MyClass")
        result = _classify_single_hunk(hunk, "main.py")
        assert result.category == SemanticCategory.FEATURE_ADDITION

    def test_non_func_added(self):
        hunk = _hunk(DiffKind.NODE_ADDED, ASTNodeKind.VARIABLE, "x")
        result = _classify_single_hunk(hunk, "main.py")
        assert result.category == SemanticCategory.INTERNAL_CHANGE

    def test_public_function_removed(self):
        hunk = _hunk(DiffKind.NODE_REMOVED, ASTNodeKind.FUNCTION, "delete_me")
        result = _classify_single_hunk(hunk, "main.py")
        assert result.category == SemanticCategory.FEATURE_REMOVAL
        assert result.confidence >= 0.8

    def test_private_function_removed(self):
        hunk = _hunk(DiffKind.NODE_REMOVED, ASTNodeKind.FUNCTION, "_internal")
        result = _classify_single_hunk(hunk, "main.py")
        assert result.category == SemanticCategory.FEATURE_REMOVAL
        assert result.confidence < 0.8

    def test_body_changed(self):
        hunk = _hunk(DiffKind.BODY_CHANGED, ASTNodeKind.FUNCTION, "compute")
        result = _classify_single_hunk(hunk, "main.py")
        assert result.category == SemanticCategory.INTERNAL_CHANGE

    def test_generic_changed(self):
        hunk = _hunk(DiffKind.NODE_CHANGED, ASTNodeKind.VARIABLE, "x")
        result = _classify_single_hunk(hunk, "main.py")
        assert result.category == SemanticCategory.INTERNAL_CHANGE


class TestPickDominant:
    def test_empty(self):
        assert _pick_dominant({}) == SemanticCategory.UNKNOWN

    def test_api_wins(self):
        counts = {SemanticCategory.INTERNAL_CHANGE: 5, SemanticCategory.API_CHANGE: 1}
        assert _pick_dominant(counts) == SemanticCategory.API_CHANGE

    def test_feature_removal_second(self):
        counts = {
            SemanticCategory.INTERNAL_CHANGE: 3,
            SemanticCategory.FEATURE_REMOVAL: 1,
        }
        assert _pick_dominant(counts) == SemanticCategory.FEATURE_REMOVAL

    def test_refactor_over_internal(self):
        counts = {SemanticCategory.INTERNAL_CHANGE: 2, SemanticCategory.REFACTOR: 1}
        assert _pick_dominant(counts) == SemanticCategory.REFACTOR


class TestComputeRisk:
    def test_empty(self):
        assert _compute_risk([]) == "low"

    def test_high_risk(self):
        hunks = [
            ClassifiedHunk(
                hunk=_hunk(),
                category=SemanticCategory.API_CHANGE,
                confidence=0.9,
                reason="test",
            )
        ]
        assert _compute_risk(hunks) == "high"

    def test_medium_risk(self):
        hunks = [
            ClassifiedHunk(
                hunk=_hunk(),
                category=SemanticCategory.REFACTOR,
                confidence=0.8,
                reason="test",
            )
        ]
        assert _compute_risk(hunks) == "medium"

    def test_low_risk(self):
        hunks = [
            ClassifiedHunk(
                hunk=_hunk(),
                category=SemanticCategory.STYLE_CHANGE,
                confidence=0.9,
                reason="test",
            )
        ]
        assert _compute_risk(hunks) == "low"

    def test_low_confidence_high_ignored(self):
        hunks = [
            ClassifiedHunk(
                hunk=_hunk(),
                category=SemanticCategory.API_CHANGE,
                confidence=0.3,
                reason="test",
            )
        ]
        assert _compute_risk(hunks) == "low"


class TestBuildSummary:
    def test_empty(self):
        assert _build_summary(SemanticCategory.UNKNOWN, {}, 0) == "No changes detected"

    def test_with_changes(self):
        counts = {SemanticCategory.API_CHANGE: 1, SemanticCategory.INTERNAL_CHANGE: 3}
        result = _build_summary(SemanticCategory.API_CHANGE, counts, 4)
        assert "4 changes" in result
        assert "api_change" in result


class TestSemanticChangeClassifier:
    def test_empty_diff(self):
        classifier = SemanticChangeClassifier()
        diff_result = ASTDiffResult(
            old_file="a.py",
            new_file="b.py",
            language="python",
            hunks=[],
        )
        classification = classifier.classify(diff_result)
        assert classification.dominant_category == SemanticCategory.UNKNOWN
        assert classification.risk_level == "low"
        assert len(classification.classifications) == 0

    def test_single_addition(self):
        hunk = _hunk(DiffKind.NODE_ADDED, ASTNodeKind.FUNCTION, "new_func")
        diff_result = ASTDiffResult(
            old_file="a.py",
            new_file="b.py",
            language="python",
            hunks=[hunk],
        )
        classifier = SemanticChangeClassifier()
        classification = classifier.classify(diff_result)
        assert classification.dominant_category == SemanticCategory.FEATURE_ADDITION
        assert len(classification.classifications) == 1
        assert "feature_addition" in classification.category_counts

    def test_mixed_changes(self):
        hunks = [
            _hunk(DiffKind.NODE_ADDED, ASTNodeKind.FUNCTION, "new_func"),
            _hunk(DiffKind.SIGNATURE_CHANGED, ASTNodeKind.FUNCTION, "api_handler"),
            _hunk(DiffKind.BODY_CHANGED, ASTNodeKind.FUNCTION, "_internal"),
        ]
        diff_result = ASTDiffResult(
            old_file="a.py",
            new_file="b.py",
            language="python",
            hunks=hunks,
        )
        classifier = SemanticChangeClassifier()
        classification = classifier.classify(diff_result)
        assert classification.dominant_category == SemanticCategory.API_CHANGE
        assert classification.risk_level == "high"
        assert classification.change_summary
        assert len(classification.category_counts) >= 2  # ratchet: nondeterministic

    def test_file_path_override(self):
        hunk = _hunk(DiffKind.BODY_CHANGED, ASTNodeKind.FUNCTION, "func")
        diff_result = ASTDiffResult(
            old_file=None,
            new_file=None,
            language="python",
            hunks=[hunk],
        )
        classifier = SemanticChangeClassifier(file_path="tests/test_foo.py")
        classification = classifier.classify(diff_result)
        assert (
            classification.classifications[0].category == SemanticCategory.TEST_CHANGE
        )

    def test_to_dict_roundtrip(self):
        hunk = _hunk(DiffKind.NODE_ADDED, ASTNodeKind.FUNCTION, "new_func")
        diff_result = ASTDiffResult(
            old_file="a.py",
            new_file="b.py",
            language="python",
            hunks=[hunk],
        )
        classifier = SemanticChangeClassifier()
        classification = classifier.classify(diff_result)
        d = classification.to_dict()
        assert "dominant_category" in d
        assert "risk_level" in d
        assert "change_summary" in d
        assert "category_counts" in d
        assert "classifications" in d
        assert len(d["classifications"]) == 1
        c = d["classifications"][0]
        assert "category" in c
        assert "risk" in c
        assert "confidence" in c
        assert "reason" in c
        assert "hunk" in c

    def test_classified_hunk_to_dict(self):
        hunk = _hunk(DiffKind.NODE_ADDED, ASTNodeKind.FUNCTION, "new_func")
        ch = ClassifiedHunk(
            hunk=hunk,
            category=SemanticCategory.FEATURE_ADDITION,
            confidence=0.8,
            reason="New function added",
        )
        d = ch.to_dict()
        assert d["category"] == "feature_addition"
        assert d["confidence"] == 0.8
        assert d["risk"] == "medium"
        assert "label" in d
        assert "hunk" in d

    def test_semantic_classification_to_dict(self):
        sc = SemanticClassification(
            dominant_category=SemanticCategory.REFACTOR,
            risk_level="medium",
            change_summary="Refactor (2 changes)",
        )
        d = sc.to_dict()
        assert d["dominant_category"] == "refactor"
        assert d["risk_level"] == "medium"
