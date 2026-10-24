# UQL guidance playbook comparison (2026-10-24), tiny fixture only

**Target: the 10-file fixture project written by `fixture.py`, not TSA.** The plan was to run on TSA itself. C: had about 2.1 GB free, so the run started, but the TSA index grew past 200 MB while free space fell to 1.58 GB. The disk guard killed the build and the partial `.ast-cache` was deleted. Fixture numbers show which way each arm moves. They do **not** show the size of the savings on a real repository, where manual loops are much longer: on TSA, "callers then their tests" took 13 calls in `benchmarks/unified_query/results-2026-10-24.md`.

Tool code: `feature/uql-adoption` at `d4d337b8`. The run used `ANSWER_CACHE_BUDGET_MB=0` and an index built just before it (deleted afterwards). Questions and the stdlib-`ast` oracle come from `benchmarks/unified_query`.

To reproduce:

```
python benchmarks/agent-tasks/uql_guidance/fixture.py <dir>
tree-sitter-analyzer --ast-cache --ast-cache-mode index --project-root <dir>
ANSWER_CACHE_BUDGET_MB=0 python benchmarks/agent-tasks/uql_guidance/playbooks.py --repo fixture --root <dir> --out <out>
```

Arms (scripted playbooks; they show what happens *if* an agent follows each guidance, not whether a model would):

- **old**: the existing single-tool guidance (`plans_today`).
- **all_uql**: one `search action=uql` query for every question (`plans_uql`).
- **routed**: this PR's guidance. Uql for the five multi-hop kinds; `nav` for callers, tests and callees.
- **old_hints**: old guidance, but the agent runs the uql query from `agent_summary.next_step` as soon as a response contains one.

| Q | kind | old calls / bytes / correct | all_uql | routed | old_hints |
| --- | --- | --- | --- | --- | --- |
| Q1 | callers_tests | 3 / 3,481 / exact | 1 / 1,996 / exact | 1 / 1,996 / exact | 3 / 4,814 / exact |
| Q2 | module_untested | 4 / 4,345 / exact | 1 / 2,303 / exact | 1 / 2,303 / exact | 3 / 4,889 / exact |
| Q3 | callers_depth | 1 / 1,223 / exact | 1 / 2,159 / exact | 1 / 2,159 / exact | 1 / 1,223 / exact |
| Q4 | implementers | 2 / 3,403 / exact | 1 / 2,388 / exact | 1 / 2,388 / exact | 2 / 3,403 / exact |
| Q5 | impact | 2 / 2,045 / exact | 1 / 1,905 / exact | 1 / 1,905 / exact | 2 / 3,502 / exact |
| Q6 | callers | 1 / 2,085 / exact | 1 / 1,780 / exact | 1 / 2,085 / exact | 1 / 2,085 / exact |
| Q7 | tests | 1 / 501 / exact | 1 / 1,752 / exact | 1 / 501 / exact | 1 / 501 / exact |
| Q8 | callees | 1 / 1,064 / 0/1 | 1 / 2,188 / 0/1 | 1 / 1,064 / 0/1 | 1 / 1,064 / 0/1 |

| arm | calls | response bytes | one-time discovery bytes | exact answers | wrong `complete` | hint switches |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| old | 15 | 18,147 | 2,868 | 7/8 | 0 | 0 |
| all_uql | 8 | 16,471 | 3,122 | 7/8 | 0 | 0 |
| routed | 8 | 14,401 | 3,122 | 7/8 | 0 | 0 |
| old_hints | 14 | 21,481 | 2,868 | 7/8 | 0 | 3 |

Call sequences: old Q1 `callers+test_map+test_map`, Q2 `callers+test_map×3`, Q5 `caller_tree+test_map`. old_hints switched after the first follow-up: Q1/Q2 `callers+test_map+uql`, Q5 `caller_tree+uql`.

What the numbers say:

- **routed is the cheapest arm:** fewest calls (8, tied with all_uql) and fewest bytes (14,401: -21% vs old, -13% vs all_uql). Correctness is the same in every arm.
- **all_uql pays a fixed ~1.7 KB per answer.** On the one-hop questions this costs more than the single tools: Q7 1,752 vs 501 B, Q8 2,188 vs 1,064 B. Q6 is the exception (1,780 vs 2,085 B). This supports keeping one-hop questions on `nav`.
- **Hints cost bytes on a repo this small.** Each manual loop here is 2–3 callers, so the agent has already paid for the `callers` answer and one `test_map` before the hint appears; adding the uql answer makes old_hints the most expensive arm (+18% vs old). The hint only pays off when the loop is long (TSA Q1: 13 calls). That case is not measured here.
- **Hints fired only where intended:** 3 switches (Q1, Q2, Q5), none on one-hop questions.
- **Q8 is a benchmark bug, not a TSA bug:** `nav callees` returns `fmt_body` and `fmt_header` with `callee_resolution: "local"` (same-file). `plans_today.callees` keeps only `"project"`, and the uql callees parse also returns nothing, so every arm scores 0/1. This probably explains the 0/1 Q8 rows in the earlier TSA/rich results too.
- **Windows path separators:** the no-index fallback path returned `app\doc.py`-style paths. The playbook normalizes them before scoring, and the indexed run here did not depend on that.
