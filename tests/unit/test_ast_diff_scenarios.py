"""ast_diff 场景化加固测试（变异测试驱动，v1.29.2 热修）。

设计原则：一个测试函数覆盖一个完整行为场景的多个断言，
对着「变异会改掉什么行为」下断言（边界值、空输入、字段级差异），
而不是一个函数只碰一下就跑。
"""

from __future__ import annotations

import hashlib

from tree_sitter_analyzer.ast_diff import (
    ASTDiffer,
    ASTDiffHunk,
    ASTDiffResult,
    ASTNodeInfo,
    ASTNodeKind,
    DiffKind,
    _body_hash_changed,
    _compute_stats,
    _diff_children,
    _diff_matched_nodes,
    _extract_signature,
    _match_nodes,
    _preview,
    _sig_diff,
    _text_hash,
)

# ---------- 场景：preview 截断行为 ----------


class TestPreviewScenarios:
    def test_边界长度_恰好80不截断_81截断加省略号(self):
        # 默认 max_len=80：80 字符原样返回；81 字符截成 77+"..."
        assert _preview("x" * 80) == "x" * 80
        assert len(_preview("x" * 80)) == 80
        assert _preview("x" * 81) == "x" * 77 + "..."
        assert len(_preview("x" * 81)) == 80

    def test_自定义max_len_边界(self):
        assert _preview("abcdef", max_len=6) == "abcdef"
        assert _preview("abcdefg", max_len=6) == "abc..."

    def test_换行折叠与首尾空白(self):
        # 语义：先把换行替换成空格、再 strip 两端——中间的多空格保留
        assert _preview("  a\n b \n c  ") == "a  b   c"
        assert "\n" not in _preview("line1\nline2")

    def test_空字符串与短文本(self):
        assert _preview("") == ""
        assert _preview("hi") == "hi"

    def test_换行后长度按折叠文本计(self):
        # 折叠换行后再判长度："a\n" + "b"*80 折叠为 "a " + "b"*80 = 82 字符 → 截断
        folded = _preview("a\n" + "b" * 80)
        assert folded == ("a " + "b" * 80)[:77] + "..."


# ---------- 场景：text_hash ----------


class TestTextHashScenarios:
    def test_等于sha256_hex_长度64(self):
        expected = hashlib.sha256(b"hello").hexdigest()
        assert _text_hash("hello") == expected
        assert len(_text_hash("hello")) == 64

    def test_非ascii按utf8编码(self):
        expected = hashlib.sha256("你好世界".encode()).hexdigest()
        assert _text_hash("你好世界") == expected

    def test_空字符串与差异(self):
        assert _text_hash("") == hashlib.sha256(b"").hexdigest()
        assert _text_hash("a") != _text_hash("b")
        assert _text_hash("ab") != _text_hash("a b")


# ---------- 场景：签名提取与签名差异 ----------


def _node(
    kind: ASTNodeKind,
    name: str = "",
    text_hash: str = "",
    children: list[ASTNodeInfo] | None = None,
    text_preview: str = "",
    node_type: str = "function_definition",
) -> ASTNodeInfo:
    """构造带子节点的 ASTNodeInfo 测试替身（只填被测行为用到的字段）。"""
    return ASTNodeInfo(
        node_type=node_type,
        kind=kind,
        name=name,
        start_line=1,
        start_col=0,
        end_line=2,
        end_col=0,
        text_hash=text_hash,
        text_preview=text_preview,
        children=children or [],
    )


def _param(preview: str, h: str) -> ASTNodeInfo:
    return _node(
        ASTNodeKind.PARAMETER, text_hash=h, text_preview=preview, node_type="parameters"
    )


def _decorator(h: str) -> ASTNodeInfo:
    return _node(ASTNodeKind.DECORATOR, text_hash=h, node_type="decorator")


def _block(h: str) -> ASTNodeInfo:
    return _node(ASTNodeKind.BLOCK, text_hash=h, node_type="block")


