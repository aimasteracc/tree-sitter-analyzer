"""semantic_change_classifier 场景化加固测试（变异测试驱动，v1.29.2 轮次二）。

设计原则：一个测试函数覆盖一个完整分类分支的多个断言——
category、confidence、reason 三元组全部锁精确值；
决策矩阵的每个分支、优先级次序、风险阈值边界都单独可追溯。
"""

from __future__ import annotations

from tree_sitter_analyzer.ast_diff import (
    ASTDiffHunk,
    ASTDiffResult,
    ASTNodeInfo,
    ASTNodeKind,
    DiffKind,
)
from tree_sitter_analyzer.semantic_change_classifier import (
    SemanticCategory,
    SemanticChangeClassifier,
    _build_summary,
    _classify_single_hunk,
    _compute_risk,
    _has_public_indicator,
    _hunk_name,
    _hunk_preview,
    _is_doc_path,
    _is_public_name,
    _is_test_path,
    _pick_dominant,
)


def _info(name: str = "", preview: str = "") -> ASTNodeInfo:
    """只填分类器会读的字段：名字与文本预览。"""
    return ASTNodeInfo(
        node_type="t",
        kind=ASTNodeKind.FUNCTION,
        name=name,
        start_line=1,
        start_col=0,
        end_line=1,
        end_col=0,
        text_hash="h",
        text_preview=preview,
    )


def _hunk(
    diff_kind: DiffKind = DiffKind.NODE_CHANGED,
    node_kind: ASTNodeKind = ASTNodeKind.FUNCTION,
    old: ASTNodeInfo | None = None,
    new: ASTNodeInfo | None = None,
) -> ASTDiffHunk:
    return ASTDiffHunk(diff_kind, node_kind, old, new, "s")


# ---------- 场景：路径前置分支 ----------


class TestPathBranches:
    def test_测试路径压倒一切(self):
        # tests/、test_ 前缀、conftest、spec 等指示符命中即 TEST_CHANGE
        # 注意:裸相对路径 "tests/unit/a.py"(无前导斜杠)不在指示符内——
        # 已作为疑似真 bug 记录到 BLOCKED.md,此处按现状锁定
        for path in (
            "/repo/tests/unit/a.py",
            "src/test_foo.py",
            "pkg/conftest.py",
            "x/spec_run.py",
        ):
            c = _classify_single_hunk(_hunk(), path)
            assert c.category == SemanticCategory.TEST_CHANGE, path
            assert c.confidence == 0.9
            assert c.reason == "File is in test directory"

    def test_测试路径大小写不敏感_反斜杠指示符也命中(self):
        assert _is_test_path("SRC/TESTS/A.PY") is True
        assert _is_test_path("src\\tests\\a.py") is True
        # 现状锁定:无前导斜杠的相对 tests 路径不命中(疑似真 bug,BLOCKED.md)
        assert _is_test_path("tests/unit/a.py") is False
        assert _is_test_path("src/__tests__/a.js") is True
        assert _is_test_path(None) is False
        assert _is_test_path("src/main.py") is False

    def test_文档扩展名分支优先于节点类型(self):
        for path in ("README.md", "doc.rst", "notes.txt", "book.adoc"):
            c = _classify_single_hunk(_hunk(diff_kind=DiffKind.SIGNATURE_CHANGED), path)
            assert c.category == SemanticCategory.DOCUMENTATION, path
            assert c.confidence == 0.9
            assert c.reason == "File is a documentation file"

    def test_文档路径判断边界(self):
        assert _is_doc_path("a.md") is True
        assert _is_doc_path("a.MD") is True  # lower() 后匹配
        assert _is_doc_path("a.py") is False
        assert _is_doc_path(None) is False
        assert _is_doc_path("markdown") is False  # 只认后缀不认子串


# ---------- 场景：节点类型与签名分支 ----------


