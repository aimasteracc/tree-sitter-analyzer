"""RED tests for HealthHomeostasisLoop classifier logic.

Target module (does NOT exist yet):
    tree_sitter_analyzer.health_homeostasis.HealthHomeostasisLoop

Contract under test:
    HealthHomeostasisLoop(
        threshold_grade: str,
        cooldown: float,
        history: HealthHistory,
        notifier: Notifier,           # any callable-like with .dispatch(event)
        scorer: Callable | None = None,
    )
        .on_sync_callback(changed_files: set[str]) -> None
            For each file: recompute via scorer, compare to history.last(),
            emit Notifier event if (a) grade strictly worsened, OR
            (b) grade.now <= threshold AND grade.prev was above threshold.

Grade ordering: A < B < C < D < F (LOWER LETTER == BETTER).
"compare worse" means worse_than('D', 'B') is True.

Classifier MUST suppress:
    - level-only repeats (F→F)
    - improvements (D→B)
    - jitter wholly above threshold

Cooldown: within `cooldown` seconds of last alert for the same file,
suppress further alerts for that file.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# ------------------------------------------------------------------ lazy imports


def _import_loop():
    from tree_sitter_analyzer.health_homeostasis import (  # noqa: WPS433
        HealthHomeostasisLoop,
    )

    return HealthHomeostasisLoop


def _import_history():
    from tree_sitter_analyzer._health_history import HealthHistory  # noqa: WPS433

    return HealthHistory


def _import_ordering():
    """Optional helper: classifier ordering function.

    Spec says A < B < C < D < F (A best). Module MAY expose a public helper —
    fall back to importing whatever the implementation chose."""
    from tree_sitter_analyzer.health_homeostasis import (  # noqa: WPS433
        is_worse_grade,
    )

    return is_worse_grade


# ------------------------------------------------------------------ fixtures


class _FakeScorer:
    """Minimal stand-in for HealthScorer. Maps file→(total, grade) per call."""

    def __init__(self, table: dict[str, tuple[float, str]]) -> None:
        self.table = table
        self.calls: list[str] = []

    def score_file(self, file_path: str):
        self.calls.append(file_path)
        total, grade = self.table[file_path]
        # Return a duck-typed HealthScore: .file_path, .total, .grade, .dimensions
        score = MagicMock()
        score.file_path = file_path
        score.total = total
        score.grade = grade
        score.dimensions = {}
        return score


@pytest.fixture
def project_root(tmp_path: Path) -> str:
    (tmp_path / ".ast-cache").mkdir(parents=True, exist_ok=True)
    return str(tmp_path)


@pytest.fixture
def history(project_root: str):
    HealthHistory = _import_history()
    h = HealthHistory(project_root)
    yield h
    close = getattr(h, "close", None)
    if callable(close):
        close()


@pytest.fixture
def notifier():
    """Mock notifier with .dispatch(event_dict)."""
    n = MagicMock()
    n.dispatch = MagicMock()
    return n


@pytest.fixture
def make_loop(history, notifier):
    """Factory: build a loop with mocked scorer + given threshold/cooldown."""

    def _make(
        threshold_grade: str = "C",
        cooldown: float = 0.0,
        scorer_table: dict[str, tuple[float, str]] | None = None,
    ):
        HealthHomeostasisLoop = _import_loop()
        scorer = _FakeScorer(scorer_table or {})
        return HealthHomeostasisLoop(
            threshold_grade=threshold_grade,
            cooldown=cooldown,
            history=history,
            notifier=notifier,
            scorer=scorer,
        )

    return _make


# ------------------------------------------------------------------ classifier helper


def test_classifier_grade_ordering() -> None:
    """Spec: A < B < C < D < F (A is best, F is worst).

    is_worse_grade(new, prev) must return True when `new` is worse than `prev`.
    """
    is_worse_grade = _import_ordering()

    # Worsening cases.
    assert is_worse_grade("B", "A") is True
    assert is_worse_grade("D", "B") is True
    assert is_worse_grade("F", "A") is True

    # Improvement cases.
    assert is_worse_grade("A", "B") is False
    assert is_worse_grade("B", "F") is False

    # Equality is not "worse".
    assert is_worse_grade("C", "C") is False


# ------------------------------------------------------------------ drop / improvement


def test_loop_alerts_on_grade_drop(make_loop, history, notifier) -> None:
    """History has file→B. Recompute yields file→D. Expect 1 alert."""
    history.append("/repo/main.py", score=82.0, grade="B")

    loop = make_loop(
        threshold_grade="F",  # high threshold so only the drop matters
        scorer_table={"/repo/main.py": (55.0, "D")},
    )
    loop.on_sync_callback({"/repo/main.py"})

    assert notifier.dispatch.call_count == 1
    event = notifier.dispatch.call_args.args[0]
    assert event["file"] == "/repo/main.py"
    assert event["previous_grade"] == "B"
    assert event["grade"] == "D"


def test_loop_silent_on_grade_improvement(make_loop, history, notifier) -> None:
    """History has file→D. Recompute yields file→B. Expect 0 alerts."""
    history.append("/repo/main.py", score=55.0, grade="D")

    loop = make_loop(
        threshold_grade="F",
        scorer_table={"/repo/main.py": (82.0, "B")},
    )
    loop.on_sync_callback({"/repo/main.py"})

    assert notifier.dispatch.call_count == 0


def test_loop_silent_on_grade_unchanged(make_loop, history, notifier) -> None:
    """History has file→C. Recompute yields file→C (level repeat). Expect 0 alerts."""
    history.append("/repo/main.py", score=75.0, grade="C")

    loop = make_loop(
        threshold_grade="F",
        scorer_table={"/repo/main.py": (75.0, "C")},
    )
    loop.on_sync_callback({"/repo/main.py"})

    assert notifier.dispatch.call_count == 0


# ------------------------------------------------------------------ edge-trigger


def test_loop_alerts_on_first_drop_below_threshold_edge_trigger(
    make_loop, history, notifier
) -> None:
    """threshold=C; prev=B (above), now=D (below) → 1 alert."""
    history.append("/repo/a.py", score=82.0, grade="B")

    loop = make_loop(
        threshold_grade="C",
        scorer_table={"/repo/a.py": (55.0, "D")},
    )
    loop.on_sync_callback({"/repo/a.py"})

    assert notifier.dispatch.call_count == 1


def test_loop_no_alert_when_already_below_threshold_no_drop(
    make_loop, history, notifier
) -> None:
    """threshold=C; prev=D (already below), now=F (still below, but worse).

    Spec is: edge-trigger fires only on the *crossing*. F is strictly worse
    than D, so rule (a) (strict worsening) DOES fire. Verify we still get
    exactly 1 event (the worsening rule), not 0 and not 2.
    """
    history.append("/repo/a.py", score=55.0, grade="D")

    loop = make_loop(
        threshold_grade="C",
        scorer_table={"/repo/a.py": (35.0, "F")},
    )
    loop.on_sync_callback({"/repo/a.py"})

    # Rule (a) — strict worsening — fires exactly once.
    assert notifier.dispatch.call_count == 1


def test_loop_no_alert_on_level_repeat_below_threshold(
    make_loop, history, notifier
) -> None:
    """threshold=C; prev=F, now=F → 0 alerts. Level-only entries suppressed."""
    history.append("/repo/a.py", score=20.0, grade="F")

    loop = make_loop(
        threshold_grade="C",
        scorer_table={"/repo/a.py": (20.0, "F")},
    )
    loop.on_sync_callback({"/repo/a.py"})

    assert notifier.dispatch.call_count == 0


# ------------------------------------------------------------------ cold start


def test_cold_start_alerts_only_below_threshold(make_loop, notifier) -> None:
    """No prior row; threshold=C.

    now=D → 1 alert (cold + below).
    now=A → 0 alerts (cold + above).
    """
    loop = make_loop(
        threshold_grade="C",
        scorer_table={
            "/repo/below.py": (55.0, "D"),
            "/repo/above.py": (95.0, "A"),
        },
    )

    loop.on_sync_callback({"/repo/below.py"})
    loop.on_sync_callback({"/repo/above.py"})

    assert notifier.dispatch.call_count == 1
    event = notifier.dispatch.call_args.args[0]
    assert event["file"] == "/repo/below.py"
    assert event["grade"] == "D"
    # previous_grade is None / absent on cold start.
    assert event.get("previous_grade") in (None, "")


def test_cold_start_at_threshold_alerts(make_loop, notifier) -> None:
    """threshold=C; no prior row; now=C → 1 alert (<= threshold edge fires).

    Spec rule (b): grade.now <= threshold. C <= C is True.
    """
    loop = make_loop(
        threshold_grade="C",
        scorer_table={"/repo/x.py": (75.0, "C")},
    )
    loop.on_sync_callback({"/repo/x.py"})

    assert notifier.dispatch.call_count == 1


# ------------------------------------------------------------------ cooldown


def test_cooldown_suppresses_repeat_alerts_same_file(
    make_loop, history, notifier
) -> None:
    """5 calls within cooldown window for the same alert-worthy file → 1 alert."""
    history.append("/repo/flaky.py", score=82.0, grade="B")

    loop = make_loop(
        threshold_grade="F",  # don't trip the edge rule
        cooldown=60.0,  # long window — all 5 calls fall inside
        scorer_table={"/repo/flaky.py": (55.0, "D")},
    )

    for _ in range(5):
        loop.on_sync_callback({"/repo/flaky.py"})

    assert notifier.dispatch.call_count == 1


def test_cooldown_does_not_cross_files(make_loop, history, notifier) -> None:
    """Cooldown is per-file. fileA cooldown does not suppress fileB alert."""
    history.append("/repo/a.py", score=82.0, grade="B")
    history.append("/repo/b.py", score=82.0, grade="B")

    loop = make_loop(
        threshold_grade="F",
        cooldown=60.0,
        scorer_table={
            "/repo/a.py": (55.0, "D"),
            "/repo/b.py": (55.0, "D"),
        },
    )

    loop.on_sync_callback({"/repo/a.py"})
    loop.on_sync_callback({"/repo/b.py"})

    assert notifier.dispatch.call_count == 2


def test_cooldown_expires_allows_new_alert(make_loop, history, notifier) -> None:
    """After cooldown window elapses, a new alert is allowed for the same file."""
    history.append("/repo/main.py", score=82.0, grade="B")

    loop = make_loop(
        threshold_grade="F",
        cooldown=0.05,  # 50ms — short for test speed
        scorer_table={"/repo/main.py": (55.0, "D")},
    )

    loop.on_sync_callback({"/repo/main.py"})
    time.sleep(0.1)
    # Seed prev=B again (the last() should reflect prior D row, but worsening
    # rule still requires comparison — re-seed to keep semantics consistent).
    history.append("/repo/main.py", score=82.0, grade="B")
    loop.on_sync_callback({"/repo/main.py"})

    assert notifier.dispatch.call_count == 2


# ------------------------------------------------------------------ threshold filter


def test_threshold_filter_suppresses_jitter_above_threshold(history, notifier) -> None:
    """threshold=C; chain B→A→B → 0 alerts (all hovering above threshold).

    Strict-worse rule (a) would fire on the A→B step. But spec says the
    classifier suppresses jitter wholly above threshold. Implementations
    should gate rule (a) on `min(prev, now) <= threshold` OR require
    crossing the threshold to fire.

    NB: This test encodes the spec's stated behavior — "Level-only entries
    (F→F repeated) suppressed. Threshold filter suppresses jitter above
    threshold." If the implementation chooses to fire on all strict
    worsenings regardless of threshold, this test flags a spec ambiguity.
    """
    HealthHomeostasisLoop = _import_loop()
    history.append("/repo/jitter.py", score=82.0, grade="B")

    # Two-step chain — build a stateful scorer whose table swaps between calls.
    scorer = _FakeScorer({"/repo/jitter.py": (95.0, "A")})
    loop = HealthHomeostasisLoop(
        threshold_grade="C",
        cooldown=0.0,
        history=history,
        notifier=notifier,
        scorer=scorer,
    )
    loop.on_sync_callback({"/repo/jitter.py"})  # B → A (improvement, silent)

    # Now: A → B. Strict worsening, but both above threshold.
    history.append("/repo/jitter.py", score=95.0, grade="A")
    scorer.table["/repo/jitter.py"] = (82.0, "B")
    loop.on_sync_callback({"/repo/jitter.py"})

    assert notifier.dispatch.call_count == 0


# ------------------------------------------------------------------ event payload


def test_alert_event_contains_template_tokens(make_loop, history, notifier) -> None:
    """Emitted event dict must include the tokens the Notifier needs:
    file, grade, previous_grade, delta_score, timestamp_iso, recommendation."""
    history.append("/repo/main.py", score=82.0, grade="B")

    loop = make_loop(
        threshold_grade="F",
        scorer_table={"/repo/main.py": (55.0, "D")},
    )
    loop.on_sync_callback({"/repo/main.py"})

    assert notifier.dispatch.call_count == 1
    event = notifier.dispatch.call_args.args[0]

    for key in ("file", "grade", "previous_grade", "delta_score", "timestamp_iso"):
        assert key in event, f"event missing required token: {key}"

    # delta is computed as new_score - prev_score; D(55) - B(82) = -27.
    assert event["delta_score"] == pytest.approx(-27.0)