class TestExtractSignatureScenarios:
    def test_只取第一个参数子节点_后续参数忽略(self):
        first, second = _param("(a, b)", "h1"), _param("(c)", "h2")
        sig = _extract_signature(
            _node(ASTNodeKind.FUNCTION, "f", children=[first, second])
        )
        assert sig == {"name": "f", "params_hash": "h1", "params_preview": "(a, b)"}

    def test_装饰器累积_参数缺省时不产生参数键(self):
        sig = _extract_signature(
            _node(
                ASTNodeKind.FUNCTION, "g", children=[_decorator("d1"), _decorator("d2")]
            )
        )
        assert sig == {"name": "g", "decorators": ["d1", "d2"]}
        assert "params_hash" not in sig
        assert "params_preview" not in sig

    def test_装饰器与参数并存_首个参数后停止遍历(self):
        # 语义锁定：遍历到第一个 PARAMETER 即 break，其后的装饰器不再收录
        sig = _extract_signature(
            _node(
                ASTNodeKind.FUNCTION,
                "h",
                children=[_decorator("d1"), _param("(x)", "p1"), _decorator("d2")],
            )
        )
        assert sig["params_hash"] == "p1"
        assert sig["params_preview"] == "(x)"
        assert sig["decorators"] == ["d1"]

    def test_无子节点只有名字(self):
        assert _extract_signature(_node(ASTNodeKind.FUNCTION, "solo")) == {
            "name": "solo"
        }


class TestSigDiffScenarios:
    def test_参数变化_带前后预览(self):
        old = {"name": "f", "params_hash": "h1", "params_preview": "(a)"}
        new = {"name": "f", "params_hash": "h2", "params_preview": "(a, b)"}
        diff = _sig_diff(old, new)
        assert diff == {
            "params_changed": True,
            "old_params": "(a)",
            "new_params": "(a, b)",
        }

    def test_参数变化_一侧无预览时省略对应键(self):
        old = {"name": "f"}
        new = {"name": "f", "params_hash": "h2", "params_preview": "(x)"}
        diff = _sig_diff(old, new)
        assert diff["params_changed"] is True
        assert "old_params" not in diff
        assert diff["new_params"] == "(x)"

    def test_装饰器变化单独成立(self):
        old = {"name": "f", "decorators": ["d1"]}
        new = {"name": "f", "decorators": ["d1", "d2"]}
        assert _sig_diff(old, new) == {"decorators_changed": True}

    def test_完全一致返回空字典(self):
        sig = {"name": "f", "params_hash": "h", "decorators": ["d"]}
        assert _sig_diff(sig, dict(sig)) == {}

    def test_名字不属于签名差异范畴(self):
        # 只改 name 不算 sig 变化（重命名走 NODE_RENAMED 分支）
        assert _sig_diff({"name": "a"}, {"name": "b"}) == {}


# ---------- 场景：body 哈希比较 ----------


class TestBodyHashChangedScenarios:
    def test_双方都有body_比较body哈希(self):
        a = _node(ASTNodeKind.FUNCTION, "f", children=[_block("b1")])
        b = _node(ASTNodeKind.FUNCTION, "f", children=[_block("b2")])
        same = _node(ASTNodeKind.FUNCTION, "f", children=[_block("b1")])
        assert _body_hash_changed(a, b) is True
        assert _body_hash_changed(a, same) is False

    def test_双方都无body_退回整体哈希(self):
        a = _node(ASTNodeKind.FUNCTION, "f", text_hash="t1")
        b = _node(ASTNodeKind.FUNCTION, "f", text_hash="t2")
        same = _node(ASTNodeKind.FUNCTION, "f", text_hash="t1")
        assert _body_hash_changed(a, b) is True
        assert _body_hash_changed(a, same) is False

    def test_单侧有body_视为变化(self):
        with_body = _node(
            ASTNodeKind.FUNCTION, "f", text_hash="t", children=[_block("b")]
        )
        no_body = _node(ASTNodeKind.FUNCTION, "f", text_hash="t")
        assert _body_hash_changed(with_body, no_body) is True
        assert _body_hash_changed(no_body, with_body) is True


# ---------- 场景：节点匹配 ----------