class TestKindBranches:
    def test_import节点恒为IMPORT_CHANGE(self):
        # IMPORT 节点类型优先于一切 diff_kind
        for dk in (DiffKind.NODE_CHANGED, DiffKind.NODE_REMOVED, DiffKind.BODY_CHANGED):
            c = _classify_single_hunk(_hunk(dk, ASTNodeKind.IMPORT))
            assert c.category == SemanticCategory.IMPORT_CHANGE
            assert c.confidence == 0.85
            assert c.reason == "Import/dependency change"

    def test_签名变化_公开名_API_CHANGE高置信(self):
        c = _classify_single_hunk(
            _hunk(
                DiffKind.SIGNATURE_CHANGED,
                old=_info("public_fn"),
                new=_info("public_fn"),
            )
        )
        assert c.category == SemanticCategory.API_CHANGE
        assert c.confidence == 0.85
        assert c.reason == "Public signature change on function 'public_fn'"

    def test_签名变化_私有名_REFACTOR(self):
        c = _classify_single_hunk(
            _hunk(
                DiffKind.SIGNATURE_CHANGED, old=_info("_private"), new=_info("_private")
            )
        )
        assert c.category == SemanticCategory.REFACTOR
        assert c.confidence == 0.7
        assert c.reason == "Private/internal signature change"

    def test_签名变化_预览含公开指示符_API_CHANGE低置信(self):
        c = _classify_single_hunk(
            _hunk(
                DiffKind.SIGNATURE_CHANGED,
                old=_info("_hidden"),
                new=_info("_hidden", preview="export const value"),
            )
        )
        assert c.category == SemanticCategory.API_CHANGE
        assert c.confidence == 0.6
        assert c.reason == "Signature change may affect external callers"

    def test_签名变化_私有名且无指示符不升API(self):
        c = _classify_single_hunk(
            _hunk(
                DiffKind.SIGNATURE_CHANGED,
                old=_info("_hidden"),
                new=_info("_hidden", preview="internal helper"),
            )
        )
        assert c.category == SemanticCategory.REFACTOR


# ---------- 场景：改名分支 ----------


class TestRenameBranch:
    def test_公开改名_API_CHANGE(self):
        c = _classify_single_hunk(
            _hunk(DiffKind.NODE_RENAMED, old=_info("old_name"), new=_info("new_name"))
        )
        assert c.category == SemanticCategory.API_CHANGE
        assert c.confidence == 0.8
        assert c.reason == "Public function renamed: possible breaking change"

    def test_私有改名_REFACTOR(self):
        c = _classify_single_hunk(
            _hunk(DiffKind.NODE_RENAMED, old=_info("_old"), new=_info("_new"))
        )
        assert c.category == SemanticCategory.REFACTOR
        assert c.confidence == 0.75
        assert c.reason == "Internal function renamed"


# ---------- 场景：新增分支 ----------


class TestAddedBranch:
    def test_新增函数类节点_FEATURE_ADDITION(self):
        for kind in (ASTNodeKind.FUNCTION, ASTNodeKind.CLASS, ASTNodeKind.METHOD):
            c = _classify_single_hunk(
                _hunk(DiffKind.NODE_ADDED, kind, new=_info("thing"))
            )
            assert c.category == SemanticCategory.FEATURE_ADDITION, kind
            assert c.confidence == 0.8
            assert c.reason == f"New {kind.value} 'thing' added"

    def test_新增非函数类节点_INTERNAL_CHANGE(self):
        c = _classify_single_hunk(
            _hunk(DiffKind.NODE_ADDED, ASTNodeKind.VARIABLE, new=_info("x"))
        )
        assert c.category == SemanticCategory.INTERNAL_CHANGE
        assert c.confidence == 0.6
        # 非函数类新增的 reason 不带名字(与函数类分支不同)
        assert c.reason == "New variable added"


# ---------- 场景：删除分支 ----------


class TestRemovedBranch:
    def test_删除公开函数类_FEATURE_REMOVAL高置信(self):
        c = _classify_single_hunk(
            _hunk(DiffKind.NODE_REMOVED, ASTNodeKind.CLASS, old=_info("Klass"))
        )
        assert c.category == SemanticCategory.FEATURE_REMOVAL
        assert c.confidence == 0.85
        assert c.reason == "Public class 'Klass' removed — likely breaking"

    def test_删除私有函数类_FEATURE_REMOVAL低置信(self):
        c = _classify_single_hunk(
            _hunk(DiffKind.NODE_REMOVED, ASTNodeKind.FUNCTION, old=_info("_helper"))
        )
        assert c.category == SemanticCategory.FEATURE_REMOVAL
        assert c.confidence == 0.7
        assert c.reason == "Internal function '_helper' removed"

    def test_删除非函数类节点_INTERNAL_CHANGE(self):
        c = _classify_single_hunk(
            _hunk(DiffKind.NODE_REMOVED, ASTNodeKind.DECORATOR, old=_info("_deco"))
        )
        assert c.category == SemanticCategory.INTERNAL_CHANGE
        assert c.confidence == 0.5
        assert c.reason == "decorator removed"


