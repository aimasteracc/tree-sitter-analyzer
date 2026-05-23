# `git_temporal` test fixtures

Helpers for Feature 2 (Temporal Activation) tests. Builds disposable git
repositories with seeded commits so we can exercise
`tree_sitter_analyzer.git_activation` without touching the developer's real
history.

## Quick start

```python
from tests.fixtures.git_temporal import make_repo

def test_something(tmp_path):
    repo = make_repo(tmp_path, [
        {
            "message": "initial",
            "files": {"src/foo.py": "def foo():\n    return 1\n"},
        },
        {
            "message": "tweak return value",
            "files": {"src/foo.py": "def foo():\n    return 2\n"},
            "date": "5 days ago",
        },
    ])
    # repo is the absolute Path to a fresh working tree.
```

## Commit dict schema

| Key       | Type                       | Required | Notes                                                                 |
|-----------|----------------------------|----------|-----------------------------------------------------------------------|
| `message` | `str`                      | yes      | Commit message.                                                       |
| `files`   | `dict[str, str \| None]`   | yes      | Relative path → content. Use `None` to delete a tracked file.         |
| `date`    | `str`                      | no       | Forwarded to `GIT_AUTHOR_DATE` / `GIT_COMMITTER_DATE`.                |
| `rename`  | `tuple[str, str]`          | no       | `(old_rel, new_rel)` — `git mv` performed BEFORE writing this commit. |

## Conventions

- The repository is created at `tmp_path / "repo"`. Use `repo / "<rel>"` to
  reach individual files.
- Identity is forced to `Test <test@example.com>` inside the repo. We never
  touch the user's global git config (project rule).
- The initial branch is `main` regardless of the host's `init.defaultBranch`.
- Pytest's `tmp_path` cleanup handles teardown automatically — no manual
  cleanup needed.

## Shallow-clone simulation

```python
from tests.fixtures.git_temporal.make_repo import make_shallow_marker

make_shallow_marker(repo)  # writes .git/shallow
```

The production module flags such repos as `git_state == 'shallow'` so the
activation row is still written with zero counts (cold-start semantics).