class TestMatchNodesScenarios:
    def test_类型加名字精确匹配_同名取第一个未占用(self):
        old = [_node(ASTNodeKind.FUNCTION, "f"), _node(ASTNodeKind.CLASS, "f")]
        new = [
            _node(ASTNodeKind.CLASS, "f"),
            _node(ASTNodeKind.FUNCTION, "f"),
        ]
        matched, old_rem, new_rem = _match_nodes(old, new)
        # 函数对函数、类对类：kind 参与键
        assert (0, 1) in matched and (1, 0) in matched
        assert old_rem == [] and new_rem == []

    def test_无名节点永不参与匹配(self):
        old = [_node(ASTNodeKind.FUNCTION, "")]
        new = [_node(ASTNodeKind.FUNCTION, "")]
        matched, old_rem, new_rem = _match_nodes(old, new)
        assert matched == []
        assert old_rem == [0] and new_rem == [0]

    def test_函数改名_子方法重叠触发模糊匹配(self):
        # 旧类 Old 有方法 a、b；新类改名为 New 但仍有 a、b → 按子名重叠配对
        old_cls = _node(
            ASTNodeKind.CLASS,
            "Old",
            children=[_node(ASTNodeKind.METHOD, "a"), _node(ASTNodeKind.METHOD, "b")],
        )
        new_cls = _node(
            ASTNodeKind.CLASS,
            "New",
            children=[
                _node(ASTNodeKind.METHOD, "a"),
                _node(ASTNodeKind.METHOD, "b"),
                _node(ASTNodeKind.METHOD, "c"),
            ],
        )
        matched, old_rem, new_rem = _match_nodes([old_cls], [new_cls])
        assert matched == [(0, 0)]
        assert old_rem == [] and new_rem == []

    def test_子名零重叠的改名不模糊匹配(self):
        old_cls = _node(
            ASTNodeKind.CLASS, "Old", children=[_node(ASTNodeKind.METHOD, "a")]
        )
        new_cls = _node(
            ASTNodeKind.CLASS, "New", children=[_node(ASTNodeKind.METHOD, "z")]
        )
        matched, old_rem, new_rem = _match_nodes([old_cls], [new_cls])
        assert matched == []
        assert old_rem == [0] and new_rem == [0]

    def test_模糊匹配只对函数类节点生效_变量走不进该分支(self):
        old_var = _node(
            ASTNodeKind.VARIABLE, "v1", children=[_node(ASTNodeKind.OTHER, "kid")]
        )
        new_var = _node(
            ASTNodeKind.VARIABLE, "v2", children=[_node(ASTNodeKind.OTHER, "kid")]
        )
        matched, _, _ = _match_nodes([old_var], [new_var])
        assert matched == []

    def test_重叠更多者胜出(self):
        # 旧函数与两个新函数都同名缺失时,选子名重叠最大的那个
        old_f = _node(
            ASTNodeKind.FUNCTION,
            "gone",
            children=[_node(ASTNodeKind.OTHER, "x"), _node(ASTNodeKind.OTHER, "y")],
        )
        weak = _node(
            ASTNodeKind.FUNCTION, "weak", children=[_node(ASTNodeKind.OTHER, "x")]
        )
        strong = _node(
            ASTNodeKind.FUNCTION,
            "strong",
            children=[_node(ASTNodeKind.OTHER, "x"), _node(ASTNodeKind.OTHER, "y")],
        )
        matched, _, _ = _match_nodes([old_f], [weak, strong])
        assert matched == [(0, 1)]


# ---------- 场景：子节点差异 ----------


class TestDiffChildrenScenarios:
    def test_类内方法增删_摘要带方法名(self):
        old_cls = _node(
            ASTNodeKind.CLASS, "C", children=[_node(ASTNodeKind.METHOD, "m1")]
        )
        new_cls = _node(
            ASTNodeKind.CLASS, "C", children=[_node(ASTNodeKind.METHOD, "m2")]
        )
        hunks = _diff_children(old_cls, new_cls)
        summaries = [h.summary for h in hunks]
        assert "Removed method 'm1'" in summaries
        assert "Added method 'm2'" in summaries
        kinds = {h.diff_kind for h in hunks}
        assert kinds == {DiffKind.NODE_REMOVED, DiffKind.NODE_ADDED}

    def test_无名子节点摘要素材退回node_type(self):
        old_cls = _node(ASTNodeKind.CLASS, "C", children=[_block("")])
        new_cls = _node(ASTNodeKind.CLASS, "C", children=[])
        hunks = _diff_children(old_cls, new_cls)
        assert len(hunks) == 1
        assert hunks[0].summary == "Removed block 'block'"
        assert hunks[0].old_node is not None and hunks[0].new_node is None


# ---------- 场景：统计 ----------