# ---------- 场景：剩余 diff_kind 分支与兜底 ----------


class TestTailBranches:
    def test_BODY_CHANGED(self):
        c = _classify_single_hunk(_hunk(DiffKind.BODY_CHANGED, ASTNodeKind.METHOD))
        assert c.category == SemanticCategory.INTERNAL_CHANGE
        assert c.confidence == 0.7
        assert c.reason == "Implementation body change in method"

    def test_NODE_CHANGED(self):
        c = _classify_single_hunk(_hunk(DiffKind.NODE_CHANGED, ASTNodeKind.CLASS))
        assert c.category == SemanticCategory.INTERNAL_CHANGE
        assert c.confidence == 0.5
        assert c.reason == "Generic change in class"

    def test_NODE_MOVED等未分类落到UNKNOWN(self):
        c = _classify_single_hunk(_hunk(DiffKind.NODE_MOVED))
        assert c.category == SemanticCategory.UNKNOWN
        assert c.confidence == 0.3
        assert c.reason == "Unable to classify"


# ---------- 场景：名字与预览取值优先级 ----------


class TestHunkAccessors:
    def test_名字取new优先_退old_再None(self):
        assert _hunk_name(_hunk(old=_info("old"), new=_info("new"))) == "new"
        assert _hunk_name(_hunk(old=_info("old"))) == "old"
        assert _hunk_name(_hunk()) is None
        # 空串名字视为缺失 → 退到 old
        assert _hunk_name(_hunk(old=_info("old"), new=_info(""))) == "old"

    def test_预览取new优先_空预览退old(self):
        assert (
            _hunk_preview(_hunk(old=_info("", "old_p"), new=_info("", "new_p")))
            == "new_p"
        )
        assert _hunk_preview(_hunk(old=_info("", "old_p"), new=_info(""))) == "old_p"
        assert _hunk_preview(_hunk()) is None

    def test_公开名判定边界(self):
        assert _is_public_name("foo") is True
        assert _is_public_name("__dunder__") is True  # 双下划线不算私有
        assert _is_public_name("_private") is False
        assert _is_public_name("") is False
        assert _is_public_name(None) is False

    def test_公开指示符判定(self):
        for text in ("export x", "public:", "__all__", "API docs", "api_key"):
            assert _has_public_indicator(text) is True, text
        assert _has_public_indicator("internal helper") is False
        assert _has_public_indicator("") is False
        assert _has_public_indicator(None) is False


# ---------- 场景：主导类别与优先级 ----------


class TestDominantAndSummary:
    def test_优先级序压制计数(self):
        # internal 有 3 票、api 只有 1 票,但 api_change 排在优先级序最前
        counts = {SemanticCategory.INTERNAL_CHANGE: 3, SemanticCategory.API_CHANGE: 1}
        assert _pick_dominant(counts) == SemanticCategory.API_CHANGE
        # feature_removal 压过 feature_addition
        assert (
            _pick_dominant(
                {
                    SemanticCategory.FEATURE_ADDITION: 2,
                    SemanticCategory.FEATURE_REMOVAL: 1,
                }
            )
            == SemanticCategory.FEATURE_REMOVAL
        )
        assert _pick_dominant({}) == SemanticCategory.UNKNOWN

    def test_摘要文本精确格式(self):
        assert _build_summary(SemanticCategory.UNKNOWN, {}, 0) == "No changes detected"
        s = _build_summary(
            SemanticCategory.API_CHANGE,
            {SemanticCategory.API_CHANGE: 1, SemanticCategory.INTERNAL_CHANGE: 2},
            3,
        )
        assert s == "Breaking API change (3 changes: 1 api_change, 2 internal_change)"


# ---------- 场景：风险聚合阈值 ----------


