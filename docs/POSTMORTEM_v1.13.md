<!-- HISTORICAL RECORD — file paths in this document reflect the codebase as of 2026. Some paths may no longer exist. Do not update them; they are intentional historical references. -->
# Postmortem — v1.13.0 / v1.13.1 Release Lifecycle

**Window**: PR #133 (feat/consolidated → main) merge through v1.13.1 publish.
**Audience**: future AI agents and human maintainers walking the release path.
**Purpose**: catalogue the failure modes hit during this release so the same shapes are caught earlier next time.

Every entry follows: **Symptom → Root cause → Why generic defenses didn't catch it → Defense added (or to add)**. If the defense is "agent discipline", the rule is in `AGENTS.md` so it survives session resets.

---

## 1. Skip-and-paper-over instead of root-cause-fix

**Symptom**: tests failing in CI were marked `pytest.skip` / `skipif` to get green, hiding three actual product bugs (`call_graph` iteration order, Windows path drift, `get_code_outline` not registered).

**Root cause**: agent reflex under deadline pressure — "make CI green now, file bug later", but "later" never came because the skip removed the failure signal.

**Why generic defenses didn't catch it**: pytest doesn't complain about new skips; PR review doesn't auto-flag them.

**Defense**:
- Agent discipline rule in `AGENTS.md` § Anti-Patterns: any new `pytest.skip*` MUST include an issue or commit reference in the `reason=` string.
- `tests/unit/test_agent_contracts.py::test_skips_have_tracking_references` enforces it for the `tests/` tree.

---

## 2. GitFlow not enforced — random branch names triggered wrong automation

**Symptom**: PR #136 branch was named `hotfix/auto-sprint-action-version` — `hotfix/*` push auto-triggered `hotfix-automation.yml` which attempted a PyPI publish of an already-published 1.13.0 (PyPI rejected 400). Forced a cleanup: close PR, rename branch, force-delete remote.

**Root cause**: branch-naming conventions lived only in `GITFLOW.md` prose. Agents read "fix the auto-sprint workflow" and picked `hotfix/*` because the change is "fixing something" — the word association was wrong but locally rational.

**Why generic defenses didn't catch it**: GH branch protection only protects `main`/`develop` from direct push. It doesn't constrain the head-branch name on PRs.