class TestComputeStatsScenarios:
    def test_全部七类计数与未知类型归入changed(self):
        hunks = [
            ASTDiffHunk(DiffKind.NODE_ADDED, ASTNodeKind.FUNCTION, None, None, ""),
            ASTDiffHunk(DiffKind.NODE_REMOVED, ASTNodeKind.CLASS, None, None, ""),
            ASTDiffHunk(DiffKind.NODE_RENAMED, ASTNodeKind.FUNCTION, None, None, ""),
            ASTDiffHunk(
                DiffKind.SIGNATURE_CHANGED, ASTNodeKind.FUNCTION, None, None, ""
            ),
            ASTDiffHunk(DiffKind.BODY_CHANGED, ASTNodeKind.FUNCTION, None, None, ""),
            ASTDiffHunk(DiffKind.NODE_MOVED, ASTNodeKind.CLASS, None, None, ""),
            ASTDiffHunk(DiffKind.NODE_CHANGED, ASTNodeKind.OTHER, None, None, ""),
        ]
        stats = _compute_stats(hunks)
        assert stats == {
            "total_changes": 7,
            "added": 1,
            "removed": 1,
            "changed": 2,  # NODE_MOVED 不在键里 + NODE_CHANGED 字面值不在键里
            "renamed": 1,
            "signature_changed": 1,
            "body_changed": 1,
        }

    def test_单类多次累计(self):
        hunks = [
            ASTDiffHunk(DiffKind.NODE_ADDED, ASTNodeKind.FUNCTION, None, None, "")
            for _ in range(3)
        ]
        stats = _compute_stats(hunks)
        assert stats["added"] == 3
        assert stats["total_changes"] == 3
        assert stats["removed"] == 0


# ---------- 场景：端到端 diff_strings（真实 python 源码） ----------


def _kinds(result: ASTDiffResult) -> list[str]:
    return [h.diff_kind.value for h in result.hunks]


def _summaries(result: ASTDiffResult) -> list[str]:
    return [h.summary for h in result.hunks]