class TestComputeRisk:
    def _ch(self, cat: SemanticCategory, conf: float):
        return _classify_single_hunk(_hunk()).__class__(
            hunk=_hunk(), category=cat, confidence=conf, reason="r"
        )

    def test_空列表为low(self):
        assert _compute_risk([]) == "low"

    def test_高风险类且置信达标为high(self):
        # FEATURE_REMOVAL 风险表值 high,置信 0.7 达阈值线
        assert (
            _compute_risk([self._ch(SemanticCategory.FEATURE_REMOVAL, 0.7)]) == "high"
        )

    def test_高风险类置信不足降级(self):
        # 置信 0.69 < 0.7 → 不算 high;风险表值 high 也不属于 medium → low
        assert (
            _compute_risk([self._ch(SemanticCategory.FEATURE_REMOVAL, 0.69)]) == "low"
        )

    def test_中风险类达标为medium_不足为low(self):
        assert _compute_risk([self._ch(SemanticCategory.REFACTOR, 0.7)]) == "medium"
        assert _compute_risk([self._ch(SemanticCategory.REFACTOR, 0.59)]) == "low"

    def test_低风险类恒low(self):
        assert _compute_risk([self._ch(SemanticCategory.INTERNAL_CHANGE, 0.9)]) == "low"

    def test_高中混存取high(self):
        assert (
            _compute_risk(
                [
                    self._ch(SemanticCategory.INTERNAL_CHANGE, 0.9),
                    self._ch(SemanticCategory.API_CHANGE, 0.85),
                ]
            )
            == "high"
        )


# ---------- 场景：classify 编排 ----------


class TestClassifyOrchestration:
    def _result(self, hunks, new_file="src/mod.py"):
        return ASTDiffResult(
            old_file="o", new_file=new_file, language="python", hunks=hunks
        )

    def test_空hunks_无变化结果(self):
        r = SemanticChangeClassifier().classify(self._result([]))
        assert r.dominant_category == SemanticCategory.UNKNOWN
        assert r.risk_level == "low"
        assert r.change_summary == "No changes detected"
        assert r.category_counts == {}
        d = r.to_dict()
        assert d["dominant_category"] == "unknown"
        assert d["dominant_label"] == "Unclassified change"
        assert d["classifications"] == []

    def test_构造器路径优先于结果里的new_file(self):
        hunks = [_hunk(DiffKind.BODY_CHANGED)]
        # new_file 指向源码,但构造器显式给了测试路径 → TEST_CHANGE
        r = SemanticChangeClassifier(file_path="src/test_x.py").classify(
            self._result(hunks)
        )
        assert r.dominant_category == SemanticCategory.TEST_CHANGE
        assert r.category_counts == {"test_change": 1}

    def test_结果new_file路径参与测试判定(self):
        hunks = [_hunk(DiffKind.BODY_CHANGED)]
        r = SemanticChangeClassifier().classify(
            self._result(hunks, new_file="pkg/test_helper.py")
        )
        assert r.dominant_category == SemanticCategory.TEST_CHANGE

    def test_混合hunks的聚合(self):
        hunks = [
            _hunk(DiffKind.NODE_ADDED, ASTNodeKind.FUNCTION, new=_info("new_api")),
            _hunk(DiffKind.BODY_CHANGED, ASTNodeKind.FUNCTION),
        ]
        r = SemanticChangeClassifier().classify(self._result(hunks))
        assert r.dominant_category == SemanticCategory.FEATURE_ADDITION
        assert r.category_counts == {"feature_addition": 1, "internal_change": 1}
        assert (
            r.change_summary
            == "Feature addition (2 changes: 1 feature_addition, 1 internal_change)"
        )
        # 新增公开函数 0.8 置信 + 中风险 feature_addition → medium
        assert r.risk_level == "medium"
        d = r.to_dict()
        assert d["classifications"][0]["label"] == "Feature addition"
        assert d["classifications"][0]["risk"] == "medium"
        assert d["classifications"][0]["confidence"] == 0.8
        assert d["classifications"][1]["category"] == "internal_change"

    def test_to_dict包含hunk结构(self):
        hunks = [_hunk(DiffKind.NODE_REMOVED, ASTNodeKind.CLASS, old=_info("Gone"))]
        r = SemanticChangeClassifier().classify(self._result(hunks))
        d = r.to_dict()
        assert d["classifications"][0]["hunk"]["kind"] == "removed"
        assert d["classifications"][0]["hunk"]["node_kind"] == "class"