**Defense** (landed in PR #137):
- `.github/workflows/gitflow-guard.yml` — CI job that fails any PR whose `head→base` pair violates the matrix.
- `AGENTS.md § GitFlow Branching Mandate` — head→base matrix + explicit MUST NEVER list. `hotfix/*` is called out by name.
- `tests/unit/test_agent_contracts.py::test_gitflow_documentation_is_present` — guards against the doc/guard being deleted.

---

## 3. YAML block scalar indentation silently broke `auto-sprint-execute.yml`

**Symptom**: GitHub Actions auto-synthesized a `startup_failure` for every push to `main` for weeks. No job ran, no logs, no email. Tip-off was a red dot in the run history with empty logs.

**Root cause**: `auto-sprint-execute.yml` step had a `run: |` literal block scalar containing a multi-line `git commit -m "..."` and `gh pr create --body "..."`. One continuation line had been re-indented back to column 0, terminating the block early. The trailing lines were then parsed as new top-level YAML keys, which produced an invalid workflow that GH Actions rejected at parser time.

**Why generic defenses didn't catch it**: `pre-commit-hooks: check-yaml` uses `yaml.safe_load` which actually *does* catch this — but the commit that introduced the bug was squash-merged from a branch where pre-commit had been bypassed (likely `--no-verify` or hook failures rescheduled).

**Defense** (landed in PR #138 + this PR):
- The immediate bug: replaced multi-line `-m "..."` strings with multiple `-m` flags and a `printf`-built `$PR_BODY` variable.
- Generic defense: `actionlint` pre-commit hook (this PR) — validates `.github/workflows/*.yml` for both YAML syntax and Actions-specific issues (non-existent action refs, bad expression syntax, etc.). actionlint catches the same class of bug check-yaml does, plus more.

---

## 4. Stale `@v1` action ref produced phantom `startup_failure`

**Symptom**: same `auto-sprint-execute.yml` referenced `anthropics/claude-code-base-action@v1` — a tag that doesn't exist (the action publishes `@beta` only). GH Actions reports this as `startup_failure` with no useful log line, indistinguishable from #3 above.

**Root cause**: copy-paste from documentation that used `@v1` as a placeholder. No reference validation at commit time.

**Why generic defenses didn't catch it**: `check-yaml` parses syntax, not action existence. `Workflow Consistency Tests` pytest doesn't probe action refs.

**Defense** (this PR): `actionlint` pre-commit hook validates every `uses:` ref against the action's actual published refs.

---

## 5. Windows PowerShell 5.1 mojibakes UTF-8 emoji in inline scripts

**Symptom**: `release/v1.13.1` Windows Test Suite jobs failed with `TerminatorExpectedAtEndOfString` on a `Write-Host "✅ ..."` line. The emoji was rendered as `âœ…` (cp1252 misinterpretation of UTF-8 bytes), which broke PowerShell's string scanner.

**Root cause**: GitHub Actions writes the inline `run:` block to a `.ps1` file on the runner. The Windows runner default shell is `powershell` (PowerShell 5.1), which reads `.ps1` as cp1252 by default. UTF-8 emoji from the YAML source get mojibake'd.

**Why generic defenses didn't catch it**: every Linux/macOS run worked fine (bash handles UTF-8 natively), so reviewers never saw the failure mode locally. The bug only surfaced when the Windows job ran in CI.

**Defense** (this PR):
- `scripts/check_ps_ascii.py` — pre-commit hook that fails the commit if any `shell: powershell` `run:` block in `.github/**/*.yml` contains a non-ASCII byte. Use `pwsh` (PowerShell Core, UTF-8 by default) if you really need Unicode.
- Inline `NOTE:` comment header in the affected block so the next agent doesn't re-introduce emoji.

---

## 6. `tree-sitter-c-sharp 0.23.1` ships platform-specific compiled grammars

**Symptom**: PR #134 grammar snapshot regenerated on macOS recorded 229 csharp node types. CI on Linux flagged 5 new ones (`collection_element`, `collection_expression`, `expression_element`, `preproc_if_in_attribute_list`, `spread_element`) — "NEW node type(s) detected!". The macOS wheel exposes 229; the Linux wheel exposes 234.

**Root cause**: `tree-sitter-c-sharp` ships precompiled grammar binaries per platform, and the macOS wheel lags behind on C# 12 collection-expression nodes.

**Why generic defenses didn't catch it**: regression suite generates the snapshot wherever the dev runs it. If that's a macOS laptop, you get the 229-node snapshot.

**Defense** (agent discipline, this PR):
- `AGENTS.md § Anti-Patterns` rule: snapshot regen for tree-sitter grammars MUST be done on the Linux CI runner (or a Linux dev container), not on the local mac. Local dry-run is fine; the committed snapshot must come from Linux.

---

## 7. Python 3.10 compat regression — stdlib `tomllib` / `datetime.UTC`

**Symptom**: `test_agent_contracts.py` and 9 other files used `tomllib` (3.11+) and `from datetime import UTC` (3.11+). Local dev was on 3.14, CI matrix tested 3.10, so 3.10 broke silently in dev and exploded in CI.

**Root cause**: agent typed the "modern" stdlib name without checking the floor version. The repo's `requires-python = ">=3.10"` should be the canonical signal but isn't surfaced at edit time.

**Why generic defenses didn't catch it**: ruff has rules for this (UP017 / UP032) but they were either disabled or applying the wrong target version. Mypy `python_version = "3.10"` should also surface it.

**Defense** (agent discipline + tooling, this PR):
- `AGENTS.md § Anti-Patterns` rule: before using any stdlib symbol new in 3.11+, check the lower bound — `tomllib`, `datetime.UTC`, `Self`, `Required`/`NotRequired`, `assert_type`, structural pattern matching exhaustiveness, etc.
- Confirm `[tool.ruff]` and `[tool.mypy]` both have `target-version = "py310"` / `python_version = "3.10"` — the postmortem checks this in the test contract.

---

## 8. Branch divergence — `develop` rotted 4 commits behind `main`

**Symptom**: `release/v1.13.0` auto-merge to develop brought BACK an older `base_formatter.py` from develop that didn't support JSON format — breaking `test_format_table_json_unsupported`. Required `git checkout origin/main -- ...` cherry-pick to undo. Eventually the user authorized "delete develop, recreate from main".

**Root cause**: develop had been forked from main weeks earlier; main had absorbed PR #133's 95 commits via squash; develop never pulled them in. The release merge-back appeared "successful" but resurrected pre-v1.13 files.

**Why generic defenses didn't catch it**: GitFlow assumes develop ≥ main + active feature work. Nothing alarms when the invariant breaks.

**Defense** (this PR):
- `tests/unit/test_agent_contracts.py::test_develop_not_far_behind_main` — skipped locally (no remote), runs in CI: fails if `git rev-list main..develop` is empty AND `git rev-list develop..main` is non-empty (i.e. develop is strictly behind main).
- Agent-facing rule in `AGENTS.md § Anti-Patterns`: before merging `release/v*` back into develop, run `git log --oneline develop..main` and verify nothing on main is being orphaned.

---

## 9. `--maxfail=10` hid the full failure set

**Symptom**: CI exited after 10 failures, but the actual failing-test count was ~85. Each fix cycle revealed new failures — multi-hour debug loops.

**Root cause**: pytest default `--maxfail=10` is fine for one-feature dev cycles but useless for full-release CI where you want the *complete* failure picture in one run.

**Why generic defenses didn't catch it**: this was a tradeoff baked into pyproject.toml.

**Defense** (already landed):
- `[tool.pytest.ini_options]` bumped `--maxfail=10 → 200` for full-suite CI runs.
- `session-timeout` bumped `300 → 600`.
- `@pytest.mark.slow` filter so the matrix excludes >5s tests.

---

## 10. Squash-merged 95-commit PR is unbisectable

**Symptom**: every regression in #1, #3, #5, #6, #7, #8 above lives somewhere inside the PR #133 squash commit. `git bisect` cannot localize.

**Root cause**: PR #133 was the consolidation PR (`feat/consolidated`) — by design it bundled the full release. Squash strategy was chosen by repo policy.

**Why generic defenses didn't catch it**: it's a policy tradeoff, not a bug.

**Defense** (agent discipline, this PR):
- `AGENTS.md § Anti-Patterns` rule: when a release-prep PR exceeds 30 commits, prefer **rebase-merge** over squash so individual commits remain bisectable on main. Reserve squash for short feature PRs.

---

## Catalogue: what's defended automatically vs. by agent discipline

| Failure mode | Automatic check | Agent rule |
|---|---|---|
| 1. Skip without tracking | `test_skips_have_tracking_references` | `AGENTS.md § Anti-Patterns` |
| 2. Wrong branch name → wrong automation | `gitflow-guard.yml` + `test_gitflow_documentation_is_present` | `AGENTS.md § GitFlow Branching Mandate` |
| 3. YAML block scalar parser bug | `actionlint` pre-commit + `check-yaml` | — |
| 4. Dead action ref | `actionlint` pre-commit | — |
| 5. Non-ASCII in Windows PowerShell | `scripts/check_ps_ascii.py` pre-commit | `AGENTS.md § Anti-Patterns` |
| 6. Snapshot regen on wrong platform | — | `AGENTS.md § Anti-Patterns` |
| 7. 3.11+ stdlib used on 3.10 floor | ruff target-version + mypy python_version | `AGENTS.md § Anti-Patterns` |
| 8. develop rotted behind main | `test_develop_not_far_behind_main` (CI-only) | `AGENTS.md § Anti-Patterns` |
| 9. maxfail hides full failure picture | `pyproject.toml [tool.pytest]` | — |
| 10. Squash-merge buries bisects | — | `AGENTS.md § Anti-Patterns` |

The bias here is intentional: automate what we can express as a deterministic check, document the rest as agent rules so they survive session resets.

---

## Meta-principle

The class of failure that hurts the most is **"silent green"** — CI passes, the test runs, the workflow uploads its artifact, but the underlying contract is violated. Examples in this release:

- skip-and-paper-over (test "passed" because it didn't run)
- `startup_failure` workflow (no failed step because no step ran)
- macOS snapshot covering 229 nodes (test "passed" because it didn't compare against Linux's 234)
- merge-back orphaning v1.13 files (merge "succeeded" because git resolves cleanly when both sides agree on a file)

The remediation pattern across all of them is the same: **add a check that fails when the contract is violated**, not just when the obvious symptom appears. That's what the table above gives.