class TestDiffStringsScenarios:
    """集成场景：真实 python 源码经 diff_strings 的实际语义（特征锁定）。

    已锁定的真实行为：
    - 函数重命名在 python 源码里不产生 renamed——函数子节点皆无名,
      模糊匹配得 0 分,最终走 removed+added(renamed 分支见直达式测试)。
    - 变化的函数总伴随块级/关键字级 added/removed 噪声 hunk。
    - 类内变化上报为类级 body_changed;class 关键字节点被归类为 CLASS。
    """

    def test_函数重命名_在python源码中表现为removed加added(self):
        differ = ASTDiffer()
        result = differ.diff_strings(
            "def old_fn():\n    return 1\n", "def new_fn():\n    return 1\n", "python"
        )
        assert _kinds(result) == ["removed", "added"]
        assert _summaries(result) == [
            "Removed function 'old_fn'",
            "Added function 'new_fn'",
        ]
        assert result.summary_stats["renamed"] == 0
        assert result.summary_stats["removed"] == 1
        assert result.summary_stats["added"] == 1

    def test_仅签名变化_带params细节与参数级body噪声(self):
        differ = ASTDiffer()
        result = differ.diff_strings(
            "def f(a):\n    return a\n", "def f(a, b):\n    return a\n", "python"
        )
        assert _kinds(result)[0] == "signature_changed"
        hunk = result.hunks[0]
        assert hunk.summary == "Signature changed for function 'f'"
        assert hunk.details == {
            "params_changed": True,
            "old_params": "(a)",
            "new_params": "(a, b)",
        }
        # 名为 a 的参数节点被匹配且文本变化 → 参数级 body_changed 噪声
        assert "Body changed in parameter 'a'" in _summaries(result)
        assert result.summary_stats["signature_changed"] == 1
        assert result.summary_stats["body_changed"] == 1

    def test_签名加函数体同时变化_摘要为组合措辞(self):
        differ = ASTDiffer()
        result = differ.diff_strings(
            "def f(a):\n    return a\n", "def f(a, b):\n    return a + b\n", "python"
        )
        assert _kinds(result)[0] == "signature_changed"
        assert result.hunks[0].summary == "Signature + body changed for function 'f'"
        assert result.hunks[0].details["params_changed"] is True
        assert result.summary_stats["signature_changed"] == 1

    def test_仅函数体变化_类块噪声成对出现(self):
        differ = ASTDiffer()
        result = differ.diff_strings(
            "def f(a):\n    return a\n", "def f(a):\n    return a * 2\n", "python"
        )
        assert _kinds(result)[0] == "body_changed"
        assert result.hunks[0].summary == "Body changed in function 'f'"
        summaries = _summaries(result)
        assert "Removed block 'block'" in summaries
        assert "Added block 'block'" in summaries
        assert result.summary_stats == {
            "total_changes": 9,
            "added": 4,
            "removed": 4,
            "changed": 0,
            "renamed": 0,
            "signature_changed": 0,
            "body_changed": 1,
        }

    def test_返回类型注解变化_落入changed兜底分支(self):
        differ = ASTDiffer()
        result = differ.diff_strings(
            "def f(a) -> int:\n    return a\n",
            "def f(a) -> str:\n    return a\n",
            "python",
        )
        assert _kinds(result)[0] == "changed"
        assert result.hunks[0].summary == "Function 'f' changed"
        assert result.summary_stats["changed"] == 1
        assert result.summary_stats["renamed"] == 0

    def test_类内方法体变化_上报为类级body_changed(self):
        differ = ASTDiffer()
        result = differ.diff_strings(
            "class C:\n    def m(self):\n        return 1\n",
            "class C:\n    def m(self):\n        return 2\n",
            "python",
        )
        assert _kinds(result)[0] == "body_changed"
        summaries = _summaries(result)
        assert summaries[0] == "Body changed in class 'C'"
        # python 语法树把 class 关键字节点也归为 CLASS 类并产生增删噪声
        assert "Removed class 'class'" in summaries
        assert "Added class 'class'" in summaries
        assert result.summary_stats["body_changed"] == 1

    def test_类内删方法_同样表现为类级body_changed(self):
        differ = ASTDiffer()
        result = differ.diff_strings(
            "class C:\n    def a(self):\n        return 1\n\n    def b(self):\n        return 2\n",
            "class C:\n    def a(self):\n        return 1\n",
            "python",
        )
        assert _kinds(result)[0] == "body_changed"
        assert result.hunks[0].summary == "Body changed in class 'C'"

    def test_类改名_因方法嵌套在block内无法模糊匹配(self):
        differ = ASTDiffer()
        result = differ.diff_strings(
            "class OldName:\n    def helper(self):\n        return 1\n",
            "class NewName:\n    def helper(self):\n        return 1\n",
            "python",
        )
        assert _kinds(result) == ["removed", "added"]
        assert _summaries(result) == [
            "Removed class 'OldName'",
            "Added class 'NewName'",
        ]

    def test_顶层变量赋值变化_表现为表达式语句增删(self):
        differ = ASTDiffer()
        result = differ.diff_strings("a = 1\n", "a = 2\n", "python")
        assert _kinds(result) == ["removed", "added"]
        assert _summaries(result) == [
            "Removed other 'expression_statement'",
            "Added other 'expression_statement'",
        ]
        assert result.summary_stats["total_changes"] == 2

    def test_增删函数并存_统计精确(self):
        differ = ASTDiffer()
        result = differ.diff_strings(
            "def keep():\n    pass\n\n\ndef drop():\n    pass\n",
            "def keep():\n    pass\n\n\ndef added():\n    pass\n",
            "python",
        )
        assert _kinds(result) == ["removed", "added"]
        assert _summaries(result) == [
            "Removed function 'drop'",
            "Added function 'added'",
        ]
        assert result.summary_stats["total_changes"] == 2

    def test_文件名标签与语言回显(self):
        differ = ASTDiffer()
        result = differ.diff_strings(
            "a = 1\n", "a = 2\n", "python", old_file="o.py", new_file="n.py"
        )
        assert result.old_file == "o.py"
        assert result.new_file == "n.py"
        assert result.language == "python"

    def test_多文件对_顺序与标签传播(self):
        differ = ASTDiffer()
        results = differ.diff_string_pairs(
            [
                ("a = 1\n", "a = 2\n", "pair1"),
                ("def f():\n    pass\n", "def f():\n    pass\n", "pair2"),
            ],
            "python",
        )
        assert [r.old_file for r in results] == ["pair1", "pair2"]
        assert [r.new_file for r in results] == ["pair1", "pair2"]
        assert _kinds(results[0]) == ["removed", "added"]
        assert _kinds(results[1]) == []
        assert results[1].summary_stats["total_changes"] == 0


# ---------- 场景：_diff_matched_nodes 五分支分类矩阵（直达式） ----------


