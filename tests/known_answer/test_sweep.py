"""``scripts.wrong_complete.sweep`` / ``candidates`` 的单元测试（夜间扫描的评分与抽样）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.wrong_complete import sweep
from scripts.wrong_complete.candidates import (
    Candidate,
    java_methods,
    python_methods,
    sample,
)
from scripts.wrong_complete.sites import POSSIBLE, Site, Target

_TARGET = Target("rich/live.py", "process_renderables", "Live", 5)
_SITE = Site("rich/console.py", 18, "call", POSSIBLE, "unresolved_receiver", "render")
_CANDIDATE = Candidate(_TARGET, 1)


def _answers(completeness: str) -> dict[str, dict[str, Any]]:
    return {mode: {"completeness": completeness, "callers": []} for mode in sweep.MODES}


def test_judge_reports_a_wrong_complete_in_both_modes() -> None:
    # #1758：``Live.process_renderables`` 曾答 complete, 0。
    row = sweep.judge(_CANDIDATE, _answers("complete"), [_SITE], {}, {}, "rich")
    assert [row[m]["wrong"] for m in sweep.MODES] == [
        [
            {
                "file": "rich/console.py",
                "line": 18,
                "verdict": POSSIBLE,
                "reason": "unresolved_receiver",
                "caller": "render",
            }
        ]
    ] * 2


def test_judge_drops_reviewed_exclusions() -> None:
    exclusions = {
        ("rich", "Live.process_renderables", "rich/console.py", 18): "reviewed"
    }
    row = sweep.judge(_CANDIDATE, _answers("complete"), [_SITE], {}, exclusions, "rich")
    assert [(row[m]["wrong"], row[m]["excluded"]) for m in sweep.MODES] == [
        ([], 1),
        ([], 1),
    ]


def test_judge_ignores_non_complete_answers() -> None:
    row = sweep.judge(_CANDIDATE, _answers("unknown"), [_SITE], {}, {}, "rich")
    assert [(row[m]["wrong"], row[m]["silent"]) for m in sweep.MODES] == [
        ([], 1),
        ([], 1),
    ]


def test_summarize_counts_targets_and_sites() -> None:
    wrong = sweep.judge(_CANDIDATE, _answers("complete"), [_SITE], {}, {}, "rich")
    fine = sweep.judge(_CANDIDATE, _answers("unknown"), [_SITE], {}, {}, "rich")
    summary = sweep.summarize([wrong, fine])
    assert summary == {
        "n": 2,
        "bare": {
            "complete": 1,
            "wrong_complete_targets": 1,
            "wrong_complete_sites": 1,
            "excluded_sites": 0,
        },
        "qualified": {
            "complete": 1,
            "wrong_complete_targets": 1,
            "wrong_complete_sites": 1,
            "excluded_sites": 0,
        },
    }


def test_exclusions_are_filtered_by_repo_label(tmp_path: Path) -> None:
    path = tmp_path / "exclusions.json"
    rows = [
        {"repo": "rich", "target": "A.b", "file": "x.py", "line": 3, "reason": "r1"},
        {"repo": "gson", "target": "C.d", "file": "Y.java", "line": 4, "reason": "r2"},
    ]
    path.write_text(json.dumps(rows), encoding="utf-8")
    assert sweep.load_exclusions(path, "rich") == {("rich", "A.b", "x.py", 3): "r1"}


def test_the_committed_exclusions_file_is_reviewed_and_well_formed() -> None:
    # 排除项必须逐条写明理由；文件为空列表时 nightly 不放过任何错误 complete。
    path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "wrong_complete"
        / "exclusions.json"
    )
    rows = json.loads(path.read_text(encoding="utf-8"))
    bad = [
        r
        for r in rows
        if set(r) != {"repo", "target", "file", "line", "reason"}
        or not r["reason"].strip()
    ]
    assert bad == []


def test_main_exits_non_zero_on_a_wrong_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = sweep.judge(_CANDIDATE, _answers("complete"), [_SITE], {}, {}, "rich")

    async def fake_run(args: Any) -> dict[str, Any]:
        return {"label": "rich", "summary": sweep.summarize([row]), "rows": [row]}

    monkeypatch.setattr(sweep, "_run", fake_run)
    out = tmp_path / "scores.json"
    code = sweep.main(["--repo", str(tmp_path), "--lang", "py", "--out", str(out)])
    assert (
        code,
        json.loads(out.read_text(encoding="utf-8"))["summary"]["bare"][
            "wrong_complete_sites"
        ],
    ) == (1, 1)


def test_main_exits_zero_without_wrong_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = sweep.judge(_CANDIDATE, _answers("unknown"), [_SITE], {}, {}, "rich")

    async def fake_run(args: Any) -> dict[str, Any]:
        return {"label": "rich", "summary": sweep.summarize([row]), "rows": [row]}

    monkeypatch.setattr(sweep, "_run", fake_run)
    assert (
        sweep.main(
            ["--repo", str(tmp_path), "--lang", "py", "--out", str(tmp_path / "s.json")]
        )
        == 0
    )


def test_python_methods_are_enumerated_with_their_class(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(
        "class A:\n    def run(self):\n        pass\n\n\ndef free():\n    pass\n",
        encoding="utf-8",
    )
    assert python_methods(tmp_path, ["m.py"]) == [Target("m.py", "run", "A", 2)]


def test_java_methods_skip_constructors_and_calls(tmp_path: Path) -> None:
    text = (
        "public final class Gson {\n"
        "  public Gson() {\n"
        "  }\n"
        "  public Object getDelegateAdapter(Object a) {\n"
        "    return toJson(a);\n"
        "  }\n"
        "}\n"
    )
    (tmp_path / "Gson.java").write_text(text, encoding="utf-8")
    assert java_methods(tmp_path, ["Gson.java"]) == [
        Target("Gson.java", "getDelegateAdapter", "Gson", 4)
    ]


def test_sample_picks_single_definition_methods_with_call_lines(tmp_path: Path) -> None:
    # 临时目录里的小项目，不扫描本仓库（#1779 教训）。
    files = {
        "a.py": "class A:\n    def render_all(self):\n        return 1\n\n    def unused_one(self):\n        return 2\n",
        "b.py": "from a import A\n\n\ndef go(x: A):\n    return x.render_all()\n",
        "c.py": "class C:\n    def render_all(self):\n        return 3\n\n    def solo_call(self):\n        return self.render_all()\n",
        "d.py": "def go2(c):\n    return c.solo_call()\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).write_text(text, encoding="utf-8")
    picked = sample(tmp_path, "py", 1, 10, files=sorted(files))
    assert [c.target.qualified for c in picked] == ["C.solo_call"]
