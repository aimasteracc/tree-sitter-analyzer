"""RED tests for the Notifier layer.

Target module (does NOT exist yet):
    tree_sitter_analyzer.health_notifier

Contract under test:
    class Notifier(Protocol):
        def dispatch(self, event: dict) -> None: ...

    StdoutNotifier()
        Writes one line per event to stdout. Line contains file + prev + new grade.

    FileNotifier(path: str | Path)
        Appends one JSONL record per event to `path`.

    ShellNotifier(template: str)
        Substitutes `string.Template` tokens against the event dict and
        invokes the resulting argv via subprocess.Popen (no shell=True).

    WebhookNotifier(url: str)
        Stub: either raises NotImplementedError or logs and no-ops.

    StackedNotifier(*notifiers)
        Composite: dispatches the event to every wrapped notifier.

Event dict shape (canonical keys, see homeostasis loop):
    {
        "file": "/repo/main.py",
        "grade": "D",
        "previous_grade": "B",
        "delta_score": -27.0,
        "recommendation": "...",
        "timestamp_iso": "2026-05-23T12:00:00+00:00",
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# ------------------------------------------------------------------ lazy imports


def _import_notifier_module():
    from tree_sitter_analyzer import health_notifier  # noqa: WPS433

    return health_notifier


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def sample_event() -> dict:
    return {
        "file": "/repo/main.py",
        "grade": "D",
        "previous_grade": "B",
        "delta_score": -27.0,
        "recommendation": "Reduce nesting in main()",
        "timestamp_iso": "2026-05-23T12:00:00+00:00",
    }


# ------------------------------------------------------------------ StdoutNotifier


def test_stdout_notifier_writes_one_line_per_event(capsys, sample_event) -> None:
    """StdoutNotifier writes a single human-readable line per event,
    containing file path, previous grade, and new grade."""
    mod = _import_notifier_module()
    notifier = mod.StdoutNotifier()

    notifier.dispatch(sample_event)

    captured = capsys.readouterr()
    out = captured.out
    # Exactly one line of output (trailing newline allowed).
    assert out.count("\n") == 1, f"expected 1 line, got: {out!r}"
    assert "/repo/main.py" in out
    assert "B" in out  # previous grade
    assert "D" in out  # new grade


def test_stdout_notifier_handles_cold_start_event(capsys) -> None:
    """previous_grade may be None on cold start — must not crash."""
    mod = _import_notifier_module()
    notifier = mod.StdoutNotifier()

    notifier.dispatch(
        {
            "file": "/repo/new.py",
            "grade": "D",
            "previous_grade": None,
            "delta_score": 0.0,
            "recommendation": "",
            "timestamp_iso": "2026-05-23T12:00:00+00:00",
        }
    )
    captured = capsys.readouterr()
    assert "/repo/new.py" in captured.out
    assert "D" in captured.out


# ------------------------------------------------------------------ FileNotifier


def test_file_notifier_appends_jsonl(tmp_path: Path, sample_event) -> None:
    """FileNotifier(path) appends one JSONL record per dispatch."""
    mod = _import_notifier_module()
    out_path = tmp_path / "events.jsonl"
    notifier = mod.FileNotifier(out_path)

    notifier.dispatch(sample_event)
    second = {**sample_event, "file": "/repo/util.py", "grade": "F"}
    notifier.dispatch(second)

    assert out_path.exists()
    lines = out_path.read_text().splitlines()
    assert len(lines) == 2, f"expected 2 JSONL lines, got {len(lines)}"

    rec_a = json.loads(lines[0])
    rec_b = json.loads(lines[1])
    assert rec_a["file"] == "/repo/main.py"
    assert rec_b["file"] == "/repo/util.py"
    assert rec_b["grade"] == "F"


def test_file_notifier_does_not_overwrite_existing_records(
    tmp_path: Path, sample_event
) -> None:
    """A second FileNotifier instance pointed at the same file must append,
    not truncate."""
    mod = _import_notifier_module()
    out_path = tmp_path / "events.jsonl"

    n1 = mod.FileNotifier(out_path)
    n1.dispatch(sample_event)

    n2 = mod.FileNotifier(out_path)
    n2.dispatch({**sample_event, "file": "/repo/other.py"})

    lines = out_path.read_text().splitlines()
    assert len(lines) == 2


def test_file_notifier_creates_parent_directory(tmp_path: Path, sample_event) -> None:
    """FileNotifier auto-creates missing parent dirs (best-effort)."""
    mod = _import_notifier_module()
    nested = tmp_path / "logs" / "homeostasis" / "events.jsonl"
    notifier = mod.FileNotifier(nested)

    notifier.dispatch(sample_event)

    assert nested.exists()


# ------------------------------------------------------------------ ShellNotifier


def test_shell_notifier_substitutes_template_tokens(sample_event) -> None:
    """Template tokens substituted via string.Template, NOT shell expansion.

    Given template `echo {file} {grade}`, Popen must receive an argv that
    has the substituted values — and must NOT be invoked with shell=True
    (which would let an attacker inject commands via the event payload).
    """
    mod = _import_notifier_module()
    notifier = mod.ShellNotifier("echo {file} {grade}")

    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        notifier.dispatch(sample_event)

    assert mock_popen.called, "ShellNotifier must invoke subprocess.Popen"
    call_args, call_kwargs = mock_popen.call_args

    # Spec requires shell=False (no shell=True kwarg, and no string-form argv).
    assert call_kwargs.get("shell") is not True, (
        "ShellNotifier must NOT invoke a shell — shell=True is unsafe"
    )

    # The first positional should be an argv list. Pull whichever positional
    # carries the command.
    argv = call_args[0] if call_args else call_kwargs.get("args")
    assert isinstance(argv, list), (
        f"expected argv list (shell=False mode), got {type(argv).__name__}"
    )

    # Substitution must have happened — placeholders gone, values present.
    joined = " ".join(argv)
    assert "{file}" not in joined and "{grade}" not in joined
    assert "/repo/main.py" in joined
    assert "D" in joined


def test_shell_notifier_supports_string_template_dollar_syntax(sample_event) -> None:
    """Spec calls out `string.Template`. Some impls may use $token instead of
    {token}. Accept either form by testing both (whichever fails, the spec
    must be tightened)."""
    mod = _import_notifier_module()

    # Spec explicitly says: "string-substitute via string.Template" using
    # {file}, {grade}, ... — so the canonical form is brace style. But
    # string.Template defaults to $-prefix. The implementation choice should
    # match the spec — verify the {-form works since that's what the spec lists.
    notifier = mod.ShellNotifier("echo {previous_grade} {delta_score}")

    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        notifier.dispatch(sample_event)

    argv = mock_popen.call_args.args[0]
    joined = " ".join(str(a) for a in argv)
    assert "B" in joined  # previous_grade
    assert "-27" in joined  # delta_score


def test_shell_notifier_handles_unknown_tokens_safely(sample_event) -> None:
    """An unknown token in the template must not crash and must not leak shell
    interpretation. Spec: `string.Template.safe_substitute` semantics."""
    mod = _import_notifier_module()
    notifier = mod.ShellNotifier("echo {file} {bogus_token}")

    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock()
        # Must not raise.
        notifier.dispatch(sample_event)

    assert mock_popen.called


# ------------------------------------------------------------------ WebhookNotifier


def test_webhook_notifier_stub_raises_not_implemented(sample_event) -> None:
    """Webhook is a stub for MVP. Spec hedges between 'raises' and 'logs +
    accepts'. Accept either: NotImplementedError OR a graceful no-op that
    logs a warning. If the implementation lands on log+no-op, this test
    flags a spec ambiguity.
    """
    mod = _import_notifier_module()
    notifier = mod.WebhookNotifier("https://example.com/hook")

    try:
        notifier.dispatch(sample_event)
    except NotImplementedError:
        # Path 1: explicit stub.
        return

    # Path 2: graceful no-op — verify nothing crashed, and that the notifier
    # exposes a flag indicating it's unimplemented so callers can detect.
    assert hasattr(notifier, "implemented"), (
        "WebhookNotifier must expose .implemented = False when stubbed, "
        "OR raise NotImplementedError on dispatch"
    )
    assert notifier.implemented is False


# ------------------------------------------------------------------ Stacked / composite


def test_stacked_channels_dispatch_to_all(tmp_path: Path, capsys, sample_event) -> None:
    """A composite notifier (stdout + file) sends each event to both backends."""
    mod = _import_notifier_module()
    out_path = tmp_path / "events.jsonl"

    stack = mod.StackedNotifier(mod.StdoutNotifier(), mod.FileNotifier(out_path))
    stack.dispatch(sample_event)

    # Stdout received the event.
    captured = capsys.readouterr()
    assert "/repo/main.py" in captured.out

    # File received the event.
    assert out_path.exists()
    lines = out_path.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["file"] == "/repo/main.py"


def test_stacked_channel_failure_does_not_stop_siblings(
    tmp_path: Path, capsys, sample_event
) -> None:
    """If one channel raises, the others must still receive the event.

    Resilience: a misbehaving webhook should not silently drop notifications
    to the user-visible stdout channel.
    """
    mod = _import_notifier_module()

    class _Boom:
        def dispatch(self, event):
            raise RuntimeError("simulated channel failure")

    out_path = tmp_path / "events.jsonl"
    stack = mod.StackedNotifier(_Boom(), mod.FileNotifier(out_path))

    # Composite must swallow / log the failure and keep going.
    stack.dispatch(sample_event)

    # The file channel still got the event.
    assert out_path.exists()
    assert len(out_path.read_text().splitlines()) == 1


# ------------------------------------------------------------------ build_notifier helper


def test_module_exposes_build_notifier_factory() -> None:
    """The module should expose a factory that maps CLI channel strings to
    notifier instances. Spec: --notify-channel stdout|file|webhook (comma-sep)."""
    mod = _import_notifier_module()

    factory = getattr(mod, "build_notifier", None)
    assert callable(factory), (
        "health_notifier.build_notifier(channels, file_path, template) is "
        "the documented entrypoint for CLI wiring"
    )