class TestDiffMatchedNodesMatrix:
    """手构节点直达五个分类分支——renamed 分支在真实 python 源码中不可达,
    只能在这里锁定。"""

    def _fn(self, name: str = "f", hash_: str = "h1", children=None) -> ASTNodeInfo:
        return _node(ASTNodeKind.FUNCTION, name, text_hash=hash_, children=children)

    def test_整体哈希相同_直接返回空(self):
        a = self._fn(hash_="same")
        b = self._fn(hash_="same")
        assert _diff_matched_nodes(a, b) == []

    def test_改名分支_摘要含新旧名(self):
        a = self._fn("old", hash_="h1")
        b = self._fn("new", hash_="h2")
        hunks = _diff_matched_nodes(a, b)
        assert hunks[0].diff_kind == DiffKind.NODE_RENAMED
        assert hunks[0].summary == "Renamed function: 'old' -> 'new'"
        assert hunks[0].old_node.name == "old" and hunks[0].new_node.name == "new"

    def test_单名缺失不算改名_名字差异进签名且并入body组合分支(self):
        # old 有名 new 无名：name_changed 要求双方都有名，不成立；
        # 但签名 dict 含 name → sig_changed；双方无 block → 回退整体哈希 → body_changed
        a = self._fn("old", hash_="h1")
        b = self._fn("", hash_="h2")
        hunks = _diff_matched_nodes(a, b)
        assert hunks[0].diff_kind == DiffKind.SIGNATURE_CHANGED
        assert hunks[0].summary == "Signature + body changed for function 'old'"

    def test_仅签名变化分支_细节透传(self):
        a = self._fn(hash_="h1", children=[_param("(a)", "p1"), _block("b1")])
        b = self._fn(hash_="h2", children=[_param("(a, b)", "p2"), _block("b1")])
        hunks = _diff_matched_nodes(a, b)
        assert hunks[0].diff_kind == DiffKind.SIGNATURE_CHANGED
        assert hunks[0].summary == "Signature changed for function 'f'"
        assert hunks[0].details == {
            "params_changed": True,
            "old_params": "(a)",
            "new_params": "(a, b)",
        }
        # 无名参数子节点增删噪声随附
        assert {h.diff_kind for h in hunks[1:]} == {
            DiffKind.NODE_REMOVED,
            DiffKind.NODE_ADDED,
        }

    def test_签名加函数体同时变化分支(self):
        a = self._fn(hash_="h1", children=[_param("(a)", "p1"), _block("b1")])
        b = self._fn(hash_="h2", children=[_param("(a, b)", "p2"), _block("b2")])
        hunks = _diff_matched_nodes(a, b)
        assert hunks[0].diff_kind == DiffKind.SIGNATURE_CHANGED
        assert hunks[0].summary == "Signature + body changed for function 'f'"
        assert hunks[0].details["params_changed"] is True

    def test_仅函数体变化分支(self):
        a = self._fn(hash_="h1", children=[_param("(a)", "p1"), _block("b1")])
        b = self._fn(hash_="h2", children=[_param("(a)", "p1"), _block("b2")])
        hunks = _diff_matched_nodes(a, b)
        assert hunks[0].diff_kind == DiffKind.BODY_CHANGED
        assert hunks[0].summary == "Body changed in function 'f'"

    def test_哈希变而签名函数体皆同_兜底changed分支(self):
        # text_hash 不同但签名与 body 哈希都相同（如返回类型注解变化）；
        # 子节点内容一致但皆无名 → 仍产生 removed/added 噪声（匹配按名字）
        a = self._fn(hash_="h1", children=[_param("(a)", "p1"), _block("b1")])
        b = self._fn(hash_="h2", children=[_param("(a)", "p1"), _block("b1")])
        hunks = _diff_matched_nodes(a, b)
        assert hunks[0].diff_kind == DiffKind.NODE_CHANGED
        assert hunks[0].summary == "Function 'f' changed"
        noise = [(h.diff_kind, h.summary) for h in hunks[1:]]
        assert (DiffKind.NODE_REMOVED, "Removed parameter 'parameters'") in noise
        assert (DiffKind.NODE_REMOVED, "Removed block 'block'") in noise
        assert (DiffKind.NODE_ADDED, "Added parameter 'parameters'") in noise
        assert (DiffKind.NODE_ADDED, "Added block 'block'") in noise

    def test_无block节点的哈希差异落入body_changed而非changed(self):
        # 无 block 子节点时 body 比较回退到整体哈希 → 永远走不到 changed 兜底
        a = _node(ASTNodeKind.CLASS, "C", text_hash="h1")
        b = _node(ASTNodeKind.CLASS, "C", text_hash="h2")
        hunks = _diff_matched_nodes(a, b)
        assert [h.diff_kind for h in hunks] == [DiffKind.BODY_CHANGED]
        assert hunks[0].summary == "Body changed in class 'C'"

    def test_子节点差异透传追加(self):
        # 匹配的子方法变化 → 子 hunk 追加在父 hunk 之后
        child_a = _node(ASTNodeKind.METHOD, "m", text_hash="m1")
        child_b = _node(ASTNodeKind.METHOD, "m", text_hash="m2")
        a = _node(ASTNodeKind.CLASS, "C", text_hash="h1", children=[child_a])
        b = _node(ASTNodeKind.CLASS, "C", text_hash="h2", children=[child_b])
        hunks = _diff_matched_nodes(a, b)
        assert [(h.diff_kind, h.summary) for h in hunks] == [
            (DiffKind.BODY_CHANGED, "Body changed in class 'C'"),
            (DiffKind.BODY_CHANGED, "Body changed in method 'm'"),
        ]


# ---------- 场景：diff_files（语言探测与文件读写） ----------


class TestDiffFilesScenarios:
    def test_显式language优先_不做扩展名探测(self):
        differ = ASTDiffer()
        # 扩展名是 .txt 但显式给 python → 按 python 解析
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            old_p = Path(td) / "a.txt"
            new_p = Path(td) / "b.txt"
            old_p.write_text("def f():\n    return 1\n", encoding="utf-8")
            new_p.write_text("def f():\n    return 2\n", encoding="utf-8")
            result = differ.diff_files(str(old_p), str(new_p), language="python")
        assert result.language == "python"
        assert _kinds(result)[0] == "body_changed"

    def test_language缺省_从新文件扩展名探测(self):
        differ = ASTDiffer()
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            old_p = Path(td) / "same_name.py"
            new_p = Path(td) / "other.py"
            old_p.write_text("x = 1\n", encoding="utf-8")
            new_p.write_text("x = 2\n", encoding="utf-8")
            result = differ.diff_files(str(old_p), str(new_p))
        assert result.language == "python"
        assert _kinds(result)[0] in ("changed", "removed")

    def test_新文件扩展名不识别_回退旧文件扩展名(self):
        differ = ASTDiffer()
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            old_p = Path(td) / "old.py"
            new_p = Path(td) / "weird.unknownext"
            old_p.write_text("x = 1\n", encoding="utf-8")
            new_p.write_text("x = 2\n", encoding="utf-8")
            result = differ.diff_files(str(old_p), str(new_p))
        assert result.language == "python"

    def test_双侧扩展名都不识别_报不支持且language为unknown(self):
        differ = ASTDiffer()
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            old_p = Path(td) / "a.qqq"
            new_p = Path(td) / "b.www"
            old_p.write_text("x", encoding="utf-8")
            new_p.write_text("y", encoding="utf-8")
            result = differ.diff_files(str(old_p), str(new_p))
        assert result.language == "unknown"
        assert [h.summary for h in result.hunks] == ["Unsupported language"]
        assert result.hunks[0].diff_kind == DiffKind.NODE_CHANGED
        assert result.hunks[0].old_node is None and result.hunks[0].new_node is None

    def test_新文件扩展名语言优先于旧文件(self):
        # 探测顺序：先新文件扩展名；两侧语言不同时必须取新的
        differ = ASTDiffer()
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            old_p = Path(td) / "old.py"
            new_p = Path(td) / "new.js"
            old_p.write_text("x = 1\n", encoding="utf-8")
            new_p.write_text("let x = 1;\n", encoding="utf-8")
            result = differ.diff_files(str(old_p), str(new_p))
        assert result.language == "javascript"

    def test_非utf8字节文件_errors_replace保证可读不崩溃(self):
        # encoding="utf-8", errors="replace" 是被锁契约：
        # 无效字节必须被替换字符吸收而不是抛 UnicodeDecodeError
        differ = ASTDiffer()
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            old_p = Path(td) / "a.py"
            new_p = Path(td) / "b.py"
            old_p.write_bytes(b"x = 1\n\xff\xfe garbage \x80\n")
            new_p.write_bytes(b"x = 2\n")
            result = differ.diff_files(str(old_p), str(new_p))
        assert result.language == "python"
        # 旧文件是两条顶层语句(赋值 + 无效字节的垃圾行) → removed×2 + added×1
        assert _kinds(result) == ["removed", "removed", "added"]
        assert result.summary_stats["total_changes"] == 3

    def test_双侧均含非utf8字节_仍可对比(self):
        differ = ASTDiffer()
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            old_p = Path(td) / "a.py"
            new_p = Path(td) / "b.py"
            old_p.write_bytes(b"def f():\n    s = 'a\xff'\n")
            new_p.write_bytes(b"def f():\n    s = 'b\xfe'\n")
            result = differ.diff_files(str(old_p), str(new_p))
        assert result.language == "python"
        assert result.hunks  # 有差异被识别,没有因解码失败而崩
        # 无效字节统一替换为 U+FFFD,有效字节 a/b 差异保留 → 函数体变化
        assert _kinds(result)[0] == "body_changed"

    def test_旧文件不存在_按空源处理_全部新增(self):
        differ = ASTDiffer()
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            new_p = Path(td) / "n.py"
            new_p.write_text("def f():\n    pass\n", encoding="utf-8")
            result = differ.diff_files(str(Path(td) / "missing.py"), str(new_p))
        assert result.language == "python"
        assert _kinds(result) == ["added"]
        assert result.summary_stats["added"] == 1


# ---------- 场景：to_dict 序列化细节 ----------


class TestToDictScenarios:
    def test_节点dict_哈希截12位_预览可选_子节点计数(self):
        node = _node(
            ASTNodeKind.FUNCTION, "f", text_hash="H" * 64, text_preview="def f..."
        )
        node.children = [_node(ASTNodeKind.BLOCK, "b")]
        d = node.to_dict()
        assert d["text_hash"] == "H" * 12
        assert len(d["text_hash"]) == 12
        assert d["preview"] == "def f..."
        assert "children" not in d
        assert "child_count" not in d
        d2 = node.to_dict(with_child_count=True)
        assert d2["child_count"] == 1
        assert "children" not in d2
        d3 = node.to_dict(include_children=True)
        assert "children" in d3 and len(d3["children"]) == 1
        assert "child_count" not in d3

    def test_空预览不产生preview键(self):
        d = _node(ASTNodeKind.FUNCTION, "f").to_dict()
        assert "preview" not in d
        assert d["kind"] == "function"

    def test_hunk_dict_新旧与details按存在裁剪(self):
        hunk_both = ASTDiffHunk(
            DiffKind.SIGNATURE_CHANGED,
            ASTNodeKind.FUNCTION,
            _node(ASTNodeKind.FUNCTION, "f"),
            _node(ASTNodeKind.FUNCTION, "f"),
            "s",
            details={"params_changed": True},
        )
        d = hunk_both.to_dict()
        assert d["old"]["name"] == "f" and d["new"]["name"] == "f"
        assert d["details"] == {"params_changed": True}

        hunk_bare = ASTDiffHunk(
            DiffKind.NODE_ADDED, ASTNodeKind.IMPORT, None, None, "s"
        )
        d2 = hunk_bare.to_dict()
        assert "old" not in d2 and "new" not in d2 and "details" not in d2
        assert d2["kind"] == "added" and d2["node_kind"] == "import"

    def test_结果dict_全链路字段(self):
        differ = ASTDiffer()
        result = differ.diff_strings(
            "a = 1\n", "a = 2\n", "python", old_file="o", new_file="n"
        )
        d = result.to_dict()
        assert d["old_file"] == "o" and d["new_file"] == "n"
        assert d["language"] == "python"
        assert isinstance(d["hunks"], list) and len(d["hunks"]) == 2
        assert d["summary"]["total_changes"] == 2


# ---------- 场景：行号基准（1-based） ----------


class TestLineNumbers:
    def test_顶层节点行号从1计(self):
        differ = ASTDiffer()
        result = differ.diff_strings("x = 1\n", "x = 2\n", "python")
        removed_hunk, added_hunk = result.hunks[0], result.hunks[1]
        assert (
            removed_hunk.old_node is not None and removed_hunk.old_node.start_line == 1
        )
        assert added_hunk.new_node is not None and added_hunk.new_node.start_line == 1

    def test_第二行起点的函数行号为2(self):
        differ = ASTDiffer()
        src_old = "x = 1\n\n\ndef f():\n    pass\n"
        src_new = "x = 1\n\n\ndef f():\n    return 2\n"
        result = differ.diff_strings(src_old, src_new, "python")
        hunk = result.hunks[0]
        assert hunk.old_node.start_line == 4
        assert hunk.old_node.end_line == 5
